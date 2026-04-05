# Documentazione Completa — Signal Chain Backtesting Lab
**Versione:** draft-2  
**Generata:** 2026-04-05

---

## 1. Scopo del documento

Questo documento definisce il **Product Requirements Document (PRD)** del progetto **Signal Chain Backtesting Lab**.

Il suo scopo è:

1. descrivere in modo chiaro il **problema da risolvere**
2. fissare il **perimetro funzionale** del sistema
3. formalizzare le **decisioni architetturali vincolanti**
4. definire il **modello operativo** della simulazione
5. fornire una base coerente per:
   - progettazione tecnica
   - creazione della struttura repository
   - pianificazione dello sviluppo incrementale
   - implementazione da parte di agenti AI o sviluppatori

Questo documento **non** descrive un framework generico di backtesting basato su indicatori.

Il sistema target è invece un **laboratorio di backtesting event-driven per signal chains**, costruito per simulare, confrontare e ottimizzare sequenze di segnali trading già ricostruite in un database esistente.

---

## 2. Visione del prodotto

### Visione

**Signal Chain Backtesting Lab** è un sistema progettato per valutare in modo riproducibile l’efficacia reale di segnali trading derivati da catene operative già parse e ricostruite.

L’unità di analisi non è il singolo messaggio e non è il singolo trade isolato, ma una **signal chain** composta da:

- segnale iniziale
- eventuali entry multiple
- aggiornamenti operativi successivi
- modifiche a stop loss
- chiusure parziali o totali
- cancellazione di ordini pendenti
- eventuale scadenza o invalidazione della chain

Il sistema deve supportare due modalità dati native:

1. **chain complete**
   - segnale iniziale
   - eventuali entry multiple
   - update operativi successivi
   - gestione stop loss
   - chiusure parziali o totali
   - cancellazione ordini pendenti
   - eventuale scadenza o invalidazione

2. **signal-only**
   - solo segnale iniziale
   - nessun update successivo disponibile nel dataset

### Problema che il prodotto risolve

Il prodotto deve permettere di capire:

- quanto una chain sia efficace **seguendo fedelmente il trader**
- quanto renda il **solo segnale iniziale**, ignorando gli update
- quali regole aggiuntive o sostitutive migliorino il risultato
- quali configurazioni siano più robuste su dataset reali

### Risultato atteso

Il sistema deve consentire il confronto sistematico tra più modalità di esecuzione della stessa chain, inclusi almeno:

- **original_chain**: esecuzione più vicina possibile alla sequenza del trader
- **signal_only**: esecuzione basata solo sul setup iniziale
- **custom_policy**: esecuzione con regole di gestione personalizzate
- **optimized_policy**: esecuzione con parametri ottimizzati dal motore

L’obiettivo finale non è solo calcolare PnL, ma fornire una base affidabile per:

- audit delle chain
- confronto tra stili di gestione
- test di policy alternative
- ottimizzazione controllata delle regole operative

La presenza di update successivi è quindi **opzionale a livello dati** e non è un prerequisito per la simulazione.

---

## 3. Principi architetturali vincolanti

1. **Core custom obbligatorio**
   - Il motore principale deve essere sviluppato su misura.
   - Framework esterni possono essere usati solo come supporto accessorio, non come nucleo decisionale del simulatore.

2. **Signal chain come unità logica primaria**
   - L’unità del sistema non è il singolo messaggio.
   - L’unità del sistema non è il singolo indicatore.
   - L’unità primaria è una **signal chain identificata da `signal_id`**.
   - Una signal chain può essere:
     - **estesa**, con eventi successivi al segnale iniziale
     - **minimale**, composta dal solo `NEW_SIGNAL`

3. **Separazione tra eventi trader e eventi engine**
   - Quello che il trader dichiara non coincide automaticamente con ciò che il motore esegue.
   - Il sistema deve distinguere sempre tra:
     - evento dichiarato dal dataset
     - azione effettivamente eseguibile
     - azione realmente eseguita

4. **Event-sourced e audit-first design**
   - Event log e state transitions sono centrali.
   - Ogni simulazione deve essere riproducibile, spiegabile e auditabile.
   - Il sistema deve tracciare almeno:
     - eventi input normalizzati
     - eventi engine generati
     - warnings
     - eventi ignorati
     - transizioni di stato

5. **State-aware e latency-aware simulation**
   - Un evento si applica solo se compatibile con:
     - lo stato realmente raggiunto dal simulatore
     - il timestamp simulativo
     - il comportamento del mercato replayato
   - Nessun update deve produrre effetti se la posizione o l’ordine richiesto non esistono nello stato simulato.

6. **Policy-driven behavior**
   - Le variazioni di logica non devono richiedere modifiche al core.
   - Devono essere introdotte tramite policy modulari e configurabili.

7. **Adapter-first integration**
   - Il sistema deve partire dal database già esistente.
   - Non si deve riscrivere subito la chain reconstruction.
   - L’integrazione iniziale deve passare da:
     - audit del DB
     - adapter canonico
     - validazione del mapping

8. **Massimo realismo compatibile con sviluppo incrementale**
   - L’obiettivo è un replay il più possibile realistico.
   - Il progetto deve però essere costruito per fasi:
     - MVP
     - V2 realism
     - V3 realism

---

## 4. Decisioni funzionali già definite

### 4.1 Unità primaria
- Unità primaria: **signal chain**
- Identificatore canonico: **`signal_id`**
- Una chain può essere:
  - **estesa**, con update successivi
  - **minimale**, composta dal solo segnale iniziale
- Il dataset può essere **multi-trader**
- Ogni chain simulata deve avere un **trader effettivo risolto**

Nota:
- la proprietà "multi-trader" appartiene al dataset / source context
- la singola chain deve sempre risultare assegnata a un solo trader effettivo

### 4.2 Start / End della chain
- Evento sorgente iniziale della chain: **`NEW_SIGNAL`**
- Evento canonico operativo iniziale del simulatore: **`OPEN_SIGNAL`**
- `OPEN_SIGNAL` viene generato dall'adapter o dal validator solo se il `NEW_SIGNAL` è simulabile

End possibili della chain:
- `CLOSED`
- `CANCELLED`
- `EXPIRED`
- `INVALID`

Nota:
- `CLOSED` è uno stato terminale
- la causa di chiusura deve essere tracciata separatamente come `close_reason`

### 4.3 Validità minima del segnale iniziale
Una chain entra nella **simulazione standard** solo se il `NEW_SIGNAL` contiene almeno:

- `entry`
- `stop loss`
- `take profit`

Se manca uno di questi elementi:
- la chain non entra nella simulazione standard
- può essere trattenuta per audit
- può essere ammessa in future modalità relaxed, ma non nel MVP standard

Questa regola vale sia per:
- chain complete con update
- chain signal-only

### 4.4 Eventi operativi V1 supportati
Il simulatore V1 deve supportare almeno i seguenti eventi canonici:

- `OPEN_SIGNAL`
- `ADD_ENTRY`
- `MOVE_STOP`
- `MOVE_STOP_TO_BE`
- `CLOSE_PARTIAL`
- `CLOSE_FULL`
- `CANCEL_PENDING`

Nota:
- `NEW_SIGNAL` resta un evento sorgente del dataset
- non è necessariamente un evento runtime del simulatore

### 4.5 Eventi esclusi dalla logica simulativa V1
Questi eventi possono essere salvati come metadati o per audit, ma **non guidano la simulazione V1**:

- `TP_HIT_INFO`
- `SL_HIT_INFO`
- `RESULT_REPORT`
- altri eventi puramente informativi

### 4.6 Stati del trade V1
Stati supportati:

- `NEW`
- `PENDING`
- `ACTIVE`
- `PARTIALLY_CLOSED`
- `CANCELLED`
- `CLOSED`
- `EXPIRED`
- `INVALID`

Regola:
- lo stato descrive la condizione della trade chain nel simulatore
- il motivo terminale deve essere salvato separatamente quando serve

### 4.7 Fill model V1
Assunzioni iniziali V1:

- `market`: fill dopo latenza configurata
- `limit`: fill touch-based secondo policy/configurazione

Regola:
- il comportamento "touch = fill garantito" è ammesso come default V1
- non deve essere modellato come verità universale del sistema

### 4.8 Conflitto SL / TP nella stessa barra
Target architetturale:
- risoluzione **intrabar**

Regola pratica per roadmap:
- nel MVP è ammesso un fallback deterministico con warning se il child timeframe non è disponibile
- dalla fase intrabar dedicata il sistema deve usare timeframe inferiore per i casi ambigui

### 4.9 Incoerenze
Modalità V1: **soft**

- evento incompatibile -> ignored
- warning loggato
- simulazione continua

Esempi:
- `MOVE_STOP` prima del fill -> ignored + warning
- `CLOSE_FULL` senza posizione attiva -> warning

### 4.10 Timeouts
Configurabili almeno:

- `pending_timeout`
- `chain_timeout`

Regola:
- i timeout devono essere applicati dal motore
- il loro esito deve essere visibile in event log e trade result

### 4.11 Baseline policy da supportare
Baseline minime richieste:

- `original_chain`
- `signal_only`

### 4.12 Policy modulari
Una policy può comporsi di:

- entry policy
- TP policy
- SL policy
- update policy
- pending policy
- risk policy
- execution policy

Nota:
- questa è la tassonomia target
- nel MVP non è obbligatorio che ogni sezione abbia già tutte le varianti avanzate

### 4.13 Dataset con soli segnali senza update
Il sistema deve supportare anche database in cui una chain contiene:

