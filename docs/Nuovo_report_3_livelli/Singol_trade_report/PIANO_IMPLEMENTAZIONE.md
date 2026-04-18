# Piano di implementazione — Single Trade Report

> Basato su: `PRD_definitivo_sistemazione_eventi_single_trade_report.md`
> e documenti derivati presenti in questa directory.
> In caso di conflitto tra questo piano e il PRD master, prevale il PRD.

---

## Contesto codebase attuale

### File coinvolti

| File | Ruolo |
|---|---|
| `src/signal_chain_lab/policy_report/event_normalizer.py` | Normalizzatore raw → canonico |
| `src/signal_chain_lab/policy_report/trade_chart_payload.py` | Builder payload chart/eventi |
| `src/signal_chain_lab/policy_report/trade_chart_echarts.py` | Renderer ECharts (JS inline) |
| `src/signal_chain_lab/policy_report/html_writer.py` | Writer HTML single-trade |
| `src/signal_chain_lab/policy_report/tests/test_event_normalizer.py` | Test normalizer |
| `src/signal_chain_lab/policy_report/tests/test_runner_trade_chart_context.py` | Test runner/chart |
| `tests/unit/test_reporting_delta_a.py` | Test delta/reporting |

### Gap rispetto al PRD

#### 1. Tassonomia `event_code`

Il codice attuale usa la classe `Subtype` con nomi non allineati al PRD.

| Attuale (`Subtype`) | Target (`event_code` PRD) |
|---|---|
| `SIGNAL_CREATED` | `SETUP_CREATED` |
| `ENTRY_PLANNED` | `ENTRY_ORDER_ADDED` |
| `ENTRY_FILLED` | `ENTRY_FILLED_INITIAL` |
| `SCALE_IN_FILLED` | `ENTRY_FILLED_SCALE_IN` |
| `MARKET_ENTRY_FILLED` | `ENTRY_FILLED_INITIAL` (market) |
| `SL_MOVED` | `STOP_MOVED` |
| `BE_ACTIVATED` | `BREAK_EVEN_ACTIVATED` |
| `TP_HIT` | `EXIT_PARTIAL_TP` |
| `PARTIAL_EXIT` | `EXIT_PARTIAL_MANUAL` |
| `FINAL_EXIT` | `EXIT_FINAL_TP` / `EXIT_FINAL_MANUAL` |
| `SL_HIT` | `EXIT_FINAL_SL` |
| `TIMEOUT` (CLOSE_FULL) | `EXIT_FINAL_TIMEOUT` |
| `CANCELLED` (trader) | `PENDING_CANCELLED_TRADER` |
| `CANCELLED` (engine) | `PENDING_CANCELLED_ENGINE` |
| `TIMEOUT` (CANCEL_PENDING) | `PENDING_TIMEOUT` |
| `IGNORED` | `IGNORED` |
| `SYSTEM_NOTE` | `SYSTEM_NOTE` |

#### 2. Campi canonici mancanti in `ReportCanonicalEvent`

Campi obbligatori PRD §6.2 non presenti o incompleti:

- `event_code` — il codice canonico PRD (attualmente solo `subtype` con naming diverso)
- `stage` — `ENTRY` / `MANAGEMENT` / `EXIT` (attualmente `phase` include anche `SETUP`, `POST_MORTEM`)
- `position_effect` — `PLAN_CREATED` / `POSITION_OPENED` / ecc.
- `display_group` — non presente
- `display_label` — non presente (usato `title`)
- `sequence_index` — presente ma non nel contratto canonico
- `raw_event_ref` — non presente
- `event_list_section` — non presente (A/B)
- `chart_marker_kind` — non presente (REQUIRED/OPTIONAL_LIGHT/NONE)
- `geometry_effect` — non presente
- `state_delta_full` — non presente
- `state_delta_essential` — non presente

#### 3. Logica stage per CANCEL/TIMEOUT

Il codice attuale mappa `CANCEL_PENDING` e timeout sempre su `Phase.EXIT`.

Il PRD §12 richiede:
- se `open_size == 0` **prima** dell'evento → `stage = ENTRY`
- se `open_size > 0` **prima** dell'evento → `stage = MANAGEMENT`

