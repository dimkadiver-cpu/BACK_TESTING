# Reference per l'agente implementatore — Sistema report 3 livelli

**Data:** 2026-04-15  
**Destinatario:** Agente Claude che implementa il sistema di reporting

---

## 0. Prima di toccare qualsiasi file

Leggi in ordine:
1. `docs/Nuovo_report_3_livelli/PRD_reporting_dinamico_3_livelli.md` (PRD-A)
2. `docs/Nuovo_report_3_livelli/PRD_operativo_report_trade_da_zero_v3_sidebar_unificata.md` (PRD-B)
3. `docs/Nuovo_report_3_livelli/implementazione/00_ANALISI_PRD_GAP.md` ← **fondamentale**
4. Questo documento (01_REFERENCE_AGENTE.md)
5. `docs/Nuovo_report_3_livelli/implementazione/02_PIANO_ATTUAZIONE.md`

**Non leggere** `docs/PRD_REPORT.md`, `docs/PRD_REPORT_revisionato_e_delta.md`, `docs/DELTA_policy_report_trade_detail.md` come istruzioni normative: sono documenti storici. Sono superati dai PRD in `Nuovo_report_3_livelli/`.

---

## 1. Mappa del sistema — 3 livelli

```
comparison_report.html          ← Livello 1
      ↓ (click su policy)
<policy_name>/policy_report.html  ← Livello 2
      ↓ (click su Detail)
<policy_name>/trades/<sig_id>/detail.html  ← Livello 3
```

### Regola di navigazione

| Da → A | Cosa porta |
|--------|-----------|
| comparison → policy | comparison context (Core filters) pre-compilati |
| policy → comparison | salva solo Core filters nel comparison context |
| policy → trade | nessun filtro, solo back_link al policy report |
| trade → policy | ritorna al policy report (con eventuale posizione sessionStorage) |

---

## 2. File da toccare vs non toccare

### Non toccare mai
- `src/signal_chain_lab/engine/` — motore di simulazione
- `src/signal_chain_lab/domain/` — modelli dati domain
- `src/signal_chain_lab/adapters/` — chain builder
- `src/signal_chain_lab/storage/` — storage layer
- `src/signal_chain_lab/reports/html_report.py` — vecchio report (legacy, non in uso nel nuovo flusso)

### Riusare senza modifiche
- `src/signal_chain_lab/policy_report/runner.py` — orchestrazione + aggregazione metriche (già completo)
- `src/signal_chain_lab/policy_report/trade_chart_payload.py` — payload chart (già completo, da estendere per SL history)
- `src/signal_chain_lab/policy_report/comparison_runner.py` — orchestrazione comparison (già completo)

### Modificare / riscrivere
- `src/signal_chain_lab/policy_report/html_writer.py` — **riscrivere** le funzioni di rendering HTML per tutti e 3 i livelli
- `src/signal_chain_lab/policy_report/trade_chart_echarts.py` — **aggiornare** per rispettare il nuovo layout PRD-B (sidebar unificata, no doppio blocco eventi)

---

## 3. Struttura dati disponibili

### TradeResult (da `domain/results.py`)
Campi rilevanti per i report:
```python
signal_id: str
symbol: str
side: str                    # LONG | SHORT
status: str                  # closed | expired | cancelled | open
close_reason: str            # tp | sl | manual | expired | cancelled | timeout
realized_pnl: float          # valore assoluto
trade_impact_pct: float | None    # % su capitale
gross_pct: float | None           # % lordo
net_pct: float | None             # % netto
fee_pct: float | None
funding_pct: float | None
cum_equity_pct: float | None      # equity cumulativa %
mae_pct: float | None
mfe_pct: float | None
r_multiple: float | None
warnings_count: int
created_at: str              # ISO datetime
closed_at: str | None
total_duration_seconds: float | None
fills_count: int | None
```

### EventLogEntry (da `domain/results.py`)
```python
event_type: str              # tipo evento (es. ENTRY_FILLED, TP_HIT, SL_HIT...)
timestamp: str               # ISO datetime
price: float | None
description: str             # label leggibile
data: dict | None            # payload dettagliato
source: str | None           # TRADER | ENGINE | SYSTEM
raw_text: str | None         # testo Telegram originale, se disponibile
```

### PolicySummary (dict prodotto da `_build_summary` in `runner.py`)
Campi aggregati già calcolati:
```python
"policy_name"
"total_return_pct"           # ritorno totale %
"max_drawdown_pct"
"expectancy_pct"
"win_rate"                   # float 0-1
"profit_factor"
"avg_trade_impact_pct"
"best_trade_pct"
"worst_trade_pct"
"trades_count"
"closed_count"
"expired_count"
"excluded_count"
"fee_pct_total"
"funding_pct_total"
"gross_pct_total"
"net_pct_total"
"final_cum_equity_pct"
"avg_r"
"equity_curve"               # list[float] — serie % cumulativa per trade
"drawdown_series"            # list[float]
"close_reason_distribution"  # dict[str, int]
"symbol_contribution"        # list[dict]
"generated_at"
```

