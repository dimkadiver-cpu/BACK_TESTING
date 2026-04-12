# Supporto simulatore — stato corrente

Documento tecnico aggiornato: 2026-04-12 (rev 3 — tp_close_distribution, slippage_model, cancel_unfilled_if_tp1_reached_before_fill).

---

## Cosa è supportato davvero

| Feature | Stato | File / Riga |
|---------|-------|-------------|
| Entry multiple con pesatura | ✅ Supportato | `state_machine.py:_entry_specs_from_payload()` |
| Fill market touch-based | ✅ Supportato | `fill_model.py:try_fill_limit_order_touch()` |
| Fill market order con latency | ✅ Supportato | `fill_model.py:fill_market_order()` |
| `execution.latency_ms` | ✅ Supportato | `latency_model.py` |
| SL/TP detection su candele | ✅ Supportato | `simulator.py:_detect_sl_tp_collision()` |
| Risoluzione intrabar collision | ✅ Supportato | `simulator.py:_resolve_collision()` |
| Fallback intrabar (+ warning) | ✅ Supportato | `simulator.py:_resolve_collision()` |
| `pending.pending_timeout_hours` | ✅ Supportato | `timeout_manager.py` |
| `pending.chain_timeout_hours` | ✅ Supportato | `timeout_manager.py` |
| ADD_ENTRY / MOVE_STOP / MOVE_STOP_TO_BE | ✅ Supportato | `state_machine.py:apply_event()` |
| CLOSE_PARTIAL / CLOSE_FULL / CANCEL_PENDING | ✅ Supportato | `state_machine.py:apply_event()` |
| **`tp.use_tp_count`** | ✅ **Implementato** | `state_machine.py:_apply_open_signal()` |
| **`tp.tp_distribution` = `equal`** | ✅ **Implementato** | `state_machine.py:_get_tp_absolute_weights()` |
| **`tp.tp_distribution` = `original`** | ✅ **Implementato** (alias di `equal`) | `state_machine.py:_get_tp_absolute_weights()` |
| **`tp.tp_distribution` = `tp_50_30_20`** | ✅ **Implementato** (2, 3, 4 TP; equal fallback per altri) | `state_machine.py:_get_tp_absolute_weights()` |
| **Multi-TP: scale-out reale** | ✅ **Implementato** | `simulator.py:_apply_close_resolution()` |
| **Evento `tp_hit_partial` (CLOSE_PARTIAL engine)** | ✅ **Implementato** | `simulator.py:_build_engine_close_event()` |
| **Evento `tp_hit_final` (CLOSE_FULL engine)** | ✅ **Implementato** | `simulator.py:_build_engine_close_event()` |
| **`sl.be_trigger` = `"tpN"`** | ✅ **Implementato** | `simulator.py:_handle_post_tp_partial_actions()` |
| **`pending.cancel_averaging_pending_after_tp1`** | ✅ **Implementato** | `simulator.py:_handle_post_tp_partial_actions()` |
| **`entry.max_entries_to_use`** | ✅ **Implementato** | `state_machine.py:_apply_open_signal()` |
| **`entry.allow_add_entry_updates`** | ✅ **Implementato** | `state_machine.py:apply_event()` |
| **`updates.apply_move_stop` / `sl.move_sl_with_trader`** | ✅ **Implementato** | `state_machine.py:apply_event()` |
| **`updates.apply_close_partial`** | ✅ **Implementato** | `state_machine.py:apply_event()` |
| **`updates.apply_close_full`** | ✅ **Implementato** | `state_machine.py:apply_event()` |
| **`updates.apply_cancel_pending`** | ✅ **Implementato** | `state_machine.py:apply_event()` |
| **`updates.apply_add_entry`** | ✅ **Implementato** | `state_machine.py:apply_event()` |
| **`pending.cancel_pending_on_timeout`** | ✅ **Implementato** | `timeout_manager.py:check_pending_timeout()` |
| **`tp.tp_distribution.tp_close_distribution`** | ✅ **Implementato** | `state_machine.py:_apply_open_signal()` — lettura tabella dal config |
| **`execution.slippage_model` = `"fixed_bps"`** | ✅ **Implementato** | `fill_model.py:_apply_slippage()` — richiede `slippage_bps` |
| **`execution.slippage_bps`** | ✅ **Implementato** | `policies/base.py` + `fill_model.py` |
| **`pending.cancel_unfilled_if_tp1_reached_before_fill`** | ✅ **Implementato** | `simulator.py:_detect_tp1_before_fill()` |

