# Prompt operativi — Implementazione funzioni Market Data Incrementale (Bybit)

Questa raccolta contiene prompt pronti da usare con un agente di sviluppo per implementare le funzioni richieste in `Incremento E` della checklist.

Riferimenti:
- `docs/PRD_market_data_backtesting_incrementale.md`
- `docs/mini_prd_allegato_bybit_provider_backtesting.md`
- `docs/PIANO_OPERATIVO.md` (Incremento E)
- `docs/CHECKLIST_SVILUPPO.md` (task IE.1 → IE.12)

---

## Prompt 1 — Scanner domanda + planner intervalli (IE.1, IE.2, IE.3)

```text
Sei un agente di sviluppo Python sul repository /workspace/back_testing.

Obiettivo sessione:
Implementare il blocco "demand scanner + coverage planner" per market data incrementale.

Task in scope (solo questi):
- IE.1 scanner domanda da DB segnali
- IE.2 planner intervalli con buffer adattivi
- IE.3 merge intervalli per simbolo

Vincoli funzionali:
1) Lo scanner deve estrarre per ogni chain almeno:
   - symbol
   - timestamp_open
   - timestamp_last_relevant_update (se presente)
   - stato chain
2) Il planner deve calcolare finestre richieste con classi durata:
   - intraday, swing, position, unknown
3) Merge intervalli per simbolo con soglia configurabile (intervalli sovrapposti/adiacenti/vicini).
4) Output planner deterministico e serializzabile (JSON-safe).

Vincoli architetturali:
- Non usare framework esterni di backtesting.
- Tipi forti + dataclass/pydantic dove già in uso nel progetto.
- Nessun refactor fuori scope.

Deliverable richiesti:
- Nuovo modulo scanner (es: src/signal_chain_lab/market/planning/demand_scanner.py)
- Nuovo modulo planner (es: src/signal_chain_lab/market/planning/coverage_planner.py)
- Config buffer e merge threshold (in config esistente o nuovo file dedicato)
- Test unit per scanner/planner con casi:
  - chain completa
  - chain incompleta
  - merge multiplo con intervalli adiacenti

Accettazione:
- I test nuovi passano.
- Nessuna regressione sui test esistenti in scope.
- Aggiornare checklist: spuntare IE.1/IE.2/IE.3 se completati.

Output finale richiesto:
- elenco file toccati
- comandi test eseguiti
- eventuali limiti residui
```

---

## Prompt 2 — Manifest + gap detection + validazione (IE.4, IE.5, IE.7)

```text
Sei un agente di sviluppo Python sul repository /workspace/back_testing.

Obiettivo sessione:
Implementare manifest locale market data e motore gap detection con validazione minima.

Task in scope:
- IE.4 coverage_index + download_log + validation_log
- IE.5 gap detection (required - covered)
- IE.7 validazione post-download

Requisiti minimi:
1) Persistenza in data/market/manifests/:
   - coverage_index.json
   - download_log.json
   - validation_log.json
2) coverage_index deve tracciare almeno:
   - exchange, market_type, timeframe, symbol
   - intervalli coperti consolidati
   - stato validazione
   - ultimo aggiornamento
3) Gap detection per simbolo/timeframe: restituisce intervalli mancanti ordinati.
4) Validazione minima batch:
   - ordinamento timestamp
   - deduplica
   - schema atteso
   - copertura range richiesto

Vincoli:
- Implementazione idempotente dove possibile.
- Logging esplicito errori/warning.
- Non cambiare API del simulatore in questa sessione.

Deliverable:
- Moduli manifest/gap/validation
- Test unit + integration leggeri su dati fixture
- README breve o docstring con formato JSON manifest

Accettazione:
- gap detection corretta su casi con copertura parziale.
- validazione segnala errori coerenti su dataset volutamente sporco.
- checklist aggiornata su IE.4/IE.5/IE.7.
```

---

## Prompt 3 — Sync Bybit incrementale last/mark (IE.6)

