# PRD — Refinement incrementale del pannello Market DATA e del flusso Backtest

## 1. Obiettivo

Rifinire l’implementazione attuale del pannello **Market DATA** del repository `BACK_TESTING` senza stravolgere la struttura introdotta di recente.

L’obiettivo è portare il comportamento operativo a questo modello:

1. selezione DB segnali/parsing;
2. selezione cartella market data;
3. scelta modalità cartella:
   - riuso cartella esistente;
   - nuova cartella/base;
4. click **Analizza**;
5. visualizzazione chiara di:
   - simboli rilevati;
   - timeframe richiesti;
   - tipi dati richiesti;
   - gap mancanti;
   - simboli non supportati / non scaricabili;
6. click **Prepara**;
7. preparazione dei soli gap mancanti;
8. validazione opzionale secondo modalità esplicita;
9. click **Backtest**;
10. esecuzione backtest solo se Market DATA è in stato coerente.

Questo PRD è **incrementale**: deve preservare i pulsanti e il layout già esistenti dove possibile.

---

## 2. Stato attuale verificato

## 2.1 Struttura GUI attuale

Nel tab **Blocco 3 - Backtest** esistono già due sezioni separate:

- pannello **Market DATA**;
- pannello **Backtest**.

Questa separazione è corretta e deve essere mantenuta.

### Pulsanti già presenti nel pannello Market DATA

- `Sfoglia` cartella market data
- radio:
  - `Usa cartella esistente e integra i gap mancanti`
  - `Prepara da capo in una nuova cartella`
- `Analizza`
- `Prepara`
- `Valida`
- `Prepara + Valida`

### Pulsanti già presenti nel pannello Backtest

- `Sfoglia` DB parsato
- `Ricarica / Modifica / Nuova` policy
- `Rileva` trader
- `Sfoglia` cartella report
- `Esegui Backtest`

Questi controlli devono rimanere.

---

## 2.2 Capacità tecniche attuali già presenti

### Già presenti e corrette

1. **Analizza separato da Backtest**
   - `Analizza` lancia il planner senza avviare il backtest.

2. **Backtest non auto-prepara più i dati**
   - il backtest verifica `market_ready` e, se falso, chiede di usare il pannello Market DATA.

3. **Supporto multi-timeframe in planner e sync**
   - esistono:
     - `download_tfs`
     - `simulation_tf`
     - `detail_tf`
   - il planner costruisce finestre e gap per timeframe richiesti.
   - lo sync scarica per `symbol + basis + timeframe`.

4. **Supporto a data type UI**
   - `OHLCV last`
   - `OHLCV mark`
   - `Funding rate`

5. **Supporto funding pipeline dedicata**
   - esistono script separati per sync/validate funding.

---

## 2.3 Problemi ancora aperti

### Problema A — `Prepara` non significa “solo preparazione gap`
Attualmente `Prepara` esegue:

- planner
- sync
- gap validation

Quindi non è un puro step di preparazione/download.

### Problema B — modalità `validate_mode = off` semanticamente incoerente
Attualmente `Prepara + Valida` con modalità `off` non scarica nulla e marca il dataset come pronto/fidato.

Questo non corrisponde al comportamento desiderato:

- `Off` deve significare: **prepara/scarica senza validazione**
- non: **non fare nulla e fidati**

### Problema C — validazione non ancora completamente allineata al multi-timeframe
Planner e sync lavorano sui timeframe richiesti.

Ma `gap_validate_market_data.py` e `validate_market_data.py` non validano ancora in modo coerente tutti i blocchi `timeframes[tf]` del piano.

Effetto:

- planner/sync vedono i gap per TF;
- validate/gap_validate lavorano ancora in parte sul livello top-level;
- il sistema non è pienamente coerente su `download_tfs + simulation_tf + detail_tf`.

### Problema D — cache di validazione incompleta rispetto al nuovo setup
Il fingerprint della validation cache considera ancora un contesto troppo ridotto:

- DB
- filtri
- cartella
- un solo timeframe
- una sola basis
- source

Non rappresenta pienamente:

- `download_tfs`
- `simulation_tf`
- `detail_tf`
- data types attivi
- funding attivo/disattivo
- validate mode
- buffer mode / preset / pre/post buffer

### Problema E — reporting di Analizza ancora poco esplicito
Il pannello mostra un riepilogo, ma manca una vista chiara e robusta di:

- simboli con copertura completa;
- simboli con gap;
- simboli non supportati / skipped;
- gap distinti per TF e tipo dato;
- funding richiesto / non richiesto / mancante.

