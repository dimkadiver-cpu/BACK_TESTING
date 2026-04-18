# Checklist di Attuazione - Funding Rate

Basato su: `PIANO_IMPLEMENTAZIONE.md`
Data: 2026-04-18

---

## Fase 1 - BybitFundingDownloader + Script CLI

### 1.1 `market/sync/bybit_funding_downloader.py` (NUOVO)

- [x] Creare `src/signal_chain_lab/market/sync/bybit_funding_downloader.py`
- [x] Definire dataclass `FundingDownloadJob(symbol, start_time, end_time)`
- [x] Definire dataclass `FundingDownloadResult(symbol, status, events_downloaded, intervals_written, error_message)`
- [x] Implementare classe `BybitFundingDownloader(market_dir, base_url, max_retries, backoff_base)`
- [x] Implementare `download(jobs: list[FundingDownloadJob]) -> list[FundingDownloadResult]`
- [x] Implementare paginazione backward su `/v5/market/funding/history` (limit=200 per request)
- [x] Implementare atomic write: scrittura su `.tmp`, poi `os.replace()`
- [x] Merge con dati esistenti nella partizione mensile prima dell'atomic write
- [x] Aggiornare `ManifestStore` con `timeframe="funding"` dopo ogni partizione scritta
- [x] Appendere evento a `download_log.json` con `event_id` univoco
- [x] Gestire rate limit HTTP 429: exponential back-off fino a `max_retries`
- [x] Gestire simbolo non disponibile: `status="skipped"`, log warning
- [x] Gestire errori generici post-retry: `status="error"`, log error

Schema parquet:
- [x] Colonna `ts_utc`: `datetime64[ns, UTC]`
- [x] Colonna `symbol`: `str`
- [x] Colonna `funding_rate`: `float64`
- [x] Colonna `source`: `str` (sempre "bybit")
- [x] Colonna `schema_version`: `int` (sempre 1)

Test:
- [x] Test unitario: download di fixture HTTP -> parquet corretto prodotto
- [x] Test unitario: partizione mensile esistente viene mergiata, non sovrascritta
- [x] Test unitario: simbolo inesistente -> `status="skipped"`, nessun parquet scritto
- [x] Test unitario: risposta 429 -> retry con back-off, poi successo

### 1.2 `scripts/sync_funding_rates.py` (NUOVO)

- [x] Creare `scripts/sync_funding_rates.py`
- [x] Argomenti: `--market-dir`, `--plan-file`, `--symbols` (opzionale override), `--dry-run`
- [x] Leggere simboli e intervalli dal piano JSON prodotto da `plan_market_data.py`
- [x] Costruire lista `FundingDownloadJob` dagli intervalli richiesti
- [x] Emettere `PHASE=funding_sync` all'avvio
- [x] Emettere `PROGRESS=N` e `STEP=X/Y` per ogni job completato
- [x] Emettere `SUMMARY=ok:N skipped:N error:N events:N` al termine
- [x] `--dry-run`: stampa job e termina senza download
- [x] Exit code 0 se tutti ok/skipped, exit code 1 se almeno un errore

---

## Fase 2 - BybitFundingProvider

### 2.1 `market/providers/bybit_funding_provider.py` (NUOVO)

- [x] Creare `src/signal_chain_lab/market/providers/bybit_funding_provider.py`
- [x] Implementare classe `BybitFundingProvider` che soddisfa il protocol `FundingRateProvider`
- [x] Costruttore: `__init__(self, market_dir: Path, symbol: str)`
- [x] Cache LRU per mese: ogni partizione mensile viene caricata una volta sola
- [x] Implementare `get_funding_rate(symbol, ts) -> float | None`
  - [x] Cerca l'evento con `ts_utc <= ts` piu vicino al timestamp richiesto
  - [x] Ritorna `None` se nessun evento e disponibile
- [x] Implementare `get_funding_events(symbol, start, end) -> list[FundingEvent]`
  - [x] Carica tutti i mesi nell'intervallo `[start, end]`
  - [x] Filtra eventi con `start <= ts_utc <= end`
  - [x] Ordina per `ts_utc` ascendente
  - [x] Ritorna lista vuota se nessun file disponibile (non errore)
- [x] Gestire parquet corrotto: log warning, ritorna lista vuota

Test:
- [x] Test: `get_funding_events` ritorna eventi in ordine cronologico
- [x] Test: `get_funding_events` filtra correttamente per intervallo
- [x] Test: mese mancante -> lista vuota, nessuna eccezione
- [x] Test: stesso provider interrogato due volte stesso mese -> una sola lettura parquet (cache hit)
- [x] Test: `get_funding_rate` ritorna l'evento immediatamente precedente al timestamp

