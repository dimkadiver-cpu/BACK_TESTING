# Parser Development Template

Documento modello da usare come base per sviluppare un nuovo parser profilo-specifico in `src/signal_chain_lab/parser/trader_profiles/<trader_code>/`.

Scopo del template:

- guidare lo sviluppo di parser nuovi o da rifattorizzare
- imporre un contratto di output coerente con il core
- evitare regressioni su replay, report e operation rules
- standardizzare checklist, casi di test e criteri di done

Questo documento va copiato e adattato per ogni nuovo trader/parser.

---

## 1. Identità parser

- `trader_code`:
- `parser_name`:
- `owner`:
- `stato`: `draft | in_progress | ready_for_replay | validated | production`
- `versione parser`: es. `trader_x_v1`
- `fonte messaggi`: canale, gruppo, topic, bot, thread
- `lingua prevalente`: es. `IT | EN | RU`

---

## 2. Obiettivo parser

Descrivere in 3-6 righe:

- che tipo di messaggi gestisce
- se il trader usa segnali completi o incompleti
- se prevalgono segnali `market`, `limit`, `range`, `two-step`, `ladder`
- se gli update sono reply-driven, link-driven, signal-id-driven o globali

---

## 3. Contratto obbligatorio di output

Ogni parser deve restituire sempre un envelope coerente con:

- `message_type`
- `completeness`
- `missing_fields`
- `entities`
- `intents`
- `target_refs`
- `target_scope`
- `confidence`
- `warnings`
- `diagnostics`
- `raw_text`
- `trader_id`
- `acquisition_mode`

### 3.1 `NEW_SIGNAL` — campi canonici minimi

Il parser deve valorizzare, quando presenti:

- `symbol`
- `direction`
- `entry_type`
- `entry_structure`
- `entry_plan_entries`
- `stop_loss`
- `take_profits`

### 3.2 `UPDATE` — campi canonici minimi

Il parser deve valorizzare, quando presenti:

- `new_sl_level`
- `new_sl_price`
- `new_sl_reference`
- `close_price`
- `close_pct`
- `new_take_profits`
- `cancel_scope`
- `reported_profit_r`
- `reported_profit_pct`

### 3.3 Alias da evitare come output primario

Questi campi non devono essere la fonte di verità del parser nuovo:

- `side` al posto di `direction`
- `new_stop_level` al posto di `new_sl_level`
- `new_stop_price` al posto di `new_sl_price`
- `partial_close_percent` al posto di `close_pct`
- `entry_type = AVERAGING`
- `entry_type = ZONE`
- `entry_structure = SINGLE`

Se servono per compatibilità:

- popolarli come alias o metadata
- ma valorizzare sempre il campo canonico corrispondente

---

## 4. Profilo semantico target

### 4.1 `entry_type`

Usare solo:

- `MARKET`
- `LIMIT`

### 4.2 `entry_structure`

Usare solo:

- `ONE_SHOT`
- `TWO_STEP`
- `RANGE`
- `LADDER`

### 4.3 `entry_plan_entries`

Ogni parser nuovo deve produrre `entry_plan_entries` come fonte primaria del piano di ingresso.

Struttura minima raccomandata:

```yaml
entry_plan_entries:
  - sequence: 1
    role: PRIMARY
    order_type: MARKET | LIMIT
    price: null
    raw_label: null
    source_style: null
    is_optional: false
```

Per piani `TWO_STEP`:

- il secondo elemento deve avere `role = AVERAGING`

Per piani `RANGE`:

- usare anche `entry_range`, `entry_range_low`, `entry_range_high`
- ma mantenere `entry_plan_entries` come piano operativo canonico

---

## 5. Campi completi consigliati

Anche se non sempre valorizzati, il parser dovrebbe restituire la struttura completa:

```yaml
entities:
  signal_id: null
  symbol: null
  symbol_raw: null
  direction: null

  entry_type: null
  entry_structure: null
  entry_order_type: null
  entry_plan_type: null
  has_averaging_plan: false

  entry_plan_entries: []
  entry: []
  entries: []
  entry_range: []
  entry_range_low: null
  entry_range_high: null

  stop_loss: null
  take_profits: []

  risk_percent: null
  risk_value_raw: null
  risk_value_normalized: null

  leverage: null
  leverage_hint_raw: null
  reported_leverage_hint: null

  new_sl_level: null
  new_sl_price: null
  new_sl_reference: null
  close_price: null
  close_pct: null
  partial_close_price: null
  old_take_profits: []
  new_take_profits: []
  cancel_scope: null
  manual_close: null
  stop_price: null

  entry_text_raw: null
  stop_loss_raw: null
  targets_text_raw: null
  take_profits_text_raw: null
  market_context: null
  conditions: null
```

---

## 6. Strategia di parsing

Compilare questa sezione prima di scrivere il parser:

### 6.1 Pattern di `NEW_SIGNAL`

- marker di symbol:
- marker di side/direction:
- marker di entry:
- marker di SL:
- marker di TP:
- marker di rischio:
- marker di leverage:

### 6.2 Pattern di `UPDATE`

