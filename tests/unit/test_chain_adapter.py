from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.models import ChainedMessage, SignalChain
from src.signal_chain_lab.parser.models.new_signal import NewSignalEntities


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


def test_adapt_signal_chain_preserves_entry_plan_entries() -> None:
    entities = NewSignalEntities.model_validate(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_type": "MARKET",
            "entries": [{"price": {"raw": "100.0", "value": 100.0}, "order_type": "MARKET"}],
            "stop_loss": {"price": {"raw": "90.0", "value": 90.0}},
            "take_profits": [{"price": {"raw": "110.0", "value": 110.0}, "label": "TP1"}],
            "entry_plan_entries": [
                {"role": "PRIMARY", "order_type": "MARKET", "price": 100.0},
                {"role": "AVERAGING", "order_type": "LIMIT", "price": 95.0},
            ],
            "entry_plan_type": "MARKET_WITH_LIMIT_AVERAGING",
            "entry_structure": "TWO_STEP",
            "has_averaging_plan": True,
        }
    )

    chain = SignalChain(
        chain_id="trader_a:attempt-1",
        trader_id="trader_a",
        symbol="BTCUSDT",
        side="BUY",
        new_signal=ChainedMessage(
            raw_message_id=1,
            parse_result_id=1,
            telegram_message_id=101,
            message_ts=_utc("2026-01-01T00:00:00"),
            message_type="NEW_SIGNAL",
            intents=["NS_CREATE_SIGNAL"],
            entities=entities,
            op_signal_id=10,
            attempt_key="attempt-1",
        ),
        updates=[],
        entry_prices=[100.0],
        sl_price=90.0,
        tp_prices=[110.0],
        open_ts=_utc("2026-01-01T00:00:00"),
    )

    canonical = adapt_signal_chain(chain)
    payload = canonical.events[0].payload

    assert payload["entry_plan_entries"][0]["order_type"] == "MARKET"
    assert payload["entry_plan_entries"][1]["order_type"] == "LIMIT"
    assert payload["entry_plan_type"] == "MARKET_WITH_LIMIT_AVERAGING"
    assert payload["entry_structure"] == "TWO_STEP"
    assert payload["has_averaging_plan"] is True
