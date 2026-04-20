from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from src.signal_chain_lab.market.planning.gap_detection import Interval
from src.signal_chain_lab.market.planning.manifest_store import ManifestStore
from src.signal_chain_lab.market.planning.validation import BatchValidator, IssueSeverity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local market-data coverage against a saved plan")
    parser.add_argument("--plan-file", required=True, help="Plan JSON produced by plan_market_data.py")
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional validation report JSON path; default under artifacts/market_data/",
    )
    parser.add_argument("--strict", action="store_true", help="Fail on WARNING in addition to CRITICAL")
    parser.add_argument(
        "--sync-file",
        default=None,
        help="Optional sync report JSON; used to identify unsupported symbols and improve error messages",
    )
    return parser.parse_args()


def _load_unsupported_symbols(sync_file: str | None) -> set[str]:
    if not sync_file:
        return set()
    path = Path(sync_file)
    if not path.exists():
        return set()
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        from_top = set(report.get("unsupported_symbols") or [])
        from_results = {
            r["symbol"]
            for r in report.get("results", [])
            if r.get("reason_code") == "unsupported_symbol"
        }
        return from_top | from_results
    except Exception:
        return set()


def main() -> int:
    args = parse_args()
    plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    market_dir = Path(args.market_dir)
    manifest = ManifestStore(root=market_dir / "manifests")
    validator = BatchValidator()

    download_tfs: list[str] = list(plan.get("download_tfs") or [str(plan.get("timeframe", "1m"))])
    unsupported_symbols: set[str] = _load_unsupported_symbols(args.sync_file)

    results: list[dict[str, object]] = []
    has_critical = False
    has_warnings = False
    cache: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    by_timeframe: dict[str, dict[str, int]] = {}

    intervals_per_entry = sum(
        len(entry.get("required_intervals", []))
        for basis_payload in plan["symbols"].values()
        for entry in basis_payload.values()
    )
    total_checks = intervals_per_entry * len(download_tfs)
    completed_checks = 0

    print("PHASE=validate")
    print(f"STEP=0/{total_checks}")
    print("PROGRESS=0")

    for tf in download_tfs:
        tf_stats = by_timeframe.setdefault(tf, {"passed": 0, "failed": 0, "warnings": 0})

        for symbol, basis_payload in plan["symbols"].items():
            for basis, entry in basis_payload.items():
                required = [Interval.from_dict(item) for item in entry.get("required_intervals", [])]

                if symbol in unsupported_symbols:
                    for interval in required:
                        has_critical = True
                        tf_stats["failed"] += 1
                        completed_checks += 1
                        print(f"STEP={completed_checks}/{total_checks}")
                        print(f"PROGRESS={int(completed_checks / max(total_checks, 1) * 100)}")
                        print(f"validate_progress {completed_checks}/{total_checks} symbol={symbol} basis={basis} tf={tf} status=FAIL reason=unsupported_symbol")
                        results.append(
                            {
                                "symbol": symbol,
                                "basis": basis,
                                "timeframe": tf,
                                "interval": interval.to_dict(),
                                "status": "FAIL",
                                "reason_code": "unsupported_symbol",
                                "critical_count": 1,
                                "warning_count": 0,
                                "info_count": 0,
                                "issues": [{"severity": "CRITICAL", "code": "unsupported_symbol", "message": f"Symbol {symbol} was not downloaded (unsupported by exchange)"}],
                            }
                        )
                    continue

                cache_key = (symbol, basis, tf)
                if cache_key not in cache:
                    partition_dir = market_dir / "bybit" / "futures_linear" / tf / symbol
                    files = sorted(partition_dir.glob(f"*.{basis}.parquet"))
                    print(
                        f"loading_cache symbol={symbol} basis={basis} tf={tf} "
                        f"partition_dir={partition_dir} files={len(files)}"
                    )
                    frames = [pd.read_parquet(path) for path in files]
                    rows: list[dict[str, object]] = []
                    if frames:
                        df = pd.concat(frames, ignore_index=True)
                        rows = df.to_dict(orient="records")
                    cache[cache_key] = rows
                    print(
                        f"loaded_cache symbol={symbol} basis={basis} tf={tf} "
                        f"files={len(files)} rows={len(rows)}"
                    )
                for interval in required:
                    rows = cache[cache_key]
                    result = validator.validate(rows=rows, requested_range=interval)
                    issues = [
                        {"severity": issue.severity.value, "code": issue.code, "message": issue.message}
                        for issue in result.issues
                    ]
                    status = "PASS" if not result.has_errors else "FAIL"
                    has_critical = has_critical or result.has_errors
                    has_warnings = has_warnings or any(i.severity == IssueSeverity.WARNING for i in result.issues)
                    if result.has_errors:
                        tf_stats["failed"] += 1
                    else:
                        tf_stats["passed"] += 1
                    tf_stats["warnings"] += result.warning_count
                    completed_checks += 1
                    print(f"STEP={completed_checks}/{total_checks}")
                    print(f"PROGRESS={int(completed_checks / max(total_checks, 1) * 100)}")
                    print(
                        f"validate_progress {completed_checks}/{total_checks} "
                        f"symbol={symbol} basis={basis} tf={tf} status={status}"
                    )
                    manifest.append_validation_event(
                        {
                            "event_id": str(uuid.uuid4()),
                            "symbol": symbol,
                            "basis": basis,
                            "timeframe": tf,
                            "status": status.lower(),
                            "issues": issues,
                        }
                    )
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

    market_ready = not has_critical and not (args.strict and has_warnings)

    output = Path(args.output) if args.output else Path("artifacts/market_data/validate_market_data.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "market_request_fingerprint": plan.get("market_request_fingerprint", ""),
                "status": "PASS" if market_ready else "FAIL",
                "checks": len(results),
                "strict": bool(args.strict),
                "critical_count": sum(int(r.get("critical_count", 0)) for r in results),
                "warning_count": sum(int(r.get("warning_count", 0)) for r in results),
                "info_count": sum(int(r.get("info_count", 0)) for r in results),
                "unsupported_symbols": sorted(unsupported_symbols),
                "by_timeframe": by_timeframe,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warning_count = sum(int(r.get("warning_count", 0)) for r in results)
    overall = "PASS" if market_ready else "FAIL"
    print(f"SUMMARY=pass:{pass_count} fail:{fail_count} warnings:{warning_count}")
    print(f"validation_report={output}")
    print(f"status={overall}")
    print(f"checks={len(results)}")
    return 0 if market_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