---

## 4. Modello canonico eventi (PRD-B §14) — mapping da EventLogEntry

Il PRD-B richiede uno schema canonico evento. Il mapping da EventLogEntry è:

```python
{
    "id":           f"{trade.signal_id}_{idx}",        # generato
    "ts":           entry.timestamp,
    "phase":        _map_phase(entry.event_type),       # vedere tabella sotto
    "class":        _map_class(entry.event_type),       # vedere tabella sotto
    "subtype":      _normalize_subtype(entry.event_type),
    "title":        entry.description,
    "price_anchor": entry.price,
    "source":       entry.source or "ENGINE",
    "impact": {
        "position": entry.data.get("position_size_after") if entry.data else None,
        "risk":     entry.data.get("current_sl_after") if entry.data else None,
        "result":   entry.data.get("realized_pnl_pct_after") if entry.data else None,
    },
    "summary":      entry.description,
    "raw_text":     entry.raw_text,
    "details":      entry.data or {},
}
```

### Tabella mapping phase/class

| event_type | phase | class |
|-----------|-------|-------|
| SIGNAL_CREATED, ENTRY_PLANNED | SETUP | STRUCTURAL |
| ENTRY_FILLED, SCALE_IN_FILLED, MARKET_ENTRY_FILLED | ENTRY | STRUCTURAL |
| SL_SET, SL_MOVED, BE_ACTIVATED, TP_ARMED | MANAGEMENT | MANAGEMENT |
| TP_HIT, PARTIAL_EXIT, SL_HIT, FINAL_EXIT | EXIT | RESULT |
| CANCELLED, EXPIRED, TIMEOUT | EXIT | RESULT |
| IGNORED, SYSTEM_NOTE | POST_MORTEM | AUDIT |

### Subtypes normalizzati (PRD-B §15)
L'event_type esistente nel codice deve essere mappato ai subtype canonici PRD-B. Se `event_type` corrisponde già a un subtype canonico, usarlo direttamente. Altrimenti mappare:

| event_type codice | subtype canonico |
|-------------------|-----------------|
| `new_signal` | `SIGNAL_CREATED` |
| `entry_fill` | `ENTRY_FILLED` |
| `scale_in` | `SCALE_IN_FILLED` |
| `market_entry` | `MARKET_ENTRY_FILLED` |
| `sl_set` | `SL_SET` |
| `sl_moved` | `SL_MOVED` |
| `be_activated` | `BE_ACTIVATED` |
| `tp_armed` | `TP_ARMED` |
| `tp_hit` | `TP_HIT` |
| `partial_exit` | `PARTIAL_EXIT` |
| `final_exit` | `FINAL_EXIT` |
| `sl_hit` | `SL_HIT` |
| `cancelled` | `CANCELLED` |
| `expired` | `EXPIRED` |
| `timeout` | `TIMEOUT` |
| `ignored` | `IGNORED` |
| `system_note` | `SYSTEM_NOTE` |

---

## 5. Regole colori e semantica visiva (PRD-A §7.2 DELTA)

```
Verde (#15803d)  → positivo / TP / gain
Rosso (#b91c1c)  → negativo / SL / loss
Blu (#1d4ed8)    → entry / setup
Arancio (#c2410c) → update / gestione
Grigio (#64748b) → metadata / neutro / disabled
Viola (#7c3aed)  → market entry (PRD-B §17.2)
```

### Colori livelli sul chart (PRD-B §17)
```
Entry limit:   blu (#1d4ed8), tratteggiato
Entry market:  viola (#7c3aed), tratteggiato
Stop loss:     rosso (#b91c1c), tratteggiato
Take profit:   verde (#15803d), tratteggiato
Average entry: colore distinto (es. ciano #0891b2), linea continua
```

---

## 6. Filtri — modello unificato (INC-7 approvata)

**Non esiste più la distinzione Core/Local.**  
Tutti i filtri sono dello stesso tipo: agiscono sulla trade list e sono tutti salvabili nel comparison context.  
Le esclusioni manuali per-trade rimangono separate (non sono filtri).

### Filtri unificati
| Filtro | Widget | Valori |
|--------|--------|--------|
| date range | date range picker (from/to) | ISO date |
| trader | dropdown / text | trader_id o "all" |
| symbol | text input (multi-value) | es. "BTCUSDT, ETHUSDT" |
| side | dropdown | All / LONG / SHORT |
| trade status | checkbox multi | closed / expired / cancelled / open |
| close reason | checkbox multi | tp / sl / manual / expired / cancelled / timeout |
| outcome | dropdown | All / gain / loss / flat |

