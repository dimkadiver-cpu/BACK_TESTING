# PRD COMPLETO --- Event-Driven Signal Chain Backtesting Lab

## 1. Visione

Sistema per simulazione e ottimizzazione di signal chains Telegram
basato su: - Core event-driven custom - Market replay latency-aware +
intrabar - Policy engine modulare - Optimizer (Optuna) - Reporting
avanzato + plotting

------------------------------------------------------------------------

## 2. Unità logica

-   Unità primaria: **signal chain**
-   Identificata da: `signal_id`
-   Start: NEW_SIGNAL
-   End: CLOSED / CANCELLED / EXPIRED / INVALID

### Validità minima chain

Richiede: - entry - stop loss - take profit

------------------------------------------------------------------------

## 3. Eventi supportati V1

### Setup

-   OPEN_SIGNAL (con entry + SL + TP)

### Operativi

-   ADD_ENTRY (market/limit, tranche indipendente)
-   MOVE_STOP
-   MOVE_STOP_TO_BE
-   CLOSE_PARTIAL (default 50% se non specificato)
-   CLOSE_FULL
-   CANCEL_PENDING

### Esclusi

-   TP_HIT_INFO
-   SL_HIT_INFO
-   RESULT_REPORT

------------------------------------------------------------------------

## 4. Stati del trade

-   NEW
-   PENDING
-   ACTIVE
-   PARTIALLY_CLOSED
-   CANCELLED
-   CLOSED
-   EXPIRED
-   INVALID

------------------------------------------------------------------------

## 5. Execution Model

### Fill model

-   limit fill: garantito se toccato
-   market fill: dopo latenza

### Latency

-   latency-aware:
    -   t_msg
    -   t_exec
    -   t_fill

### SL/TP conflict

-   risoluzione intrabar (lower timeframe)

------------------------------------------------------------------------

## 6. Incoerenze

### Modalità: SOFT

-   eventi incompatibili:
    -   ignorati
    -   warning loggato
    -   simulazione continua

### Esempi

-   MOVE_STOP prima del fill → ignored
-   CLOSE_FULL senza posizione → warning

------------------------------------------------------------------------

## 7. Timeout

Configurabili: - pending_timeout - chain_timeout

------------------------------------------------------------------------

## 8. Policy Engine

Policy = Entry + TP + SL + Update + Pending + Risk + Execution

### Baseline

-   original_chain
-   signal_only

------------------------------------------------------------------------

### Entry Policy

-   override possibile
-   allocation configurabile
-   force market/limit

------------------------------------------------------------------------

### TP Policy

-   numero TP selezionabile
-   distribuzione custom
-   modalità sequenziale o all-in

------------------------------------------------------------------------

### SL Policy

-   use trader SL
-   break-even:
    -   TP1 / TP2 / RR / tempo

------------------------------------------------------------------------

### Update Policy

-   enable/disable:
    -   move_stop
    -   close_partial
    -   close_full
    -   cancel_pending
    -   add_entry

------------------------------------------------------------------------

### Pending Policy

-   timeout
-   auto_cancel
-   cancel_on_new_signal

------------------------------------------------------------------------

### Risk Policy

-   fixed / percent
-   leverage
-   max_positions

------------------------------------------------------------------------

### Execution Policy

-   latency
-   slippage (V2)

------------------------------------------------------------------------

## 9. Output

### Event Log

-   timestamp
-   event_type
-   source
-   status (applied/ignored)
-   reason
-   state_before/after

------------------------------------------------------------------------

### Trade Results

-   pnl
-   mfe / mae
-   duration
-   drawdown
-   warnings_count

------------------------------------------------------------------------

### Scenario Results

-   total_pnl
-   drawdown
-   win_rate
-   expectancy

------------------------------------------------------------------------

## 10. Plot

### Chain plot

-   entry
-   averaging
-   SL dinamico
-   TP
-   TP hit
-   SL hit
-   close partial/full

### Overlay

-   trader vs engine

------------------------------------------------------------------------

## 11. Architettura

signal_lab/ - adapters/ - engine/ - market/ - policies/ - results/ -
visualization/ - optimizer/ - config/

------------------------------------------------------------------------

## 12. Librerie

Core: - pandas - numpy - pydantic - sqlalchemy

Data: - pyarrow - postgres/sqlite

Optimization: - optuna

Visualization: - plotly - matplotlib

Reference: - NautilusTrader - QF-Lib

------------------------------------------------------------------------

## 13. Roadmap

### MVP

-   adapter DB
-   simulator base
-   SL/TP
-   latency
-   plot base

### V2

-   intrabar completo
-   slippage
-   optimizer

### V3

-   order book
-   partial fill realistici
-   funding/liquidation

------------------------------------------------------------------------

## Generated

2026-04-04 20:38:06.599336
