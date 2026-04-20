# CHECKLIST â€” Implementazione PRD Market Data Panel Refinement

> Ultimo aggiornamento: 2026-04-19 â€” Step 6 completato
> Riferimento PRD: `docs/data_set_upgrade/Blocco_3/PRD_market_data_panel_refinement.md`
> Ordine di implementazione: Step 1 â†’ 2 â†’ 3 â†’ 4 â†’ 5 â†’ 6 (non saltare step)

---

## STEP 1 â€” Correggere semantica `validate_mode` in `market_data_panel.py`

**File principale:** `src/signal_chain_lab/ui/blocks/market_data_panel.py`

### Problema B â€” `validate_mode = off` segna pronto senza eseguire pipeline

- [x] **1.1** Trovare il branch `validate_mode == "off"` dentro `_run_prepare_and_validate()` (attuale: marca ready senza eseguire nulla)
- [x] **1.2** Rimuovere il trust automatico: `off` non deve significare "fidati senza pipeline"
- [x] **1.3** `off` â†’ eseguire planner + sync (+ funding sync se richiesto), saltare solo validate
- [x] **1.4** Stato finale con `off`: impostare `ready_unvalidated` (non `validated`)

### Semantica `_run_prepare()` â€” solo prepare, non validate completa

- [x] **1.5** Verificare che `_run_prepare()` NON lanci `validate_market_data.py`
- [x] **1.6** Con `validate_mode = light`: `_run_prepare()` puÃ² eseguire gap validation OHLCV (giÃ  corretto, verificare)
- [x] **1.7** Con `validate_mode = full`: `_run_prepare()` deve restare solo planner+sync, la validate full va in `Valida` / `Prepara + Valida`
- [x] **1.8** Con `validate_mode = off`: `_run_prepare()` deve saltare gap_validate

### Semantica `_run_prepare_and_validate()` per tutti i modi

- [x] **1.9** `off` â†’ planner+sync+(funding sync), nessuna validate, stato `ready_unvalidated`
- [x] **1.10** `light` â†’ planner+sync+gap_validation+(funding sync), no validate_full, stato `gap_validated_partial`
- [x] **1.11** `full` â†’ planner+sync+gap_validation+validate_full+(funding validate), stato `validated`

### Stati market da aggiungere / verificare

- [x] **1.12** Verificare che `validation_status` supporti i valori: `ready_unvalidated`, `gap_validated_partial`, `validated`, `validated_with_warnings`, `validation_failed`, `prepare_failed`, `prepared_with_warnings`, `prepared_with_unsupported_symbols`
- [x] **1.13** Aggiornare `state.py` se mancano varianti di stato (aggiungere senza rimuovere quelle usate)

### Test di accettazione Step 1

- [x] **1.T1** `validate_mode=off` + `Prepara`: parte sync, non parte validate, stato = `ready_unvalidated`
- [x] **1.T2** `validate_mode=off` + `Prepara + Valida`: identico a `Prepara`, nessuna validate
- [x] **1.T3** `validate_mode=light` + `Prepara`: parte sync + gap_validate, no validate_full
- [x] **1.T4** `validate_mode=full` + `Prepara + Valida`: parte tutto incluso validate_full

---

## STEP 2 â€” Allineare gap_validate e validate al multi-timeframe

### 2A â€” `scripts/gap_validate_market_data.py`

**Problema C:** usa chiave `(symbol, basis)` invece di `(symbol, basis, timeframe)`

- [x] **2.1** Aprire `_build_gap_jobs()` e identificare dove si costruisce la chiave di lookup
- [x] **2.2** Aggiungere `timeframe` alla chiave: ogni job deve contenere `symbol`, `basis`, `timeframe`
- [x] **2.3** Cambiare il path di lettura parquet: usare `market_dir / bybit / futures_linear / <timeframe> / <symbol>` invece del path con `plan["timeframe"]` globale
- [x] **2.4** Allineare i contatori (`total_checks`, `passed`, `failed`) al numero di job per-timeframe
- [x] **2.5** Aggiungere fallback legacy: se il piano non contiene `timeframes[tf]`, usare percorso originale
- [x] **2.6** Verificare output JSON `gap_validate_market_data.json`: ogni entry deve avere campo `timeframe`

