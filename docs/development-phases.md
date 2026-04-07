# Development Phases

## Phase 0 — Audit & bootstrap
- Audit existing source DB (`scripts/audit_existing_db.py`)
- Verify data contract minimum (entry + SL + TP present in NEW_SIGNAL)
- Bootstrap repo structure ✅

## Phase 1 — Canonical domain models
- `domain/enums.py`: EventType, TradeStatus, CloseReason, ChainInputMode, EventSource
- `domain/events.py`: CanonicalEvent, CanonicalChain
- `domain/trade_state.py`: TradeState, EntryPlan, FillRecord
- `domain/results.py`: TradeResult, ScenarioResult
- `domain/warnings.py`: WarningCode, SimWarning

## Phase 2 — Adapter layer
- `adapters/chain_adapter.py`: SignalChain → CanonicalChain
- `adapters/validators.py`: simulability check
- `adapters/mapping.py`: field mapping helpers

## Phase 3 — Policy layer
- `policies/base.py`: PolicyConfig Pydantic model
- `policies/policy_loader.py`: load from YAML
- Baseline policies: `original_chain`, `signal_only`

## Phase 4 — Simulation engine (MVP)
- `engine/state_machine.py`: trade state transitions
- `engine/fill_model.py`: touch-based fill V1
- `engine/latency_model.py`: configurable latency
- `engine/timeout_manager.py`: pending + chain timeouts
- `engine/simulator.py`: main simulation loop

## Phase 5 — Market data layer
- `market/providers/csv_provider.py`
- `market/providers/parquet_provider.py`
- `market/symbol_mapper.py`

## Phase 6 — Scripts & first end-to-end run
- `scripts/run_single_chain.py`
- `scripts/run_scenario.py`
- First replay: original_chain vs signal_only on real dataset

## Phase 7 — Reports & output
- `reports/event_log_report.py`
- `reports/trade_report.py`
- Artifact export (JSON, CSV, PNG)

## Phase 8 — Optimizer (future)
- Optuna-based parameter search over policy space
- Restricted initial search space per PRD section 11.7
