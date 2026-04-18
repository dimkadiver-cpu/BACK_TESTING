# Checklist lavoro svolto — Single Trade Report

> Aggiornare questa checklist a ogni sessione di lavoro.
> Per ogni item: `[ ]` = da fare, `[x]` = completato, `[~]` = parziale / in corso.

---

## Step 1 — Tassonomia `event_code` (`event_normalizer.py`)

- [x] Rinominare costanti `Subtype` → nuovi `event_code` PRD
- [x] Aggiornare `_SUBTYPE_TITLE` con nuovi nomi
- [x] Aggiornare `_VISUAL_COLOR_KEY` con nuovi nomi
- [x] Aggiornare `_derive_subtype_phase_class`:
  - [x] `CLOSE_PARTIAL` + reason TP → `EXIT_PARTIAL_TP`
  - [x] `CLOSE_PARTIAL` senza reason TP → `EXIT_PARTIAL_MANUAL`
  - [x] `CLOSE_FULL` + reason TP → `EXIT_FINAL_TP`
  - [x] `CLOSE_FULL` + reason SL → `EXIT_FINAL_SL`
  - [x] `CLOSE_FULL` + reason manual → `EXIT_FINAL_MANUAL`
  - [x] `CLOSE_FULL` + reason timeout → `EXIT_FINAL_TIMEOUT`
  - [x] `CANCEL_PENDING` + source trader → `PENDING_CANCELLED_TRADER`
  - [x] `CANCEL_PENDING` + source engine → `PENDING_CANCELLED_ENGINE`
  - [x] `CANCEL_PENDING` + reason timeout → `PENDING_TIMEOUT`
- [x] Rinominare `Phase.SETUP` → `ENTRY` (SETUP_CREATED ha stage ENTRY nel PRD)
- [x] Aggiornare test `test_event_normalizer.py` con nuovi nomi
- [~] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 2 — Campi canonici PRD §6 (`event_normalizer.py`)

- [x] Aggiungere campo `event_code` a `ReportCanonicalEvent`
- [x] Aggiungere campo `stage` (ENTRY/MANAGEMENT/EXIT)
- [x] Aggiungere campo `position_effect`
- [x] Aggiungere campo `display_group`
- [x] Aggiungere campo `display_label` (con fallback da `event_code`)
- [x] Aggiungere campo `event_list_section` ("A" o "B")
- [x] Aggiungere campo `chart_marker_kind` (REQUIRED/OPTIONAL_LIGHT/NONE)
- [x] Aggiungere campo `geometry_effect`
- [x] Aggiungere campo `state_delta_full` (lista con schema PRD §11.2)
- [x] Aggiungere campo `state_delta_essential` (derivato da `state_delta_full`)
- [x] Aggiungere campo `raw_event_ref`
- [x] Implementare `_build_state_delta_full(before, after)`
- [x] Implementare `_derive_state_delta_essential(delta_full)`
- [x] Implementare `_build_position_effect(event_code, state_before, state_after)`
- [x] Implementare `_build_geometry_effect(event_code)` dalla matrice PRD §15.2
- [x] Implementare `_build_chart_marker_kind(event_code)` dalla matrice PRD §9
- [x] Implementare `_build_event_list_section(event_code)` → A o B
- [x] Implementare logica stage CANCEL/TIMEOUT (PRD §12): legge `open_size` da `state_before`
- [x] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 3 — Ordinamento deterministico multi-evento (`event_normalizer.py`)

- [x] Aggiornare funzione sort in `normalize_events` con priorità PRD §13.2
- [x] Caso setup market-fill: `SETUP_CREATED` prima di `ENTRY_FILLED_INITIAL`
- [x] Caso TP + BE: `EXIT_PARTIAL_TP` prima di `BREAK_EVEN_ACTIVATED`
- [x] Aggiungere test: multi-evento stesso timestamp (setup+fill)
- [x] Aggiungere test: multi-evento stesso timestamp (TP+BE)
- [x] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 4 — Payload chart allineato (`trade_chart_payload.py`)

- [x] Aggiornare `_EVENT_KIND_MAP` con nuovi `event_code`
- [x] In `_build_events`: aggiungere `event_code` al dict evento
- [x] In `_build_events`: aggiungere `chart_marker_kind` al dict evento
- [x] In `_build_events`: aggiungere `geometry_effect` al dict evento
- [x] In `_build_events`: aggiungere `event_list_section` al dict evento
- [x] In `_build_events`: aggiungere `position_effect` al dict evento
- [x] In `_build_events`: aggiungere `state_delta_essential` al dict evento
- [x] Logica placement: `chart_marker_kind=NONE` → `placement="rail"` (no marker chart)
- [x] Verificare `STOP_MOVED` → `placement="rail"` (nessun marker chart)
- [x] Verificare `BREAK_EVEN_ACTIVATED` → `placement="rail"` (nessun marker chart)
- [x] Verificare `SETUP_CREATED` → `placement="rail"` (nessun marker chart)
- [x] Verificare `ENTRY_ORDER_ADDED` → `placement="rail"` (nessun marker chart)
- [x] Verificare `IGNORED` / `SYSTEM_NOTE` → `placement="section_b"` (fuori rail standard)
- [~] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 5 — Event list Section A/B (`html_writer.py`)

