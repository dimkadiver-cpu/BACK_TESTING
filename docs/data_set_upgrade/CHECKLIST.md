# Checklist di Attuazione - Market DATA Blocco 3

Basato su: `PIANO_IMPLEMENTAZIONE.md`
Data: 2026-04-18

---

## Fase 1 - Refactor UI ✅ COMPLETATA

### 1.1 Nuovo file: `market_data_support.py` ✅
- [x] Creare `src/signal_chain_lab/ui/blocks/market_data_support.py`
- [x] Implementare `parse_progress_line(line: str) -> ProgressEvent | None`
- [x] Implementare `format_coverage_summary(plan_json: dict) -> str`
- [x] Implementare `format_validation_summary(report_json: dict) -> str`
- [x] Implementare `map_phase_label(phase: str) -> str`
- [x] Test unitari per `parse_progress_line` con righe valide e malformate

### 1.2 Refactor `state.py` ✅
- [x] Creare dataclass `MarketState` con tutti i campi Market estratti da `UiState`
- [x] Aggiungere campi nuovi: `validate_mode`, `download_tf`, `simulation_tf`, `detail_tf`, `buffer_mode`, `pre_buffer_days`, `post_buffer_days`, `buffer_preset`
- [x] Sostituire 15 variabili sparse in `UiState` con `market: MarketState = field(default_factory=MarketState)`
- [x] Verificare che nessun campo venga perso nel refactor

### 1.3 Aggiornare riferimenti a `state.market_*` ✅
- [x] `block_backtest.py` - aggiornare tutti gli accessi `state.market_data_*` -> `state.market.*`
- [x] `backtest_support.py` - verificare e aggiornare se necessario (nessun riferimento diretto)
- [x] `backtest_observability.py` - verificare e aggiornare se necessario (nessun riferimento diretto)
- [x] `preparation_cache.py` - verificare compatibilità con `MarketState` (usata via parametri, OK)

### 1.4 Nuovo file: `market_data_panel.py` ✅
- [x] Creare `src/signal_chain_lab/ui/blocks/market_data_panel.py`
- [x] Implementare sezione `Setup`: market dir, dataset mode, validate mode, source, timeframe, buffer mode, tipo dati
- [x] Implementare sezione `Discovery`: simboli rilevati, finestre richieste, gap stimati, cache hit/miss (read-only, pre-download)
- [x] Implementare sezione `Run`: progress bar globale con % e fase, log strutturato per fase (append-only, scrollable)
- [x] Implementare sezione `Result`: artifacts paths, coverage summary, validation summary, badge readiness
- [x] Aggiungere pulsante `Analizza` (solo discovery, nessun download)
- [x] Aggiungere pulsante `Prepara` (planner + sync + gap_validate)
- [x] Aggiungere pulsante `Valida` (validate_full su dataset esistente)
- [x] Aggiungere pulsante `Prepara + Valida` (pipeline completa)
- [x] Implementare badge finale: `READY` / `READY (unvalidated)` / `NOT READY`
- [x] Il panel è collassabile con lifecycle proprio
- [x] Il panel legge `_run_streaming_command` passato dall'app

### 1.5 Refactor `block_backtest.py` ✅
- [x] Rimuovere metodo `_prepare_market_data()`
- [x] Rimuovere sezione UI Market DATA (inputs, pulsanti, log, progress)
- [x] Mantenere lettura di `state.market.market_ready`, `state.market.market_validation_status`, `state.market.latest_artifact_path`
- [x] Verificare che il Backtest parta solo se `state.market.market_ready == True`
- [x] Verificare che `backtest_observability.py` riceva ancora `market_validation_status` e `market_prepare_total_seconds`

### 1.6 Aggiornare `app.py` ✅
- [x] Importare `MarketDataPanel`
- [x] Comporre Blocco 3: `MarketDataPanel` (collassabile, in alto) + sezione Backtest (sotto)
- [x] Passare `_run_streaming_command` al `MarketDataPanel`
- [x] Verificare che il tab workflow generale non cambi

### 1.7 Verifica Fase 1
- [ ] L'applicazione si avvia senza errori
- [ ] Il Blocco 3 mostra il panel Market DATA collassabile
- [ ] Il Blocco 3 mostra la sezione Backtest sotto
- [ ] I dati di stato sono coerenti tra panel e backtest block
- [ ] Test di regressione: un run backtest completo funziona end-to-end

---

