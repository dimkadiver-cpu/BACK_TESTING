# PRD — Unificazione semantica degli ingressi (`entry_type`, `entry_structure`, `entry_plan_type`)

Documento tecnico aggiornato: 2026-04-11.

---

## 1. Obiettivo

Questo PRD definisce la unificazione della semantica degli ingressi nel parser e nel simulatore di `Signal Chain Lab`.

L'obiettivo è eliminare ridondanze e ambiguità tra:

- `entry_type`
- `entry_structure`
- `entry_plan_type`
- semantiche legacy come `AVERAGING` e `ZONE`

e sostituirle con un modello canonico unico, stabile e facilmente dispatchabile dal core.

Il risultato atteso è:

- una sola rappresentazione canonica del piano di ingresso
- regole di dispatch semplici e deterministiche nel simulatore
- parser profilo-specifici allineati alla stessa semantica
- policy `entry_split` più pulita e meno ridondante
- backward compatibility gestita tramite normalizzazione e deprecazione graduale

---

## 2. Problema attuale

Oggi il sistema mescola tre livelli semantici diversi:

- il tipo ordine principale, espresso da `entry_type`
- la forma del piano di ingresso, espressa in parte da `entry_structure`
- una label descrittiva o ibrida, espressa da `entry_plan_type`

Esempi osservati:

- `entry_structure = SINGLE`
- `entry_structure = ONE_SHOT`
- `entry_structure = TWO_STEP`
- `entry_structure = RANGE`
- `entry_structure = LADDER`
- `entry_type = AVERAGING`
- `entry_type = ZONE`
- `entry_plan_type = SINGLE_MARKET`
- `entry_plan_type = LIMIT_WITH_LIMIT_AVERAGING`

Questo produce i seguenti problemi:

- `SINGLE` e `ONE_SHOT` descrivono quasi lo stesso concetto
- `AVERAGING` è usato come tipo di entry, ma rappresenta in realtà una struttura multi-entry
- `ZONE` e `RANGE` sono semanticamente vicini e nel simulatore hanno forte sovrapposizione
- il simulatore dispatcha oggi usando un mix di `entry_type`, `entry_structure`, `entry_plan_type` e `has_averaging_plan`
- parte della semantica è implicita nelle stringhe, per esempio `"AVERAGING" in entry_plan_type`
- la policy contiene rami che riflettono sia il dominio reale sia residui legacy

Conseguenza pratica: il comportamento è difficile da spiegare, testare e mantenere.

---

## 3. Stato corrente osservato

### 3.1 Parser

I parser profilo-specifici emettono attualmente combinazioni diverse:

- `trader_a`
  - `SINGLE_MARKET`
  - `SINGLE_LIMIT`
  - `MARKET_WITH_LIMIT_AVERAGING`
  - `LIMIT_WITH_LIMIT_AVERAGING`
  - `entry_structure = SINGLE | TWO_STEP`

- `trader_b`
  - `entry_plan_type = SINGLE`
  - `entry_structure = ONE_SHOT`

- `trader_c`
  - `entry_structure = RANGE`
  - `entry_structure = LADDER`
  - `entry_plan_type = SINGLE | MULTI`

- `trader_3`
  - `entry_plan_type = SINGLE`
  - `entry_structure = RANGE`
  - `has_averaging_plan = False`

- `trader_d`
  - `SINGLE_MARKET`
  - `SINGLE`
  - `entry_structure = ONE_SHOT`

### 3.2 Simulatore

Il simulatore dispatcha i pesi ingresso usando:

- `entry_structure == RANGE` -> `LIMIT.range`
- `entry_structure == LADDER` -> `LIMIT.ladder`
- `has_averaging_plan` o `"AVERAGING"` in `entry_plan_type` -> `LIMIT.averaging`
- `entry_type == MARKET` -> `MARKET.single/averaging`
- `entry_type in {LIMIT, AVERAGING}` -> `LIMIT.single/averaging`
- `entry_type == ZONE` -> `ZONE.weights`

### 3.3 Policy

Nel blocco `entry.entry_split` oggi convivono:

- `LIMIT.single`
- `LIMIT.range`
- `LIMIT.averaging`
- `LIMIT.ladder`
- `MARKET.single`
- `MARKET.averaging`
- `ZONE`
- residui legacy `AVERAGING` in alcuni contesti/repo