### Problema F — gestione simboli non supportati troppo bloccante
Se il downloader produce `skipped` su simboli non riconosciuti/non supportati, la pipeline può finire in FAIL globale.

Serve distinguere:

- errore reale di sync;
- simbolo non supportato;
- dato opzionale non disponibile;
- gap rimasto aperto.

---

## 3. Obiettivo di questa implementazione

Portare il pannello Market DATA a una semantica operativa stabile e leggibile **senza cambiare i pulsanti principali già introdotti**.

### Comportamento target

#### `Analizza`
Solo analisi.

Non deve:

- scaricare;
- validare;
- modificare parquet;
- marcare dataset come ready.

Deve restituire:

- simboli rilevati;
- timeframe richiesti;
- tipi dati richiesti;
- gap mancanti;
- simboli non supportati / non scaricabili;
- funding richiesto / non richiesto;
- stato cartella (vuota, parziale, completa, incoerente).

#### `Prepara`
Solo preparazione dei dati mancanti.

Deve:

- lanciare planner;
- scaricare solo i gap mancanti;
- eseguire sync funding se richiesto;
- **non** eseguire validate full;
- **non** forzare gap validation se la modalità è `off`.

#### `Valida`
Solo validazione del dataset già presente.

Deve:

- validare OHLCV richiesti per tutti i TF richiesti;
- validare funding se richiesto;
- aggiornare stato di readiness/validation.

#### `Prepara + Valida`
Pipeline completa.

Deve:

- eseguire prepare;
- poi validate;
- rispettare la modalità di validazione selezionata.

#### `Esegui Backtest`
Deve limitarsi a:

- verificare che lo stato market sia compatibile;
- usare il dataset già preparato;
- non attivare prepare/validate implicitamente.

---

## 4. Vincoli di implementazione

## 4.1 Non stravolgere la UI

Non va fatta una nuova UX da zero.

Devono essere conservati:

- pannello `Market DATA`
- pannello `Backtest`
- pulsanti esistenti
- radio modalità cartella
- campi timeframe/data type
- log panel dedicato

## 4.2 Modifica minima, ma coerente

Cambiare la semantica interna dei pulsanti dove necessario, evitando rinominazioni inutili.

## 4.3 No automazioni implicite nel Backtest

Il backtest non deve più preparare dati automaticamente.

Questo comportamento attuale corretto va mantenuto.

---

## 5. Requisiti funzionali

## 5.1 Analizza

### Requisiti

Quando l’utente clicca `Analizza`, il sistema deve:

1. leggere DB parsato attivo;
2. leggere filtri dataset attivi:
   - trader
   - date range
   - max trades
3. leggere setup market attivo:
   - market_data_dir
   - market_data_mode
   - download_tfs
   - simulation_tf
   - detail_tf
   - data types attivi
   - source
   - buffer mode
4. costruire il piano;
5. non scrivere parquet;
6. non modificare coverage manifest;
7. non cambiare `market_ready=True`.

### Output UI minimo richiesto

Il riepilogo deve includere almeno:

- numero simboli;
- numero intervalli richiesti;
- numero gap;
- lista timeframe attivi;
- lista tipi dati attivi;
- preview finestre;
- conteggio simboli non supportati/non mappati, se rilevabili;
- funding richiesto sì/no.

### Stato dopo Analizza

Impostare stato interno esplicito, ad esempio:

- `market_validation_status = analyzed`
- `market_ready = False`

Se si preferisce mantenere `needs_check`, serve comunque un indicatore separato `analysis_ready = True`.

---

## 5.2 Prepara

### Requisiti

Quando l’utente clicca `Prepara`, il sistema deve:

1. rieseguire il planner oppure riusare un piano compatibile;
2. calcolare i gap;
3. scaricare **solo** i gap mancanti;
4. se `funding_rate=True`, eseguire il funding sync per gli intervalli richiesti;
5. aggiornare manifest e artifact di sync;
6. non eseguire automaticamente validate full.

### Semantica per validate mode

#### `validate_mode = off`
`Prepara` deve:

- fare planner + sync (+ funding sync se richiesto)
- non eseguire gap validation
- non eseguire validate full
- marcare stato finale come `ready_unvalidated`

#### `validate_mode = light`
`Prepara` deve:

- fare planner + sync
- fare gap validation per OHLCV
- fare funding sync se richiesto
- funding validate opzionale: **non in Prepara**
- stato finale: `ready_unvalidated` oppure `gap_validated_partial`

#### `validate_mode = full`
`Prepara` deve comunque restare “solo prepare”:

- planner + sync
- funding sync se richiesto
- opzionale gap validation leggera
- **non validate full**

