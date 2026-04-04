# Documentazione Completa — Signal Chain Backtesting Lab
**Versione:** draft-1  
**Generata:** 2026-04-04 20:50:27

---

## 1. Scopo del documento

Questo documento serve come **handoff tecnico completo** per un agente di sviluppo che dovrà:

1. creare la **struttura iniziale del repository**
2. definire i **moduli principali**
3. pianificare lo sviluppo in **fasi incrementali**
4. preparare la base per:
   - simulazione event-driven
   - market replay
   - policy engine
   - optimizer
   - report e plotting

Il sistema target **non** è un classico framework di backtesting indicator-based.  
È un **event-driven backtesting lab per signal chains** provenienti da un database già esistente.

---

## 2. Visione del prodotto

### Obiettivo
Simulare e ottimizzare catene di segnali di trading (signal chains), dove ogni chain è composta da:

- segnale iniziale
- eventuali entry multiple
- aggiornamenti operativi successivi
- gestione stop loss
- chiusure parziali / totali
- annullamento ordini pendenti
- eventuale scadenza della chain

### Risultato atteso
Permettere di confrontare:

- chain originale del trader
- esecuzione solo del segnale iniziale
- chain con regole custom aggiuntive
- versioni ottimizzate della stessa chain

---

## 3. Principi architetturali vincolanti

1. **Core custom obbligatorio**
   - Il motore principale deve essere sviluppato su misura.
   - Framework esterni possono essere usati solo come riferimento architetturale o supporto non centrale.

2. **Signal chain come unità logica primaria**
   - L'unità del sistema non è il singolo messaggio.
   - L'unità non è il singolo indicatore.
   - L'unità è una **chain identificata da `signal_id`**.

3. **Separazione tra eventi trader e eventi engine**
   - Quello che dichiara il trader non coincide automaticamente con ciò che il motore esegue.

4. **Event-sourced design**
   - Event log e state transitions sono centrali.
   - Il sistema deve essere riproducibile e auditabile.

5. **Latency-aware simulation**
   - Gli update vanno applicati solo se compatibili con lo stato realmente raggiunto dal simulatore.

6. **Policy-driven behavior**
   - Le variazioni di logica non devono modificare il core.
   - Devono entrare come configurazioni / policy modulari.

7. **Massimo realismo compatibile con sviluppo incrementale**
   - L'obiettivo è alto realismo.
   - Ma il progetto va costruito in fasi: MVP -> V2 -> V3.

---

## 4. Decisioni funzionali già definite

### 4.1 Unità primaria
- Unità primaria: **signal chain**
- Identificatore: **`signal_id`**
- Il dataset può essere **multi-trader**
- Ogni chain simulata deve avere un trader effettivo risolto

### 4.2 Start / End della chain
- Start: `NEW_SIGNAL`
- End possibili:
  - `CLOSED`
  - `CANCELLED`
  - `EXPIRED`
  - `INVALID`

### 4.3 Validità minima del segnale iniziale
Una chain è simulabile solo se il `NEW_SIGNAL` contiene almeno:

- `entry`
- `stop loss`
- `take profit`

Se manca uno di questi elementi:
- la chain non entra nella simulazione standard
- può essere trattenuta per audit

### 4.4 Eventi operativi V1 supportati
- `OPEN_SIGNAL`
- `ADD_ENTRY`
- `MOVE_STOP`
- `MOVE_STOP_TO_BE`
- `CLOSE_PARTIAL`
- `CLOSE_FULL`
- `CANCEL_PENDING`

### 4.5 Eventi esclusi dalla logica simulativa V1
Questi possono essere salvati come metadati o per audit, ma **non guidano la simulazione**:

- `TP_HIT_INFO`
- `SL_HIT_INFO`
- `RESULT_REPORT`
- altri eventi puramente informativi

### 4.6 Stati del trade V1
- `NEW`
- `PENDING`
- `ACTIVE`
- `PARTIALLY_CLOSED`
- `CANCELLED`
- `CLOSED`
- `EXPIRED`
- `INVALID`

