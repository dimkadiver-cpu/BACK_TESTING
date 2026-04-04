# PRD --- Event-Driven Signal Chain Backtesting Lab

## Visione

Sistema avanzato per simulazione e ottimizzazione di signal chains
(Telegram trading signals).

Core principles: - Event-driven custom engine - Market replay realistico
(latency-aware, intrabar) - Policy engine modulare - Optimizer
(Optuna) - Reporting + plotting avanzato

------------------------------------------------------------------------

## Architettura

Flow:

DB (chain esistenti) → Adapter → Event Model → Execution Engine → Policy
Engine → Event Log → Trade Results → Scenario Results → Visualization →
Optimizer

------------------------------------------------------------------------

## Moduli

### adapters/

-   chain_adapter.py
-   validators.py

### engine/

-   simulator.py
-   state_machine.py
-   fill_model.py
-   latency_model.py

### market/

-   data_loader.py
-   intrabar_resolver.py

### policies/

-   policy.py
-   entry_policy.py
-   tp_policy.py
-   sl_policy.py
-   update_policy.py
-   pending_policy.py
-   risk_policy.py
-   execution_policy.py

### results/

-   event_log.py
-   trade_results.py
-   scenario_results.py

### visualization/

-   chain_plot.py
-   portfolio_plot.py
-   comparison_plot.py

### optimizer/

-   runner.py
-   objective.py

------------------------------------------------------------------------

## Event Model

Event: - signal_id - timestamp - type - payload - source (trader/engine)

------------------------------------------------------------------------

## Trade State

-   status
-   open_size
-   avg_entry_price
-   current_sl
-   tp_levels
-   realized_pnl

------------------------------------------------------------------------

## Eventi V1

-   OPEN_SIGNAL
-   ADD_ENTRY
-   MOVE_STOP
-   MOVE_STOP_TO_BE
-   CLOSE_PARTIAL
-   CLOSE_FULL
-   CANCEL_PENDING

------------------------------------------------------------------------

## Metriche

Trade-level: - PnL - MFE / MAE - duration

Portfolio-level: - total_pnl - drawdown - win_rate - expectancy

------------------------------------------------------------------------

## Policy Engine

Policy = Entry + TP + SL + Update + Pending + Risk + Execution

------------------------------------------------------------------------

## Librerie

Core: - pandas - numpy - pydantic - sqlalchemy

Optimization: - optuna

Data: - pyarrow - sqlite/postgres

Visualization: - plotly - matplotlib

Reference: - NautilusTrader - QF-Lib

------------------------------------------------------------------------

## Roadmap

MVP: - adapter DB - replay base - SL/TP - metriche base

V2: - intrabar - slippage - optimizer

V3: - order book - funding - dashboard

------------------------------------------------------------------------

## Generated

2026-04-04 20:06:07.735112