- solo segnale iniziale
- nessun update operativo successivo

In questo caso:
- la chain è pienamente valida se il `NEW_SIGNAL` contiene minimo `entry + SL + TP`
- la simulazione procede usando solo il setup iniziale
- questo caso coincide logicamente con una chain **signal-only nativa**
- non deve essere trattato come anomalia né come dataset incompleto

Implicazioni:
- l'adapter deve accettare chain con un solo evento operativo iniziale
- il simulatore non deve aspettarsi update successivi
- i report devono distinguere tra:
  - chain senza update per natura del dataset
  - chain con update disponibili ma ignorati da policy

---

## 5. Architettura logica di alto livello

L’architettura deve essere organizzata in livelli chiari, separando:

- integrazione dati
- simulazione core
- orchestrazione scenari
- reporting e ottimizzazione

### 5.1 Flusso logico principale

```text
DB esistente / chain reconstruction già disponibile
-> DB reader
-> canonical adapter
-> validator
-> canonical chain package
-> scenario runner
-> simulation engine
   + policy modules
   + market data layer
   + latency / fill / timeout handling
-> event log
-> trade result
-> scenario result
-> reporting / plots
```

### 5.2 Ruolo dei componenti

#### A. Data integration layer
Responsabilità:
- leggere il DB esistente
- recuperare chain già ricostruite
- normalizzare nel modello canonico del simulatore

Componenti:
- `db_reader`
- `chain_adapter`
- `mapping`
- `validators`

#### B. Canonical simulation layer
Responsabilità:
- applicare eventi canonici alla trade state
- gestire fill, stop, TP, close, timeout
- distinguere tra evento dichiarato e azione realmente eseguita

Componenti:
- `state_machine`
- `event_processor`
- `fill_model`
- `latency_model`
- `timeout_manager`
- `warning_manager`

#### C. Market layer
Responsabilità:
- replay del mercato
- lookup candele / intervalli
- supporto intrabar nei casi ambigui

Componenti:
- `market provider`
- `symbol mapper`
- `intrabar resolver`

#### D. Policy layer
Responsabilità:
- definire il comportamento configurabile del simulatore
- abilitare o disabilitare update
- gestire entry allocation, TP policy, SL policy, pending policy, risk policy, execution policy

Nota:
- il policy layer non è un post-processing
- agisce come input decisionale del simulatore

#### E. Scenario orchestration layer
Responsabilità:
- eseguire la stessa chain con più policy
- eseguire dataset multipli
- aggregare i risultati per confronto

Componenti:
- `run_single_chain`
- `run_scenario`
- portfolio/scenario aggregation

#### F. Audit and output layer
Responsabilità:
- salvare event log
- produrre trade results
- produrre scenario results
- generare export e plotting

### 5.3 Posizione dell’optimizer

L’optimizer non appartiene al core path della simulazione.

Deve stare sopra il motore come orchestratore esterno:

```text
optimizer
-> build policy candidate
-> scenario runner / simulator
-> scoring
-> ranking / saved trials
```

Regola:
- nessuna logica optimizer-specific deve contaminare il simulation core

### 5.4 Regola architetturale fondamentale

Il cuore del sistema deve essere:

```text
canonical chain + market data + policy -> simulator -> event log + results
```

e non:

```text
dataset raw -> logica custom per ogni trader -> risultati
```

Questo garantisce:
- auditabilità
- riuso
- confronto scenari
- compatibilità con dataset chain-complete e signal-only

---

## 6. Vincolo strategico: riuso del database esistente

Esiste già un sistema che ricostruisce le signal chains nel database sorgente.

Questo introduce un vincolo progettuale forte:

### Regola di progetto
**Il simulatore deve nascere sopra il DB esistente, non sopra una nuova pipeline di parsing/reconstruction.**

Il punto di partenza obbligatorio è quindi:

```text
DB esistente -> DB reader -> canonical adapter -> validator -> simulator
```

e non:

```text
raw telegram -> parse -> reconstruction -> simulator
```

### Ordine obbligatorio delle attività iniziali
Prima di qualunque refactor profondo bisogna eseguire:

1. **audit del DB esistente**
2. **verifica del contratto dati minimo richiesto dal simulatore**
3. **adapter canonico** dal formato attuale al modello eventi/stati del simulatore
4. **validazione del mapping su chain reali**
5. solo dopo, eventuali correzioni o estensioni mirate del sistema sorgente

### Obiettivo del vincolo
Questo vincolo serve a:

- ridurre il rischio di riscrittura prematura
- ottenere rapidamente un replay end-to-end validabile
- separare i problemi del simulatore dai problemi del parser/reconstruction
- permettere audit realistici su dati già esistenti

### Quando è lecito superare questo vincolo
La chain reconstruction esistente può essere modificata solo se l’audit mostra almeno una di queste condizioni:

- impossibilità di ottenere il contratto dati minimo richiesto
- perdita sistematica di informazioni operative rilevanti
- mapping ambiguo non risolvibile nell’adapter
- incoerenze strutturali che impediscono replay affidabile

### Regola di governance
Fino a prova contraria:
- il **DB esistente è la source of truth operativa iniziale**
- l’**adapter assorbe la complessità di integrazione**
- parser e reconstruction non vanno riscritti nel MVP

---

## 7. Struttura repository proposta

La repository va definita su due livelli:

1. **bootstrap structure minima**, necessaria per Fase 0 e Fase 1
2. **target structure completa**, da completare progressivamente nelle fasi successive

### 7.1 Bootstrap structure minima

```text
signal_chain_lab/
├─ README.md
├─ pyproject.toml
├─ .env.example
├─ configs/
│  ├─ app.yaml
│  ├─ logging.yaml
│  └─ policies/
│     ├─ original_chain.yaml
│     └─ signal_only.yaml
├─ docs/
│  ├─ architecture.md
│  ├─ data-contracts.md
│  └─ development-phases.md
├─ src/
│  └─ signal_chain_lab/
│     ├─ __init__.py
│     ├─ settings.py
│     ├─ logging_config.py
│     ├─ adapters/
│     │  ├─ db_reader.py
│     │  ├─ chain_adapter.py
│     │  ├─ validators.py
│     │  └─ mapping.py
│     ├─ domain/
│     │  ├─ enums.py
│     │  ├─ events.py
│     │  ├─ trade_state.py
│     │  ├─ warnings.py
│     │  └─ results.py
│     ├─ engine/
│     │  ├─ simulator.py
│     │  ├─ state_machine.py
│     │  ├─ fill_model.py
│     │  ├─ latency_model.py
│     │  └─ timeout_manager.py
│     ├─ market/
│     │  ├─ data_models.py
│     │  ├─ symbol_mapper.py
│     │  └─ providers/
│     │     ├─ __init__.py
│     │     ├─ parquet_provider.py
│     │     └─ csv_provider.py
│     ├─ policies/
│     │  ├─ base.py
│     │  └─ policy_loader.py
│     └─ reports/
│        ├─ event_log_report.py
│        └─ trade_report.py
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ fixtures/
│  └─ golden/
└─ scripts/
   ├─ audit_existing_db.py
   ├─ run_single_chain.py
   └─ run_scenario.py
```

### 7.2 Target structure completa

La struttura completa può poi estendersi con:

- moduli policy specializzati
- reporting avanzato
- visualization
- optimizer
- persistence dedicata risultati
- export avanzati

Questi moduli non sono obbligatori nel bootstrap iniziale.

### 7.3 Regola di modularità
La repo deve essere progettata in modo che:

- i package del core simulativo siano stabili presto
- i moduli avanzati possano essere aggiunti senza rifattorizzare il core
- optimizer, reporting avanzato e realism non blocchino il primo replay end-to-end

### 7.4 Regola di priorità strutturale

Nel bootstrap iniziale sono obbligatori solo i moduli necessari a:

- leggere il DB esistente
- produrre chain canoniche
- simulare una chain singola
- produrre event log e trade result minimi
- confrontare almeno `original_chain` e `signal_only`

Tutto il resto può essere introdotto progressivamente.

---

## 8. Dipendenze consigliate

Le dipendenze devono essere classificate in base al loro ruolo reale nel progetto, distinguendo tra bootstrap del simulatore, sviluppo, analytics e ottimizzazione.

### 8.1 Runtime core (bootstrap iniziale)

#### `pydantic`
Uso:
- data contracts
- validazione eventi
- validazione payload
- modelli dominio e risultati

#### `pydantic-settings`
Uso:
- gestione settings da env
- configurazione centralizzata dell'app

#### `PyYAML`
Uso:
- lettura di `configs/app.yaml`
- lettura delle policy YAML

#### `numpy`
Uso:
- calcoli numerici
- metriche base
- supporto a logiche quantitative del simulatore

#### `sqlalchemy`
Uso:
- integrazione con DB esistente
- lettura / mapping dati
- compatibilità futura SQLite / PostgreSQL

Nota:
- `sqlalchemy` è core per l’integrazione dati
- non è parte del simulation core in senso stretto

### 8.2 Runtime utili ma non obbligatorie nel bootstrap

#### `matplotlib`
Uso:
- plot base della singola chain
- export statici minimi per MVP

#### `orjson`
Uso:
- serializzazione JSON veloce per event log e artifact

#### `typer`
Uso:
- CLI pulite per `run_single_chain`, `run_scenario`, `audit_existing_db`

#### `rich`
Uso:
- output CLI leggibile
- logging locale più chiaro

### 8.3 Dev / test essentials

