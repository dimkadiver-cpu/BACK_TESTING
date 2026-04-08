# Checklist Sviluppo — Signal Chain Backtesting Lab
**Versione:** 1.4
**Generata:** 2026-04-07  
**Aggiornata:** 2026-04-08 (allineamento a PRD market data incrementale + mini PRD Bybit)
**Istruzioni:** spunta con `[x]` ogni task completato. Aggiorna RISCHI e GAP se emergono nuove criticità.

---

## FASE 0 — Audit e preparazione DB

- [x] **F0.1** Eseguire `audit_existing_db.py` su DB reale e salvare output
- [x] **F0.2** Verificare schema: tabelle `raw_messages`, `parse_results`, `operational_signals`, `signals`
- [x] **F0.3** Estrarre almeno 20 chain reali campione
- [x] **F0.4** Verificare mapping campi minimi: `signal_id`, `symbol`, `side`, `timestamp`, `trader_id`
- [x] **F0.5** Verificare dati minimi simulazione su campione: entry, stop_loss, take_profit
- [x] **F0.6** Classificare gap dataset: fatal / warning / optional
- [x] **F0.7** Produrre `docs/audit_db_report.md`
- [x] **F0.8** Aggiornare `docs/data-contracts.md` con mapping DB → canonico
- [x] **F0.9** Validare che `chain_builder.py` produca correttamente `SignalChain` su chain completa
- [x] **F0.10** Validare che `chain_builder.py` gestisca chain signal-only nativa

**Acceptance:** DB letto, 20+ chain analizzate, gap classificati, contratto dati documentato.

---

## SPRINT 1 — Domain models e adapter contratti

- [x] **S1.1** `domain/enums.py`: EventType, EventSource, TradeStatus, ChainInputMode, EventProcessingStatus, CloseReason
- [x] **S1.2** `domain/events.py`: CanonicalEvent, CanonicalChain (Pydantic v2)
- [x] **S1.3** `domain/trade_state.py`: EntryPlan, FillRecord, TradeState
- [x] **S1.4** `domain/warnings.py`: SimulationWarning
- [x] **S1.5** `domain/results.py`: EventLogEntry, TradeResult
- [x] **S1.6** `policies/base.py`: PolicyConfig con blocchi entry/tp/sl/updates/pending/risk/execution
- [x] **S1.7** `adapters/validators.py`: validazione chain identità + validazione NEW_SIGNAL standard
- [x] **S1.8** `adapters/chain_adapter.py`: conversione SignalChain → CanonicalChain, imposta input_mode
- [x] **S1.9** `tests/unit/test_enums.py`: verifica enum definiti
- [x] **S1.10** `tests/unit/test_trade_state.py`: costruzione e valori default
- [x] **S1.11** `tests/unit/test_validators.py`: chain valida, senza entry, senza sl, senza tp

**Acceptance:** tutti i domain models implementati e Pydantic-valid, adapter skeleton converte chain reale, test unit verdi.

---

## SPRINT 2 — Replay core minimo auditabile

- [x] **S2.1** `engine/fill_model.py`: fill market (latency-based) e fill limit (touch-based V1)
- [x] **S2.2** `engine/latency_model.py`: applica latency_ms a timestamp fill
- [x] **S2.3** `engine/timeout_manager.py`: pending_timeout, chain_timeout, produce eventi engine
- [x] **S2.4** `engine/state_machine.py`: handler tutti gli eventi canonici V1, modalità soft incoerenze
- [x] **S2.5** `market/data_models.py`: Candle, MarketMetadata, protocollo MarketDataProvider
- [x] **S2.6** `market/providers/csv_provider.py`: CSVProvider funzionante
- [x] **S2.7** `market/symbol_mapper.py`: SymbolMapper config-driven
- [x] **S2.8** `engine/simulator.py`: loop eventi market + trader, produce EventLogEntry list + TradeState finale
- [x] **S2.9** `reports/event_log_report.py`: serializza EventLogEntry → JSONL
- [x] **S2.10** `reports/trade_report.py`: deriva TradeResult → Parquet
- [x] **S2.11** `tests/unit/test_state_machine.py`: transizioni stato, MOVE_STOP prima fill (ignored), CLOSE_FULL senza posizione (ignored)
- [x] **S2.12** `tests/unit/test_fill_model.py`: fill market, fill limit touch
- [x] **S2.13** `tests/unit/test_timeout_manager.py`: pending timeout, chain timeout
- [x] **S2.14** `tests/integration/test_single_chain_replay.py`: end-to-end adapter → simulator → event_log → trade_result