## Fase 2 - Buffer manuale e opzioni utente esplicite ✅ COMPLETATA (test automatici ✅, verifiche UI manuali pendenti)

### 2.1 Nuove opzioni validate mode nella UI ✅
- [x] Sostituire toggle SAFE/FAST con select: `Full` / `Light` / `Off (Trust existing)`
- [x] Mappare Full -> planner + sync + gap_validate + validate_full
- [x] Mappare Light -> planner + sync + gap_validate (comportamento attuale FAST)
- [x] Mappare Off -> skip tutto, `market_ready = True` con stato `ready_unvalidated`
- [x] Aggiornare `state.market.validate_mode` di conseguenza

### 2.2 Buffer mode nella UI ✅
- [x] Aggiungere toggle `AUTO / MANUAL` nel Setup
- [x] In modalità `MANUAL`: mostrare input `pre_buffer_days`, `post_buffer_days`
- [x] Aggiungere preset rapidi: `Intraday` (pre=2d, post=1d) / `Swing` (pre=7d, post=3d) / `Position` (pre=30d, post=7d) / `Custom`
- [x] Selezionando un preset, i valori si pre-compilano (modificabili)
- [x] In modalità `AUTO`: nascondere gli input manuali

### 2.3 `market/planning/coverage_planner.py` ✅
- [x] Creare dataclass `ManualBuffer(pre_days: int, post_days: int, preset: str)`
- [x] Aggiungere parametro `manual_buffer: ManualBuffer | None = None` a `CoveragePlanner.plan()`
- [x] Se `manual_buffer` presente: applicare pre/post fissi, ignorare profilo adattivo
- [x] Se `manual_buffer` assente: comportamento attuale invariato
- [x] Test: buffer manuale produce finestre corrette (`test_coverage_planner.py::test_coverage_planner_manual_buffer_emits_execution_chart_and_download_windows`)
- [x] Test: buffer auto produce le stesse finestre di prima (`test_coverage_planner.py::test_coverage_planner_auto_buffer_keeps_execution_inside_chart_and_download`)

### 2.4 `scripts/plan_market_data.py` ✅
- [x] Aggiungere argomento `--buffer-mode auto|manual` (default: auto)
- [x] Aggiungere argomento `--pre-buffer-days` (solo se manual)
- [x] Aggiungere argomento `--post-buffer-days` (solo se manual)
- [x] Aggiungere argomento `--buffer-preset intraday|swing|position|custom`
- [x] Aggiungere argomento `--validate-mode full|light|off` (default: light)
- [x] Il panel passa i valori da `state.market` come argomenti CLI

### 2.5 Protocollo stdout - tutti gli script ✅
- [x] `plan_market_data.py`: emettere `PHASE=planner`, `PROGRESS=N`, `SUMMARY=symbols:N gaps:N`
- [x] `sync_market_data.py`: emettere `PHASE=sync`, `PROGRESS=N`, `SUMMARY=ok:N skipped:N error:N`
- [x] `gap_validate_market_data.py`: emettere `PHASE=gap_validate`, `PROGRESS=N`, `STEP=X/Y`
- [x] `validate_market_data.py`: emettere `PHASE=validate`, `PROGRESS=N`, `STEP=X/Y`, `SUMMARY=pass:N fail:N`
- [x] Verificare che `parse_progress_line()` in `market_data_support.py` legga correttamente tutti i formati (`test_market_data_support.py`)

### 2.6 Verifica Fase 2
- [ ] Selezionando "Off" la validazione viene saltata e il dataset viene marcato `ready_unvalidated`
- [ ] Selezionando buffer `MANUAL` con preset Swing, il piano usa pre=7d post=3d
- [ ] Selezionando buffer `AUTO`, il comportamento è identico a prima
- [ ] La progress bar si aggiorna durante planner, sync, gap_validate, validate
- [ ] Il log mostra le fasi in ordine con le relative righe strutturate

---

## Fase 3 - Planner chart-aware ✅ COMPLETATA

### 3.1 Nuovo file: `market/runtime_config.py` ✅
- [x] Creare `src/signal_chain_lab/market/runtime_config.py`
- [x] Implementare dataclass `MarketRuntimeConfig` con: `download_tf`, `simulation_tf`, `detail_tf`, `price_basis`, `source`, `buffer_mode`, `pre_buffer_days`, `post_buffer_days`
- [x] Implementare `runtime_config_from_state(market_state: MarketState) -> MarketRuntimeConfig`

