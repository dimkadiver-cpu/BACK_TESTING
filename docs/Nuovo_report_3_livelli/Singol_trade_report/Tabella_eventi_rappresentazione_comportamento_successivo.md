# Tabella completa — eventi, rappresentazione e comportamento successivo

> Documento derivato dal PRD master:
> `PRD_definitivo_sistemazione_eventi_single_trade_report.md`
> In caso di conflitto prevale sempre il PRD master.

## 1. Scopo

Questa tabella riassume in forma operativa la matrice finale degli eventi canonici del single trade report.

Serve come riferimento rapido per:

- normalizer;
- chart payload builder;
- event rail;
- event list;
- audit drawer;
- QA e test di coerenza.

---

## 2. Legenda sintetica

### Marker rule

- `REQUIRED` = marker obbligatorio sul chart
- `OPTIONAL_LIGHT` = marker leggero opzionale
- `NONE` = nessun marker

### Geometry effect

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

### Delta policy

- `PLAN`
- `OPEN`
- `INCREASE`
- `REDUCE`
- `CLOSE`
- `CANCEL_PENDING`
- `INFO_ONLY`

---

## 3. Matrice finale

| event_code | stage | source | position_effect | marker_rule | geometry_effect | delta_policy | rail | chart | event_list_section | audit_drawer | note |
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

## 4. Regole globali

### 4.1 Event rail

La rail contiene gli eventi con effetto concreto sul trade, in ordine temporale deterministico.

### 4.2 Chart

Il chart non deve essere una timeline testuale completa.
Deve mostrare soprattutto:

- prezzo;
- livelli;
- fill;
- riduzioni;
- chiusure;
- cambi geometrici dei livelli.

### 4.3 Event list

La event list è più ricca del chart e deve includere:

- sezione A = eventi con effetto concreto sul trade;
- sezione B = eventi non operativi / audit.

### 4.4 Audit drawer

L’audit drawer è il livello tecnico completo e contiene tutti gli eventi.

### 4.5 Apertura audit

L’audit drawer si apre solo dalla event list tramite bottone `AUDIT`.

---

## 5. Regole critiche da non violare

- `ENTRY_ORDER_ADDED` non è un fill;
- `STOP_MOVED` non crea marker indipendente;
- `BREAK_EVEN_ACTIVATED` non crea marker indipendente;
- `PENDING_CANCELLED_*` e `PENDING_TIMEOUT` non usano `EXIT` come default;
- `IGNORED` e `SYSTEM_NOTE` non alterano la geometria del trade;
- dopo `EXIT_FINAL_*` non devono esistere eventi operativi mutativi;
- una linea pending di entry si interrompe nel punto in cui quella gamba viene fillata;
- la `Average Entry line` compare dal secondo fill eseguito in poi e prosegue fino all’uscita finale.
