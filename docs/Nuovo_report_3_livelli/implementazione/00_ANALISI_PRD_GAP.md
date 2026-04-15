# Analisi critica PRD — Incongruenze, Ambiguità, Gap

**Data analisi:** 2026-04-15  
**PRD analizzati:**
- `docs/Nuovo_report_3_livelli/PRD_reporting_dinamico_3_livelli.md` (PRD-A)
- `docs/Nuovo_report_3_livelli/PRD_operativo_report_trade_da_zero_v3_sidebar_unificata.md` (PRD-B)

**PRD di riferimento precedenti (contesto storico):**
- `docs/PRD_REPORT_revisionato_e_delta.md`
- `docs/DELTA_policy_report_trade_detail.md`

---

## Legenda

| Tag | Tipo | Priorità |
|-----|------|----------|
| INC | Incongruenza interna o tra PRD | Blocca l'implementazione |
| AMB | Ambiguità — interpretazione multipla possibile | Richiede decisione prima di implementare |
| GAP | Gap — punto non specificato che serve all'implementazione | Deve essere coperto dal piano |
| NOTE | Nota — errore redazionale minore, non bloccante | Correggere nel PRD |

---

## Incongruenze (INC)

---

### INC-1 — Filtro `side` duplicato tra Core e Local

**Posizione:** PRD-A §9.5.1 e §9.5.2

**Problema:**  
`side` appare nella lista dei Core filters (§9.5.1) **e** nella lista dei Local filters (§9.5.2).  
Un filtro non può avere entrambe le semantiche: se è Core viene salvato nel comparison context; se è Local rimane alla policy.

**Decisione concordata:**  
Rimuovere `side` dai Local filters (§9.5.2). Rimane solo tra i Core filters.  
Il filtro `side` è strutturale e riapplicabile su tutte le policy: appartiene al Core.

**Azione:** Aggiornare §9.5.2 rimuovendo `side`.

---

### INC-2 — Colonne comparison report — solo negativo, nessuna lista positiva

**Posizione:** PRD-A §8.4

**Problema:**  
Il PRD-A elenca le colonne da **rimuovere** rispetto a un "esempio attuale" non allegato.  
Non esiste una lista positiva completa delle colonne da mantenere/aggiungere.  
L'implementatore non sa cosa deve esserci.

**Colonne da rimuovere secondo PRD-A:**
`Policy`, `Trades`, `Excluded`, `Win rate`, `Net Profit`, `Profit`, `Loss`, `Profit factor`, `Fee %`, `Funding %`, `Total costs %`

**Decisione:** Definire la lista positiva nel Piano di Attuazione (02_PIANO_ATTUAZIONE.md §4).

---

### INC-3 — Esclusioni manuali e comparison context — punto aperto nel PRD

**Posizione:** PRD-A §8.5

**Testo originale:**
> "Il confronto non deve usare: filtri locali della policy; esclusioni manuali della trade list. ?????"

**Problema:** I `?????` indicano esplicitamente che il punto non è stato risolto durante la redazione del PRD.

**Decisione:**  
Le esclusioni manuali **non devono** influenzare il comparison report.  
Motivazione: §11.2 del PRD-A è coerente: "Non devono passare al comparison_report: esclusioni manuali dei trade."  
I `?????` vanno eliminati e la regola di §11.2 è quella vigente.

---

### INC-4 — `Dataset Name` duplicato in §9.2

**Posizione:** PRD-A §9.2

**Problema:** Il campo `Dataset Name` appare due volte nella lista dei metadati del `single_policy_report`.

**Decisione:** Il secondo `Dataset Name` era probabilmente `Source DB` o `Dataset ID`.  
Basandosi sui dati disponibili nel codice (`runner.py`), la lista corretta è:
- Dataset Name
- Source DB
- Period (date range)
- Market Provider
- Timeframe
- Price Basis
- Selected Chains

---

### INC-5 — Conflitto Hero compact: PRD-B vs DELTA precedente

**Posizione:** PRD-B §9 vs `DELTA_policy_report_trade_detail.md` §5.2

**Problema:**  
PRD-B (§9) dice: *"non mettere in hero dettagli tipo first fill / final exit / avg entry"*  
Il DELTA precedente (§5.2) dice di avere nel summary: *"first fill price, final exit price, fills count"*

**Decisione:** PRD-B è il documento normativo più recente. Prevale.  
L'hero compact non deve contenere: `first fill`, `final exit`, `avg entry`.  
Questi dati possono comparire nella lista eventi sidebar espansa, non nell'hero.

