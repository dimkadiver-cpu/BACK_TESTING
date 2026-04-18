# Sidebar + Audit Drawer — proposta aggiornata definitiva

> Documento derivato dal PRD master:
> `PRD_definitivo_sistemazione_eventi_single_trade_report.md`
> In caso di conflitto prevale sempre il PRD master.

## 1. Decisioni definitive

### 1.1 Event list

La event list è il livello operativo leggibile.

Deve mostrare:

- eventi della sezione A con impatto sul trade;
- eventi della sezione B non operativi / audit;
- delta essenziali leggibili;
- accesso al raw text trader, se disponibile;
- pulsante `AUDIT`.

### 1.2 Audit drawer

L’audit drawer è il livello tecnico completo.

Deve mostrare:

- payload evento completo;
- `state_delta_full`;
- structured event data;
- reason / mapping;
- raw payload o raw technical data, se disponibili;
- raw text originario del trader, se presente.

### 1.3 Apertura audit

L’audit drawer si apre **solo** da:

- event list, tramite pulsante `AUDIT`.

Chart e rail possono sincronizzare la selezione, ma non devono aprire direttamente l’audit drawer.

### 1.4 Raw text originale del trader

Quando l’evento deriva da un messaggio trader, il raw text deve essere accessibile sia da:

- event list;
- audit drawer.

---

## 2. Distinzione finale tra Event List e Audit Drawer

### 2.1 Event List

La event list serve a leggere velocemente il trade.

Deve privilegiare:

- titolo evento;
- timestamp;
- source;
- summary breve;
- prezzo o riferimento operativo, se utile;
- delta essenziali;
- eventuale raw text breve;
- bottone `AUDIT`.

Non deve mostrare tutto il payload tecnico.

### 2.2 Audit Drawer

L’audit drawer serve a ispezionare il dettaglio tecnico.

Deve essere più completo, esplicito e verboso della event list.

### 2.3 Source of truth dei delta

Il sistema deve avere una sola fonte di verità:

- `state_delta_full`

Da questo devono essere derivati automaticamente:

- `state_delta_essential`

Uso:

- **Event List** → `state_delta_essential`
- **Audit Drawer** → `state_delta_full`

La UI non deve costruire manualmente i delta tramite logiche sparse.

---

## 3. Aperture e sincronizzazione

### 3.1 Event rail

Se l’utente seleziona un evento dalla rail:

- la sidebar deve mostrare il selected event summary;
- l’item corrispondente della event list deve aprirsi o evidenziarsi;
- l’audit resta apribile solo dal bottone `AUDIT` della card event list.

### 3.2 Chart

Se l’utente seleziona un marker chart:

- la sidebar deve mostrare il selected event summary;
- l’item corrispondente della event list deve aprirsi o evidenziarsi.

### 3.3 Event list

La event list è il punto di lettura principale dell’evento selezionato.

### 3.4 Bottone `AUDIT`

Il pulsante `AUDIT` deve esistere in ogni card evento e aprire il drawer completo relativo all’evento.

---

## 4. Event List — struttura finale

### 4.1 Struttura generale

La event list deve essere divisa in due sezioni:

#### A. Eventi con impatto sul trade

Eventi che hanno modificato posizione, piano attivo, livelli o pending rilevanti.

Qui rientrano, tra gli altri:

- `SETUP_CREATED`
- `ENTRY_ORDER_ADDED`
- `ENTRY_FILLED_INITIAL`
- `ENTRY_FILLED_SCALE_IN`
- `STOP_MOVED`
- `BREAK_EVEN_ACTIVATED`
- `EXIT_PARTIAL_*`
- `EXIT_FINAL_*`
- `PENDING_CANCELLED_*`
- `PENDING_TIMEOUT`

#### B. Eventi non operativi / audit

Eventi ignorati, post mortem, system note, note tecniche o eventi non mutativi ma utili alla comprensione.

Qui rientrano, tra gli altri:

- `IGNORED`
- `SYSTEM_NOTE`
- eventi informativi senza effetto concreto sul trade

### 4.2 Card chiusa

Una card chiusa deve mostrare almeno:

- `display_label`;
- timestamp;
- source;
- summary breve;
- piccolo indicatore di impatto;
- bottone `AUDIT`.

### 4.3 Card aperta

Una card aperta può mostrare:

- prezzo o livello rilevante;
- source;
- summary;
- `state_delta_essential`;
- eventuale raw text breve del trader;
- azioni utili.

### 4.4 Delta essenziali da mostrare in event list

I delta mostrati in event list devono essere derivati automaticamente da `state_delta_full`.

Esempi ammessi:

