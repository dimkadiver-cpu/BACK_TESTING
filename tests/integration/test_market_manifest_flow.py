from __future__ import annotations

import json
from datetime import datetime, timezone

from src.signal_chain_lab.market.planning.gap_detection import Interval, detect_gaps
from src.signal_chain_lab.market.planning.manifest_store import (
    CoverageKey,
    CoverageRecord,
    ManifestStore,
)


def test_manifest_persistence_and_gap_detection(tmp_path) -> None:
    store = ManifestStore(root=tmp_path / "data" / "market" / "manifests")

    store.upsert_coverage(
        CoverageRecord(
            key=CoverageKey(
                exchange="bybit",
                market_type="futures_linear",
                timeframe="1m",
                symbol="BTCUSDT",
            ),
            covered_intervals=[
                Interval(
                    start=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                    end=datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc),
                )
            ],
            validation_status="ok",
            last_updated=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
        )
    )

    store.upsert_coverage(
        CoverageRecord(
            key=CoverageKey(
                exchange="bybit",
                market_type="futures_linear",
                timeframe="1m",
                symbol="BTCUSDT",
            ),
            covered_intervals=[
                Interval(
                    start=datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc),
                    end=datetime(2026, 4, 1, 2, 0, tzinfo=timezone.utc),
                )
            ],
            validation_status="ok",
            last_updated=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
        )
    )

    assert store.append_download_event({"event_id": "d-1", "status": "ok"}) is True
    assert store.append_download_event({"event_id": "d-1", "status": "ok"}) is False
    assert store.append_validation_event({"event_id": "v-1", "status": "warning"}) is True

    saved = json.loads(store.coverage_path.read_text(encoding="utf-8"))
    assert saved["entries"][0]["exchange"] == "bybit"
    assert len(saved["entries"][0]["covered_intervals"]) == 1

    required = [
        Interval(
            start=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 1, 3, 0, tzinfo=timezone.utc),
        )
    ]
    loaded = store.load_coverage_index()
    covered = loaded[0].covered_intervals
    gaps = detect_gaps(required=required, covered=covered)

    assert len(gaps) == 1
    assert gaps[0].start == datetime(2026, 4, 1, 2, 0, tzinfo=timezone.utc)
    assert gaps[0].end == datetime(2026, 4, 1, 3, 0, tzinfo=timezone.utc)