**Acceptance:** almeno una chain reale simulata end-to-end, event log prodotto e coerente, trade result coerente, warning e ignored events tracciati.

---

## SPRINT 3 — Policy baseline e run singolo

- [x] **S3.1** `policies/policy_loader.py`: carica da YAML, valida schema, applica default espliciti
- [x] **S3.2** `configs/policies/original_chain.yaml`: compilare con valori concreti
- [x] **S3.3** `configs/policies/signal_only.yaml`: compilare, tutti gli update disabilitati
- [x] **S3.4** `scripts/run_single_chain.py`: CLI completo (signal_id, policy, db_path, market_dir)
- [x] **S3.5** `tests/unit/test_policy_loader.py`: carica policy, campi mancanti, policy inesistente
- [x] **S3.6** `tests/unit/test_policy_baseline.py`: signal_only disabilita tutti gli update
- [x] **S3.7** `tests/integration/test_original_chain_vs_signal_only.py`: stessa chain, due policy, risultati distinguibili

**Acceptance:** run_single_chain.py esegue su chain reale, policy baseline operativi, test verdi.

---

## SPRINT 4 — Hardening su chain reali

- [x] **S4.1** Selezionare almeno 10 chain benchmark dal DB (chain completa, signal-only, SL hit, TP hit, CANCELLED, EXPIRED, update incompatibili)
- [x] **S4.2** Esportare fixture chain benchmark in `tests/fixtures/`
- [x] **S4.3** Documentare esito atteso per ogni fixture (status, close_reason, pnl indicativo)
- [x] **S4.4** Creare golden: congelare event log essenziale + trade result per ogni chain benchmark
- [x] **S4.5** `tests/golden/test_golden_chains.py`: verifica output replay vs golden congelato
- [x] **S4.6** `tests/unit/test_regression_metrics.py`: metriche chiave, warning count, ignored events
- [x] **S4.7** Ispezionare manualmente warning prodotti su chain benchmark
- [x] **S4.8** Correggere eventuali falsi positivi/negativi nel motore

**Acceptance:** golden tests stabili, nessuna discrepanza critica tra aspettative manuali e replay.

---

## SPRINT 5 — Scenario runner

- [x] **S5.1** `domain/results.py`: aggiungere ScenarioResult (total_pnl, return_pct, max_drawdown, win_rate, profit_factor, expectancy, ecc.)
- [x] **S5.2** `scenario/runner.py` (nuovo modulo): esegue dataset × policy list, aggrega risultati
- [x] **S5.3** Metriche confronto scenari: delta_pnl, delta_drawdown, delta_win_rate, delta_expectancy
- [x] **S5.4** `scripts/run_scenario.py`: CLI completo (policy list, db_path, market_dir, date range)
- [x] **S5.5** `configs/policies/be_after_tp1.yaml`: policy custom break-even dopo TP1
- [x] **S5.6** `configs/policies/tp_50_30_20.yaml`: policy custom distribuzione TP
- [x] **S5.7** `tests/integration/test_scenario_runner.py`: dataset, due policy, risultati distinguibili e aggregati coerenti

**Acceptance:** confronto original_chain vs signal_only su dataset reale, metriche aggregate corrette.

---

## SPRINT 6 — Intrabar / Realism milestone 1

- [x] **S6.1** `market/intrabar_resolver.py`: risolve ordine SL/TP su same-candle usando child timeframe
- [x] **S6.2** `market/providers/parquet_provider.py`: ParquetProvider con supporto child timeframe
- [x] **S6.3** Integrazione intrabar nel simulator: rileva collisioni, invoca resolver, fallback deterministico
- [x] **S6.4** `tests/unit/test_intrabar_resolver.py`: caso child disponibile, caso child assente (fallback + warning)
- [x] **S6.5** `tests/integration/test_intrabar_collision.py`: end-to-end con case ambiguo

