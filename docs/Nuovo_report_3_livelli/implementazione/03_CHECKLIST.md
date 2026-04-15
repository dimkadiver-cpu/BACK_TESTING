# Checklist di attuazione — Sistema report 3 livelli

**Data:** 2026-04-15  
**Come usare:** spuntare ogni item solo dopo verifica reale, non solo dopo aver scritto il codice.

Legenda: `[ ]` = da fare, `[x]` = completato, `[~]` = parziale/bloccato

---

## PRE-REQUISITI (verifica prima di iniziare)

- [ ] Letti tutti i documenti: PRD-A, PRD-B, 00_ANALISI_PRD_GAP.md, 01_REFERENCE_AGENTE.md, 02_PIANO_ATTUAZIONE.md
- [ ] Test suite esistente passa: `pytest src/signal_chain_lab/policy_report/`
- [ ] Il report di esempio in `docs/policy_report_full_example/` è apribile in browser senza errori
- [ ] Confermata la lista di decisioni da 00_ANALISI_PRD_GAP.md con il product owner

---

## FASE 1 — Normalizzatore eventi canonico

### Implementazione
- [ ] Creato `src/signal_chain_lab/policy_report/event_normalizer.py`
- [ ] Definito dataclass `CanonicalEvent` con tutti i campi dello schema PRD-B §14
- [ ] Implementata funzione `normalize_events(trade, event_log) -> list[CanonicalEvent]`
- [ ] Mapping phase/class implementato per tutti i 17+ event_type rilevati nel codice
- [ ] Tutti i subtype canonici PRD-B §15 supportati (17 subtype minimi)
- [ ] Fallback a `SYSTEM_NOTE` per event_type sconosciuti
- [ ] Campo `raw_text` propagato correttamente (solo per eventi TRADER)

### Test
- [ ] Creato `src/signal_chain_lab/policy_report/tests/test_event_normalizer.py`
- [ ] Test: evento ENTRY_FILLED → subtype `ENTRY_FILLED`, phase `ENTRY`, class `STRUCTURAL`
- [ ] Test: evento senza raw_text → campo `raw_text` None nel canonico
- [ ] Test: evento IGNORED → class `AUDIT`
- [ ] Test: trade senza eventi → lista vuota, nessun crash
- [ ] `pytest` passa

---

## FASE 2 — Segmenti livelli temporali

### Verifica e completamento
- [ ] Letto `trade_chart_payload.py` per capire lo stato attuale
- [ ] Verificato: SL con history multipla → segmenti separati (ogni `SL_MOVED` chiude e apre)
- [ ] Verificato: TP multipli → un segmento per ciascun TP distinto
- [ ] Verificato: `average_entry` non disegnata se `fills_count < 2`
- [ ] Struttura `LevelSegment` con campi: kind, label, price, ts_start, ts_end, color, style
- [ ] Entry limit: blu, tratteggiato
- [ ] Entry market: viola, tratteggiato
- [ ] Stop loss: rosso, tratteggiato
- [ ] Take profit: verde, tratteggiato
- [ ] Average entry: ciano, continuo (solo se fills >= 2)
- [ ] Segmenti coerenti con asse temporale del chart (non statici)

### Test
- [ ] Test: trade con SL moved → 2 segmenti SL, il primo chiuso al timestamp SL_MOVED
- [ ] Test: trade con single fill → nessun segmento avg_entry
- [ ] Test: trade con 2 fill → segmento avg_entry presente
- [ ] Test: TP multipli → segmenti distinti, ciascuno termina al suo hit timestamp o al trade close
- [ ] `pytest` passa

---

## FASE 3 — Single trade report HTML (layout PRD-B)

### Hero compact
- [ ] Campi presenti: symbol/side/status, return % net, return % gross, costs total %, fees %, funding %, R, MAE %, MFE %, duration
- [ ] Warnings mostrati solo se > 0
- [ ] Hero NON contiene: first fill, final exit, avg entry (INC-5 applicato)
- [ ] Layout leggibile su viewport ridotti

### Toolbar
- [ ] Toggle `Volume` presente e funzionante
- [ ] Toggle `Event Rail` presente e funzionante
- [ ] Selector timeframe presente (se dati disponibili per più timeframe)
- [ ] Tutti sulla stessa riga

