# Piano di Implementazione — Funding Rate

Documento di implementazione per il supporto completo al Funding Rate:
download storico, provider runtime, applicazione nel simulatore, validazione, UI.

*Codebase analizzata: `C:/Back_Testing/src/signal_chain_lab/`*
*Data: 2026-04-18*

---

## Contesto e motivazione

Il Funding Rate è un costo periodico (ogni ~8h) pagato/ricevuto da chi detiene
posizioni aperte su contratti perpetui. Ignorarlo produce PnL lordo anziché netto,
con bias sistematico sulle posizioni lunghe tenute più di un ciclo di funding.

**Senza funding:** `pnl_net_raw = pnl_gross_raw - fees`
**Con funding:** `pnl_net_raw = pnl_gross_raw - fees + funding_net`

---

## Stato attuale — già implementato

| Componente | File | Stato |
|---|---|---|
| `FundingEvent` model | `market/data_models.py:48` | ✅ |
| `FundingRateProvider` protocol | `market/data_models.py:56` | ✅ |
| `funding_model: str = "none"` in policy | `policies/base.py:326` | ✅ |
| `funding_apply_to_pnl: bool = True` in policy | `policies/base.py:327` | ✅ |
| Validator `funding_model` (none/historical) | `policies/base.py:358` | ✅ |
| `funding_paid`, `funding_events_count` in TradeState | `domain/trade_state.py:60` | ✅ |
| `funding_watermark_ts`, `applied_funding_event_keys` | `domain/trade_state.py:62` | ✅ |
| `funding_total_raw_net` in TradeResult | `domain/results.py:61` | ✅ |
| `pnl_net_raw = pnl_gross_raw - fees + funding` | `reports/trade_report.py:92` | ✅ |
| Sezione cost breakdown nel report HTML | `policy_report/html_writer.py:495` | ✅ |

**Non serve toccare nulla di quanto sopra.**

---

## Cosa manca — gap da colmare

| Componente | File da creare/modificare | Priorità |
|---|---|---|
| `BybitFundingDownloader` | `market/sync/bybit_funding_downloader.py` (CREA) | Alta |
| Script CLI download | `scripts/sync_funding_rates.py` (CREA) | Alta |
| `BybitFundingProvider` | `market/providers/bybit_funding_provider.py` (CREA) | Alta |
| Wiring simulatore | `engine/simulator.py` (MODIFICA) | Alta |
| Propagazione in runner | `policy_report/runner.py` (MODIFICA) | Alta |
| Validazione funding | `market/planning/validation.py` (MODIFICA) | Media |
| Script validate funding | `scripts/validate_funding_rates.py` (CREA) | Media |
| UI — sblocco toggle | `ui/state.py` + `ui/blocks/market_data_panel.py` (MODIFICA) | Media |
| UI — helper support | `ui/blocks/market_data_support.py` (MODIFICA) | Bassa |

---

## Dipendenze tra fasi

```
Fase 1 — Download
    └── Fase 2 — Provider    ← legge i parquet prodotti dal downloader
            └── Fase 3 — Simulatore  ← usa il provider
                    └── Fase 5 — Runner  ← passa il provider al simulatore

Fase 4 — Validazione  ← indipendente, può partire dopo Fase 1
Fase 6 — UI           ← dipende da Fase 1 (download funzionante) per essere utile
```

---

## Fase 1 — BybitFundingDownloader

**Obiettivo:** Scaricare e persistere il funding rate storico da Bybit.

### Endpoint Bybit

```
GET /v5/market/funding/history
Params: category=linear, symbol=BTCUSDT, startTime=<ms>, endTime=<ms>, limit=200
Auth: nessuna (endpoint pubblico)
Response fields: symbol, fundingRate, fundingRateTimestamp
```

Ogni risposta contiene al massimo 200 eventi. Il loop deve paginarsi indietro
usando `endTime` = timestamp minore dell'ultimo evento ricevuto, fino a coprire
l'intervallo richiesto.

### Storage layout

```
<market_dir>/bybit/futures_linear/funding/<SYMBOL>/YYYY-MM.funding.parquet
```

Schema parquet (colonne obbligatorie):

