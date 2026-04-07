# Data Contracts

Describes the canonical data models used at each layer boundary.

## Source DB → Adapter

The adapter reads from these tables in the source database:
- `operational_signals` (NEW_SIGNAL + UPDATE rows)
- `parse_results` (normalized JSON with entities and intents)
- `raw_messages` (timestamps, telegram IDs, source_chat_id)
- `signals` (resolved symbol + side per attempt_key)

## Adapter → Simulator

Output of the adapter is a `CanonicalChain` (see `domain/events.py` — TODO).

Minimum contract for a chain to enter standard simulation:
- `entry` present
- `stop_loss` present
- `take_profit` (at least one level) present

## Simulator → Output

- `event_log`: list of `CanonicalEvent` with processing_status (APPLIED / IGNORED / REJECTED / GENERATED)
- `trade_result`: final `TradeState` with PnL, close_reason, warnings_count
- `scenario_result`: aggregation of multiple trade_results

## Policy contract

See `configs/policies/` for the YAML schema.
See `domain/enums.py` for EventType, TradeStatus, CloseReason enums.
