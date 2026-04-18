from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.market.planning.gap_detection import Interval, merge_intervals
from src.signal_chain_lab.market.sync.bybit_funding_downloader import (
    BybitFundingDownloader,
    FundingDownloadJob,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Bybit funding-rate history to local parquet storage")
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument("--plan-file", required=True, help="Plan JSON produced by plan_market_data.py")
    parser.add_argument(
        "--symbols",
        default="",
        help="Optional comma-separated symbol override, e.g. BTCUSDT,ETHUSDT",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print jobs without downloading funding rates",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    selected_symbols = {
        item.strip().upper()
        for item in str(args.symbols or "").split(",")
        if item.strip()
    }

    print("PHASE=funding_sync")
    print("PROGRESS=0")

    jobs = build_jobs(plan, selected_symbols=selected_symbols)
    total_jobs = len(jobs)

    if args.dry_run:
        for index, job in enumerate(jobs, start=1):
            print(f"STEP={index}/{total_jobs}")
            print(
                f"JOB symbol={job.symbol} start={job.start_time.isoformat()} end={job.end_time.isoformat()}"
            )
        print("SUMMARY=ok:0 skipped:0 error:0 events:0")
        return 0

    downloader = BybitFundingDownloader(market_dir=Path(args.market_dir))
    results = downloader.download(jobs)

    total_events = 0
    ok_count = 0
    skipped_count = 0
    error_count = 0
    for index, result in enumerate(results, start=1):
        print(f"STEP={index}/{total_jobs}")
        progress = int(index * 100 / total_jobs) if total_jobs else 100
        print(f"PROGRESS={progress}")
        total_events += result.events_downloaded
        if result.status == "ok":
            ok_count += 1
        elif result.status == "skipped":
            skipped_count += 1
        else:
            error_count += 1

    print(f"SUMMARY=ok:{ok_count} skipped:{skipped_count} error:{error_count} events:{total_events}")
    return 1 if error_count else 0


def build_jobs(
    plan: dict[str, object],
    *,
    selected_symbols: set[str] | None = None,
) -> list[FundingDownloadJob]:
    jobs: list[FundingDownloadJob] = []
    symbols_payload = plan.get("symbols", {})
    if not isinstance(symbols_payload, dict):
        return jobs

    for symbol, symbol_payload in symbols_payload.items():
        symbol_name = str(symbol).upper()
        if selected_symbols and symbol_name not in selected_symbols:
            continue

        intervals = _collect_symbol_intervals(symbol_payload)
        for interval in merge_intervals(intervals):
            jobs.append(
                FundingDownloadJob(
                    symbol=symbol_name,
                    start_time=interval.start,
                    end_time=interval.end,
                )
            )

    jobs.sort(key=lambda item: (item.symbol, item.start_time, item.end_time))
    return jobs


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


if __name__ == "__main__":
    raise SystemExit(main())