- [x] Separare la event list in Sezione A e Sezione B
- [~] Card Sezione A — struttura chiusa:
  - [ ] `display_label` + timestamp + source + badge impatto
  - [x] bottone `[AUDIT]` per-evento
- [~] Card Sezione A — struttura aperta:
  - [x] prezzo/livello rilevante
  - [x] summary
  - [~] `state_delta_essential` leggibile
  - [x] raw text collassato (se source=TRADER)
  - [x] azioni: `[Original message]` + `[AUDIT]`
- [x] Card Sezione B — struttura:
  - [x] stile muted/dimmed
  - [x] label + timestamp + reason
  - [x] bottone `[AUDIT]`
- [x] Aggiungere CSS per Sezione A / Sezione B
- [x] Aggiungere JS: `openAuditDrawer(eventId)` collegato al bottone AUDIT
- [~] Verifica visiva HTML generato

---

## Step 6 — Audit drawer per-evento (`html_writer.py`)

- [x] Rimuovere audit drawer globale `<details>`
- [x] Implementare drawer per-evento (es. `<dialog>` HTML nativo)
- [x] Drawer aperto SOLO da bottone `[AUDIT]` in event list
- [~] Struttura interna drawer:
  - [x] Sezione "Execution summary" (evento, motivo, effetto, prezzo, outcome)
  - [~] Sezione "Readable state delta" (`state_delta_full` formattato, non JSON grezzo)
  - [x] Sezione "Structured event data" (campi canonici PRD §8.3)
  - [x] Sezione "Original trader message" (se disponibile)
  - [x] Sezione "Raw technical data" (in sotto-toggle)
- [x] JS: `openAuditDrawer(eventId)` e `closeAuditDrawer()`
- [x] Verifica: click su rail/chart NON apre audit drawer
- [x] Verifica: click su `[AUDIT]` apre drawer per l'evento corretto

---

## Step 7 — Rail e sincronizzazione UX (`trade_chart_echarts.py`)

- [x] Rail: filtrare a solo `event_list_section = "A"` (no IGNORED/SYSTEM_NOTE)
- [x] Chart marker: mostrare solo `chart_marker_kind = "REQUIRED"` (e opzionale OPTIONAL_LIGHT)
- [x] Escludere dal chart marker gli eventi con `chart_marker_kind = "NONE"`
- [x] Click su marker chart → `trade-event-focus` → scroll event list (NON apre audit)
- [x] Click su rail → `trade-event-focus` → scroll event list (NON apre audit)
- [~] Verifica sincronizzazione chart ↔ rail ↔ event list
- [x] Verifica: STOP_MOVED non genera marker chart
- [x] Verifica: BREAK_EVEN_ACTIVATED non genera marker chart
- [x] Verifica: SETUP_CREATED non genera marker chart
- [x] Verifica: ENTRY_FILLED_INITIAL genera marker forte

---

## Step 8 — Test di copertura

- [x] Mapping completo raw → event_code per tutti i 17 event_code PRD
- [x] Stage CANCEL: open_size==0 → ENTRY
- [x] Stage CANCEL: open_size>0 → MANAGEMENT
- [x] Ordine deterministico: setup+fill stesso timestamp
- [x] Ordine deterministico: TP+BE stesso timestamp
- [x] `state_delta_full` prodotto correttamente
- [x] `state_delta_essential` derivato da `state_delta_full`
- [x] `chart_marker_kind = REQUIRED` per ENTRY_FILLED_INITIAL
- [x] `chart_marker_kind = NONE` per SETUP_CREATED
- [x] `chart_marker_kind = NONE` per STOP_MOVED
- [x] `chart_marker_kind = NONE` per BREAK_EVEN_ACTIVATED
- [x] `event_list_section = A` per SETUP_CREATED
- [x] `event_list_section = B` per IGNORED
- [x] `event_list_section = B` per SYSTEM_NOTE
- [x] Payload chart contiene `event_code` e `chart_marker_kind`
- [x] STOP_MOVED non genera marker chart nel payload
- [x] ENTRY_ORDER_ADDED non genera marker chart nel payload

---

## Criteri di accettazione (PRD §16)

- [~] RF-1: un solo sistema semantico per chart, rail, event list, audit
- [x] RF-2: `ENTRY_ORDER_ADDED` non mostrato come fill reale
- [x] RF-3: fill iniziale e scale-in distinguibili
- [x] RF-4: `STOP_MOVED` e `BREAK_EVEN_ACTIVATED` cambiano geometria senza marker
- [x] RF-5: `PENDING_CANCELLED_*` e `PENDING_TIMEOUT` usano ENTRY/MANAGEMENT
- [ ] RF-6: event list mostra `state_delta_essential`, audit mostra `state_delta_full`
- [x] RF-7: audit drawer si apre solo dalla event list
- [x] RF-8: nessun marker per SETUP_CREATED, ENTRY_ORDER_ADDED, IGNORED, SYSTEM_NOTE,
           STOP_MOVED, BREAK_EVEN_ACTIVATED