`outcome` è derivato da `Net %`: gain = Net% > 0, loss = Net% < 0, flat = Net% == 0.

### UI del pannello filtri nel `single_policy_report`
```
┌─ Filters ──────────────────────────────────────────────────────┐
│  Date range: [from]──[to]   Trader: [____]   Symbol: [_______] │
│  Side: [All▾]   Status: [✓closed ✓expired □cancelled □open]    │
│  Close reason: [✓tp ✓sl □manual □expired □cancelled □timeout]  │
│  Outcome: [All▾]                                               │
│                                                                 │
│  [Apply]  [Save as comparison context]  [Reset filters]        │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. Comparison context — struttura JSON

Contiene l'intero stato filtri al momento del salvataggio.

```json
{
  "version": 1,
  "date_from": "2025-01-01",
  "date_to": "2025-12-31",
  "trader": "trader_a",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "side": "LONG",
  "trade_status": ["closed", "expired"],
  "close_reason": ["tp", "sl"],
  "outcome": "gain"
}
```

Chiave sessionStorage: `"compCtx"` (costante condivisa tra tutti i file HTML della stessa sessione).

Campi omessi o `null` = filtro non attivo (nessun vincolo su quel campo).

---

## 8. Persistenza sessionStorage — struttura completa

```javascript
// Globale (per tutto il report set)
sessionStorage["compCtx"]         // comparison context JSON (filtri unificati)
sessionStorage["reportRoot"]      // pathname radice (da comparison_report.html)

// Per policy (chiave per policy_name)
// Nota: ora c'è un solo set filtri, non più "local" separati
sessionStorage["policy_<name>_filters"]    // filtri attivi nel policy report (stesso schema compCtx)
sessionStorage["policy_<name>_sort"]       // sort attivo JSON {col, dir}
sessionStorage["policy_<name>_excluded"]   // lista signal_id esclusi manualmente JSON array
```

**Flusso sessionStorage:**

1. Apertura `comparison_report.html` → legge `compCtx`, applica al ricalcolo metriche
2. Click su policy → apre `policy_report.html` passando context via URL param `?ctx=<encoded>` oppure via `sessionStorage["compCtx"]`
3. `policy_report.html` all'apertura → legge `compCtx` e pre-popola i filtri; legge `policy_<name>_filters` per ripristinare lo stato locale precedente
4. Utente modifica filtri → scrive `sessionStorage["policy_<name>_filters"]`
5. Utente clicca "Save as comparison context" → sovrascrive `sessionStorage["compCtx"]` con i filtri correnti del policy report
6. Utente torna al `comparison_report` → `focus` event rilegge `compCtx` e aggiorna la tabella

---

## 9. Struttura file output attesa

```
<output_dir>/
├── comparison_report.html
├── assets/
│   └── echarts.min.js
└── <policy_name>/
    ├── policy_report.html
    ├── policy_summary.json
    ├── policy_summary.csv
    ├── trade_results.csv
    ├── excluded_chains.csv
    ├── policy.yaml
    └── trades/
        └── <signal_id>/
            ├── detail.html
            ├── event_log.jsonl
            └── trade_result.csv
