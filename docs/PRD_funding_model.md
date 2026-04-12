# PRD — funding_model

Specifica completa per l'implementazione del modello di funding rate nel simulatore Signal Chain Lab.

---

## Obiettivo

Aggiungere la capacità di detrarre il costo di funding dai trade su futures perpetui durante il backtest.
Il funding influenza il PnL netto reale ogni 8 ore: ignorarlo sovrastima i profitti delle posizioni long
in mercati bullish e delle short in mercati bearish.

---

## Contesto tecnico

### Cos'è il funding rate

I futures perpetui (Bybit linear: BTCUSDT, ETHUSDT, ecc.) non hanno scadenza.
Per mantenere il prezzo del perp allineato allo spot, ogni **8 ore** (00:00, 08:00, 16:00 UTC)
avviene un trasferimento tra long e short:

```
funding_payment = notional * funding_rate
notional        = avg_entry_price * open_size
```

- `funding_rate > 0` → longs pagano shorts (perp sopra spot, mercato bullish)
- `funding_rate < 0` → shorts pagano longs (perp sotto spot, mercato bearish)
- Il pagamento è **per lato**: chi detiene la posizione al momento del funding timestamp la subisce

### Impatto pratico

| Durata trade | Funding events | Impatto tipico |
|---|---|---|
| < 8h | 0–1 | trascurabile |
| 1 giorno | ~3 | 0.01–0.1% del notional |
| 1 settimana | ~21 | rilevante in periodi di funding elevato |
| > 2 settimane | 42+ | significativo, errore di simulazione senza questo modello |

In bull run estremi il funding può toccare 0.3% ogni 8 ore (~1% al giorno sul notional).

### API Bybit disponibile

```
GET https://api.bybit.com/v5/market/funding/history
params: category=linear, symbol=BTCUSDT, limit=200, startTime, endTime
output: [{ "fundingRate": "0.00003126", "fundingRateTimestamp": "1775952000000" }]
```

- Un record ogni 8 ore
- Storico disponibile per anni
- Paginated: `limit=200` = ~66 giorni per richiesta
- Nessun costo, endpoint pubblico senza autenticazione

---

## Switch YAML

```yaml
execution:
  # Modello funding rate per futures perpetui.
  # none       → nessun funding applicato (default, comportamento V1)
  # historical → usa i dati storici scaricati da Bybit per ogni funding timestamp
  funding_model: none

  # Usato solo con funding_model: historical.
  # true  → la fee di funding è inclusa in fees_paid e sottratta da realized_pnl
  # false → funding calcolato e loggato ma non dedotto dal PnL (dry-run/debug)
  funding_apply_to_pnl: true
```

---

## Specifiche per componente

### 1. Download — `BybitFundingDownloader`

**File nuovo:** `src/signal_chain_lab/market/sync/bybit_funding_downloader.py`

Modellato su `bybit_downloader.py` ma con endpoint e struttura dati diversi.

**Storage layout:**
```
<market_dir>/bybit/futures_linear/funding/<SYMBOL>/YYYY-MM.funding.parquet
```

**Schema parquet:**
| Colonna | Tipo | Note |
|---|---|---|
| `timestamp` | `datetime64[ns, UTC]` | funding timestamp (inizio intervallo) |
| `symbol` | `str` | es. "BTCUSDT" |
| `funding_rate` | `float64` | valore da API, già normalizzato (0.0001 = 0.01%) |

**Comportamento:**
- Download paginato: 200 record per richiesta (≈ 66 giorni)
- Scrittura atomica con `.tmp` → `os.replace()` (stesso pattern del downloader OHLCV)
- Merge incrementale: se il file mensile esiste, carica + deduplica + salva
- Aggiorna `ManifestStore` dopo ogni partizione scritta
- Gestione rate limit con exponential back-off (riusa `BybitRateLimitError`)
- Se il simbolo non esiste come linear future: log warning, status "skipped"

**Interfaccia pubblica:**
```python
class BybitFundingDownloader:
    def download(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> DownloadResult: ...
```

---

### 2. Provider — `FundingRateProvider`