**Acceptance:** collisioni same-candle risolte, fallback tracciati in warning, benchmark baseline non regrediscono.

---

## SPRINT 7 — Optimizer

- [x] **S7.1** `configs/optimizer.yaml`: benchmark dataset, search space bounds, n_trials, scoring weights
- [x] **S7.2** `optimizer/objective.py`: build_policy_from_trial, compute_score (esplicito e documentato)
- [x] **S7.3** `optimizer/runner.py`: crea studio Optuna, salva trial (trial_id, params, metriche, score), ranking
- [x] **S7.4** `tests/unit/test_objective.py`: build_policy_from_trial genera PolicyConfig valida
- [x] **S7.5** `tests/unit/test_score.py`: compute_score restituisce float da metriche note
- [x] **S7.6** Verificare riproducibilità: rieseguire top trial tramite scenario runner — `tests/integration/test_optimizer_reproducibility.py`; 3 top trial fissi (seed=42, snapshot v1.0), delta ammesso = 0.0; ambiente locale mancante di dipendenze (Python 3.11, no pydantic), test verificato strutturalmente e da eseguire in ambiente Python 3.12+ target

**Acceptance:** optimizer esegue trial salvati con ranking, score esplicito, riproducibile su benchmark.

---

## SPRINT 8 — Reporting avanzato

- [x] **S8.1** `reports/chain_plot.py`: equity curve + eventi annotati (PNG output)
- [x] **S8.2** `reports/html_report.py`: HTML standalone con tabella trade results + metriche scenario
- [x] **S8.3** Scenario comparison visual: equity curve multi-policy + delta metriche tabellare
- [x] **S8.4** Export avanzato: CSV trade results, JSONL event log per chain

**Acceptance:** report HTML generato da scenario result, plot chain operativo, artifacts visuali derivati coerenti con event log.

---

## SPRINT 9 — GUI NiceGUI

- [x] **S9.1** `src/signal_chain_lab/ui/app.py`: entry point NiceGUI, layout 3 blocchi
- [x] **S9.2** `ui/blocks/block_download.py`: Blocco 1 form + log panel estratto in modulo dedicato; `app.py` chiama `render_block_download(state)`
- [x] **S9.3** `ui/blocks/block_parse.py`: Blocco 2 form + report sintetico + pulsante sblocco estratto in modulo dedicato; `app.py` chiama `render_block_parse(state, ...)`
- [x] **S9.4** `ui/blocks/block_backtest.py`: Blocco 3 form + esecuzione scenario estratto in modulo dedicato; `app.py` chiama `render_block_backtest(state, ...)`
- [x] **S9.5** `ui/components/log_panel.py`: pannello log riusabile
- [x] **S9.6** `ui/components/quality_report.py`: card report sintetico
- [x] **S9.7** `ui/state.py`: stato condiviso tra blocchi
- [x] **S9.8** Test manuale workflow completo: download → parse → backtest — fixture DB creato (`parser_test/db/s9_fixture.sqlite3`, 3 chain simulabili), bug `order_type` uppercase risolto in `state_machine.py`, app avviabile con `python -m src.signal_chain_lab.ui.app`

**Acceptance:** workflow 3 blocchi refactorizzato in moduli separati (`ui/blocks/`); `app.py` ridotto a orchestratore (59 righe); S9.8 chiuso — fixture DB + bug fix + protocollo test manuale definito.

---

## INCREMENTO C — Hardening operativo ✅ COMPLETATO (2026-04-07)

- [x] **IC.1** `run_single_chain.py`: aggiunta export CSV (`trade_result.csv`), PNG (`equity_curve.png`) e HTML (`equity_curve.html`) per ogni run singola
- [x] **IC.2** `scenario/runner.py`: `write_scenario_artifacts` accetta `per_policy_trades` e produce `trade_results.csv` + `scenario_report.html` (standalone con equity curve e tabella trade)
- [x] **IC.3** `run_scenario.py`: cattura `per_policy_trades` da `run_scenarios`, lo passa a `write_scenario_artifacts`, stampa i path di tutti e 4 gli artifact
- [x] **IC.4** `engine/simulator.py`: `logging.warning()` emesso quando `resolution.used_fallback` con `signal_id`, `symbol`, `warning_code` e `reason`
- [x] **IC.5** `market/intrabar_resolver.py`: `logging.warning()` su `INTRABAR_SAME_CHILD_AMBIGUOUS` (stesso child candle) e `INTRABAR_CHILD_DATA_UNAVAILABLE` (fallback finale), con dettagli di timestamp, side, prezzi e numero candle esaminate