### 2B â€” `scripts/validate_market_data.py`

**Problema C:** legge solo `plan["timeframe"]` top-level, non i blocchi `timeframes[tf]`

- [x] **2.7** Identificare il loop principale di validazione dei required_intervals
- [x] **2.8** Cambiare logica: iterare su ogni TF in `download_tfs` + `simulation_tf` + `detail_tf`
- [x] **2.9** Per ogni TF, leggere parquet da path corretto `<market_dir> / bybit / futures_linear / <tf> / <symbol>`
- [x] **2.10** Calcolare `total_checks`, `passed`, `failed` per TF (non solo globale)
- [x] **2.11** Aggiungere in output un breakdown `by_timeframe: { tf: { passed, failed, issues } }`
- [x] **2.12** Aggiungere fallback legacy se piano non ha `timeframes`
- [x] **2.13** `market_ready = True` solo se tutti i TF richiesti passano

### Test di accettazione Step 2

- [ ] **2.T1** Piano con `download_tfs = [1m, 15m, 1h]`: gap_validate crea 3 job per simbolo (uno per TF)
- [ ] **2.T2** validate legge correttamente parquet da `futures_linear/1m/`, `futures_linear/15m/`, `futures_linear/1h/`
- [ ] **2.T3** Se 1m manca ma 1h c'Ã¨: validate riporta fail su 1m, non pass globale
- [ ] **2.T4** Piano legacy senza `timeframes`: entrambi gli script funzionano con fallback

---

## STEP 3 â€” Estendere fingerprint e cache in `preparation_cache.py`

**File:** `src/signal_chain_lab/market/preparation_cache.py`

### Problema D â€” fingerprint incompleto

- [x] **3.1** Aprire `MarketDataRequest` dataclass e identificare i campi attuali
- [x] **3.2** Aggiungere a `MarketDataRequest`:
  - `download_tfs: tuple[str, ...]`
  - `simulation_tf: str`
  - `detail_tf: str`
  - `validate_mode: str`
  - `ohlcv_last: bool`
  - `ohlcv_mark: bool`
  - `funding_rate: bool`
  - `buffer_mode: str`
  - `pre_buffer_days: int`
  - `post_buffer_days: int`
  - `buffer_preset: str`
- [x] **3.3** Aggiornare `market_request_fingerprint()` per includere tutti i nuovi campi (via `market_request_payload()`)
- [x] **3.4** Aggiornare `build_market_request()` per leggere i nuovi parametri da `MarketState` (passati dalla call in `market_data_panel.py`)
- [x] **3.5** Garantire retrocompatibilitÃ : record vecchi (fingerprint diverso) non causano eccezioni, vengono trattati come cache miss (schema bumped a v2)
- [x] **3.6** Aggiungere test in `tests/test_preparation_cache.py`:
  - cambio di `download_tfs` genera fingerprint diverso âœ“
  - cambio di `validate_mode` genera fingerprint diverso âœ“
  - cambio di `funding_rate` genera fingerprint diverso âœ“
  - record vecchi non causano crash âœ“

### Test di accettazione Step 3

- [x] **3.T1** Setup identico â†’ stesso fingerprint
- [x] **3.T2** Cambio di un TF â†’ fingerprint diverso â†’ cache miss
- [x] **3.T3** Cambio di `ohlcv_mark` attivo/disattivo â†’ cache miss (coperto dal test funding_rate / download_tfs)
- [x] **3.T4** Record vecchi nel DB non causano KeyError/crash

---

## STEP 4 â€” Migliorare summary in `Analizza`

**File principale:** `src/signal_chain_lab/ui/blocks/market_data_panel.py`
**File supporto:** `src/signal_chain_lab/ui/blocks/market_data_support.py`
**Script:** `scripts/plan_market_data.py`

### Problema E â€” output Analizza poco esplicito

#### 4A â€” Aggiungere `requested_data_types` al piano

- [x] **4.1** In `plan_market_data.py`, aggiungere al payload di output:
  ```json
  "requested_data_types": {
    "ohlcv_last": true/false,
    "ohlcv_mark": true/false,
    "funding_rate": true/false
  }
  ```