---

## 4. Decisione di prodotto

La rappresentazione canonica del piano di ingresso deve essere basata su:

- `entry_type`
- `entry_structure`
- `entry_plan_entries`

`entry_plan_type` non deve più essere una fonte di verità del core. Può restare come campo derivato, diagnostico o transitorio, ma non deve guidare la logica principale.

---

## 5. Modello canonico target

### 5.1 Campo `entry_type`

`entry_type` deve esprimere solo la natura dell'ordine principale.

Valori canonici ammessi:

- `MARKET`
- `LIMIT`

Valori legacy ammessi solo in input transitorio:

- `AVERAGING`
- `ZONE`

Semantica:

- `MARKET`: il primo leg operativo del piano è market
- `LIMIT`: il primo leg operativo del piano è limit

### 5.2 Campo `entry_structure`

`entry_structure` deve esprimere solo la geometria del piano di ingresso.

Valori canonici ammessi:

- `ONE_SHOT`
- `TWO_STEP`
- `RANGE`
- `LADDER`

Semantica:

- `ONE_SHOT`: un solo ingresso operativo
- `TWO_STEP`: due ingressi operativi con semantica primary + averaging
- `RANGE`: una fascia di prezzo definita da due estremi
- `LADDER`: più livelli discreti già espliciti nel payload

### 5.3 Campo `entry_plan_entries`

`entry_plan_entries` diventa il dettaglio operativo autorevole.

Ogni elemento deve includere almeno:

- `sequence`
- `role`
- `order_type`
- `price` se applicabile

Esempio:

```yaml
entry_type: MARKET
entry_structure: TWO_STEP
entry_plan_entries:
  - sequence: 1
    role: PRIMARY
    order_type: MARKET
    price: null
  - sequence: 2
    role: AVERAGING
    order_type: LIMIT
    price: 98234.5
```

### 5.4 Campo `entry_plan_type`

`entry_plan_type` diventa:

- opzionale
- derivato
- non usato dal core per il dispatch

Può essere mantenuto per:

- logging
- debugging
- retrocompatibilità temporanea
- export verso report storici

---

## 6. Normalizzazione canonica

Prima che il simulatore elabori il payload, deve essere eseguita una normalizzazione che converte il formato legacy nel formato canonico.

### 6.1 Regole di mapping

| Input legacy | Output canonico |
|---|---|
| `entry_structure = SINGLE` | `entry_structure = ONE_SHOT` |
| `entry_plan_type = SINGLE_MARKET` | `entry_structure = ONE_SHOT`, `entry_type = MARKET` |
| `entry_plan_type = SINGLE_LIMIT` | `entry_structure = ONE_SHOT`, `entry_type = LIMIT` |
| `entry_plan_type = MARKET_WITH_LIMIT_AVERAGING` | `entry_structure = TWO_STEP`, `entry_type = MARKET` |
| `entry_plan_type = LIMIT_WITH_LIMIT_AVERAGING` | `entry_structure = TWO_STEP`, `entry_type = LIMIT` |
| `entry_type = AVERAGING` con 2 entry | `entry_type = LIMIT`, `entry_structure = TWO_STEP` |
| `entry_type = AVERAGING` con 3+ entry | `entry_type = LIMIT`, `entry_structure = LADDER` |
| `entry_type = ZONE` | `entry_type = LIMIT`, `entry_structure = RANGE` |

### 6.2 Regole di inferenza minime

Se il payload non è completo, la normalizzazione deve inferire i campi mancanti in ordine prudente:

1. Se `entry_plan_entries` contiene 1 solo livello -> `ONE_SHOT`
2. Se contiene 2 livelli con ruolo primary + averaging -> `TWO_STEP`
3. Se la struttura è chiaramente un intervallo low/high -> `RANGE`
4. Se contiene 3+ livelli discreti -> `LADDER`

Se non è possibile inferire senza ambiguità:

- generare warning esplicito
- usare fallback documentato
- non introdurre logica implicita silenziosa

---

## 7. Dispatch target nel simulatore

Il simulatore deve dispatchare il blocco policy degli ingressi usando quasi esclusivamente `entry_structure`, con `entry_type` usato solo per distinguere `MARKET` da `LIMIT` nei casi applicabili.

