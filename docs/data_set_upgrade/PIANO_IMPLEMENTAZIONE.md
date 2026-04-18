# Piano di Implementazione — Market DATA Blocco 3

Basato su: `C:\Back_Testing\docs\data_set_upgrade\market_data_blocco3_documento_dettagliato_v2.md`
Codebase analizzata: `C:/Back_Testing/src/signal_chain_lab/`
Data: 2026-04-18

---

## Scope

### In scope
- Fase 1: Refactor UI — estrazione sotto-blocco Market DATA
- Fase 2: Buffer manuale e opzioni utente esplicite
- Fase 3: Planner chart-aware (execution window + chart window)
- Fase 4: Validazione rafforzata
- Fase 5: Multi-timeframe (parent TF + child TF selettivo)
- Fase 6: Stubs UI per tipi dati futuri (roadmap)

### Escluso esplicitamente
- Logica simulation-aware automatica basata su eventi terminali trader
- Rilevamento automatico timeout da policy YAML nel planner
- Copertura automatica: il buffer manuale è la soluzione adottata per entrambi i casi

---

## Stato attuale rilevante (da codebase)

| File | Righe | Ruolo attuale |
|------|-------|---------------|
| `ui/blocks/block_backtest.py` | 1132 | Contiene tutta la logica Market DATA mescolata al Backtest |
| `ui/state.py` | 87 | 15 variabili Market sparse nella dataclass principale UiState |
| `ui/app.py` | 90 | Entry point NiceGUI, composizione Blocco 3 |
| `ui/blocks/backtest_support.py` | 103 | Helper discovery DB, policy management |
| `market/planning/coverage_planner.py` | 159 | Buffer adattivo per profilo (intraday/swing/position) |
| `market/planning/demand_scanner.py` | 119 | Scansione segnali da DB SQLite |
| `market/planning/validation.py` | 169 | BatchValidator: schema, sort, dedup, coverage check |
| `market/preparation_cache.py` | 161 | Fingerprint SHA256 + validation_index.json |
| `market/sync/bybit_downloader.py` | 718 | Download incrementale Bybit V5 API |
| `scripts/plan_market_data.py` | 128 | Entry point planner CLI |
| `scripts/sync_market_data.py` | 398 | Entry point sync CLI |
| `scripts/validate_market_data.py` | 127 | Entry point validate CLI |
| `scripts/gap_validate_market_data.py` | 179 | Entry point gap-validate CLI |

`market/runtime_config.py` — **non esiste**, da creare.
`ui/blocks/market_data_panel.py` — **non esiste**, da creare.
`ui/blocks/market_data_support.py` — **non esiste**, da creare.

---

## Fase 1 — Refactor UI

**Obiettivo:** Estrarre la logica Market DATA da `block_backtest.py` in un panel autonomo collassabile dentro Blocco 3.

### File da creare

#### `src/signal_chain_lab/ui/blocks/market_data_panel.py` (NUOVO)

Panel NiceGUI collassabile con quattro sezioni interne:

| Sezione | Contenuto | Azione |
|---------|-----------|--------|
| Setup | Root market dir, dataset mode, validate mode, source, timeframe, buffer mode, tipo dati | Configura |
| Discovery | Simboli rilevati, finestre richieste, gap stimati, cache hit/miss | Analizza (read-only) |
| Run | Fasi: planner → sync → gap_validate → validate full | Prepara / Valida / Prepara+Valida |
| Result | Artifacts paths, coverage summary, validation summary, readiness badge | Solo visualizzazione |

Elementi UI obbligatori:
- Progress bar globale con percentuale e fase corrente (`PHASE=...`)
- Log strutturato per fase (append-only, scrollable)
- Riepilogo numerico: simboli, intervalli richiesti, gap totali, cache hit, artifacts
- Quattro pulsanti distinti: **Analizza**, **Prepara**, **Valida**, **Prepara + Valida**
- Stato finale visibile: badge `READY` / `READY (unvalidated)` / `NOT READY`

#### `src/signal_chain_lab/ui/blocks/market_data_support.py` (NUOVO)

Helper per orchestrazione e parsing stdout:
- `parse_progress_line(line: str) -> ProgressEvent | None` — legge protocollo `PHASE=... PROGRESS=... STEP=... SUMMARY=...`
- `format_coverage_summary(plan_json: dict) -> str` — formatta riepilogo simboli/gap
- `format_validation_summary(report_json: dict) -> str`
- `map_phase_label(phase: str) -> str` — etichette leggibili per progress bar

