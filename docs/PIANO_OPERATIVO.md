# Piano Operativo di Sviluppo — Signal Chain Backtesting Lab
**Versione:** 1.0  
**Generato:** 2026-04-07  
**Riferimento PRD:** `PRD_consolidato_signal_chain_lab.md`

---

## Stato attuale del repository

| Modulo | File | Stato |
|---|---|---|
| Bootstrap struttura repo | cartelle, pyproject, configs | ✅ FATTO |
| `chain_builder.py` | adapter lettura DB | ✅ IMPLEMENTATO |
| `audit_existing_db.py` | script audit 127 righe | ✅ IMPLEMENTATO |
| `domain/` enums, events, trade_state | tutti i file | 🔲 STUB solo |
| `engine/` simulator, state_machine, fill_model | tutti i file | 🔲 STUB solo |
| `market/` data_models, providers | tutti i file | 🔲 STUB solo |
| `policies/` base, policy_loader | tutti i file | 🔲 STUB solo |
| `reports/` event_log, trade_report | tutti i file | 🔲 STUB solo |
| `scripts/run_single_chain.py` | 9 righe stub | 🔲 STUB solo |
| `scripts/run_scenario.py` | 9 righe stub | 🔲 STUB solo |
| `tests/unit/` | vuoto | 🔲 TODO |
| `tests/integration/` | vuoto | 🔲 TODO |
| `tests/golden/` | solo README | 🔲 TODO |

---

## Fase 0 — Audit e preparazione del DB esistente

**Obiettivo:** verificare che il DB esistente sia riusabile senza riscrittura profonda.

**Stato:** PARZIALMENTE COMPLETATO (chain_builder esiste, audit script esiste)

### Task F0.1 — Eseguire audit_existing_db.py su DB reale
- Leggere schema DB esistente (tabelle: `raw_messages`, `parse_results`, `operational_signals`, `signals`)
- Estrarre almeno 20 chain reali campione
- Verificare presenza campi minimi: `signal_id`, `symbol`, `side`, `timestamp`, `trader_id`
- Verificare presenza dati minimi per simulazione: entry, stop_loss, take_profit
- Output: report audit DB in `docs/audit_db_report.md`

### Task F0.2 — Validare mapping verso modello canonico
- Verificare che `chain_builder.py` produca correttamente `SignalChain` / `ChainedMessage`
- Testare conversione su chain reale completa (con update)
- Testare conversione su chain signal-only nativa
- Classificare gap dati riscontrati: fatal / warning / optional

### Task F0.3 — Documentare contratto dati
- Aggiornare `docs/data-contracts.md` con mapping effettivo DB → modello canonico
- Elencare colonne DB usate per ogni campo canonico
- Marcare campi assenti o con mapping ambiguo

**Deliverable F0:**
- `docs/audit_db_report.md` con risultati
- `docs/data-contracts.md` aggiornato
- lista gap classificata

**Acceptance criteria F0:**
- DB letto correttamente
- contratto dati minimo verificato su esempi reali
- almeno 20 chain analizzate
- gap classificati in fatal / warning / optional

---

## Sprint 1 — Bootstrap e contratti (STRUTTURA COMPLETATA)

**Stato:** STRUTTURA COMPLETATA — tutti i file sono stub da implementare

Già presente:
- struttura cartelle
- `pyproject.toml`
- `.env.example`
- `configs/app.yaml`, `logging.yaml`
- `configs/policies/original_chain.yaml`, `signal_only.yaml`
- test skeleton (directory vuote)
- `settings.py`, `logging_config.py`

**Ancora da implementare nei file esistenti:**

### Task S1.1 — domain/enums.py
Implementare tutti gli enum dal PRD §12.1:
- `EventType`, `EventSource`, `TradeStatus`, `ChainInputMode`, `EventProcessingStatus`, `CloseReason`

### Task S1.2 — domain/events.py
Implementare Pydantic models dal PRD §12.2:
- `CanonicalEvent`, `CanonicalChain`

### Task S1.3 — domain/trade_state.py
Implementare dal PRD §12.4:
- `EntryPlan`, `FillRecord`, `TradeState`

