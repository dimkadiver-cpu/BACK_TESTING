# PRD definitivo — Sistemazione eventi dal simulatore al report del singolo trade

## 1. Obiettivo

Rendere coerente, leggibile e standardizzata la rappresentazione degli eventi lungo tutto il flusso:

**simulatore → event log → canonical normalizer → chart payload → HTML single trade report**

Questo PRD definisce una sola semantica condivisa per:

- chart del singolo trade;
- event rail;
- event list;
- selected event summary;
- audit drawer;
- payload intermedi usati dal report.

In caso di conflitto con i documenti derivati, prevale sempre questo PRD.

---

## 2. Problema da risolvere

Nel flusso attuale coesistono più livelli semantici non perfettamente allineati:

1. eventi raw del dominio / simulatore;
2. reason tecniche e stati di engine;
3. mapping report non sempre uniformi;
4. regole visuali chart / trail / event list non sempre equivalenti.

Le conseguenze tipiche sono:

- `OPEN_SIGNAL` o `SETUP_CREATED` letti talvolta come setup e talvolta come fill;
- `ADD_ENTRY` letto come piano in un punto e come esecuzione in un altro;
- `CLOSE_FULL` e `CLOSE_PARTIAL` troppo compressi semanticamente;
- `CANCEL_PENDING` non distinto tra trader, engine e timeout;
- chart, trail, event list e audit che non raccontano sempre la stessa storia.

---

## 3. Decisioni definitive di progetto

### D1 — Unico layer canonico per il report

Tutte le viste del single trade report devono usare la stessa tassonomia evento.

### D2 — Il raw event non è la semantica visiva primaria

Il raw event resta utile per:

- tracciabilità;
- debug;
- backward compatibility.

Non deve essere il driver principale della UI.

### D3 — I fill reali devono essere espliciti

Il report deve distinguere chiaramente:

- setup;
- piano entry;
- fill iniziale;
- scale-in;
- riduzioni;
- chiusure finali.

### D4 — Apertura audit solo da event list

L’audit drawer si apre esplicitamente solo dalla **event list** tramite bottone `AUDIT`.

Click su chart o event rail:

- seleziona l’evento;
- aggiorna il selected event summary;
- apre o evidenzia l’item corrispondente nella event list;
- non apre direttamente l’audit drawer.

### D5 — Classificazione A / B unificata

- **Sezione A / eventi rail / chart**: eventi con effetto concreto sul trade, sui livelli, sulla posizione o sul piano attivo.
- **Sezione B**: eventi non mutativi o non operativi, come ignored, post mortem, system note e note tecniche.
- **Audit drawer**: contiene sempre tutti gli eventi.

### D6 — Separare evento, motivo, effetto e rappresentazione

Ogni evento finale deve distinguere almeno:

- identità dell’evento;
- motivo tecnico, se disponibile;
- effetto su posizione o piano;
- bucket di presentazione;
- effetto geometrico sul chart.

### D7 — `POST_MORTEM` non è uno stage operativo principale

Per la matrice operativa e per il chart si usano come stage principali:

- `ENTRY`
- `MANAGEMENT`
- `EXIT`

Eventi puramente audit o tecnici possono continuare a esistere come note, ma non devono introdurre ambiguità nella semantica operativa primaria.

### D8 — L’ordine logico prevale quando due eventi condividono lo stesso timestamp

Quando più eventi cadono nello stesso istante logico, il sistema deve applicare una priorità deterministica.

Esempi minimi obbligatori:

- setup market-fill: prima `SETUP_CREATED`, poi `ENTRY_FILLED_INITIAL`;
- TP che attiva BE: prima evento TP rilevante, poi `BREAK_EVEN_ACTIVATED`.

---

## 4. Strategia generale del flusso target

Il flusso corretto deve essere:

1. raw engine event;
2. canonical normalization;
3. enrichment report fields;
4. backward adapter per eventuali consumer legacy;
5. payload finale per chart, event rail, event list e audit drawer.

La UI non deve reinterpretare business logic dispersa.

---

## 5. Fill e compatibilità con il dominio

Per il report è necessario poter rappresentare i fill reali in modo esplicito.