### 4.7 Fill model V1
- `market`: fill dopo latenza
- `limit`: fill garantito se il prezzo viene toccato

### 4.8 Conflitto SL / TP nella stessa barra
- Risoluzione: **intrabar**
- Il sistema deve prevedere timeframe inferiore per i casi ambigui

### 4.9 Incoerenze
Modalità: **soft**
- evento incompatibile -> ignored
- warning loggato
- simulazione continua

Esempi:
- `MOVE_STOP` prima del fill -> ignored + warning
- `CLOSE_FULL` senza posizione attiva -> warning

### 4.10 Timeouts
Configurabili:
- `pending_timeout`
- `chain_timeout`

### 4.11 Baseline policy da supportare
- `original_chain`
- `signal_only`

### 4.12 Policy modulari
Una policy è composta da:
- entry policy
- TP policy
- SL policy
- update policy
- pending policy
- risk policy
- execution policy

---

## 5. Architettura logica di alto livello

```text
DB esistente / parse results / chain reconstruction
-> adapter canonico eventi V1
-> validator
-> market data layer
-> simulation engine
-> policy engine
-> event log engine
-> trade results
-> scenario results
-> report / plots
-> optimizer
```

---

## 6. Vincolo strategico: riuso del database esistente

Esiste già un sistema che ricostruisce le chain nel DB.

### Regola di progetto
**Non riscrivere subito la chain reconstruction.**

Prima bisogna implementare:

1. **audit del DB esistente**
2. **adapter** che traduce il formato attuale nel modello canonico della simulazione
3. solo se necessario, correzioni o estensioni mirate

### Implicazione
Il progetto deve partire da:

```text
DB esistente -> adapter -> simulator
```

e non da:

```text
raw telegram -> parse -> reconstruction -> simulator
```

---

## 7. Struttura repository proposta

```text
signal_chain_lab/
├─ README.md
├─ pyproject.toml
├─ .env.example
├─ Makefile
├─ configs/
│  ├─ app.yaml
│  ├─ policies/
│  │  ├─ original_chain.yaml
│  │  ├─ signal_only.yaml
│  │  └─ examples/
│  │     ├─ be_after_tp1.yaml
│  │     ├─ tp_50_30_20.yaml
│  │     └─ entry_70_30.yaml
│  └─ logging.yaml
├─ docs/
│  ├─ architecture.md
│  ├─ domain-model.md
│  ├─ event-model.md
│  ├─ state-machine.md
│  ├─ policies.md
│  ├─ data-contracts.md
│  ├─ development-phases.md
│  └─ testing-strategy.md
├─ src/
│  └─ signal_chain_lab/
│     ├─ __init__.py
│     ├─ main.py
│     ├─ settings.py
│     ├─ logging_config.py
│     ├─ adapters/
│     │  ├─ __init__.py
│     │  ├─ chain_adapter.py
│     │  ├─ db_reader.py
│     │  ├─ validators.py
│     │  └─ mapping.py
│     ├─ domain/
│     │  ├─ __init__.py
│     │  ├─ enums.py
│     │  ├─ ids.py
│     │  ├─ events.py
│     │  ├─ orders.py
│     │  ├─ positions.py
│     │  ├─ trade_state.py
│     │  ├─ warnings.py
│     │  └─ results.py
│     ├─ engine/
│     │  ├─ __init__.py
│     │  ├─ simulator.py
│     │  ├─ state_machine.py
│     │  ├─ event_processor.py
│     │  ├─ fill_model.py
│     │  ├─ latency_model.py
│     │  ├─ timeout_manager.py
│     │  └─ warning_manager.py
│     ├─ market/
│     │  ├─ __init__.py
│     │  ├─ data_loader.py
│     │  ├─ data_models.py
│     │  ├─ intrabar_resolver.py
│     │  ├─ symbol_mapper.py
│     │  └─ providers/
│     │     ├─ __init__.py
│     │     ├─ parquet_provider.py
│     │     └─ csv_provider.py
│     ├─ policies/
│     │  ├─ __init__.py
│     │  ├─ base.py
│     │  ├─ policy_loader.py
│     │  ├─ entry_policy.py
│     │  ├─ tp_policy.py
│     │  ├─ sl_policy.py
│     │  ├─ update_policy.py
│     │  ├─ pending_policy.py
│     │  ├─ risk_policy.py
│     │  └─ execution_policy.py
│     ├─ optimizer/
│     │  ├─ __init__.py
│     │  ├─ objective.py
│     │  ├─ search_space.py
│     │  ├─ runner.py
│     │  └─ scoring.py
│     ├─ reports/
│     │  ├─ __init__.py
│     │  ├─ event_log_report.py
│     │  ├─ trade_report.py
│     │  ├─ scenario_report.py
│     │  ├─ portfolio_report.py
│     │  └─ exporters.py
│     ├─ visualization/
│     │  ├─ __init__.py
│     │  ├─ chain_plot.py
│     │  ├─ portfolio_plot.py
│     │  ├─ comparison_plot.py
│     │  └─ styles.py
│     ├─ persistence/
│     │  ├─ __init__.py
│     │  ├─ base.py
│     │  ├─ models.py
│     │  ├─ repositories.py
│     │  └─ session.py
│     └─ utils/
│        ├─ __init__.py
│        ├─ time.py
│        ├─ math.py
│        ├─ serialization.py
│        └─ hashing.py
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ fixtures/
│  └─ golden/
└─ scripts/
   ├─ run_single_chain.py
   ├─ run_scenario.py
   ├─ run_optimizer.py
   ├─ audit_existing_db.py
   └─ export_reports.py
```