### 7.1 Regole target

- `ONE_SHOT`
  - se `entry_type = MARKET` -> `MARKET.single`
  - se `entry_type = LIMIT` -> `LIMIT.single`

- `TWO_STEP`
  - se il primo leg è market -> `MARKET.averaging`
  - altrimenti -> `LIMIT.averaging`

- `RANGE`
  - usa `LIMIT.range`

- `LADDER`
  - usa `LIMIT.ladder`

### 7.2 Regole da eliminare dal core

Devono essere rimosse o deprecate dal dispatch principale:

- `entry_type == AVERAGING`
- `entry_type == ZONE`
- controlli basati su substring come `"AVERAGING" in entry_plan_type`
- dipendenze implicite da `entry_plan_type` come fonte di verità

---

## 8. Policy target

### 8.1 Struttura target di `entry_split`

La policy target deve essere:

```yaml
entry:
  entry_split:
    LIMIT:
      single:
        weights:
          E1: 1.0
      range:
        split_mode: endpoints
        weights:
          E1: 0.50
          E2: 0.50
      averaging:
        weights:
          E1: 0.70
          E2: 0.30
      ladder:
        weights:
          E1: 0.50
          E2: 0.30
          E3: 0.20
    MARKET:
      single:
        weights:
          E1: 1.0
      averaging:
        weights:
          E1: 0.70
          E2: 0.30
```

### 8.2 Blocchi da deprecare

Devono essere deprecati:

- `entry_split.AVERAGING`
- `entry_split.ZONE`

### 8.3 Gestione di `ZONE`

Decisione proposta:

- `ZONE` deve sopravvivere solo come alias parser-side o input legacy
- durante la normalizzazione deve essere convertito in `entry_structure = RANGE`
- il ramo policy dedicato `entry_split.ZONE` deve essere eliminato a regime

Nota:

- se si desidera mantenere `ZONE` come concetto descrittivo a livello UI/report, lo si può preservare come metadata non operativo

---

## 9. Impatti sui parser

### 9.1 Obiettivo parser

Ogni parser profilo-specifico deve emettere il formato canonico direttamente, senza richiedere che il simulatore interpreti label legacy.

### 9.2 Cambiamenti richiesti

#### `trader_a`

- sostituire `entry_structure = SINGLE` con `ONE_SHOT`
- mantenere `TWO_STEP` per primary + averaging
- mantenere `entry_plan_entries` come fonte autorevole
- impostare `entry_type` in base al primo leg del piano
- rendere `entry_plan_type` derivato e non centrale

#### `trader_b`

- confermare `ONE_SHOT`
- garantire `entry_type` coerente con `order_type`
- non usare label generiche come `SINGLE` come fonte semantica

#### `trader_c`

- mantenere `RANGE`
- mantenere `LADDER`
- evitare sovrapposizione implicita con `ZONE`
- garantire che il parser produca `entry_plan_entries` coerenti con la struttura

#### `trader_3`

- mantenere `RANGE` come struttura canonica
- sostituire eventuale semantica `SINGLE` con `ONE_SHOT` solo dove il piano ha davvero un solo punto operativo
- non usare `entry_plan_type = SINGLE` come fonte semantica quando la struttura reale è `RANGE`
- garantire che il payload canonico distingua chiaramente tra:
  - fascia di prezzo `RANGE`
  - ingresso singolo `ONE_SHOT`

#### `trader_d`

- eliminare `SINGLE` in favore di `ONE_SHOT`
- allineare `SINGLE_MARKET` a campo derivato, non autorevole

### 9.3 Contratto parser aggiornato

Ogni `CREATE_SIGNAL` deve produrre sempre, quando disponibile:

- `entry_type`
- `entry_structure`
- `entry_plan_entries`
- `has_averaging_plan` solo se ancora utile per compatibilità, non come semantica primaria

---

## 10. Impatti sul simulatore

### 10.1 Funzione di normalizzazione

Va introdotta una funzione dedicata, per esempio:

- `normalize_entry_semantics(payload: dict[str, Any]) -> dict[str, Any]`

Responsabilità:

- convertire i valori legacy nel formato canonico
- garantire la presenza di `entry_type` e `entry_structure` coerenti
- derivare eventualmente `entry_plan_type` per compatibilità
- emettere warning quando il payload è ambiguo o legacy