#### `pytest`
Uso:
- unit tests
- integration tests
- regression tests
- golden tests

#### `pytest-cov`
Uso:
- coverage

#### `ruff`
Uso:
- lint
- check stile
- qualità base repository

#### `mypy`
Uso:
- controllo statico tipi
- migliore robustezza del core

### 8.4 Analytics / reporting / optimization extras

#### `pandas`
Uso:
- aggregazioni scenario / portfolio
- export tabellari
- analisi risultati

#### `pyarrow`
Uso:
- storage Parquet
- dataset veloci per risultati e market data

#### `plotly`
Uso:
- chart interattivi
- report HTML
- plotting avanzato

#### `duckdb`
Uso:
- query veloci su Parquet
- analisi massiva offline

#### `polars`
Uso:
- alternativa veloce a pandas su dataset grandi

#### `optuna`
Uso:
- optimizer
- ricerca spazio parametri
- studi replicabili

---

## 9. Esempio dipendenze — `pyproject.toml`

Il file `pyproject.toml` deve riflettere la distinzione tra:

- runtime core del simulatore
- extra per CLI
- extra per plotting
- extra per analytics
- extra per optimizer
- dipendenze di sviluppo e test

Configurazione consigliata:

```toml
[project]
name = "signal-chain-lab"
version = "0.1.0"
description = "Event-driven backtesting lab for signal chains"
requires-python = ">=3.12"

dependencies = [
  "pydantic>=2.0",
  "pydantic-settings>=2.0",
  "PyYAML>=6.0",
  "sqlalchemy>=2.0",
  "numpy>=1.26",
]

[project.optional-dependencies]
cli = [
  "typer>=0.12",
  "rich>=13.0",
  "orjson>=3.0",
]

plot = [
  "matplotlib>=3.8",
]

analytics = [
  "pandas>=2.0",
  "pyarrow>=15.0",
  "duckdb>=1.0",
  "polars>=1.0",
  "plotly>=5.0",
]

optimizer = [
  "optuna>=4.0",
]

dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "mypy>=1.0",
  "ruff>=0.5",
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

La configurazione deve essere divisa in due livelli distinti:

1. **global runtime config**
   - ambiente applicativo
   - DB e path
   - market data sources
   - output / artifact settings
   - default tecnici

2. **scenario / policy config**
   - comportamento della simulazione
   - gestione update
   - TP / SL rules
   - risk rules
   - execution behavior

### 10.1 Regola di separazione

La configurazione globale non deve contenere logica di simulazione scenario-specific quando questa può variare tra policy.

Regola:
- `app.yaml` contiene infrastruttura e default
- i file policy contengono le scelte di comportamento del replay

### 10.2 `.env.example`

Le env vars devono coprire soprattutto:

- `APP_ENV`
- `LOG_LEVEL`
- `DATABASE_URL`
- `RESULTS_DB_URL`
- `MARKET_DATA_DIR`
- `DEFAULT_TIMEZONE`
- `ARTIFACTS_DIR`

Opzionale nelle fasi successive:
- storage optimizer
- study name optimizer

### 10.3 `configs/app.yaml`

`app.yaml` deve contenere solo configurazione applicativa stabile, ad esempio:

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
  intrabar:
    supported: true
    enabled_by_default: false
    default_child_timeframe: "1m"

runtime_defaults:
  inconsistency_mode: soft
  pending_timeout_hours: 24
  chain_timeout_hours: 168

artifacts:
  output_dir: "./artifacts"
  save_event_logs: true
  save_trade_reports: true
  save_plots_png: true
  save_plots_html: false
```

### 10.4 Cosa non deve stare in `app.yaml` come vincolo assoluto

Questi parametri non devono essere trattati come hardcoded globali se possono variare tra scenari:

- latency
- fill touch guarantee
- slippage model
- break-even behavior
- TP distribution
- update application rules

Questi devono vivere nella policy oppure essere overridable per scenario.

### 10.5 Optimizer config

La configurazione optimizer deve essere separabile dal bootstrap iniziale, ad esempio in:

- `configs/optimizer.yaml`
oppure
- env vars dedicate abilitate solo quando il modulo optimizer viene introdotto

---

## 11. Policy configuration

Le policy devono descrivere il **comportamento della simulazione** per singolo scenario.

Regola:
- la policy non descrive l’infrastruttura applicativa
- la policy non sostituisce il contratto dati
- la policy governa il comportamento del replay

### 11.1 Struttura logica delle policy

Ogni policy può contenere queste sezioni:

- `entry`
- `tp`
- `sl`
- `updates`
- `pending`
- `risk`
- `execution`

Questa tassonomia è il contratto logico standard del sistema.

### 11.2 Distinzione tra obbligatorio e opzionale

#### Campi obbligatori minimi
- `name`
- `updates`
- `execution`

#### Campi fortemente consigliati
- `entry`
- `tp`
- `sl`
- `pending`

#### Campi opzionali o scenario-dependent
- `risk`

Regola:
- i campi mancanti devono essere riempiti da default espliciti
- il `policy_loader` non deve inferire comportamenti impliciti non documentati

### 11.3 Regola di semantica

La policy deve poter esprimere almeno tre categorie di comportamento:

1. **keep trader behavior**
   - conserva la logica del dataset quando disponibile

2. **ignore trader behavior**
   - ignora update o componenti del dataset

3. **override with engine behavior**
   - sostituisce il comportamento trader con regole del simulatore

### 11.4 Baseline obbligatorie

#### `original_chain`
Scopo:
- eseguire la chain nel modo più fedele possibile al dataset disponibile

Regole:
- update trader supportati
- TP e allocazioni originali mantenute dove possibile
- stop trader updates ammessi
- execution defaults applicati dal simulatore

#### `signal_only`
Scopo:
- eseguire solo il setup iniziale ignorando gli update successivi

Regole:
- tutti gli update trader disabilitati
- gestione solo del setup iniziale
- pienamente compatibile sia con dataset completi sia con dataset signal-only

Nota:
- va distinta nei report la differenza tra:
  - dataset realmente privo di update
  - dataset con update ignorati dalla policy

### 11.5 Evoluzione del blocco `updates`

Nel bootstrap iniziale è ammesso usare flag semplici come:

- `apply_move_stop`
- `apply_close_partial`
- `apply_close_full`
- `apply_cancel_pending`
- `apply_add_entry`

Ma il modello target deve poter evolvere verso regole più espressive, ad esempio:

- applica sempre
- applica solo se posizione attiva
- applica solo dopo primo fill
- applica solo se compatibile con lo stato
- ignora e lascia warning

### 11.6 Distinzione tra execution e runtime config

La sezione `execution` della policy può contenere parametri scenario-specific come:

- `latency_ms`
- `slippage_model`

Ma questi devono restare overridable e non sostituire la configurazione infrastrutturale globale.

### 11.7 Esempi di policy

Esempi validi:
- `original_chain`
- `signal_only`
- `be_after_tp1`
- `tp_50_30_20`
- `entry_70_30`

Questi esempi servono come:
- baseline
- esempi di override mirati
- base iniziale per scenario comparison e optimizer

---

## 12. Modello di dominio — classi principali

Il modello di dominio deve rappresentare in modo esplicito:

- la chain input proveniente dall’adapter
- gli eventi canonici del simulatore
- lo stato della trade nel tempo
- le policy caricate
- il log auditabile degli eventi
- il risultato finale del replay

### 12.1 Enums principali

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

class ChainInputMode(str, Enum):
    CHAIN_COMPLETE = "chain_complete"
    SIGNAL_ONLY_NATIVE = "signal_only_native"

class EventProcessingStatus(str, Enum):
    APPLIED = "applied"
    IGNORED = "ignored"
    REJECTED = "rejected"
    GENERATED = "generated"

class CloseReason(str, Enum):
    TP = "tp"
    SL = "sl"
    MANUAL = "manual"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INVALID = "invalid"
    EXPIRED = "expired"
```

### 12.2 Chain input model

```python
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any