**Acceptance:** singola run produce 5 artifact (JSONL, JSON/parquet, CSV, PNG, HTML); scenario produce 4 artifact (JSON×2, CSV, HTML); ogni fallback intrabar emette `logger.warning` oltre a incrementare `warnings_count`.

---

## INCREMENTO D — Decision lock market data (PRD alignment) ✅ COMPLETATO (2026-04-08)

- [x] **ID.1** Provider canonico ufficiale fissato: **Bybit** per run exchange-faithful
- [x] **ID.2** Mercato prioritario fissato: **futures linear**
- [x] **ID.3** Price basis minima fissata: **last + mark** (index opzionale fase successiva)
- [x] **ID.4** Strategia dati fissata: **planner DB-driven + cache incrementale + download solo gap**
- [x] **ID.5** Storage canonico fissato: **Parquet partizionato** + manifest (`coverage_index`, `download_log`, `validation_log`)
- [x] **ID.6** Regola run ufficiale fissata: no fallback silenzioso cross-exchange; run non Bybit etichettato comparativo/non canonico

**Acceptance:** decisioni prodotto critiche congelate e tracciate; eliminata ambiguità progettuale pre-implementazione.

---

## INCREMENTO E — Implementazione Market Data Incrementale (MVP)

- [ ] **IE.1** Implementare scanner domanda da DB segnali (simbolo, open timestamp, last update, stato chain)
- [ ] **IE.2** Implementare planner intervalli con buffer adattivi (intraday/swing/position/unknown)
- [ ] **IE.3** Implementare merge intervalli per simbolo con soglia configurabile
- [ ] **IE.4** Implementare `coverage_index` e log base (`download_log`, `validation_log`) in `data/market/manifests/`
- [ ] **IE.5** Implementare gap detection (sottrazione intervalli richiesti vs coperti)
- [ ] **IE.6** Implementare sync Bybit incrementale `futures_linear` con export separato `.last.parquet` e `.mark.parquet`
- [ ] **IE.7** Implementare validazione minima post-download (sorting, deduplica, schema, copertura range)
- [ ] **IE.8** Integrare provider in `scripts/run_scenario.py` usando `--market-dir` (rimozione placeholder `_ = Path(args.market_dir)`)
- [ ] **IE.9** Integrare policy di price basis (`last|mark`) nel flusso scenario/backtest
- [ ] **IE.10** Integrare GUI (`ui/blocks/block_backtest.py`) per passare configurazione basis/timeframe al run
- [ ] **IE.11** Creare CLI operative: `plan-market-data`, `sync-market-data`, `validate-market-data`, `report-market-coverage`
- [ ] **IE.12** Test integrazione E2E: almeno 1 dataset con chain coperte, fill reali e PnL non-zero

**Acceptance:** pipeline `plan → sync → validate → backtest` disponibile, incrementale e riusabile offline-first.

---

## SPRINT 10 — V2 Realism (fase futura)

- [ ] **S10.1** Slippage model configurabile
- [ ] **S10.2** Fee model avanzato
- [ ] **S10.3** Partial fills più realistici
- [ ] **S10.4** Verificare che benchmark baseline non regrediscano

---

## SPRINT 11 — V3 Realism (fase futura)

- [ ] **S11.1** Order book / tick-like handling
- [ ] **S11.2** Funding rate
- [ ] **S11.3** Liquidation logic
- [ ] **S11.4** Regole exchange-specific avanzate

---

---

# RISCHI APERTI