---

## Fase 3 - Wiring simulatore

### 3.1 `domain/enums.py`

- [x] Aggiungere `FUNDING_APPLIED = "funding_applied"` all'enum `EventType`

### 3.2 `engine/simulator.py`

- [x] Aggiungere import `FundingRateProvider` da `market.data_models`
- [x] Aggiungere parametro `funding_provider: FundingRateProvider | None = None` a `simulate_chain()`
- [x] Propagare `funding_provider` a `_replay_market_segment()` e a `_replay_parent_candle_with_events()`
- [x] Implementare `_apply_funding_events(*, state, funding_provider, policy, candle_start, candle_end, symbol, logs)`
  - [x] Chiamare `funding_provider.get_funding_events(symbol, candle_start, candle_end)`
  - [x] Per ogni evento non gia in `state.applied_funding_event_keys`:
    - [x] Calcolare `amount = state.open_size * candle.close * funding_rate` con segno netto positivo=received
    - [x] Aggiornare `state.funding_paid += amount`
    - [x] Aggiungere `event.funding_ts_utc.isoformat()` a `state.applied_funding_event_keys`
    - [x] Incrementare `state.funding_events_count`
    - [x] Aggiornare `state.funding_watermark_ts = event.funding_ts_utc`
    - [x] Appendere `EventLogEntry` con `event_type=FUNDING_APPLIED`
  - [x] Se `policy.execution.funding_apply_to_pnl == False`: registra log ma non aggiorna `funding_paid`
- [x] Chiamare `_apply_funding_events()` in `_replay_market_segment()` dopo ogni candela se:
  - `funding_provider is not None`
  - `state.open_size > 0`
  - `policy.funding_model == "historical"`
- [x] Chiamare `_apply_funding_events()` in `_replay_parent_candle_with_events()` per ogni child candle (stesso guard)
- [x] Verificare idempotenza: stesso funding_ts mai applicato due volte (via `applied_funding_event_keys`)

Test:
- [x] Test: posizione aperta su eventi funding multipli -> `funding_paid != 0`, `funding_events_count` coerente
- [x] Test: `funding_model = "none"` -> `funding_paid == 0` anche con provider non-null
- [x] Test: stesso evento funding non applicato due volte se la candela viene processata in due passaggi
- [x] Test: `funding_apply_to_pnl = False` -> log registrato, `funding_paid == 0`
- [ ] Test: `pnl_net_raw = pnl_gross_raw - fees + funding_paid` (regression test vs trade_report.py)

---

## Fase 4 - Validazione funding

### 4.1 `market/planning/validation.py`

- [x] Aggiungere classe `FundingBatchValidator`
- [x] Costruttore: `__init__(self, gap_warning_hours: float = 12.0, gap_critical_hours: float = 24.0)`
- [x] Implementare `validate(symbol, parquet_paths, interval) -> ValidationResult`
  - [x] Step 1 - Schema: `ts_utc`, `symbol`, `funding_rate` presenti in ogni riga -> CRITICAL se mancanti
  - [x] Step 2 - Finitudine: `funding_rate` non `NaN`/`Inf` -> CRITICAL
  - [x] Step 3 - Ordinamento: `ts_utc` monotono crescente -> CRITICAL
  - [x] Step 4 - Duplicati: stesso `ts_utc` per lo stesso simbolo -> WARNING
  - [x] Step 5 - Gap inter-evento > `gap_warning_hours` -> WARNING
  - [x] Step 6 - Gap inter-evento > `gap_critical_hours` -> CRITICAL
  - [x] Step 7 - Funding rate out-of-range: `abs(rate) > 0.05` -> WARNING
- [x] Riutilizzare `IssueSeverity`, `ValidationIssue`, `ValidationResult` esistenti

Test:
- [x] Test: eventi in ordine con gap di 8h -> nessuna issue
- [x] Test: gap di 16h -> WARNING
- [x] Test: gap di 30h -> CRITICAL
- [x] Test: duplicato stesso timestamp -> WARNING
- [x] Test: `funding_rate = NaN` -> CRITICAL
- [x] Test: `funding_rate = 0.1` (10%) -> WARNING range anomalo

### 4.2 `scripts/validate_funding_rates.py` (NUOVO)