Nel breve periodo è accettabile introdurre eventi di fill sintetici a livello engine/report pipeline, purché il risultato finale sia stabile, testabile e coerente con lo stato del trade.

Il report deve distinguere nettamente tra:

- **entry pianificata**;
- **entry realmente eseguita**.

---

## 6. Contratto canonico evento

### 6.1 Obiettivo

Il sistema deve usare un modello evento canonico unico per report, chart, event list e audit drawer.

### 6.2 Campi obbligatori del payload canonico

Ogni evento canonico deve contenere obbligatoriamente:

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

Questi campi sono il minimo contrattuale richiesto per sincronizzazione, ordinamento e rendering coerente.

### 6.3 Campi raccomandati / enrichment

Il payload finale consumato dalla UI deve includere, quando disponibili:

- `event_class`
- `reason_code`
- `summary`
- `details`
- `price_anchor`
- `state_before`
- `state_after`
- `state_delta_full`
- `state_delta_essential`
- `event_list_section`
- `chart_marker_kind`
- `geometry_effect`
- `geometry_payload`

### 6.4 Regole di fallback

Se il payload finale non contiene alcuni campi arricchiti, applicare fallback deterministici:

- se manca `display_label`, derivarlo da `event_code`;
- se manca `summary`, generare una summary standard;
- se mancano `details`, usare lista vuota;
- se l’evento non è riconosciuto, mapparlo a `SYSTEM_NOTE`;
- se manca `event_list_section`, derivarlo dalla classificazione A/B.

### 6.5 Compatibilità legacy

Il sistema deve prevedere un backward adapter che:

- accetti il payload canonico finale;
- generi eventuali campi legacy ancora richiesti;
- impedisca che la UI legga direttamente chiavi legacy come fonte primaria.

---

## 7. Mapping raw → canonical

### 7.1 Principio

`event_normalizer.py` è il punto centrale di mapping raw → canonico.

### 7.2 Regole minime obbligatorie

Il normalizer deve gestire in modo normativo almeno i seguenti casi:

- `OPEN_SIGNAL` / apertura setup → `SETUP_CREATED`
- `ADD_ENTRY` / piano entry aggiunto → `ENTRY_ORDER_ADDED`
- fill reale iniziale → `ENTRY_FILLED_INITIAL`
- fill reale successivo con posizione già aperta → `ENTRY_FILLED_SCALE_IN`
- `CLOSE_PARTIAL` con reason TP → `EXIT_PARTIAL_TP`
- `CLOSE_PARTIAL` con reason manual / non-TP → `EXIT_PARTIAL_MANUAL`
- `CLOSE_FULL` con reason TP → `EXIT_FINAL_TP`
- `CLOSE_FULL` con reason SL → `EXIT_FINAL_SL`
- `CLOSE_FULL` con reason manual → `EXIT_FINAL_MANUAL`
- `CLOSE_FULL` con reason timeout → `EXIT_FINAL_TIMEOUT`
- `CANCEL_PENDING` da trader → `PENDING_CANCELLED_TRADER`
- `CANCEL_PENDING` da engine → `PENDING_CANCELLED_ENGINE`
- pending scaduto → `PENDING_TIMEOUT`

### 7.3 Regola su `open_size`

Quando una regola di mapping o classificazione usa `open_size`, quel valore deve essere letto come **state before event**, non come stato dopo l’applicazione dell’evento.

---

## 8. Regole visuali chart, event rail, event list e audit

### 8.1 Event rail

L’event rail non è la timeline completa di tutto il rumore tecnico.

Deve mostrare gli eventi della **Sezione A**, cioè gli eventi con effetto concreto sul trade.

Gli eventi della Sezione B restano leggibili in event list e audit drawer, ma non devono appesantire la rail standard.

### 8.2 Chart

Il chart deve mostrare:

- candlestick;
- livelli attivi nel tempo;
- marker solo per eventi visivamente forti o esecutivi;
- effetti geometrici dei cambi di livello.

Il chart non deve diventare una seconda event list.

### 8.3 Event list

La event list è il livello operativo leggibile e deve essere divisa in due sezioni:

- **Sezione A** = eventi con effetto concreto sul trade;
- **Sezione B** = eventi non operativi / audit.

### 8.4 Audit drawer

L’audit drawer è il livello tecnico completo e deve mostrare sempre tutti gli eventi.

### 8.5 Apertura e sincronizzazione

- click su rail → aggiorna selected event summary e apre/evidenzia l’item corrispondente in event list;
- click su chart marker → aggiorna selected event summary e apre/evidenzia l’item corrispondente in event list;
- click su card event list → aggiorna selected event summary;
- click su `AUDIT` in event list → apre audit drawer sull’evento corretto.

---

## 9. Marker chart e eventi solo geometrici

### 9.1 Marker obbligatori

Devono produrre marker esplicito sul chart:

- `ENTRY_FILLED_INITIAL`
- `ENTRY_FILLED_SCALE_IN`
- `EXIT_PARTIAL_TP`
- `EXIT_PARTIAL_MANUAL`
- `EXIT_FINAL_TP`
- `EXIT_FINAL_SL`
- `EXIT_FINAL_MANUAL`
- `EXIT_FINAL_TIMEOUT`

### 9.2 Marker opzionali leggeri

Possono produrre marker leggero opzionale:

- `PENDING_CANCELLED_TRADER`
- `PENDING_CANCELLED_ENGINE`
- `PENDING_TIMEOUT`

### 9.3 Nessun marker dedicato

Non devono generare marker dedicato sul chart:

- `SETUP_CREATED`
- `ENTRY_ORDER_ADDED`
- `IGNORED`
- `SYSTEM_NOTE`
- `STOP_MOVED`
- `BREAK_EVEN_ACTIVATED`

### 9.4 Eventi che modificano solo la geometria

`STOP_MOVED` e `BREAK_EVEN_ACTIVATED` devono essere rappresentati solo tramite modifica della geometria o dello stile delle linee.

Effetti ammessi:

- chiusura del vecchio segmento stop;
- apertura del nuovo segmento stop;
- cambio livello della linea;
- eventuale cambio etichetta o stile coerente.

---

## 10. Regole geometriche del chart

### 10.1 `SETUP_CREATED`

- compare in event rail e in event list Sezione A;
- non ha marker chart;
- sul chart è il **punto di partenza** delle linee iniziali di `ENTRY`, `SL` e `TP`.

### 10.2 `ENTRY_ORDER_ADDED`

- compare in event rail e in event list Sezione A;
- non ha marker chart;
- sul chart aggiunge o estende una linea pending di entry pianificata.

### 10.3 `ENTRY_FILLED_INITIAL`

- compare in event rail e in event list Sezione A;
- ha marker forte di fill sul chart;
- la specifica linea pending di entry coinvolta deve **interrompersi** nel punto del fill;
- da questo punto il trade è realmente aperto.

### 10.4 `ENTRY_FILLED_SCALE_IN`

- compare in event rail e in event list Sezione A;
- ha marker forte di fill sul chart;
- la specifica linea pending di entry coinvolta deve interrompersi nel punto del fill;
- il chart deve aggiornare la struttura reale della posizione e il prezzo medio.

### 10.5 `Average Entry line`

La `Average Entry line` rappresenta il prezzo medio della posizione realmente aperta.

Regole:

- con una sola entry fillata può restare nascosta di default;
- deve comparire automaticamente dal **secondo fill eseguito in poi**;
- deve proseguire per tutta la durata del trade aperto;
- deve aggiornarsi a ogni nuovo scale-in che modifica il prezzo medio;
- deve terminare alla chiusura finale della posizione.

### 10.6 Entry plan line

Le linee di entry pianificata devono esistere solo finché il piano è attivo.

Una singola linea pending di entry termina quando quella gamba viene:

- fillata;
- cancellata;
- scaduta;
- resa irrilevante dalla chiusura finale.

### 10.7 Stop line

La linea stop è segmentata nel tempo.

Ogni `STOP_MOVED` o `BREAK_EVEN_ACTIVATED` chiude un segmento e ne apre un altro.

### 10.8 TP lines