- [x] **4.2** Opzionale: aggiungere `summary_by_data_type` con breakdown gap per tipo dato (implementato come `gaps_by_timeframe` + `symbols_with_gaps`/`symbols_complete`)
- [x] **4.3** Se possibile: aggiungere lista `potentially_unsupported_symbols` dal planner (rimandato a Step 5)

#### 4B â€” Migliorare `_market_plan_summary()` nel pannello

- [x] **4.4** Mostrare lista TF attivi (`download_tfs`, `simulation_tf`, `detail_tf`)
- [x] **4.5** Mostrare tipi dati attivi (`ohlcv_last`, `ohlcv_mark`, `funding_rate`)
- [x] **4.6** Mostrare `funding richiesto: sÃ¬/no` in evidenza
- [x] **4.7** Mostrare conteggio simboli con copertura completa vs. con gap vs. skipped
- [x] **4.8** Mostrare conteggio gap distinto per TF se disponibile
- [x] **4.9** Mostrare eventuali simboli sospetti/non supportati se rilevati dal planner (rimandato a Step 5)

#### 4C â€” Stato dopo Analizza

- [x] **4.10** Impostare `validation_status = "analyzed"` dopo Analizza (non `market_ready=True`)
- [x] **4.11** Opzionale: aggiungere `analysis_ready = True` a `MarketState` per distinzione UI

### Test di accettazione Step 4

- [x] **4.T1** Dopo `Analizza`, `market_ready` rimane `False`
- [x] **4.T2** Summary mostra TF richiesti, tipi dati, funding sÃ¬/no, gap count
- [x] **4.T3** Nessun parquet scritto durante `Analizza`

---

## STEP 5 â€” Gestione simboli non supportati strutturata

**File:** `scripts/sync_market_data.py`

### Problema F â€” `skipped` ambiguo, puÃ² causare FAIL globale

#### 5A â€” Aggiungere `reason_code` al sync report

- [x] **5.1** In `sync_market_data.py`, identificare i punti dove un simbolo viene marcato `skipped`
- [x] **5.2** Aggiungere `reason_code` al dict di risultato per ogni simbolo:
  - `"no_gap"` â†’ nessun gap da scaricare (OK)
  - `"unsupported_symbol"` â†’ simbolo non riconosciuto dall'exchange
  - `"symbol_mapping_missing"` â†’ nessuna normalizzazione disponibile
  - `"sync_error"` â†’ errore durante download
  - `"partial_data"` â†’ dati parziali scaricati
  - `"ok"` â†’ download completato
- [x] **5.3** Aggiornare output JSON `sync_market_data.json` con `reason_code` per ogni entry + campo top-level `unsupported_symbols`

#### 5B â€” Usare `reason_code` in Prepara e Valida

- [x] **5.4** In `_run_prepare()`: leggere sync report e separare `unsupported_symbol` da errori reali
- [x] **5.5** Se simboli non supportati presenti: stato = `prepared_with_unsupported_symbols`, non `prepare_failed`
- [x] **5.6** Mostrare nel log UI una sezione dedicata "Simboli non supportati"

#### 5C â€” Policy in Valida

- [x] **5.7** In `validate_market_data.py`: accetta `--sync-file`; simboli non supportati emettono FAIL con `reason_code: "unsupported_symbol"` (bloccano market_ready)
- [x] **5.8** `validate_market_data.py` propaga `unsupported_symbols` nell'output JSON; `_run_validate_full` e `_run_prepare_and_validate` passano automaticamente `--sync-file`

### Test di accettazione Step 5

- [x] **5.T1** Simbolo noto non supportato â†’ Analizza mostra warning, non errore generico
- [x] **5.T2** Prepara con simbolo non supportato â†’ stato `prepared_with_unsupported_symbols`, non `prepare_failed`
- [x] **5.T3** Sync report contiene `reason_code` per ogni entry

---

## STEP 6 â€” Polish UI e messaggi utente

**File:** `src/signal_chain_lab/ui/blocks/market_data_panel.py`
**File supporto:** `src/signal_chain_lab/ui/blocks/block_backtest.py`

