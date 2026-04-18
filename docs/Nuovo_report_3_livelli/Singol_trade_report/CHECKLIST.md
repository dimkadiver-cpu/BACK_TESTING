# Checklist lavoro svolto — Single Trade Report

> Aggiornare questa checklist a ogni sessione di lavoro.
> Per ogni item: `[ ]` = da fare, `[x]` = completato, `[~]` = parziale / in corso.

---

## Step 1 — Tassonomia `event_code` (`event_normalizer.py`)

- [ ] Rinominare costanti `Subtype` → nuovi `event_code` PRD
- [ ] Aggiornare `_SUBTYPE_TITLE` con nuovi nomi
- [ ] Aggiornare `_VISUAL_COLOR_KEY` con nuovi nomi
- [ ] Aggiornare `_derive_subtype_phase_class`:
  - [ ] `CLOSE_PARTIAL` + reason TP → `EXIT_PARTIAL_TP`
  - [ ] `CLOSE_PARTIAL` senza reason TP → `EXIT_PARTIAL_MANUAL`
  - [ ] `CLOSE_FULL` + reason TP → `EXIT_FINAL_TP`
  - [ ] `CLOSE_FULL` + reason SL → `EXIT_FINAL_SL`
  - [ ] `CLOSE_FULL` + reason manual → `EXIT_FINAL_MANUAL`
  - [ ] `CLOSE_FULL` + reason timeout → `EXIT_FINAL_TIMEOUT`
  - [ ] `CANCEL_PENDING` + source trader → `PENDING_CANCELLED_TRADER`
  - [ ] `CANCEL_PENDING` + source engine → `PENDING_CANCELLED_ENGINE`
  - [ ] `CANCEL_PENDING` + reason timeout → `PENDING_TIMEOUT`
- [ ] Rinominare `Phase.SETUP` → `ENTRY` (SETUP_CREATED ha stage ENTRY nel PRD)
- [ ] Aggiornare test `test_event_normalizer.py` con nuovi nomi
- [ ] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 2 — Campi canonici PRD §6 (`event_normalizer.py`)

- [ ] Aggiungere campo `event_code` a `ReportCanonicalEvent`
- [ ] Aggiungere campo `stage` (ENTRY/MANAGEMENT/EXIT)
- [ ] Aggiungere campo `position_effect`
- [ ] Aggiungere campo `display_group`
- [ ] Aggiungere campo `display_label` (con fallback da `event_code`)
- [ ] Aggiungere campo `event_list_section` ("A" o "B")
- [ ] Aggiungere campo `chart_marker_kind` (REQUIRED/OPTIONAL_LIGHT/NONE)
- [ ] Aggiungere campo `geometry_effect`
- [ ] Aggiungere campo `state_delta_full` (lista con schema PRD §11.2)
- [ ] Aggiungere campo `state_delta_essential` (derivato da `state_delta_full`)
- [ ] Aggiungere campo `raw_event_ref`
- [ ] Implementare `_build_state_delta_full(before, after)`
- [ ] Implementare `_derive_state_delta_essential(delta_full)`
- [ ] Implementare `_build_position_effect(event_code, state_before, state_after)`
- [ ] Implementare `_build_geometry_effect(event_code)` dalla matrice PRD §15.2
- [ ] Implementare `_build_chart_marker_kind(event_code)` dalla matrice PRD §9
- [ ] Implementare `_build_event_list_section(event_code)` → A o B
- [ ] Implementare logica stage CANCEL/TIMEOUT (PRD §12): legge `open_size` da `state_before`
- [ ] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 3 — Ordinamento deterministico multi-evento (`event_normalizer.py`)

- [ ] Aggiornare funzione sort in `normalize_events` con priorità PRD §13.2
- [ ] Caso setup market-fill: `SETUP_CREATED` prima di `ENTRY_FILLED_INITIAL`
- [ ] Caso TP + BE: `EXIT_PARTIAL_TP` prima di `BREAK_EVEN_ACTIVATED`
- [ ] Aggiungere test: multi-evento stesso timestamp (setup+fill)
- [ ] Aggiungere test: multi-evento stesso timestamp (TP+BE)
- [ ] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 4 — Payload chart allineato (`trade_chart_payload.py`)

- [ ] Aggiornare `_EVENT_KIND_MAP` con nuovi `event_code`
- [ ] In `_build_events`: aggiungere `event_code` al dict evento
- [ ] In `_build_events`: aggiungere `chart_marker_kind` al dict evento
- [ ] In `_build_events`: aggiungere `geometry_effect` al dict evento
- [ ] In `_build_events`: aggiungere `event_list_section` al dict evento
- [ ] In `_build_events`: aggiungere `position_effect` al dict evento
- [ ] In `_build_events`: aggiungere `state_delta_essential` al dict evento
- [ ] Logica placement: `chart_marker_kind=NONE` → `placement="rail"` (no marker chart)
- [ ] Verificare `STOP_MOVED` → `placement="rail"` (nessun marker chart)
- [ ] Verificare `BREAK_EVEN_ACTIVATED` → `placement="rail"` (nessun marker chart)
- [ ] Verificare `SETUP_CREATED` → `placement="rail"` (nessun marker chart)
- [ ] Verificare `ENTRY_ORDER_ADDED` → `placement="rail"` (nessun marker chart)
- [ ] Verificare `IGNORED` / `SYSTEM_NOTE` → `placement="section_b"` (fuori rail standard)
- [ ] Verifica: `pytest src/signal_chain_lab/policy_report/tests/` verde

---

