# PRD — Fix Problema 3: mapping fragile tra `entries_planned` e `fills`

## 1. Titolo

**Fix del bug logico nel simulatore relativo alla selezione delle entry ancora pendenti (`_try_fill_pending_entries`)**

---

## 2. Contesto

Nel simulatore del progetto `BACK_TESTING`, la funzione `_try_fill_pending_entries()` decide quali `EntryPlan` siano ancora pendenti usando una logica implicita basata sulla posizione nella lista:

```python
pending_plans = [
    plan for index, plan in enumerate(state.entries_planned)
    if index >= len(state.fills) and (plan.price is not None or plan.order_type == "market")
]
```

Questa scelta assume che:

1. i fill avvengano nello stesso ordine di `entries_planned`
2. il numero di fill corrisponda sempre al numero di piani già consumati
3. il rapporto tra `EntryPlan` e `FillRecord` possa essere ricostruito solo dal conteggio

Queste assunzioni non sono robuste quando il sistema supporta `ADD_ENTRY` o, più in generale, quando una entry aggiunta successivamente può fillare prima di una entry più vecchia ancora pendente.

---

## 3. Problema

### 3.1 Descrizione del bug

Il bug nasce dal fatto che il motore non traccia **quale entry specifica** sia stata fillata, ma solo **quanti fill** sono avvenuti.

Di conseguenza, se una nuova entry aggiunta con `ADD_ENTRY` viene eseguita prima di una entry più vecchia ancora aperta, il conteggio `len(state.fills)` può far “sparire” dalla selezione una entry che in realtà non è mai stata eseguita.

### 3.2 Scenario concreto

Caso esempio:

- `E1 = 100`
- `E2 = 90`
- prima candela: fill di `E1`, `E2` resta pendente
- arriva `ADD_ENTRY`, che aggiunge `E3 = 98`
- seconda candela: fill di `E3`, `E2` ancora no
- ora `len(state.fills) == 2`
- la selezione `index >= len(state.fills)` esclude `E2` perché il suo indice è `1`
- `E2` resta non fillata ma non verrà più rivalutata

Questo produce una corruzione silenziosa del comportamento simulato.

---

## 4. Obiettivo

Eliminare la dipendenza dalla posizione nella lista e introdurre un legame esplicito e stabile tra:

- piano di entry (`EntryPlan`)
- fill risultante (`FillRecord`)

Il simulatore deve determinare le entry ancora pendenti sulla base di una relazione diretta “questo piano è già stato fillato / non è stato fillato”, non tramite il conteggio dei fill.

---

## 5. Non obiettivi

Questa revisione **non** introduce:

- partial fill model
- gestione quantitativa residua per singola entry
- order book simulation
- refactor completo del fill model
- modifica della logica economica di PnL

Il fix deve essere **mirato**, con impatto minimo e comportamento economico invariato rispetto all’attuale modello all-or-nothing.

---

## 6. Root cause tecnica

### 6.1 Stato attuale del modello dati

`TradeState` mantiene:

- `entries_planned: list[EntryPlan]`
- `fills: list[FillRecord]`

Ma attualmente:

- `EntryPlan` non ha un identificatore univoco persistente
- `FillRecord` non punta a uno specifico `EntryPlan`
- `_try_fill_pending_entries()` usa una relazione implicita basata sull’indice

### 6.2 Perché `source_event_sequence` non basta

`FillRecord` contiene `source_event_sequence`, ma non è sufficiente per identificare univocamente una entry.

Motivo:

- tutte le entry create da `OPEN_SIGNAL` possono condividere la stessa `event.sequence`
- quindi due o più entry iniziali possono avere lo stesso riferimento di origine
- serve un identificatore specifico per il singolo piano

---

## 7. Soluzione proposta

### 7.1 Principio

Ogni `EntryPlan` deve avere un `plan_id` univoco e deterministico.

Ogni `FillRecord` generato dal fill di un piano deve riportare lo stesso `plan_id`.

La funzione `_try_fill_pending_entries()` deve selezionare come pendenti i soli piani il cui `plan_id` **non compare** tra i fill già registrati.

---

## 8. Requisiti funzionali