class CanonicalEvent(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    timestamp: datetime
    event_type: EventType
    source: EventSource
    payload: dict[str, Any] = Field(default_factory=dict)
    sequence: int

    source_event_type: str | None = None
    source_record_id: str | None = None

class CanonicalChain(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    input_mode: ChainInputMode
    has_updates_in_dataset: bool
    created_at: datetime
    events: list[CanonicalEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 12.3 Order / fill model

```python
from pydantic import BaseModel, Field
from typing import Literal

class EntryPlan(BaseModel):
    role: Literal["primary", "averaging"]
    order_type: Literal["market", "limit", "unknown"]
    price: float | None = None
    size_ratio: float
    label: str | None = None
    sequence: int | None = None

class FillRecord(BaseModel):
    price: float
    qty: float
    timestamp: datetime
    source_event_sequence: int | None = None
    fee_paid: float = 0.0
```

### 12.4 Trade state

```python
class TradeState(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    status: TradeStatus

    input_mode: ChainInputMode
    policy_name: str

    entries_planned: list[EntryPlan] = Field(default_factory=list)
    fills: list[FillRecord] = Field(default_factory=list)

    pending_size: float = 0.0
    open_size: float = 0.0
    avg_entry_price: float | None = None
    max_position_size: float = 0.0

    initial_sl: float | None = None
    current_sl: float | None = None
    tp_levels: list[float] = Field(default_factory=list)
    next_tp_index: int = 0

    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_paid: float = 0.0

    warnings_count: int = 0
    ignored_events_count: int = 0

    close_reason: CloseReason | None = None
    terminal_reason: str | None = None

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
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
```

### 12.6 Event log model

```python
class EventLogEntry(BaseModel):
    timestamp: datetime
    signal_id: str
    event_type: str
    source: str

    requested_action: str | None = None
    executed_action: str | None = None
    processing_status: EventProcessingStatus

    price_reference: float | None = None
    reason: str | None = None

    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)
```

### 12.7 Policy model

```python
class PolicyConfig(BaseModel):
    name: str
    entry: dict[str, Any] = Field(default_factory=dict)
    tp: dict[str, Any] = Field(default_factory=dict)
    sl: dict[str, Any] = Field(default_factory=dict)
    updates: dict[str, Any] = Field(default_factory=dict)
    pending: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)
```

### 12.8 Results model

```python
class TradeResult(BaseModel):
    signal_id: str
    trader_id: str | None = None
    symbol: str
    side: str
    status: str
    input_mode: ChainInputMode
    policy_name: str
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

### 12.9 Regola di progetto sul dominio

Il dominio del simulatore deve rappresentare:

- cosa arriva dal dataset
- cosa il simulatore tenta di applicare
- cosa viene realmente applicato
- quale stato risulta
- perché un evento è stato ignorato o applicato

Il dominio non deve dipendere da strutture raw Telegram o da formati parser-specific.

---

## 13. Contratti dati minimi

Questa sezione definisce il contratto minimo tra:

- database sorgente / adapter
- modello canonico del simulatore

Obiettivo:
- chiarire cosa serve per identificare una chain
- chiarire cosa serve per dichiararla simulabile
- distinguere errori bloccanti da dati opzionali

### 13.1 Contratto minimo per identificare una chain

Per ogni unità simulabile il DB deve poter fornire almeno:

- `signal_id`
- `timestamp` del segnale iniziale
- `trader_id` oppure informazione sufficiente a risolvere il trader effettivo
- `symbol`
- `side`

Senza questi campi:
- la chain non è accettabile come input canonico
- può essere solo segnalata come anomalia del dataset

### 13.2 Contratto minimo per simulazione standard

Per entrare nella simulazione standard, il `NEW_SIGNAL` iniziale deve fornire almeno:

- una o più `entries`
- `stop_loss`
- uno o più `take_profit`

Questa regola vale sia per:
- chain complete con update
- chain signal-only

Se manca uno di questi elementi:
- la chain non entra nella simulazione standard
- resta disponibile per audit
- può essere ammessa in future modalità relaxed, ma non nel MVP standard

### 13.3 Update successivi

Gli update successivi sono **opzionali**.

Quindi una unità simulabile può essere:

#### A. Chain completa
- `NEW_SIGNAL`
- zero o più update operativi successivi

#### B. Signal-only nativa
- solo `NEW_SIGNAL`
- nessun update successivo nel dataset

Regola:
- entrambi i casi sono validi
- l’assenza di update non è di per sé una anomalia

### 13.4 Mapping verso modello canonico

L’adapter deve trasformare il dato sorgente in un oggetto canonico equivalente a:

- `CanonicalChain`
- lista ordinata di `CanonicalEvent`

Campi minimi attesi nel modello canonico:

#### `CanonicalChain`
- `signal_id`
- `symbol`
- `side`
- `input_mode`
- `has_updates_in_dataset`
- `created_at`
- `events[]`

#### `CanonicalEvent`
- `signal_id`
- `timestamp`
- `event_type`
- `source`
- `sequence`
- `payload`

### 13.5 Classificazione dei gap dati

I gap del dataset devono essere classificati almeno in tre categorie:

#### Fatal for simulation
Esempi:
- manca `signal_id`
- manca `symbol`
- manca `side`
- manca `entry`
- manca `stop_loss`
- manca `take_profit`

Effetto:
- chain esclusa dalla simulazione standard

#### Warning
Esempi:
- `trader_id` non presente ma risolvibile indirettamente
- metadata secondari mancanti
- campi opzionali incompleti

Effetto:
- chain simulabile con warning

#### Optional enrichment
Esempi:
- tags aggiuntivi
- note parser
- metriche ausiliarie
- raw references

Effetto:
- nessun impatto sulla simulazione base

### 13.6 Regola di ordinamento eventi

Gli eventi devono essere ordinabili in modo deterministico almeno per:

- `timestamp`
- `sequence`

Se il DB non consente ordinamento deterministico:
- il gap deve emergere in audit
- l’adapter non deve inventare un ordine non giustificato

### 13.7 Regola di source of truth iniziale

Nel bootstrap iniziale:
- il DB esistente è la source of truth
- l’adapter traduce
- il validator verifica
- il simulatore non corregge il dataset sorgente

Eventuali correzioni della reconstruction sorgente sono ammesse solo dopo audit negativo strutturato.

---

## 14. Regole operative dettagliate

Questa sezione definisce la semantica runtime minima del simulatore.

Regola generale:
- ogni evento canonico deve essere valutato rispetto a:
  - stato corrente della trade
  - timestamp simulativo
  - policy attiva
  - disponibilità di prezzo/mercato necessario

### 14.1 OPEN_SIGNAL
Richiede minimo:
- entry
- SL
- TP

Se mancano:
- chain non simulabile nello standard mode

Effetti runtime:
- inizializza `TradeState`
- carica piano entry
- imposta SL iniziale
- imposta TP iniziali
- determina se lo stato parte come `PENDING` o `ACTIVE` in base al fill model e al tipo ordine

### 14.2 ADD_ENTRY
- può essere `market` o `limit`
- rappresenta una tranche aggiuntiva o di averaging
- è applicabile solo se compatibile con:
  - policy attiva
  - stato non terminale
  - posizione/order lifecycle corrente

Se incompatibile:
- ignored + warning

### 14.3 MOVE_STOP
- aggiorna lo stop corrente a un nuovo livello esplicito
- è valido solo se esiste una posizione aperta o una logica pending compatibile
- non può essere applicato su chain già terminale

Se incompatibile:
- ignored + warning

### 14.4 MOVE_STOP_TO_BE
- sposta lo stop al break-even secondo definizione policy/runtime
- può usare:
  - entry medio
  - entry iniziale
  - eventuale offset configurato

Se la posizione non è ancora attiva:
- ignored + warning

### 14.5 CLOSE_PARTIAL
- riduce la posizione aperta senza chiuderla interamente
- se la size non è specificata, usa un fallback configurabile
- il fallback del MVP può essere 50%, ma deve essere esplicito e configurabile
- la percentuale si applica alla **open size residua al momento dell’evento**

Se non esiste posizione aperta:
- ignored + warning

### 14.6 CLOSE_FULL
- chiude tutta la posizione residua
- porta la chain in stato terminale `CLOSED`, salvo diversa classificazione di close reason

Se non esiste posizione aperta:
- ignored + warning

### 14.7 CANCEL_PENDING
- se non ci sono fill: cancella tutti gli ordini pendenti
- se esiste posizione attiva: cancella solo i pending residui
- se non esistono pending: ignored + warning

### 14.8 Eventi con stesso timestamp
Ordine di risoluzione:
1. usare l’ordine deterministico fornito dall’adapter
2. se non esiste criterio migliore, usare l’ordine del DB
3. il simulatore non deve inventare un ordinamento non auditabile

### 14.9 Incoerenze
Modalità V1:
- ignored + warning
- la chain continua

Esempi:
- `MOVE_STOP` prima del fill
- `CLOSE_FULL` senza posizione attiva
- `ADD_ENTRY` su chain già chiusa

### 14.10 Latency-aware behavior
Un evento si applica solo se:
- al suo timestamp simulativo
- esiste già lo stato necessario
- la chain non è terminale
- la policy ne consente l’applicazione

### 14.11 Trigger di mercato
Il motore deve anche gestire eventi engine-driven derivati dal mercato, almeno per:
- fill ordini
- hit di stop
- hit di take profit
- timeout pending
- timeout chain

Nota:
- gli eventi trader non esauriscono la dinamica del replay
- il simulatore deve produrre anche eventi engine interni coerenti con mercato e stato

---

## 15. Market data design

Il market layer deve essere progettato come componente critico del replay, non come semplice accesso a file OHLCV.

Deve fornire al simulatore una fonte di verità temporale e di prezzo sufficiente per:

- fill ordini
- trigger di stop loss
- trigger di take profit
- timeout valutati sul tempo di mercato
- risoluzione di casi ambigui intrabar

### 15.1 Requisiti funzionali

Il market layer deve supportare almeno:

- timeframe principale di replay
- timeframe inferiore per intrabar
- lookup per `symbol + timeframe + timestamp`
- query su range temporali
- rilevazione di collisioni SL/TP nella stessa barra
- gestione di assenza dati / buchi di mercato in modo esplicito

### 15.2 Requisiti di integrazione

Il market layer deve gestire anche:

- `symbol mapping` tra simboli del DB sorgente e simboli del dataset di mercato
- normalizzazione timezone
- metadati su provider, timeframe e coverage disponibile

Regola:
- il simulatore non deve contenere mapping simboli hardcoded
- il mapping deve essere centralizzato nel market layer

### 15.3 Provider iniziali consigliati

Provider minimi iniziali:

- `CSVProvider`
- `ParquetProvider`

Questi provider devono essere intercambiabili dietro una interfaccia comune.

### 15.4 Interfaccia logica minima

```python
class MarketDataProvider:
    def has_symbol(self, symbol: str) -> bool: ...
    def get_candle(self, symbol: str, timeframe: str, ts: datetime): ...
    def get_range(self, symbol: str, timeframe: str, start: datetime, end: datetime): ...
    def get_intrabar_range(self, symbol: str, parent_timeframe: str, child_timeframe: str, ts: datetime): ...
    def get_metadata(self, symbol: str, timeframe: str): ...
```

### 15.5 Regola intrabar

L’intrabar non deve essere eseguito sempre per default.

Uso raccomandato:
- attivarlo solo nei casi ambigui o quando richiesto dalla configurazione dello scenario

Se il child timeframe non è disponibile:
- il sistema deve usare fallback deterministico
- il fallback deve essere tracciato in warning / event log

### 15.6 Separazione delle responsabilità

#### Provider
Responsabilità:
- leggere i dati di mercato
- restituire candele e range
- dichiarare copertura e assenza dati

#### Intrabar resolver
Responsabilità:
- usare il child timeframe quando necessario
- determinare l’ordine plausibile dei trigger nella barra parent
- restituire un esito auditabile

#### Symbol mapper
Responsabilità:
- risolvere il simbolo usato dal simulatore verso il simbolo del dataset di mercato

### 15.7 Regola di auditabilità

Ogni decisione di replay dipendente dal mercato deve poter essere ricondotta a:

- simbolo usato
- timeframe usato
- timestamp o range consultato
- eventuale fallback applicato
- eventuale mancanza di dati

---

## 16. Event log design

L’event log è il record canonico del replay.

Non serve solo a “salvare eventi”, ma a spiegare in modo auditabile:

- cosa è arrivato dal dataset
- cosa il simulatore ha tentato di fare
- cosa ha realmente eseguito
- quale stato ne è derivato
- perché un evento è stato applicato, ignorato o rifiutato

### 16.1 Regola generale

Per ogni evento trader o engine rilevante il sistema deve produrre una `EventLogEntry`.

L’event log è obbligatorio nel MVP.

### 16.2 Campi minimi obbligatori

Per ogni record devono essere disponibili almeno:

- `timestamp`
- `signal_id`
- `policy_name`
- `event_type`
- `source`
- `requested_action`
- `executed_action`
- `processing_status`
- `reason`
- `state_before`
- `state_after`

Campi fortemente consigliati:
- `trader_id`
- `symbol`
- `side`
- `input_mode`
- `price_reference`
- `source_event_sequence`

### 16.3 Semantica di `processing_status`

Il log deve distinguere almeno tra:

- `APPLIED`
- `IGNORED`
- `REJECTED`
- `GENERATED`

Dove:
- `APPLIED` = evento eseguito con effetto sullo stato
- `IGNORED` = evento non applicabile ma non fatale
- `REJECTED` = evento scartato per violazione o condizione bloccante
- `GENERATED` = evento creato dal motore a partire da mercato, timeout o stato

### 16.4 Snapshot minimo dello stato

`state_before` e `state_after` devono contenere almeno un sottoinsieme stabile e confrontabile di stato, ad esempio:

- `trade_status`
- `open_size`
- `pending_size`
- `avg_entry_price`
- `current_sl`
- `next_tp_index`
- `realized_pnl`

Regola:
- il log deve essere abbastanza ricco per audit
- ma non deve dipendere da dump arbitrari dell’intero oggetto runtime

### 16.5 Tracciabilità del mercato

Quando una decisione dipende dal mercato, il log deve poter riportare anche:

- `market_symbol`
- `timeframe_used`
- `price_reference`
- eventuale `intrabar_used`
- eventuale `fallback_used`

Questo è particolarmente importante per:
- fill
- stop hit
- tp hit
- collisioni same-candle

### 16.6 Contesto di scenario

Ogni log deve essere attribuibile senza ambiguità a:

- chain simulata
- policy/scenario usato
- modalità input del dataset

Questo è necessario per confrontare:
- `original_chain`
- `signal_only`
- policy custom
- dataset signal-only nativi vs update ignorati da policy

### 16.7 Relazione con warning e report

Regola:
- l’event log è il record primario
- warning, trade result, plot e report sono output derivati o collegati all’event log

### 16.8 Formati di persistenza

Formati consigliati:
- `JSONL` per debug locale e ispezione line-by-line
- `Parquet` per batch, analytics e confronto scenari

---

## 17. Output e artifact

Gli output del sistema devono essere organizzati in livelli, distinguendo tra:

- artifact primari di replay
- risultati derivati di trade
- aggregazioni di scenario
- visualizzazioni e report

### 17.1 Gerarchia degli artifact

#### A. Artifact primario obbligatorio
- `event_log`

#### B. Artifact derivato obbligatorio
- `trade_result`

#### C. Artifact aggregato
- `scenario_result`

#### D. Artifact visuali / opzionali
- plot chain
- HTML report
- dashboard export futuri

### 17.2 Artifact minimi del MVP

Per il MVP ogni run deve poter produrre almeno:

- `event_log.jsonl`
- `trade_results.parquet`

Per run di scenario o batch:
- `scenario_results.parquet`

### 17.3 Regola di derivazione

Regola:
- `trade_results` deve essere derivato in modo coerente dall’event log e dallo stato finale
- `scenario_results` deve essere derivato da insiemi di `trade_results`
- plot e report non devono introdurre logica propria che alteri i risultati

### 17.4 Distinzione per livello di esecuzione

#### Run singolo
Artifact tipici:
- event log della chain
- trade result della chain
- plot della chain

#### Run scenario
Artifact tipici:
- event log per chain/run
- trade results multipli
- scenario result aggregato

#### Run optimizer / batch avanzato
Artifact tipici:
- risultati multipli per policy candidate
- ranking / score
- export trial-level

### 17.5 Identità degli artifact

Ogni artifact deve essere collegabile almeno a:

- `run_id`
- `signal_id` oppure insieme di chain
- `policy_name`
- `scenario_id` se applicabile
- `input_mode` quando rilevante

### 17.6 Formati consigliati

- `JSONL` per event log
- `Parquet` per trade/scenario results
- `PNG` o equivalente per plot statici
- `HTML` opzionale per report interattivi

### 17.7 Priorità di sviluppo

Ordine corretto di implementazione:

1. `event_log`
2. `trade_results`
3. `scenario_results`
4. plot chain
5. HTML report

Regola:
- gli artifact visuali non devono bloccare il completamento del core replay

---

## 18. Metriche

Le metriche devono essere organizzate in quattro livelli distinti:

1. metriche per trade
2. metriche aggregate di scenario / portfolio
3. metriche di confronto tra scenari
4. metriche di scoring per optimizer

### 18.1 Metriche trade-level

Ogni `trade_result` deve includere almeno:

#### Metriche economiche
- `realized_pnl`
- `unrealized_pnl` (solo se rilevante)
- `fees_paid`

#### Metriche di rischio / escursione
- `mae`
- `mfe`

#### Metriche temporali
- `duration_seconds`
- `first_fill_at`
- `closed_at`

#### Metriche strutturali
- `entries_count`
- `max_position_size`
- `final_position_size`
- `close_reason`

#### Metriche di qualità replay
- `warnings_count`
- `ignored_events_count`
- `input_mode`
- `policy_name`

### 18.2 Metriche scenario / portfolio-level

Ogni `scenario_result` deve poter includere almeno:

- `total_pnl`
- `return_pct`
- `max_drawdown`
- `win_rate`
- `profit_factor`
- `expectancy`

Metriche fortemente consigliate:
- `trades_count`
- `simulated_chains_count`
- `excluded_chains_count`
- `avg_warnings_per_trade`
- `avg_ignored_events_per_trade`

### 18.3 Metriche di confronto scenari

Per confrontare due o più policy/scenari servono almeno:

- `delta_pnl`
- `delta_drawdown`
- `delta_win_rate`
- `delta_expectancy`

Metriche aggiuntive consigliate:
- `delta_profit_factor`
- `delta_avg_duration`
- `delta_warning_rate`

### 18.4 Stability / robustness metrics

Se si introduce uno `stability_score`, questo non deve essere una label vaga.

Deve essere:
- definito esplicitamente
- derivato da componenti note
- confrontabile tra run

Fino a definizione formale, è meglio trattarlo come:
- metrica opzionale
- placeholder di fase successiva

### 18.5 Metriche per optimizer

Ogni trial optimizer deve salvare almeno:

- `params`
- metriche base di scenario
- `score_finale`

Regola:
- lo `score_finale` deve essere derivato da metriche esplicite e documentate
- non deve essere una black box non spiegabile

---

## 19. Optimizer design

L’optimizer deve essere un layer esterno al simulatore.

Il suo compito è:
- generare policy candidate
- eseguire replay/scenario run con il motore esistente
- calcolare score confrontabili
- salvare trial e ranking

Regola:
- l’optimizer non deve introdurre logica speciale nel simulation core

### 19.1 Posizionamento architetturale

Flusso corretto:

```text
optimizer
-> build policy candidate
-> scenario runner / simulator
-> compute metrics
-> compute score
-> save trial
-> ranking
```

### 19.2 Parametri ottimizzabili — fase iniziale

Search space iniziale consigliato solo su parametri già ben supportati dal core, ad esempio:

- `entry_allocation`
- `use_tp_count`
- `tp_distribution`
- `be_trigger`
- `pending_timeout_hours`

Questi parametri sono adatti alla fase iniziale perché:
- sono già modellabili come policy
- non richiedono realism avanzato
- non contaminano il core simulativo

### 19.3 Parametri da rinviare

Non devono entrare nello search space iniziale parametri che dipendono da realism non ancora robusto, ad esempio:

- `slippage_model` avanzato
- partial fills probabilistici
- funding
- liquidation
- logiche exchange-specific avanzate

Questi possono essere introdotti solo dopo le fasi dedicate al realism.

### 19.4 Obiettivo dell’optimizer

L’optimizer deve ottimizzare principalmente su:
- dataset benchmark
- scenario result aggregati

Non deve essere pensato principalmente come ottimizzatore di una singola chain isolata.

### 19.5 Struttura base

```python
def objective(trial):
    policy = build_policy_from_trial(trial)
    scenario_result = scenario_runner.run(dataset=benchmark_dataset, policy=policy)
    score = compute_score(scenario_result)
    return score
```

### 19.6 Scoring

Lo `score` deve essere:
- esplicito
- documentato
- spiegabile

Deve derivare da metriche note, ad esempio:
- `return_pct`
- `max_drawdown`
- `expectancy`
- penalità per warning rate
- penalità per ignored event rate
- penalità per excluded chains

Regola:
- nessuno score black-box non spiegabile

### 19.7 Anti-overfitting

L’optimizer deve essere progettato con cautele minime contro overfitting, ad esempio:

- benchmark dataset separato
- possibile split train / validation nelle fasi successive
- riesecuzione dei top trial con replay auditabile completo

### 19.8 Trial artifact

Ogni trial deve salvare almeno:

- `trial_id`
- `params`
- metriche principali
- `score_finale`
- `scenario_id` o benchmark usato

Per i top trial è fortemente consigliato salvare anche:
- link o riferimento agli artifact del replay
- summary dei warning
- summary delle chain escluse

---

## 20. Fasi di sviluppo

La roadmap deve privilegiare:

1. correttezza del replay
2. auditabilità
3. confronto scenari
4. ottimizzazione
5. realism avanzato
6. reporting avanzato

### Fase 0 — Audit e preparazione
Obiettivo:
- verificare che il DB esistente sia riusabile senza riscrittura profonda

Task principali:
- leggere schema esistente
- estrarre chain reali campione
- verificare mapping eventi
- definire adapter canonico
- classificare gap e anomalie frequenti

Deliverable:
- report audit DB
- mapping document
- lista gap
- contratto dati minimo validato

### Fase 1 — MVP replay core
Obiettivo:
- primo replay end-to-end corretto di una chain singola

Scope minimo:
- adapter base
- validazione `NEW_SIGNAL`
- event model
- trade state
- state machine
- fill model base
- timeout base
- event log
- trade result

Scope opzionale leggero:
- plot base della chain

Deliverable:
- simulazione di una chain singola
- event log coerente
- trade result coerente

### Fase 1.5 — Hardening su chain reali
Obiettivo:
- validare il replay su casi campione reali

Scope:
- golden tests iniziali
- replay su chain note
- verifica warning / ignored events
- confronto con aspettative manuali

Deliverable:
- set di chain benchmark validate
- primi regression test affidabili

### Fase 2 — Scenario runner
Obiettivo:
- confronto tra policy sulla stessa chain o dataset

Scope:
- `original_chain`
- `signal_only`
- 1-2 policy custom
- scenario runner
- scenario results
- aggregazioni base

Deliverable:
- confronto multi-policy su dataset campione
- metriche aggregate corrette

### Fase 3 — Intrabar / realism milestone 1
Obiettivo:
- gestire collisioni realistiche e casi ambigui

Scope:
- intrabar resolver
- dataset child timeframe
- audit casi SL/TP same candle
- fallback deterministici tracciati

Deliverable:
- replay realistico su casi ambigui
- warning/fallback auditabili

### Fase 4 — Optimizer
Obiettivo:
- ricerca di parametri policy su benchmark dataset

Prerequisiti:
- scenario runner stabile
- metriche scenario stabili
- score esplicito
- trial artifact minimi

Scope:
- integrazione optimizer
- search space iniziale limitato
- scoring spiegabile
- salvataggio trial
- ranking configurazioni

Deliverable:
- studio optimizer replicabile

### Fase 5 — Reporting avanzato
Obiettivo:
- rendere il sistema utile per analisi operative e confronto leggibile

Scope:
- report HTML
- confronto scenari esteso
- plotting avanzato
- dashboard offline iniziale

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

La pianificazione tecnica deve seguire la maturità del replay, non la sola visibilità delle feature.

### Sprint 1 — Bootstrap e contratti
- repo init
- pyproject
- settings
- logging
- test skeleton
- domain enums / events / trade state
- adapter skeleton
- validator skeleton

Obiettivo:
- fissare contratti dominio + adapter + test base

### Sprint 2 — Replay core minimo auditabile
- state machine
- simulator base
- fill model base
- timeout manager
- event log minimo
- trade result minimo

Obiettivo:
- primo replay singolo corretto e già auditabile

### Sprint 3 — Policy baseline e run singolo
- policy model
- policy loader
- `original_chain`
- `signal_only`
- `run_single_chain`
- output artifact minimi

Opzionale leggero:
- chain plot base

Obiettivo:
- replay singolo governato da policy baseline

### Sprint 4 — Hardening su chain reali
- integration tests su chain campione
- golden tests iniziali
- verifica warning / ignored events
- benchmark set iniziale

Obiettivo:
- validazione forte del replay su casi reali

### Sprint 5 — Scenario runner
- `run_scenario`
- scenario results
- aggregazioni base
- confronto `original_chain` vs `signal_only`
- 1-2 policy custom

Obiettivo:
- confronto multi-policy coerente

### Sprint 6 — Intrabar / realism milestone 1
- intrabar resolver
- child timeframe support
- audit casi SL/TP same candle
- fallback tracciati

Obiettivo:
- gestione robusta dei casi ambigui

### Sprint 7 — Optimizer
- optimizer runner
- scoring esplicito
- search space iniziale limitato
- salvataggio trial
- ranking

Obiettivo:
- primo optimizer replicabile su benchmark dataset

### Sprint 8 — Reporting avanzato
- exports
- HTML report
- plotting avanzato
- scenario comparison visuals

Obiettivo:
- pacchetto report leggibile per analisi operative

---

## 22. Acceptance criteria per fase

I criteri di accettazione devono verificare non solo la presenza delle feature, ma anche:

- correttezza del replay
- auditabilità
- riproducibilità
- readiness della fase successiva

### Fase 0 — Audit e preparazione
La fase è accettata se:

- il DB esistente viene letto correttamente
- il contratto dati minimo è verificato su esempi reali
- l’adapter mapping è documentato
- almeno 20 chain reali sono analizzate
- i gap dataset sono classificati in:
  - fatal for simulation
  - warning
  - optional enrichment

### Fase 1 — MVP replay core
La fase è accettata se:

- almeno una chain reale valida viene simulata end-to-end
- una chain signal-only valida viene simulata correttamente
- una chain senza setup minimo viene esclusa correttamente dalla simulazione standard
- l’event log viene prodotto ed è coerente con:
  - eventi input
  - azioni eseguite
  - stato finale
- il trade result è coerente con l’event log
- warning e ignored events sono tracciati correttamente

Nota:
- il plot base è utile ma non è criterio bloccante del core replay

### Fase 1.5 — Hardening su chain reali
La fase è accettata se:

- esiste un set iniziale di chain benchmark validate
- golden tests iniziali sono presenti
- replay e warning su casi campione risultano stabili
- non emergono discrepanze critiche tra aspettative manuali e replay del motore

### Fase 2 — Scenario runner
La fase è accettata se:

- la stessa chain o dataset può essere eseguita con almeno:
  - `original_chain`
  - `signal_only`
- i risultati dei run sono distinguibili per `policy_name`
- vengono prodotti `scenario_results` aggregati coerenti
- il confronto tra policy è riproducibile

### Fase 3 — Intrabar / realism milestone 1
La fase è accettata se:

- i casi SL/TP same candle vengono risolti usando intrabar quando disponibile
- se il child timeframe manca, viene applicato fallback deterministico
- fallback e warning risultano tracciati in log
- esiste un set minimo di casi campione intrabar validati

### Fase 4 — Optimizer
La fase è accettata se:

- l’optimizer esegue trial salvati e ranking
- lo score è esplicito e documentato
- lo search space iniziale è limitato a parametri supportati
- i trial sono riproducibili sul benchmark dataset
- i top trial possono essere rieseguiti tramite scenario runner

### Fase 5 — Reporting avanzato
La fase è accettata se:

- report e visualizzazioni vengono generati senza alterare la logica dei risultati
- il contenuto dei report è coerente con event log, trade results e scenario results
- gli artifact visuali sono chiaramente derivati e non fonte di verità

### Fase 6 — V2 realism
La fase è accettata se:

- modelli realism aggiuntivi (fee/slippage/partial fills) sono configurabili
- i nuovi effetti sono tracciabili in log e metriche
- non introducono regressioni inattese nei benchmark baseline

### Fase 7 — V3 realism
La fase è accettata se:

- le logiche avanzate exchange-specific sono isolate dal core
- i benchmark baseline restano riproducibili
- il livello di complessità aggiuntiva è auditabile e testato

---

## 23. Strategia di test

La strategia di test deve verificare non solo che le feature esistano, ma che il replay sia:

- corretto
- auditabile
- stabile nel tempo
- riproducibile su chain reali

### 23.1 Famiglie di test

Il sistema deve avere almeno queste famiglie di test:

- `unit tests`
- `integration tests`
- `golden tests`
- `regression tests`

### 23.2 Unit tests

Devono coprire almeno:

- event mapping
- validazione `NEW_SIGNAL`
- state transitions
- fill model
- timeout rules
- warning logic

Casi minimi raccomandati:
- segnale valido vs segnale non simulabile
- `MOVE_STOP` prima del fill -> ignored + warning
- `CLOSE_FULL` senza posizione attiva
- `CANCEL_PENDING` con pending presenti vs assenti
- distinzione tra `requested_action` e `executed_action`

### 23.3 Integration tests

Devono coprire almeno:

- chain completa da input DB a trade result
- chain `signal-only` nativa da input DB a trade result
- scenario comparison
- intrabar collision cases

Regola:
- almeno un test di integrazione deve verificare end-to-end:
  - adapter
  - simulator
  - event log
  - trade result

### 23.4 Golden tests

I golden tests devono essere basati su:

- chain reali note
- output attesi congelati
- benchmark cases mantenuti stabili nel repository

Scopo:
- rilevare cambiamenti non intenzionali nel replay
- validare il comportamento su casi reali ad alta priorità

Artifact da congelare quando appropriato:
- event log essenziale
- trade result essenziale
- warning summary

### 23.5 Regression tests

I regression tests devono proteggere almeno:

- metriche chiave
- warning / ignored events
- struttura semantica dell’event log

Regola:
- una modifica che non cambia il PnL ma altera warning o logica evento deve emergere nei test

### 23.6 Test intrabar

Per l’intrabar servono almeno:

- caso con child timeframe disponibile
- caso con child timeframe assente
- fallback deterministico verificato
- warning / log coerenti

### 23.7 Benchmark dataset di test

È fortemente consigliato mantenere un piccolo benchmark dataset stabile con:

- chain complete
- chain signal-only native
- casi con update incompatibili
- casi ambigui same-candle

Questo benchmark deve essere riutilizzato per:
- integration tests
- golden tests
- optimizer validation

---

## 24. Handoff diretto all’agente di sviluppo

L’agente che riceve questo documento deve implementare il progetto seguendo i vincoli e le priorità del PRD, non limitarsi a generare scaffolding.

### 24.1 Obiettivo immediato

Il primo obiettivo non è optimizer, reporting avanzato o realism avanzato.

Il primo obiettivo è ottenere un **replay corretto, auditabile e validabile** di una signal chain reale.

### 24.2 Output minimi richiesti all’agente

L’agente deve produrre almeno:

1. struttura repository bootstrap coerente con le fasi iniziali
2. `pyproject.toml` coerente con dipendenze bootstrap
3. `.env.example`
4. configurazione applicativa minima
5. domain models tipizzati
6. adapter skeleton + validator
7. simulator skeleton + state machine base
8. event log minimo canonico
9. policy baseline iniziali
10. test scaffolding + primi test reali
11. script minimi:
   - `audit_existing_db.py`
   - `run_single_chain.py`
   - `run_scenario.py`

### 24.3 Vincoli non negoziabili

L’agente deve rispettare queste regole:

- non riscrivere parser o chain reconstruction salvo audit negativo strutturato
- partire da `DB esistente -> adapter -> validator -> simulator`
- supportare sia:
  - chain complete
  - signal-only native
- trattare l’event log come record canonico del replay
- mantenere optimizer separato dal simulation core
- mantenere reporting e plotting come output derivati

### 24.4 Ordine corretto di implementazione

Ordine raccomandato:

1. contratti dominio e adapter
2. replay core minimo auditabile
3. event log + trade result
4. policy baseline
5. hardening su chain reali
6. scenario runner
7. intrabar milestone
8. optimizer
9. reporting avanzato

### 24.5 Cosa l’agente non deve anticipare

L’agente non deve anticipare:

- optimizer prima del core stabile
- reporting avanzato prima di event log e trade results
- realism avanzato prima dei benchmark base
- refactor parser/reconstruction senza evidenza da audit

### 24.6 Priorità assolute

- adapter prima del refactor
- event log prima di optimizer
- correctness prima di features
- replay singola chain prima di portfolio
- baseline policies prima di optimization
- golden tests reali prima di realism avanzato

---

## 25. Domande aperte fuori MVP

Questa sezione raccoglie temi importanti ma non bloccanti per il MVP.

Regola:
- il MVP non deve attendere la definizione completa di questi punti
- questi temi vanno trattati nelle fasi successive, mantenendo il core stabile e auditabile

### 25.1 Realism di esecuzione
Temi da definire nelle fasi successive:

- partial fills realistici
- fee model avanzato
- slippage model
- execution precision exchange-specific

### 25.2 Risk / portfolio layer
Temi da definire nelle fasi successive:

- leverage model completo
- liquidation logic
- portfolio constraints
- multi-asset concurrency

### 25.3 Market / exchange specifics
Temi da definire nelle fasi successive:

- funding
- perpetual-specific behavior
- regole exchange-specific avanzate

### 25.4 Data semantics / replay semantics
Temi da definire nelle fasi successive:

- timeframe resampling rules
- governance del fallback intrabar se il child timeframe non è disponibile
- regole future per relaxed mode su chain incomplete

### 25.5 Policy semantics da raffinare
Temi da definire nelle fasi successive:

- definizione finale del break-even:
  - initial entry
  - avg entry
  - offset-based
- semantica estesa del blocco `updates`
- regole avanzate per partial close sizing

### 25.6 Metriche e scoring
Temi da definire nelle fasi successive:

- formalizzazione dello `stability_score`
- eventuali score compositi per optimizer
- regole di penalizzazione standard per warning / excluded chains / ignored events

### 25.7 Regola architetturale
Quando questi temi verranno introdotti:

- non devono rompere il simulation core
- devono restare modulari
- devono essere auditabili e testabili separatamente

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


---

## 29. Integrazioni PRD per copertura gap di prodotto

Questa sezione integra il PRD con requisiti espliciti lato prodotto per coprire i gap residui tra il motore di simulazione già definito e il workflow operativo richiesto.

L’obiettivo è garantire che il sistema non sia solo un simulation core corretto, ma anche un prodotto utilizzabile per:

- acquisire dataset da fonti operative reali
- riusare e adattare parser esistenti con minima frizione
- costruire dataset simulabili senza lavoro manuale sul codice
- eseguire simulazioni da GUI semplice
- essere distribuito su altro PC o server in una fase successiva

### 29.1 Concetto principale del prodotto

Il concetto principale del prodotto è il **test dei segnali trading**.

Il sistema deve consentire all’utente di:

1. acquisire dati da una fonte operativa
2. applicare parser esistenti o nuovi parser specifici
3. costruire o verificare la chain dei messaggi/eventi
4. simulare il comportamento dei segnali in più configurazioni
5. confrontare i risultati in modo rapido, semplice e riproducibile

Il prodotto non è quindi solo un simulatore tecnico, ma una **workbench applicativa per il test dei segnali**.

### 29.2 Workflow utente target

Il workflow target di prodotto deve essere formalizzato come segue.

#### Step 1 — Acquisizione dati da fonte
Il sistema deve supportare l’acquisizione dati da almeno queste sorgenti:

- **canale Telegram**
- **topic di un canale Telegram**
- **chat Telegram**

Nota di progetto:
- esiste già una parte del sistema sorgente che acquisisce dati Telegram
- nel PRD questo componente non deve essere dato per scontato in modo implicito
- deve essere trattato come **modulo verificabile e integrabile** del prodotto

Requisiti minimi:
- selezione sorgente da configurazione o GUI
- identificazione della sorgente tramite `chat_id`, `channel_id`, `topic_id` o equivalente
- import incrementale o storicizzato, in base alle capacità del sistema sorgente
- stato di acquisizione visibile almeno a livello di log o schermata stato
- possibilità di lavorare anche su DB già popolato senza rieseguire l’ingestione

#### Step 2 — Applicazione parser
Dopo l’acquisizione, il sistema deve permettere di applicare il parser per estrazione di:

- segnali iniziali
- update operativi
- metadata utili alla chain reconstruction

Vincolo fondamentale:
- il parser esiste già ed è riusabile
- il prodotto deve facilitare il riuso del parser esistente senza richiedere refactor completo del core

#### Step 2.1 — Costruzione o verifica della chain
Il sistema deve supportare database in cui i dati possano apparire in una o più di queste forme:

- **chain completa**
- **solo segnale iniziale**
- **dataset attribuito a un singolo trader**
- **dataset multi-trader**

Requisito prodotto:
- la chain reconstruction esistente deve essere verificata e resa osservabile
- il sistema deve permettere audit e controllo qualità della chain costruita
- il simulatore deve poter ricevere dataset costruiti automaticamente dal layer esistente oppure dataset validati manualmente tramite strumenti di verifica

#### Step 3 — Simulazione di eventi e configurazioni
Il sistema deve permettere la simulazione su:

- dataset con **solo segnali**
- dataset con **segnali + update significativi**
- dataset con configurazioni differenti di policy e variabili operative

L’utente deve poter scegliere se eseguire test:

- fedeli alla chain originale
- basati solo sul segnale iniziale
- con update filtrati o reinterpretati
- con parametri personalizzati

### 29.3 Modulo prodotto: Data Acquisition

Il PRD deve includere esplicitamente un modulo di prodotto chiamato **Data Acquisition**.

Scopo del modulo:
- rendere utilizzabile e verificabile il flusso di ingestione dati da sorgenti operative reali
- separare il concetto di “fonte dati” dal concetto di “DB già pronto”

Responsabilità del modulo:
- configurazione sorgenti
- avvio importazione
- verifica ultimo stato acquisito
- lettura da DB già esistente
- sincronizzazione incrementale dove supportata
- diagnostica su errori di acquisizione

Output attesi del modulo:
- dataset raw o semi-strutturato persistito nel DB sorgente
- metadati minimi di provenienza
- stato di sincronizzazione
- log errori / warning

Il modulo può inizialmente riusare il codice già esistente, ma deve essere modellato come componente di prodotto con interfaccia chiara.

### 29.4 Modulo prodotto: Parser Management

Il PRD deve includere un modulo esplicito chiamato **Parser Management**.

Scopo del modulo:
- consentire il riuso del parser esistente
- facilitare la creazione di parser specifici o varianti di parser
- permettere aggiornamenti di vocabolario, alias, pattern e profili trader senza interventi invasivi sul core

#### Requisiti funzionali minimi
Il modulo deve permettere almeno:

- visualizzare i parser/profili disponibili
- duplicare un parser esistente come base di partenza
- modificare file di vocabolario, alias, mapping o pattern
- testare il parser su uno o più messaggi campione
- salvare una nuova variante parser con nome/versione distinta
- ripristinare rapidamente una configurazione precedente

#### Requisiti GUI minimi
La GUI non deve essere un editor avanzato di codice completo nel MVP, ma deve almeno consentire:

- selezione del parser attivo
- duplicazione di un parser/profilo
- modifica di testi configurativi o template parser tramite area di testo, copia/incolla o file editor semplice
- esecuzione di un test parser su input campione
- visualizzazione dell’output estratto

#### Vincolo di implementazione
Nel MVP è accettabile che il parser resti basato su file editabili, purché il prodotto offra una modalità semplice per:

- clonare i file necessari
- modificarli
- salvarli
- ricaricarli senza intervento manuale complesso sulla codebase

Questo requisito è soddisfatto anche da una GUI che opera come wrapper semplificato sopra file YAML/JSON/TXT/Python configurativi, purché il flusso utente sia semplice.

### 29.5 Modulo prodotto: Chain Builder / Dataset Builder

Il PRD deve includere un modulo esplicito chiamato **Chain Builder / Dataset Builder**.

Scopo del modulo:
- trasformare dati acquisiti e parse in un dataset simulabile e verificabile
- rendere trasparente all’utente se sta lavorando con chain complete o dataset signal-only

Il modulo deve supportare almeno questi tipi di dataset:

- **signal_only_native**: dataset che contiene solo segnali iniziali
- **chain_complete**: dataset con segnali e update ricostruiti
- **filtered_chain**: dataset in cui solo alcuni update sono considerati significativi
- **single_trader_dataset**
- **multi_trader_dataset**

Funzioni minime richieste:
- selezionare range temporale / sorgente / trader
- costruire dataset candidati alla simulazione
- eseguire validazione minima del dataset
- mostrare anomalie principali
- distinguere tra:
  - chain realmente prive di update
  - chain con update presenti ma non risolti
  - chain con update presenti ma filtrati da policy o configurazione

Output minimi richiesti:
- dataset simulabile
- report qualità dataset
- elenco chain escluse con motivazione

### 29.6 Verifica esplicita del sistema già esistente

Poiché alcune parti del workflow sono dichiarate come già esistenti, il PRD deve includere una fase esplicita di **verification-first integration**.

Le componenti da verificare obbligatoriamente sono:

1. ingestione da canale Telegram
2. ingestione da topic Telegram
3. ingestione da chat Telegram
4. parser esistente
5. chain reconstruction esistente
6. gestione dataset single-trader e multi-trader

Per ciascuna componente vanno definiti almeno:
- stato atteso
- evidenza di funzionamento
- gap rilevati
- decisione: riuso / correzione / sostituzione parziale

Questa verifica deve precedere i refactor profondi.

### 29.7 GUI operativa semplice

Il prodotto deve prevedere una **GUI semplice** come requisito funzionale esplicito.

Scopo della GUI:
- permettere l’uso del sistema senza intervenire direttamente sul codice nella maggior parte dei casi operativi
- rendere rapide le attività di configurazione, test e confronto scenari

#### Aree minime della GUI
La GUI MVP deve includere almeno queste aree o pagine:

1. **Sources / Import**
   - selezione sorgente
   - stato importazione o stato DB
   - eventuale avvio sync/import

2. **Parser**
   - scelta parser attivo
   - duplicazione / modifica semplice
   - test parser su messaggi campione

3. **Dataset / Chains**
   - selezione dataset
   - filtri per trader, periodo, sorgente, tipo chain
   - indicatori di qualità dataset

4. **Simulation**
   - scelta policy
   - modifica variabili principali
   - avvio simulazione
   - riepilogo warnings/errori

5. **Results**
   - metriche aggregate
   - confronto scenari
   - export risultati e log

#### Requisiti UI minimi
La GUI deve essere progettata per:
- semplicità operativa
- riduzione del numero di passaggi manuali
- leggibilità dei risultati
- possibilità di modificare impostazioni e variabili senza aprire file nel repository

Nel MVP è ammessa una GUI desktop semplice oppure una web UI locale leggera.

### 29.8 Variabili configurabili da GUI

Le variabili principali di simulazione devono essere modificabili da GUI o da pannello di configurazione semplice.

Esempi minimi:
- policy di simulazione
- timeout
- uso o esclusione update
- parametri di entry/fill di base
- filtri per trader o dataset
- risk settings principali
- configurazioni di scenario salvabili

Regola:
- la configurazione avanzata può restare su file
- la configurazione operativa più usata deve essere accessibile da interfaccia

### 29.9 Packaging, build e distribuzione

Il PRD deve includere una sezione esplicita di **Packaging & Deployment**.

Obiettivo:
- permettere in una fase successiva la distribuzione del prodotto su:
  - altro PC
  - server
  - ambiente operativo non di sviluppo

#### Requisiti minimi di roadmap
Devono essere previsti almeno questi target:

1. **developer mode**
   - esecuzione da repository
   - configurazione tramite file

2. **packaged desktop/server build**
   - build distribuibile
   - avvio semplificato
   - documentazione installativa minima

3. **future protected distribution**
   - sistema di verifica abilitazione/licenza
   - non richiesto nel MVP
   - deve però essere previsto come estensione architetturale possibile

#### Requisiti tecnici minimi da fissare nel PRD
- supporto a packaging riproducibile
- configurazione esterna separata dal core
- logging e diagnostica disponibili anche in build distribuita
- modalità headless o service-mode preferibile per uso server
- GUI o pannello accessibile quando il prodotto è installato fuori dall’ambiente di sviluppo

### 29.10 Modalità di deployment da supportare

Il prodotto deve essere concepito per supportare almeno due modalità di esecuzione.

#### A. Desktop mode
Per uso locale su PC dedicato:
- GUI locale
- accesso a dataset locali o DB configurato
- packaging installabile

#### B. Server mode
Per uso remoto o su macchina sempre accesa:
- esecuzione come servizio o processo persistente
- accesso remoto via GUI web o interfaccia equivalente
- separazione chiara tra configurazione, dati e log

Nel MVP non è obbligatorio implementare entrambe complete, ma il PRD deve mantenere compatibilità architetturale con entrambe.

### 29.11 Acceptance criteria trasversali di prodotto

Oltre agli acceptance criteria per fase, il PRD deve includere questi criteri trasversali di prodotto.

#### AC-PROD-01 — Acquisizione sorgenti
L’utente può lavorare con dati provenienti da:
- canale Telegram
- topic Telegram
- chat Telegram
oppure con DB già popolato derivato da tali sorgenti.

#### AC-PROD-02 — Verifica pipeline esistente
Il sistema espone una checklist o report di verifica che indica se ingestione, parser e chain reconstruction esistenti sono riusabili senza modifiche maggiori.

#### AC-PROD-03 — Gestione parser semplice
L’utente può duplicare o adattare un parser/profilo esistente con flusso semplificato, senza dover intervenire manualmente sul core del simulatore.

#### AC-PROD-04 — Test parser da interfaccia
L’utente può eseguire un test parser su input campione e visualizzare l’output estratto.

#### AC-PROD-05 — Costruzione dataset simulabile
L’utente può costruire un dataset simulabile distinguendo almeno tra:
- solo segnali
- segnali + update
- single trader
- multi trader

#### AC-PROD-06 — Simulazione da GUI
L’utente può lanciare una simulazione da GUI scegliendo dataset, policy e variabili principali senza modificare codice.

#### AC-PROD-07 — Risultati confrontabili
L’utente può confrontare almeno due scenari simulativi sullo stesso dataset.

#### AC-PROD-08 — Distribuibilità futura
La struttura del progetto supporta packaging e distribuzione su altro PC o server senza dipendere da un ambiente di sviluppo non replicabile.

#### AC-PROD-09 — Compatibilità con futura licenza
L’architettura non impedisce l’introduzione futura di un sistema di abilitazione o licenza, pur non richiedendolo nel MVP.

### 29.12 Priorità di implementazione dei gap

Ordine consigliato di implementazione:

1. verifica integrazione esistente
2. data acquisition verificabile
3. parser management minimo
4. dataset/chain builder con quality checks
5. simulation GUI minima
6. results GUI minima
7. packaging desktop/server base
8. licenze/abilitazione in fase successiva

Questa priorità serve a mantenere il focus sul valore principale del prodotto: **test rapido, configurabile e riproducibile dei segnali**.
