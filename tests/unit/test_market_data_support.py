from __future__ import annotations

from src.signal_chain_lab.ui.blocks.market_data_support import (
    format_data_types_summary,
    format_window_preview,
    parse_progress_line,
    roadmap_data_type_labels,
    supported_data_type_labels,
)
from src.signal_chain_lab.ui.state import MarketDataTypeState


def test_parse_progress_line_reads_summary_with_spaces() -> None:
    event = parse_progress_line("PHASE=validate PROGRESS=75 STEP=3/4 SUMMARY=pass:2 fail:1 warnings:1")

    assert event is not None
    assert event.phase == "validate"
    assert event.progress == 75
    assert event.step == "3/4"
    assert event.summary == "pass:2"


def test_parse_progress_line_returns_none_for_unstructured_line() -> None:
    assert parse_progress_line("normal log line without protocol") is None


def test_format_window_preview_summarizes_execution_chart_and_download_counts() -> None:
    plan = {
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "execution_window": [{"start": "2026-04-18T10:00:00+00:00", "end": "2026-04-18T10:03:00+00:00"}],
                    "chart_window": [{"start": "2026-04-11T10:00:00+00:00", "end": "2026-04-21T10:03:00+00:00"}],
                    "download_window": [
                        {"start": "2026-04-11T10:00:00+00:00", "end": "2026-04-21T10:03:00+00:00"},
                        {"start": "2026-04-22T10:00:00+00:00", "end": "2026-04-23T10:00:00+00:00"},
                    ],
                }
            }
        }
    }

    preview = format_window_preview(plan)

    assert preview.startswith("Finestre: BTCUSDT: exec=1 chart=1 download=2 | BTCUSDT range ")
    assert "exec[2026-04-18T10:00:00+00:00" in preview
    assert "chart[2026-04-11T10:00:00+00:00" in preview
    assert "download[2026-04-11T10:00:00+00:00" in preview


def test_supported_data_type_labels_includes_funding_rate_when_enabled() -> None:
    labels = supported_data_type_labels(
        MarketDataTypeState(ohlcv_last=True, ohlcv_mark=False, funding_rate=True)
    )

    assert labels == ["OHLCV last", "Funding rate"]


def test_roadmap_data_type_labels_excludes_funding_rate() -> None:
    assert "Funding rate" not in roadmap_data_type_labels()


def test_format_data_types_summary_shows_funding_rate_when_active() -> None:
    summary = format_data_types_summary(
        MarketDataTypeState(ohlcv_last=False, ohlcv_mark=False, funding_rate=True)
    )

    assert summary == "Tipi dati attivi: Funding rate"
