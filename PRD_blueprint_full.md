# PRD + Blueprint Tecnico --- Signal Chain Backtesting Lab

## 1. Overview

Sistema event-driven per simulazione, analisi e ottimizzazione di signal
chains da Telegram.

------------------------------------------------------------------------

## 2. Struttura Repository

``` text
signal_lab/
  adapters/
  engine/
  market/
  policies/
  results/
  visualization/
  optimizer/
  tests/
  config/
  main.py
```

------------------------------------------------------------------------

## 3. Moduli principali

### adapters/chain_adapter.py

-   input: DB esistente
-   output: lista eventi canonici

### engine/simulator.py

-   loop eventi
-   aggiorna TradeState

### engine/state_machine.py

-   gestisce transizioni

### engine/fill_model.py

-   logica fill

### engine/latency_model.py

-   delay simulato

------------------------------------------------------------------------

## 4. Classi principali

``` python
class Event:
    signal_id: str
    timestamp: datetime
    type: str
    payload: dict
    source: str

class TradeState:
    status: str
    open_size: float
    avg_entry_price: float
    current_sl: float
    realized_pnl: float
```

------------------------------------------------------------------------

## 5. Simulator Core

``` python
class Simulator:

    def run(self, events, policy):
        state = TradeState()

        for event in events:
            if policy.updates.apply(event):
                self.apply_event(state, event)

        return state
```

------------------------------------------------------------------------

## 6. Policy System

``` python
class Policy:
    def __init__(self, entry, tp, sl, updates):
        self.entry = entry
        self.tp = tp
        self.sl = sl
        self.updates = updates
```

------------------------------------------------------------------------

## 7. Market Layer

``` python
class MarketData:

    def get_price(self, symbol, timestamp):
        return price

    def resolve_intrabar(self, candle):
        return lower_tf_data
```

------------------------------------------------------------------------

## 8. Results

``` python
class TradeResult:
    pnl: float
    drawdown: float
    mfe: float
    mae: float
```

------------------------------------------------------------------------

## 9. Visualization

``` python
def plot_chain(trade, market):
    # plot entry, tp, sl
    pass
```

------------------------------------------------------------------------

## 10. Optimizer

``` python
import optuna

def objective(trial):
    policy = build_policy(trial)
    result = simulator.run(events, policy)
    return result.pnl
```

------------------------------------------------------------------------

## 11. Config

``` yaml
execution:
  latency_ms: 1000

risk:
  percent: 0.02
```

------------------------------------------------------------------------

## 12. MVP Tasks

1.  Adapter DB
2.  TradeState
3.  Simulator base
4.  Policy base
5.  Plot base

------------------------------------------------------------------------

## 13. V2 Tasks

-   intrabar
-   optimizer
-   multi-policy compare

------------------------------------------------------------------------

## 14. Generated

2026-04-04 20:35:44.931898