#### 4. Event list in `html_writer.py`

- Non divisa in Sezione A e Sezione B
- Nessun `state_delta_essential` per card
- Nessun bottone `AUDIT` per-evento
- Audit drawer: globale con `<details>`, non per-evento
- Audit drawer apribile anche senza click su `AUDIT` (D4 violata)
- Struttura audit drawer non conforme al PRD §7: mancano sezioni
  execution summary / readable state delta / structured event data /
  original trader message / raw technical data

#### 5. Chart e rail in `trade_chart_echarts.py`

- Rail mostra anche eventi Section B (IGNORED, SYSTEM_NOTE)
- Marker chart non filtrati per `chart_marker_kind` (REQUIRED/OPTIONAL/NONE)
- STOP_MOVED e BE_ACTIVATED vanno già su "rail" non su chart — corretto —
  ma la gestione geometrica non usa ancora `geometry_effect`
- Click su chart/rail apre direttamente `AUDIT` invece di scrollare event list

---

## Architettura del flusso target

```
raw EventLogEntry
      ↓
event_normalizer.py
  - mapping raw_type → event_code canonico PRD
  - assegna: stage, position_effect, source, event_list_section
  - assegna: chart_marker_kind, geometry_effect
  - costruisce: state_delta_full → deriva state_delta_essential
  - ordine deterministico multi-evento stesso timestamp (PRD §13.2)
      ↓
ReportCanonicalEvent (contratto completo PRD §6.2 + §6.3)
      ↓
trade_chart_payload.py
  - usa event_code / chart_marker_kind per eventi chart
  - usa geometry_effect per level segments
  - passa state_delta_essential al payload
      ↓
payload JSON (events + level_segments + meta)
      ↓
┌──────────────────┬──────────────────────────┐
│ trade_chart_echarts.py │ html_writer.py               │
│ - rail: solo Section A  │ - event list Section A + B   │
│ - chart: REQUIRED+OPT   │ - state_delta_essential      │
│ - click → event list    │ - per-event AUDIT button     │
│   (non audit drawer)    │ - audit drawer per-evento    │
└──────────────────┴──────────────────────────┘
```

---

## Step di implementazione

### Step 1 — Allineamento tassonomia `event_code` in `event_normalizer.py` ✅ COMPLETATO

**Obiettivo:** allineare naming interno al PRD.

**Azioni:**

1. ✅ Rinominare le costanti della classe `Subtype` con i nuovi `event_code` PRD.
   17 costanti PRD complete — nessun backward alias necessario (test aggiornati contestualmente).

2. ✅ Aggiornare `_SUBTYPE_TITLE`, `_VISUAL_COLOR_KEY`, `_EVENT_KIND_MAP` con i nuovi nomi.
   Aggiornati anche in `trade_chart_payload.py` e `html_writer.py`.

3. ✅ Aggiornare `_derive_subtype_phase_class`:
   - `CLOSE_PARTIAL` con reason TP → `EXIT_PARTIAL_TP`
   - `CLOSE_PARTIAL` senza reason TP → `EXIT_PARTIAL_MANUAL`
   - `CLOSE_FULL` con reason TP → `EXIT_FINAL_TP`
   - `CLOSE_FULL` con reason SL → `EXIT_FINAL_SL`
   - `CLOSE_FULL` con reason manual → `EXIT_FINAL_MANUAL`
   - `CLOSE_FULL` con reason timeout → `EXIT_FINAL_TIMEOUT`
   - `CANCEL_PENDING` con source trader → `PENDING_CANCELLED_TRADER`
   - `CANCEL_PENDING` con source engine → `PENDING_CANCELLED_ENGINE`
   - `CANCEL_PENDING` con reason timeout → `PENDING_TIMEOUT`

4. ✅ Rimossi `Phase.SETUP` e `Phase.POST_MORTEM`.
   SETUP_CREATED → `Phase.ENTRY`. IGNORED/SYSTEM_NOTE → `Phase.MANAGEMENT`.

5. ✅ Aggiornato `test_event_normalizer.py`: 37 test (32 originali + 5 nuovi per le distinzioni granulari).
   Aggiunto sort deterministico `_SUBTYPE_SORT_PRIORITY` (precursore Step 3).