**File nuovo:** `src/signal_chain_lab/market/providers/bybit_funding_provider.py`

**Protocol da aggiungere in `data_models.py`:**
```python
class FundingRateProvider(Protocol):
    def get_funding_rate(self, symbol: str, ts: datetime) -> float | None:
        """Restituisce il funding rate applicato al timestamp esatto, None se non disponibile."""
        ...

    def get_funding_events(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, float]]:
        """Restituisce tutti i (timestamp, funding_rate) nell'intervallo [start, end]."""
        ...
```

**Implementazione `BybitFundingProvider`:**
- Carica parquet mensili da `<market_dir>/bybit/futures_linear/funding/<SYMBOL>/`
- Cache in memoria per simbolo: `dict[str, list[tuple[datetime, float]]]`
- `get_funding_events`: lookup binario su lista ordinata per timestamp
- Se i dati mancano per un simbolo: log warning + ritorna lista vuota (simulazione prosegue senza funding)

---

### 3. Policy config — `ExecutionPolicy`

**File:** `src/signal_chain_lab/policies/base.py`

Aggiungere a `ExecutionPolicy`:
```python
funding_model: str = "none"           # "none" | "historical"
funding_apply_to_pnl: bool = True     # se False: calcola ma non deduce
```

---

### 4. TradeState — tracking funding

**File:** `src/signal_chain_lab/domain/trade_state.py`

Aggiungere a `TradeState`:
```python
funding_paid: float = 0.0    # somma algebrica dei pagamenti funding (positivo = pagato, negativo = ricevuto)
funding_events_count: int = 0
```

Nota: `fees_paid` rimane separato (fee di esecuzione). Il funding è un costo di mantenimento,
semanticamente diverso anche se entrambi riducono il PnL netto.

---

### 5. TradeResult — output report

**File:** `src/signal_chain_lab/domain/results.py`

Aggiungere a `TradeResult`:
```python
funding_paid: float = 0.0
funding_events_count: int = 0
```

Il `realized_pnl` nel report deve già includere il funding se `funding_apply_to_pnl: true`
(perché viene dedotto da `state.realized_pnl` durante la simulazione).

---

### 6. Simulator — applicazione funding nel loop candele

**File:** `src/signal_chain_lab/engine/simulator.py`

#### Punto di iniezione

`_replay_market_segment` riceve già `policy` e `market_provider`.
Serve un parametro aggiuntivo opzionale:

```python
def _replay_market_segment(
    *,
    ...
    funding_provider: FundingRateProvider | None = None,
) -> datetime | None:
```

#### Logica nel loop candele

Dopo `_try_fill_pending_entries` e prima del check TP/SL, per ogni candela:

```python
if (
    funding_provider is not None
    and policy.execution.funding_model == "historical"
    and state.open_size > 0
    and state.avg_entry_price is not None
):
    _apply_funding_events(
        state=state,
        policy=policy,
        funding_provider=funding_provider,
        candle=candle,
        last_funding_applied_ts=last_funding_applied_ts,  # variabile di loop
    )
```

#### Funzione `_apply_funding_events`

```python
def _apply_funding_events(
    state: TradeState,
    policy: PolicyConfig,
    funding_provider: FundingRateProvider,
    candle: Candle,
    last_funding_applied_ts: datetime | None,
) -> datetime | None:
    """Applica tutti i funding events che ricadono nella finestra [last+1, candle.timestamp]."""
    window_start = last_funding_applied_ts or state.first_fill_at or candle.timestamp
    events = funding_provider.get_funding_events(state.symbol, window_start, candle.timestamp)
    for event_ts, rate in events:
        if last_funding_applied_ts is not None and event_ts <= last_funding_applied_ts:
            continue
        notional = (state.avg_entry_price or 0.0) * state.open_size
        direction = 1.0 if state.side.upper() in {"BUY", "LONG"} else -1.0
        # long paga quando rate > 0, short paga quando rate < 0
        payment = notional * rate * direction
        state.funding_paid += payment
        state.funding_events_count += 1
        if policy.execution.funding_apply_to_pnl:
            state.realized_pnl -= payment
        last_funding_applied_ts = event_ts
    return last_funding_applied_ts
```

