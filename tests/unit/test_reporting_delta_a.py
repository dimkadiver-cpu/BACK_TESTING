from __future__ import annotations

from datetime import datetime, timezone
import typing

if not hasattr(typing, "Self"):
    typing.Self = object  # type: ignore[attr-defined]

from src.signal_chain_lab.adapters.chain_builder import _normalize_chain_id
from src.signal_chain_lab.domain.enums import ChainInputMode, EventProcessingStatus
from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policy_report.html_writer import write_single_trade_html_report


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _sample_trade() -> TradeResult:
    return TradeResult(
        signal_id="trader_c:rm1571",
        trader_id="trader_c",
        symbol="BTCUSDT",
        side="BUY",
        status="CLOSED",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="original_chain",
        close_reason="tp",
        realized_pnl=2.5,
    )


def test_normalize_chain_id_avoids_duplicate_trader_prefix() -> None:
    assert _normalize_chain_id("trader_c", "trader_c:rm1571") == "trader_c:rm1571"
    assert _normalize_chain_id("trader_c", "rm1571") == "trader_c:rm1571"


def test_single_trade_report_limits_raw_text_to_trader_events_and_shows_levels(tmp_path) -> None:
    event_log = [
        EventLogEntry(
            timestamp=_utc("2026-01-01T00:00:00"),
            signal_id="trader_c:rm1571",
            event_type="OPEN_SIGNAL",
            source="trader",
            requested_action="OPEN_SIGNAL",
            executed_action="OPEN_SIGNAL",
            processing_status=EventProcessingStatus.APPLIED,
            raw_text="telegram payload",
            state_after={
                "entries_planned": [{"price": 100.0}, {"price": 101.0}],
                "current_sl": 95.0,
                "tp_levels": [110.0, 112.0],
            },
        ),
        EventLogEntry(
            timestamp=_utc("2026-01-01T01:00:00"),
            signal_id="trader_c:rm1571",
            event_type="CLOSE_FULL",
            source="engine",
            requested_action="CLOSE_FULL",
            executed_action="CLOSE_FULL",
            processing_status=EventProcessingStatus.APPLIED,
            raw_text="engine synthetic",
            state_after={"avg_entry_price": 100.0},
        ),
    ]

    path = write_single_trade_html_report(trade=_sample_trade(), event_log=event_log, output_path=tmp_path / "detail.html")
    text = path.read_text(encoding="utf-8")

    assert "Extracted levels" in text
    assert "entry=100.0000, 101.0000 | sl=95.0000 | tp=110.0000, 112.0000" in text
    assert text.count("Open raw telegram text") == 1
    assert "Price Chart" in text
    assert "No market candles available" in text


def test_single_trade_chart_formats_timestamps_in_utc(tmp_path) -> None:
    event_log = [
        EventLogEntry(
            timestamp=_utc("2026-01-05T14:19:24"),
            signal_id="trader_c:rm1571",
            event_type="OPEN_SIGNAL",
            source="trader",
            requested_action="OPEN_SIGNAL",
            executed_action="OPEN_SIGNAL",
            processing_status=EventProcessingStatus.APPLIED,
            state_after={
                "entries_planned": [{"price": 0.16}],
                "current_sl": 0.16134,
                "tp_levels": [0.1445],
            },
        ),
    ]
    candles = {
        "1m": [
            Candle(
                timestamp=_utc("2026-01-05T14:19:00"),
                open=0.16,
                high=0.161,
                low=0.1585,
                close=0.15881,
                volume=1234.0,
                symbol="STORJUSDT",
                timeframe="1m",
            )
        ]
    }

    path = write_single_trade_html_report(
        trade=_sample_trade(),
        event_log=event_log,
        candles_by_timeframe=candles,
        output_path=tmp_path / "detail.html",
    )
    text = path.read_text(encoding="utf-8")

    assert "formatUtcDateTime" in text
    assert "formatUtcAxis" in text
    assert " UTC" in text