### File da modificare

#### `src/signal_chain_lab/ui/state.py`

Attuale: 15 variabili Market sparse in `UiState`.

Intervento: Introdurre sotto-struttura dedicata.

```python
@dataclass
class MarketState:
    # Setup
    market_data_dir: str = ""
    market_data_mode: str = "existing_dir"   # existing_dir | new_dir
    validate_mode: str = "light"             # full | light | off
    market_data_source: str = "bybit"
    # Timeframe
    download_tf: str = "1m"
    simulation_tf: str = "1m"               # parent TF (futuro Fase 5)
    detail_tf: str = "1m"                   # child TF (futuro Fase 5)
    price_basis: str = "last"
    # Buffer
    buffer_mode: str = "auto"               # auto | manual
    pre_buffer_days: int = 0
    post_buffer_days: int = 0
    buffer_preset: str = ""                 # intraday | swing | position | custom
    # Risultati
    market_ready: bool = False
    market_validation_status: str = "needs_check"
    market_validation_fingerprint: str = ""
    market_data_gap_count: int = 0
    latest_market_plan_path: str = ""
    latest_market_sync_report_path: str = ""
    latest_market_validation_report_path: str = ""
    market_prepare_total_seconds: float = 0.0

@dataclass
class UiState:
    # ... campi esistenti non-Market ...
    market: MarketState = field(default_factory=MarketState)
```

Tutti gli accessi `state.market_data_*` nei file esistenti vanno aggiornati a `state.market.*`.

#### `src/signal_chain_lab/ui/blocks/block_backtest.py`

- Rimuovere: tutto il metodo `_prepare_market_data()` e la sezione UI Market DATA
- Mantenere: lettura di `state.market.market_ready`, `state.market.market_validation_status`, `state.market.latest_artifact_path`
- Il Backtest consuma solo lo stato sintetico; non orchestra più la preparazione

#### `src/signal_chain_lab/ui/app.py`

- Importare e istanziare `MarketDataPanel`
- Comporre Blocco 3 come: `MarketDataPanel` (collassabile, in alto) + sezione Backtest (sotto)
- Passare `_run_streaming_command` al panel (pattern già usato)

---

## Fase 2 — Buffer manuale e opzioni utente esplicite

**Obiettivo:** Rendere il buffer una scelta esplicita invece di logica nascosta nel planner.

### Opzioni validate mode (sostituisce SAFE/FAST)

| Modalità | Fasi eseguite | Uso consigliato |
|----------|--------------|-----------------|
| Full | planner + sync + gap_validate + validate_full | Run importanti, QA |
| Light | planner + sync + gap_validate | Uso quotidiano |
| Off / Trust existing | Nessuna fase, riusa dataset | Power user, dataset già verificato |

### Buffer mode

**AUTO**: usa `CoveragePlanner` adattivo esistente (comportamento attuale, invariato).

**MANUAL**: l'utente imposta `pre_buffer_days` e `post_buffer_days`.
Preset rapidi:
- **Intraday**: pre=2d, post=1d
- **Swing**: pre=7d, post=3d
- **Position**: pre=30d, post=7d
- **Custom**: valori liberi

### File da modificare

#### `market/planning/coverage_planner.py`

Aggiungere supporto a override manuale:
```python
def plan(self, ..., manual_buffer: ManualBuffer | None = None) -> CoveragePlan:
    if manual_buffer:
        # usa pre/post buffer specificati, ignora profilo adattivo
    else:
        # comportamento attuale invariato
```

Struttura `ManualBuffer`:
```python
@dataclass
class ManualBuffer:
    pre_days: int
    post_days: int
    preset: str = "custom"
```

#### `scripts/plan_market_data.py`

Aggiungere argomenti CLI:
```
--buffer-mode   auto | manual  (default: auto)
--pre-buffer-days   int        (solo se manual)
--post-buffer-days  int        (solo se manual)
--buffer-preset     str        (intraday | swing | position | custom)
--validate-mode     full | light | off  (default: light)
```

---

## Fase 3 — Planner chart-aware ✅ Incrementata il 2026-04-18

**Obiettivo:** Il planner produce due finestre distinte; la finestra scaricata è la loro unione.

### Concetti