---

## 8. Dipendenze consigliate

### 8.1 Dipendenze core

#### `pydantic`
Uso:
- data contracts
- validazione eventi
- validazione config
- serializzazione forte

#### `pydantic-settings`
Uso:
- gestione settings da env / secret / config files

#### `sqlalchemy`
Uso:
- persistenza risultati
- adapter su DB esistente
- repository pattern
- compatibilità SQLite / PostgreSQL

#### `pandas`
Uso:
- analisi risultati
- export tabellari
- aggregazioni scenario / portfolio

#### `numpy`
Uso:
- calcoli numerici
- metriche
- performance support

#### `pyarrow`
Uso:
- storage Parquet
- dataset veloci per market data e risultati

#### `optuna`
Uso:
- optimizer
- ricerca spazio parametri
- studi replicabili

#### `plotly`
Uso:
- chart interattivi
- report HTML
- plotting chain / scenario / portfolio

#### `matplotlib`
Uso:
- export rapido PNG statici
- grafici semplici batch/offline

### 8.2 Dipendenze opzionali ma molto utili

#### `duckdb`
Uso:
- query veloci su parquet
- analisi massiva senza server DB

#### `polars`
Uso:
- alternativa veloce a pandas su dataset grandi

#### `orjson`
Uso:
- serializzazione JSON veloce per logs / results

#### `rich`
Uso:
- CLI leggibile
- logging colorato
- debug locale

#### `typer`
Uso:
- CLI pulite per script `run_*`

#### `pytest`
Uso:
- test unitari
- test integrazione
- regression tests

#### `pytest-cov`
Uso:
- coverage

#### `mypy`
Uso:
- controllo statico tipi

#### `ruff`
Uso:
- lint + format check veloce

---

## 9. Esempio dipendenze — `pyproject.toml`

