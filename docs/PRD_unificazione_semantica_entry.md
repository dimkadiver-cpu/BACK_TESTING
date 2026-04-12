

## Appendice A — Contratto canonico completo del parser

Questa appendice estende il PRD oltre la sola semantica entry e definisce il profilo completo comune da usare come output parser per tutti i trader.

L'obiettivo è avere:

- stessa struttura di output per tutti i parser
- stessi nomi campo per tutti i consumer downstream
- campi non valorizzati espressi come `null`, `[]` o `{}` invece che omessi o sostituiti con nomi alternativi

La struttura completa è divisa in:

- campi `canonical`
- campi `legacy_alias`
- campi `metadata_audit`

### A.1 Contratto canonico `NEW_SIGNAL`

```yaml
message_type: NEW_SIGNAL

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

  entry_text_raw: null
  stop_loss_raw: null
  targets_text_raw: null
  take_profits_text_raw: null
  market_context: null
  conditions: null
```

#### A.1.1 Campi canonici `NEW_SIGNAL`

I consumer downstream devono usare come fonte primaria:

- `symbol`
- `direction`
- `entry_type`
- `entry_structure`
- `entry_plan_entries`
- `stop_loss`
- `take_profits`

#### A.1.2 Alias legacy `NEW_SIGNAL`

Devono essere accettati in input transitorio ma non usati come fonte di verità:

- `side` -> `direction`
- `risk_pct` -> `risk_percent`
- `entry`
- `entries`
- `entry_range`
- `entry_range_low`
- `entry_range_high`
- `entry_type = AVERAGING`
- `entry_type = ZONE`

#### A.1.3 Metadata e audit `NEW_SIGNAL`

Questi campi restano utili per debugging, reportistica, audit o UI:

- `signal_id`
- `symbol_raw`
- `entry_order_type`
- `entry_plan_type`
- `entry_text_raw`
- `stop_loss_raw`
- `targets_text_raw`
- `take_profits_text_raw`
- `market_context`
- `conditions`
- `leverage_hint_raw`
- `reported_leverage_hint`

### A.2 Contratto canonico `UPDATE`

```yaml
message_type: UPDATE

entities:
  signal_id: null
  symbol: null
  symbol_raw: null
  direction: null

  new_sl_level: null
  new_sl_price: null
  new_sl_reference: null

  close_price: null
  close_pct: null
  partial_close_price: null

  reenter_entries: []
  reenter_entry_type: null

  new_entry_price: null
  new_entry_type: null

  old_entry_price: null
  modified_entry_price: null

  old_take_profits: []
  new_take_profits: []

  tp_hit_number: null
  reported_profit_r: null
  reported_profit_pct: null

  cancel_scope: null
  manual_close: null
  stop_price: null

  entry_plan_entries: []
  entry_range: []
  entry_range_low: null
  entry_range_high: null

  entry_text_raw: null
  stop_loss_raw: null
  targets_text_raw: null
  take_profits_text_raw: null
```

#### A.2.1 Campi canonici `UPDATE`

I consumer downstream devono usare come fonte primaria:

- `new_sl_level`
- `new_sl_price`
- `new_sl_reference`
- `close_price`
- `close_pct`
- `reenter_entries`
- `reenter_entry_type`
- `new_entry_price`
- `new_entry_type`
- `old_entry_price`
- `modified_entry_price`
- `old_take_profits`
- `new_take_profits`
- `tp_hit_number`
- `reported_profit_r`
- `reported_profit_pct`
- `cancel_scope`

#### A.2.2 Alias legacy `UPDATE`

Devono essere accettati in input transitorio ma convertiti:

- `new_stop_level` -> `new_sl_level`
- `new_stop_price` -> `new_sl_price`
- `new_stop_reference_text` -> `new_sl_reference`
- `partial_close_percent` -> `close_pct`
- `side` -> `direction`

#### A.2.3 Metadata e audit `UPDATE`