- **Execution window**: range minimo perché il simulatore possa vedere fill, TP, SL
- **Chart window**: execution window + pre-buffer visuale + post-buffer visuale indipendenti
- **Download window**: unione di execution window e chart window (sempre >= execution window)

Con buffer manuale attivo, l'utente controlla direttamente chart window pre/post. L'automatismo simulation-aware è escluso dallo scope.

### File da creare

#### `src/signal_chain_lab/market/runtime_config.py` (NUOVO)

```python
@dataclass
class MarketRuntimeConfig:
    download_tf: str
    simulation_tf: str     # parent TF per scansione principale
    detail_tf: str         # child TF per risoluzione intra-bar
    price_basis: str
    source: str
    buffer_mode: str       # auto | manual
    pre_buffer_days: int
    post_buffer_days: int
```

Funzione factory: `runtime_config_from_state(market_state: MarketState) -> MarketRuntimeConfig`

Stato attuale:
- `runtime_config.py` creato
- `MarketRuntimeConfig` implementato
- `runtime_config_from_state()` implementata con mapping diretto da `MarketState`

### File da modificare

#### `market/planning/coverage_planner.py`

- Output `CoveragePlan` deve includere:
  - `execution_window: list[Interval]`
  - `chart_window: list[Interval]` (= execution_window allargata con pre/post buffer)
  - `download_window: list[Interval]` (= unione, usata per il download effettivo)

Stato attuale:
- `CoveragePlan` ora espone `windows_by_symbol`
- `intervals_by_symbol` resta disponibile come vista retrocompatibile su `download_window`
- implementate `execution_window`, `chart_window`, `download_window` per simbolo

#### `scripts/plan_market_data.py`

- Output JSON del piano include le tre finestre per simbolo
- Retrocompatibile: `required_intervals` = `download_window` (nessuna breaking change a valle)

Stato attuale:
- output JSON esteso con `execution_window`, `chart_window`, `download_window`
- `required_intervals` mantenuto come alias di `download_window`
- downstream `sync_market_data.py` e `validate_market_data.py` restano compatibili senza modifiche strutturali

---

## Fase 4 — Validazione rafforzata

**Obiettivo:** `BatchValidator` garantisce qualità OHLC forte e continuità interna completa.

### File da modificare

#### `market/planning/validation.py`

Aggiungere step al `BatchValidator`:

**Step 5 — OHLC strong check** per ogni candela:
- `low <= open <= high`
- `low <= close <= high`
- `low <= high`
- `volume >= 0`

**Step 6 — Continuità interna**:
- Nessun gap temporale non atteso tra candele consecutive (data il timeframe)
- Tolleranza: ≤ 1 candela mancante (da configurare)

**Step 7 — Severity classificata**:
```python
class IssueSeverity(Enum):
    CRITICAL = "critical"   # dati inutilizzabili
    WARNING  = "warning"    # anomalia, dati usabili con cautela
    INFO     = "info"       # nota informativa
```

**Modalità incrementale**:
- `validate_incremental(new_intervals_only: bool)` — valida solo i gap appena scaricati
- Già parzialmente prevista da `gap_validate_market_data.py`, va estesa con i nuovi step

#### `scripts/validate_market_data.py`

- Output JSON include severity per ogni issue
- Aggiungere flag `--strict` per fallire su WARNING oltre che su CRITICAL

---

## Fase 5 — Multi-timeframe intelligente

**Obiettivo:** Parent TF per scansione veloce + child TF solo nelle barre candidate.

### Logica di discesa al child TF

Una barra parent è "candidata" (richiede verifica a child TF) se:
- Possibile touch di entry pending
- Possibile touch dello SL corrente
- Possibile touch del TP corrente
- Possibile collisione SL/TP
- Presenza update trader dentro la barra parent
- Presenza di confini temporali importanti (timeout, cambio stato)

Il parent TF **non decide** l'esecuzione — esclude rapidamente le barre inerti.
Il child TF **decide** fill, TP, SL e ordine degli eventi nelle barre candidate.

### File da modificare

#### `market/intrabar_resolver.py`

Già esiste (109 righe) per collisioni SL/TP. Va esteso:
- Accettare `MarketRuntimeConfig` per sapere parent TF e detail TF
- Implementare logica di selezione barre candidate
- Restituire `IntrabarResult` con: barre discese, eventi risolti, ordine finale

#### `scripts/plan_market_data.py` e `market/planning/coverage_planner.py`

