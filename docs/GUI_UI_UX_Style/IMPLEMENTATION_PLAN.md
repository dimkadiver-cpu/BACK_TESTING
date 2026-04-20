# Signal Chain Lab — Piano di implementazione GUI

**Data:** 2026-04-19  
**Riferimento visivo:** `ui_mockup.html`  
**Riferimento funzionale:** `UX_REFERENCE_definitivo.md`  
**Stile:** `UI_STYLE_GUIDE.md`  
**Codebase target:** `src/signal_chain_lab/ui/`

---

## Analisi delta — codice attuale vs target

### Struttura

| Aspetto | Attuale | Target |
|---|---|---|
| Tab 3 nome | "Backtest" | "Market Data & Backtest" |
| Tab 3 struttura | Market data panel collassabile in fondo + Backtest | Shared context collassabile + card con sub-tab Market Data / Backtesting |
| Shared context | Non esiste | Card collassabile con DB, filtri, cartella market |
| Persistenza stato | Nessuna (solo RAM) | JSON file `%APPDATA%/SignalChainLab/ui_state.json` |

### Market Data

| Aspetto | Attuale | Target |
|---|---|---|
| Validate mode | Full / Light / Off | GAPs / OFF |
| Data types | Checkbox OHLCV last / OHLCV mark / Funding rate | Multi-select Perp / Spot / Funding rate |
| Price basis | Dentro data types | Campo separato `last` / `mark` |
| Buffer unità | Ore (h) | Giorni |
| Buffer preset | Dropdown intraday/swing/position/custom | Non presente nel target |
| Nuova directory | Mode dropdown (existing_dir / new_dir) | Toggle ON/OFF + input path |
| Simulation TF | In Market Data panel | Spostato nel sub-tab Backtesting |
| Detail TF | In Market Data panel | Spostato nel sub-tab Backtesting |
| Copertura | Non esposta | Sezione Coverage: Simboli, Intervalli req., Gap, % |
| Azioni | Analizza / Prepara / Prepara+Valida / Valida / Arresta | Analizza / Prepara / Valida / Arresta |

### Backtesting

| Aspetto | Attuale | Target |
|---|---|---|
| Timeout | Secondi | Minuti (label `Timeout (m)`) |
| Simulation TF | In Market Data | Qui nel sub-tab |
| Detail TF | In Market Data | Qui nel sub-tab |
| Market source / Price basis | Controlli editabili | Solo display, auto-rilevati |
| Gating | `market_ready` flag | Coverage-only (copertura richiesta soddisfatta) |
| Risultati | Card summary | Tabella Policy/Trades/Excluded/PnL%/Win rate/Expectancy/Report |
| Notice auto-detect | Non presente | Presente in cima al sub-tab |

### Visual