La validate full deve restare nel pulsante `Valida` o `Prepara + Valida`.

### Stato dopo Prepara

Possibili stati:

- `ready_unvalidated`
- `prepared_with_warnings`
- `prepared_with_unsupported_symbols`
- `prepare_failed`

---

## 5.3 Valida

### Requisiti

Quando l’utente clicca `Valida`, il sistema deve validare il dataset **già esistente** senza scaricare.

### Deve validare:

#### OHLCV
Per ogni:

- simbolo
- basis richiesta (`last`, `mark`)
- timeframe richiesto in `download_tfs`, `simulation_tf`, `detail_tf`

#### Funding
Se `funding_rate=True`, deve validare funding rate sui medesimi intervalli richiesti dal piano.

### Regola fondamentale
La validate deve leggere i path corretti per ogni timeframe e tipo dato.

Non deve usare solo `plan["timeframe"]` come fallback globale se il piano contiene blocchi `timeframes[tf]`.

### Stato dopo Valida

Possibili esiti:

- `validated`
- `gap_validated`
- `validated_with_warnings`
- `validation_failed`

Con `market_ready=True` solo se l’esito finale è coerente con la policy scelta.

---

## 5.4 Prepara + Valida

### Requisiti

Deve essere la pipeline completa e coerente con `validate_mode`.

#### `off`
Comportamento target:

- planner + sync (+ funding sync)
- nessuna validate
- stato finale `ready_unvalidated`

#### `light`
Comportamento target:

- planner + sync
- gap validation OHLCV
- funding sync
- funding validate opzionale ma preferibile separata
- stato finale coerente con warning/unsupported

#### `full`
Comportamento target:

- planner + sync
- gap validation
- validate full OHLCV
- validate funding se richiesto
- scrittura validation cache completa
- stato finale `validated` / `gap_validated`

---

## 5.5 Backtest

### Requisiti

`Esegui Backtest` deve essere permesso solo se:

- DB parsato valido;
- stato market compatibile;
- dataset richiesto coerente con setup corrente.

### Regole minime

- consentito con `ready_unvalidated` solo se l’utente ha esplicitamente scelto una modalità che lo permette;
- consentito con `validated`;
- non consentito con `needs_check` o `prepare_failed` o `validation_failed`.

### Messaggio UX
Se bloccato, il messaggio deve essere preciso, ad esempio:

- `Market DATA non preparati`
- `Analizza prima la copertura`
- `Il dataset è preparato ma non validato`
- `Sono presenti simboli non supportati che bloccano la run`

---

## 6. Requisiti tecnici dettagliati

## 6.1 Allineare planner/sync/validate al multi-timeframe

## Problema attuale
Planner e sync supportano i blocchi `timeframes[tf]`, ma validate e gap_validate non sono ancora pienamente allineati.

## Implementazione richiesta

### `scripts/gap_validate_market_data.py`

Correggere `_build_gap_jobs(...)` e la fase di lettura cache affinché lavorino su chiave:

- `symbol`
- `basis`
- `timeframe`

Non più solo su:

- `symbol`
- `basis`

Ogni job deve contenere anche `timeframe`.

La lettura parquet deve usare:

`market_dir / bybit / futures_linear / <requested_timeframe> / <symbol>`

non il solo `plan["timeframe"]`.

### `scripts/validate_market_data.py`

Validare per:

- simbolo
- basis
- timeframe richiesto

Il conteggio `total_checks` deve essere basato sui `required_intervals` per timeframe richiesto, non solo sui top-level.

### Compatibilità
Se il piano non contiene `timeframes`, mantenere un fallback legacy.

---

## 6.2 Distinguere chiaramente tipi dati

## OHLCV
Il planner deve riflettere esplicitamente nel payload quali tipi OHLCV sono richiesti:

- `ohlcv_last`
- `ohlcv_mark`

Non basta che `bases=last,mark` sia hardcoded se l’utente disattiva uno dei toggle.

## Funding
Il funding non va trattato come basis OHLCV.

Va mantenuto come dataset separato, ma l’analisi deve esplicitare:

- funding richiesto sì/no;
- funding coverage disponibile sì/no;
- funding gap presenti sì/no.

### Richiesta minima
Nel `plan_market_data.json` aggiungere un blocco descrittivo coerente, ad esempio:

```json
"requested_data_types": {
  "ohlcv_last": true,
  "ohlcv_mark": false,
  "funding_rate": true
}
```

Facoltativo ma consigliato:

```json
"summary_by_data_type": {
  "ohlcv_last": {...},
  "ohlcv_mark": {...},
  "funding_rate": {...}
}
```

---