- [x] Creare `scripts/validate_funding_rates.py`
- [x] Argomenti: `--market-dir`, `--plan-file`, `--strict`, `--output PATH`
- [x] Emettere `PHASE=validate_funding`, `PROGRESS=N`, `STEP=X/Y`, `SUMMARY=pass:N fail:N warnings:N`
- [x] Con `--strict`: exit code 1 anche su WARNING
- [x] Senza `--strict`: exit code 1 solo su CRITICAL
- [x] Output JSON opzionale con lista issue per simbolo

---

## Fase 5 - Propagazione in runner

### 5.1 `policy_report/runner.py`

- [x] Importare `BybitFundingProvider` da `market.providers.bybit_funding_provider`
- [x] Aggiungere parametro `market_dir: Path | None = None` alla funzione runner principale
- [x] Implementare `_build_funding_provider(policy, market_dir, symbol) -> FundingRateProvider | None`
  - [x] Se `policy.funding_model == "none"`: ritorna `None`
  - [ ] Se `policy.funding_model == "historical"`:
    - [ ] Se `market_dir is None`: log warning "market_dir non disponibile, funding disabilitato", ritorna `None`
    - [x] Se path funding non esiste per il simbolo: log warning, ritorna `None`
    - [x] Altrimenti: ritorna `BybitFundingProvider(market_dir, symbol)`
- [x] Passare `funding_provider` a `simulate_chain()` per ogni chain

Nota implementativa:
- [x] La propagazione `market_dir -> funding_provider` e stata estesa anche a `policy_report/comparison_runner.py` e agli script `run_policy_report.py` / `run_comparison_report.py` per mantenere funding storico attivo anche nei report multi-policy.

Test:
- [x] Test: `funding_model="none"` -> `funding_provider=None` passato al simulatore
- [x] Test: `funding_model="historical"` con parquet presenti -> provider costruito correttamente
- [x] Test: `funding_model="historical"` con parquet assenti -> log warning, `funding_provider=None`

---

## Fase 6 - UI unlock

### 6.1 `ui/state.py`

- [x] Aggiungere `funding_rate: bool = False` a `MarketDataTypeState`
- [x] Verificare che `funding_rate` sia `False` di default (opt-in esplicito)

### 6.2 `ui/blocks/market_data_panel.py`

- [x] Spostare "Funding rate" dal blocco `roadmap_data_type_labels()` al blocco toggle supportati
- [x] Aggiungere `ui.checkbox("Funding rate", value=state.market.data_types.funding_rate)` nel Setup
- [x] Binding checkbox -> `state.market.data_types.funding_rate`
- [x] Aggiungere helper text: "Richiede sync_funding_rates.py prima del backtest"
- [x] Aggiornare `_sync_state_from_ui()` per includere `funding_rate`
- [x] Verificare che il toggle sia visibile nel gruppo "Tipo dati" dopo OHLCV mark

### 6.3 `ui/blocks/market_data_support.py`

- [x] Aggiornare `supported_data_type_labels()`:
  ```python
  if selected.funding_rate:
      labels.append("Funding rate")
  ```
- [x] Aggiornare `roadmap_data_type_labels()`: rimuovere "Funding rate" dalla lista

Test:
- [x] Test: `supported_data_type_labels` con `funding_rate=True` include "Funding rate"
- [x] Test: `roadmap_data_type_labels` non contiene piu "Funding rate"
- [x] Test: `format_data_types_summary` mostra "Funding rate" quando attivo

---

## Verifica end-to-end

- [ ] Scaricare funding rate reale per BTCUSDT su un intervallo noto
- [ ] Validare il file scaricato con `validate_funding_rates.py` -> PASS
- [ ] Eseguire backtest con policy `funding_model="historical"` su una chain lunga > 8h
- [ ] Verificare `funding_total_raw_net != 0` nel trade result
- [ ] Verificare `funding_events_count >= 1` nello stato finale
- [ ] Eseguire backtest con policy `funding_model="none"` -> `funding_total_raw_net == 0`
- [ ] Verificare che `pnl_net_raw = pnl_gross_raw - fees_total_raw + funding_total_raw_net`
- [ ] Report HTML mostra correttamente la sezione cost breakdown con funding

---

## Criteri di accettazione finali

- [ ] Download incrementale: seconda esecuzione non ri-scarica dati gia presenti
- [ ] Provider idempotente: stesso evento funding mai applicato due volte in una simulazione
- [ ] `funding_model="none"` e backward-compatible: nessun cambiamento di output su backtest esistenti
- [x] Toggle UI "Funding rate" non altera CLI o backend se rimane disattivato
- [ ] La validazione rileva gap > 24h come CRITICAL e duplicati come WARNING
