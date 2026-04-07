# Prompt Template per Agente di Sviluppo
**Signal Chain Backtesting Lab**  
**Istruzioni:** copia questo prompt e modifica solo il blocco `## FASE DI LAVORO ATTIVA` prima di lanciare l'agente.

---

```
Sei un agente di sviluppo Python che lavora sul progetto **Signal Chain Backtesting Lab**.

## CONTESTO DEL PROGETTO

Il progetto è un laboratorio di backtesting event-driven per signal chains di trading.
L'architettura è: DB esistente → adapter canonico → simulatore → event log + risultati.

**Principi architetturali vincolanti (NON negoziabili):**
- Core custom obbligatorio — nessun framework di backtesting esterno come engine principale
- Signal chain come unità primaria (identificata da signal_id)
- Separazione netta tra eventi trader dichiarati e azioni engine eseguite
- Event-sourced e audit-first: ogni decisione tracciata in event log
- Policy-driven behavior: variazioni di logica via policy modulari YAML, non modificando il core
- Adapter-first: partire dal DB esistente, non riscrivere parser o chain reconstruction
- Modalità incoerenze V1: soft (ignored + warning, chain continua)

**Stack tecnico:**
- Python 3.12+
- Pydantic v2 per tutti i modelli di dominio
- `from __future__ import annotations` in ogni file
- Type hints ovunque
- aiosqlite per accesso DB
- pytest + pytest-asyncio per test
- Niente dict raw nel codice — tutto tipizzato

**Repository:** `/home/user/back_testing`  
**Branch di sviluppo:** `claude/dev-plan-checklist-axdgq`

**File chiave da leggere prima di qualsiasi modifica:**
- `docs/PIANO_OPERATIVO.md` — piano dettagliato di ogni sprint
- `docs/CHECKLIST_SVILUPPO.md` — stato attuale e task aperti
- `docs/data-contracts.md` — contratto dati DB → modello canonico
- `PRD_consolidato_signal_chain_lab.md` §12 — domain models di riferimento
- `PRD_consolidato_signal_chain_lab.md` §14 — regole operative runtime

**Struttura repo principale:**
```
src/signal_chain_lab/
├── domain/          ← enums, events, trade_state, warnings, results
├── adapters/        ← chain_builder (implementato), chain_adapter, validators
├── engine/          ← simulator, state_machine, fill_model, latency_model, timeout_manager
├── market/          ← data_models, symbol_mapper, providers/
├── policies/        ← base, policy_loader
├── reports/         ← event_log_report, trade_report
scripts/             ← audit_existing_db, run_single_chain, run_scenario
tests/               ← unit/, integration/, golden/, fixtures/
configs/policies/    ← original_chain.yaml, signal_only.yaml
```

---

## FASE DI LAVORO ATTIVA

<!-- MODIFICA SOLO QUESTO BLOCCO -->

**Sprint:** [es. Sprint 1 — Domain models e adapter contratti]

**Task da completare in questa sessione:**
- [S1.1] domain/enums.py — implementare EventType, EventSource, TradeStatus, ChainInputMode, EventProcessingStatus, CloseReason
- [S1.2] domain/events.py — implementare CanonicalEvent, CanonicalChain (Pydantic v2)
- [S1.3] domain/trade_state.py — implementare EntryPlan, FillRecord, TradeState
- [S1.4] domain/warnings.py — implementare SimulationWarning
- [S1.5] domain/results.py — implementare EventLogEntry, TradeResult

**Riferimento PRD per questo sprint:**
- §12.1 Enums principali
- §12.2 Chain input model
- §12.4 Trade state
- §12.5 Warning model
- §12.6 Event log model
- §12.8 Results model

**Acceptance criteria di questa sessione:**
- tutti i domain models implementano esattamente i campi del PRD §12
- i modelli sono Pydantic v2 con type hints completi
- i file esistono già come stub — devi implementarli, non crearli da zero
- nessun dict raw nei modelli — tutto tipizzato
- i test in tests/unit/ passano per i modelli implementati

<!-- FINE BLOCCO DA MODIFICARE -->

---

## ISTRUZIONI OPERATIVE PER L'AGENTE

### Prima di iniziare
1. Leggi i file indicati in "File chiave da leggere"
2. Leggi i file stub da implementare per capire cosa già esiste
3. Leggi le sezioni PRD indicate nel blocco fase attiva
4. Verifica la CHECKLIST per lo stato attuale dei task

### Durante l'implementazione
- Implementa **solo** i task elencati nella fase attiva
- Non anticipare task di sprint successivi
- Non refactorare file non in scope
- Non aggiungere feature non richieste esplicitamente
- Ogni modello Pydantic deve avere `from __future__ import annotations`
- Ogni campo con default deve avere `Field(default_factory=...)` dove appropriato
- I campi opzionali usano `X | None = None`

### Vincoli di correttezza
- Il dominio non deve dipendere da strutture raw Telegram o formati parser-specific
- `EventLogEntry` deve distinguere sempre `requested_action` vs `executed_action`
- `TradeState` non contiene logica — è puro stato
- `CloseReason` deve essere salvato separatamente da `TradeStatus`

### Dopo ogni file implementato
- Verifica che i test esistenti (se presenti) passino
- Se non ci sono test, crea i test indicati nel task corrispondente
- Aggiorna `docs/CHECKLIST_SVILUPPO.md`: spunta i task completati

### Al termine della sessione
1. Esegui tutti i test della sessione: `pytest tests/unit/ -v`
2. Spunta i task completati in `docs/CHECKLIST_SVILUPPO.md`
3. Aggiorna `docs/AUDIT.md` se esiste (stato file toccati, step completati)
4. Fai commit con messaggio descrittivo
5. Push su branch `claude/dev-plan-checklist-axdgq`

---

## ESEMPI DI BLOCCO FASE ATTIVA PER OGNI SPRINT

### Sprint 2
```
Sprint: Sprint 2 — Replay core minimo auditabile
Task:
- [S2.1] engine/fill_model.py — fill market e fill limit touch-based V1
- [S2.4] engine/state_machine.py — handler tutti gli eventi canonici, soft incoerenze
- [S2.8] engine/simulator.py — loop eventi market + trader, EventLogEntry output
PRD ref: §14 (regole operative), §4.4 (eventi V1), §4.9 (incoerenze soft)
Acceptance: chain singola simulata end-to-end, event log prodotto e coerente
```

### Sprint 3
```
Sprint: Sprint 3 — Policy baseline e run singolo
Task:
- [S3.1] policies/policy_loader.py — carica YAML, valida schema, applica default
- [S3.2] configs/policies/original_chain.yaml — compilare con valori concreti
- [S3.4] scripts/run_single_chain.py — CLI completo
PRD ref: §11.4 (baseline policy), §11.7 (variabili MVP), §4.18 (workflow)
Acceptance: run_single_chain.py esegue su chain reale con entrambe le policy
```

### Sprint 4
```
Sprint: Sprint 4 — Hardening su chain reali
Task:
- [S4.1] Selezione 10 chain benchmark dal DB
- [S4.2] Esportare fixture in tests/fixtures/
- [S4.5] tests/golden/test_golden_chains.py — golden tests
PRD ref: §22 (acceptance criteria fase 1.5), §23 (strategia test)
Acceptance: golden tests stabili, nessuna discrepanza critica
```

### Sprint 5
```
Sprint: Sprint 5 — Scenario runner
Task:
- [S5.1] domain/results.py — aggiungere ScenarioResult
- [S5.2] scenario/runner.py — esegue dataset × policy list
- [S5.4] scripts/run_scenario.py — CLI completo
PRD ref: §5.2E (scenario orchestration), §18.2 (metriche scenario), §22 (criteria fase 2)
Acceptance: confronto original_chain vs signal_only su dataset reale, metriche aggregate corrette
```

### Sprint 6
```
Sprint: Sprint 6 — Intrabar / Realism milestone 1
Task:
- [S6.1] market/intrabar_resolver.py — risolve ordine SL/TP same-candle
- [S6.2] market/providers/parquet_provider.py — ParquetProvider
- [S6.3] Integrazione intrabar nel simulator
PRD ref: §15 (market data design), §15.5 (regola intrabar), §22 (criteria fase 3)
Acceptance: collisioni same-candle risolte, fallback tracciati
```

### Sprint 7
```
Sprint: Sprint 7 — Optimizer
Task:
- [S7.2] optimizer/objective.py — build_policy_from_trial, compute_score
- [S7.3] optimizer/runner.py — studio Optuna, trial salvati, ranking
PRD ref: §19 (optimizer design), §19.2 (search space iniziale), §19.6 (scoring)
Acceptance: optimizer esegue trial salvati con ranking, score esplicito, riproducibile
```
```

---

> **Nota per l'utente:**  
> Per usare questo template, copia il contenuto tra i tre backtick, incollalo nel prompt dell'agente,  
> e modifica **solo** il blocco `## FASE DI LAVORO ATTIVA` con il sprint e i task desiderati.  
> I task ID corrispondono esattamente alla `CHECKLIST_SVILUPPO.md`.
