# Piano di Attuazione — Sistema report 3 livelli

**Data:** 2026-04-15  
**Riferimento PRD:** PRD-A (reporting dinamico 3 livelli) + PRD-B (single trade da zero)  
**Decisioni applicate:** vedi 00_ANALISI_PRD_GAP.md

---

## Principio generale

Il sistema report è già parzialmente implementato in `src/signal_chain_lab/policy_report/`.  
Il lavoro consiste in **riscrivere il layer HTML** (html_writer.py) e **aggiungere la logica JS** di stato sessione, confronto contestualizzato e interazione, senza toccare il backend di simulazione.

L'implementazione va eseguita in 5 fasi sequenziali.  
**Non iniziare una fase se la precedente non è verificata.**

---

## Fase 1 — Normalizzatore eventi canonico

**Obiettivo:** Produrre un modello evento unico usato da chart, rail, sidebar e audit.  
**File:** `src/signal_chain_lab/policy_report/event_normalizer.py` (nuovo)

### Task

1. Creare `event_normalizer.py` con funzione:
   ```python
   def normalize_events(
       trade: TradeResult,
       event_log: list[EventLogEntry],
   ) -> list[CanonicalEvent]:
   ```
2. Definire il dataclass `CanonicalEvent` che corrisponde allo schema PRD-B §14.
3. Implementare la tabella di mapping `event_type → subtype, phase, class` definita in 01_REFERENCE_AGENTE.md §4.
4. Aggiungere test unitari in `src/signal_chain_lab/policy_report/tests/test_event_normalizer.py`.

### Output atteso
- `CanonicalEvent` lista completa per ogni trade
- Tutti i subtype PRD-B §15 supportati
- Nessun evento senza subtype canonico (fallback: `SYSTEM_NOTE`)

### Dipendenze
- `domain/results.py` (EventLogEntry) — solo lettura

---

## Fase 2 — Segmenti livelli temporali

**Obiettivo:** Costruire la rappresentazione dei livelli (SL, TP, entry) come segmenti start/end.  
**File:** `src/signal_chain_lab/policy_report/trade_chart_payload.py` (estendere)

### Task

1. Verificare la funzione esistente che costruisce i segmenti livelli. Aprire il file e leggere la logica.
2. Verificare che l'history degli SL sia correttamente gestita: ogni `SL_MOVED` deve chiudere il segmento precedente e aprire uno nuovo.
3. Verificare che i TP multipli siano segmenti distinti con end al momento del hit o del termine del trade.
4. Verificare che `average_entry` appaia solo se `fills_count >= 2`.
5. Aggiornare o estendere la funzione `build_trade_chart_payload` per esporre una lista di `LevelSegment` con campi:
   ```python
   {
     "kind": "SL" | "TP" | "ENTRY_LIMIT" | "ENTRY_MARKET" | "AVG_ENTRY",
     "label": str,
     "price": float,
     "ts_start": str,   # ISO datetime
     "ts_end": str,     # ISO datetime
     "color": str,      # hex
     "style": "dashed" | "solid"
   }
   ```

### Output atteso
- Payload con livelli come segmenti (non linee statiche)
- SL history: ogni moved SL = nuovo segmento
- TP multipli: uno per ciascun livello, distinti

### Dipendenze
- `CanonicalEvent` da Fase 1

---

## Fase 3 — Single trade report HTML (nuovo layout PRD-B)

**Obiettivo:** Riscrivere `write_single_trade_html_report` in `html_writer.py` con il layout PRD-B.  
**File:** `src/signal_chain_lab/policy_report/html_writer.py` (riscrivere la funzione)

### Layout obbligatorio (PRD-B §7)
```
Single Trade Report
├─ Hero compact
├─ Main analysis block
│  ├─ Price chart (ECharts)
│  ├─ Timeframe row + Toggle (Volume, Event Rail) + Legend
│  ├─ Event rail (opzionale, default ON)
│  └─ Side panel
│      └─ Unified operational events list
├─ Navigation bar (Prev | Back to Policy | Next)
└─ Audit drawer (collapsed)
```

### Task

**3a. Hero compact**
- Campi: symbol / side / status, return % net, return % gross, costs total %, fees total %, funding net %, R multiple, MAE %, MFE %, duration, warnings (solo se presenti)
- NO: first fill, final exit, avg entry nell'hero
- Layout: griglia compatta 2-3 colonne, badge colorati per net %

