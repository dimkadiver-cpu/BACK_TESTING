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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    market_dir = Path(args.market_dir)
    manifest = ManifestStore(root=market_dir / "manifests")
    validator = BatchValidator()

    results: list[dict[str, object]] = []
    has_critical = False
    has_warnings = False
    cache: dict[tuple[str, str], list[dict[str, object]]] = {}
    total_checks = sum(
        len(entry.get("required_intervals", []))
        for basis_payload in plan["symbols"].values()
        for entry in basis_payload.values()
    )
    completed_checks = 0

    print("PHASE=validate")
    print(f"STEP=0/{total_checks}")
    print("PROGRESS=0")

    for symbol, basis_payload in plan["symbols"].items():
        for basis, entry in basis_payload.items():
            required = [Interval.from_dict(item) for item in entry.get("required_intervals", [])]
            cache_key = (symbol, basis)
            if cache_key not in cache:
                partition_dir = market_dir / "bybit" / "futures_linear" / plan["timeframe"] / symbol
                files = sorted(partition_dir.glob(f"*.{basis}.parquet"))
                print(
                    f"loading_cache symbol={symbol} basis={basis} "
                    f"partition_dir={partition_dir} files={len(files)}"
                )
                frames = [pd.read_parquet(path) for path in files]
                rows: list[dict[str, object]] = []
                if frames:
                    df = pd.concat(frames, ignore_index=True)
                    rows = df.to_dict(orient="records")
                cache[cache_key] = rows
                print(
                    f"loaded_cache symbol={symbol} basis={basis} "
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
                completed_checks += 1
                print(f"STEP={completed_checks}/{total_checks}")
                print(f"PROGRESS={int(completed_checks / max(total_checks, 1) * 100)}")
                print(
                    f"validate_progress {completed_checks}/{total_checks} "
                    f"symbol={symbol} basis={basis} status={status}"
                )
                manifest.append_validation_event(
                    {
                        "event_id": str(uuid.uuid4()),
                        "symbol": symbol,
                        "basis": basis,
                        "timeframe": plan["timeframe"],
                        "status": status.lower(),
                        "issues": issues,
                    }
                )
                results.append(
                    {
                        "symbol": symbol,
                        "basis": basis,
                        "interval": interval.to_dict(),
                        "status": status,
                        "critical_count": result.critical_count,
                        "warning_count": result.warning_count,
                        "info_count": result.info_count,
                        "issues": issues,
                    }
                )

    output = Path(args.output) if args.output else Path("artifacts/market_data/validate_market_data.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "market_request_fingerprint": plan.get("market_request_fingerprint", ""),
                "status": "PASS" if not has_critical and not (args.strict and has_warnings) else "FAIL",
                "checks": len(results),
                "strict": bool(args.strict),
                "critical_count": sum(int(r.get("critical_count", 0)) for r in results),
                "warning_count": sum(int(r.get("warning_count", 0)) for r in results),
                "info_count": sum(int(r.get("info_count", 0)) for r in results),
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    fail_on_strict = args.strict and has_warnings
    warning_count = sum(int(r.get("warning_count", 0)) for r in results)
    overall = "PASS" if not has_critical and not fail_on_strict else "FAIL"
    print(f"SUMMARY=pass:{pass_count} fail:{fail_count} warnings:{warning_count}")
    print(f"validation_report={output}")
    print(f"status={overall}")
    print(f"checks={len(results)}")
    return 0 if not has_critical and not fail_on_strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