**File toccati:** `event_normalizer.py`, `test_event_normalizer.py`, `trade_chart_payload.py`, `html_writer.py`

**Dipendenze:** nessuna — step base.

**Risultato:** 43 test verdi (tutti i test policy_report + test_reporting_delta_a).

---

### Step 2 — Estensione contratto `ReportCanonicalEvent` con campi PRD §6

**Obiettivo:** aggiungere i campi obbligatori e raccomandati del contratto canonico.

**Azioni:**

1. Aggiungere a `ReportCanonicalEvent`:
   ```python
   event_code: str                          # = event_code PRD (rinominato da subtype)
   stage: str                               # ENTRY | MANAGEMENT | EXIT
   position_effect: str                     # PLAN_CREATED | POSITION_OPENED | ecc.
   display_group: str                       # raggruppa eventi correlati
   display_label: str                       # label leggibile per UI (fallback da event_code)
   event_list_section: str                  # "A" | "B"
   chart_marker_kind: str                   # REQUIRED | OPTIONAL_LIGHT | NONE
   geometry_effect: str                     # CREATE_INITIAL_LEVELS | ADD_PENDING_LEVEL | ecc.
   state_delta_full: list[dict]             # schema PRD §11.2
   state_delta_essential: list[dict]        # derivato da state_delta_full
   raw_event_ref: str | None                # riferimento evento raw sorgente
   ```

2. Implementare funzione `_build_state_delta_full(before, after)` che produce la lista
   di delta con campi: `field_path`, `before`, `after`, `unit`, `is_mutative`, `display_priority`.

3. Implementare funzione `_derive_state_delta_essential(delta_full)` che filtra e
   seleziona i delta più rilevanti per la event list (i.e. `is_mutative=True` e
   `display_priority <= N`).

4. Implementare `_build_position_effect(event_code, state_before, state_after)` che
   restituisce il `position_effect` corretto per ogni evento canonico.

5. Implementare `_build_geometry_effect(event_code)` che restituisce il `geometry_effect`
   dalla matrice PRD §15.2.

6. Implementare `_build_chart_marker_kind(event_code)` che restituisce
   `REQUIRED` / `OPTIONAL_LIGHT` / `NONE` dalla matrice PRD §9.

7. Implementare `_build_event_list_section(event_code)` che restituisce `A` o `B`.

8. Implementare la logica stage per CANCEL/TIMEOUT (PRD §12):
   leggere `open_size` da `state_before` (non `state_after`).

**File:** `event_normalizer.py`

**Dipendenze:** Step 1 completato.

---

### Step 3 — Ordinamento deterministico multi-evento (PRD §13.2)

**Obiettivo:** garantire ordine causale corretto quando più eventi hanno lo stesso timestamp.

**Azioni:**

1. Aggiornare la funzione di sort in `normalize_events` con la priorità PRD §13.2:
   ```
   1. setup / creazione piano  (SETUP_CREATED, ENTRY_ORDER_ADDED)
   2. fill iniziale o scale-in (ENTRY_FILLED_INITIAL, ENTRY_FILLED_SCALE_IN)
   3. move stop / break-even  (STOP_MOVED, BREAK_EVEN_ACTIVATED)
   4. exit partial             (EXIT_PARTIAL_TP, EXIT_PARTIAL_MANUAL)
   5. exit final               (EXIT_FINAL_*)
   6. eventi informativi/audit (IGNORED, SYSTEM_NOTE)
   ```

2. Casi eccezione espliciti:
   - setup market-fill: `SETUP_CREATED` prima di `ENTRY_FILLED_INITIAL`
   - TP con regola automatica BE: `EXIT_PARTIAL_TP` prima di `BREAK_EVEN_ACTIVATED`

3. Aggiungere test dedicati per gli scenari multi-evento stesso timestamp.

**File:** `event_normalizer.py`, `test_event_normalizer.py`

**Dipendenze:** Step 2.

---

### Step 4 — Aggiornamento `trade_chart_payload.py`

**Obiettivo:** allineare il payload chart ai nuovi campi canonici.

**Azioni:**

1. Aggiornare `_EVENT_KIND_MAP` con i nuovi `event_code`.