### 10.2 Punto di chiamata

La normalizzazione deve avvenire:

- prima di `_entry_specs_from_payload()`
- idealmente subito all'ingresso del payload nello state machine

### 10.3 Refactor `_weights_from_policy`

`_weights_from_policy()` deve essere semplificata in modo che:

- il branch principale dipenda da `entry_structure`
- `entry_type` serva solo per distinguere `MARKET` vs `LIMIT` nei casi `ONE_SHOT` e `TWO_STEP`
- non esistano più branch core per `ZONE` e `AVERAGING`

### 10.4 Refactor `_entry_specs_from_payload`

`_entry_specs_from_payload()` deve:

- assumere che il payload sia già normalizzato
- usare `entry_plan_entries` come fonte principale
- usare fallback su `entries` solo in transizione
- trattare `RANGE` come struttura canonica di fascia

---

## 11. Migrazione della configurazione

### 11.1 Config da aggiornare

I file policy devono essere aggiornati per rimuovere progressivamente:

- `entry_split.AVERAGING`
- `entry_split.ZONE`

La configurazione raccomandata deve basarsi solo su:

- `LIMIT.single`
- `LIMIT.range`
- `LIMIT.averaging`
- `LIMIT.ladder`
- `MARKET.single`
- `MARKET.averaging`

### 11.2 Compatibilità transitoria

Nel periodo di migrazione:

- i blocchi legacy ancora presenti devono generare `DeprecationWarning`
- se usati, devono essere convertiti internamente nel comportamento equivalente canonico
- la documentazione deve chiarire che non rappresentano più la semantica target

---

## 12. Strategia di rollout

### Fase 1 — Introduzione del formato canonico

- introdurre la funzione di normalizzazione
- aggiornare il simulatore per usare il formato canonico
- mantenere retrocompatibilità con warning

### Fase 2 — Allineamento parser

- aggiornare `trader_a`, `trader_b`, `trader_c`, `trader_d`
- far emettere `ONE_SHOT`, `TWO_STEP`, `RANGE`, `LADDER`
- ridurre l'uso operativo di `entry_plan_type`

### Fase 3 — Pulizia policy e docs

- rimuovere esempi legacy dalle policy template
- aggiornare `Supporto simulatore.md`
- aggiornare `data-contracts.md`
- aggiornare eventuali PRD o template che ancora descrivono `AVERAGING` o `ZONE` come semantiche core

### Fase 4 — Rimozione definitiva compatibilità legacy

- rimuovere branch core per `entry_type = AVERAGING`
- rimuovere branch core per `entry_type = ZONE`
- rimuovere `entry_split.ZONE`
- rimuovere uso di `entry_plan_type` nel dispatch

---

## 13. Test da aggiungere o aggiornare

### 13.1 Test unitari normalizzazione

Copertura minima:

- `SINGLE` -> `ONE_SHOT`
- `SINGLE_MARKET` -> `ONE_SHOT + MARKET`
- `SINGLE_LIMIT` -> `ONE_SHOT + LIMIT`
- `MARKET_WITH_LIMIT_AVERAGING` -> `TWO_STEP + MARKET`
- `LIMIT_WITH_LIMIT_AVERAGING` -> `TWO_STEP + LIMIT`
- `AVERAGING` con 2 entry -> `TWO_STEP`
- `AVERAGING` con 3+ entry -> `LADDER`
- `ZONE` -> `RANGE`

### 13.2 Test simulatore

Copertura minima:

- `ONE_SHOT + MARKET` usa `MARKET.single`
- `ONE_SHOT + LIMIT` usa `LIMIT.single`
- `TWO_STEP + MARKET` usa `MARKET.averaging`
- `TWO_STEP + LIMIT` usa `LIMIT.averaging`
- `RANGE` usa `LIMIT.range`
- `LADDER` usa `LIMIT.ladder`

### 13.3 Test parser profilo-specifici

Aggiornare i test in modo che verifichino:

- emissione della struttura canonica
- coerenza tra `entry_type`, `entry_structure` e `entry_plan_entries`
- eventuale corretto mantenimento di `entry_plan_type` come campo derivato

### 13.4 Test di compatibilità

Serve una suite transitoria che verifichi:

