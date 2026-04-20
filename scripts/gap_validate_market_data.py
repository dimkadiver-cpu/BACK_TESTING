from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src.signal_chain_lab.market.planning.gap_detection import Interval
from src.signal_chain_lab.market.planning.validation import BatchValidator, IssueSeverity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate only newly synced market-data gaps")
    parser.add_argument("--plan-file", required=True, help="Plan JSON produced by plan_market_data.py")
    parser.add_argument("--sync-file", required=True, help="Sync report JSON produced by sync_market_data.py")
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional gap-validation report JSON path; default under artifacts/market_data/",
    )
    return parser.parse_args()


def _build_gap_jobs(
    *,
    plan: dict[str, object],
    sync_report: dict[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    # Index sync results by (symbol, basis, timeframe); fall back to (symbol, basis) for legacy reports
    sync_results = sync_report.get("results", [])
    sync_index: dict[tuple[str, str, str], dict[str, object]] = {}
    sync_index_legacy: dict[tuple[str, str], dict[str, object]] = {}
    if isinstance(sync_results, list):
        for row in sync_results:
            if isinstance(row, dict):
                symbol = str(row.get("symbol") or "")
                basis = str(row.get("basis") or "")
                timeframe = str(row.get("timeframe") or "")
                if symbol and basis and timeframe:
                    sync_index[(symbol, basis, timeframe)] = row
                elif symbol and basis:
                    sync_index_legacy[(symbol, basis)] = row

    download_tfs: list[str] = list(plan.get("download_tfs") or [str(plan.get("timeframe", "1m"))])

    jobs: list[dict[str, object]] = []
    sync_issues: list[dict[str, object]] = []
    symbols_payload = plan.get("symbols", {})
    if not isinstance(symbols_payload, dict):
        return jobs, sync_issues

    for symbol, basis_payload in symbols_payload.items():
        if not isinstance(basis_payload, dict):
            continue
        for basis, entry in basis_payload.items():
            if not isinstance(entry, dict):
                continue
            gaps = [Interval.from_dict(item) for item in entry.get("gaps", [])]
            if not gaps:
                continue

            for tf in download_tfs:
                sync_row = sync_index.get((str(symbol), str(basis), tf))
                if sync_row is None:
                    # Legacy fallback: sync report without timeframe field
                    sync_row = sync_index_legacy.get((str(symbol), str(basis)))
                if sync_row is None:
                    sync_issues.append(
                        {
                            "symbol": symbol,
                            "basis": basis,
                            "timeframe": tf,
                            "status": "FAIL",
                            "reason": "missing_sync_result",
                        }
                    )
                    continue

                sync_status = str(sync_row.get("status") or "").lower()
                if sync_status != "ok":
                    sync_issues.append(
                        {
                            "symbol": symbol,
                            "basis": basis,
                            "timeframe": tf,
                            "status": "FAIL",
                            "reason": "sync_not_ok",
                            "sync_status": sync_status or "unknown",
                        }
                    )
                    continue

                for interval in gaps:
                    jobs.append({"symbol": symbol, "basis": basis, "timeframe": tf, "interval": interval})

    return jobs, sync_issues


def main() -> int:
    args = parse_args()
    plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    sync_report = json.loads(Path(args.sync_file).read_text(encoding="utf-8"))
    market_dir = Path(args.market_dir)
    validator = BatchValidator()

    jobs, sync_issues = _build_gap_jobs(plan=plan, sync_report=sync_report)
    cache: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    results: list[dict[str, object]] = []
    has_critical = bool(sync_issues)
    total_checks = len(jobs)
    by_timeframe: dict[str, dict[str, int]] = {}

    print("PHASE=gap_validate")
    print(f"STEP=0/{total_checks}")
    print("PROGRESS=0")

    for item in sync_issues:
        tf = str(item.get("timeframe", ""))
        results.append(
            {
                "symbol": item["symbol"],
                "basis": item["basis"],
                "timeframe": tf,
                "interval": None,
                "status": "FAIL",
                "issues": [
                    {
                        "severity": IssueSeverity.CRITICAL.value,
                        "code": "GAP_SYNC_STATUS_INVALID",
                        "message": f"gap sync non valido: {item['reason']} ({item.get('sync_status', 'n/a')})",
                    }
                ],
            }
        )
        tf_stats = by_timeframe.setdefault(tf, {"passed": 0, "failed": 0, "warnings": 0})
        tf_stats["failed"] += 1

    for idx, job in enumerate(jobs, start=1):
        symbol = str(job["symbol"])
        basis = str(job["basis"])
        tf = str(job["timeframe"])
        interval = job["interval"]
        cache_key = (symbol, basis, tf)
        if cache_key not in cache:
            partition_dir = market_dir / "bybit" / "futures_linear" / tf / symbol
            files = sorted(partition_dir.glob(f"*.{basis}.parquet"))
            print(
                f"loading_gap_cache symbol={symbol} basis={basis} tf={tf} "
                f"partition_dir={partition_dir} files={len(files)}"
            )
            frames = [pd.read_parquet(path) for path in files]
            rows: list[dict[str, object]] = []
            if frames:
                df = pd.concat(frames, ignore_index=True)
                rows = df.to_dict(orient="records")
            cache[cache_key] = rows
            print(f"loaded_gap_cache symbol={symbol} basis={basis} tf={tf} files={len(files)} rows={len(rows)}")

        result = validator.validate(rows=cache[cache_key], requested_range=interval)
        issues = [{"severity": issue.severity.value, "code": issue.code, "message": issue.message} for issue in result.issues]
        status = "PASS" if not result.has_errors else "FAIL"
        has_critical = has_critical or result.has_errors
        tf_stats = by_timeframe.setdefault(tf, {"passed": 0, "failed": 0, "warnings": 0})
        if result.has_errors:
            tf_stats["failed"] += 1
        else:
            tf_stats["passed"] += 1
        tf_stats["warnings"] += result.warning_count
        print(f"STEP={idx}/{total_checks}")
        print(f"PROGRESS={int(idx / max(total_checks, 1) * 100)}")
        print(f"gap_validate_progress {idx}/{total_checks} symbol={symbol} basis={basis} tf={tf} status={status}")
        results.append(
            {
                "symbol": symbol,
                "basis": basis,
                "timeframe": tf,
                "interval": interval.to_dict(),
                "status": status,
                "critical_count": result.critical_count,
                "warning_count": result.warning_count,
                "info_count": result.info_count,
                "issues": issues,
            }
        )

    output = Path(args.output) if args.output else Path("artifacts/market_data/gap_validate_market_data.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "market_request_fingerprint": plan.get("market_request_fingerprint", ""),
                "status": "PASS" if not has_critical else "FAIL",
                "checks": len(results),
                "critical_count": sum(int(r.get("critical_count", 0)) for r in results),
                "warning_count": sum(int(r.get("warning_count", 0)) for r in results),
                "info_count": sum(int(r.get("info_count", 0)) for r in results),
                "by_timeframe": by_timeframe,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    warning_count = sum(int(r.get("warning_count", 0)) for r in results)
    overall = "PASS" if not has_critical else "FAIL"
    print(f"SUMMARY=pass:{sum(1 for r in results if r['status'] == 'PASS')} fail:{sum(1 for r in results if r['status'] == 'FAIL')} warnings:{warning_count}")
    print(f"gap_validation_report={output}")
    print(f"status={overall}")
    print(f"checks={len(results)}")
    return 0 if not has_critical else 1


if __name__ == "__main__":
    raise SystemExit(main())