### Task S1.4 — domain/warnings.py
Implementare dal PRD §12.5:
- `SimulationWarning`

### Task S1.5 — domain/results.py
Implementare dal PRD §12.8:
- `TradeResult`, `EventLogEntry` (dal PRD §12.6)

### Task S1.6 — policies/base.py
Implementare dal PRD §12.7:
- `PolicyConfig` con tutti i blocchi: entry, tp, sl, updates, pending, risk, execution

### Task S1.7 — adapters/validators.py (nuovo file o esistente)
Implementare:
- validazione `CanonicalChain` (campi minimi identità chain)
- validazione `NEW_SIGNAL` per simulazione standard (entry + sl + tp)
- classificazione gap: fatal / warning / optional

### Task S1.8 — chain_adapter.py (da chain_builder a canonical)
Implementare convertitore da `SignalChain` (formato chain_builder) a `CanonicalChain`:
- mappa eventi `NEW_SIGNAL` → `OPEN_SIGNAL`
- mappa update → eventi canonici
- imposta `input_mode` (CHAIN_COMPLETE o SIGNAL_ONLY_NATIVE)
- imposta `has_updates_in_dataset`

### Task S1.9 — Test base per domain models
In `tests/unit/`:
- `test_enums.py`: verifica enum definiti
- `test_trade_state.py`: costruzione, valori default
- `test_validators.py`: chain valida, chain senza entry, chain senza sl, chain senza tp

**Deliverable S1:**
- tutti i domain models implementati e validati
- adapter skeleton funzionante
- primi test unit verdi

---

## Sprint 2 — Replay core minimo auditabile

**Obiettivo:** primo replay end-to-end corretto e auditabile di una chain singola.

**Prerequisiti:** Sprint 1 completato e testato.

### Task S2.1 — engine/fill_model.py
Implementare fill model V1 (PRD §14):
- `market` order: fill dopo latenza configurata
- `limit` order: fill touch-based (touch = fill garantito V1, con warning che è assunzione)
- restituire `FillRecord` con price, qty, timestamp, fee

### Task S2.2 — engine/latency_model.py
Implementare latency model base:
- leggere `latency_ms` dalla policy execution
- applicare a timestamp fill

### Task S2.3 — engine/timeout_manager.py
Implementare gestione timeout (PRD §4.10, §11.8):
- `pending_timeout_hours`: cancella pending non fillati
- `chain_timeout_hours`: chiude/invalida chain scaduta
- output: eventi engine `CANCEL_PENDING` o `EXPIRED`

### Task S2.4 — engine/state_machine.py
Implementare state machine completa (PRD §14):
- transizioni stati: NEW → PENDING → ACTIVE → PARTIALLY_CLOSED → CLOSED/CANCELLED/EXPIRED/INVALID
- handler per ogni evento canonico:
  - `OPEN_SIGNAL`: init state, load entries, set sl/tp
  - `ADD_ENTRY`: aggiungi entry se compatibile
  - `MOVE_STOP`: aggiorna sl
  - `MOVE_STOP_TO_BE`: sposta sl a break-even
  - `CLOSE_PARTIAL`: riduci open size
  - `CLOSE_FULL`: chiudi tutto
  - `CANCEL_PENDING`: cancella pending
- modalità incoerenze V1: `soft` (ignored + warning)
- produrre `EventLogEntry` per ogni evento processato

### Task S2.5 — market/data_models.py
Implementare modelli market data:
- `Candle` (open, high, low, close, volume, timestamp, symbol, timeframe)
- `MarketMetadata`
- protocollo `MarketDataProvider` con metodi: `has_symbol`, `get_candle`, `get_range`, `get_intrabar_range`, `get_metadata`

### Task S2.6 — market/providers/csv_provider.py
Implementare `CSVProvider`:
- lettura file CSV OHLCV
- lookup per symbol + timeframe + timestamp
- gestione assenza dati (None esplicito)

### Task S2.7 — market/symbol_mapper.py
Implementare `SymbolMapper`:
- mapping simboli DB → simboli market data
- config-driven (non hardcoded)