**3b. Toolbar row**
- Selector timeframe (dal più basso al più alto disponibile)
- Toggle `Volume` (default: off o on secondo disponibilità dati)
- Toggle `Event rail` (default: on)
- Tutto sulla stessa riga

**3c. Legend**
- Doppia funzione: spiegazione visiva + toggle visibilità categorie sul chart
- Elementi: Entry limit, Entry market, Stop loss, Take profit, Avg Entry, marker TP hit, marker SL hit, marker fill, marker exit
- Colori coerenti con PRD-B §17 e 01_REFERENCE_AGENTE.md §5

**3d. Price chart (ECharts)**
- Candele OHLC
- Livelli come segmenti temporali (da Fase 2)
- Marker eventi sul chart per: ENTRY_FILLED, TP_HIT, SL_HIT, PARTIAL_EXIT, FINAL_EXIT, SCALE_IN_FILLED, MARKET_ENTRY_FILLED
- Tooltip con tipo evento + timestamp + prezzo + summary
- Zoom/pan sincronizzato con event rail e volume
- Usare `trade_chart_echarts.py` come base, aggiornare per nuovi requisiti

**3e. Event rail**
- Separato dal chart prezzo, allineato temporalmente
- Visibile per: SL_MOVED, BE_ACTIVATED, CANCELLED, EXPIRED, TIMEOUT, SYSTEM_NOTE
- Lane separate per eventi nello stesso timestamp
- Sincronizzato con zoom/pan del chart

**3f. Sidebar — lista eventi unificata**
- Un solo componente, sostituisce vecchi `Selected event summary` + `Operational timeline`
- Tutti gli eventi ordinati temporalmente
- Ogni item: collassato di default, apribile al click
- Vista collassata: timestamp + label + descrizione breve + 1-3 chip
- Vista espansa: dettaglio completo + raw message text button (solo per TRADER source)
- Interazione bidirezionale con chart e rail (click evento → evidenzia item lista, click item → evidenzia evento chart)
- Un solo item aperto alla volta

**3g. Navigation bar**
- Tra il blocco principale e l'audit drawer
- Contenuto: `← Prev Trade` | `Back to Policy Report` | `Next Trade →`
- Disabilitato (greyed) se non esiste prev/next

**3h. Audit drawer**
- `<details>` chiuso di default
- Contiene: tutti gli eventi con payload completo (inclusi IGNORED, SYSTEM_NOTE)
- Formato: lista con timestamp + tipo + `<pre>` JSON payload

### Dipendenze
- Fase 1 (normalizzatore eventi)
- Fase 2 (segmenti livelli)

---

## Fase 4 — Single policy report HTML (nuovo layout PRD-A)

**Obiettivo:** Riscrivere `write_policy_html_report` in `html_writer.py` con il layout PRD-A.  
**File:** `src/signal_chain_lab/policy_report/html_writer.py`

### Layout obbligatorio (PRD-A §9, §10 — aggiornato con INC-7)
```
Policy Report
├─ Titolo
├─ Dataset metadata (collapsible)
├─ Metadata — policy.yaml values (collapsible)
├─ Filtri unificati (sempre visibile, sopra le metriche)
│   └─ [Apply]  [Save as comparison context]  [Reset filters]
├─ Contatori base
├─ Metriche cumulative base (aggiornabili dinamicamente)
├─ Trade list (tabella con checkbox Include)
└─ Segnali esclusi (collapsible, separato dalla trade list)
```

### Task

**4a. Metadati**
Dataset metadata (collapsible):
- Dataset Name, Source DB, Period, Market Provider, Timeframe, Price Basis, Selected Chains
- Correzione INC-4 applicata: no duplicati

policy.yaml values (collapsible):
- tabella chiave/valore dei parametri policy

**4b. Filtri unificati** (INC-7 — nessuna distinzione Core/Local)

Un solo pannello filtri con tutti i widget:
- Date range (from/to date input)
- Trader (text o dropdown)
- Symbol (text multi-value)
- Side (dropdown: All / LONG / SHORT)
- Trade Status (checkbox multi: closed, expired, cancelled, open)
- Close Reason (checkbox multi: tp, sl, manual, expired, cancelled, timeout)
- Outcome (dropdown: All / gain / loss / flat)