**Nota su `last_funding_applied_ts`:** variabile di stato locale al loop `_replay_market_segment`,
inizializzata a `None` o a `state.first_fill_at`. Evita di applicare due volte lo stesso evento
se la candela viene rielaborata.

---

### 7. Adattatori — propagazione `funding_provider`

**File:** `src/signal_chain_lab/adapters/chain_adapter.py` e `chain_builder.py`

Gli adattatori costruiscono il contesto di simulazione passando i provider al simulatore.
Aggiungere `funding_provider: FundingRateProvider | None = None` come parametro opzionale
in `simulate_chain()` / `run_scenario()`.

Se `funding_model == "none"` nella policy → passare `None` (nessun overhead).
Se `funding_model == "historical"` → il chiamante deve fornire un `BybitFundingProvider` istanziato.

---

### 8. Script — download funding

**File nuovo:** `scripts/download_funding_rates.py`

```
Usage:
  python scripts/download_funding_rates.py --symbols BTCUSDT ETHUSDT --start 2023-01-01 --end 2024-12-31
```

Pattern uguale a `scripts/run_single_chain.py` per coerenza.

---

## Integrazione con fee_model

Il funding non interferisce con `fee_model`. Sono costi distinti:

| Costo | Quando | Tracking |
|---|---|---|
| `fee_model: fixed_bps` | Su ogni fill (entry + TP/SL close) | `fees_paid` |
| `funding_model: historical` | Ogni 8h durante la vita della posizione | `funding_paid` |

Il `realized_pnl` netto = PnL lordo − fees_paid − funding_paid (se entrambi attivi).

---

## Template YAML aggiornato (sezione execution completa)

```yaml
execution:
  latency_ms: 0
  slippage_model: none
  slippage_bps: 0
  fill_touch_guaranteed: true
  fee_model: none
  fee_bps: 0.0
  funding_model: none          # none | historical
  funding_apply_to_pnl: true   # usato solo con funding_model: historical
  # partial_fill_model: none   # design: docs/DESIGN_partial_fill_model.md
  # spread_model: none
```

---

## Ordine di sviluppo

```
Step 1  BybitFundingDownloader      market/sync/bybit_funding_downloader.py
        → test: download 30gg BTCUSDT, verifica parquet su disco

Step 2  FundingRateProvider protocol + BybitFundingProvider
        → test: get_funding_events con dati noti, verifica lookup e cache

Step 3  ExecutionPolicy + TradeState + TradeResult
        → aggiungere campi, verificare che i test esistenti non rompano

Step 4  Simulator — _apply_funding_events
        → test: trade 7gg con funding_model=historical, verifica funding_paid accumulato

Step 5  Adattatori — propagazione funding_provider

Step 6  Script download_funding_rates.py

Step 7  Aggiornamento YAML template e policy esistenti
```

**Non saltare step. Step 4 richiede Step 2 completo.**

---

## Prompt di implementazione (da usare quando si inizia)

```
Implementa funding_model nel simulatore Signal Chain Lab.
Contesto completo: docs/PRD_funding_model.md

Inizia da Step 1: BybitFundingDownloader.

File di riferimento per lo stile di implementazione:
- src/signal_chain_lab/market/sync/bybit_downloader.py (pattern download + manifest + retry)
- src/signal_chain_lab/market/providers/bybit_parquet_provider.py (pattern provider + cache)

Storage target:
  <market_dir>/bybit/futures_linear/funding/<SYMBOL>/YYYY-MM.funding.parquet
  colonne: timestamp (datetime64[ns,UTC]), symbol (str), funding_rate (float64)

API Bybit:
  GET /v5/market/funding/history
  params: category=linear, symbol, limit=200, startTime (ms), endTime (ms)
  response: result.list → [{ fundingRate, fundingRateTimestamp }]

Dopo aver scritto il downloader, scrivi i test unitari con client mockato
(stesso pattern dei test del downloader OHLCV se esistono).
```