Ogni TP resta vivo finché viene colpito o finché la posizione termina in altro modo.

### 10.9 Exit finale

Un `EXIT_FINAL_*` deve chiudere tutte le linee residue del trade.

---

## 11. Delta di stato: source of truth

### 11.1 Principio generale

La fonte unica di verità per i delta è:

- `state_delta_full`

Da questa devono essere derivati automaticamente i delta sintetici per UI:

- `state_delta_essential`

La UI non deve costruire manualmente i delta con logiche sparse.

### 11.2 Schema minimo di `state_delta_full`

Ogni item di `state_delta_full` deve poter esprimere almeno:

- `field_path`
- `before`
- `after`
- `unit`
- `is_mutative`
- `display_priority`

### 11.3 Uso dei delta

- **Event list** → mostra `state_delta_essential`
- **Audit drawer** → mostra `state_delta_full`

Esempi tipici ammessi in event list:

- `open_size: 1.00 -> 0.50`
- `realized_pnl: 0.00 -> 115.0`
- `close_fees_paid: 0.00 -> 0.72`
- `current_sl: 43080.0 -> 43052.7`

---

## 12. Stage semantics per cancel e timeout

Gli eventi di cancellazione pending o timeout non devono essere classificati automaticamente come `EXIT`.

Regole:

- se `open_size == 0` **prima dell’evento** → `stage = ENTRY`
- se `open_size > 0` **prima dell’evento** → `stage = MANAGEMENT`

Non usare `EXIT` come default per:

- `PENDING_CANCELLED_TRADER`
- `PENDING_CANCELLED_ENGINE`
- `PENDING_TIMEOUT`

---

## 13. Invarianti hard del lifecycle

### 13.1 Invarianti minimi obbligatori

1. Dopo un evento `EXIT_FINAL_*` non possono esistere ulteriori eventi operativi mutativi sulla stessa posizione.
2. `IGNORED` e `SYSTEM_NOTE` non devono alterare posizione, rischio, geometria dei livelli o stato operativo del trade.
3. Un livello pending cancellato o scaduto non può riapparire senza un nuovo evento strutturale che lo ricrei.
4. `ENTRY_FILLED_INITIAL` può comparire al massimo una volta per trade.
5. `ENTRY_FILLED_SCALE_IN` è valido solo se esiste già una posizione aperta prima dell’evento.
6. `STOP_MOVED` e `BREAK_EVEN_ACTIVATED` non devono essere trattati come marker chart indipendenti.
7. Quando più eventi hanno lo stesso timestamp logico, deve essere applicato un ordinamento deterministico coerente con la causalità del trade.

### 13.2 Regole minime di priorità con timestamp uguale

Ordine minimo obbligatorio:

1. setup / creazione piano;
2. fill iniziale o scale-in;
3. move stop / break-even;
4. exit partial;
5. exit final;
6. eventi informativi o audit.

Eccezioni normative esplicite:

- setup market-fill: `SETUP_CREATED` prima di `ENTRY_FILLED_INITIAL`;
- TP con regola automatica BE: evento TP prima di `BREAK_EVEN_ACTIVATED`.

---

## 14. Confine tra responsabilità dei layer

### 14.1 Engine

L’engine deve:

- produrre eventi grezzi affidabili;
- produrre o rendere derivabili i campi del payload canonico minimo;
- produrre `state_delta_full` o dati sufficienti a costruirlo.

### 14.2 Canonical normalizer

Il canonical normalizer deve:

- convertire eventi raw in `event_code` canonici;
- applicare il mapping raw → canonical;
- assegnare i campi minimi obbligatori;
- classificare la sezione A/B.

### 14.3 Enrichment layer

L’enrichment layer deve:

- completare `summary`, `details`, `price_anchor`, `reason_code`;
- derivare `state_delta_essential`;
- produrre `geometry_payload` e campi utili a chart, event list e audit drawer.

### 14.4 Chart payload builder

Il chart payload builder deve:

- applicare le regole A/B/C dei marker;
- applicare le regole geometriche delle linee;
- non inventare una tassonomia parallela;
- gestire correttamente l’interruzione delle linee pending al fill e la `Average Entry line`.