Restano utili ma non devono guidare la semantica core:

- `signal_id`
- `symbol`
- `symbol_raw`
- `direction`
- `manual_close`
- `stop_price`
- `entry_text_raw`
- `stop_loss_raw`
- `targets_text_raw`
- `take_profits_text_raw`

### A.3 Envelope comune a tutti i messaggi parser

Tutti i profili parser devono restituire un envelope coerente:

```yaml
message_type: NEW_SIGNAL | UPDATE | INFO_ONLY | UNCLASSIFIED
completeness: COMPLETE | INCOMPLETE | null
missing_fields: []

entities: {}

intents: []
target_refs: []
target_scope: {}

confidence: 0.0
warnings: []
diagnostics: {}
raw_text: ""
trader_id: ""
acquisition_mode: live | catchup
```

### A.4 Divergenze osservate oggi che questo contratto deve risolvere

Le principali incongruenze attuali osservate nei parser sono:

- `side` vs `direction`
- `risk_percent` vs `risk_pct` vs `risk_value_normalized`
- `new_sl_level` vs `new_stop_level`
- `close_pct` vs `partial_close_percent`
- `entry_plan_entries` presente solo in parte dei profili
- `entry_range_low/high` usati da alcuni parser al posto del piano canonico
- `entry_plan_type` con semantica troppo forte o troppo variabile tra profili

### A.5 Regole di standardizzazione

Devono diventare regole ufficiali del contratto parser:

- `direction` è il nome canonico; `side` è solo alias input/compatibilità
- `risk_percent` è il nome canonico
- `entry_plan_entries` è la fonte di verità del piano di ingresso
- `entry_plan_type` è solo metadata
- `entry_type` canonico: `MARKET | LIMIT`
- `entry_structure` canonico: `ONE_SHOT | TWO_STEP | RANGE | LADDER`
- `new_sl_*` è la famiglia canonica per gli update stop

### A.6 Criterio operativo per i parser

Ogni parser profilo-specifico deve:

1. Riempire sempre il contratto completo comune.
2. Valorizzare i campi canonici quando l'informazione esiste.
3. Valorizzare i campi non applicabili con vuoti canonici.
4. Tenere alias e metadata solo per compatibilità, audit o debugging.
5. Non introdurre nuovi campi profilo-specifici come fonte primaria downstream senza prima estendere il contratto canonico.

---

## Appendice B — Matrice `campo x trader`

Legenda:

- `OK` = campo già presente con semantica vicina al canonico
- `ALIAS` = informazione presente ma con nome o forma non canonica
- `META` = presente come metadata/audit, non ancora come campo canonico forte
- `MISS` = non osservato come output strutturato principale

### B.1 `NEW_SIGNAL`