## 6.3 Correggere la semantica di validate mode

## Stato target

### `off`
- prepara ma non valida
- non deve significare “trust senza pipeline”

### `light`
- prepara + gap validation
- senza validate full

### `full`
- prepara + validate full

### Impatto sul codice

Correggere in `market_data_panel.py`:

- `_run_prepare(...)`
- `_run_validate_full(...)`
- `_run_prepare_and_validate(...)`

In particolare:

- rimuovere la branch attuale in cui `off` marca pronto senza eseguire pipeline;
- spostare la logica `off = no validate` dentro la semantica di `Prepara` e `Prepara + Valida`.

---

## 6.4 Migliorare la validation cache

## Problema attuale
Il fingerprint non rappresenta tutto il setup reale del pannello Market DATA.

## Requisito
Estendere `MarketDataRequest` e il fingerprint per includere almeno:

- `download_tfs`
- `simulation_tf`
- `detail_tf`
- `validate_mode`
- `data_types`
  - `ohlcv_last`
  - `ohlcv_mark`
  - `funding_rate`
- `buffer_mode`
- `pre_buffer_days`
- `post_buffer_days`
- `buffer_preset`

### File da modificare
- `src/signal_chain_lab/market/preparation_cache.py`

### Obiettivo
Se l’utente cambia uno di questi parametri, la cache PASS precedente non deve essere riusata impropriamente.

---

## 6.5 Gestire simboli non supportati senza ambiguità

## Problema
Uno `skipped` del downloader può portare a FAIL globale senza distinzione semantica chiara.

## Requisito
Introdurre una classificazione più precisa, almeno nel reporting interno e negli artifact:

- `unsupported_symbol`
- `symbol_mapping_missing`
- `sync_error`
- `partial_data`
- `optional_data_missing`

## Policy proposta

### In `Analizza`
Se possibile, marcare già:

- simboli sicuramente scaricabili;
- simboli sospetti/non standard;
- simboli non supportati.

### In `Prepara`
Se un simbolo non supportato viene saltato:

- non deve apparire come semplice “gap generico”;
- deve comparire in una sezione dedicata.

### In `Valida`
Definire se:

- i simboli non supportati bloccano sempre;
- oppure sono consentiti come warning/esclusione.

## Decisione consigliata
Per ora:

- **bloccanti** in modalità `full`;
- **warning espliciti** in modalità `light`, con backtest bloccato solo se quei simboli sono effettivamente richiesti dal motore di simulazione.

---

## 7. Modifiche file-by-file

## 7.1 `src/signal_chain_lab/ui/blocks/market_data_panel.py`

### Da mantenere
- struttura pannello;
- pulsanti esistenti;
- stato badge;
- log panel.

### Da cambiare
1. correggere semantica `validate_mode`;
2. fare in modo che `Prepara` sia realmente uno step di prepare, non di validate completa;
3. mostrare meglio i risultati di `Analizza`;
4. mostrare nel summary anche:
   - TF attivi
   - data types attivi
   - funding richiesto
   - eventuali unsupported/skipped.

---

## 7.2 `scripts/plan_market_data.py`

### Da mantenere
- supporto `download_tfs`, `simulation_tf`, `detail_tf`;
- supporto buffer mode.

### Da cambiare
1. aggiungere nel payload del piano una rappresentazione esplicita dei data types richiesti;
2. opzionalmente aggiungere summary per data type;
3. se possibile aggiungere lista simboli non supportati/potenzialmente non normalizzati.

---

## 7.3 `scripts/sync_market_data.py`

### Da mantenere
- sync per `symbol + basis + timeframe`;
- manifest coverage update.

### Da cambiare
1. distinguere meglio `skipped` per gap assente da `skipped` per simbolo non supportato;
2. includere nel report un `reason_code` strutturato.

---

## 7.4 `scripts/gap_validate_market_data.py`

### Da cambiare
1. introdurre chiave `(symbol, basis, timeframe)`;
2. leggere parquet dal timeframe corretto;
3. validare i gap per TF, non solo top-level;
4. allineare i contatori al multi-timeframe.

---

## 7.5 `scripts/validate_market_data.py`

### Da cambiare
1. validazione per ogni timeframe richiesto;
2. lettura parquet dal path corretto per TF;
3. conteggi pass/fail coerenti per TF;
4. summary finale con breakdown per TF e basis.

---

## 7.6 `src/signal_chain_lab/market/preparation_cache.py`

### Da cambiare
1. estendere `MarketDataRequest`;
2. estendere fingerprint;
3. mantenere retrocompatibilità con record vecchi dove possibile.

---

## 7.7 `src/signal_chain_lab/ui/state.py`