## Step 5 — Event list Section A/B (`html_writer.py`)

- [ ] Separare la event list in Sezione A e Sezione B
- [ ] Card Sezione A — struttura chiusa:
  - [ ] `display_label` + timestamp + source + badge impatto
  - [ ] bottone `[AUDIT]` per-evento
- [ ] Card Sezione A — struttura aperta:
  - [ ] prezzo/livello rilevante
  - [ ] summary
  - [ ] `state_delta_essential` leggibile
  - [ ] raw text collassato (se source=TRADER)
  - [ ] azioni: `[Original message]` + `[AUDIT]`
- [ ] Card Sezione B — struttura:
  - [ ] stile muted/dimmed
  - [ ] label + timestamp + reason
  - [ ] bottone `[AUDIT]`
- [ ] Aggiungere CSS per Sezione A / Sezione B
- [ ] Aggiungere JS: `openAuditDrawer(eventId)` collegato al bottone AUDIT
- [ ] Verifica visiva HTML generato

---

## Step 6 — Audit drawer per-evento (`html_writer.py`)

- [ ] Rimuovere audit drawer globale `<details>`
- [ ] Implementare drawer per-evento (es. `<dialog>` HTML nativo)
- [ ] Drawer aperto SOLO da bottone `[AUDIT]` in event list
- [ ] Struttura interna drawer:
  - [ ] Sezione "Execution summary" (evento, motivo, effetto, prezzo, outcome)
  - [ ] Sezione "Readable state delta" (`state_delta_full` formattato, non JSON grezzo)
  - [ ] Sezione "Structured event data" (campi canonici PRD §8.3)
  - [ ] Sezione "Original trader message" (se disponibile)
  - [ ] Sezione "Raw technical data" (in sotto-toggle)
- [ ] JS: `openAuditDrawer(eventId)` e `closeAuditDrawer()`
- [ ] Verifica: click su rail/chart NON apre audit drawer
- [ ] Verifica: click su `[AUDIT]` apre drawer per l'evento corretto

---

## Step 7 — Rail e sincronizzazione UX (`trade_chart_echarts.py`)

- [ ] Rail: filtrare a solo `event_list_section = "A"` (no IGNORED/SYSTEM_NOTE)
- [ ] Chart marker: mostrare solo `chart_marker_kind = "REQUIRED"` (e opzionale OPTIONAL_LIGHT)
- [ ] Escludere dal chart marker gli eventi con `chart_marker_kind = "NONE"`
- [ ] Click su marker chart → `trade-event-focus` → scroll event list (NON apre audit)
- [ ] Click su rail → `trade-event-focus` → scroll event list (NON apre audit)
- [ ] Verifica sincronizzazione chart ↔ rail ↔ event list
- [ ] Verifica: STOP_MOVED non genera marker chart
- [ ] Verifica: BREAK_EVEN_ACTIVATED non genera marker chart
- [ ] Verifica: SETUP_CREATED non genera marker chart
- [ ] Verifica: ENTRY_FILLED_INITIAL genera marker forte

---

## Step 8 — Test di copertura

- [ ] Mapping completo raw → event_code per tutti i 17 event_code PRD
- [ ] Stage CANCEL: open_size==0 → ENTRY
- [ ] Stage CANCEL: open_size>0 → MANAGEMENT
- [ ] Ordine deterministico: setup+fill stesso timestamp
- [ ] Ordine deterministico: TP+BE stesso timestamp
- [ ] `state_delta_full` prodotto correttamente
- [ ] `state_delta_essential` derivato da `state_delta_full`
- [ ] `chart_marker_kind = REQUIRED` per ENTRY_FILLED_INITIAL
- [ ] `chart_marker_kind = NONE` per SETUP_CREATED
- [ ] `chart_marker_kind = NONE` per STOP_MOVED
- [ ] `chart_marker_kind = NONE` per BREAK_EVEN_ACTIVATED
- [ ] `event_list_section = A` per SETUP_CREATED
- [ ] `event_list_section = B` per IGNORED
- [ ] `event_list_section = B` per SYSTEM_NOTE
- [ ] Payload chart contiene `event_code` e `chart_marker_kind`
- [ ] STOP_MOVED non genera marker chart nel payload
- [ ] ENTRY_ORDER_ADDED non genera marker chart nel payload

---

## Criteri di accettazione (PRD §16)

- [ ] RF-1: un solo sistema semantico per chart, rail, event list, audit
- [ ] RF-2: `ENTRY_ORDER_ADDED` non mostrato come fill reale
- [ ] RF-3: fill iniziale e scale-in distinguibili
- [ ] RF-4: `STOP_MOVED` e `BREAK_EVEN_ACTIVATED` cambiano geometria senza marker
- [ ] RF-5: `PENDING_CANCELLED_*` e `PENDING_TIMEOUT` usano ENTRY/MANAGEMENT
- [ ] RF-6: event list mostra `state_delta_essential`, audit mostra `state_delta_full`
- [ ] RF-7: audit drawer si apre solo dalla event list
- [ ] RF-8: nessun marker per SETUP_CREATED, ENTRY_ORDER_ADDED, IGNORED, SYSTEM_NOTE,
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
- [ ] Storia coerente e non contraddittoria in tutti i livelli
- [ ] Pending cancel senza posizione → ENTRY (non EXIT)
- [ ] Pending cancel con posizione → MANAGEMENT (non EXIT)
- [ ] Click su rail → scroll event list (non audit)
- [ ] Click su chart → scroll event list (non audit)
- [ ] Click su AUDIT → apre drawer corretto

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