- stop to breakeven:
- move stop numerico:
- close partial:
- close full:
- cancel pending:
- update take profits:
- tp hit:
- sl hit:
- result report:
- manual close:

### 6.3 Targeting

Specificare se gli update usano:

- reply
- telegram link
- message id
- signal id
- symbol fallback
- scope globale

---

## 7. Mapping semantico richiesto

### 7.1 `NEW_SIGNAL`

Compilare:

| Caso messaggio | Output target |
|---|---|
| Market singolo | `entry_type=MARKET`, `entry_structure=ONE_SHOT` |
| Limit singolo | `entry_type=LIMIT`, `entry_structure=ONE_SHOT` |
| Primary + averaging | `entry_type=MARKET/LIMIT`, `entry_structure=TWO_STEP` |
| Fascia low-high | `entry_type=LIMIT`, `entry_structure=RANGE` |
| Più livelli discreti | `entry_type=LIMIT`, `entry_structure=LADDER` |

### 7.2 `UPDATE`

Compilare:

| Caso messaggio | Intent | Campi canonici |
|---|---|---|
| Move SL to BE | `U_MOVE_STOP_TO_BE` | `new_sl_level`, `new_sl_reference` |
| Move SL numerico | `U_MOVE_STOP` | `new_sl_level`, `new_sl_price` |
| Partial close | `U_CLOSE_PARTIAL` | `close_pct`, `partial_close_price` |
| Full close | `U_CLOSE_FULL` | `close_price` se disponibile |
| Cancel pending | `U_CANCEL_PENDING_ORDERS` | `cancel_scope` |
| TP hit | `U_TP_HIT` | `tp_hit_number`, `reported_profit_*` |
| SL hit | `U_STOP_HIT` | `reported_profit_*`, `stop_price` se disponibile |

---

## 8. Test plan minimo

Ogni nuovo parser deve avere almeno:

### 8.1 Smoke tests

- parser registrato correttamente
- parse senza crash su esempi base
- output envelope coerente

### 8.2 Real cases `NEW_SIGNAL`

Almeno:

- 1 market one-shot
- 1 limit one-shot
- 1 range
- 1 two-step o ladder se il trader li usa
- 1 caso incompleto

### 8.3 Real cases `UPDATE`

Almeno:

- move stop to BE
- move stop numerico
- partial close
- close full
- cancel pending
- tp/sl hit o result report

### 8.4 Contract tests

Verificare:

- presenza dei campi canonici
- assenza di dipendenza da alias legacy
- naming coerente con il contratto comune

### 8.5 Replay tests in `parser_test`

Obbligatori:

1. replay sul DB del canale/topic target
2. export CSV aggiornato
3. controllo manuale dei report `new_signal`, `update`, `all_messages`

---

## 9. Checklist di sviluppo

### 9.1 Prima implementazione

- creare cartella `src/signal_chain_lab/parser/trader_profiles/<trader_code>/`
- creare `profile.py`
- creare `parsing_rules.json` se serve
- registrare il parser nel registry
- creare test smoke

### 9.2 Allineamento contratto

- usare `direction`, non `side`, come output primario
- usare `entry_structure` canonico
- produrre `entry_plan_entries`
- usare naming update canonico `new_sl_*`
- usare `risk_percent` come nome principale

### 9.3 Validazione con harness

- eseguire replay con `parser_test/scripts/replay_parser.py`
- generare report con `parser_test/scripts/generate_parser_reports.py`
- confrontare warning, intents e campi chiave sui CSV

### 9.4 Done criteria

Parser considerato pronto quando:

1. passa i test unitari
2. passa almeno un replay realistico su dataset dedicato
3. produce output coerente con il contratto canonico
4. non introduce alias legacy come semantica primaria
5. ha warning e confidence ragionevoli sui casi ambigui

---

## 10. Comandi utili

Replay parser:

```powershell
python parser_test/scripts/replay_parser.py --chat-id <CHAT_ID> --db-per-chat --trader <TRADER_CODE> --only-unparsed
```

Replay + report:

```powershell
python parser_test/scripts/generate_parser_reports.py --chat-id <CHAT_ID> --db-per-chat --trader <TRADER_CODE>
```

Watch mode:

```powershell
python parser_test/scripts/watch_parser.py --trader <TRADER_CODE>
```

---

## 11. Note per il reviewer

Quando si revisiona un parser nuovo, controllare sempre:

- naming canonico dei campi
- coerenza `direction` / `entry_type` / `entry_structure`
- presenza di `entry_plan_entries`
- coerenza tra intents e fields valorizzati
- uso corretto di `target_refs` e `target_scope`
- presenza di test reali, non solo smoke

---

## 12. Collegamenti consigliati

Documenti di riferimento:

- [PRD unificazione semantica entry](C:/Back_Testing/docs/PRD_unificazione_semantica_entry.md)
- [Supporto simulatore](C:/Back_Testing/docs/Supporto%20simulatore.md)
- [parser_test README](C:/Back_Testing/parser_test/README.md)

Questo file è un template operativo: ogni nuovo parser dovrebbe avere una copia compilata o una issue/PR description equivalente che dimostri come vengono coperti contratto, test e replay.