| Aspetto | Attuale | Target |
|---|---|---|
| Tema | Parzialmente applicato (Quasar defaults + alcuni overrides) | Pieno GitHub dark (CSS tokens) |
| Font | System font + alcune classi mono | IBM Plex Mono + IBM Plex Sans dappertutto |
| Badge di stato | ui.badge() generico | Badge semantici: NOT_STARTED/READY/RUNNING/DONE/WARNING/STALE/ERROR |
| Tab nav | ui.tabs() Quasar | Nav fissa con border-bottom indicator stile mockup |
| Log panel | LogPanel component (esiste) | Allineamento stile (log-bg #010409, testo verde, header $ prompt) |

---

## Architettura implementazione

### File da modificare

```
src/signal_chain_lab/ui/
├── app.py                    ← theming globale + layout tab rinnovato
├── state.py                  ← UiState espanso + persistenza JSON
├── persistence.py            ← NUOVO: load/save ui_state.json
├── blocks/
│   ├── block_download.py     ← allineamento visivo
│   ├── block_parse.py        ← allineamento visivo
│   ├── block_backtest.py     ← sub-tab Backtesting + azioni rinnovate
│   ├── market_data_panel.py  ← sub-tab Market Data + nuovi controlli
│   ├── shared_context.py     ← NUOVO: contesto condiviso collassabile
│   ├── backtest_support.py   ← aggiornare gating coverage-only
│   └── market_data_support.py ← aggiornare data types model
└── components/
    ├── log_panel.py          ← allineamento stile
    ├── status_badge.py       ← NUOVO: badge semantici riutilizzabili
    └── quality_report.py     ← allineamento visivo
```

### Ordine di esecuzione fasi

```
Fase 1  Fondamenta (theme + persistence)
Fase 2  Componenti condivisi (badge, log, chip)
Fase 3  Tab 1 — Download (allineamento visivo)
Fase 4  Tab 2 — Parse (allineamento visivo)
Fase 5  Tab 3 — Shared context (nuovo blocco)
Fase 6  Sub-tab Market Data (nuovi controlli + azioni)
Fase 7  Sub-tab Backtesting (spostamenti + gating)
Fase 8  Persistenza UI state (wiring tutti i controlli)
Fase 9  QA e test regressione
```

**Non saltare fasi. Fase 2 deve essere completata prima di Fase 3.**

---

## Fase 1 — Fondamenta

### 1.1 Theming globale in `app.py`

Sostituire l'attuale inizializzazione `ui.colors()` e `ui.add_head_html()` con:

```python
ui.colors(
    primary='#58a6ff',
    secondary='#30363d',
    accent='#3fb950',
    positive='#3fb950',
    negative='#f85149',
    warning='#d29922',
    info='#58a6ff',
    dark='#161b22',
)

ui.add_head_html("""
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#0d1117; --surface:#161b22; --surface-2:#1c2128; --surface-h:#1f2937;
    --border:#30363d; --border-s:#21262d;
    --accent:#58a6ff; --accent-d:rgba(88,166,255,.12);
    --ok:#3fb950; --ok-d:rgba(63,185,80,.10);
    --wa:#d29922; --wa-d:rgba(210,153,34,.10);
    --er:#f85149; --er-d:rgba(248,81,73,.10);
    --muted:#8b949e; --text:#e6edf3; --text2:#c9d1d9;
    --log-bg:#010409; --log-g:#39d353;
    --mono:'IBM Plex Mono',monospace;
    --sans:'IBM Plex Sans',system-ui,sans-serif;
    --nav-h:42px; --panel-w:980px; --r:6px; --rs:4px;
  }
  body { font-family: var(--sans) !important; font-size:14px; background:var(--bg) !important; }
  ::-webkit-scrollbar { width:5px; height:5px; }
  ::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
  *:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
</style>
""")
```

### 1.2 Nuovo file `persistence.py`

Gestisce caricamento e salvataggio di `ui_state.json`.

**Percorso:**
- Windows: `%APPDATA%/SignalChainLab/ui_state.json`
- Linux/macOS: `~/.config/signal_chain_lab/ui_state.json`

**Responsabilità:**
- `get_state_path() -> Path`
- `load_ui_state() -> dict` — restituisce dict vuoto se file non esiste o malformato
- `save_ui_state(data: dict) -> None` — salvataggio atomico (write + rename)
- `debounced_save(data: dict, delay_ms=500)` — evita write storm durante input rapido

**Campi persistiti (lista minima):**
```
db_path, market_data_dir, source_provider, price_basis,
download_tf, simulation_tf, detail_tf, data_types,
buffer_mode, pre_buffer_days, post_buffer_days,
validate_mode, new_dir_toggle, new_dir_path,
backtest_policies, report_dir, trader_filter,
date_from, date_to, max_trades
```

**Regole:**
- Path non più esistenti: mantenere il valore salvato, mostrarlo come "non valido" (colore `--er`)
- Non salvare credenziali Telegram (API_ID, HASH, telefono)
- Salvataggio a ogni modifica rilevante dei controlli principali

### 1.3 Espandere `state.py`

Aggiungere a `UiState`:
- `validate_mode: str = "Off"` (sarà rimappato in "GAPs"/"OFF")
- `new_dir_enabled: bool = False`
- `new_dir_path: str = ""`
- `pre_buffer_days: int = 2` (era in ore — unità cambia)
- `post_buffer_days: int = 1`
- `data_types_perp: bool = True`
- `data_types_spot: bool = False`
- `data_types_funding: bool = True`

Rimuovere (o deprecare con alias):
- `buffer_preset` — non nel target UX
- `market_data_mode` (existing_dir/new_dir) → sostituito da `new_dir_enabled`

---

## Fase 2 — Componenti condivisi

### 2.1 `status_badge.py` — badge semantici

Creare funzione `render_status_badge(status: str, label: str | None = None)`:

Stati supportati: `NOT_STARTED | READY | RUNNING | DONE | WARNING | STALE | ERROR`

Classe CSS per ogni stato (iniettare via `ui.add_head_html` o inline):
```
NOT_STARTED → muted bg + muted text
READY       → ok-d bg + ok text + ok border
RUNNING     → accent-d bg + accent text + pulse animation
DONE        → ok-d bg (più scuro) + ok text
WARNING     → wa-d bg + wa text + wa border
STALE       → transparent bg + wa text + wa dashed border
ERROR       → er-d bg + er text + er border
```

### 2.2 `log_panel.py` — allineamento stile

Verificare che il `LogPanel` usi:
- Background `var(--log-bg)` = `#010409`
- Testo `var(--log-g)` = `#39d353`
- Header con `$` prompt (colore `#238636`) e titolo monospace
- Chevron `▸`/`▾` per toggle
- Colori per `warn` → `#d29922`, `err` → `#f85149`, `dim` → `#238636`
- Altezza fissa 176–200px con overflow-y auto

### 2.3 CSS globale aggiuntivo per form elements

Aggiungere al `ui.add_head_html`:
```css
.inp-mono input { font-family: var(--mono) !important; font-size: 12px !important; }
.sec-lbl { font-size:9px; font-weight:600; text-transform:uppercase;
           letter-spacing:.1em; color:var(--muted); }
.path-chip { font-family:var(--mono); font-size:11px;
             background:var(--surface-2); border:1px solid var(--border-s);
             border-radius:var(--rs); padding:4px 9px; color:var(--muted);
             display:inline-flex; align-items:center; gap:5px; }
```

---

## Fase 3 — Tab 1: Download (allineamento visivo)

Nessuna modifica funzionale. Solo allineamento al mockup.

**Modifiche a `block_download.py`:**
- Titolo card: `"01 · Download dati Telegram"` con numero in monospace muted
- Sessione: stato attiva/non attiva come chip verde/grigio con `●`
- Bottone credenziali: stile ghost `"🔑 Modifica credenziali"`
- Pannello credenziali: dentro `.adv` collassabile
- Chip sorgente (Chat ID + Topic ID): monospace troncato
- Date range: nascosto quando toggle "Scarica tutto lo storico" è ON
- Risultato download: `sum-grid` 4 card (Messaggi, Con media, Image blob, DB size)
- Path DB: `path-chip` con icona `🗄`
- Bottoni azione: `▶ Esegui Download` (primary), `■ Arresta` (secondary+danger), `✓ Usa come DB attivo` (secondary), `✕ Elimina DB` (danger)
- Log: stile unificato con `$` prompt

---

## Fase 4 — Tab 2: Parse (allineamento visivo)

Nessuna modifica funzionale rilevante. Solo allineamento al mockup.

**Modifiche a `block_parse.py`:**
- Titolo card: `"02 · Parse — Signal chain reconstruction"`
- DB sorgente: path-chip con conteggio messaggi sotto l'input
- Toggle "Esporta CSV": allineato a destra nella stessa riga di Trader profile
- Status cards: `st-cards` griglia 3 colonne (Parse / Chain Builder / Backtest Readiness)
  - Ogni card: titolo UPPERCASE 9px + pill stato + detail monospace 10px
- Top warnings: tabella compatta (Tipo / Count / Esempio) con `wc` badge count
- Bottoni: `▶ Esegui Parse` / `■ Arresta` / `📊 Apri report qualità` / `📥 Esporta CSV`

---

## Fase 5 — Tab 3: Shared context (nuovo blocco)

Creare `shared_context.py` con funzione `render_shared_context(state: UiState)`.

### Struttura HTML/NiceGUI

```
shared-coll (collassabile, aperto di default)
  ├── header collassabile
  │     ├── icona ▶/▾
  │     ├── "Contesto condiviso"
  │     ├── subtitle "DB · filtri · cartella Market Data"
  │     └── summary compatta (visibile quando chiuso):
  │           "🗄 nome_db.sqlite3 · Tutti · 2024-01-01→2024-12-31 · 📂 data/market"
  └── body
        ├── [sezione] Database segnali
        │     └── input path + Sfoglia
        ├── [riga] Trader filter | Dal | Al | Max trades
        └── [sezione] Cartella Market Data
              ├── input path + Sfoglia
              └── path-chip contenuto rilevato + notice "rilevato: ..."
```

### Comportamento summary

Quando il contenitore è chiuso, mostrare riga compatta leggibile:
- `🗄 {nome_file_db}` 
- `·`
- `{trader_filter} · {date_from}→{date_to}`
- `·`
- `📂 {market_dir_short}`

### Wire a `app.py`

In `app.py`, nel rendering del Tab 3:
1. Rendere `shared_context` prima della card container
2. Passare callback per aggiornare la summary quando i valori cambiano

---

## Fase 6 — Sub-tab Market Data

### 6.1 Restructure tab 3 in `app.py`

```python
with ui.tab_panel("mktbt"):
    render_shared_context(APP_STATE)
    with ui.card().classes("bg-[#161b22] border border-[#30363d] rounded-[6px] p-0"):
        with ui.tabs().classes("sub-nav"):
            ui.tab("market", "Market Data")
            ui.tab("backtest", "Backtesting")
        with ui.tab_panels(tabs):
            with ui.tab_panel("market"):
                render_market_data_subtab(APP_STATE)
            with ui.tab_panel("backtest"):
                render_backtest_subtab(APP_STATE)
```

### 6.2 Modifiche a `market_data_panel.py`

**Controlli da modificare:**

| Controllo | Da | A |
|---|---|---|
| Validate mode | select Full/Light/Off | select GAPs/OFF |
| Data types | 3 checkbox OHLCV | multi-select custom: Perp/Spot(roadmap)/Funding rate |
| Price basis | dentro data types | campo separato (select last/mark) |
| Buffer unità | ore | giorni (label "Pre buffer (d)", "Post buffer (d)") |
| Nuova directory | dropdown existing/new | toggle ON/OFF + input condizionale |
| Buffer preset | presente | rimuovere dalla UI |

**Controlli da spostare (a Backtesting):**
- Simulation TF → `block_backtest.py`
- Detail TF → `block_backtest.py`

**Sezione Coverage (nuova):**
```
cov-grid (4 colonne):
  Simboli | Intervalli req. | Gap | Copertura %
```
Valori aggiornati dopo "Analizza". Default: trattini `—`.

**Multi-select Data types:**
- Perp → abilitato
- Spot → ROADMAP (disabilitato, label roadmap badge)
- Funding rate → abilitato
- Open interest → ROADMAP
- Liquidations → ROADMAP

**Azioni:**
```
▶ Analizza (primary) | ⬇ Prepara (secondary) | ✓ Valida (secondary) | ■ Arresta (secondary+danger)
```
Rimuovere: bottone "Prepara + Valida", bottoni funding separati (se presenti).

**Semantica azioni:**
- `Analizza` → solo `plan_market_data.py`, aggiorna Coverage
- `Prepara` → plan + sync + gap_validate se mode=GAPs
- `Valida` → `validate_market_data.py` solo su dati non ancora validati
- `Arresta` → termina processo in corso

### 6.3 Validate mode — rimappatura

Rimappare internamente:
```python
"GAPs" → gap_validate=True, validate_full=False
"OFF"  → gap_validate=False, validate_full=False
```

Il bottone "Valida" lancia sempre `validate_full` indipendentemente da validate_mode.

---

## Fase 7 — Sub-tab Backtesting

### 7.1 Modifiche a `block_backtest.py`

**Notice info in cima:**
```
ℹ  Price basis e Market source sono rilevati automaticamente dalla cartella Market Data.
```

**Riga 1:**
- Policy multi-select (invariato)
- `Timeout (m)` — cambiare label e unità (moltiplicare/dividere per 60 in conversione)
- Report output dir + Sfoglia

**Riga 2 (nuova):**
- `Simulation TF` — spostato da Market Data
- `Detail TF / childs` — spostato da Market Data
- `Price basis` → select display-only con label `"· auto da market dir"` — non editabile
- `Market source` → select display-only con label `"· auto da market dir"` — non editabile

**Policy Studio (invariato, solo stile):**
- Dentro collassabile `.adv`
- Editor YAML + bottoni Salva / Salva come nuova / Nuova policy / Ricarica lista

**Azioni:**
```
▶ Esegui Backtest (primary) | ■ Arresta (secondary+danger) | 📄 Apri report HTML (secondary) | 📂 Artifact dir (secondary)
```

**Risultati — tabella:**
```html
<table class="res-tbl">
  <thead>
    <tr><th>Policy</th><th>Trades</th><th>Excluded</th>
        <th>PnL %</th><th>Win rate</th><th>Expectancy</th><th>Report</th></tr>
  </thead>
  <tbody>
    <!-- una riga per policy eseguita -->
  </tbody>
</table>
```
- Quando nessun run: placeholder `"— nessun run eseguito —"` in monospace muted
- Rimuovere card summary attuali

### 7.2 Gating coverage-only

In `backtest_support.py`, modificare `_market_backtest_gate()`:

**Attuale:** blocca se `market_ready == False`

**Target:** 
1. Quando l'utente clicca "Esegui Backtest":
   - Eseguire check copertura (leggere ultimo risultato Coverage dal MarketState)
   - Se copertura ≥ threshold (configurabile, default 0%): consentire il run
   - Se gap critici mancanti: mostrare warning nel log ma NON bloccare hard (a meno di copertura 0%)
   - Mostrare nel log: `"[check] Copertura dataset: 85% · 12 gap · run consentito"`
2. `market_ready` può restare nel modello interno ma non deve essere l'unico gate bloccante nella UX

---

## Fase 8 — Persistenza UI state

### 8.1 Wire in `app.py`

All'avvio (`main_page()`):
```python
saved = load_ui_state()
APP_STATE.apply_saved(saved)  # metodo da aggiungere a UiState
```

Alla chiusura (`app.on_shutdown`):
```python
app.on_shutdown(lambda: save_ui_state(APP_STATE.to_dict()))
```

### 8.2 Salvataggio on-change

Per ogni controllo principale, aggiungere save dopo l'update handler:
```python
def on_change(e):
    APP_STATE.some_field = e.value
    debounced_save(APP_STATE.to_dict())
```

### 8.3 Metodi su `UiState`

- `to_dict() -> dict` — serializza tutti i campi persistibili
- `apply_saved(data: dict) -> None` — applica valori salvati con fallback ai default
- `validate_paths() -> list[str]` — ritorna lista di path che non esistono più

### 8.4 Feedback visivo path non validi

Quando un path salvato non esiste più:
- Mostrare il valore nel campo con bordo colore `--er`
- Tooltip o label sotto: `"percorso non trovato"`
- Non cancellare il valore — lasciare che l'utente decida

---

## Fase 9 — QA e test regressione

### 9.1 Checklist funzionale

- [ ] Download: esecuzione completa da GUI → DB creato
- [ ] Parse: esecuzione completa → quality report visualizzato
- [ ] Market Data → Analizza → Coverage aggiornata
- [x] Market Data → Prepara → sync eseguito
- [x] Backtest: run singola policy - risultati tabella visualizzati
- [x] Backtest: run multi-policy - risultati tabella con piu righe
- [x] Shared context collassabile: summary compatta corretta
- [x] Persistenza: chiudere e riaprire → tutti i valori ripristinati
- [x] Persistenza: path non esistente → marcato come non valido
- [x] Validate mode GAPs → gap_validate eseguito, validate_full non eseguito
- [x] Timeout in minuti: valore 5 - 300s internamente
- [x] Gating coverage-only: market non validato - backtest consentito con warning

Verifiche automatiche eseguite in Fase 9:
- `pytest tests/unit/test_market_data_panel_acceptance.py tests/unit/test_backtest_support.py tests/unit/test_ui_state_persistence.py tests/unit/test_block_backtest_acceptance.py -q`
- Esito: `12 passed`

### 9.2 Checklist visiva (confronto mockup)

- [x] Font IBM Plex Mono per valori tecnici, path, ticker
- [x] Colori CSS tokens corretti (no hardcoded hex fuori dalle variabili)
- [ ] Nav fissa con border-bottom indicator
- [x] Card: surface bg + border + radius 6px
- [x] Log panel: bg #010409, testo verde, header $ prompt
- [x] Badge stati: pulse animation per RUNNING
- [ ] Bottoni: primario filled accent, secondario outline, danger outline rosso
- [ ] Multi-select: dropdown custom con checkbox
- [x] Coverage grid 4 colonne
- [x] Risultati backtest in tabella (no card summary)
- [x] Shared context: summary riga compatta quando chiuso
- [x] Sezioni collassabili: chevron ▸/▾ senza animazione

---

## Note implementative

### NiceGUI vs HTML mockup

Il mockup è HTML puro. La traduzione in NiceGUI usa:

| HTML/CSS | NiceGUI |
|---|---|
| `.card` | `ui.card().classes(...)` |
| `.inp` / `select.inp` | `ui.input()` / `ui.select()` con classi CSS |
| `.tog` (toggle) | `ui.switch()` |
| `.ms-wrap` (multi-select) | `ui.select(multiple=True)` o componente custom |
| `.log-panel` | `LogPanel` esistente — allineare stile |
| `.adv` (collapsible) | `ui.expansion()` |
| `.badge` stato | funzione `render_status_badge()` da creare |
| `.path-chip` | `ui.label().classes('path-chip')` |
| `.res-tbl` | `ui.table()` con columns definite |
| `.cov-grid` | `ui.grid(columns=4)` + card custom |
| Sub-tab | `ui.tabs()` + `ui.tab_panels()` innestati |

### Trappole da evitare

1. **ui.select(multiple=True)** in NiceGUI/Quasar ha comportamento diverso dal multi-select custom del mockup. Valutare se usare `ui.select` con chips o componente HTML custom iniettato.
2. **Display-only per Price basis / Market source nel Backtesting**: usare `ui.input(readonly=True)` o `ui.label()` stilizzata — non `ui.select()` editabile.
3. **Timeout**: la conversione minuti → secondi deve avvenire al momento dell'esecuzione, non nello stato. `state.timeout_seconds = minutes * 60` al click di "Esegui Backtest".
4. **Debounce salvataggio**: evitare write storm su ogni keystroke — usare timer 500ms come in `persistence.py`.
5. **Path validation**: fare check `Path(v).exists()` solo al caricamento stato e al tentativo di esecuzione, non a ogni render.

---

## Priorità

### Must-have (P0)

- [x] Theming globale (fase 1)
- [x] Tab 3 restructure: shared context + sub-tab (fase 5 — shared context completo; sub-tab Fase 6)
- [x] Market Data: validate mode GAPs/OFF
- [x] Market Data: data types nuovo modello
- [x] Market Data: Coverage section
- [x] Market Data: azioni rinnovate (rimozione Prepara+Valida)
- [x] Backtesting: Simulation TF / Detail TF spostati
- [x] Backtesting: timeout in minuti
- [x] Backtesting: risultati in tabella
- [x] Persistenza stato UI (JSON)

### Should-have (P1)

- [x] Gating coverage-only
- [x] Backtesting: Price basis / Market source display-only
- [x] Buffer in giorni
- [x] Nuova directory come toggle
- [x] Badge semantici unificati

### Nice-to-have (P2)

- [x] Animation pulse per badge RUNNING
- [x] Summary riga compatta nel shared context chiuso
- [x] Scrollbar CSS personalizzata
- [x] Focus ring CSS consistente

---

*Documento generato: 2026-04-19*

