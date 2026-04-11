# Supporto simulatore — stato corrente

Documento tecnico aggiornato: 2026-04-10.

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

## Feature configurabili ma non ancora applicate nel core

| Campo policy | Stato | Note |
|-------------|-------|------|
| `tp.use_original_tp` | ⚠️ Ignorato | Il simulatore usa sempre i TP del segnale |
| `sl.use_original_sl` | ⚠️ Ignorato | Il simulatore usa sempre l'SL del segnale |
| `sl.move_sl_with_trader` | ⚠️ Ignorato | I MOVE_STOP del trader sono sempre applicati |
| `updates.apply_move_stop` | ⚠️ Ignorato | Gli update MOVE_STOP sono sempre applicati |
| `updates.apply_close_partial` | ⚠️ Ignorato | I CLOSE_PARTIAL del trader sono sempre applicati |
| `updates.apply_close_full` | ⚠️ Ignorato | I CLOSE_FULL del trader sono sempre applicati |
| `updates.apply_cancel_pending` | ⚠️ Ignorato | I CANCEL_PENDING del trader sono sempre applicati |
| `updates.apply_add_entry` | ⚠️ Ignorato | Gli ADD_ENTRY del trader sono sempre applicati |
| `pending.cancel_pending_on_timeout` | ⚠️ Ignorato (sempre True) | Il timeout cancella sempre i pending |
| `pending.cancel_unfilled_if_tp1_reached_before_fill` | ❌ Non implementato | Richiederebbe detection di TP1 senza posizione aperta |
| `execution.slippage_model` | ❌ Non implementato | Solo touch = fill senza slippage |
| `execution.fill_touch_guaranteed` | ⚠️ Sempre True | Non c'è partial fill o mancato fill dopo touch |

### Nota su `cancel_unfilled_if_tp1_reached_before_fill`

Il simulatore attuale detecta SL/TP solo quando `open_size > 0` (vedi `_detect_sl_tp_collision`).
Se il prezzo raggiunge TP1 prima che le limit entry siano fillate (gap di prezzo verso l'alto),
la situazione non viene rilevata. Implementare questa feature richiederebbe un
loop separato di detection del prezzo TP senza posizione aperta.

---

## Matrice definitiva

```
Policy field                          | Supporto
--------------------------------------|----------
tp.use_original_tp                    | ignorato
tp.use_tp_count                       | ✅ supportato
tp.tp_distribution (equal/original)  | ✅ supportato
tp.tp_distribution (tp_50_30_20)      | ✅ supportato (2/3/4 TP)
tp.tp_distribution (altro)            | fallback equal + warning

sl.use_original_sl                    | ignorato
sl.break_even_mode                    | parziale: solo "none" vs non-none
sl.be_trigger ("tpN")                 | ✅ supportato
sl.move_sl_with_trader                | ignorato (sempre applicato)

updates.apply_move_stop               | ignorato (sempre applicato)
updates.apply_close_partial           | ignorato (sempre applicato)
updates.apply_close_full              | ignorato (sempre applicato)
updates.apply_cancel_pending          | ignorato (sempre applicato)
updates.apply_add_entry               | ignorato (sempre applicato)

pending.pending_timeout_hours         | ✅ supportato
pending.chain_timeout_hours           | ✅ supportato
pending.cancel_pending_on_timeout     | ignorato (sempre True)
pending.cancel_averaging_after_tp1    | ✅ supportato
pending.cancel_unfilled_if_tp1_*      | ❌ non implementato

execution.latency_ms                  | ✅ supportato
execution.slippage_model              | ❌ non implementato
execution.fill_touch_guaranteed       | ignorato (sempre True)
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
