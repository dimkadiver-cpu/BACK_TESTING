from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.adapters.chain_builder import _preferred_symbol_side
from src.signal_chain_lab.adapters.models import ChainedMessage
from src.signal_chain_lab.parser.models.new_signal import NewSignalEntities


def _utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)


class _FakeRow(dict):
    def keys(self):  # type: ignore[override]
        return super().keys()


def test_preferred_symbol_side_uses_message_entities_when_joined_signal_row_is_wrong() -> None:
    row = _FakeRow({"symbol": "LINKUSDT", "side": "BUY"})
    message = ChainedMessage(
        raw_message_id=1,
        parse_result_id=1,
        telegram_message_id=1,
        message_ts=_utc("2026-01-01T00:00:00"),
        message_type="NEW_SIGNAL",
        entities=NewSignalEntities.model_validate(
            {
                "symbol": "WLFIUSDT",
                "direction": "LONG",
                "entry_type": "LIMIT",
                "entries": [{"price": {"raw": "0.12", "value": 0.12}, "order_type": "LIMIT"}],
                "stop_loss": {"price": {"raw": "0.11", "value": 0.11}},
                "take_profits": [{"price": {"raw": "0.13", "value": 0.13}}],
            }
        ),
    )

    symbol, side = _preferred_symbol_side(row, message)

    assert symbol == "WLFIUSDT"
    assert side == "BUY"