```text
Sei un agente di sviluppo Python sul repository /workspace/back_testing.

Obiettivo sessione:
Implementare sync incrementale Bybit futures linear con storage separato last/mark.

Task in scope:
- IE.6 sync incrementale Bybit (.last.parquet / .mark.parquet)

Requisiti:
1) Provider canonico: Bybit.
2) Mercato: futures_linear.
3) Basis supportate: last + mark.
4) Download solo gap mancanti (input dal planner/manifest).
5) Salvataggio path atteso:
   data/market/bybit/futures_linear/<timeframe>/<SYMBOL>/YYYY-MM.<basis>.parquet

Gestione errori:
- rate limit con retry/backoff
- simbolo non disponibile -> log + stato job
- scrittura atomica file (temp + rename) dove possibile

Deliverable:
- modulo downloader bybit
- integrazione con manifest update
- test (mock API) su:
  - primo sync completo
  - secondo sync senza nuovi gap
  - sync con gap parziale

Accettazione:
- no duplicati su rerun
- manifest aggiornato coerentemente
- checklist IE.6 aggiornata
```

---

## Prompt 4 — Integrazione runner/GUI + CLI operative (IE.8, IE.9, IE.10, IE.11)

```text
Sei un agente di sviluppo Python sul repository /workspace/back_testing.

Obiettivo sessione:
Integrare la pipeline market data nel flusso scenario e nella GUI, aggiungendo CLI operative.

Task in scope:
- IE.8 integrare provider in scripts/run_scenario.py
- IE.9 propagare price_basis (last|mark)
- IE.10 integrare UI block_backtest per basis/timeframe
- IE.11 creare CLI: plan-market-data, sync-market-data, validate-market-data, report-market-coverage

Requisiti:
1) Rimuovere placeholder attuale `_ = Path(args.market_dir)` in run_scenario.py.
2) run_scenario deve istanziare provider reale da market-dir + config basis/timeframe.
3) Aggiungere flag CLI espliciti (esempio):
   - --exchange bybit
   - --market-type futures_linear
   - --timeframe 1m
   - --price-basis last|mark
4) GUI deve permettere selezione price basis e passarlo al comando.
5) Nessun fallback silenzioso cross-exchange in modalità ufficiale.

Deliverable:
- update script scenario
- update blocco GUI backtest
- nuovi script CLI market data
- test integrazione in cui PnL non resta sempre zero su dataset coperto

Accettazione:
- scenario usa davvero il provider
- basis visibile negli artifact/log
- checklist IE.8/IE.9/IE.10/IE.11 aggiornata
```

---

## Prompt 5 — E2E e chiusura incremento (IE.12)

```text
Sei un agente di sviluppo Python sul repository /workspace/back_testing.

Obiettivo sessione:
Eseguire test end-to-end e chiudere Incremento E con evidenze.

Task in scope:
- IE.12 test integrazione E2E

Scenario minimo richiesto:
1) plan-market-data su dataset reale/fixture
2) sync-market-data su gap trovati
3) validate-market-data con esito PASS
4) run_scenario con provider attivo + basis dichiarata
5) verifica output: almeno una chain con fill e PnL != 0

Output richiesto:
- tabella evidenze (comando, esito, artifact prodotto)
- path artifact (scenario json/csv/html + manifest)
- aggiornamento checklist con IE.12 spuntato
- note sui limiti residui (se presenti)
```

---

## Prompt master (opzionale) — Implementazione completa Incremento E

```text
Implementa integralmente i task IE.1 → IE.12 di docs/CHECKLIST_SVILUPPO.md seguendo i PRD market data incrementale + mini PRD Bybit.
Lavora per step piccoli e committabili:
1) planner core
2) manifest/gap/validation
3) sync bybit
4) integrazione scenario/gui + CLI
5) test E2E

Ad ogni step:
- esegui test pertinenti
- aggiorna checklist
- evita refactor fuori scope
- documenta file toccati e decisioni

Vincoli chiave:
- provider canonico Bybit
- futures_linear
- basis last+mark
- parquet partizionato
- offline-first
- no fallback silenzioso cross-exchange in run ufficiale
```