- `open_size: 1.00 -> 0.50`
- `realized_pnl: 0.00 -> 115.0`
- `close_fees_paid: 0.00 -> 0.72`
- `current_sl: 43080.0 -> 43052.7`
- `avg_entry_price: 43120.5 -> 42990.2`

Non devono essere selezionati manualmente nel frontend con logiche ad hoc evento per evento.

---

## 5. Event List — raw text originale

### 5.1 Quando mostrarlo

Il raw text trader va mostrato quando:

- l’evento deriva direttamente o indirettamente da un messaggio del trader;
- il testo è utile alla comprensione operativa.

### 5.2 Come mostrarlo

In event list il raw text deve essere:

- sintetico o collassato di default;
- espandibile;
- distinto dal summary generato.

### 5.3 Comportamento

Il raw text non sostituisce la summary e non sostituisce i delta.
È un supporto di verifica contestuale.

---

## 6. Event List — esempi aggiornati

### 6.1 Setup created

**Source:** `trader`

**Summary:** `Signal opened and initial plan created`

**Levels:** `entry, SL, TP set`

**State delta essential:**

- `pending_structure: none -> created`

**Sezione:** `A`

**Actions:**

- `[Original message]`
- `[AUDIT]`

### 6.2 Initial entry filled

**Source:** `engine`

**Price:** `43120.5`

**Summary:** `Initial entry filled`

**State delta essential:**

- `open_size: 0.00 -> 1.00`
- `avg_entry_price: null -> 43120.5`

**Sezione:** `A`

**Actions:**

- `[AUDIT]`

### 6.3 Break-even activated

**Source:** `trader`

**Summary:** `Stop moved to break-even`

**State delta essential:**

- `current_sl: 43080.0 -> 43052.7`

**Sezione:** `A`

**Actions:**

- `[Original message]`
- `[AUDIT]`

### 6.4 TP partial hit

**Source:** `engine`

**Summary:** `Partial take-profit executed`

**State delta essential:**

- `open_size: 1.00 -> 0.50`
- `realized_pnl: 0.00 -> 115.0`
- `close_fees_paid: 0.00 -> 0.72`

**Sezione:** `A`

**Actions:**

- `[AUDIT]`

### 6.5 Pending cancel trader

**Source:** `trader`

**Summary:** `Pending entries cancelled`

**State delta essential:**

- `pending_size: 1.00 -> 0.00`

**Sezione:** `A`

**Actions:**

- `[Original message]`
- `[AUDIT]`

### 6.6 Ignored

**Source:** `engine`

**Summary:** `Event ignored`

**Reason:** `not applicable to current trade state`

**Sezione:** `B`

**Actions:**

- `[AUDIT]`

---

## 7. Audit Drawer — struttura finale

### 7.1 Header

L’header deve mostrare:

- titolo evento;
- timestamp;
- source;
- event_code;
- stage;
- eventuale reason_code.

### 7.2 Sezioni interne

L’audit drawer deve avere sezioni leggibili, non solo JSON grezzo:

1. execution summary
2. readable state delta
3. structured event data
4. original trader message
5. raw technical data

---

## 8. Audit Drawer — contenuto completo

### 8.1 Execution summary

Sezione leggibile con:

- evento;
- motivo;
- effetto sulla posizione;
- livello o prezzo rilevante;
- eventuale outcome.

### 8.2 Readable state delta

L’audit drawer deve mostrare la versione completa leggibile di `state_delta_full`.

Il JSON raw, se presente, deve stare in un sotto-toggle o sezione dedicata, non come vista primaria.

### 8.3 Structured event data

Qui vanno almeno:

- `event_id`
- `trade_id`
- `occurred_at`
- `sequence_index`
- `raw_event_ref`
- `event_code`
- `stage`
- `source`
- `position_effect`
- `display_group`
- `display_label`
- `reason_code`
- `price_anchor`
- `summary`
- `details`

### 8.4 Original trader message

Se disponibile, mostrare:

- messaggio originale o estratto;
- eventuale riferimento messaggio / source metadata.

### 8.5 Raw technical data

Qui vanno:

- raw payload;
- dati engine / simulator;
- mapping trace;
- note tecniche utili a debug o QA.

---

## 9. Regole finali

### 9.1 Event list

La event list è il livello operativo primario.

### 9.2 Audit drawer

L’audit drawer è il livello tecnico completo.

### 9.3 Apertura audit

L’audit drawer si apre soltanto da `AUDIT` nella event list.

### 9.4 Raw trader text

Il raw trader text deve essere consultabile sia in event list sia in audit drawer quando disponibile.

---

## 10. Nota implementativa

La UI non deve mantenere due semantiche parallele.

La card event list, il selected event summary e l’audit drawer devono derivare dallo stesso evento canonico già normalizzato.