- Il piano deve includere entrambi i TF nella lista dei dati da scaricare
- `download_window` viene calcolata per `(symbol, download_tf)` e per `(symbol, detail_tf)` se diversi

---

## Fase 6 — Stubs UI per tipi dati futuri ✅ COMPLETATA (2026-04-18)

**Obiettivo:** La struttura UI consente di aggiungere nuovi tipi dati senza riscrivere il flusso.

| Tipo dato | Stato | UI |
|-----------|-------|----|
| OHLCV last | Supportato | Toggle attivo |
| OHLCV mark | Supportato | Toggle attivo |
| Funding rate | Parzialmente predisposto | Voce disabilitata, label "roadmap" |
| Open interest | Non supportato | Voce disabilitata, label "roadmap" |
| Liquidations | Non supportato | Voce disabilitata, label "roadmap" |
| Bid/ask spread | Non supportato | Voce disabilitata, label "roadmap" |
| Order book | Non supportato | Voce disabilitata, label "roadmap" |

**Fees exchange**: va in sezione separata "Cost Model", non nel gruppo Market DATA.

Nessuna implementazione backend in questa fase — solo placeholder UI con stato disabilitato.

---

### Incremento operativo Fase 6 (2026-04-18)

La Fase 6 viene incrementata con un contratto piÃ¹ esplicito: i tipi dato supportati devono diventare stato UI reale, mentre i tipi roadmap devono restare solo stub visivi senza impatto su CLI o backend.

#### Principi di design

- Il gruppo `Tipo dati` deve stare nel `Setup` del `MarketDataPanel`, vicino a source e timeframe
- I tipi supportati devono essere selezionabili e persistiti nello stato UI
- I tipi roadmap devono essere visibili ma non interagibili
- Le voci roadmap non devono alterare CLI, planner, sync, validator o readiness
- `Fees exchange` non appartiene a Market DATA: va mostrato come nota verso il futuro blocco `Cost Model`

#### Modello UI target

| Categoria | Comportamento | Impatto runtime |
|-----------|---------------|-----------------|
| `supported` | checkbox/toggle attivo | influisce su stato UI e summary |
| `roadmap` | checkbox/toggle disabilitato + badge `roadmap` | nessun impatto runtime |
| `external` | nota informativa fuori gruppo | nessun impatto runtime |

#### Tipi dato previsti

| Tipo dato | Chiave consigliata | Stato | UI |
|-----------|--------------------|-------|----|
| OHLCV last | `ohlcv_last` | Supportato | Toggle attivo, default ON |
| OHLCV mark | `ohlcv_mark` | Supportato | Toggle attivo, default configurabile |
| Funding rate | `funding_rate` | Roadmap | Voce disabilitata, badge `roadmap` |
| Open interest | `open_interest` | Roadmap | Voce disabilitata, badge `roadmap` |
| Liquidations | `liquidations` | Roadmap | Voce disabilitata, badge `roadmap` |
| Bid/ask spread | `bid_ask_spread` | Roadmap | Voce disabilitata, badge `roadmap` |
| Order book | `order_book` | Roadmap | Voce disabilitata, badge `roadmap` |

#### File da modificare

`src/signal_chain_lab/ui/state.py`
- Estendere `MarketState` con un contenitore tipizzato per i soli dataset supportati
- Struttura consigliata:

```python
@dataclass
class MarketDataTypeState:
    ohlcv_last: bool = True
    ohlcv_mark: bool = False

@dataclass
class MarketState:
    # ... campi esistenti ...
    data_types: MarketDataTypeState = field(default_factory=MarketDataTypeState)
```

Vincoli:
- nessun boolean operativo per funding/open_interest/liquidations/bid_ask_spread/order_book
- i tipi non supportati restano metadata UI, non stato di pipeline

`src/signal_chain_lab/ui/blocks/market_data_panel.py`
- Incrementare il `Setup` con un sottoblocco `Tipo dati`
- Mostrare prima i toggle supportati e poi le voci roadmap in ordine stabile
- Aggiungere badge o suffix text `roadmap`
- Spiegare il disabled con helper text o tooltip
- Separare visivamente `Cost Model / Fees exchange` come nota, senza checkbox

Comportamento richiesto:
- `OHLCV last`: sempre selezionabile
- `OHLCV mark`: selezionabile ma opzionale
- roadmap: non cliccabili, nessun binding verso pipeline
- Discovery/Result possono mostrare solo i tipi dati supportati attivi