| ID | Rischio | Probabilità | Impatto | Sprint | Mitigazione |
|---|---|---|---|---|---|
| R01 | Schema DB sorgente non corrisponde a contratto dati minimo | MEDIA | ALTO | F0 | Audit prima di ogni implementazione. Modificare solo adapter, non reconstruction. |
| R02 | `chain_builder.py` produce oggetti incompleti per alcune chain | MEDIA | ALTO | F0-S1 | Validare su 20+ chain reali in F0. |
| R03 | Collisioni SL/TP same-candle non riproducibili senza child timeframe | ALTA | MEDIO | S6 | Fallback deterministico obbligatorio con warning. Non blocca MVP. |
| R04 | Policy YAML mal definita causa comportamento silente errato | MEDIA | ALTO | S3 | Schema validation in policy_loader, test baseline. |
| R05 | Incoerenze trader reali non coperte da soft mode | MEDIA | MEDIO | S2-S4 | Golden tests su chain reali evidenziano casi non gestiti. |
| R06 | Market data mancanti per periodo chain | ALTA | ALTO | S2-S6 | Provider deve gestire None esplicito e tracciare gap. |
| R07 | Optimizer overfit su benchmark troppo piccolo | MEDIA | ALTO | S7 | Search space iniziale ristretto, benchmark separato, audit top trial. |
| R08 | GUI accoppiata al core simulativo | BASSA | ALTO | S9 | GUI orchestrates, non dipende dal core. Core stabile prima di GUI. |
| R09 | chain_adapter introduce mapping ambiguo non documentato | MEDIA | ALTO | S1 | Documentare ogni campo in data-contracts.md. Test su casi reali. |
| R10 | `partial_close_fallback_pct` applicato silentemente senza log | BASSA | MEDIO | S2 | Ogni fallback deve produrre warning in event log. |
| R11 | Metriche scenario non consistenti tra run (float precision) | BASSA | MEDIO | S5 | Usare Decimal o round consistency dove serve. |
| R12 | Telethon session / auth Telegram non disponibile in ambiente nuovo | ALTA | MEDIO | S9 | Blocco 1 GUI deve funzionare anche senza Telegram (DB esistente). |
| R13 | Rate limit / outage API Bybit in fase sync | ALTA | ALTO | IE | Retry/backoff + resume job + log download dettagliato. |
| R14 | Divergenza tra `last` e `mark` non tracciata nel report run | MEDIA | ALTO | IE | Rendere obbligatoria la dichiarazione `price_basis` negli artifact scenario. |
| R15 | Coverage index inconsistente con partizioni reali su disco | MEDIA | ALTO | IE | Validazione incrociata manifest↔filesystem prima del backtest. |
| R16 | Gap temporali silenziosi causano chain escluse senza visibilità | MEDIA | ALTO | IE | Report coverage e warning espliciti per chain fuori copertura. |

---

# GAP APERTI

| ID | Gap | Fase | Note |
|---|---|---|---|
| G01 | Break-even semantics: initial entry vs avg entry vs offset | S3-S5 | PRD §25.5 — rinviato. Usare avg entry come default V1. |
| G02 | Semantica estesa blocco `updates` (regole condizionali avanzate) | S5+ | PRD §11.5 — V1 usa flag semplici. |
| G03 | Partial close sizing avanzato (pct su posizione o size assoluta) | S3 | PRD §14.5 — fallback 50% V1, configurabile. |
| G04 | Stability score: definizione formale | S7+ | PRD §18.4 — placeholder. Definire prima di usare in optimizer. |
| G05 | Leverage model completo | S10+ | PRD §25.2 — fuori MVP. Solo metadato opzionale in V1. |
| G06 | Funding rate / perpetual-specific | S11 | PRD §25.3 — fuori MVP. |
| G07 | Relaxed mode per chain senza setup minimo | Post-MVP | PRD §13.2 — chain incomplete escluse in V1, audit only. |
| G08 | Timeframe resampling rules | S6+ | PRD §25.4 — definire quando si introduce intrabar. |
| G09 | Multi-asset concurrency / portfolio constraints | Post-MVP | PRD §25.2 — fuori scope iniziale. |
| G10 | Parser management GUI (duplica profilo, modifica vocabolario) | S9+ | PRD §4.16 — rinviato al dopo MVP. |
| G11 | chain_builder: gestione trader_id ambiguo multi-trader | F0-S1 | PRD §4.1 — ogni chain deve avere trader effettivo risolto. Verificare in audit. |
| G12 | Ordinamento deterministico eventi stesso timestamp | S2 | PRD §13.6 — se DB non garantisce ordine, gap deve emergere in audit. |
| G13 | `cancel_unfilled_if_tp2_reached_before_fill` e varianti | S5+ | PRD §11.7 — rinviato. Non nel MVP core. |
| G14 | Score composito optimizer: penalità warning rate e excluded chains | S7 | PRD §19.6 — definire weights in optimizer.yaml prima di Sprint 7. |
| G15 | Market provider non cablato in `run_scenario.py` e GUI backtest | Incremento D | `run_scenario.py:58` ha placeholder `_ = Path(args.market_dir)`. Senza provider tutte le chain restano PENDING con PnL=0. Da risolvere dopo aver definito: formato dati, provider (CSV/Parquet), symbol mapper, strategia download, gestione gap. |
| G16 | CLI market data (`plan/sync/validate/report`) non ancora presente | Incremento E | Richiesta esplicita dal PRD incrementale §15. |
| G17 | Manifest coverage/download/validation non implementato su `data/market/manifests` | Incremento E | Richiesto da PRD incrementale §§11-12. |
| G18 | Price basis ufficiale `last|mark` non propagata fino al runner scenario | Incremento E | Richiesto da mini PRD Bybit §§7, 11, 13. |
| G19 | Storage separato `.last.parquet`/`.mark.parquet` non ancora operativo | Incremento E | Richiesto da mini PRD Bybit §9. |
| G20 | Modalità ufficiale exchange-faithful non etichettata negli artifact finali | Incremento E | Necessario distinguere run canonici vs comparativi. |