2. In `_build_events`:
   - aggiungere `event_code` al dict evento
   - aggiungere `chart_marker_kind` al dict evento
   - aggiungere `geometry_effect` al dict evento
   - aggiungere `event_list_section` al dict evento
   - aggiungere `position_effect` al dict evento
   - aggiungere `state_delta_essential` al dict evento

3. In `_build_events`: filtrare i marker chart usando `chart_marker_kind`:
   - `REQUIRED` → `placement = "chart"` se ha `price_anchor`
   - `OPTIONAL_LIGHT` → `placement = "chart_optional"` (o mantenere "rail" con flag)
   - `NONE` → `placement = "rail"` (visibile solo in event list, non in chart)

4. Verificare che `STOP_MOVED` e `BREAK_EVEN_ACTIVATED` abbiano `placement = "rail"`
   (nessun marker chart, solo geometria linee).

5. Verificare che `SETUP_CREATED` e `ENTRY_ORDER_ADDED` abbiano `placement = "rail"`
   (nessun marker chart).

6. Verificare che `IGNORED` e `SYSTEM_NOTE` abbiano `placement = "section_b"`
   (esclusi da rail standard).

**File:** `trade_chart_payload.py`

**Dipendenze:** Step 2.

---

### Step 5 — Aggiornamento `html_writer.py`: event list con Section A/B

**Obiettivo:** implementare la event list divisa in sezione A e B con `state_delta_essential`.

**Azioni:**

1. Rinominare/ristrutturare `_build_event_rail_and_sidebar` per separare Section A e B.

2. Struttura card event list (Sezione A):
   - header: `display_label` + timestamp + source + piccolo badge impatto
   - corpo espandibile: price_anchor, summary, `state_delta_essential`, raw_text (collassato)
   - azioni: `[Original message]` (se trader), `[AUDIT]`

3. Struttura card event list (Sezione B):
   - stile diverso (dimmed / muted)
   - header: label + timestamp + reason
   - azione: `[AUDIT]`

4. Implementare bottone `AUDIT` per-evento che:
   - apre l'audit drawer per quell'evento specifico
   - non apre un drawer globale

5. Aggiungere CSS per Sezione A / Sezione B.

6. Aggiungere JS: `openAuditDrawer(eventId)` che apre il drawer per l'evento corretto.

**File:** `html_writer.py`

**Dipendenze:** Step 2.

---

### Step 6 — Aggiornamento `html_writer.py`: audit drawer per-evento

**Obiettivo:** implementare l'audit drawer per-evento con la struttura PRD §7-8.

**Azioni:**

1. Cambiare il modello da `<details>` globale a:
   - drawer per-evento (elemento `<dialog>` o div con overlay)
   - aperto solo dal bottone `AUDIT` della event list

2. Struttura interna audit drawer (PRD §8):
   - **Execution summary**: evento, motivo, effetto posizione, prezzo/livello, outcome
   - **Readable state delta**: `state_delta_full` in formato leggibile (non JSON grezzo)
   - **Structured event data**: campi canonici minimi (PRD §8.3)
   - **Original trader message**: se disponibile
   - **Raw technical data**: payload engine/simulator in sotto-toggle

3. Implementare JS:
   - `openAuditDrawer(eventId)` → apre drawer per quell'evento
   - `closeAuditDrawer()` → chiude drawer
   - drawer NON si apre da click su rail o chart

**File:** `html_writer.py`

**Dipendenze:** Step 5.

---

### Step 7 — Aggiornamento `trade_chart_echarts.py`: rail e sincronizzazione

**Obiettivo:** allineare rail e sincronizzazione UX al PRD §8.5.

**Azioni:**

1. Filtrare la rail: mostrare solo eventi `event_list_section = "A"`.
   `IGNORED` e `SYSTEM_NOTE` (Section B) non devono entrare nella rail.

2. Aggiornare `buildPriceEvents()`:
   - mostrare marker solo per `chart_marker_kind = "REQUIRED"` (e opzionale per `OPTIONAL_LIGHT`)
   - escludere eventi con `chart_marker_kind = "NONE"`

3. Click su marker chart → dispatch `trade-event-focus` (già presente) → scroll event list.
   **Non** aprire direttamente l'audit drawer.

