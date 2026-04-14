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