Tre pulsanti azioni:
- `Apply` — applica i filtri alla trade list e aggiorna le metriche
- `Save as comparison context` — serializza l'intero stato filtri in `sessionStorage["compCtx"]`
- `Reset filters` — azzera tutti i filtri e ripristina tutte le checkbox Include

Nessuna separazione visiva "Core vs Local" nel pannello — è un unico blocco.

**4c. Contatori base**
- Simulated chains
- Excluded signals
- Closed
- Expired

**4d. Metriche cumulative** (si aggiornano con filtri e inclusioni/esclusioni)
Aggiornare JS ogni volta che cambia: filtro applicato, checkbox Include cambiata.
Metriche: vedere 01_REFERENCE_AGENTE.md §11.

**4e. Trade list** (tabella con checkbox)
Colonne: vedere 01_REFERENCE_AGENTE.md §10.
- Checkbox `Include` con effetto immediato sulle metriche
- Trade esclusi: opacità 0.4, in fondo (default order), altrimenti seguono sort
- Sort dinamico colonne: comportamento PRD-A §10.6

**4f. Segnali esclusi** (collapsible, separato)
- Lista delle chain escluse dal processo (non trade esclusi manualmente)
- Colonne: Signal ID, Symbol, Reason, Note, Raw Message Text (click → modal)
- Etichetta chiara "Excluded from simulation" per non confondere con esclusioni manuali