### Possibili aggiunte consigliate
Aggiungere stato sintetico più ricco, per esempio:

- `analysis_ready`
- `unsupported_symbol_count`
- `analysis_summary`
- `requested_data_types_summary`

Queste aggiunte non sono obbligatorie, ma semplificano la UI.

---

## 8. Acceptance criteria

## 8.1 Analizza

- cliccando `Analizza` non viene scritto nessun parquet;
- viene generato il piano;
- vengono mostrati simboli, gap, TF richiesti, tipi dati attivi;
- funding richiesto compare nel riepilogo;
- stato finale non è `market_ready=True`.

## 8.2 Prepara con `validate_mode=off`

- vengono scaricati i gap mancanti;
- non parte validate full;
- non parte gap validation;
- se funding attivo, parte funding sync;
- stato finale `ready_unvalidated`.

## 8.3 Prepara con `validate_mode=light`

- planner + sync eseguiti;
- gap validation eseguita;
- validate full non eseguita;
- stato finale coerente.

## 8.4 Prepara + Valida con `validate_mode=full`

- planner + sync + validate full eseguiti;
- funding validate eseguita se funding richiesto;
- validation cache scritta con fingerprint corretto.

## 8.5 Validate multi-timeframe

Dato un piano con:

- `download_tfs = [1m, 15m, 1h]`
- `simulation_tf = 1h`
- `detail_tf = 1m`

la validazione deve:

- verificare 1m;
- verificare 15m;
- verificare 1h;
- leggere i parquet corretti per ciascun TF.

## 8.6 Reuse cartella esistente

Con cartella già popolata e manifest coerente:

- `Analizza` deve mostrare gap residui corretti;
- `Prepara` deve scaricare solo gap residui;
- non deve proporre implicitamente un full redownload.

---

## 9. Test plan

## 9.1 Test UI base

1. caricare DB valido;
2. selezionare cartella market esistente;
3. cliccare `Analizza`;
4. verificare output summary;
5. cliccare `Prepara`;
6. verificare sync solo gap;
7. cliccare `Backtest`.

## 9.2 Test validate off

1. cartella market parziale;
2. `validate_mode=off`;
3. clic `Prepara`;
4. atteso:
   - download eseguito;
   - nessuna validate;
   - stato `ready_unvalidated`.

## 9.3 Test multi-timeframe

1. selezionare `download_tfs = 1m,15m,1h,4h,1d`;
2. eseguire `Analizza`;
3. verificare piano con gap distinti per TF;
4. eseguire `Prepara + Valida`;
5. verificare validate per tutti i TF.

## 9.4 Test funding

1. attivare `Funding rate`;
2. eseguire `Prepara`;
3. atteso: parte `sync_funding_rates.py`;
4. eseguire `Valida` o `Prepara + Valida`;
5. atteso: parte `validate_funding_rates.py`.

## 9.5 Test simbolo non supportato

1. usare DB con simbolo noto non supportato/mal normalizzato;
2. eseguire `Analizza`;
3. atteso: warning/issue chiaro;
4. eseguire `Prepara`;
5. atteso: report strutturato, non messaggio ambiguo.

---

## 10. Out of scope per questa iterazione

Non fanno parte di questo PRD:

- redesign completo del layout Blocco 3;
- sostituzione storage parquet con DB SQL;
- nuovo sistema di symbol normalization globale cross-exchange;
- fees/cost model integrato nella stessa sezione Market DATA;
- refactor completo del simulatore.

---

## 11. Ordine consigliato di implementazione

### Step 1
Correggere `validate_mode` e la semantica di `Prepara` / `Prepara + Valida`.

### Step 2
Allineare `gap_validate_market_data.py` e `validate_market_data.py` al multi-timeframe.

### Step 3
Estendere fingerprint/cache.

### Step 4
Aggiungere summary più chiaro in `Analizza`.

### Step 5
Migliorare gestione `unsupported / skipped`.

### Step 6
Polish UI e messaggi utente.

---

## 12. Risultato atteso finale

Alla fine di questa implementazione, il comportamento dell’utente deve diventare:

1. scelgo DB;
2. scelgo cartella market;
3. scelgo riuso cartella o nuova base;
4. scelgo TF e tipi dati;
5. clicco `Analizza` e vedo cosa manca davvero;
6. clicco `Prepara` e scarico solo i gap necessari;
7. clicco `Valida` solo se voglio validare il dataset;
8. clicco `Backtest` e il sistema usa solo ciò che ho già preparato.

Con questa semantica il flusso diventa leggibile, auditabile e coerente con l’evoluzione attuale del repository.