---

### INC-6 — Toggle: PRD-B vs DELTA precedente

**Posizione:** PRD-B §11 vs `DELTA_policy_report_trade_detail.md` §5.3

**Problema:**  
PRD-B (§11): *"solo questi toggle principali: Volume, Event rail"*  
DELTA precedente (§5.3): elenco di 6+ toggle (levels, event labels, markers, volume, position size, pnl)

**Decisione:** PRD-B prevale. Solo Volume e Event Rail come toggle principali sulla toolbar.  
La Legend (§12 PRD-B) sostituisce funzionalmente i toggle di categoria del vecchio DELTA.

---

## Ambiguità (AMB)

---

### AMB-1 — "Da zero" vs codice esistente nel PRD-B

**Posizione:** PRD-B §1, §3 (vincolo 10)

**Testo:** *"Il report va costruito da zero, senza riusare pattern del vecchio report che confliggono con questi requisiti."*

**Ambiguità:** L'implementazione esistente include:
- `trade_chart_payload.py`: serializzazione eventi e livelli (robusto)
- `trade_chart_echarts.py`: chart ECharts con candele OHLC (funzionante)
- `html_writer.py`: template HTML completo

Il vincolo "da zero" va inteso come ristrutturazione del **layout e della logica sidebar**, non come riscrittura del backend Python.

**Decisione:**
- Backend Python (`runner.py`, `trade_chart_payload.py`) → **riusare**
- Chart ECharts (logica candele/livelli) → **riusare** come base, estendere per livelli come segmenti temporali
- Layout HTML del single trade report → **rifare** rispettando il nuovo layout PRD-B
- Sidebar con doppi blocchi (`Selected event summary` + `Operational timeline`) → **eliminare** e sostituire con la lista eventi unificata

---

### AMB-2 — Navigation menu trade: cosa mostra esattamente

**Posizione:** PRD-B §7 (nota layout)

**Testo:** *"tra il blocco principale e l'audit deve essere presente un navigation menu che permetta di navigare tra i vari trade senza tornare alla pagina del report policy"*

**Ambiguità:** Non specifica:
- Solo prev/next? O anche link al policy report?
- Filtro prev/next winning/losing?
- Comportamento al primo e all'ultimo trade?

**Decisione:**  
Navigation bar minimale tra blocco principale e audit:
- `← Prev Trade` | `Back to Policy Report` | `Next Trade →`
- Disabilitato (greyed) quando non esiste prev/next
- NO filtro winning/losing (troppo complesso, non richiesto esplicitamente)

---

### AMB-3 — Meccanismo di propagazione del comparison context

**Posizione:** PRD-A §7.1, §7.2, §6.2

**Ambiguità:** Il PRD dice di usare `sessionStorage` ma non specifica come i filtri Core viaggiano da `comparison_report` a `single_policy_report` (e viceversa) dato che sono file HTML statici separati.

**Decisione:**  
Meccanismo: **`sessionStorage` con chiave condivisa derivata da URL.**
- Alla apertura di `comparison_report.html`, viene scritto `sessionStorage["reportRoot"] = window.location.pathname`
- Il comparison context viene serializzato in `sessionStorage["comparisonCtx"]`
- Il single_policy_report legge `sessionStorage["comparisonCtx"]` all'apertura e pre-popola i filtri Core
- Quando il policy report salva un nuovo context, aggiorna `sessionStorage["comparisonCtx"]`
- Il comparison report, all'attivazione (visibilitychange / focus), rilegge sessionStorage e si aggiorna

---

### AMB-4 — Dati del comparison_report: embedded vs fetch

**Posizione:** PRD-A §8.5 ("metriche ricalcolate/filtrate con il comparison context")

**Ambiguità:** Per ricalcolare le metriche lato client con filtri, il comparison_report ha bisogno dei dati granulari (lista trade per policy). Ma questi sono in file separati. `fetch()` su `file://` è bloccato dai browser.

**Decisione:**  
I dati trade per policy devono essere **embedded nel comparison_report.html** come JSON inline `<script>const POLICY_DATA = {...};</script>` al momento della generazione Python.  
Il ricalcolo avviene lato JS su questi dati embedded.

**Implicazione:** La generazione Python deve includere i trade_results di ogni policy dentro il comparison_report.html.

---