### Task S2.8 — engine/simulator.py
Implementare simulator core (PRD §5.2B):
- input: `CanonicalChain` + `PolicyConfig` + `MarketDataProvider`
- loop eventi: per ogni barra di mercato nel range della chain:
  - applica eventi trader in ordine
  - applica trigger di mercato (fill, sl hit, tp hit)
  - gestisci timeout
- output: lista `EventLogEntry` + `TradeState` finale

### Task S2.9 — reports/event_log_report.py
Implementare produzione event log (PRD §16, §17):
- serializza lista `EventLogEntry` in JSONL
- salva in `artifacts/`

### Task S2.10 — reports/trade_report.py
Implementare produzione trade result (PRD §18.1):
- deriva `TradeResult` da `TradeState` finale + event log
- salva in Parquet

### Task S2.11 — Test replay singola chain
In `tests/unit/`:
- `test_state_machine.py`: tutte le transizioni di stato, MOVE_STOP prima del fill (ignored), CLOSE_FULL senza posizione (ignored)
- `test_fill_model.py`: fill market, fill limit touch
- `test_timeout_manager.py`: pending timeout, chain timeout

In `tests/integration/`:
- `test_single_chain_replay.py`: chain completa end-to-end (adapter → simulator → event_log → trade_result)

**Deliverable S2:**
- simulazione singola chain corretto end-to-end
- event log coerente
- trade result coerente
- warning e ignored events tracciati

---

## Sprint 3 — Policy baseline e run singolo

**Obiettivo:** replay singolo governato da policy baseline.

**Prerequisiti:** Sprint 2 completato e testato.

### Task S3.1 — policies/policy_loader.py
Implementare `PolicyLoader`:
- carica policy da YAML
- valida schema policy (campi obbligatori: name, updates, execution)
- fallback su default espliciti per campi mancanti
- restituisce `PolicyConfig`

### Task S3.2 — Compilare configs/policies/original_chain.yaml
Popolare con valori concreti (PRD §11.4, §11.7):
```yaml
name: original_chain
entry:
  use_original_entries: true
  entry_allocation: equal
  max_entries_to_use: null
  allow_add_entry_updates: true
tp:
  use_original_tp: true
  use_tp_count: null
  tp_distribution: original
sl:
  use_original_sl: true
  break_even_mode: none
  be_trigger: null
  move_sl_with_trader: true
updates:
  apply_move_stop: true
  apply_close_partial: true
  apply_close_full: true
  apply_cancel_pending: true
  apply_add_entry: true
  partial_close_fallback_pct: 0.5
pending:
  pending_timeout_hours: 24
  chain_timeout_hours: 168
  cancel_pending_on_timeout: true
  cancel_unfilled_if_tp1_reached_before_fill: false
  cancel_averaging_pending_after_tp1: false
execution:
  latency_ms: 0
  slippage_model: none
  fill_touch_guaranteed: true
```

### Task S3.3 — Compilare configs/policies/signal_only.yaml
Tutti gli update disabilitati, solo setup iniziale.

### Task S3.4 — scripts/run_single_chain.py
Implementare script CLI completo:
- argomenti: `--signal-id`, `--policy`, `--db-path`, `--market-dir`
- flusso: db_reader → chain_builder → chain_adapter → validator → simulator → report
- output: event log JSONL + trade result Parquet in `artifacts/`

### Task S3.5 — Test policy baseline
In `tests/unit/`:
- `test_policy_loader.py`: carica original_chain, carica signal_only, policy mancante
- `test_policy_baseline.py`: verifica che signal_only disabiliti tutti gli update

In `tests/integration/`:
- `test_original_chain_vs_signal_only.py`: stessa chain, due policy, risultati diversi distinguibili per policy_name

**Deliverable S3:**
- policy loader funzionante
- policy baseline compilate
- run_single_chain.py operativo

---

## Sprint 4 — Hardening su chain reali

**Obiettivo:** validazione forte del replay su casi reali.

**Prerequisiti:** Sprint 3 completato.

