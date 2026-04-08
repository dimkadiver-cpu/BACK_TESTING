# Piano Operativo di Sviluppo — Signal Chain Backtesting Lab
**Versione:** 1.7
**Aggiornato:** 2026-04-08
**Riferimento PRD:** `PRD_consolidato_signal_chain_lab.md`, `docs/PRD_market_data_backtesting_incrementale.md`, `docs/mini_prd_allegato_bybit_provider_backtesting.md`

---

## 1) Stato reale del repository

### Core backtesting
- ✅ Modelli dominio canonico (`src/signal_chain_lab/domain/`)
- ✅ Adapter DB e validazione (`src/signal_chain_lab/adapters/`)
- ✅ Simulation engine (`src/signal_chain_lab/engine/`)
- ✅ Market data layer CSV/Parquet + intrabar (`src/signal_chain_lab/market/`)
- ✅ Policy loader + policy baseline/custom (`src/signal_chain_lab/policies/`, `configs/policies/`)
- ✅ Scenario runner (`src/signal_chain_lab/scenario/`, `scripts/run_scenario.py`)
- ✅ Reporting (`src/signal_chain_lab/reports/`)
- ✅ Optimizer implementato + riproducibilità top trial verificata (`src/signal_chain_lab/optimizer/`, `tests/integration/test_optimizer_reproducibility.py`)
- ✅ UI NiceGUI: blocchi modulari estratti (`ui/blocks/block_download/parse/backtest.py`), `app.py` ridotto a orchestratore; workflow manuale S9.8 chiuso
- 🔶 Ingestion Telegram disponibile in modalità **storica/offline** via `parser_test/scripts/import_history.py`; listener live `src.telegram` non incluso nel workspace corrente
- 🔶 Market provider layer presente a livello libreria (`market/providers/csv_provider.py`, `parquet_provider.py`) ma non ancora cablato nel flusso scenario ufficiale (`scripts/run_scenario.py` usa ancora `market_provider=None`)

### Qualità e test
- ✅ Presenza suite unit/integration/golden (`tests/`)
- ⚠️ Esecuzione locale bloccata in questo ambiente su Python 3.11 / mancano dipendenze (pydantic, ecc.) — il progetto richiede Python 3.12+ con deps installate

---

## 2) Obiettivi operativi correnti

1. ~~**Chiudere Sprint 7 (S7.6)**~~ ✅ **FATTO** — test riproducibilità top trial in `tests/integration/test_optimizer_reproducibility.py` (3 trial, snapshot v1.0, delta ammesso = 0.0).
2. ~~**Chiudere Sprint 9 (UI)**~~ ✅ **FATTO** — blocchi modulari e test manuale workflow S9.8 completati.
3. ~~**Stabilizzare pipeline CI locale**~~ ✅ **FATTO** — 56/56 test verdi su Python 3.12.9 con `pip install -e ".[analytics,optimizer,dev]"` + `python -m pytest tests/ -v`.
4. **Sbloccare integrazione market data incrementale** allineata ai nuovi PRD: planner DB-driven, cache persistente, sync gap-only, validazione e provider canonico Bybit (last/mark).

---

## 3) Piano esecutivo breve (prossimi incrementi)

### Incremento A — Optimizer reproducibility ✅ COMPLETATO (2026-04-07)
- ~~Selezionare top-N trial da output optimizer.~~ → 3 trial fissi con parametri rappresentativi (seed=42, snapshot v1.0).
- ~~Rieseguire ogni trial su benchmark fisso.~~ → `run_scenarios` su `benchmark_chains.json`.
- ~~Confrontare score/metriche aggregate e registrare scostamento ammesso.~~ → delta = 0.0 (motore deterministico).
- ~~Aggiornare checklist S7.6 e aggiungere test/regression check dedicato.~~ → `tests/integration/test_optimizer_reproducibility.py` — 2 test: `test_top_trial_is_reproducible` (parametrizzato × 3) + `test_top_trials_regression_snapshot`.