- payload legacy ancora accettati
- warning emessi correttamente
- comportamento operativo equivalente al formato nuovo

---

## 14. Criteri di accettazione

La feature è considerata completata quando:

1. Il simulatore dispatcha il sizing entry senza dipendere da string matching su `entry_plan_type`.
2. `entry_structure` usa solo i valori canonici:
   - `ONE_SHOT`
   - `TWO_STEP`
   - `RANGE`
   - `LADDER`
3. `entry_type = AVERAGING` e `entry_type = ZONE` non sono più necessari al core.
4. `entry_split.AVERAGING` e `entry_split.ZONE` sono deprecati e documentati come tali.
5. I parser principali emettono il formato canonico in uscita.
6. Le policy template ufficiali non contengono più semantiche legacy operative.
7. Esiste copertura test automatica per mapping, dispatch e compatibilità.

---

## 15. Rischi e attenzioni

### 15.1 Rischio di regressione silenziosa

Cambiare semantica dei campi di ingresso può alterare:

- sizing delle entry
- numero di livelli operativi
- comportamento dei piani two-step
- interpretazione delle zone

Mitigazione:

- test golden su casi reali
- confronti before/after su dataset storico
- warning espliciti in presenza di mapping legacy

### 15.2 Rischio di mismatch parser/simulatore

Se i parser vengono aggiornati ma il simulatore resta ibrido, o viceversa, il sistema può produrre risultati incoerenti.

Mitigazione:

- introdurre prima la normalizzazione centralizzata
- far convergere tutti i consumer sullo stesso payload canonico

### 15.3 Rischio documentale

Le policy e i docs potrebbero continuare a descrivere semantiche non più operative.

Mitigazione:

- aggiornamento coordinato di template, docs e checklist

---

## 16. Non obiettivi

Questo PRD non introduce:

- nuove logiche di sizing
- nuovi algoritmi di split range
- nuovi tipi ordine avanzati
- nuove semantiche multi-leg oltre a `ONE_SHOT`, `TWO_STEP`, `RANGE`, `LADDER`

Non fa parte di questo intervento:

- redesign del blocco TP
- redesign del blocco pending
- redesign del parser updates, salvo il minimo necessario per coerenza contrattuale

---

## 17. Raccomandazione finale

La raccomandazione è adottare come semantica core:

- `entry_type` = natura dell'ordine principale
- `entry_structure` = forma del piano
- `entry_plan_entries` = dettaglio operativo

e trattare:

- `entry_plan_type`
- `AVERAGING`
- `ZONE`
- `SINGLE`

come compatibilità legacy o metadata derivati, non come fondamento del core.

Questa scelta riduce la complessità, rende il dispatch esplicito e allinea meglio parser, policy e simulatore a una sola grammatica di dominio.

---

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

### C.1 Modelli canonici parser

File:

- `src/signal_chain_lab/parser/models/new_signal.py`
- `src/signal_chain_lab/parser/models/update.py`

Task:

- `NEW_SIGNAL`
  - rendere `direction` il campo canonico esplicito
  - deprecare semanticamente `entry_type = AVERAGING | ZONE`
  - documentare `entry_structure = ONE_SHOT | TWO_STEP | RANGE | LADDER`
  - aggiungere o ufficializzare:
    - `entry_plan_entries`
    - `entry_range`
    - `risk_percent`
    - `risk_value_raw`
    - `risk_value_normalized`

- `UPDATE`
  - introdurre ufficialmente:
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
  - consolidare `ONE_SHOT`
  - mantenere `entry_plan_entries` come fonte primaria

- `trader_c`
  - convertire `entries` nel formato canonico `entry_plan_entries`
  - mantenere `entries` solo come compatibilità
  - mantenere `RANGE` e `LADDER` come strutture canoniche

- `trader_3`
  - costruire `entry_plan_entries` anche per i casi `RANGE`
  - mantenere `entry_range_low/high` come metadata o compatibilità

- `trader_d`
  - consolidare `ONE_SHOT`
  - mantenere `entry_plan_entries`
  - allineare naming update a `new_sl_*`

### C.3 Normalizzazione centrale

File:

- `src/signal_chain_lab/engine/state_machine.py`

Task:

- mantenere e rifinire `normalize_entry_semantics()`
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