### AMB-5 — Ordinamento trade esclusi manualmente

**Posizione:** PRD-A §10.5 e §10.6

**Conflitto interno:** §10.5 dice che i trade esclusi "devono essere spostati in fondo alla lista". §10.6 definisce ordinamento dinamico per colonna.

**Ambiguità:** Se l'utente ordina per `Net %`, i trade esclusi seguono il sort o restano in fondo?

**Decisione:**  
- **Ordine default** (nessun sort attivo): esclusi in fondo alla lista
- **Con sort attivo** (click colonna): gli esclusi seguono il sort normale, ma mantengono opacità ridotta e restano visivamente distinti
- Motivazione: l'ordinamento per colonna ha senso sull'intera lista; il "fondo" è solo una convenzione visiva nel default

---

### AMB-6 — Badge `filter active`: contenuto e posizionamento

**Posizione:** PRD-A §8.3

**Testo:** *"badge sintetico `filter active` quando è attivo un contesto non vuoto; dettaglio espandibile o tooltip del contenuto del context"*

**Ambiguità:** Non specifica:
- Cosa mostra il badge (solo testo "Filters active" o anche un count "3 filters")?
- Il tooltip è hover-only o c'è un pannello espandibile cliccabile?

**Decisione:**
- Badge mostra: `Filters active (N)` dove N è il numero di filtri Core attivi
- Comportamento: click sul badge apre un pannello inline che mostra i filtri attivi con etichette leggibili
- Se N = 0, il badge non è mostrato

---

## Gap (GAP)

---

### GAP-1 — Valori ammessi di `trade status` non definiti

**Posizione:** PRD-A §9.5.1 (Core filter), §10.2 (colonna tabella)

**Gap:** Il filtro Core `trade status` e la colonna omonima non hanno valori definiti nel PRD.

**Dal codice esistente (`domain/enums.py`, `domain/results.py`):**
- `closed`
- `expired`
- `cancelled`
- `open` (trade ancora attivi, se presenti)

Questi 4 valori devono essere l'elenco del dropdown filtro.

---

### GAP-2 — `outcome` come filtro Local: su quale campo agisce

**Posizione:** PRD-A §5.2

**Gap:** `outcome` (All / gain / loss / flat) non è una colonna della tabella. Non è specificato su quale campo calcola.

**Decisione:** `outcome` è derivato da `Net %`:
- `gain`: `Net % > 0`
- `loss`: `Net % < 0`
- `flat`: `Net % == 0`
- `All`: nessun filtro

**Nota:** superseded da INC-7 — `outcome` è ora filtro unificato (Core).

---

### GAP-3 — `Warn` vs `Warnings` — naming inconsistente

**Posizione:** PRD-A §10.2

**Gap:** PRD-A chiama la colonna `Warn`. Il codice esistente usa `Warnings`. Il PRD-B usa `warnings` nel campo hero.

**Decisione:** Standardizzare su `Warn` come etichetta colonna breve nella tabella. Tooltip espanso mostra "Warnings". Il campo dati rimane `warnings_count`.

---

### GAP-4 — Sezione 2 mancante nel PRD-A

**Posizione:** PRD-A struttura generale

**Note:** Il documento passa da §1 a §3 senza §2. Non è chiaro se ci sia contenuto omesso.

**Azione:** Non blocca l'implementazione. Da verificare con il product owner se c'è contenuto mancante.

---

### GAP-5 — Sezioni 5, 6, 8 mancanti nel PRD-B

**Posizione:** PRD-B struttura generale

**Note:** Numerazione discontinua: 1, 2, 3, 4, poi 7, poi 9, 10, 11... Sezioni 5, 6, 8 assenti.

**Azione:** Non blocca l'implementazione. Il contenuto presente è sufficiente. Da verificare con il product owner.

---

### GAP-6 — Modello canonico eventi: mapping da EventLogEntry esistente

**Posizione:** PRD-B §14

**Gap:** Il PRD-B definisce uno schema canonico evento JSON. Il codice esistente ha `EventLogEntry` (Pydantic model) con campi diversi.  
Non è specificato come mappare i campi esistenti nello schema canonico PRD-B.

**Dal codice (`domain/results.py`):**
```python
class EventLogEntry(BaseModel):
    event_type: str
    timestamp: str
    price: float | None
    description: str
    data: dict | None
    source: str | None
    ...
```

**Mapping richiesto definito nel Piano di Attuazione (02_PIANO_ATTUAZIONE.md §6).**