```toml
[project]
name = "signal-chain-lab"
version = "0.1.0"
description = "Event-driven backtesting lab for signal chains"
requires-python = ">=3.12"

dependencies = [
  "pydantic>=2.0",
  "pydantic-settings>=2.0",
  "sqlalchemy>=2.0",
  "pandas>=2.0",
  "numpy>=1.26",
  "pyarrow>=15.0",
  "optuna>=4.0",
  "plotly>=5.0",
  "matplotlib>=3.8",
  "orjson>=3.0",
  "rich>=13.0",
  "typer>=0.12",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "mypy>=1.0",
  "ruff>=0.5",
]

analytics = [
  "duckdb>=1.0",
  "polars>=1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = false
```

---

## 10. Configurazione applicativa

### 10.1 `.env.example`

```env
APP_ENV=dev
LOG_LEVEL=INFO

DATABASE_URL=sqlite:///./data/signal_lab.sqlite3
RESULTS_DB_URL=sqlite:///./data/results.sqlite3

MARKET_DATA_DIR=./data/market
PARQUET_RESULTS_DIR=./data/results_parquet

DEFAULT_TIMEZONE=UTC

DEFAULT_PENDING_TIMEOUT_HOURS=24
DEFAULT_CHAIN_TIMEOUT_HOURS=168

DEFAULT_LATENCY_MS=1000

ENABLE_INTRABAR=true
INTRABAR_TIMEFRAME=1m

OPTUNA_STORAGE=sqlite:///./data/optuna.sqlite3
OPTUNA_STUDY_NAME=signal_chain_lab
```

### 10.2 `configs/app.yaml`

```yaml
app:
  env: dev
  timezone: UTC

db:
  source_url: "sqlite:///./data/source.sqlite3"
  results_url: "sqlite:///./data/results.sqlite3"

market:
  data_dir: "./data/market"
  base_timeframe: "1h"
  intrabar_enabled: true
  intrabar_timeframe: "1m"

simulation:
  pending_timeout_hours: 24
  chain_timeout_hours: 168
  default_latency_ms: 1000
  fill_touch_guaranteed: true
  inconsistency_mode: soft

reports:
  output_dir: "./artifacts"
  save_event_logs: true
  save_trade_reports: true
  save_plots_png: true
  save_plots_html: true

optimizer:
  storage: "sqlite:///./data/optuna.sqlite3"
  study_name: "signal_chain_lab"
```

---

## 11. Policy configuration — esempi

### 11.1 `original_chain.yaml`

```yaml
name: original_chain

entry:
  mode: keep_original
  allocation: keep_original
  force_order_type: keep

tp:
  use_count: all
  distribution: keep_original
  mode: sequential

sl:
  use_trader_updates: true
  break_even:
    enabled: false

updates:
  apply_move_stop: true
  apply_close_partial: true
  apply_close_full: true
  apply_cancel_pending: true
  apply_add_entry: true

pending:
  timeout_hours: 24
  auto_cancel: true
  cancel_on_new_signal: false

risk:
  mode: percent
  value: 0.02
  leverage: keep_original
  max_positions: 5

execution:
  latency_ms: 1000
  slippage_model: none
```

### 11.2 `signal_only.yaml`

```yaml
name: signal_only

entry:
  mode: keep_original
  allocation: keep_original
  force_order_type: keep

tp:
  use_count: all
  distribution: keep_original
  mode: sequential

sl:
  use_trader_updates: false
  break_even:
    enabled: false

updates:
  apply_move_stop: false
  apply_close_partial: false
  apply_close_full: false
  apply_cancel_pending: false
  apply_add_entry: false

pending:
  timeout_hours: 24
  auto_cancel: true
  cancel_on_new_signal: false

risk:
  mode: percent
  value: 0.02
  leverage: keep_original
  max_positions: 5

execution:
  latency_ms: 1000
  slippage_model: none
```

### 11.3 `be_after_tp1.yaml`