### 3.2 `market/planning/coverage_planner.py` ✅
- [x] Aggiornare output `CoveragePlan` per includere per simbolo:
  - `execution_window: list[Interval]`
  - `chart_window: list[Interval]` (execution_window + pre/post buffer visuale)
  - `download_window: list[Interval]` (unione delle due, usata per il download)
- [x] `required_intervals` nel JSON di output = `download_window` (nessuna breaking change a valle)
- [x] Test: execution_window ⊆ chart_window ⊆ download_window

### 3.3 `scripts/plan_market_data.py` ✅
- [x] Output JSON del piano include `execution_window`, `chart_window`, `download_window` per simbolo
- [x] Campo `required_intervals` mantiene il valore precedente per retrocompatibilità
- [x] Test: lo script sync e validate ricevono `required_intervals` invariati

### 3.4 Verifica Fase 3 ✅
- [x] Il piano JSON mostra tre finestre distinte per ogni simbolo
- [x] Con buffer `MANUAL` pre=7d post=3d: `chart_window` = `execution_window` allargata di 7d pre e 3d post
- [x] Con buffer `AUTO`: `chart_window` usa i buffer adattivi del profilo
- [x] Sync scarica `download_window` (non `execution_window`)

Note stato 2026-04-18:
- [x] Aggiunti test unitari in `src/signal_chain_lab/market/tests/test_coverage_planner.py`
- [x] Verificata la retrocompatibilità del downstream mantenendo `required_intervals = download_window`
- [x] La Fase 3 qui chiusa copre il planner chart-aware single-timeframe; la parte multi-TF resta in Fase 5

---

## Fase 4 - Validazione rafforzata ✅ PARZIALMENTE COMPLETATA

### 4.1 `market/planning/validation.py` ✅
- [x] Aggiungere `IssueSeverity(CRITICAL, WARNING, INFO)` enum
- [x] Aggiornare `ValidationIssue` per includere `severity: IssueSeverity`
- [x] Implementare Step 5 - OHLC strong check: `low <= open <= high`, `low <= close <= high`, `volume >= 0`
- [x] Implementare Step 6 - Continuità interna: nessun gap temporale non atteso tra candele consecutive
- [x] Aggiungere parametro tolleranza gap (default: 1 candela mancante tollerata)
- [x] `ValidationResult` include conteggi per severity: `critical_count`, `warning_count`
- [x] Test per ogni step con dati sintetici corretti e corrotti

### 4.2 `scripts/validate_market_data.py` ✅
- [x] Output JSON include severity per ogni issue
- [x] Aggiungere flag `--strict`: fallisce su WARNING oltre che su CRITICAL
- [x] Aggiornare `SUMMARY=` nel protocollo stdout: `pass:N fail:N warnings:N`

### 4.3 Verifica Fase 4
- [x] Candela con `low > high` viene rilevata come CRITICAL
- [x] Candela con `volume < 0` viene rilevata come CRITICAL
- [x] Gap di 2 candele consecutive mancanti viene rilevato come WARNING
- [x] Con `--strict`: gap produce exit non-zero
- [x] Senza `--strict`: gap non blocca il processo

---

## Fase 5 - Multi-timeframe intelligente ✅ COMPLETATA

### 5.1 `market/runtime_config.py`
- [x] Verificare che `simulation_tf` e `detail_tf` siano distinti e configurabili
- [x] `simulation_tf` = parent TF per scansione principale
- [x] `detail_tf` = child TF per risoluzione intra-bar

### 5.2 `market/intrabar_resolver.py`
- [x] Accettare `MarketRuntimeConfig` per leggere `simulation_tf` e `detail_tf`
- [x] Implementare logica selezione barre candidate:
  - [x] Possibile touch di entry pending
  - [x] Possibile touch dello SL corrente
  - [x] Possibile touch del TP corrente
  - [x] Possibile collisione SL/TP nella stessa barra
  - [x] Presenza update trader intra-barra
  - [x] Confini temporali (timeout, cambio stato)
- [x] Restituire `IntrabarResult`: barre discese, eventi risolti, ordine finale
- [x] Barre non candidate: non scendono al child TF (performance)
- [x] Test: barra senza livelli rilevanti non genera discesa al child TF

