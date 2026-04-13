from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.models import ChainedMessage, SignalChain
from src.signal_chain_lab.parser.models.new_signal import NewSignalEntities
from src.signal_chain_lab.parser.models.update import UpdateEntities


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
    assert payload["entry_plan_entries"][0]["price"] == 100.0
    assert payload["entry_plan_entries"][1]["price"] == 95.0
    assert payload["entry_plan_type"] == "MARKET_WITH_LIMIT_AVERAGING"
    assert payload["entry_structure"] == "TWO_STEP"
    assert payload["has_averaging_plan"] is True


def test_adapt_signal_chain_inferrs_market_entry_type_from_plan_metadata() -> None:
    entities = NewSignalEntities.model_validate(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry_plan_entries": [{"order_type": "MARKET", "price": None}],
            "entry_plan_type": "SINGLE_MARKET",
            "entry_structure": "ONE_SHOT",
            "stop_loss": {"price": {"raw": "90.0", "value": 90.0}},
            "take_profits": [{"price": {"raw": "110.0", "value": 110.0}, "label": "TP1"}],
        }
    )

    chain = SignalChain(
        chain_id="trader_a:attempt-market-legacy",
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
            attempt_key="attempt-market-legacy",
        ),
        updates=[],
        entry_prices=[],
        sl_price=90.0,
        tp_prices=[110.0],
        open_ts=_utc("2026-01-01T00:00:00"),
    )

    canonical = adapt_signal_chain(chain)
    payload = canonical.events[0].payload

    assert payload["entry_type"] == "MARKET"
    assert payload["entry_plan_type"] == "SINGLE_MARKET"
    assert payload["entries"] == [{"price": None, "order_type": "MARKET"}]


def test_adapt_signal_chain_uses_canonical_update_fields() -> None:
    chain = SignalChain(
        chain_id="trader_a:attempt-2",
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
            entities=NewSignalEntities.model_validate(
                {
                    "symbol": "BTCUSDT",
                    "direction": "LONG",
                    "entry_type": "LIMIT",
                    "entry_plan_entries": [{"price": 100.0, "order_type": "LIMIT"}],
                    "stop_loss": {"price": {"raw": "90.0", "value": 90.0}},
                    "take_profits": [{"price": {"raw": "110.0", "value": 110.0}}],
                }
            ),
            op_signal_id=10,
            attempt_key="attempt-2",
        ),
        updates=[
            ChainedMessage(
                raw_message_id=2,
                parse_result_id=2,
                telegram_message_id=102,
                message_ts=_utc("2026-01-01T01:00:00"),
                message_type="UPDATE",
                intents=["U_MOVE_STOP", "U_CLOSE_PARTIAL"],
                entities=UpdateEntities.model_validate(
                    {
                        "signal_id": 77,
                        "new_sl_level": 101.5,
                        "new_sl_price": 101.5,
                        "new_sl_reference": "TP1",
                        "close_pct": 0.5,
                        "partial_close_price": 108.0,
                        "cancel_scope": "TARGETED",
                        "manual_close": True,
                        "stop_price": 96.0,
                    }
                ),
                op_signal_id=11,
            )
        ],
        entry_prices=[100.0],
        sl_price=90.0,
        tp_prices=[110.0],
        open_ts=_utc("2026-01-01T00:00:00"),
    )

    canonical = adapt_signal_chain(chain)
    payload = canonical.events[1].payload

    assert payload["new_sl_level"] == 101.5
    assert payload["new_sl_price"] == 101.5
    assert payload["new_sl_reference"] == "TP1"
    assert payload["close_pct"] == 0.5
    assert payload["partial_close_price"] == 108.0
    assert payload["cancel_scope"] == "TARGETED"
    assert payload["manual_close"] is True
    assert payload["stop_price"] == 96.0
    assert payload["signal_id"] == 77