### Incremento B — UI hardening ✅ PARZIALE (2026-04-07)
- ~~Estrarre la logica da `ui/app.py` in `ui/blocks/block_download.py`, `block_parse.py`, `block_backtest.py`.~~ → Fatto: 3 moduli creati, `app.py` da 260 → 59 righe, orchestrazione via `backtest_button_holder` condiviso.
- ~~Mantenere `ui/components/log_panel.py` e `quality_report.py` come componenti riusabili.~~ → Invariati, importati dai blocchi.
- ~~Eseguire test manuale guidato completo con checkpoint umano tra parse e backtest (chiusura S9.8)~~ ✅ **FATTO** — fixture DB `parser_test/db/s9_fixture.sqlite3` (3 chain simulabili), bug `order_type` uppercase/lowercase risolto in `state_machine.py`, `block_parse.py` skip `replay_parser` su `source_kind=existing_db`.

### Incremento D — Decision lock Market Data (PRD alignment) ✅ COMPLETATO (2026-04-08)

**Obiettivo:** congelare decisioni di prodotto/architettura per il market data layer in modo da rimuovere ambiguità implementative.

**Decisioni fissate (fonte PRD incrementale + mini PRD Bybit):**
- provider canonico ufficiale: **Bybit** per run exchange-faithful
- mercato prioritario: **futures linear**
- basi prezzo minime: **last + mark** (index opzionale fase successiva)
- strategia dati: **planner iniziale DB-driven + cache locale incrementale + download solo gap**
- storage: **Parquet partizionato** con manifest di copertura/validazione/download log
- runtime desiderato: **offline-first**, senza fallback silenzioso cross-exchange nei run ufficiali

### Incremento E — Market Data Backtesting Incrementale (MVP) 🔲 TODO

**Obiettivo:** rendere operativo il flusso `plan → sync → validate → backtest` con cache locale incrementale.

**Deliverable MVP (in ordine):**
1. Scanner domanda da DB segnali (simboli + intervalli chain)
2. Coverage planner con buffer adattivi e merge intervalli
3. Coverage index/manifest + gap detection
4. Sync incrementale Bybit (`last` e `mark`) in Parquet
5. Validazione minima dataset e logging job
6. Integrazione provider in `run_scenario.py` e GUI (`block_backtest.py`)

### Incremento F — Hardening Market Data 🔲 TODO

**Obiettivo:** completare robustezza operativa e governance dati.

**Deliverable hardening:**
- estensione automatica finestre per trade ancora aperti
- report coverage leggibile per simbolo/timeframe/basis
- gestione errori strutturata (rate limit, simboli assenti, partizioni corrotte)
- test integrazione/golden su run ufficiale Bybit exchange-faithful

---

### Incremento C — Hardening operativo ✅ COMPLETATO (2026-04-07)
- ~~Uniformare export artifact (`JSONL`, `CSV`, `HTML`, `PNG`) per singola run e scenario.~~ → Fatto: `run_single_chain.py` produce 5 artifact; `run_scenario.py` produce 4 artifact (CSV combinato + HTML scenario con equity curve).
- ~~Rafforzare logging warning su fallback e collisioni intrabar.~~ → Fatto: `logging.warning()` emesso in `simulator.py` (con signal_id/symbol/warning_code) e in `intrabar_resolver.py` (con timestamp/side/prezzi) su ogni caso di fallback.
- ~~Verificare allineamento docs (`README`, checklist, architecture) ad ogni merge.~~ → Fatto: `CHECKLIST_SVILUPPO.md` v1.1 aggiornata con sezione Incremento C; `PIANO_OPERATIVO.md` v1.4 aggiornato; `README.md` aggiornato.

---

## 4) Criteri di completamento aggiornati

Il progetto può considerarsi "MVP backtesting completo" quando:

- [x] replay end-to-end chain singola e scenario policy comparison sono disponibili
- [x] report base/avanzati sono generabili da CLI
- [x] optimizer top-trial reproducibility è verificato e tracciato
- [x] UI NiceGUI completata (blocchi modulari estratti, S9.8 chiuso)
- [ ] test suite eseguita green in ambiente Python 3.12
- [ ] pipeline market data incrementale disponibile (plan/sync/validate/coverage)
- [ ] run ufficiale Bybit exchange-faithful attivo (last/mark, no fallback cross-exchange)
- [ ] market provider cablato in `run_scenario.py` e GUI con PnL non-zero su dataset coperto

---

## 5) Regole di aggiornamento documentazione

Ad ogni variazione di stato sprint:

1. aggiornare `docs/CHECKLIST_SVILUPPO.md`
2. aggiornare questo file (`docs/PIANO_OPERATIVO.md`)
3. aggiornare `README.md` se cambia setup/stato globale
4. riportare eventuali blocchi ambiente con data esplicita
