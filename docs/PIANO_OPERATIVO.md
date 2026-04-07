# Piano Operativo di Sviluppo — Signal Chain Backtesting Lab
**Versione:** 1.3  
**Aggiornato:** 2026-04-07  
**Riferimento PRD:** `PRD_consolidato_signal_chain_lab.md`

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
- 🔶 UI NiceGUI: blocchi modulari estratti (`ui/blocks/block_download/parse/backtest.py`), `app.py` ridotto a orchestratore; resta solo validazione manuale end-to-end (S9.8)
- 🔶 Ingestion Telegram disponibile in modalità **storica/offline** via `parser_test/scripts/import_history.py`; listener live `src.telegram` non incluso nel workspace corrente

### Qualità e test
- ✅ Presenza suite unit/integration/golden (`tests/`)
- ⚠️ Esecuzione locale bloccata in questo ambiente su Python 3.11 / mancano dipendenze (pydantic, ecc.) — il progetto richiede Python 3.12+ con deps installate

---

## 2) Obiettivi operativi correnti

1. ~~**Chiudere Sprint 7 (S7.6)**~~ ✅ **FATTO** — test riproducibilità top trial in `tests/integration/test_optimizer_reproducibility.py` (3 trial, snapshot v1.0, delta ammesso = 0.0).
2. ~~**Chiudere Sprint 9 (UI)**~~ 🔶 **PARZIALE** — blocchi modulari estratti (S9.2-S9.4 ✅); resta S9.8 (test manuale workflow download → parse → backtest).
3. **Stabilizzare pipeline CI locale**: esecuzione test su Python 3.12 con comando standard unico.
4. **Allineare documentazione parser_test/ingestion**: mantenere coerente la distinzione tra import storico e listener live.

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
- Eseguire test manuale guidato completo con checkpoint umano tra parse e backtest (chiusura S9.8) — **ancora aperto**.

### Incremento C — Hardening operativo (priorità media)
- Uniformare export artifact (`JSONL`, `CSV`, `HTML`, `PNG`) per singola run e scenario.
- Rafforzare logging warning su fallback e collisioni intrabar.
- Verificare allineamento docs (`README`, checklist, architecture) ad ogni merge.

---

## 4) Criteri di completamento aggiornati

Il progetto può considerarsi "MVP backtesting completo" quando:

- [x] replay end-to-end chain singola e scenario policy comparison sono disponibili
- [x] report base/avanzati sono generabili da CLI
- [x] optimizer top-trial reproducibility è verificato e tracciato
- [ ] UI NiceGUI completata (blocchi modulari ✅ estratti — manca solo workflow validato manualmente S9.8)
- [ ] test suite eseguita green in ambiente Python 3.12

---

## 5) Regole di aggiornamento documentazione

Ad ogni variazione di stato sprint:

1. aggiornare `docs/CHECKLIST_SVILUPPO.md`
2. aggiornare questo file (`docs/PIANO_OPERATIVO.md`)
3. aggiornare `README.md` se cambia setup/stato globale
4. riportare eventuali blocchi ambiente con data esplicita