**4g. Persistenza sessione**
All'apertura del policy report:
- leggere `sessionStorage["compCtx"]` e pre-popolare i filtri (l'intero stato)
- se esiste `sessionStorage["policy_<name>_filters"]`, ha precedenza su compCtx (stato locale più recente)
- leggere `sessionStorage["policy_<name>_excluded"]` e ripristinare checkbox Include
- leggere `sessionStorage["policy_<name>_sort"]` e ripristinare sort

All'interazione utente:
- scrivere in `sessionStorage["policy_<name>_filters"]` ad ogni cambio filtro
- scrivere in `sessionStorage["policy_<name>_excluded"]` ad ogni cambio checkbox
- scrivere in `sessionStorage["policy_<name>_sort"]` ad ogni cambio sort

Al click "Save as comparison context":
- sovrascrivere `sessionStorage["compCtx"]` con il contenuto corrente di `policy_<name>_filters`

**4i. Dati embedded**
Il Python deve embedded nel policy_report.html la lista trade completa come JSON:
```html
<script>
const TRADE_DATA = [
  { "signal_id": "...", "net_pct": -1.2, "gross_pct": ..., ... },
  ...
];
const EXCLUDED_DATA = [...];
const POLICY_METADATA = {...};
</script>
```
Il JS legge questi dati e non usa fetch().

### Dipendenze
- Fase 1 (per link al single trade report)

---

## Fase 5 — Comparison report HTML (nuovo layout PRD-A)

**Obiettivo:** Riscrivere `write_comparison_html_report` in `html_writer.py` con il layout PRD-A.  
**File:** `src/signal_chain_lab/policy_report/html_writer.py`

### Layout obbligatorio (PRD-A §8)
```
Comparison Report
├─ Titolo + Metadati run
├─ Comparison context visibile + Badge "Filters active (N)"
├─ Pulsante "Reset context"
└─ Tabella policy di confronto
```

### Task

**5a. Metadati run**
- Timeframe del backtest
- Price basis
- Market provider
- Generated (timestamp)
- Date range dati testati

**5b. Comparison context visibile**
- Mostrare il context attivo (filtri attivi) in modo leggibile
- Badge `Filters active (N)` dove N = numero filtri attivi non vuoti
- Click sul badge → pannello che lista i filtri attivi con label
- Se context vuoto: no badge, solo testo "No active context"

**5c. Pulsante reset**
- "Reset context" → svuota `sessionStorage["compCtx"]`, aggiorna badge e metriche
- NON tocca le esclusioni per-policy (`policy_<name>_excluded`)

**5d. Tabella di confronto**
Colonne (INC-2 + INC-8, vedere 01_REFERENCE_AGENTE.md §12):
- Policy Name (link a policy_report.html + badge `N excl.` se esclusioni attive in sessionStorage)
- Net %, Gross %, Max DD %, Win Rate %, Profit Factor, Expectancy %, Avg R, Best Trade %, Worst Trade %, Trades, Open Report

Evidenziazione:
- Badge `Best` sotto il nome policy migliore (per Net %)
- Highlight celle: massimo per metriche positive, minimo per Max DD

Aggiornamento dinamico:
- Quando il comparison context cambia (lettura da sessionStorage al focus/visibilitychange), ricalcolare le metriche dal POLICY_DATA embedded

**5e. Dati embedded**
Il Python deve includere in comparison_report.html:
```html
<script>
const POLICY_DATA = {
  "policy_a": {
    "trades": [
      { "signal_id": "...", "net_pct": ..., "gross_pct": ..., "side": ...,
        "status": ..., "symbol": ..., "close_reason": ..., "outcome": ...,
        "created_at": ..., "trader_id": ..., ... },
      ...
    ],
    "summary": { ... }
  },
  "policy_b": { ... }
};
const RUN_METADATA = { ... };
</script>
```

Il JS filtra e ricalcola lato client. Non usa fetch().

**5f. Ricalcolo metriche — funzione `computeAll()`**

Sequenza per ogni policy (INC-8 applicata):

```
1. Leggi POLICY_DATA[policy].trades
2. Applica filtri del comparison context (date, trader, symbol, side, trade_status, close_reason, outcome)
3. Leggi sessionStorage["policy_<name>_excluded"] → lista signal_id esclusi
4. Rimuovi i trade esclusi dalla lista filtrata
5. Calcola metriche sul set risultante
6. Conta N_excluded = esclusi presenti nel set filtrato (non in assoluto)
7. Aggiorna cella tabella + badge "N excl." se N_excluded > 0
```

Nota al punto 6: il badge `N excl.` deve contare solo i trade che sarebbero stati inclusi dopo i filtri ma sono stati esclusi manualmente — non tutti gli esclusi in assoluto. Questo è il numero rilevante per l'utente.

### Dipendenze
- Fase 4 (il policy report deve essere già funzionante per testare la navigazione)

---

## Fase 6 — Test e validazione end-to-end

**Obiettivo:** Verificare tutti i casi obbligatori del PRD-B §30.

### Test case obbligatori (PRD-B §30)
1. Trade con 1 fill e più TP parziali
2. Trade con 2+ fill e average entry dinamica
3. Trade chiuso in stop loss
4. Trade con BE e successivo stop hit
5. Trade scaduto o timeout
6. Trade cancellato senza fill
7. Trade con update ravvicinati nello stesso timestamp

### Test case aggiuntivi per il policy report
8. Policy con 0 trade (tutti esclusi)
9. Policy con trade misto gain/loss/flat
10. Comparison con 2 policy con trade diversi
11. Sessione: aprire policy report, escludere trade, tornare al comparison, verificare che non cambi
12. Sessione: salvare comparison context, aprire altro policy report, verificare pre-compilazione filtri

### Come testare
- Usare i dati nella cartella `docs/policy_report_full_example/` come fixture
- Aprire i report HTML generati in browser (Chrome/Firefox)
- Verificare ogni acceptance criterion del PRD-A §15 e PRD-B §31

---

## Appendice — File toccati per fase

| Fase | File modificati | File creati |
|------|----------------|-------------|
| 1 | — | `policy_report/event_normalizer.py`, `policy_report/tests/test_event_normalizer.py` |
| 2 | `policy_report/trade_chart_payload.py` | — |
| 3 | `policy_report/html_writer.py` (funzione single trade), `policy_report/trade_chart_echarts.py` | — |
| 4 | `policy_report/html_writer.py` (funzione policy report) | — |
| 5 | `policy_report/html_writer.py` (funzione comparison report), `policy_report/comparison_runner.py` | — |
| 6 | — | test e report esempio |

---

## Note implementative finali

- Ogni fase deve concludersi con i test esistenti ancora funzionanti.
- Il cambio di layout HTML non deve rompere il contratto degli output file (stesso path, stessa naming convention).
- Il `comparison_runner.py` passa già `dataset_metadata` e `initial_capital`: verificare che tutti i nuovi campi necessari siano passati alle funzioni html_writer.
- La propagazione del comparison context via URL è preferibile se possibile: `policy_report.html?ctx=<encoded_json>` — il policy report legge il parametro e lo scrive in sessionStorage. Questo rende la navigazione bookmarkable.