| Campo | trader_a | trader_b | trader_c | trader_3 | trader_d | Note |
|---|---|---|---|---|---|---|
| `symbol` | OK | OK | OK | OK | OK | Campo base già abbastanza uniforme |
| `symbol_raw` | META | MISS | MISS | OK | OK | Non uniforme tra i profili |
| `direction` | ALIAS | ALIAS | ALIAS | ALIAS | ALIAS | Oggi prevale spesso `side` |
| `entry_type` | OK | OK | OK | OK | OK | Semantica da restringere a `MARKET | LIMIT` |
| `entry_structure` | OK | OK | OK | OK | OK | Migliorare solo la grammatica canonica |
| `entry_order_type` | META | OK | OK | MISS | OK | `trader_3` usa soprattutto range dedicato |
| `entry_plan_type` | META | META | META | META | META | Da mantenere solo diagnostico |
| `has_averaging_plan` | OK | OK | OK | OK | OK | Campo quasi uniforme |
| `entry_plan_entries` | OK | OK | MISS | MISS | OK | Gap principale da chiudere |
| `entry` | META | META | META | META | META | Da tenere solo per compatibilità |
| `entries` | META | MISS | OK | MISS | MISS | `trader_c` usa ancora questo come primario |
| `entry_range` | MISS | MISS | ALIAS | ALIAS | MISS | Da canonizzare come campo comune |
| `entry_range_low` | MISS | MISS | MISS | OK | MISS | Oggi quasi solo `trader_3` |
| `entry_range_high` | MISS | MISS | MISS | OK | MISS | Oggi quasi solo `trader_3` |
| `stop_loss` | OK | OK | OK | OK | OK | Campo base uniforme |
| `take_profits` | OK | OK | OK | OK | OK | Campo base uniforme |
| `risk_percent` | MISS | OK | ALIAS | MISS | OK | Canonico da consolidare |
| `risk_value_raw` | MISS | MISS | OK | MISS | OK | Audit field oggi non uniforme |
| `risk_value_normalized` | MISS | MISS | OK | MISS | OK | Audit/normalization field |
| `leverage` | MISS | MISS | MISS | MISS | MISS | Modello canonico esiste ma poco usato |
| `leverage_hint_raw` | MISS | MISS | MISS | OK | MISS | Presente soprattutto in `trader_3` |
| `reported_leverage_hint` | MISS | MISS | MISS | OK | MISS | Presente soprattutto in `trader_3` |
| `entry_text_raw` | MISS | OK | OK | OK | OK | Quasi uniforme salvo `trader_a` |
| `stop_loss_raw` | MISS | MISS | MISS | OK | MISS | Non uniforme |
| `targets_text_raw` | MISS | MISS | MISS | OK | MISS | Non uniforme |
| `take_profits_text_raw` | MISS | MISS | OK | MISS | MISS | Non uniforme |
| `market_context` | MISS | OK | MISS | MISS | MISS | Solo alcuni profili |

### B.2 `UPDATE`

| Campo | trader_a | trader_b | trader_c | trader_3 | trader_d | Note |
|---|---|---|---|---|---|---|
| `new_sl_level` | ALIAS | ALIAS | MISS | MISS | MISS | Oggi prevale famiglia `new_stop_*` |
| `new_sl_price` | MISS | ALIAS | ALIAS | MISS | MISS | Da uniformare |
| `new_sl_reference` | MISS | ALIAS | MISS | MISS | MISS | Da uniformare |
| `close_price` | META | MISS | MISS | MISS | MISS | Poco valorizzato come campo canonico |
| `close_pct` | MISS | MISS | ALIAS | MISS | MISS | `trader_c` usa `partial_close_percent` |
| `partial_close_price` | MISS | MISS | ALIAS | MISS | MISS | Oggi non canonico |
| `reenter_entries` | MISS | MISS | MISS | MISS | MISS | Non osservato come contratto uniforme |
| `reenter_entry_type` | MISS | MISS | MISS | MISS | MISS | Non osservato come contratto uniforme |
| `new_entry_price` | MISS | MISS | MISS | MISS | MISS | Non osservato in modo uniforme |
| `new_entry_type` | MISS | MISS | MISS | MISS | MISS | Non osservato in modo uniforme |
| `old_entry_price` | MISS | MISS | MISS | MISS | MISS | Non osservato in modo uniforme |
| `modified_entry_price` | MISS | MISS | MISS | MISS | MISS | Non osservato in modo uniforme |
| `old_take_profits` | MISS | MISS | MISS | MISS | MISS | Non osservato in modo uniforme |
| `new_take_profits` | MISS | MISS | ALIAS | MISS | MISS | `trader_c` ha update TP ma naming non unificato |
| `tp_hit_number` | META | MISS | MISS | MISS | MISS | Più vicino a metadata/report nei parser reali |
| `reported_profit_r` | OK | MISS | MISS | MISS | MISS | Forte soprattutto in `trader_a` |
| `reported_profit_pct` | MISS | MISS | MISS | MISS | MISS | Non uniforme |
| `cancel_scope` | OK | OK | MISS | MISS | MISS | Già usato downstream ma non nel modello canonico |
| `manual_close` | MISS | MISS | MISS | OK | MISS | Presente soprattutto in `trader_3` |
| `stop_price` | MISS | MISS | MISS | OK | MISS | `trader_3` reporting/update |
| `signal_id` | MISS | MISS | MISS | OK | MISS | Forte solo in `trader_3` |