`src/signal_chain_lab/ui/blocks/market_data_support.py`
- Aggiungere helper di presentation:
- `supported_data_type_labels(selected: MarketDataTypeState) -> list[str]`
- `roadmap_data_type_labels() -> list[str]`
- `format_data_types_summary(...) -> str`

#### Contratto esplicito della fase

Questa fase **non** deve:
- aggiungere nuovi argomenti CLI per funding, open interest, liquidations, spread o order book
- modificare `CoveragePlanner`, `BybitDownloader`, `BatchValidator`, `PreparationCache`
- cambiare il criterio `market_ready`
- introdurre branching backend per le voci roadmap

Questa fase **puÃ²**:
- persistere i soli toggle supportati nello stato UI
- esporre i tipi attivi nei summary del panel
- predisporre naming coerente per una futura fase backend-oriented

#### Deliverable minimi

- `MarketState` esteso con `data_types`
- `MarketDataPanel` con sottosezione `Tipo dati` strutturata
- helper UI centralizzati per label e summary
- zero differenze nei comandi CLI quando si interagisce solo con voci roadmap
- testo esplicito: `Fees / Cost Model -> sezione separata`

#### Criteri di completamento Fase 6

- L'utente vede due dataset supportati e cinque dataset roadmap nello stesso gruppo UI
- I dataset roadmap sono visibili ma non interagibili
- L'attivazione/disattivazione di `OHLCV last` e `OHLCV mark` aggiorna solo stato e summary UI
- Nessun path backend riceve richieste per dataset non supportati
- La roadmap UI Ã¨ estendibile aggiungendo una voce metadata/stub senza riscrivere il flusso principale

## Protocollo stdout standardizzato

Tutti gli script Market devono emettere righe strutturate parsabili dalla GUI:

```
PHASE=discover
PHASE=planner
PHASE=sync
PHASE=gap_validate
PHASE=validate
PROGRESS=37
STEP=12/31
SUMMARY=symbols:5 gaps:3 artifacts:2
```

La GUI legge queste righe via `parse_progress_line()`, aggiorna la progress bar e continua ad appendere il log testuale integrale.

Script da aggiornare:
- `scripts/plan_market_data.py` — aggiungere `PHASE=planner`, `PROGRESS=`, `SUMMARY=`
- `scripts/sync_market_data.py` — uniformare output progressivo
- `scripts/gap_validate_market_data.py` — uniformare output progressivo
- `scripts/validate_market_data.py` — uniformare output, aggiungere `SUMMARY=`

---

## Dipendenze tra fasi

```
Fase 1 (UI refactor)
    └── Fase 2 (buffer manuale)       ← dipende da MarketState in state.py
            └── Fase 3 (chart-aware)  ← dipende da ManualBuffer in planner
                    └── Fase 5 (multi-TF) ← dipende da runtime_config.py

Fase 4 (validazione) ← indipendente, può partire dopo Fase 1
Fase 6 (stubs UI)    ← dipende da market_data_panel.py (Fase 1)
```

**Non iniziare Fase 2 prima che `MarketState` e `market_data_panel.py` siano funzionanti.**

---

## Riepilogo file toccati

| File | Intervento | Fase |
|------|-----------|------|
| `ui/blocks/market_data_panel.py` | CREA | 1 |
| `ui/blocks/market_data_support.py` | CREA | 1 |
| `market/runtime_config.py` | CREA | 3 |
| `ui/state.py` | MODIFICA — introduce `MarketState` | 1 |
| `ui/blocks/block_backtest.py` | MODIFICA — rimuove logica Market | 1 |
| `ui/app.py` | MODIFICA — composizione Blocco 3 | 1 |
| `market/planning/coverage_planner.py` | MODIFICA — manual buffer + chart window | 2, 3 |
| `scripts/plan_market_data.py` | MODIFICA — nuovi argomenti + protocollo stdout | 2, 3 |
| `scripts/sync_market_data.py` | MODIFICA — protocollo stdout | 2 |
| `scripts/gap_validate_market_data.py` | MODIFICA — protocollo stdout | 2 |
| `scripts/validate_market_data.py` | MODIFICA — protocollo stdout + strict flag | 4 |
| `market/planning/validation.py` | MODIFICA — OHLC strong, continuità, severity | 4 |
| `market/intrabar_resolver.py` | MODIFICA — candidate bars, runtime config | 5 |
