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
- 🔲 UI NiceGUI ancora da completare (`src/signal_chain_lab/ui/`)

### Qualità e test
- ✅ Presenza suite unit/integration/golden (`tests/`)
- ⚠️ Esecuzione locale bloccata in questo ambiente su Python 3.10 (il progetto richiede 3.12+)

---

## 2) Obiettivi operativi correnti

1. **Chiudere Sprint 7 (S7.6)**: riprodurre top trial optimizer via scenario runner e documentare delta.
2. **Avviare Sprint 9 (UI)**: implementare workflow 3 blocchi (download/parse/backtest) con stato condiviso.
3. **Stabilizzare pipeline CI locale**: esecuzione test su Python 3.12 con comando standard unico.

---

## 3) Piano esecutivo breve (prossimi incrementi)

### Incremento A — Optimizer reproducibility (priorità alta)
- Selezionare top-N trial da output optimizer.
- Rieseguire ogni trial su benchmark fisso.
- Confrontare score/metriche aggregate e registrare scostamento ammesso.
- Aggiornare checklist S7.6 e aggiungere test/regression check dedicato.

### Incremento B — UI MVP (priorità media)
- Implementare `ui/app.py` con layout a 3 blocchi.
- Collegare `ui/components/log_panel.py` e `quality_report.py` ai dati scenario.
- Definire checkpoint manuale obbligatorio tra parse e backtest.

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
- [ ] UI NiceGUI minima operativa per workflow guidato
- [ ] test suite eseguita green in ambiente Python 3.12

---

## 5) Regole di aggiornamento documentazione

Ad ogni variazione di stato sprint:

1. aggiornare `docs/CHECKLIST_SVILUPPO.md`
2. aggiornare questo file (`docs/PIANO_OPERATIVO.md`)
3. aggiornare `README.md` se cambia setup/stato globale
4. riportare eventuali blocchi ambiente con data esplicita