### B.3 Priorità di convergenza

Le priorità di unificazione emerse dalla matrice sono:

1. Uniformare `direction` e smettere di usare `side` come nome primario.
2. Rendere `entry_plan_entries` obbligatorio per tutti i parser.
3. Canonizzare il blocco range:
   - `entry_structure = RANGE`
   - `entry_range`
   - `entry_range_low`
   - `entry_range_high`
4. Uniformare i campi di rischio:
   - `risk_percent`
   - `risk_value_raw`
   - `risk_value_normalized`
5. Uniformare gli update di stop:
   - `new_sl_level`
   - `new_sl_price`
   - `new_sl_reference`
6. Portare nel modello canonico i campi update già usati downstream:
   - `cancel_scope`
   - `manual_close`
   - `stop_price`
   - `signal_id`

### B.4 Profilo base consigliato

Come base del contratto comune conviene usare:

- struttura entry di `trader_a` per `entry_plan_entries`
- semplicità `ONE_SHOT` di `trader_b` / `trader_d`
- semantica `RANGE` di `trader_c` e `trader_3`
- metadata di leverage e `signal_id` di `trader_3`
- campi rischio più completi osservati in `trader_d`

Questa combinazione fornisce un superset realistico già presente nel codebase, senza inventare campi estranei al dominio corrente.

---

## Appendice C — Checklist implementativa file-per-file

Questa appendice traduce il PRD in una task list concreta per allineare:

- parser
- persistenza `parse_results`
- action builders
- report/export
- adapter verso il simulatore

### C.0 Stato reale del codebase

Le seguenti parti risultano già implementate o parzialmente implementate nel codice attuale e non devono essere pianificate come lavoro "da iniziare da zero":

- `state_machine.py`
  - esiste già `normalize_entry_semantics()`
  - gestisce già:
    - `SINGLE -> ONE_SHOT`
    - `ZONE -> LIMIT + RANGE`
    - `AVERAGING -> LIMIT + TWO_STEP/LADDER`
    - `entry_plan_type` legacy come fallback di compatibilità

- `trader_a`
  - usa già `entry_structure = ONE_SHOT | TWO_STEP`
  - usa già `entry_type` canonico `MARKET | LIMIT`

- `trader_b`
  - usa già `entry_type`
  - usa già `entry_structure = ONE_SHOT`
  - usa già `entry_plan_entries`

- `trader_d`
  - deriva già `entry_type` canonico da `entry_order_type`

- `trader_3`
  - usa già `entry_structure = RANGE`
  - non usa più `SINGLE` come semantica primaria del range

- persistenza DB
  - `parse_result_normalized_json` esiste già ed è il punto corretto per ospitare il contratto canonico completo

Conclusione operativa:

- lato `entry semantics` una parte importante del refactor è già avviata
- il lavoro ancora aperto è concentrato soprattutto su:
  - contratto completo parser
  - `UPDATE`
  - report / flatteners
  - action builders
  - chain reconstruction

### C.1 Modelli canonici parser

File:

- `src/signal_chain_lab/parser/models/new_signal.py`
- `src/signal_chain_lab/parser/models/update.py`

Task:

- `NEW_SIGNAL`
  - rendere `direction` il campo canonico esplicito
  - deprecare semanticamente `entry_type = AVERAGING | ZONE`
  - consolidare a livello di modello e documentazione `entry_structure = ONE_SHOT | TWO_STEP | RANGE | LADDER`
  - ufficializzare come parte stabile del contratto:
    - `entry_plan_entries`
    - `entry_range`
    - `risk_percent`
    - `risk_value_raw`
    - `risk_value_normalized`