### RF-1 — Identificatore univoco per ogni entry plan

Il sistema deve introdurre un campo `plan_id: str` su `EntryPlan`.

### RF-2 — Tracciamento del piano originario nel fill

Il sistema deve introdurre un campo `plan_id: str | None = None` su `FillRecord`.

### RF-3 — Generazione deterministica del `plan_id`

Il `plan_id` deve essere generato in modo deterministico e leggibile.

Formato consigliato:

```text
{signal_id}:{event.sequence}:E{ordinal}
```

Esempi:

- `btc_001:10:E1`
- `btc_001:10:E2`
- `btc_001:45:E3`

### RF-4 — Selezione corretta delle pending entries

La funzione `_try_fill_pending_entries()` non deve più usare `index >= len(state.fills)`.

Deve invece:

1. costruire l’insieme dei `plan_id` già fillati
2. considerare pendenti i soli `EntryPlan` con `plan_id` assente in tale insieme

### RF-5 — Conservazione del `plan_id` al momento del fill

Quando un piano viene eseguito, il `FillRecord` prodotto deve essere aggiornato con il `plan_id` del piano che ha generato quel fill.

### RF-6 — Compatibilità con `ADD_ENTRY`

Le entry aggiunte via `ADD_ENTRY` devono ricevere `plan_id` univoco senza collidere con quelli già esistenti.

---

## 9. Requisiti non funzionali

### RNF-1 — Determinismo

La generazione dei `plan_id` non deve introdurre casualità.

Non usare UUID random.

### RNF-2 — Basso impatto

La patch deve modificare solo:

- modello dati di trade state
- creazione `EntryPlan`
- creazione/propagazione `FillRecord`
- selezione dei pending plans

### RNF-3 — Nessuna modifica al PnL

Il fix non deve cambiare:

- formula di PnL
- fee
- slippage
- timeout
- logica TP/SL

### RNF-4 — Retrocompatibilità interna ragionevole

Dove possibile, aggiungere il nuovo campo senza rompere serializzazione, snapshot e log esistenti.

---

## 10. Modifiche richieste per file

## 10.1 `src/signal_chain_lab/domain/trade_state.py`

### Modifiche

Aggiungere:

```python
class EntryPlan(BaseModel):
    plan_id: str
    ...

class FillRecord(BaseModel):
    plan_id: str | None = None
    ...
```

### Motivazione

Serve una relazione esplicita piano ↔ fill.

---

## 10.2 `src/signal_chain_lab/engine/state_machine.py`

### Modifiche

#### In `_apply_open_signal`
Ogni entry iniziale deve ricevere un `plan_id` deterministico.

#### In `ADD_ENTRY`
Ogni entry aggiunta deve ricevere un nuovo `plan_id` coerente con le entry già presenti.

### Helper consigliato

```python
def _next_plan_id(state: TradeState, event: CanonicalEvent) -> str:
    ordinal = len(state.entries_planned) + 1
    return f"{event.signal_id}:{event.sequence}:E{ordinal}"
```

### Nota

Il campo `label` può restare separato da `plan_id`. `label` serve a leggibilità, `plan_id` a identità tecnica.

---

## 10.3 `src/signal_chain_lab/engine/simulator.py`

### Modifiche

#### Da rimuovere

La logica basata su:

```python
index >= len(state.fills)
```

#### Da introdurre

Una logica del tipo:

```python
filled_plan_ids = {
    fill.plan_id
    for fill in state.fills
    if fill.plan_id is not None
}

pending_plans = [
    plan
    for plan in state.entries_planned
    if plan.plan_id not in filled_plan_ids
    and (plan.price is not None or plan.order_type == "market")
]
```

#### Al momento del fill

Dopo la generazione del `FillRecord`, associare il piano:

```python
fill = fill.model_copy(update={"plan_id": plan.plan_id})
```

---

## 11. Criteri di accettazione

Il fix è accettato se tutti i seguenti criteri sono veri.

### CA-1
Una entry iniziale più vecchia non deve essere persa dopo il fill di una entry aggiunta successivamente.

### CA-2
Il sistema deve consentire fill fuori ordine rispetto alla posizione in `entries_planned`.