```yaml
name: be_after_tp1

entry:
  mode: keep_original
  allocation: keep_original
  force_order_type: keep

tp:
  use_count: all
  distribution: keep_original
  mode: sequential

sl:
  use_trader_updates: true
  break_even:
    enabled: true
    trigger:
      type: tp_hit
      value: 1
    offset: 0.0

updates:
  apply_move_stop: true
  apply_close_partial: true
  apply_close_full: true
  apply_cancel_pending: true
  apply_add_entry: true

pending:
  timeout_hours: 24
  auto_cancel: true
  cancel_on_new_signal: false

risk:
  mode: percent
  value: 0.02
  leverage: keep_original
  max_positions: 5

execution:
  latency_ms: 1000
  slippage_model: none
```

### 11.4 `tp_50_30_20.yaml`

```yaml
name: tp_50_30_20

entry:
  mode: keep_original
  allocation: keep_original
  force_order_type: keep

tp:
  use_count: 3
  distribution: [0.5, 0.3, 0.2]
  mode: sequential

sl:
  use_trader_updates: true
  break_even:
    enabled: false

updates:
  apply_move_stop: true
  apply_close_partial: true
  apply_close_full: true
  apply_cancel_pending: true
  apply_add_entry: true

pending:
  timeout_hours: 24
  auto_cancel: true
  cancel_on_new_signal: false

risk:
  mode: percent
  value: 0.02
  leverage: keep_original
  max_positions: 5

execution:
  latency_ms: 1000
  slippage_model: none
```

### 11.5 `entry_70_30.yaml`

```yaml
name: entry_70_30

entry:
  mode: override
  allocation: [0.7, 0.3]
  force_order_type: keep

tp:
  use_count: all
  distribution: keep_original
  mode: sequential

sl:
  use_trader_updates: true
  break_even:
    enabled: false

updates:
  apply_move_stop: true
  apply_close_partial: true
  apply_close_full: true
  apply_cancel_pending: true
  apply_add_entry: true

pending:
  timeout_hours: 24
  auto_cancel: true
  cancel_on_new_signal: false

risk:
  mode: percent
  value: 0.02
  leverage: keep_original
  max_positions: 5

execution:
  latency_ms: 1000
  slippage_model: none
```

---

## 12. Modello di dominio — classi principali

### 12.1 Event enums

```python
from enum import Enum

class EventType(str, Enum):
    OPEN_SIGNAL = "OPEN_SIGNAL"
    ADD_ENTRY = "ADD_ENTRY"
    MOVE_STOP = "MOVE_STOP"
    MOVE_STOP_TO_BE = "MOVE_STOP_TO_BE"
    CLOSE_PARTIAL = "CLOSE_PARTIAL"
    CLOSE_FULL = "CLOSE_FULL"
    CANCEL_PENDING = "CANCEL_PENDING"

class EventSource(str, Enum):
    TRADER = "trader"
    ENGINE = "engine"

class TradeStatus(str, Enum):
    NEW = "NEW"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"
```

### 12.2 Event model

```python
from datetime import datetime
from pydantic import BaseModel
from typing import Any, Literal

class CanonicalEvent(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str | None = None
    side: Literal["long", "short"] | None = None
    timestamp: datetime
    event_type: EventType
    source: EventSource
    payload: dict[str, Any]
    sequence: int
```

### 12.3 Order / fill model

```python
from pydantic import BaseModel
from typing import Literal

class EntryPlan(BaseModel):
    role: Literal["primary", "averaging"]
    order_type: Literal["market", "limit"]
    price: float | None = None
    size_ratio: float

class FillRecord(BaseModel):
    price: float
    qty: float
    timestamp: datetime
    source_event_sequence: int
```

### 12.4 Trade state

```python
class TradeState(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: Literal["long", "short"]
    status: TradeStatus

    entries_planned: list[EntryPlan] = []
    fills: list[FillRecord] = []

    pending_size: float = 0.0
    open_size: float = 0.0
    avg_entry_price: float | None = None

    initial_sl: float | None = None
    current_sl: float | None = None

    tp_levels: list[float] = []
    realized_pnl: float = 0.0
    fees_paid: float = 0.0

    created_at: datetime | None = None
    first_fill_at: datetime | None = None
    closed_at: datetime | None = None
```