- `UPDATE`
  - introdurre ufficialmente nel modello canonico:
    - `new_sl_level`
    - `new_sl_price`
    - `new_sl_reference`
    - `partial_close_price`
    - `cancel_scope`
    - `manual_close`
    - `stop_price`
    - `signal_id`
  - mantenere fallback legacy per:
    - `new_stop_level`
    - `new_stop_price`
    - `new_stop_reference_text`
    - `partial_close_percent`

### C.2 Parser profilo-specifici

File area:

- `src/signal_chain_lab/parser/trader_profiles/trader_a/profile.py`
- `src/signal_chain_lab/parser/trader_profiles/trader_b/profile.py`
- `src/signal_chain_lab/parser/trader_profiles/trader_c/profile.py`
- `src/signal_chain_lab/parser/trader_profiles/trader_3/profile.py`
- `src/signal_chain_lab/parser/trader_profiles/trader_d/profile.py`

Task comuni:

- valorizzare sempre `direction`, non `side`, come campo primario
- valorizzare sempre `entry_plan_entries`
- valorizzare i campi non applicabili con vuoti canonici
- usare naming update canonico `new_sl_*`

Task specifici:

- `trader_a`
  - mantenere la struttura ricca di `entry_plan_entries`
  - ridurre il ruolo operativo di `entry_plan_type`

- `trader_b`
  - mantenere l'assetto già canonico `ONE_SHOT`
  - mantenere `entry_plan_entries` come fonte primaria

- `trader_c`
  - convertire `entries` nel formato canonico `entry_plan_entries`
  - mantenere `entries` solo come compatibilità
  - mantenere `RANGE` e `LADDER` come strutture canoniche

- `trader_3`
  - costruire `entry_plan_entries` anche per i casi `RANGE`
  - emettere `direction` come campo primario al posto di `side`
  - mantenere `entry_range_low/high` come metadata o compatibilità

- `trader_d`
  - mantenere l'assetto già canonico `ONE_SHOT`
  - mantenere `entry_plan_entries`
  - allineare naming update a `new_sl_*`

### C.3 Normalizzazione centrale

File:

- `src/signal_chain_lab/engine/state_machine.py`

Task:

- mantenere e rifinire `normalize_entry_semantics()` già esistente
- aggiungere normalizzazione generale per:
  - `side -> direction`
  - `new_stop_* -> new_sl_*`
  - `partial_close_percent -> close_pct`
- far avvenire la normalizzazione prima dei consumer downstream

### C.4 Action builders

File:

- `src/signal_chain_lab/parser/action_builders/canonical_v2.py`

Task:

- usare `direction` come fonte primaria con fallback `side`
- per `MOVE_STOP`:
  - leggere prima `new_sl_level`
  - poi fallback `new_stop_level`
  - leggere prima `new_sl_price`
  - poi fallback `new_stop_price`
  - leggere prima `new_sl_reference`
  - poi fallback `new_stop_reference_text`
- per `CLOSE_PARTIAL`:
  - leggere prima `close_pct`
  - fallback `partial_close_percent`
- per `CREATE_SIGNAL`:
  - usare `entry_plan_entries` come fonte primaria
  - fallback `entries` / `entry` solo in transizione

### C.5 Persistenza `parse_results`

File:

- `src/signal_chain_lab/storage/parse_results.py`

Task:

- continuare a usare `parse_result_normalized_json` come payload autorevole
- garantire che il JSON salvato sia già nel formato canonico normalizzato
- mantenere le colonne storiche del DB come supporto minimo/legacy

Nota:

- non è richiesta una migrazione ampia del DB per introdurre il contratto canonico parser

### C.6 Report flatteners

File:

- `parser_test/reporting/flatteners.py`

Task:

- `direction`
  - usare `normalized["direction"]`
  - fallback `entities["direction"]`
  - solo infine fallback `entities["side"]`