| Colonna | Tipo | Note |
|---|---|---|
| `ts_utc` | `datetime64[ns, UTC]` | Timestamp evento funding |
| `symbol` | `str` | Es. "BTCUSDT" |
| `funding_rate` | `float64` | Valore raw Bybit (es. 0.0001) |
| `source` | `str` | Sempre "bybit" |
| `schema_version` | `int` | Sempre 1 |

### File da creare

#### `src/signal_chain_lab/market/sync/bybit_funding_downloader.py`

Struttura analoga a `bybit_downloader.py`, con queste differenze:

- Classe: `BybitFundingDownloader`
- Nessun parametro `basis` (il funding non ha varianti last/mark)
- Paginazione backward (dal più recente verso il più vecchio) fino a `start_time`
- Atomic write: `.tmp` → `os.replace()` come nel downloader OHLCV
- ManifestStore aggiornato con `timeframe="funding"` come chiave di coverage
- Strutture dati:

```python
@dataclass
class FundingDownloadJob:
    symbol: str
    start_time: datetime
    end_time: datetime

@dataclass
class FundingDownloadResult:
    symbol: str
    status: Literal["ok", "skipped", "error"]
    events_downloaded: int
    intervals_written: list[Interval]
    error_message: str | None = None
```

- Rate limiting: stesso pattern di `bybit_downloader.py` (exponential back-off su 429)
- Se il simbolo non esiste sull'exchange: `status="skipped"`, log warning

### File da creare

#### `scripts/sync_funding_rates.py`

Script CLI che accetta:

```
--market-dir     PATH       Cartella radice market data
--plan-file      PATH       Piano JSON prodotto da plan_market_data.py
--symbols        LIST       Override simboli (opzionale)
--dry-run                   Stampa job senza eseguire
```

Emette protocollo stdout standardizzato:

```
PHASE=funding_sync
PROGRESS=N
STEP=X/Y
SUMMARY=ok:N skipped:N error:N events:N
```

---

## Fase 2 — BybitFundingProvider

**Obiettivo:** Implementare `FundingRateProvider` leggendo i parquet locali.

### File da creare

#### `src/signal_chain_lab/market/providers/bybit_funding_provider.py`

```python
class BybitFundingProvider:
    """Implements FundingRateProvider reading local .funding.parquet files."""

    def __init__(self, market_dir: Path, symbol: str) -> None: ...

    def get_funding_rate(self, symbol: str, ts: datetime) -> float | None:
        """Return the funding rate for the event at or immediately before ts."""

    def get_funding_events(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[FundingEvent]:
        """Return all funding events in [start, end] sorted by ts_utc."""
```

Logica interna:
- Carica in memoria i parquet dei mesi coperti dall'intervallo richiesto
- Cache LRU per mese per evitare riletture ripetute durante la simulazione
- `get_funding_events()` usa ricerca binaria su `ts_utc` per efficienza
- Se nessun file esiste per un mese: ritorna lista vuota (non errore)
- Se il parquet è corrotto: log warning, ritorna lista vuota

### Null provider

Quando `funding_model == "none"` il simulatore non deve creare alcun provider.
Introdurre `NullFundingProvider` che restituisce sempre `[]` e `None`,
oppure usare `None` direttamente con guard nel simulatore.

---

## Fase 3 — Wiring simulatore

**Obiettivo:** Applicare il funding agli stati aperti durante il replay di mercato.

### File da modificare

#### `engine/simulator.py`

**Modifica 1 — firma `simulate_chain()`:**

```python
def simulate_chain(
    chain: CanonicalChain,
    policy: PolicyConfig,
    market_provider: MarketDataProvider | None = None,
    funding_provider: FundingRateProvider | None = None,   # NUOVO
) -> tuple[list[EventLogEntry], TradeState]:
```

**Modifica 2 — nuova funzione `_apply_funding_events()`:**

```python
def _apply_funding_events(
    *,
    state: TradeState,
    funding_provider: FundingRateProvider,
    policy: PolicyConfig,
    candle_start: datetime,
    candle_end: datetime,
    symbol: str,
    logs: list[EventLogEntry],
) -> None:
```