### 12.5 Warning model

```python
class SimulationWarning(BaseModel):
    signal_id: str
    timestamp: datetime
    code: str
    message: str
    event_type: str
    state_snapshot: dict
```

### 12.6 Results model

```python
class TradeResult(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    status: str
    close_reason: str | None = None

    created_at: datetime | None = None
    first_fill_at: datetime | None = None
    closed_at: datetime | None = None
    duration_seconds: float | None = None

    entries_count: int = 0
    avg_entry_price: float | None = None
    max_position_size: float = 0.0
    final_position_size: float = 0.0

    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_paid: float = 0.0

    mae: float | None = None
    mfe: float | None = None
    warnings_count: int = 0
    ignored_events_count: int = 0
```

---

## 13. Contratti dati minimi

### 13.1 Input atteso dall'adapter
Per ogni chain il DB deve poter fornire almeno:

- `signal_id`
- `trader_id` o equivalente
- `symbol`
- `side`
- timestamp eventi
- sequenza ordinata eventi
- payload iniziale con:
  - entries
  - stop loss
  - take profits

### 13.2 Output dell'adapter
Lista ordinata di `CanonicalEvent`, con:
- ordine deterministico
- mapping corretto degli eventi V1
- normalizzazione dei campi principali

### 13.3 Output del simulatore
- event log engine
- trade result
- warnings
- artifacts opzionali (plot, report, export)

---

## 14. Regole operative dettagliate

### 14.1 OPEN_SIGNAL
Richiede minimo:
- entry
- SL
- TP

Se mancano:
- chain non simulabile

### 14.2 ADD_ENTRY
- può essere `market` o `limit`
- rappresenta tranche indipendente

### 14.3 CLOSE_PARTIAL
- se size non specificata -> default 50%
- default deve essere configurabile

### 14.4 CANCEL_PENDING
- se non ci sono fill -> cancella tutto
- se posizione già attiva -> cancella solo i pending residui

### 14.5 Eventi con stesso timestamp
- vale l'ordine del DB

### 14.6 Incoerenze
- ignored + warning
- la chain continua

### 14.7 Latency-aware behavior
Un update si applica solo se:
- al suo `timestamp` simulativo
- esiste già lo stato necessario

---

## 15. Market data design

### 15.1 Requisiti
Il market layer deve supportare:

- timeframe principale replay
- timeframe inferiore per intrabar
- lookup per `symbol + timestamp`
- risoluzione collisioni SL/TP

### 15.2 Provider iniziali consigliati
- CSV provider
- Parquet provider

### 15.3 Interfaccia esempio

```python
class MarketDataProvider:
    def get_candle(self, symbol: str, timeframe: str, ts: datetime): ...
    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime): ...
    def get_intrabar_range(self, symbol: str, parent_timeframe: str, child_timeframe: str, ts: datetime): ...
```

---

## 16. Event log design

### 16.1 Event log minimo
Per ogni evento trader o engine:

- `timestamp`
- `signal_id`
- `event_type`
- `source`
- `price_reference`
- `requested_action`
- `executed_action`
- `status`
- `reason`
- `state_before`
- `state_after`

### 16.2 Scopo
Serve per:
- audit
- debug
- plotting
- confronto trader vs engine

---

## 17. Output e artifact

### 17.1 Event log
Formato consigliato:
- Parquet per batch
- JSONL per debug

### 17.2 Trade results
Formato consigliato:
- Parquet
- CSV export opzionale

### 17.3 Scenario results
Formato consigliato:
- Parquet
- JSON summary

### 17.4 Plot
Tipi richiesti:

#### Plot singola chain
- candlestick o price line
- entry
- averaging
- SL
- TP
- TP colpiti
- SL colpito
- close partial
- close full

#### Overlay trader vs engine
- update trader
- eventi eseguiti realmente

#### Plot aggregati
- equity curve
- drawdown curve
- confronto scenari
- distribuzione PnL