---

## Semantica multi-TP implementata

### Flusso per ogni TP hit

1. **`_detect_sl_tp_collision`** controlla `tp_levels[next_tp_index]` (non sempre TP1).
2. **`_apply_close_resolution`** (per TP hit):
   - Recupera `close_fraction = tp_close_fractions[next_tp_index]` (pre-calcolato all'apertura del segnale).
   - Realizza PnL solo per `close_qty = open_size × close_fraction`.
   - Incrementa `next_tp_index`.
   - Ritorna `(is_full_close, close_fraction)`.
3. **`_build_engine_close_event`**:
   - Se parziale → `CLOSE_PARTIAL` con `close_pct = close_fraction`.
   - Se finale (ultimo TP) → `CLOSE_FULL` con `reason = "tp_hit"`.
4. **`apply_event(CLOSE_PARTIAL)`** nel state_machine riduce `open_size` senza re-realizzare PnL.
5. **`_handle_post_tp_partial_actions`** (solo per partial):
   - Emette `MOVE_STOP_TO_BE` se `sl.be_trigger` corrisponde al TP appena colpito.
   - Emette `CANCEL_PENDING` se `pending.cancel_averaging_pending_after_tp1 = True` e TP1 era il livello colpito.

### Calcolo `tp_close_fractions`

Calcolato in `_apply_open_signal` al momento dell'`OPEN_SIGNAL`.

**Step 1 — pesi assoluti** (`_get_tp_absolute_weights`):

| Distribution | N TPs | Pesi assoluti |
|-------------|-------|---------------|
| `equal` / `original` | qualsiasi | `[1/N, 1/N, ..., 1/N]` |
| `tp_50_30_20` | 2 | `[0.5, 0.5]` |
| `tp_50_30_20` | 3 | `[0.5, 0.3, 0.2]` |
| `tp_50_30_20` | 4 | `[0.5, 0.3, 0.15, 0.05]` |
| `tp_50_30_20` | altro | fallback `equal` + log warning |
| sconosciuta | qualsiasi | fallback `equal` |

**Step 2 — conversione in frazioni di open_size corrente** (`_weights_to_fractions_of_current`):

Data distribuzione `[w0, w1, w2]` con somma = 1.0:
```
f0 = w0 / 1.0
f1 = w1 / (1 - w0)
f2 = 1.0   # sempre 1.0 all'ultimo TP
```

Esempio per `equal` con 3 TP:
- pesi = [1/3, 1/3, 1/3]
- `f0 = 0.333`, `f1 = 0.500`, `f2 = 1.0`

Esempio per `tp_50_30_20` con 3 TP:
- pesi = [0.5, 0.3, 0.2]
- `f0 = 0.500`, `f1 = 0.600`, `f2 = 1.0`

### Garanzia di coerenza PnL

- PnL viene realizzato UNA SOLA VOLTA in `_apply_close_resolution` per `close_qty`.
- `CLOSE_PARTIAL` engine event NON include `close_price` → il state_machine NON ri-realizza PnL.
- `CLOSE_FULL` engine event NON include `close_price` → stessa garanzia.

---

## Semantica policy guards — update e entry

### Guards su eventi trader-source

Tutti i flag `updates.*`, `entry.allow_add_entry_updates` e `sl.move_sl_with_trader` agiscono
**solo su eventi con `source = EventSource.TRADER`**.  
Gli eventi generati dall'engine (SL/TP hit, timeout, break-even) ignorano queste impostazioni e
vengono sempre applicati.

Quando un evento trader viene bloccato da policy, lo stato `processing_status` diventa `ignored`
e il `reason` indica la causa (es. `move_stop_disabled_by_policy`).

### `entry.max_entries_to_use`

Viene applicato in `_apply_open_signal()` dopo `_entry_specs_from_payload()`:
- Tronca la lista agli N entry levels richiesti.
- Re-normalizza i `size_ratio` residui in modo che la loro somma torni a 1.0.
  Questo garantisce che `pending_size` sia coerente con il budget totale allocato.

### `pending.cancel_pending_on_timeout`

Se `False`, `check_pending_timeout()` ritorna `None` e i pending limit order rimangono attivi
indefinitamente oltre la finestra `pending_timeout_hours`.  
`chain_timeout_hours` non è influenzato da questo flag: la chain viene comunque chiusa al suo scadere.

### `tp.tp_distribution.tp_close_distribution`

Quando `tp_distribution` è un oggetto `TpDistributionConfig` con `tp_close_distribution` popolato,
il campo ha **priorità** sulla tabella interna di `_get_tp_absolute_weights()`.

Lookup: `tp_close_distribution[N]` dove `N = len(tp_levels)` dopo l'applicazione di `use_tp_count`.  
I valori sono interi (percentuali); vengono normalizzati a somma 1.0 prima dell'uso.  
Se la riga per `N` è assente o mal formata, si cade back sul `mode` (es. `follow_all_signal_tps`).

### `execution.slippage_model = "fixed_bps"`

Applicato **solo ai market order** (non ai limit order, che fillano sempre al prezzo esatto del limite).  
Il `fill_price` viene sfasato di `slippage_bps / 10000` in direzione avversa:
- LONG: `fill_price = reference_price × (1 + bps/10000)`
- SHORT: `fill_price = reference_price × (1 - bps/10000)`

`slippage_bps = 0` è equivalente a `slippage_model = "none"`.  
Il parametro `slippage_bps` è un campo distinto in `ExecutionPolicy`.

---

## Feature configurabili ma non ancora applicate nel core

| Campo policy | Stato | Note |
|-------------|-------|------|
| `entry.use_original_entries` | ⚠️ Ignorato | L'engine usa sempre le entry presenti nel payload |
| `entry.entry_allocation` | ⚠️ Ignorato | I pesi reali vengono letti da `entry_split`; questo campo non è consultato |
| **`entry.max_entries_to_use`** | ✅ **Implementato** | `state_machine.py:_apply_open_signal()` — slicing + re-normalizzazione size_ratio |
| **`entry.allow_add_entry_updates`** | ✅ **Implementato** | `state_machine.py:apply_event()` — ignora ADD_ENTRY da trader se False |
| `tp.use_original_tp` | ⚠️ Ignorato | Il simulatore usa sempre i TP del segnale |
| **`tp.tp_distribution.tp_close_distribution`** | ✅ **Implementato** | `state_machine.py:_apply_open_signal()` — priorità sulla tabella interna se la riga per N TPs è presente |
| `sl.use_original_sl` | ⚠️ Ignorato | Il simulatore usa sempre l'SL del segnale |
| **`sl.move_sl_with_trader`** | ✅ **Implementato** | `state_machine.py:apply_event()` — ignora MOVE_STOP da trader se False |
| **`updates.apply_move_stop`** | ✅ **Implementato** | `state_machine.py:apply_event()` — ignora MOVE_STOP da trader se False |
| **`updates.apply_close_partial`** | ✅ **Implementato** | `state_machine.py:apply_event()` — ignora CLOSE_PARTIAL da trader se False |
| **`updates.apply_close_full`** | ✅ **Implementato** | `state_machine.py:apply_event()` — ignora CLOSE_FULL da trader se False |
| **`updates.apply_cancel_pending`** | ✅ **Implementato** | `state_machine.py:apply_event()` — ignora CANCEL_PENDING da trader se False |
| **`updates.apply_add_entry`** | ✅ **Implementato** | `state_machine.py:apply_event()` — ignora ADD_ENTRY da trader se False |
| **`pending.cancel_pending_on_timeout`** | ✅ **Implementato** | `timeout_manager.py:check_pending_timeout()` — se False non emette CANCEL_PENDING al timeout |
| **`pending.cancel_unfilled_if_tp1_reached_before_fill`** | ✅ **Implementato** | `simulator.py:_detect_tp1_before_fill()` — detection TP1 senza posizione aperta |
| **`execution.slippage_model` = `"fixed_bps"`** | ✅ **Implementato** | `fill_model.py:_apply_slippage()` — richiede `execution.slippage_bps` |
| `execution.slippage_model` altri valori | ⚠️ Fallback a `"none"` | log warning, nessuno slippage applicato |
| `execution.fill_touch_guaranteed` | ⚠️ Sempre True | Non c'è partial fill o mancato fill dopo touch |

### Nota su `cancel_unfilled_if_tp1_reached_before_fill`

Implementato in `simulator.py:_detect_tp1_before_fill()`.

La funzione verifica, ad ogni candela, se il prezzo ha raggiunto TP1 con `open_size == 0` e `pending_size > 0`.
Se la condizione è vera e il flag è attivo, viene emesso `CANCEL_PENDING` con `reason = "tp1_reached_before_fill"`.

**Semantica direzione:**
- LONG: TP1 raggiunto se `candle.high >= tp_levels[0]`
- SHORT: TP1 raggiunto se `candle.low <= tp_levels[0]`

Il check avviene dopo `_try_fill_pending_entries()`, quindi se la stessa candela filla anche l'entry il cancel non scatta.

---

## Matrice definitiva

```
Policy field                                   | Supporto
-----------------------------------------------|----------
entry.use_original_entries                     | ignorato
entry.entry_allocation                         | ignorato
entry.max_entries_to_use                       | ✅ supportato (slicing + re-norm size_ratio)
entry.allow_add_entry_updates                  | ✅ supportato (guard su ADD_ENTRY trader)
entry.entry_split (LIMIT/MARKET)               | ✅ supportato

tp.use_original_tp                             | ignorato
tp.use_tp_count                                | ✅ supportato
tp.tp_distribution (equal/original)           | ✅ supportato
tp.tp_distribution (follow_all_signal_tps)    | ✅ alias di equal (nessun warning)
tp.tp_distribution (tp_50_30_20)               | ✅ supportato (2/3/4 TP)
tp.tp_distribution (altro sconosciuto)         | fallback equal + warning log
tp.tp_distribution.tp_close_distribution      | ✅ supportato (priorità sulla tabella interna per N TPs)

sl.use_original_sl                             | ignorato
sl.break_even_mode                             | parziale: solo "none" vs non-none
sl.be_trigger ("tpN")                          | ✅ supportato (richiede anche break_even_mode != "none")
sl.move_sl_with_trader                         | ✅ supportato (guard su MOVE_STOP trader)

updates.apply_move_stop                        | ✅ supportato (guard su MOVE_STOP trader)
updates.apply_close_partial                    | ✅ supportato (guard su CLOSE_PARTIAL trader)
updates.apply_close_full                       | ✅ supportato (guard su CLOSE_FULL trader)
updates.apply_cancel_pending                   | ✅ supportato (guard su CANCEL_PENDING trader)
updates.apply_add_entry                        | ✅ supportato (guard su ADD_ENTRY trader)

pending.pending_timeout_hours                  | ✅ supportato
pending.chain_timeout_hours                    | ✅ supportato
pending.cancel_pending_on_timeout              | ✅ supportato (se False non emette cancel su timeout)
pending.cancel_averaging_pending_after_tp1     | ✅ supportato
pending.cancel_unfilled_if_tp1_*               | ✅ supportato (detection su candle senza posizione aperta)

execution.latency_ms                           | ✅ supportato
execution.slippage_model (none)                | ✅ supportato (nessuno slippage)
execution.slippage_model (fixed_bps)           | ✅ supportato (richiede slippage_bps > 0)
execution.slippage_bps                         | ✅ supportato
execution.fill_touch_guaranteed                | ignorato (sempre True)
```

---

## Log eventi: come distinguere partial vs final TP

| `event_type` | `source` | `reason` | Significato |
|-------------|----------|----------|-------------|
| `CLOSE_PARTIAL` | `engine` | `tp_hit_partial` | TP parziale, posizione ancora aperta |
| `CLOSE_FULL` | `engine` | `tp_hit` | Ultimo TP, posizione chiusa completamente |
| `CLOSE_FULL` | `engine` | `sl_hit` | SL hit, posizione chiusa completamente |
| `MOVE_STOP_TO_BE` | `engine` | `be_trigger` | SL mosso a break-even dopo trigger TP |
| `CANCEL_PENDING` | `engine` | `cancel_averaging_after_tp1` | Pending annullati dopo TP1 |