Logica:
1. `events = funding_provider.get_funding_events(symbol, candle_start, candle_end)`
2. Per ogni evento con `ts_utc` non già in `state.applied_funding_event_keys`:
   - Calcola `amount = state.open_size * mark_price_at_ts * event.funding_rate`
   - Segno: positivo = received (short in funding positivo), negativo = paid
   - Aggiorna `state.funding_paid += amount`
   - Aggiunge `ts_utc.isoformat()` a `state.applied_funding_event_keys`
   - Incrementa `state.funding_events_count`
   - Aggiorna `state.funding_watermark_ts = ts_utc`
   - Appende `EventLogEntry` con `event_type=FUNDING_APPLIED`
3. Se `policy.funding_apply_to_pnl == False`: non aggiornare `funding_paid` ma registra il log

**Modifica 3 — chiamata in `_replay_market_segment()`:**

Dopo ogni candela processata, se `funding_provider is not None` e `state.open_size > 0`
e `policy.funding_model == "historical"`:

```python
_apply_funding_events(
    state=state,
    funding_provider=funding_provider,
    policy=policy,
    candle_start=candle.ts,
    candle_end=candle.ts + candle_duration,
    symbol=state.symbol,
    logs=logs,
)
```

**Propagazione a `_replay_parent_candle_with_events()`:** stessa logica, funding
applicato per ogni child candle in ordine cronologico.

**EventType da aggiungere in `domain/enums.py`:**

```python
FUNDING_APPLIED = "funding_applied"
```

---

## Fase 4 — Validazione funding

**Obiettivo:** Verificare che i dati scaricati siano completi e corretti.

### Regole di validazione specifiche per funding

| Check | Severity | Condizione |
|---|---|---|
| Schema: campi obbligatori presenti | CRITICAL | `ts_utc`, `symbol`, `funding_rate` assenti |
| `funding_rate` finito (non NaN/Inf) | CRITICAL | `isnan` o `isinf` |
| Timestamp monotono crescente | CRITICAL | evento non ordinato per ts_utc |
| Duplicati per stesso timestamp | WARNING | due eventi con stesso ts_utc per stesso simbolo |
| Gap inter-evento > 12h | WARNING | previsto ~8h, tolleranza fino a 12h |
| Gap inter-evento > 24h | CRITICAL | gap grave, dati mancanti |
| Funding rate fuori range plausibile | WARNING | `abs(rate) > 0.05` (5% per singolo evento è anomalo) |

### File da modificare

#### `market/planning/validation.py`

Aggiungere classe `FundingBatchValidator` separata da `BatchValidator` (che è OHLCV-specific):

```python
class FundingBatchValidator:
    def validate(
        self,
        symbol: str,
        parquet_paths: list[Path],
        interval: Interval,
        expected_period_hours: float = 8.0,
        gap_warning_hours: float = 12.0,
        gap_critical_hours: float = 24.0,
    ) -> ValidationResult: ...
```

### File da creare

#### `scripts/validate_funding_rates.py`

Script CLI:

```
--market-dir     PATH
--plan-file      PATH
--strict                  Fallisce su WARNING
--output         PATH     JSON report (opzionale)
```

Protocollo stdout:

```
PHASE=validate_funding
PROGRESS=N
STEP=X/Y
SUMMARY=pass:N fail:N warnings:N
```

---

## Fase 5 — Propagazione in runner

**Obiettivo:** Il runner costruisce il `BybitFundingProvider` e lo passa al simulatore.

### File da modificare

#### `policy_report/runner.py`

**Attuale:**
```python
event_log, state = simulate_chain(chain, policy=policy, market_provider=market_provider)
```

**Nuovo:**
```python
funding_provider = _build_funding_provider(policy, market_dir, chain.symbol)
event_log, state = simulate_chain(
    chain,
    policy=policy,
    market_provider=market_provider,
    funding_provider=funding_provider,
)
```

Funzione `_build_funding_provider()`:
- Se `policy.funding_model == "none"`: ritorna `None`
- Se `policy.funding_model == "historical"`:
  - Se `market_dir` è `None` o il path funding non esiste: log warning, ritorna `None`
  - Altrimenti: `BybitFundingProvider(market_dir, symbol)`