### Task S4.1 — Selezione benchmark dataset
- Selezionare almeno 10 chain reali dal DB
- Includere: chain completa con tutti gli update, chain signal-only nativa, chain con update incompatibili, chain con SL hit, chain con TP hit, chain CANCELLED, chain EXPIRED

### Task S4.2 — Fixtures benchmark
In `tests/fixtures/`:
- esportare le chain selezionate come fixture JSON/JSONL
- documentare l'esito atteso (close_reason, status, pnl indicativo)

### Task S4.3 — Golden tests
In `tests/golden/`:
- per ogni chain benchmark: congelare event log essenziale + trade result essenziale
- `test_golden_chains.py`: verifica che output replay corrisponda al golden congelato

### Task S4.4 — Regression test base
- `test_regression_metrics.py`: verifica metriche chiave, warning count, ignored events

### Task S4.5 — Verifica warning / ignored events reali
- Eseguire replay su tutte le chain benchmark
- Ispezionare manualmente warning prodotti
- Correggere eventuali falsi positivi o falsi negativi nel motore

**Deliverable S4:**
- set chain benchmark validate
- golden tests stabili
- regression test operativi

---

## Sprint 5 — Scenario runner

**Obiettivo:** confronto multi-policy coerente.

**Prerequisiti:** Sprint 4 completato.

### Task S5.1 — Scenario runner core
In `src/signal_chain_lab/`:
- `scenario/runner.py`: esegue stessa chain (o dataset) con lista policy
- aggrega `TradeResult` multipli in `ScenarioResult`
- `ScenarioResult`: total_pnl, return_pct, max_drawdown, win_rate, profit_factor, expectancy, trades_count, simulated_chains_count, excluded_chains_count, avg_warnings_per_trade

### Task S5.2 — domain/results.py — ScenarioResult
Aggiungere `ScenarioResult` ai modelli dominio.

### Task S5.3 — Confronto scenari
- metriche di confronto (PRD §18.3): delta_pnl, delta_drawdown, delta_win_rate, delta_expectancy
- output: `scenario_comparison.parquet`

### Task S5.4 — scripts/run_scenario.py
Implementare script CLI completo:
- argomenti: `--policy original_chain,signal_only`, `--db-path`, `--market-dir`, `--date-from`, `--date-to`
- output: scenario_results.parquet + summary console

### Task S5.5 — Policy custom base (1-2 esempi)
- `be_after_tp1`: break-even automatico dopo TP1
- `tp_50_30_20`: distribuzione custom dei TP

### Task S5.6 — Test scenario runner
- `test_scenario_runner.py`: stesso dataset, due policy, risultati distinguibili e aggregati coerenti

**Deliverable S5:**
- scenario runner operativo
- confronto original_chain vs signal_only funzionante
- metriche aggregate corrette

---

## Sprint 6 — Intrabar / Realism milestone 1

**Obiettivo:** gestione robusta dei casi ambigui SL/TP same-candle.

**Prerequisiti:** Sprint 5 completato.

### Task S6.1 — market/intrabar_resolver.py
Implementare `IntrabarResolver`:
- accetta parent candle + child timeframe candles
- determina ordine plausibile tra SL hit e TP hit
- restituisce esito auditabile con motivo

### Task S6.2 — market/providers/parquet_provider.py
Implementare `ParquetProvider`:
- lettura dati di mercato da file Parquet
- supporto child timeframe per intrabar

### Task S6.3 — Integrazione intrabar nel simulator
- rilevare collisioni SL/TP nella stessa barra
- invocare intrabar_resolver quando child timeframe disponibile
- fallback deterministico con warning se child non disponibile

### Task S6.4 — Test intrabar
- caso con child timeframe disponibile
- caso con child timeframe assente (verifica fallback + warning)
- caso no-collision (verifica che intrabar non venga invocato inutilmente)

**Deliverable S6:**
- intrabar resolver implementato
- collisioni same-candle risolte correttamente
- fallback tracciati

---

## Sprint 7 — Optimizer

**Obiettivo:** primo studio optimizer replicabile su benchmark dataset.

**Prerequisiti:** Sprint 5 completato e stabile, metriche scenario stabili.