### 14.5 UI renderer

La UI deve:

- consumare payload già normalizzati;
- non duplicare logiche di classificazione evento;
- non costruire manualmente mapping semantici dispersi.

La UI deve essere renderer, non interprete di business logic.

---

## 15. Matrice finale eventi canonici

### 15.1 Legenda

**Marker rule**

- `REQUIRED` = marker obbligatorio sul chart
- `OPTIONAL_LIGHT` = marker leggero opzionale
- `NONE` = nessun marker

**Geometry effect**

- `CREATE_INITIAL_LEVELS`
- `ADD_PENDING_LEVEL`
- `ACTIVATE_FILLED_ENTRY`
- `UPDATE_AVERAGE_ENTRY_AND_POSITION_LEVELS`
- `UPDATE_STOP_LINE`
- `CONVERT_STOP_TO_BE`
- `REMOVE_PENDING_LEVEL`
- `REDUCE_POSITION_LEVELS`
- `CLOSE_POSITION_LEVELS`
- `ANNOTATION_ONLY`

**Delta policy**

- `PLAN`
- `OPEN`
- `INCREASE`
- `REDUCE`
- `CLOSE`
- `CANCEL_PENDING`
- `INFO_ONLY`

### 15.2 Matrice normativa

| event_code | stage | source | position_effect | marker_rule | geometry_effect | delta_policy | rail | chart | event_list_section | audit | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `SETUP_CREATED` | `ENTRY` | trader / engine | `PLAN_CREATED` | `NONE` | `CREATE_INITIAL_LEVELS` | `PLAN` | sì | nessun marker | `A` | sì | crea setup e livelli iniziali |
| `ENTRY_ORDER_ADDED` | `ENTRY` | trader / engine | `PLAN_UPDATED` | `NONE` | `ADD_PENDING_LEVEL` | `PLAN` | sì | nessun marker | `A` | sì | aggiunge pending / gamba pianificata |
| `ENTRY_FILLED_INITIAL` | `ENTRY` | exchange / engine | `POSITION_OPENED` | `REQUIRED` | `ACTIVATE_FILLED_ENTRY` | `OPEN` | sì | marker forte | `A` | sì | primo fill reale; interrompe la pending corrispondente |
| `ENTRY_FILLED_SCALE_IN` | `MANAGEMENT` | exchange / engine | `POSITION_INCREASED` | `REQUIRED` | `UPDATE_AVERAGE_ENTRY_AND_POSITION_LEVELS` | `INCREASE` | sì | marker forte | `A` | sì | fill successivo; aggiorna average entry |
| `STOP_MOVED` | `MANAGEMENT` | trader / engine | `PLAN_UPDATED` | `NONE` | `UPDATE_STOP_LINE` | `PLAN` | sì | solo geometria | `A` | sì | nessun marker dedicato |
| `BREAK_EVEN_ACTIVATED` | `MANAGEMENT` | trader / engine | `PLAN_UPDATED` | `NONE` | `CONVERT_STOP_TO_BE` | `PLAN` | sì | solo geometria | `A` | sì | nessun marker dedicato |
| `EXIT_PARTIAL_TP` | `MANAGEMENT` | exchange / engine | `POSITION_REDUCED` | `REQUIRED` | `REDUCE_POSITION_LEVELS` | `REDUCE` | sì | marker forte | `A` | sì | riduzione per TP |
| `EXIT_PARTIAL_MANUAL` | `MANAGEMENT` | trader / engine | `POSITION_REDUCED` | `REQUIRED` | `REDUCE_POSITION_LEVELS` | `REDUCE` | sì | marker forte | `A` | sì | riduzione manuale |
| `EXIT_FINAL_TP` | `EXIT` | exchange / engine | `POSITION_CLOSED` | `REQUIRED` | `CLOSE_POSITION_LEVELS` | `CLOSE` | sì | marker forte | `A` | sì | chiusura finale TP |
| `EXIT_FINAL_SL` | `EXIT` | exchange / engine | `POSITION_CLOSED` | `REQUIRED` | `CLOSE_POSITION_LEVELS` | `CLOSE` | sì | marker forte | `A` | sì | chiusura finale SL |
| `EXIT_FINAL_MANUAL` | `EXIT` | trader / engine | `POSITION_CLOSED` | `REQUIRED` | `CLOSE_POSITION_LEVELS` | `CLOSE` | sì | marker forte | `A` | sì | chiusura finale manuale |
| `EXIT_FINAL_TIMEOUT` | `EXIT` | engine | `POSITION_CLOSED` | `REQUIRED` | `CLOSE_POSITION_LEVELS` | `CLOSE` | sì | marker forte | `A` | sì | chiusura finale timeout |
| `PENDING_CANCELLED_TRADER` | `ENTRY` o `MANAGEMENT` | trader | `PENDING_CANCELLED` | `OPTIONAL_LIGHT` | `REMOVE_PENDING_LEVEL` | `CANCEL_PENDING` | sì | marker leggero opzionale | `A` | sì | `ENTRY` se `open_size == 0` before event |
| `PENDING_CANCELLED_ENGINE` | `ENTRY` o `MANAGEMENT` | engine | `PENDING_CANCELLED` | `OPTIONAL_LIGHT` | `REMOVE_PENDING_LEVEL` | `CANCEL_PENDING` | sì | marker leggero opzionale | `A` | sì | `ENTRY` se `open_size == 0` before event |
| `PENDING_TIMEOUT` | `ENTRY` o `MANAGEMENT` | engine | `PENDING_CANCELLED` | `OPTIONAL_LIGHT` | `REMOVE_PENDING_LEVEL` | `CANCEL_PENDING` | sì | marker leggero opzionale | `A` | sì | non usare `EXIT` come default |
| `IGNORED` | dipende dal contesto | trader / engine | `NONE` | `NONE` | `ANNOTATION_ONLY` | `INFO_ONLY` | no | nessun marker | `B` | sì | evento non mutativo |
| `SYSTEM_NOTE` | dipende dal contesto | engine / system | `NONE` | `NONE` | `ANNOTATION_ONLY` | `INFO_ONLY` | no | nessun marker | `B` | sì | nota tecnica / audit |