Il `market_dir` deve essere passabile al runner (già disponibile da `MarketState`).

---

## Fase 6 — UI unlock

**Obiettivo:** Spostare "Funding rate" da voce roadmap a voce supportata con toggle.

### File da modificare

#### `ui/state.py`

```python
@dataclass(slots=True)
class MarketDataTypeState:
    ohlcv_last: bool = True
    ohlcv_mark: bool = False
    funding_rate: bool = False    # NUOVO — default off (opt-in)
```

#### `ui/blocks/market_data_panel.py`

- Spostare "Funding rate" dal blocco roadmap al blocco toggle supportati
- Aggiungere checkbox "Funding rate" abilitato, default OFF
- Binding su `state.market.data_types.funding_rate`
- Aggiungere nota: "Richiede sync_funding_rates prima del backtest"
- Lasciare gli altri 5 tipi (open interest, liquidations, ecc.) nella sezione roadmap

#### `ui/blocks/market_data_support.py`

- Aggiornare `supported_data_type_labels()` per includere "Funding rate" se attivo:

```python
def supported_data_type_labels(selected: MarketDataTypeState) -> list[str]:
    labels: list[str] = []
    if selected.ohlcv_last:
        labels.append("OHLCV last")
    if selected.ohlcv_mark:
        labels.append("OHLCV mark")
    if selected.funding_rate:
        labels.append("Funding rate")
    return labels

def roadmap_data_type_labels() -> list[str]:
    return [
        "Open interest",
        "Liquidations",
        "Bid/ask spread",
        "Order book",
    ]
```

---

## Protocollo stdout per `sync_funding_rates.py`

Coerente con gli altri script Market:

```
PHASE=funding_sync
PROGRESS=37
STEP=3/8
SUMMARY=ok:5 skipped:1 error:0 events:1240
```

---

## Riepilogo file toccati

| File | Intervento | Fase |
|---|---|---|
| `market/sync/bybit_funding_downloader.py` | CREA | 1 |
| `scripts/sync_funding_rates.py` | CREA | 1 |
| `market/providers/bybit_funding_provider.py` | CREA | 2 |
| `engine/simulator.py` | MODIFICA — firma + `_apply_funding_events` | 3 |
| `domain/enums.py` | MODIFICA — aggiunge `FUNDING_APPLIED` | 3 |
| `policy_report/runner.py` | MODIFICA — propaga funding_provider | 5 |
| `market/planning/validation.py` | MODIFICA — `FundingBatchValidator` | 4 |
| `scripts/validate_funding_rates.py` | CREA | 4 |
| `ui/state.py` | MODIFICA — `funding_rate: bool = False` | 6 |
| `ui/blocks/market_data_panel.py` | MODIFICA — toggle funding abilitato | 6 |
| `ui/blocks/market_data_support.py` | MODIFICA — aggiorna label lists | 6 |

---

## Criteri di accettazione

- Con `funding_model = "historical"` e dati scaricati: `funding_total_raw_net != 0`
  per posizioni tenute oltre un ciclo di funding.
- Con `funding_model = "none"`: `funding_total_raw_net == 0` (comportamento attuale invariato).
- Il download è incrementale: eseguire due volte non scarica dati già presenti.
- La validazione rileva gap > 24h come CRITICAL e duplicati come WARNING.
- Il simulatore non applica mai lo stesso evento funding due volte
  (idempotenza via `applied_funding_event_keys`).
- Il toggle UI "Funding rate" non modifica CLI o backend se non viene attivato.

---

## Ordine di sviluppo consigliato

```
Step 1  BybitFundingDownloader + sync_funding_rates.py   ← dati scaricabili
Step 2  BybitFundingProvider                              ← dati leggibili
Step 3  simulator.py wiring                               ← funding applicato
Step 4  runner.py propagazione                            ← end-to-end funzionante
Step 5  FundingBatchValidator + validate_funding_rates.py ← QA dati
Step 6  UI unlock                                         ← visibile all'utente

Non iniziare Step 2 senza dati parquet reali da testare.
Non iniziare Step 3 senza un provider funzionante su fixture.
```
