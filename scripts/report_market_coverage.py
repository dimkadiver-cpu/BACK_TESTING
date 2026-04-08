from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signal_chain_lab.market.planning.manifest_store import ManifestStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a readable report from the market-data coverage manifest")
    parser.add_argument("--market-dir", required=True, help="Path to market data root")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional CSV output path; default under artifacts/market_data/",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    market_dir = Path(args.market_dir)
    manifest = ManifestStore(root=market_dir / "manifests")
    records = manifest.load_coverage_index()

    output = Path(args.output) if args.output else Path("artifacts/market_data/report_market_coverage.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "exchange",
                "market_type",
                "timeframe",
                "symbol",
                "basis",
                "validation_status",
                "intervals_count",
                "start",
                "end",
                "last_updated",
            ],
        )
        writer.writeheader()
        for record in records:
            start = record.covered_intervals[0].start.isoformat() if record.covered_intervals else ""
            end = record.covered_intervals[-1].end.isoformat() if record.covered_intervals else ""
            writer.writerow(
                {
                    "exchange": record.key.exchange,
                    "market_type": record.key.market_type,
                    "timeframe": record.key.timeframe,
                    "symbol": record.key.symbol,
                    "basis": record.key.basis,
                    "validation_status": record.validation_status,
                    "intervals_count": len(record.covered_intervals),
                    "start": start,
                    "end": end,
                    "last_updated": record.last_updated.isoformat(),
                }
            )

    print(f"coverage_report={output}")
    print(f"entries={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
