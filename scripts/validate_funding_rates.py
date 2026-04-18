from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.market.planning.gap_detection import Interval, merge_intervals
from src.signal_chain_lab.market.planning.validation import FundingBatchValidator, IssueSeverity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate local funding-rate parquet coverage against a saved plan"
    )
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument("--plan-file", required=True, help="Plan JSON produced by plan_market_data.py")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional validation report JSON path; default under artifacts/market_data/",
    )
    parser.add_argument("--strict", action="store_true", help="Fail on WARNING in addition to CRITICAL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    market_dir = Path(args.market_dir)
    validator = FundingBatchValidator()
    jobs = build_jobs(plan)

    results: list[dict[str, object]] = []
    has_critical = False
    has_warnings = False
    total_checks = len(jobs)

    print("PHASE=validate_funding")
    print(f"STEP=0/{total_checks}")
    print("PROGRESS=0")

    for index, job in enumerate(jobs, start=1):
        parquet_paths = funding_parquet_paths(
            market_dir=market_dir,
            symbol=job["symbol"],
            interval=job["interval"],
        )
        result = validator.validate(
            symbol=job["symbol"],
            parquet_paths=parquet_paths,
            interval=job["interval"],
        )
        issues = [
            {"severity": issue.severity.value, "code": issue.code, "message": issue.message}
            for issue in result.issues
        ]
        status = "PASS" if not result.has_errors else "FAIL"
        has_critical = has_critical or result.has_errors
        has_warnings = has_warnings or any(
            issue.severity == IssueSeverity.WARNING for issue in result.issues
        )
        print(f"STEP={index}/{total_checks}")
        print(f"PROGRESS={int(index / max(total_checks, 1) * 100)}")
        print(
            f"validate_funding_progress {index}/{total_checks} "
            f"symbol={job['symbol']} status={status}"
        )
        results.append(
            {
                "symbol": job["symbol"],
                "interval": job["interval"].to_dict(),
                "status": status,
                "critical_count": result.critical_count,
                "warning_count": result.warning_count,
                "info_count": result.info_count,
                "issues": issues,
                "parquet_files": [str(path) for path in parquet_paths],
            }
        )

    output = (
        Path(args.output)
        if args.output
        else Path("artifacts/market_data/validate_funding_rates.json")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "market_request_fingerprint": plan.get("market_request_fingerprint", ""),
                "status": "PASS" if not has_critical and not (args.strict and has_warnings) else "FAIL",
                "checks": len(results),
                "strict": bool(args.strict),
                "critical_count": sum(int(row.get("critical_count", 0)) for row in results),
                "warning_count": sum(int(row.get("warning_count", 0)) for row in results),
                "info_count": sum(int(row.get("info_count", 0)) for row in results),
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    pass_count = sum(1 for row in results if row["status"] == "PASS")
    fail_count = sum(1 for row in results if row["status"] == "FAIL")
    warning_count = sum(int(row.get("warning_count", 0)) for row in results)
    fail_on_strict = args.strict and has_warnings
    overall = "PASS" if not has_critical and not fail_on_strict else "FAIL"

    print(f"SUMMARY=pass:{pass_count} fail:{fail_count} warnings:{warning_count}")
    print(f"validation_report={output}")
    print(f"status={overall}")
    print(f"checks={len(results)}")
    return 0 if not has_critical and not fail_on_strict else 1


def build_jobs(plan: dict[str, object]) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    symbols_payload = plan.get("symbols", {})
    if not isinstance(symbols_payload, dict):
        return jobs

    for symbol, symbol_payload in symbols_payload.items():
        intervals = _collect_symbol_intervals(symbol_payload)
        for interval in merge_intervals(intervals):
            jobs.append({"symbol": str(symbol).upper(), "interval": interval})

    jobs.sort(key=lambda item: (str(item["symbol"]), item["interval"].start, item["interval"].end))
    return jobs


def funding_parquet_paths(*, market_dir: Path, symbol: str, interval: Interval) -> list[Path]:
    symbol_dir = market_dir / "bybit" / "futures_linear" / "funding" / symbol
    if not symbol_dir.exists():
        return []

    month_keys = _month_keys_between(interval.start, interval.end)
    paths = [symbol_dir / f"{month_key}.funding.parquet" for month_key in month_keys]
    return [path for path in paths if path.exists()]


def _collect_symbol_intervals(symbol_payload: object) -> list[Interval]:
    intervals: list[Interval] = []
    if not isinstance(symbol_payload, dict):
        return intervals

    for basis_payload in symbol_payload.values():
        if not isinstance(basis_payload, dict):
            continue
        intervals.extend(_intervals_from_entry(basis_payload))
        timeframes = basis_payload.get("timeframes")
        if isinstance(timeframes, dict):
            for timeframe_payload in timeframes.values():
                intervals.extend(_intervals_from_entry(timeframe_payload))
    return intervals


def _intervals_from_entry(entry: object) -> list[Interval]:
    if not isinstance(entry, dict):
        return []

    candidates = entry.get("required_intervals")
    if not isinstance(candidates, list) or not candidates:
        candidates = entry.get("download_window")
    if not isinstance(candidates, list):
        return []

    intervals: list[Interval] = []
    for item in candidates:
        if isinstance(item, dict) and "start" in item and "end" in item:
            intervals.append(Interval.from_dict(item))
    return intervals


def _month_keys_between(start: datetime, end: datetime) -> list[str]:
    start_dt = _as_utc_datetime(start)
    end_dt = _as_utc_datetime(end)
    cursor = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    final = end_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    keys: list[str] = []
    while cursor <= final:
        keys.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return keys


def _as_utc_datetime(raw: datetime) -> datetime:
    if raw.tzinfo is None:
        return raw.replace(tzinfo=timezone.utc)
    return raw.astimezone(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
