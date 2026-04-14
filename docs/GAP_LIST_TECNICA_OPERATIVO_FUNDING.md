# GAP-list tecnica operativo — Funding model

Questa checklist traduce il PRD funding in attività implementative concrete nel codice attuale.

## 1) GAP attuali (stato codice)

- Engine senza `funding_provider` in `simulate_chain(...)`.
- `TradeState` senza campi runtime per tracking funding.
- `trade_report` con funding placeholder a `0.0`.
- `ExecutionPolicy` senza `funding_model` e `funding_apply_to_pnl`.
- Data-preparation layer orientato a OHLCV (`last`/`mark`), non funding history.

## 2) Piano operativo (ordine consigliato)

### Step 1 — Downloader funding
- **Nuovo file:** `src/signal_chain_lab/market/sync/bybit_funding_downloader.py`
- Implementare client Bybit `/v5/market/funding/history` con paginazione + retry/backoff.
- Salvare in:
  - `<market_dir>/bybit/futures_linear/funding/<SYMBOL>/YYYY-MM.funding.parquet`
- Scrittura atomica (`.tmp` + `os.replace`), merge dedup incrementale.
- Logging eventi download e integrazione manifest.

### Step 2 — Protocol + provider funding
- **Modifica:** `src/signal_chain_lab/market/data_models.py`
  - Aggiungere `FundingRateProvider(Protocol)`:
    - `get_funding_rate(symbol, ts)`
    - `get_funding_events(symbol, start, end)`
- **Nuovo file:** `src/signal_chain_lab/market/providers/bybit_funding_provider.py`
  - Lettura parquet funding mensili, cache per simbolo, lookup binario eventi.

### Step 3 — Policy execution
- **Modifica:** `src/signal_chain_lab/policies/base.py` (`ExecutionPolicy`)
  - `funding_model: str = "none"` (`none | historical`)
  - `funding_apply_to_pnl: bool = True`

### Step 4 — Stato trade
- **Modifica:** `src/signal_chain_lab/domain/trade_state.py`
  - `funding_paid: float = 0.0`
  - `funding_events_count: int = 0`

### Step 5 — Simulator (core logic)
- **Modifica:** `src/signal_chain_lab/engine/simulator.py`
  - Propagare `funding_provider: FundingRateProvider | None = None`.
  - Integrare `_apply_funding_events(...)` nel loop candele (pre TP/SL).
  - Aggiornare:
    - `state.funding_paid`
    - `state.funding_events_count`
    - `state.realized_pnl` se `funding_apply_to_pnl=True`

### Step 6 — Wiring script/runner
- **Modifica:**
  - `scripts/run_scenario.py`
  - `scripts/run_policy_report.py`
  - `scripts/run_comparison_report.py`
- Istanziare e passare provider funding quando policy richiede `historical`.

### Step 7 — Reporting
- **Modifica:** `src/signal_chain_lab/reports/trade_report.py`
  - Sostituire il placeholder funding con valore reale da stato trade.
  - Mantenere formula netta:
    - `pnl_net_raw = pnl_gross_raw - fees_total_raw + funding_total_raw_net`
- Verificare aggregazioni in `policy_report/runner.py`.

### Step 8 — CLI dedicata
- **Nuovo file:** `scripts/download_funding_rates.py`
- Parametri minimi:
  - `--symbols`
  - `--start`
  - `--end`
  - `--market-dir`

### Step 9 — Test
- **Nuovi test unit/integration:**
  - downloader funding
  - provider funding
  - simulator funding on/off
  - report trade/policy con funding

## 3) Definition of Done

- Funding storico scaricabile e persistito in parquet.
- Policy attiva/disattiva funding correttamente.
- Simulator applica funding con segno corretto (long/short, rate +/-).
- Nessuna doppia applicazione evento funding in replay.
- Trade report espone funding reale.
- Policy report aggrega funding correttamente.
- Test principali verdi.

## 4) Rischi principali

1. Segno economico funding non coerente tra long/short.
2. Doppio conteggio su intrabar/replay.
3. Dati funding mancanti: fallback robusto senza bloccare simulazione.
4. Errori timezone/allineamento timestamp (usare UTC end-to-end).

## 5) Incremento operativo (round successivo)

Per accelerare l’implementazione, il piano viene incrementato con task più granulari,
criteri di accettazione e metriche minime di controllo.

### 5.1 Backlog esecutivo (P0 → P2)

#### P0 — Bloccanti funzionali
- [ ] **Contratto dati funding canonico**
  - Definire schema parquet minimo: `symbol`, `funding_ts_utc`, `funding_rate`, `source`, `ingested_at`.
  - Versionare schema (`schema_version`) per migrazioni future.
- [ ] **Applicazione funding in simulator idempotente**
  - Introdurre chiave evento univoca (`symbol + funding_ts_utc`) per prevenire doppio conteggio.
  - Persistenza in `TradeState` degli ultimi eventi già applicati (o watermark temporale).
- [ ] **Segno economico formalizzato**
  - Tabelle di verità long/short × rate +/- con expected PnL.
  - Assertion runtime (debug) su casi impossibili.

#### P1 — Robustezza operativa
- [ ] **Downloader production-ready**
  - Retry esponenziale con jitter.
  - Circuit breaker locale su errori ripetuti API.
  - Resume download da ultimo timestamp disponibile.
- [ ] **Gap filling e qualità dato**
  - Controllo buchi temporali per finestra richiesta.
  - Report di coverage per simbolo (`events_found / events_expected`).
- [ ] **Wiring completo runner**
  - Fallback esplicito a `funding_model=none` se provider non disponibile.
  - Warning strutturato nel report scenario.

#### P2 — Osservabilità e UX tecnica
- [ ] **Metriche e logging**
  - Contatori: `funding_events_loaded`, `funding_events_applied`, `funding_events_skipped`.
  - Timing: latenza lookup provider e costo download.
- [ ] **CLI evoluta**
  - Flag `--resume`, `--force-refresh`, `--dry-run`.
  - Output riepilogo per simbolo e mese.
- [ ] **Documentazione utente/dev**
  - Esempi end-to-end (download → backtest → report).
  - Troubleshooting (dataset incompleto, timezone, mismatch simboli).

### 5.2 Criteri di accettazione tecnici (aggiuntivi)

- **Correttezza finanziaria:** differenza tra PnL atteso e PnL simulato < `1e-9` sui test deterministici.
- **Idempotenza:** due replay consecutivi sugli stessi dati producono funding totale identico.
- **Copertura test:** almeno un test per:
  - funding positivo su posizione long e short;
  - funding negativo su posizione long e short;
  - assenza eventi funding nell’intervallo trade.
- **Degrado controllato:** in assenza dati funding, simulazione completata con warning e senza crash.

### 5.3 Piano test incrementale (pratico)

1. **Unit test provider** con fixture parquet sintetiche multi-mese.
2. **Unit test simulator** con timeline minima (entry, 2 funding event, exit).
3. **Integration test runner** con `funding_model=historical` e confronto snapshot report.
4. **Regression test** su scenario reale già validato senza funding (`funding_model=none` invariato).

### 5.4 Exit criteria del round

Il round è chiuso quando:
- tutti i task P0 sono completati;
- almeno il 70% dei task P1 è completato;
- la pipeline CI esegue i nuovi test funding senza flaky failure;
- i report espongono in modo trasparente il contributo funding (trade e policy).