### Legend
- [ ] Mostra tutti gli elementi richiesti (entry, sl, tp, marker fill, marker exit, ecc.)
- [ ] Colori coerenti con PRD-B §17 e 01_REFERENCE_AGENTE.md §5
- [ ] Click su elemento legend → toggle visibilità categoria sul chart

### Price chart
- [ ] Candele OHLC visibili
- [ ] Livelli come segmenti temporali (non linee statiche)
- [ ] SL history: ogni SL moved = nuovo segmento distinto
- [ ] Marker eventi sul chart (ENTRY_FILLED, TP_HIT, SL_HIT, PARTIAL_EXIT, FINAL_EXIT)
- [ ] Tooltip su marker: tipo + timestamp + prezzo + summary
- [ ] Zoom e pan funzionanti
- [ ] Livelli allineati con candele durante zoom/pan
- [ ] Volume toggle funzionante e allineato all'asse temporale
- [ ] Nessun desync tra chart, rail, volume durante navigazione

### Event rail
- [ ] Visibile di default
- [ ] Nascondibile via toggle
- [ ] Stessa scala temporale del chart
- [ ] Si aggiorna con zoom/pan
- [ ] Lane separate per eventi vicini nello stesso timestamp
- [ ] Simboli coerenti per categoria (SL_MOVED, BE_ACTIVATED, CANCELLED, EXPIRED, TIMEOUT, SYSTEM_NOTE)

### Sidebar — lista eventi unificata
- [ ] UN SOLO componente (no `Selected event summary` + `Operational timeline` separati)
- [ ] Tutti gli eventi ordinati cronologicamente
- [ ] Ogni item collassato di default
- [ ] Click → espande item; espansione di un item chiude gli altri
- [ ] Vista collassata: timestamp + label + breve descrizione + chip
- [ ] Vista espansa: dettaglio evento + raw text button (solo se source=TRADER)
- [ ] Click evento sul chart → evidenzia e apre item corrispondente in sidebar
- [ ] Click evento sulla rail → stessa cosa
- [ ] Click item sidebar → evidenzia evento su chart o rail
- [ ] Setup item mostra: symbol, side, tipo entry, livelli entry, SL, TP (se pertinenti)
- [ ] NO dump raw di requested_action / executed_action in vista base
- [ ] Audit drawer separato (vedi sotto)

### Navigation bar
- [ ] Presente tra blocco principale e audit
- [ ] Pulsanti: `← Prev` | `Back to Policy Report` | `Next →`
- [ ] Prev/Next disabilitati (greyed) al primo/ultimo trade
- [ ] Back to Policy Report: link al policy_report.html corretto

### Audit drawer
- [ ] `<details>` HTML, chiuso di default
- [ ] Contiene: tutti gli eventi inclusi IGNORED e SYSTEM_NOTE
- [ ] Ogni evento: timestamp + tipo + `<pre>` JSON completo del payload
- [ ] Non compete visivamente con la vista principale

### Funzionamento offline
- [ ] Report aperto da file:// senza rete: funziona senza errori
- [ ] Nessun link a CDN esterni

---

## FASE 4 — Single policy report HTML (layout PRD-A)

### Metadati
- [ ] Dataset metadata (collapsible): Dataset Name, Source DB, Period, Market Provider, Timeframe, Price Basis, Selected Chains
- [ ] No `Dataset Name` duplicato (INC-4 applicato)
- [ ] policy.yaml values (collapsible): tabella chiave/valore

### Filtri Core
- [ ] Date range picker (from/to)
- [ ] Trader input
- [ ] Symbol input (multi-value)
- [ ] Side dropdown (All / LONG / SHORT)
- [ ] Trade Status checkbox multi (closed, expired, cancelled, open)
- [ ] Pulsante "Save as comparison context": salva solo Core in sessionStorage
- [ ] `side` NON presente nei Local filters (INC-1 applicato)

### Filtri Local
- [ ] Close Reason checkbox multi
- [ ] Outcome dropdown (All / gain / loss / flat)
- [ ] Separati visivamente dai Core filters
- [ ] Label che indica "local — not saved to context"