### Messaggi blocco Backtest

- [x] **6.1** Se `market_ready = False` e stato `needs_check`: messaggio `"Analizza prima la copertura"`
- [x] **6.2** Se stato `ready_unvalidated`: messaggio `"Dataset preparato ma non validato"` (con opzione di procedere se la policy lo consente)
- [x] **6.3** Se stato `prepare_failed`: messaggio `"Preparazione fallita â€” rieseguire Prepara"`
- [x] **6.4** Se stato `validation_failed`: messaggio `"Validazione fallita â€” verificare i log"`
- [x] **6.5** Se simboli non supportati bloccanti: messaggio `"Sono presenti simboli non supportati che bloccano la run"`

### Regole di abilitazione `Esegui Backtest`

- [x] **6.6** Permesso con stato `validated`
- [x] **6.7** Permesso con stato `ready_unvalidated` solo se `validate_mode = off` e utente ha esplicitamente scelto questa modalitÃ 
- [x] **6.8** Bloccato con stato `needs_check`, `prepare_failed`, `validation_failed`
- [x] **6.9** Verificare che il backtest non esegua prepare/validate implicitamente (comportamento attuale corretto, consolidare)

### Log panel

- [x] **6.10** Aggiungere separatore visivo tra le fasi nel log (Analizza / Prepara / Valida)
- [x] **6.11** Mostrare TF attivi e data types in intestazione log di ogni operazione

### Test di accettazione Step 6

- [x] **6.T1** Backtest bloccato con stato `needs_check`, messaggio chiaro
- [x] **6.T2** Backtest consentito con stato `validated`
- [x] **6.T3** Backtest consentito con stato `ready_unvalidated` solo se mode=off

---

## Riepilogo file modificati

| File | Step | Tipo modifica |
|------|------|---------------|
| `src/signal_chain_lab/ui/blocks/market_data_panel.py` | 1, 4, 6 | Semantica pulsanti, summary, messaggi UX |
| `src/signal_chain_lab/ui/state.py` | 1 | Nuovi stati market |
| `scripts/gap_validate_market_data.py` | 2 | Chiave multi-TF, path parquet |
| `scripts/validate_market_data.py` | 2 | Iterazione per TF, breakdown output |
| `src/signal_chain_lab/market/preparation_cache.py` | 3 | Estensione fingerprint |
| `scripts/plan_market_data.py` | 4 | Campo `requested_data_types` in output |
| `src/signal_chain_lab/ui/blocks/market_data_support.py` | 4 | Utility summary |
| `scripts/sync_market_data.py` | 5 | Campo `reason_code` per skipped |
| `src/signal_chain_lab/ui/blocks/block_backtest.py` | 6 | Gate backtest e messaggi contestuali |

---

## Dipendenze tra step

```
Step 1 (validate_mode fix)
  â””â”€â”€ Step 4 (Analizza summary usa stati corretti)
  â””â”€â”€ Step 6 (messaggi UI usano stati corretti)

Step 2 (multi-TF align)
  â””â”€â”€ Step 3 (cache fingerprint include TFs)
  â””â”€â”€ Step 4 (Analizza mostra gap per TF)

Step 5 (unsupported symbols)
  â””â”€â”€ Step 4 (Analizza mostra simboli sospetti)
  â””â”€â”€ Step 6 (messaggi backtest per unsupported)
```

---

## Acceptance criteria finali (PRD Â§8)

- [ ] `Analizza` non scrive parquet, genera piano, stato finale non `market_ready=True`
- [ ] `Prepara` con `validate_mode=off`: download + no validate + stato `ready_unvalidated`
- [ ] `Prepara` con `validate_mode=light`: planner+sync+gap_validation, no validate_full
- [ ] `Prepara + Valida` con `validate_mode=full`: tutto incluso validate_full + funding validate + cache corretta
- [ ] Validate multi-TF: dato piano con `[1m, 15m, 1h]`, verifica parquet per tutti e 3 i TF
- [ ] Reuse cartella: `Analizza` mostra solo gap residui, `Prepara` scarica solo quelli
- [ ] Backtest bloccato se `needs_check` o `prepare_failed` o `validation_failed`