---

## 18. Metriche

### 18.1 Trade-level
- realized PnL
- unrealized PnL
- MAE
- MFE
- duration
- entries count
- warnings count
- ignored events count

### 18.2 Portfolio-level
- total PnL
- return %
- max drawdown
- win rate
- profit factor
- expectancy

### 18.3 Scenario comparison
- delta PnL
- delta drawdown
- delta win rate
- delta expectancy
- stability score

### 18.4 Optimization output
Ogni trial deve salvare:
- params
- metriche
- score finale

---

## 19. Optimizer design

### 19.1 Parametri candidati
- entry allocation
- numero TP usati
- TP distribution
- break-even trigger
- pending timeout
- latency
- slippage model
- leverage
- risk per trade

### 19.2 Struttura base

```python
def objective(trial):
    policy = build_policy_from_trial(trial)
    result = simulator.run(dataset, policy)
    score = compute_score(result)
    return score
```

### 19.3 Search space esempio

```python
def build_policy_from_trial(trial):
    return {
        "entry_allocation": [
            trial.suggest_float("entry_1", 0.1, 0.9),
            trial.suggest_float("entry_2", 0.1, 0.9),
        ],
        "use_tp_count": trial.suggest_int("use_tp_count", 1, 3),
        "be_trigger": trial.suggest_categorical("be_trigger", ["none", "tp1", "tp2"]),
        "pending_timeout_hours": trial.suggest_int("pending_timeout_hours", 1, 48),
    }
```

---

## 20. Fasi di sviluppo

### Fase 0 — Audit e preparazione
Obiettivo:
- capire se il DB esistente è riusabile senza riscrittura profonda

Task:
1. leggere schema esistente
2. estrarre esempi reali di chain
3. verificare mapping eventi
4. definire adapter
5. individuare anomalie frequenti

Deliverable:
- report audit DB
- mapping document
- lista gap

### Fase 1 — MVP simulatore
Obiettivo:
- primo replay end-to-end

Scope:
- adapter base
- validazione `NEW_SIGNAL`
- event model
- trade state
- state machine
- fill model base
- latency base
- timeout base
- event log
- trade results
- chain plot base

Deliverable:
- simulazione di una chain singola
- export event log
- plot PNG/HTML

### Fase 2 — Scenario runner
Obiettivo:
- confronto tra policy

Scope:
- `original_chain`
- `signal_only`
- 1-2 policy custom
- report scenario
- portfolio aggregation
- comparison plots

Deliverable:
- confronto multi-policy su dataset campione

### Fase 3 — Intrabar robusto
Obiettivo:
- gestire collisioni realistiche

Scope:
- intrabar resolver
- dataset child timeframe
- audit casi SL/TP same candle

Deliverable:
- replay realistico su casi ambigui

### Fase 4 — Optimizer
Obiettivo:
- ricerca parametri migliore

Scope:
- integrazione Optuna
- search space iniziale
- scoring
- salvataggio trial
- ranking configurazioni

Deliverable:
- studio Optuna replicabile

### Fase 5 — Reporting avanzato
Obiettivo:
- rendere il sistema utile per decisioni operative

Scope:
- report HTML
- confronto scenari
- dashboard offline iniziale
- plotting esteso

Deliverable:
- pacchetto report completo

### Fase 6 — V2 realism
Scope:
- slippage
- fee models
- multi-market nuances
- partial fills più realistici

### Fase 7 — V3 realism
Scope:
- order book / tick-like handling
- funding
- liquidation logic
- regole exchange-specific avanzate

---

## 21. Pianificazione tecnica consigliata

### Sprint 1
- repo init
- pyproject
- settings
- logging
- adapter skeleton
- domain models
- tests skeleton

### Sprint 2
- state machine
- simulator base
- fill model
- timeout manager

### Sprint 3
- event log
- trade results
- chain plot base

