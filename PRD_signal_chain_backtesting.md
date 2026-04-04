# PRD --- Event-Driven Signal Chain Backtesting Lab

## Vision

Sistema di simulazione avanzata per trading basato su **signal chains**,
non su indicatori.

> Core custom + market replay + policy engine + optimizer (Optuna)

------------------------------------------------------------------------

## Principi architetturali

-   Core **event-driven custom**
-   Separazione tra:
    -   eventi trader (input)
    -   eventi engine (realtà simulata)
-   Market replay indipendente
-   Policy modulari
-   Optimizer sopra il motore (non al posto)

------------------------------------------------------------------------

## Architettura

### Moduli principali

1.  **Signal Layer**
    -   parsing già fatto (tuo sistema)
    -   normalizzazione eventi
2.  **Event Store**
    -   sequenza temporale eventi
    -   chain per signal_id
3.  **Market Replay**
    -   OHLCV
    -   slippage
    -   fees
4.  **Execution Engine**
    -   stato trade
    -   fill logic
    -   SL/TP
    -   partial close
5.  **Policy Engine**
    -   regole custom
    -   override trader
6.  **Optimizer**
    -   ricerca parametri
7.  **Reporting**
    -   metriche
    -   equity curve

------------------------------------------------------------------------

## Modello dati

### Event

-   signal_id
-   event_type
-   timestamp
-   payload
-   source (trader / engine)

### Trade State

-   entries
-   size
-   avg_price
-   SL
-   TP
-   pnl

------------------------------------------------------------------------

## Modalità

### 1. Replay

Simulazione singola

### 2. Scenario

Confronto policy

### 3. Optimization

Ricerca automatica

------------------------------------------------------------------------

## Librerie

### Core (obbligatorie)

-   pandas
-   numpy
-   pydantic
-   sqlalchemy

### Data

-   pyarrow
-   parquet
-   sqlite / postgres

### Optimization

-   optuna

### Visual

-   plotly

------------------------------------------------------------------------

## Riferimenti architetturali

-   NautilusTrader
-   QF-Lib

(non core, solo reference)

------------------------------------------------------------------------

## NON usare come core

-   vectorbt
-   backtesting.py
-   freqtrade

------------------------------------------------------------------------

## MVP

### Fase 1

-   replay base
-   SL/TP
-   report

### Fase 2

-   multi-entry
-   partial close
-   policy

### Fase 3

-   latenza
-   slippage
-   optimizer

------------------------------------------------------------------------

## Metriche

-   PnL
-   drawdown
-   win rate
-   expectancy

------------------------------------------------------------------------

## Formula sistema

signal_chain + market + policy + execution = risultato

optimizer(parametri) = best config

------------------------------------------------------------------------

Generated: 2026-04-04 18:54:57.417148