### Task S7.1 — optimizer/objective.py
Implementare funzione objective Optuna:
- `build_policy_from_trial(trial)` → `PolicyConfig`
- search space iniziale (PRD §19.2): entry_allocation, use_tp_count, tp_distribution, be_trigger, pending_timeout_hours
- `compute_score(scenario_result)` → float (esplicito e documentato)

### Task S7.2 — optimizer/runner.py
Implementare optimizer runner:
- crea studio Optuna con benchmark dataset
- salva trial: trial_id, params, metriche principali, score
- ranking configurazioni

### Task S7.3 — configs/optimizer.yaml
Configurazione optimizer separata:
- benchmark dataset path
- search space bounds
- n_trials
- scoring weights

### Task S7.4 — Test optimizer
- `test_objective.py`: build_policy_from_trial genera PolicyConfig valida
- `test_score.py`: compute_score restituisce float da metriche note

**Deliverable S7:**
- optimizer che gira trial salvati e ranking
- score esplicito e documentato
- riproducibile su benchmark dataset

---

## Sprint 8 — Reporting avanzato

**Obiettivo:** pacchetto report leggibile per analisi operative.

**Prerequisiti:** Sprint 5-7 completati.

### Task S8.1 — Plot singola chain
- `reports/chain_plot.py`: equity curve + eventi annotati su chart
- output PNG + HTML opzionale

### Task S8.2 — HTML report scenario
- `reports/html_report.py`: tabella trade results, metriche scenario, chart equity
- output HTML standalone

### Task S8.3 — Scenario comparison visual
- confronto multi-policy su equity curve unica
- delta metriche tabellare

### Task S8.4 — Export avanzato
- export CSV trade results
- export JSONL event log per singola chain

**Deliverable S8:**
- report HTML generato da scenario result
- plot chain operativo
- tutti gli artifact visuali derivati (non fonte di verità)

---

## Sprint 9 — GUI NiceGUI (parallelo a Sprint 6-8)

**Obiettivo:** pannello di configurazione e lancio (PRD §4.18).

Può iniziare dopo Sprint 3 se il backend è stabile.

### Task S9.1 — src/signal_chain_lab/ui/app.py
Entry point NiceGUI, layout 3 blocchi sequenziali.

### Task S9.2 — Blocco 1: Download dati
- form: sorgente (Telegram / DB esistente), chat_id, date range
- log panel in tempo reale
- output: path DB

### Task S9.3 — Blocco 2: Parse dati
- form: selezione DB, parser/profilo, trader mapping
- esegue replay parser → chain builder
- mostra report sintetico: N segnali, N simulabili, top warnings
- pulsante "Procedi al Backtest" sblocca Blocco 3

### Task S9.4 — Blocco 3: Backtest
- form: selezione DB parsato, policy, market data dir, timeframe, timeout
- esegue scenario runner
- mostra log + link artifact

### Task S9.5 — Componenti condivisi
- `ui/components/log_panel.py`: pannello log riusabile
- `ui/components/quality_report.py`: card report sintetico
- `ui/state.py`: stato condiviso tra blocchi

---

## Sprint 10 — V2 Realism (fase futura)

Scope (PRD §20 Fase 6):
- slippage model configurabile
- fee model avanzato
- partial fills più realistici

**Prerequisiti:** benchmark baseline stabili + golden tests passanti.

---

## Sprint 11 — V3 Realism (fase futura)

Scope (PRD §20 Fase 7):
- order book / tick-like handling
- funding
- liquidation logic
- regole exchange-specific avanzate

---

## Ordine di priorità assoluta (da PRD §24.6)

1. adapter prima del refactor
2. event log prima di optimizer
3. correctness prima di features
4. replay singola chain prima di portfolio
5. baseline policies prima di optimization
6. golden tests reali prima di realism avanzato

---

## Dipendenze tra sprint

```
F0 → S1 → S2 → S3 → S4 → S5 → S6
                              ↘ S7 (dopo S5)
                              ↘ S8 (dopo S5)
                    S3 → S9 (può iniziare in parallelo)
               S5 → S10 → S11
```