4. Click su rail → dispatch `trade-event-focus` → scroll event list.
   **Non** aprire direttamente l'audit drawer.

5. Verificare che la sincronizzazione sidebar ↔ chart ↔ rail funzioni
   per tutti gli event_code.

**File:** `trade_chart_echarts.py`

**Dipendenze:** Step 4.

---

### Step 8 — Test di copertura

**Obiettivo:** verificare tutti i Requisiti Funzionali e i Criteri di Accettazione PRD §16.

**Test da aggiungere / aggiornare:**

| Test | File | PRD |
|---|---|---|
| Mapping completo raw → event_code per tutti i 17 event_code | `test_event_normalizer.py` | §7.2 |
| Stage CANCEL: open_size==0 → ENTRY | `test_event_normalizer.py` | §12 |
| Stage CANCEL: open_size>0 → MANAGEMENT | `test_event_normalizer.py` | §12 |
| Ordine deterministico setup+fill stesso timestamp | `test_event_normalizer.py` | §13.2 |
| Ordine deterministico TP+BE stesso timestamp | `test_event_normalizer.py` | §13.2 |
| `state_delta_full` prodotto correttamente | `test_event_normalizer.py` | §11 |
| `state_delta_essential` derivato da `state_delta_full` | `test_event_normalizer.py` | §11 |
| `chart_marker_kind` = REQUIRED per ENTRY_FILLED_INITIAL | `test_event_normalizer.py` | §9 |
| `chart_marker_kind` = NONE per SETUP_CREATED | `test_event_normalizer.py` | §9 |
| `event_list_section` = A per SETUP_CREATED | `test_event_normalizer.py` | §5 |
| `event_list_section` = B per IGNORED | `test_event_normalizer.py` | §5 |
| Payload chart contiene event_code e chart_marker_kind | `test_runner_trade_chart_context.py` | §14.4 |
| STOP_MOVED non genera marker chart | `test_runner_trade_chart_context.py` | RF-4 |
| ENTRY_ORDER_ADDED non genera marker chart | `test_runner_trade_chart_context.py` | RF-2 |

**File:** `test_event_normalizer.py`, `test_runner_trade_chart_context.py`

**Dipendenze:** Step 1-7.

---

## Ordine di sviluppo raccomandato

```
Step 1  Tassonomia event_code            event_normalizer.py
Step 2  Campi canonici PRD §6            event_normalizer.py
Step 3  Ordinamento deterministico       event_normalizer.py
Step 4  Payload chart allineato          trade_chart_payload.py
Step 5  Event list Section A/B           html_writer.py
Step 6  Audit drawer per-evento          html_writer.py
Step 7  Rail + sincronizzazione UX       trade_chart_echarts.py
Step 8  Test di copertura                test_event_normalizer.py, test_runner_*
```

**Non saltare step. Non iniziare Step 4 prima che Step 1-3 abbiano test verdi.**

---

## Vincoli e regole

- Non modificare `src/storage/` o `src/core/`.
- Non toccare il simulatore o il dominio (`src/signal_chain_lab/domain/`).
- Non mischiare responsabilità: il normalizer produce il canonico, il payload builder lo consuma.
- La UI (chart JS) deve essere renderer, non interprete di business logic.
- I delta `state_delta_essential` devono essere derivati automaticamente da `state_delta_full`,
  non costruiti manualmente evento per evento.
- L'audit drawer NON si apre da click su rail o chart.

---

## Rischi aperti

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Backward compat con consumer esterni che leggono `subtype` | Alto | Mantenere campo `subtype` come alias di `event_code` durante la migrazione |
| `state_delta_full` richiede `state_before` affidabile da engine | Medio | Verificare che tutti i `EventLogEntry` abbiano `state_before` popolato |
| Audit drawer per-evento richiede refactoring JS non banale | Medio | Usare `<dialog>` nativo HTML per semplicità |
| Il test suite esistente usa vecchi nomi `Subtype` | Basso | Aggiornare contestualmente ai test |
| MARKET_ENTRY_FILLED non ha entry pending da interrompere | Basso | `geometry_effect = ACTIVATE_FILLED_ENTRY` senza linea pending da chiudere |
