"""Converts SignalChain (chain_builder output) to CanonicalChain (simulator input)."""
from __future__ import annotations

from src.signal_chain_lab.adapters.models import ChainedMessage, SignalChain
from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent
from src.signal_chain_lab.parser.models.new_signal import NewSignalEntities
from src.signal_chain_lab.parser.models.update import UpdateEntities


# ---------------------------------------------------------------------------
# Intent → EventType mapping
# ---------------------------------------------------------------------------

_INTENT_TO_EVENT_TYPE: dict[str, EventType] = {
    "U_MOVE_STOP": EventType.MOVE_STOP,
    "U_MOVE_STOP_TO_BE": EventType.MOVE_STOP_TO_BE,
    "U_CLOSE_PARTIAL": EventType.CLOSE_PARTIAL,
    "U_CLOSE_FULL": EventType.CLOSE_FULL,
    "U_CANCEL_PENDING": EventType.CANCEL_PENDING,
    "U_ADD_ENTRY": EventType.ADD_ENTRY,
}


def _update_to_event_type(msg: ChainedMessage) -> EventType | None:
    """Return the primary EventType for an UPDATE message based on its intents."""
    for intent in msg.intents:
        if intent in _INTENT_TO_EVENT_TYPE:
            return _INTENT_TO_EVENT_TYPE[intent]
    return None


def _new_signal_payload(chain: SignalChain) -> dict:
    """Build the payload for the OPEN_SIGNAL event from a SignalChain."""
    payload: dict = {
        "entry_prices": chain.entry_prices,
        "sl_price": chain.sl_price,
        "tp_levels": chain.tp_prices,
        "side": chain.side,
        "symbol": chain.symbol,
        "raw_text": chain.new_signal.raw_text,
    }

    # Include richer entities if available
    if isinstance(chain.new_signal.entities, NewSignalEntities):
        ents = chain.new_signal.entities
        payload["entry_type"] = ents.entry_type
        if ents.stop_loss is not None:
            payload["stop_loss"] = ents.stop_loss.price.value
        payload["entries"] = [
            {"price": e.price.value, "order_type": e.order_type}
            for e in ents.entries
            if e.price is not None
        ]
        payload["take_profits"] = [
            {"price": tp.price.value, "label": tp.label}
            for tp in ents.take_profits
        ]
        # entry_plan_entries: serialize EntryLevel objects to dicts for downstream consumers
        epe = ents.entry_plan_entries
        if epe:
            payload["entry_plan_entries"] = [
                _serialize_entry_level(e)
                for e in epe
            ]
        for extra_key in ("entry_plan_type", "entry_structure", "has_averaging_plan"):
            extra_value = getattr(ents, extra_key, None)
            if extra_value is not None:
                payload[extra_key] = extra_value
        # direction → keep as canonical in payload; simulator uses `side`
        if ents.direction:
            payload["direction"] = ents.direction

    return payload


def _update_payload(msg: ChainedMessage) -> dict:
    """Build the payload for an UPDATE-derived event."""
    payload: dict = {"intents": msg.intents, "raw_text": msg.raw_text}

    if not isinstance(msg.entities, UpdateEntities):
        return payload

    ents = msg.entities
    if ents.new_sl_level is not None:
        payload["new_sl_level"] = ents.new_sl_level.value
    if ents.new_sl_price is not None:
        payload["new_sl_price"] = ents.new_sl_price.value
    elif ents.new_sl_level is not None:
        payload["new_sl_price"] = ents.new_sl_level.value
    if ents.new_sl_reference is not None:
        payload["new_sl_reference"] = ents.new_sl_reference
    if ents.close_pct is not None:
        payload["close_pct"] = ents.close_pct
    if ents.close_price is not None:
        payload["close_price"] = ents.close_price.value
    if ents.partial_close_price is not None:
        payload["partial_close_price"] = ents.partial_close_price.value
    if ents.cancel_scope is not None:
        payload["cancel_scope"] = ents.cancel_scope
    if ents.signal_id is not None:
        payload["signal_id"] = ents.signal_id
    if ents.manual_close:
        payload["manual_close"] = True
    if ents.stop_price is not None:
        payload["stop_price"] = ents.stop_price.value

    return payload


def _serialize_entry_level(entry: object) -> dict:
    raw = entry.model_dump(mode="python", exclude_none=False) if hasattr(entry, "model_dump") else dict(entry)  # type: ignore[arg-type]
    price = raw.get("price")
    if isinstance(price, dict) and isinstance(price.get("value"), (int, float)):
        raw["price"] = float(price["value"])
    return raw


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

def adapt_signal_chain(chain: SignalChain) -> CanonicalChain:
    """Convert a SignalChain to a CanonicalChain for the simulator.

    Mapping rules:
    - NEW_SIGNAL → OPEN_SIGNAL (EventType, source=TRADER)
    - UPDATE with recognized intent → corresponding EventType (source=TRADER)
    - UPDATE without recognized intent → skipped (stored in metadata only)
    - input_mode: SIGNAL_ONLY_NATIVE if no updates, CHAIN_COMPLETE otherwise
    - has_updates_in_dataset: True if chain.updates is non-empty

    Args:
        chain: A SignalChain produced by SignalChainBuilder.

    Returns:
        A CanonicalChain ready for the simulator.
    """
    has_updates = bool(chain.updates)
    input_mode = (
        ChainInputMode.CHAIN_COMPLETE if has_updates
        else ChainInputMode.SIGNAL_ONLY_NATIVE
    )

    events: list[CanonicalEvent] = []
    seq = 0

    # OPEN_SIGNAL event
    open_event = CanonicalEvent(
        signal_id=chain.chain_id,
        trader_id=chain.trader_id,
        symbol=chain.symbol,
        side=chain.side,
        timestamp=chain.open_ts,
        event_type=EventType.OPEN_SIGNAL,
        source=EventSource.TRADER,
        payload=_new_signal_payload(chain),
        sequence=seq,
        source_event_type="NEW_SIGNAL",
        source_record_id=str(chain.new_signal.op_signal_id),
    )
    events.append(open_event)
    seq += 1

    # UPDATE events (skipped without recognized intent)
    skipped_updates: list[dict] = []
    for upd in chain.updates:
        event_type = _update_to_event_type(upd)
        if event_type is None:
            skipped_updates.append({
                "op_signal_id": upd.op_signal_id,
                "intents": upd.intents,
                "message_ts": upd.message_ts.isoformat(),
            })
            continue

        events.append(CanonicalEvent(
            signal_id=chain.chain_id,
            trader_id=chain.trader_id,
            symbol=chain.symbol,
            side=chain.side,
            timestamp=upd.message_ts,
            event_type=event_type,
            source=EventSource.TRADER,
            payload=_update_payload(upd),
            sequence=seq,
            source_event_type="UPDATE",
            source_record_id=str(upd.op_signal_id),
        ))
        seq += 1

    metadata: dict = {
        "attempt_key": chain.new_signal.attempt_key,
        "is_blocked": chain.new_signal.is_blocked,
        "block_reason": chain.new_signal.block_reason,
        "new_signal_raw_text": chain.new_signal.raw_text,
    }
    if skipped_updates:
        metadata["skipped_updates"] = skipped_updates

    return CanonicalChain(
        signal_id=chain.chain_id,
        trader_id=chain.trader_id,
        symbol=chain.symbol,
        side=chain.side,
        input_mode=input_mode,
        has_updates_in_dataset=has_updates,
        created_at=chain.open_ts,
        events=events,
        metadata=metadata,
    )
