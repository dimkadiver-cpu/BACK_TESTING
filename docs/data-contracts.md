# Data Contracts — Signal Chain Backtesting Lab
**Versione:** 1.1  
**Aggiornato:** 2026-04-07 (post audit F0)

---

## 1. Source DB → Adapter (chain_builder)

Il chain_builder legge da 4 tabelle del DB sorgente:

| Tabella | Uso |
|---|---|
| `operational_signals` | Righe NEW_SIGNAL e UPDATE con metadati |
| `parse_results` | `parse_result_normalized_json` con entities e intents |
| `raw_messages` | `message_ts`, `telegram_message_id`, `source_chat_id` |
| `signals` | `symbol`, `side` per ogni `attempt_key` |

### Mapping colonne DB → SignalChain

| Campo SignalChain | Colonna DB sorgente | Note |
|---|---|---|
| `chain_id` | `os.trader_id + ":" + os.attempt_key` | Formato: `{trader_id}:{attempt_key}` |
| `trader_id` | `os.trader_id` | — |
| `symbol` | `signals.symbol` | Risolto via attempt_key |
| `side` | `signals.side` | Risolto via attempt_key |
| `open_ts` | `raw_messages.message_ts` del NEW_SIGNAL | Parsed come ISO-8601 UTC |
| `close_ts` | `raw_messages.message_ts` di U_CLOSE_FULL o U_SL_HIT | Derivato da updates |
| `entry_prices` | `parse_result_normalized_json.entities.entries[].price.value` | Lista float |
| `sl_price` | `parse_result_normalized_json.entities.stop_loss.price.value` | Singolo float, 0.0 se assente |
| `tp_prices` | `parse_result_normalized_json.entities.take_profits[].price.value` | Lista float |
| `new_signal` | Oggetto ChainedMessage dal NEW_SIGNAL | Contiene entities, intents |
| `updates` | Lista ChainedMessage dagli UPDATE collegati | Ordinati per message_ts ASC |

### Linking UPDATE → NEW_SIGNAL

Due strategie (in ordine di priorità):
1. `os.resolved_target_ids` (JSON list[int] di op_signal_id) — priorità alta
2. `rm.reply_to_message_id` → lookup in `(source_chat_id, telegram_message_id)` — fallback

UPDATE orfano (nessuna strategia risolve): skippato con warning log.

---

## 2. Adapter → Simulator (chain_adapter)

Output del chain_adapter: `CanonicalChain` (vedi `domain/events.py`)

### Mapping SignalChain → CanonicalChain

| Campo CanonicalChain | Sorgente | Note |
|---|---|---|
| `signal_id` | `chain.chain_id` | — |
| `trader_id` | `chain.trader_id` | — |
| `symbol` | `chain.symbol` | — |
| `side` | `chain.side` | — |
| `input_mode` | CHAIN_COMPLETE se updates non vuoti, else SIGNAL_ONLY_NATIVE | — |
| `has_updates_in_dataset` | `bool(chain.updates)` | — |
| `created_at` | `chain.open_ts` | — |
| `events[0]` | OPEN_SIGNAL (EventType) con payload da NEW_SIGNAL | Sempre primo evento |
| `events[1..]` | UPDATE eventi con EventType derivato da intents | Uno per UPDATE con intent riconosciuto |

### Intent → EventType mapping (chain_adapter)

| Intent (UPDATE) | EventType canonico |
|---|---|
| `U_MOVE_STOP` | `MOVE_STOP` |
| `U_MOVE_STOP_TO_BE` | `MOVE_STOP_TO_BE` |
| `U_CLOSE_PARTIAL` | `CLOSE_PARTIAL` |
| `U_CLOSE_FULL` | `CLOSE_FULL` |
| `U_CANCEL_PENDING` | `CANCEL_PENDING` |
| `U_ADD_ENTRY` | `ADD_ENTRY` |
| altri intents (U_TP_HIT, U_SL_HIT, ...) | skipped — salvati in metadata |

### OPEN_SIGNAL payload

```python
{
    "entry_prices": list[float],      # da chain.entry_prices
    "sl_price": float,                # da chain.sl_price
    "tp_levels": list[float],         # da chain.tp_prices
    "side": str,
    "symbol": str,
    # da NewSignalEntities se presente:
    "entry_type": str,                # LIMIT | MARKET (canonico); AVERAGING / ZONE deprecati
    "stop_loss": float,               # ridondante con sl_price
    "entries": list[{"price": float, "order_type": str}],
    "take_profits": list[{"price": float, "label": str|None}],
}
```

---

## 3. Contratto minimo per simulazione standard (validator)

Verificato da `adapters/validators.py`:

### Chain valida per simulazione (tutti i seguenti):
- `signal_id` non vuoto
- `symbol` non vuoto
- `side` non vuoto
- almeno un evento `OPEN_SIGNAL`
- payload OPEN_SIGNAL contiene `entry_prices` (non vuoto)
- payload OPEN_SIGNAL contiene `sl_price` (non None)
- payload OPEN_SIGNAL contiene `tp_levels` (non vuoto)

### Classificazione gap

| Tipo | Esempi | Effetto |
|---|---|---|
| **FATAL** | entry assente, SL assente, TP assente, signal_id vuoto | Chain esclusa da simulazione standard |
| **WARNING** | UPDATE orfano, trader_id non risolto | Chain inclusa con avviso |
| **OPTIONAL** | risk_budget_usdt, management_rules_json, entry_split_json | Non usato dal simulator V1 |

---

## 4. Simulator → Output

### event_log
- Lista `EventLogEntry` (vedi `domain/results.py`)
- Ogni entry distingue `requested_action` vs `executed_action`
- `processing_status`: APPLIED / IGNORED / REJECTED / GENERATED
- Serializzazione: JSONL tramite `reports/event_log_report.py`

### trade_result
- `TradeResult` (vedi `domain/results.py`)
- Derivato da `TradeState` finale + event log
- Serializzazione: Parquet tramite `reports/trade_report.py`

### scenario_result
- Aggregazione di più `TradeResult` (Sprint 5)
- Non ancora implementato

---

## 5. Policy contract

- Schema: `policies/base.py` — classe `PolicyConfig` Pydantic v2
- Caricamento: `policies/policy_loader.py` (Sprint 3)
- File YAML: `configs/policies/`

### Blocchi policy

| Blocco | Classe | Descrizione |
|---|---|---|
| `entry` | `EntryPolicy` | Allocazione e uso entries |
| `tp` | `TpPolicy` | Strategia take profit |
| `sl` | `SlPolicy` | Stop loss e break-even |
| `updates` | `UpdatesPolicy` | Quali update trader applicare |
| `pending` | `PendingPolicy` | Timeout pending e chain |
| `risk` | `RiskPolicy` | Risk sizing (V1 vuoto) |
| `execution` | `ExecutionPolicy` | Latency, slippage, fill model |

---

## 6. Gap dataset — classificazione da audit F0

Da `docs/audit_db_report.md`:

| Gap | Severity | Catene affette (campione 25) |
|---|---|---|
| stop_loss assente | FATAL | 3/25 (12%) |
| take_profit assente | FATAL | 4/25 (16%) |
| is_blocked=1 | esclusione gate | 1/25 (4%) |
| UPDATE orfano | WARNING | 0/25 nel campione |

Catene completamente simulabili nel campione: **18/25 (72%)**.