### 5.3 Download multi-TF
- [x] `plan_market_data.py`: se `simulation_tf != detail_tf`, generare richieste per entrambi i TF
- [x] `coverage_planner.py`: `download_window` calcolata per `(symbol, download_tf)` e `(symbol, detail_tf)` se diversi
- [x] `BybitDownloader` riceve lista di `(symbol, timeframe)` - già supportato, verificare

### 5.4 Verifica Fase 5
- [x] Con `simulation_tf=15m` e `detail_tf=1m`: il piano include download per entrambi
- [x] Barre parent che non toccano livelli non generano accesso ai dati child
- [x] Barre candidate vengono risolte con i dati child 1m

Note stato 2026-04-18:
- [x] `plan_market_data.py` ora accetta `--simulation-tf` e `--detail-tf`
- [x] `sync_market_data.py` scarica anche il child TF leggendo il piano multi-timeframe
- [x] `IntrabarResolution` esteso con audit su candidate reasons, barre discese ed ordine eventi

---

## Fase 6 - Stubs UI tipi dati futuri ✅ COMPLETATA

### 6.1 Modello stato in `ui/state.py` ✅
- [x] Introdurre dataclass `MarketDataTypeState`
- [x] Aggiungere `ohlcv_last: bool = True`
- [x] Aggiungere `ohlcv_mark: bool = False`
- [x] Estendere `MarketState` con `data_types: MarketDataTypeState = field(default_factory=MarketDataTypeState)`
- [x] Verificare che nessuna voce roadmap venga persistita come flag runtime operativo

### 6.2 Sezione tipo dati in `market_data_panel.py` ✅
- [x] Aggiungere gruppo `Tipo dati` nel `Setup`
- [x] Mostrare prima i dataset supportati e poi quelli roadmap in ordine stabile
- [x] Toggle `OHLCV last`: attivo, abilitato, default ON
- [x] Toggle `OHLCV mark`: attivo, abilitato, opzionale
- [x] Voce `Funding rate`: disabilitata, badge/label `roadmap`
- [x] Voce `Open interest`: disabilitata, badge/label `roadmap`
- [x] Voce `Liquidations`: disabilitata, badge/label `roadmap`
- [x] Voce `Bid/ask spread`: disabilitata, badge/label `roadmap`
- [x] Voce `Order book`: disabilitata, badge/label `roadmap`
- [x] Helper text spiega perché le voci roadmap sono disabilitate
- [x] Nota visibile: `Fees / Cost Model -> sezione separata`

### 6.3 Helper UI in `market_data_support.py` ✅
- [x] Implementare `supported_data_type_labels(selected: MarketDataTypeState) -> list[str]`
- [x] Implementare `roadmap_data_type_labels() -> list[str]`
- [x] Implementare `format_data_types_summary(...) -> str`
- [x] Riutilizzare gli helper nei summary del panel invece di duplicare label inline

### 6.4 Contratto backend invariato ✅
- [x] Nessun nuovo argomento CLI per funding/open interest/liquidations/spread/order book
- [x] Nessuna modifica a planner, sync, validate, cache o readiness per le voci roadmap
- [x] Interagire con voci roadmap non produce differenze nei comandi emessi dalla UI
- [x] Nessun branching backend aggiunto per tipi dati non supportati

### 6.5 Verifica Fase 6 ✅
- [x] I toggle roadmap sono visibili ma non cliccabili (`.disable()` in panel)
- [x] Selezionando `OHLCV last` o `OHLCV mark` si aggiorna solo stato/summary UI
- [x] Discovery e Result mostrano solo i tipi dati supportati attivi (via `supported_data_type_labels`)
- [x] Nessun codice backend aggiunto per i tipi dati non supportati
- [x] La roadmap UI resta estendibile aggiungendo una nuova voce stub senza riscrivere il flusso

---

## Criteri di accettazione finali (dal documento)

- [ ] L'utente vede una sezione Market DATA collassabile, separata e autosufficiente dentro Blocco 3
- [ ] Prima del download è disponibile una preview dei simboli e delle finestre richieste
- [ ] L'utente può scegliere chiaramente la modalità di validazione (`Full / Light / Off`)
- [ ] La GUI mostra una progress bar e una fase corrente leggibile durante tutto il processo
- [ ] Il processo produce un riepilogo finale con artifacts, coverage e validation status
- [ ] Il planner supporta buffer manuale con preset rapidi
- [ ] La struttura consente in futuro di aggiungere nuovi tipi dati senza riscrivere il flusso base