```

---

## 10. Colonne tabella trade nel `single_policy_report`

Colonne obbligatorie (PRD-A §10.2):

| Colonna | Tipo | Sort | Note |
|---------|------|------|------|
| Include | checkbox | no | checked = incluso nel calcolo |
| Signal ID | str | testo ↑↓ | |
| Symbol | str | testo ↑↓ | |
| Side | str | testo ↑↓ | LONG / SHORT |
| Trade Status | str | testo ↑↓ | closed / expired / cancelled |
| Close Reason | str | testo ↑↓ | |
| Net % | float | num ↑↓ (best→worst) | colore verde/rosso |
| Gross % | float | num ↑↓ | |
| Warn | int | num ↑↓ | |
| Cum Equity | float | num ↑↓ | |
| R | float | num ↑↓ | |
| Detail | link | no | apre detail.html |

**Comportamento sort numeriche:** 1° click = migliore → peggiore (header verde), 2° click = peggiore → migliore (header rosso), 3° click = reset default.  
**Comportamento sort testuali:** 1° click = A→Z, 2° click = Z→A, 3° click = reset.

---

## 11. Metriche cumulative `single_policy_report` — aggiornamento dinamico

Le metriche si aggiornano ogni volta che cambiano:
- filtri Core attivi
- filtri Local attivi
- set trade inclusi/esclusi manualmente

### Metriche da mostrare (PRD-A §9.4)
| Metrica | Formula |
|---------|---------|
| Trades included | count di trade con checkbox checked |
| Win rate | (trade con Net% > 0) / included |
| Gross % | somma Gross% inclusi |
| Net % | somma Net% inclusi |
| Fee % | somma Fee% inclusi |
| Funding % | somma Funding% inclusi |
| Total costs % | Fee% + Funding% |
| Final Cum Equity | ultimo valore Cum Equity dei trade inclusi ordinati per data |
| Avg R | media R dei trade inclusi |
| Best Trade % Net | max(Net%) tra inclusi |
| Worst Trade % Net | min(Net%) tra inclusi |
| Profit Factor | (somma Net% trade positivi) / abs(somma Net% trade negativi) |

**Nota:** Il ricalcolo avviene interamente lato client JavaScript, sui dati embedded nel HTML.

---

## 12. Comparison report — colonne tabella (decisione su INC-2)

Lista positiva completa colonne del comparison_report:

| Colonna | Tipo | Note |
|---------|------|------|
| Policy Name | str | link al policy_report.html |
| Net % | float | totale netto |
| Gross % | float | totale lordo |
| Max DD % | float | drawdown massimo |
| Win Rate % | float | |
| Profit Factor | float | |
| Expectancy % | float | |
| Avg R | float | |
| Best Trade % | float | |
| Worst Trade % | float | |
| Trades | int | numero trade nel context attivo |
| Open Report | link | apre policy_report.html con context |

**Evidenziazione migliori:**
- Net %, Gross %, Win Rate %, Profit Factor, Expectancy %, Avg R, Best Trade %: evidenziare il massimo
- Max DD %: evidenziare il minimo (il meno negativo)
- Badge `Best` sotto il nome della policy con il miglior Net %

---

## 13. Lista eventi unificata sidebar — struttura DOM

Il componente sidebar del `single_trade_report` deve seguire questa struttura:

```html
<aside class="sidebar">
  <h3>Trade Events</h3>
  <ul class="event-list" id="eventList">
    <li class="event-item" data-event-id="<id>" data-phase="SETUP">
      <!-- Vista collassata (sempre visibile) -->
      <div class="event-collapsed" onclick="toggleEvent(this)">
        <span class="event-ts">2025-01-15 10:32</span>
        <span class="event-label">ENTRY_FILLED</span>
        <span class="event-desc">Entry limit filled @ 42150</span>
        <div class="event-chips">
          <span class="chip">size: 0.1</span>
          <span class="chip">avg: 42150</span>
        </div>
      </div>
      <!-- Vista espansa (toggle) -->
      <div class="event-expanded" style="display:none">
        <dl>
          <dt>Source</dt><dd>TRADER</dd>
          <dt>Price</dt><dd>42150.00</dd>
          <dt>Position after</dt><dd>0.1 BTC</dd>
        </dl>
        <button onclick="openRawText('<raw_text_escaped>')">Raw Message Text</button>
      </div>
    </li>
    ...
  </ul>
</aside>
```

### Comportamento interazione bidirezionale

```javascript
// Chart event click → highlight sidebar item
function onChartEventClick(eventId) {
    closeAllItems();
    const item = document.querySelector(`[data-event-id="${eventId}"]`);
    item.classList.add('highlighted');
    item.querySelector('.event-expanded').style.display = 'block';
    item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Sidebar item click → highlight chart event
function onSidebarItemClick(eventId) {
    highlightChartEvent(eventId);  // funzione del chart engine
}
```

---

## 14. Audit drawer — struttura

```html
<details class="audit-drawer" id="auditDrawer">
  <summary>Audit / Debug log</summary>
  <div class="audit-content">
    <!-- Per ogni evento, inclusi IGNORED e SYSTEM_NOTE -->
    <div class="audit-entry">
      <span class="audit-ts">...</span>
      <span class="audit-type">...</span>
      <pre class="audit-payload"><!-- JSON completo --></pre>
    </div>
  </div>
</details>
```

L'elemento `<details>` è collassato per default (`open` attribute assente).

---

## 15. Vincoli tecnici fondamentali

1. **Offline-first**: tutti i file HTML devono funzionare senza rete. ECharts già incluso in `assets/echarts.min.js`.
2. **No CDN**: nessun link a risorse esterne nei file HTML finali.
3. **sessionStorage** per stato sessione, non localStorage.
4. **Dati trade embedded** nel comparison_report.html come `<script>const POLICY_DATA = {...};</script>`.
5. **Vanilla JS**: nessun framework (React, Vue, etc.). Solo HTML + CSS + JS puro.
6. **No server**: nessun fetch() → tutti i dati devono essere embedded al momento della generazione Python.
7. **Python 3.12+**, Pydantic v2, type hints ovunque.