### Contatori base
- [ ] Simulated chains
- [ ] Excluded signals
- [ ] Closed
- [ ] Expired

### Metriche cumulative (aggiornamento dinamico)
- [ ] Trades included
- [ ] Win rate
- [ ] Gross %
- [ ] Net %
- [ ] Fee %
- [ ] Funding %
- [ ] Total costs %
- [ ] Final Cum Equity
- [ ] Avg R
- [ ] Best Trade % Net
- [ ] Worst Trade % Net
- [ ] Profit Factor
- [ ] Tutte le metriche si aggiornano quando: filtro applicato, checkbox Include cambiata

### Trade list
- [ ] Colonna `Include` con checkbox
- [ ] Tutte le colonne richieste (vedere 01_REFERENCE_AGENTE.md §10)
- [ ] Trade escluso → opacità ridotta (0.4), spostato in fondo nel default order
- [ ] Con sort attivo → esclusi seguono il sort (AMB-5 applicato)
- [ ] Sort numerico: click1 = best→worst (header verde), click2 = worst→best (header rosso), click3 = reset
- [ ] Sort testuale: click1 = A→Z, click2 = Z→A, click3 = reset
- [ ] Colonna `Detail`: link che apre detail.html del trade (non click sull'intera riga)

### Segnali esclusi
- [ ] Sezione separata e chiaramente distinta dalla trade list
- [ ] Label "Excluded from simulation" (non confondere con esclusioni manuali)
- [ ] Collapsible
- [ ] Colonne: Signal ID, Symbol, Reason, Note, Raw Message Text
- [ ] Click Raw Message Text → modal con testo originale

### Reset controls
- [ ] Pulsante "Reset local filters"
- [ ] Ripristina anche tutte le checkbox Include (riattiva tutti i trade)

### Persistenza sessione
- [ ] All'apertura: legge sessionStorage e ripristina Core filters, Local filters, excluded set, sort
- [ ] Ad ogni interazione: scrive in sessionStorage
- [ ] Chiave per Core: `compCtx`
- [ ] Chiave per Local: `policy_<name>_filters`, `policy_<name>_sort`, `policy_<name>_excluded`

### Dati embedded
- [ ] `<script>const TRADE_DATA = [...]</script>` nel HTML
- [ ] Contiene tutti i campi necessari per le metriche e i filtri
- [ ] Nessuna fetch() di file esterni

---

## FASE 5 — Comparison report HTML (layout PRD-A)

### Metadati run
- [ ] Timeframe del backtest
- [ ] Price basis
- [ ] Market provider
- [ ] Generated timestamp
- [ ] Date range dati

### Comparison context
- [ ] Context attivo mostrato in modo leggibile (filtri attivi con label)
- [ ] Badge `Filters active (N)` con N = count filtri attivi
- [ ] Click badge → pannello filtri attivi espandibile
- [ ] Se context vuoto: no badge, testo "No active context"
- [ ] Pulsante "Reset context" → svuota sessionStorage["compCtx"], aggiorna tutto

### Tabella confronto
- [ ] Colonne: Policy Name, Net %, Gross %, Max DD %, Win Rate %, Profit Factor, Expectancy %, Avg R, Best Trade %, Worst Trade %, Trades, Open Report
- [ ] Badge `Best` sotto policy migliore per Net %
- [ ] Highlight celle: max per metriche positive, min per Max DD
- [ ] Click Policy Name / Open Report → apre policy_report.html con context propagato

### Aggiornamento dinamico con context
- [ ] Metriche ricalcolate in JS sui dati POLICY_DATA embedded
- [ ] Filtri Core del context applicati ai trade per policy
- [ ] Highlights e badge aggiornati dopo ricalcolo
- [ ] Si aggiorna quando torna in focus (window.addEventListener('focus', ...)) e legge sessionStorage

### Dati embedded
- [ ] `<script>const POLICY_DATA = {...}</script>` nel HTML
- [ ] Trade list completa per ogni policy (con tutti i campi per filtraggio)
- [ ] Summary policy presente
- [ ] RUN_METADATA presente

### Funzionamento offline
- [ ] Nessuna fetch() di file esterni
- [ ] Tutto funziona da file://

---

## FASE 6 — Test e validazione end-to-end

### Test case PRD-B §30
- [ ] Trade con 1 fill e più TP parziali → chart corretto, events in sidebar
- [ ] Trade con 2+ fill e average entry → segmento avg_entry visibile
- [ ] Trade chiuso in stop loss → SL hit marker sul chart, evento in sidebar
- [ ] Trade con BE e successivo stop hit → SL history con 2 segmenti
- [ ] Trade scaduto o timeout → evento EXPIRED/TIMEOUT in rail
- [ ] Trade cancellato senza fill → no fill marker, evento CANCELLED in sidebar
- [ ] Trade con update ravvicinati → no sovrapposizioni illeggibili

### Test navigazione inter-report
- [ ] Comparison → Policy: Core filters pre-compilati nel policy report
- [ ] Policy → Comparison: "Save context" aggiorna il comparison report
- [ ] Policy → Trade: trade detail si apre correttamente
- [ ] Trade → Policy: back link funziona

### Test persistenza sessione
- [ ] Esclusione trade in policy report → metriche aggiornate
- [ ] Ricaricamento policy report → set esclusi ripristinato
- [ ] Esclusioni NON visibili nel comparison report (INC-3 applicato)
- [ ] Salvataggio context → comparison report si aggiorna

### Test acceptance criteria PRD-A §15
- [ ] 1. Navigazione tra 3 livelli funzionante
- [ ] 2. single_trade_report non ridefinito da PRD-A (gestito da PRD-B)
- [ ] 3. comparison_report applica comparison context con soli Core filters
- [ ] 4. single_policy_report: filtri Core e Local separati
- [ ] 5. single_policy_report: esclusione manuale via checkbox
- [ ] 6. Esclusioni manuali non alterano dati sorgente né comparison report
- [ ] 7. Trade list: colonne concordate, sort concordato
- [ ] 8. comparison_report: context visibile, badge, Best tag, highlight
- [ ] 9. single_policy_report: contatori, metriche, segnali esclusi, policy.yaml
- [ ] 10. Stato sessione preservato durante navigazione

### Test acceptance criteria PRD-B §31
- [ ] 1. Grafico è il fulcro del report
- [ ] 2. Volume e Event Rail funzionano indipendentemente
- [ ] 3. No toggle Focus/Management/Audit (rimossi)
- [ ] 4. Livelli come segmenti temporali reali
- [ ] 5. SL, TP, entry seguono logica temporale
- [ ] 6. Average entry solo con 2+ fill
- [ ] 7. Rail evita collisioni distruttive
- [ ] 8. Etichette non tagliate in condizioni standard
- [ ] 9. Zoom/pan mantiene allineamento chart, rail, livelli
- [ ] 10. Side panel: SOLA lista eventi unificata
- [ ] 11. Lista: collassata default, sintetica, espandibile
- [ ] 12. Vista espansa = sostituisce Selected event summary
- [ ] 13. Sotto al blocco principale solo audit (separato, collassato)
- [ ] 14. Report funziona offline

---

## COMMIT POINTS consigliati

Eseguire commit separati a fine di ogni fase verificata:

```
feat(report): add canonical event normalizer [fase 1]
feat(report): refactor level segments as temporal ranges [fase 2]
feat(report): rewrite single trade report layout (PRD-B) [fase 3]
feat(report): rewrite policy report with dynamic filters (PRD-A) [fase 4]
feat(report): rewrite comparison report with context system (PRD-A) [fase 5]
test(report): add e2e validation for 3-level report system [fase 6]
```

---

## SEGNALI DI RISCHIO — quando fermarsi e discutere

- Il mapping EventLogEntry → CanonicalEvent non copre event_type nuovi trovati nei dati reali → aggiornare la tabella in 01_REFERENCE_AGENTE.md
- La struttura `LevelSegment` non è sufficiente per ricostruire la storia SL da certi trade → escalare con esempi concreti
- Il `POLICY_DATA` embedded nel comparison_report.html diventa troppo grande (> 5MB) → valutare paginazione o lazy load JSON separato servito via schema diverso
- Il ricalcolo JS delle metriche con context applicato produce risultati diversi dal Python (discrepanza numerica) → debug e allineamento obbligatorio prima del rilascio
