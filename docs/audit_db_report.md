# Audit DB Report — Signal Chain Backtesting Lab
**Data:** 2026-04-07  
**DB:** `data/source.sqlite3`  
**Script:** `scripts/audit_existing_db.py`

---

## 1. Riepilogo esecutivo

| Metrica | Valore |
|---|---|
| DB disponibile | ✅ |
| Tabelle presenti | `raw_messages`, `parse_results`, `operational_signals`, `signals` |
| Catene totali analizzate | 25 |
| Catene completamente simulabili (entry+SL+TP, non bloccate) | 18 |
| Catene con almeno un UPDATE | ~7 |
| Gap classificati | ✅ |
| Contratto dati minimo verificato | ✅ |

---

## 2. Schema DB — tabelle presenti

Tutte le tabelle necessarie per il chain_builder sono presenti:

| Tabella | Stato | Note |
|---|---|---|
| `raw_messages` | ✅ PRESENTE | Contiene `message_ts`, `source_chat_id`, `telegram_message_id`, `processing_status` |
| `parse_results` | ✅ PRESENTE | Contiene `parse_result_normalized_json` con entities e intents |
| `operational_signals` | ✅ PRESENTE | Contiene `attempt_key`, `trader_id`, `message_type`, `resolved_target_ids` |
| `signals` | ✅ PRESENTE | Contiene `symbol`, `side` per attempt_key |
| `review_queue` | ✅ PRESENTE | Vuota nel campione |

---

## 3. Analisi campione — 25 chain

### 3.1 Distribuzione per trader

| Trader | Chain | Note |
|---|---|---|
| trader_3 | 9 | — |
| trader_a | 8 | — |
| trader_b | 8 | — |

### 3.2 Distribuzione processing_status (raw_messages)

| Status | Count |
|---|---|
| done | 33 (25 NEW_SIGNAL + 8 UPDATE) |

### 3.3 Presenza campi minimi identità chain

| Campo | Presente | Note |
|---|---|---|
| `signal_id` (attempt_key) | 25/25 (100%) | Derivato da `os.attempt_key` |
| `trader_id` | 25/25 (100%) | Da `os.trader_id` |
| `symbol` | 25/25 (100%) | Da tabella `signals` via `attempt_key` |
| `side` | 25/25 (100%) | Da tabella `signals` via `attempt_key` |
| `timestamp` | 25/25 (100%) | Da `raw_messages.message_ts` |

### 3.4 Presenza dati minimi per simulazione

| Campo | Presente | Mancante | IDs mancanti |
|---|---|---|---|
| `entry` (almeno 1) | 25/25 (100%) | 0 | — |
| `stop_loss` | 22/25 (88%) | 3 | op_signal_id: 1, 12, 23 |
| `take_profit` (almeno 1) | 21/25 (84%) | 4 | op_signal_id: 1, 8, 15, 22 |
| Non bloccate | 24/25 (96%) | 1 | op_signal_id: 4 (block: global_cap_exceeded) |

### 3.5 Simulabilità per standard V1 (entry + SL + TP, non bloccate)

| Condizione | Count |
|---|---|
| Completamente simulabili | **18 / 25** (72%) |
| Mancano SL o TP | 6 |
| Bloccate (is_blocked=1) | 1 |

### 3.6 Catene con UPDATE

| Tipo update | Count chains | Note |
|---|---|---|
| U_MOVE_STOP | ~4 catene | SL modificato |
| U_CLOSE_FULL | ~3 catene | Chiusura totale |
| Catene signal-only native | ~18 | Solo NEW_SIGNAL, nessun UPDATE |

---

## 4. Verifica chain_builder.py

### F0.9 — Chain completa con update
**Risultato:** ✅ VERIFICATO  
Il chain_builder produce correttamente `SignalChain` su chain con UPDATE:
- linkage via `resolved_target_ids` funziona
- fallback via `reply_to_message_id` funziona
- ordinamento cronologico update funziona
- `close_ts` derivato da `U_CLOSE_FULL` funziona

Test di riferimento: `src/signal_chain_lab/adapters/tests/test_chain_builder.py` (11 test, tutti verdi)

### F0.10 — Chain signal-only nativa
**Risultato:** ✅ VERIFICATO  
Il chain_builder accetta chain con solo `NEW_SIGNAL` e nessun update.  
`updates` = `[]`, `close_ts` = `None`.

---

## 5. Classificazione gap dataset

### Fatal for simulation (chain esclusa)

| Gap | Catene affette | Impatto |
|---|---|---|
| `stop_loss` assente | 3/25 (12%) | Chain non entra in simulazione standard |
| `take_profit` assente | 4/25 (16%) | Chain non entra in simulazione standard |
| `is_blocked = 1` | 1/25 (4%) | Chain non simulata (gate bloccato) |

Totale chain con gap fatale: **7/25** (28%)

### Warning (chain inclusa con avviso)

| Gap | Catene affette | Impatto |
|---|---|---|
| UPDATE orfano (no link a NEW_SIGNAL) | 0 nel campione | Skip + warning log |
| `trader_id` ambiguo | 0 nel campione | — |
| `symbol` o `side` mancante in `signals` | 0 nel campione | Chain skippata con warning |

### Optional (non blocca, solo metadato)

| Campo | Note |
|---|---|
| `risk_budget_usdt` | Assente/NULL in molte righe, non necessario per simulazione V1 |
| `position_size_usdt` | Opzionale, fallback su policy execution |
| `management_rules_json` | Snapshot config opzionale, non usato dal simulator V1 |
| `entry_split_json` | Allocazione entry, opzionale in V1 |

---

## 6. Mapping DB → modello canonico (sintesi)

| Campo canonico | Sorgente DB | Stato |
|---|---|---|
| `signal_id` | `os.attempt_key` | ✅ PRESENTE |
| `trader_id` | `os.trader_id` | ✅ PRESENTE |
| `symbol` | `signals.symbol` | ✅ PRESENTE |
| `side` | `signals.side` | ✅ PRESENTE |
| `timestamp` | `raw_messages.message_ts` | ✅ PRESENTE |
| `entry_prices` | `parse_result_normalized_json.entities.entries[].price.value` | ✅ PRESENTE (100%) |
| `stop_loss` | `parse_result_normalized_json.entities.stop_loss.price.value` | ⚠️ MANCANTE 12% |
| `take_profits` | `parse_result_normalized_json.entities.take_profits[].price.value` | ⚠️ MANCANTE 16% |
| `intents` | `parse_result_normalized_json.intents[].name` | ✅ PRESENTE |
| `update_type` | derivato da `intents` (U_MOVE_STOP, U_CLOSE_FULL, ...) | ✅ PRESENTE |

---

## 7. Acceptance criteria F0

| Criterio | Stato |
|---|---|
| DB letto correttamente | ✅ |
| ≥ 20 chain analizzate | ✅ (25) |
| Contratto dati minimo verificato su esempi reali | ✅ |
| Gap classificati in fatal / warning / optional | ✅ |
| chain_builder produce SignalChain su chain completa | ✅ |
| chain_builder gestisce chain signal-only nativa | ✅ |

---

## 8. Conclusioni

Il DB è **utilizzabile senza riscrittura profonda**.

Il chain_builder esistente legge correttamente le 4 tabelle chiave e produce `SignalChain` validi.

I gap principali (SL e TP mancanti in ~28% delle catene) sono **attesi** nel dataset reale e devono essere gestiti dal validator (classificazione `FATAL_FOR_SIMULATION`).

**Prossimo step:** implementare domain models Sprint 1 e validator con classificazione gap.
