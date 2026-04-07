# Piano Operativo di Sviluppo — Signal Chain Backtesting Lab
**Versione:** 1.1  
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
- 🔶 Optimizer implementato, da chiudere validazione riproducibilità top trial (`src/signal_chain_lab/optimizer/`)
- 🔶 UI NiceGUI in stato MVP parziale (`src/signal_chain_lab/ui/`): presenti app/state/components, manca refactor blocchi dedicati + validazione manuale
- 🔶 Ingestion Telegram disponibile in modalità **storica/offline** via `parser_test/scripts/import_history.py`; listener live `src.telegram` non incluso nel workspace corrente

### Qualità e test
- ✅ Presenza suite unit/integration/golden (`tests/`)
- ⚠️ Esecuzione locale bloccata in questo ambiente su Python 3.10 (il progetto richiede 3.12+)

---

## 2) Obiettivi operativi correnti

1. **Chiudere Sprint 7 (S7.6)**: riprodurre top trial optimizer via scenario runner e documentare delta.
2. **Chiudere Sprint 9 (UI)**: estrarre i 3 blocchi in moduli dedicati e completare validazione manuale end-to-end.
3. **Stabilizzare pipeline CI locale**: esecuzione test su Python 3.12 con comando standard unico.
4. **Allineare documentazione parser_test/ingestion**: mantenere coerente la distinzione tra import storico e listener live.

---

## 3) Piano esecutivo breve (prossimi incrementi)

### Incremento A — Optimizer reproducibility (priorità alta)
- Selezionare top-N trial da output optimizer.
- Rieseguire ogni trial su benchmark fisso.
- Confrontare score/metriche aggregate e registrare scostamento ammesso.
- Aggiornare checklist S7.6 e aggiungere test/regression check dedicato.

### Incremento B — UI hardening (priorità media)
- Estrarre la logica da `ui/app.py` in `ui/blocks/block_download.py`, `block_parse.py`, `block_backtest.py`.
- Mantenere `ui/components/log_panel.py` e `quality_report.py` come componenti riusabili.
- Eseguire test manuale guidato completo con checkpoint umano tra parse e backtest (chiusura S9.8).

### Incremento C — Hardening operativo (priorità media)
- Uniformare export artifact (`JSONL`, `CSV`, `HTML`, `PNG`) per singola run e scenario.
- Rafforzare logging warning su fallback e collisioni intrabar.
- Verificare allineamento docs (`README`, checklist, architecture) ad ogni merge.

---

## 4) Criteri di completamento aggiornati

Il progetto può considerarsi "MVP backtesting completo" quando:

- [x] replay end-to-end chain singola e scenario policy comparison sono disponibili
- [x] report base/avanzati sono generabili da CLI
- [ ] optimizer top-trial reproducibility è verificato e tracciato
- [ ] UI NiceGUI completata (blocchi modulari + workflow validato manualmente)
- [ ] test suite eseguita green in ambiente Python 3.12

---

## 5) Regole di aggiornamento documentazione

Ad ogni variazione di stato sprint:

1. aggiornare `docs/CHECKLIST_SVILUPPO.md`
2. aggiornare questo file (`docs/PIANO_OPERATIVO.md`)
3. aggiornare `README.md` se cambia setup/stato globale
4. riportare eventuali blocchi ambiente con data esplicita
