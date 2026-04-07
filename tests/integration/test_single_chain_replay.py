from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.engine.simulator import simulate_chain
from src.signal_chain_lab.policies.base import PolicyConfig
from src.signal_chain_lab.reports.event_log_report import write_event_log_jsonl
from src.signal_chain_lab.reports.trade_report import build_trade_result, write_trade_result_parquet


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def test_single_chain_replay_end_to_end(tmp_path) -> None:
    chain = CanonicalChain(
        signal_id="sig-1",
        trader_id="trader-a",
        symbol="BTCUSDT",
        side="BUY",
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        has_updates_in_dataset=True,
        created_at=_utc("2026-01-01T00:00:00"),
        events=[
            CanonicalEvent(
                signal_id="sig-1",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc("2026-01-01T00:00:00"),
                event_type=EventType.OPEN_SIGNAL,
                source=EventSource.TRADER,
                payload={"entry_prices": [100.0], "sl_price": 90.0, "tp_levels": [110.0]},
                sequence=0,
            ),
            CanonicalEvent(
                signal_id="sig-1",
                trader_id="trader-a",
                symbol="BTCUSDT",
                side="BUY",
                timestamp=_utc("2026-01-01T01:00:00"),
                event_type=EventType.CANCEL_PENDING,
                source=EventSource.TRADER,
                payload={},
                sequence=1,
            ),
        ],
    )
    logs, state = simulate_chain(chain, PolicyConfig(name="original_chain"))
    assert len(logs) == 2
    assert state.status.value in {"CANCELLED", "EXPIRED", "CLOSED"}

    event_path = write_event_log_jsonl(logs, tmp_path / "artifacts" / "event_log.jsonl")
    result = build_trade_result(state, logs)
    trade_path = write_trade_result_parquet(result, tmp_path / "artifacts" / "trade_result.parquet")

    assert event_path.exists()
    assert trade_path.exists()
