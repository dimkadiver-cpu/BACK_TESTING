# Architecture

Signal Chain Backtesting Lab — architecture overview.

## High-level flow

```
DB esistente / chain reconstruction già disponibile
  -> DB reader (adapters/chain_builder.py)
  -> canonical adapter (adapters/chain_adapter.py)  [TODO]
  -> validator (adapters/validators.py)              [TODO]
  -> canonical chain package (domain/events.py)
  -> scenario runner (scripts/run_scenario.py)
  -> simulation engine (engine/simulator.py)         [TODO]
     + policy modules (policies/)
     + market data layer (market/)
     + latency / fill / timeout handling
  -> event log
  -> trade result
  -> scenario result
  -> reporting / plots
```

## Package structure

See `src/signal_chain_lab/` for module layout.

## Development phases

See `docs/development-phases.md`.