---

## 16. Requisiti funzionali e criteri di accettazione

### RF-1
Il single trade report deve usare una sola semantica evento per chart, event rail, event list e audit drawer.

### RF-2
`ENTRY_ORDER_ADDED` non deve mai essere mostrato come fill reale.

### RF-3
I fill reali devono essere distinguibili tra fill iniziale e scale-in.

### RF-4
`STOP_MOVED` e `BREAK_EVEN_ACTIVATED` devono cambiare la geometria delle linee senza creare marker indipendenti.

### RF-5
`PENDING_CANCELLED_*` e `PENDING_TIMEOUT` devono usare `ENTRY` o `MANAGEMENT` in base a `open_size` letto prima dell’evento.

### RF-6
La event list deve mostrare `state_delta_essential` e l’audit drawer deve mostrare `state_delta_full`.

### RF-7
L’audit drawer deve aprirsi esplicitamente solo dalla event list.

### RF-8
Il chart non deve mostrare marker per `SETUP_CREATED`, `ENTRY_ORDER_ADDED`, `IGNORED`, `SYSTEM_NOTE`, `STOP_MOVED`, `BREAK_EVEN_ACTIVATED`.

### RF-9
Quando una entry pending viene fillata, la sua linea deve interrompersi nel punto del fill.

### RF-10
La `Average Entry line` deve comparire automaticamente dal secondo fill eseguito in poi e durare per tutto il trade aperto.

### Criteri di accettazione minimi

- un trade con setup + add_entry + fill iniziale + move stop + TP partial + final SL produce una storia coerente e non contraddittoria;
- un pending cancel senza posizione aperta risulta `ENTRY`, non `EXIT`;
- un pending cancel con posizione aperta risulta `MANAGEMENT`, non `EXIT`;
- event list, audit drawer, rail e chart raccontano lo stesso lifecycle;
- click su marker chart o rail porta all’item corretto in event list;
- l’audit si apre solo dal bottone `AUDIT` nella card della event list;
- la UI non contiene mapping semantici paralleli o contraddittori.