---

### GAP-7 — Segmenti temporali livelli: dati disponibili nel payload

**Posizione:** PRD-B §16, §17

**Gap:** Il PRD-B richiede che i livelli (SL, TP, entry) siano segmenti temporali (start/end timestamp). Il `trade_chart_payload.py` esistente genera già segmenti, ma non è chiaro se gestisce correttamente la storia degli SL multipli (moved SL).

**Azione:** Verificare `trade_chart_payload.py` e completare la logica per SL multipli durante l'implementazione.

---

### GAP-8 — Interazione cross-report: `single_trade_report` → `single_policy_report`

**Posizione:** PRD-A §6.4, §7.5

**Gap:** Il PRD dice che aprendo il trade report non deve perdersi il "contesto di navigazione utile al ritorno". Non specifica cosa deve essere preservato (filtri? posizione scroll? sort?).

**Decisione:** Il trade report preserva:
- Link di ritorno al policy report che include i filtri attivi come query parameter o via sessionStorage
- Nessun scroll position (troppo complesso)
- Solo il riferimento alla policy di provenienza (già implementato con `back_link_href` nel codice)

---

---

### INC-7 — Distinzione Core/Local filtri è artificiale — APPROVATA unificazione

**Posizione:** PRD-A §9.5.1, §9.5.2

**Problema:**
La separazione Core/Local presuppone che `close reason` e `outcome` non siano "portabili" nel comparison context. Questa ipotesi è falsa:
- "Confronta le policy solo sui trade chiusi in TP" → filtro `close reason = TP` è pienamente comparabile cross-policy.
- "Confronta le policy solo sui trade in gain" → filtro `outcome = gain` è pienamente comparabile cross-policy.

Tutti i filtri agiscono sulla stessa trade list. Non esiste un filtro che abbia senso solo per una singola policy e non per un confronto.

L'unica distinzione che mantiene senso è tra **filtri** (tutti riapplicabili) e **esclusioni manuali per-trade** (specifiche di un trade, non portabili).

**Decisione approvata:** Opzione A — unificazione totale.

**Modello risultante:**
- Un solo pannello filtri nel `single_policy_report`
- Tutti i filtri sono Core e tutti salvabili nel comparison context
- Filtri unificati: `date range`, `trader`, `symbol`, `side`, `trade status`, `close reason`, `outcome`
- Le esclusioni manuali per-trade rimangono separate (non sono filtri)
- Pulsante "Save as comparison context" salva l'intero stato filtri

**Impatto su INC-1:** La rimozione di `side` dai Local filters (INC-1) è ora irrilevante: la distinzione Core/Local non esiste più.

---

## Riepilogo decisioni concordate

| ID | Decisione |
|----|-----------|
| INC-1 | Superato da INC-7 |
| INC-2 | Lista colonne comparison definita in 02_PIANO_ATTUAZIONE.md §4 |
| INC-3 | Esclusioni manuali NON passano al comparison report (§11.2 prevalente) |
| INC-4 | Secondo `Dataset Name` → `Source DB` |
| INC-5 | PRD-B prevale su DELTA: no avg/fill nell'hero compact |
| INC-6 | PRD-B prevale su DELTA: solo Volume e Event Rail come toggle |
| **INC-7** | **Filtri unificati — nessuna distinzione Core/Local. Tutti salvabili nel comparison context.** |
| AMB-1 | "Da zero" = rifacimento layout HTML, non del backend Python |
| AMB-2 | Nav menu: Prev/Back/Next, senza filtri winning/losing |
| AMB-3 | Propagazione context via sessionStorage con chiave da pathname |
| AMB-4 | Dati trade embedded nel comparison_report.html come JSON inline |
| AMB-5 | Sort attivo prevale sul "esclusi in fondo"; default order = esclusi in fondo |
| AMB-6 | Badge `Filters active (N)`, pannello espandibile al click |
| GAP-1 | trade status values: closed, expired, cancelled, open |
| GAP-2 | outcome agisce su Net %: >0 gain, <0 loss, =0 flat |
| GAP-3 | Colonna chiamata `Warn`, campo dati `warnings_count` |
| GAP-6 | Mapping EventLogEntry → canonico definito in 02_PIANO_ATTUAZIONE.md §6 |
| GAP-7 | Verificare e completare payload SL multipli durante implementazione |
| GAP-8 | Ritorno al policy report via back_link_href + sessionStorage filtri |