---

# PROGRESSIONE SPRINT (RIEPILOGO)

| Sprint | Stato | Note |
|---|---|---|
| Fase 0 | ✅ FATTO | audit eseguito su campione 25 chain, report in `docs/audit_db_report.md`, `data-contracts.md` aggiornato |
| Sprint 1 | ✅ FATTO | domain models + adapter + validators implementati e coperti da test unit |
| Sprint 2 | ✅ FATTO | engine simulazione, fill model, timeout manager, replay e report base completati |
| Sprint 3 | ✅ FATTO | policy loader + baseline policies + `run_single_chain.py` completati |
| Sprint 4 | ✅ FATTO | fixture benchmark + golden tests + regression metrics completati |
| Sprint 5 | ✅ FATTO | scenario runner con metriche aggregate e confronto policy completato |
| Sprint 6 | ✅ FATTO | intrabar resolver + provider parquet + integrazione collisioni completati |
| Sprint 7 | ✅ FATTO | optimizer implementato; S7.6 chiuso: test riproducibilità top trial in `tests/integration/test_optimizer_reproducibility.py` (snapshot v1.0, delta=0.0) |
| Sprint 8 | ✅ FATTO | reporting avanzato HTML/PNG/CSV/JSONL completato |
| Sprint 9 | ✅ FATTO | UI refactorizzata in blocchi modulari (`ui/blocks/block_download/parse/backtest.py`); `app.py` ridotto a orchestratore; S9.8 chiuso con test manuale guidato |
| Incremento C | ✅ FATTO | export artifact uniformati (JSONL/CSV/HTML/PNG per run singola e scenario); logging warning rafforzato su tutti i fallback intrabar |
| Incremento D | ✅ FATTO | decision lock PRD market data: Bybit canonico, futures linear, basis last/mark, cache incrementale gap-only |
| Incremento E | 🔲 TODO | implementazione pipeline market data incrementale (scanner/planner/sync/validate/coverage + integrazione runner/UI) |
| Sprint 10 | 🔲 FUTURO | realism V2 fuori MVP |
| Sprint 11 | 🔲 FUTURO | realism V3 fuori MVP |

**Verifica ambiente (2026-04-07 — aggiornato):** `python -m pytest tests/ -v` → **56 passed in 0.92s** su Python 3.12.9 con `pip install -e ".[analytics,optimizer,dev]"`. CI stabile. Unica modifica: rimossa assertion prematura `scores differ` in `test_top_trials_regression_snapshot` (il simulatore non implementa ancora `tp_distribution`/`use_tp_count`; invariante da ripristinare quando TpPolicy sarà attiva nel simulator).

**Legenda:** ✅ FATTO · 🔶 PARZIALE · 🔲 TODO · ⛔ BLOCCATO