- [ ] RF-9: linea entry pending si interrompe nel punto del fill
- [ ] RF-10: Average Entry line compare dal secondo fill in poi

---

## Scenario di test end-to-end

Trade di riferimento per validazione manuale:

1. `SETUP_CREATED` → rail sì, chart no, event list A
2. `ENTRY_ORDER_ADDED` → rail sì, chart no, event list A
3. `ENTRY_FILLED_INITIAL` → rail sì, chart marker forte, event list A, linea pending interrotta
4. `STOP_MOVED` → rail sì, chart solo geometria linea, event list A
5. `EXIT_PARTIAL_TP` → rail sì, chart marker forte, event list A
6. `BREAK_EVEN_ACTIVATED` → rail sì, chart solo geometria, event list A
7. `EXIT_FINAL_SL` → rail sì, chart marker forte, event list A, tutte linee chiuse
8. `IGNORED` → rail no, chart no, event list B

Verifica complessiva:
- [~] Storia coerente e non contraddittoria in tutti i livelli
- [x] Pending cancel senza posizione → ENTRY (non EXIT)
- [x] Pending cancel con posizione → MANAGEMENT (non EXIT)
- [x] Click su rail → scroll event list (non audit)
- [x] Click su chart → scroll event list (non audit)
- [x] Click su AUDIT → apre drawer corretto

---

## Note di sessione

<!-- Aggiungere note libere per ogni sessione di lavoro -->

### 2026-04-17
- Analisi completa dei 4 doc PRD e codebase attuale.
- Creati `PIANO_IMPLEMENTAZIONE.md` e `CHECKLIST.md`.
- Gap principali identificati: tassonomia event_code, campi canonici mancanti,
  stage CANCEL/TIMEOUT errato, event list non divisa A/B, audit drawer globale
  invece di per-evento.
- Nessun codice modificato questa sessione.

### 2026-04-17 — verifica stato implementazione
- Verificato lo stato reale della codebase rispetto a `PIANO_IMPLEMENTAZIONE.md`.
- Step 1, 4, 5, 6, 7 risultano implementati in codice.
- Step 2 risulta parziale: presenti `event_code`, `stage`, `position_effect`,
  `event_list_section`, `chart_marker_kind`, `geometry_effect`, ma mancano
  `display_group`, `display_label`, `state_delta_full`, `raw_event_ref` e la
  derivazione reale di `state_delta_essential`.
- Eseguiti test:
  - `pytest src/signal_chain_lab/policy_report/tests -q` → 91 pass, 1 fail
    (`test_deterministic_order_tp_before_be_same_timestamp`)
  - `pytest tests/unit/test_reporting_delta_a.py -q` → 3 pass

### 2026-04-17 — completamento Step 2
- Completato Step 2 in `event_normalizer.py`.
- Aggiunti a `ReportCanonicalEvent`: `display_group`, `display_label`,
  `state_delta_full`, `raw_event_ref`.
- Implementati `_build_state_delta_full`, `_derive_state_delta_essential`,
  `_build_position_effect`, `_build_geometry_effect`,
  `_build_chart_marker_kind`, `_build_event_list_section`.
- `html_writer.py` aggiornato per mostrare `state_delta_full` nell'audit drawer
  e usare `display_label` quando disponibile.
- `trade_chart_payload.py` aggiornato per esporre `display_label` come `label`
  quando presente.
- Corretto anche l'ordinamento TP+BE a pari timestamp, portando a verde lo Step 3.
- Eseguiti test:
  - `pytest src/signal_chain_lab/policy_report/tests -q` → 96 pass
  - `pytest src/signal_chain_lab/policy_report/tests/test_runner_trade_chart_context.py -q` → 13 pass
  - `pytest tests/unit/test_reporting_delta_a.py -q` → 3 pass

### 2026-04-17 — chiusura fase 3
- Allineato `PIANO_IMPLEMENTAZIONE.md` allo stato reale: Step 2 e Step 3 marcati
  come completati.
- Chiusura fase 3 confermata lato codice e test.
- Prossimo fronte aperto: Step 8, copertura test residua PRD §16.

### 2026-04-17 — chiusura Step 8
- Aggiunto test payload per `ENTRY_ORDER_ADDED` senza marker chart nel payload finale.
- Step 8 completato: tutti gli item del blocco "Test di copertura" risultano chiusi.
- Eseguiti test:
  - `pytest src/signal_chain_lab/policy_report/tests/test_runner_trade_chart_context.py -q` → 14 pass
  - `pytest src/signal_chain_lab/policy_report/tests -q` → 97 pass
