# PRD --- Signal Chain Backtesting & Optimization Engine

## 1. Obiettivo

Costruire un sistema che: - replaya segnali + update (catena eventi) da
Telegram - simula esecuzione realistica (latenza, fill, SL/TP,
partial) - confronta scenari (policy diverse) - ottimizza parametri
operativi - produce report quantitativi affidabili

------------------------------------------------------------------------

## 2. Scope

### In scope

-   Backtesting basato su eventi esterni (signal-driven)
-   Multi-entry (primary + averaging)
-   Gestione SL dinamico (move, BE)
-   Take profit multipli e chiusure parziali
-   Cancellazione ordini pendenti
-   Simulazione latenza e slippage
-   Policy configurabili
-   Ottimizzazione parametri

### Out of scope (MVP)

-   Live trading
-   Integrazione exchange reale
-   HFT / tick-level ultra preciso

------------------------------------------------------------------------

## 3. Architettura

### Core Components

1.  Event Store
2.  Market Data Layer
3.  Execution Simulator
4.  Policy Engine
5.  Optimizer
6.  Reporting Layer

------------------------------------------------------------------------

## 4. Data Model (semplificato)

Event: - signal_id - event_type - timestamp - payload

Trade State: - entries\[\] - avg_price - size - SL - TP\[\] -
realized_pnl

------------------------------------------------------------------------

## 5. Modalità operative

### 1. Replay

Simulazione singola

### 2. Scenario Comparison

Confronto più configurazioni

### 3. Optimization

Ricerca automatica parametri

------------------------------------------------------------------------

## 6. Librerie consigliate

### Core

-   pandas
-   numpy

### Backtesting / Simulation

-   vectorbt
-   backtesting.py
-   NautilusTrader (avanzato)

### Ottimizzazione

-   optuna

### Data

-   pyarrow (parquet)
-   sqlite / postgres

### Visualizzazione

-   matplotlib
-   plotly

------------------------------------------------------------------------

## 7. MVP Roadmap

### Fase 1

-   Replay base segnali
-   Entry + SL + TP
-   Report base

### Fase 2

-   Multi-entry
-   Partial close
-   Policy engine

### Fase 3

-   Latenza
-   Slippage
-   Optimizer

------------------------------------------------------------------------

## 8. Metriche

-   PnL totale
-   Max drawdown
-   Win rate
-   Sharpe ratio
-   Expectancy

------------------------------------------------------------------------

## 9. Output

-   Equity curve
-   Report per trader
-   Confronto scenari
-   Best config (optimizer)

------------------------------------------------------------------------

## 10. Stack consigliato

-   Python 3.12
-   pandas + numpy
-   optuna
-   parquet (pyarrow)
-   sqlite/postgres

------------------------------------------------------------------------

Generated: 2026-04-04 18:45:47.980576