### Sprint 4
- policy loader
- original_chain + signal_only
- scenario runner

### Sprint 5
- intrabar resolver
- integration tests su casi reali

### Sprint 6
- optimizer
- scoring
- search space

### Sprint 7
- reporting
- exports
- HTML plots

---

## 22. Acceptance criteria per fase

### Fase 0
- DB letto correttamente
- adapter documentato
- almeno 20 chain reali analizzate

### Fase 1
- simulazione end-to-end su chain singola
- event log coerente
- trade result coerente
- plot generato

### Fase 2
- confronto `original_chain` vs `signal_only`
- metriche aggregate corrette

### Fase 3
- casi SL/TP same candle risolti via intrabar

### Fase 4
- optimizer produce trial salvati e ranking

---

## 23. Strategia di test

### Unit tests
- event mapping
- state transitions
- fill model
- timeout rules
- warning logic

### Integration tests
- chain completa da input DB a trade result
- scenario comparison
- intrabar collision cases

### Golden tests
- chain reali note
- output attesi congelati

### Regression tests
- nessuna regressione su metriche chiave
- nessun cambiamento accidentale nei warning

---

## 24. Handoff diretto all'agente di sviluppo

L'agente che riceve questo documento deve:

1. creare la repo structure proposta
2. generare `pyproject.toml`
3. generare `.env.example`
4. creare domain models Pydantic
5. creare skeleton dell'adapter
6. creare skeleton del simulator
7. creare config policies iniziali
8. creare test scaffolding
9. pianificare lo sviluppo secondo le fasi elencate
10. evitare di riscrivere il parser o chain reconstruction salvo audit negativo

### Priorità assolute
- adapter prima del refactor
- event log prima di optimizer
- correctness prima di features
- replay singola chain prima di portfolio
- baseline policies prima di optimization

---

## 25. Domande aperte che possono restare fuori dal MVP

- fee model specifico per exchange
- slippage model realistico
- partial fills probabilistici
- funding / liquidation
- gestione precisa simboli multi-exchange
- dashboards web complete

---

## 26. Checklist finale per bootstrap repo

- [ ] creare struttura cartelle
- [ ] creare pyproject
- [ ] creare settings
- [ ] creare domain models
- [ ] creare enums
- [ ] creare chain adapter skeleton
- [ ] creare state machine skeleton
- [ ] creare simulator skeleton
- [ ] creare market provider interface
- [ ] creare policy loader
- [ ] creare due policy baseline
- [ ] creare tests base
- [ ] creare script `audit_existing_db.py`
- [ ] creare script `run_single_chain.py`
- [ ] creare script `run_scenario.py`

---

## 27. Riassunto esecutivo finale

Questo progetto deve essere implementato come:

- **core custom event-driven**
- con **adapter sul DB esistente**
- con **market replay realistico**
- con **policy modulari**
- con **optimizer separato sopra il motore**
- con forte enfasi su:
  - auditabilità
  - riproducibilità
  - confronto scenari
  - plotting e report

Il primo obiettivo non è l'ottimizzazione.  
Il primo obiettivo è ottenere un **replay corretto, spiegabile e validabile** di una signal chain reale.

Una volta ottenuto questo, si aggiungono:
- confronto scenari
- intrabar robusto
- optimizer
- realism avanzato

---

## 28. Allegato — esempio sequenza minima di sviluppo codice

Ordine pratico raccomandato:

1. `domain/enums.py`
2. `domain/events.py`
3. `domain/trade_state.py`
4. `adapters/validators.py`
5. `adapters/chain_adapter.py`
6. `engine/state_machine.py`
7. `engine/fill_model.py`
8. `engine/simulator.py`
9. `reports/trade_report.py`
10. `visualization/chain_plot.py`
11. `policies/base.py`
12. `policies/policy_loader.py`
13. `scripts/run_single_chain.py`
14. `scripts/run_scenario.py`
15. `optimizer/objective.py`
16. `optimizer/runner.py`

---