### CA-3
Ogni `FillRecord` deve riportare il `plan_id` corretto del piano eseguito.

### CA-4
I `plan_id` devono essere univoci all’interno della chain.

### CA-5
I risultati economici del simulatore devono restare invariati in tutti i casi in cui l’ordine dei fill coincida già con l’ordine dei piani.

---

## 12. Test di regressione richiesti

## 12.1 Test principale — bug reale

### Nome suggerito

```python
def test_add_entry_fill_does_not_hide_older_pending_plan():
```

### Scenario

- `OPEN_SIGNAL` con 2 entry: `E1`, `E2`
- fill di `E1`
- `ADD_ENTRY` crea `E3`
- fill di `E3`
- candela successiva tocca `E2`

### Atteso

`E2` deve ancora poter essere fillata.

### Assert minimo

- `len(state.fills) == 3`
- ordine dei `plan_id` nei fill coerente con i trigger reali, non con l’indice in lista

---

## 12.2 Test unicità `plan_id`

### Nome suggerito

```python
def test_open_signal_assigns_unique_deterministic_plan_ids():
```

### Atteso

- nessuna collisione tra `plan_id`
- formato stabile e deterministico

---

## 12.3 Test propagazione `plan_id` nel fill

### Nome suggerito

```python
def test_fill_record_carries_plan_id_of_filled_entry():
```

### Atteso

- il fill riporta il `plan_id` della entry eseguita

---

## 12.4 Test non regressione sul caso semplice

### Nome suggerito

```python
def test_sequential_fill_order_behaviour_remains_unchanged():
```

### Atteso

In un caso lineare senza `ADD_ENTRY`, il comportamento deve restare invariato rispetto a prima.

---

## 13. Rischi residui

### 13.1 Partial fill futuri

Questo fix risolve il problema nel modello attuale “un piano = fill completo”.

Se in futuro verranno introdotti partial fill, servirà estendere il modello con concetti come:

- quantità residua per piano
- stato del piano (`PENDING`, `PARTIAL`, `FILLED`, `CANCELLED`)
- possibile pluralità di fill per lo stesso `plan_id`

### 13.2 Log storici o snapshot preesistenti

Se esistono test o serializzazioni che assumono l’assenza del campo `plan_id`, potrebbero richiedere aggiornamento.

---

## 14. Strategia di implementazione consigliata

### Fase 1 — Modello dati

- aggiungere `plan_id` a `EntryPlan`
- aggiungere `plan_id` a `FillRecord`

### Fase 2 — Creazione piani

- assegnare `plan_id` in `OPEN_SIGNAL`
- assegnare `plan_id` in `ADD_ENTRY`

### Fase 3 — Fill engine

- sostituire la selezione per indice con selezione per `plan_id`
- propagare `plan_id` al fill

### Fase 4 — Test

- aggiungere test di regressione
- verificare non regressione nei casi lineari

---

## 15. Definition of Done

Il lavoro è completato quando:

1. il codice non usa più `index >= len(state.fills)` per identificare i pending plans
2. ogni `EntryPlan` ha un `plan_id`
3. ogni `FillRecord` derivato da un piano riporta il `plan_id`
4. il bug con `ADD_ENTRY` è coperto da test automatico
5. i test esistenti continuano a passare
6. non ci sono cambiamenti inattesi nel PnL dei casi lineari già validi

---

## 16. Prompt breve per implementazione

```text
Fix the fragile entry-to-fill mapping in the simulator.

Problem:
_try_fill_pending_entries() currently decides which entry plans are still pending using index >= len(state.fills). This is incorrect when ADD_ENTRY appends a new plan and that newer plan fills before an older still-unfilled plan.

Required changes:
1. Add plan_id: str to EntryPlan.
2. Add plan_id: str | None = None to FillRecord.
3. Generate deterministic plan_id for OPEN_SIGNAL entries and ADD_ENTRY entries.
4. Replace index-based pending selection with plan_id-based selection.
5. When a fill occurs, copy the EntryPlan.plan_id into FillRecord.plan_id.
6. Add regression tests covering out-of-order fills caused by ADD_ENTRY.

Do not change PnL logic, fee logic, TP/SL logic, or timeout behavior.
```