- stop update
  - leggere prima `new_sl_level`
  - fallback `new_stop_level`
  - se utile aggiungere anche:
    - `new_sl_price`
    - `new_sl_reference`

- partial close
  - leggere `close_pct`
  - fallback legacy

- entry
  - usare `entry_plan_entries` come sorgente principale per `entries_summary`

- rischio/leverage
  - leggere `risk_percent`
  - fallback `risk_value_normalized`
  - mantenere `reported_leverage_hint`

### C.7 Report schema CSV

File:

- `parser_test/reporting/report_schema.py`

Task:

- decidere strategia per lo stop update nei CSV:
  - breve termine: mantenere `new_stop_level` ma popolarlo dal canonico `new_sl_level`
  - medio termine: introdurre colonne canoniche:
    - `new_sl_level`
    - `new_sl_price`
    - `new_sl_reference`

Raccomandazione:

- compatibilità nel breve
- schema più pulito nel medio termine

### C.8 Chain builder e adapter

File:

- `src/signal_chain_lab/adapters/chain_builder.py`
- `src/signal_chain_lab/adapters/chain_adapter.py`

Task:

- mantenere `side` come campo operativo verso il simulatore
- derivarlo da `direction` quando il parser fornisce il dato canonico
- mantenere nel payload:
  - `entry_plan_entries`
  - `entry_structure`
  - `has_averaging_plan`
- aggiornare `_update_payload()` per usare i campi `new_sl_*` canonici

### C.8.b Nota esplicita su Chain reconstruction

La chain reconstruction è esplicitamente nel perimetro dell'intervento.

Questo significa che:

- non basta aggiornare i parser
- non basta aggiornare il report
- va aggiornato anche il layer che ricostruisce la `SignalChain` a partire da:
  - `raw_messages`
  - `parse_results`
  - `operational_signals`

Impatto atteso:

- `chain_builder.py` deve leggere correttamente il payload canonico salvato in `parse_result_normalized_json`
- `chain_adapter.py` deve convertire il contratto parser canonico nel payload operativo richiesto dal simulatore
- il mapping `direction -> side` deve essere esplicito e stabile
- i campi entry canonici devono attraversare correttamente la ricostruzione:
  - `entry_type`
  - `entry_structure`
  - `entry_plan_entries`
  - `has_averaging_plan`
- i campi update canonici devono attraversare correttamente la ricostruzione:
  - `new_sl_level`
  - `new_sl_price`
  - `new_sl_reference`
  - `close_pct`
  - `cancel_scope`
  - `signal_id`

Nota importante:

- la chain reconstruction va aggiornata come consumer del nuovo contratto canonico
- non è richiesto un redesign completo del dominio `SignalChain`
- il suo ruolo è fare da ponte robusto tra parser canonico e simulatore, mantenendo compatibilità con i dati storici

### C.9 Boundary DB / dominio backtest

Area:

- migrazioni DB storiche
- dominio `SignalChain`
- simulatore

Task:

- non rinominare subito `side` nelle tabelle e nel dominio storico
- formalizzare il mapping:
  - parser canonical name = `direction`
  - simulator / domain operational name = `side`
- mantenere adapter espliciti tra i due livelli

### C.10 Test

Da aggiornare:

- test parser profilo-specifici
- test action builders
- test reporting/export
- test adapter/simulator integration

Copertura minima:

- `direction` valorizzato e riportato correttamente
- `new_sl_*` valorizzato e visibile nei report
- `entry_plan_entries` presente in tutti i parser
- `RANGE`, `TWO_STEP`, `LADDER`, `ONE_SHOT` arrivano correttamente a report e simulatore
- fallback legacy ancora funzionante sui dataset storici

### C.11 Ordine consigliato di esecuzione

1. Modelli canonici parser
2. Action builders
3. Flatteners / report
4. Parser profilo-specifici
5. Adapter chain
6. Test automatici e replay `parser_test`
