# Design: partial_fill_model

Documento di analisi e specifica per la futura implementazione del modello di fill parziale degli ordini limit nel simulatore.

---

## Problema

Il simulatore attuale usa un modello **touch = fill garantito al 100%** (`fill_touch_guaranteed: true`).
Quando una candela tocca il prezzo di un ordine limit, l'intera size viene eseguita immediatamente.

In realtà questo non accade sempre:
- Ordini in coda davanti al nostro (market microstructure)
- Candele che lambiscono il prezzo senza volume sufficiente
- Mercati poco liquidi con spread ampi
- Ordini di size elevata rispetto alla liquidità disponibile al livello

Il placeholder nel template YAML è già presente:
```yaml
execution:
  # partial_fill_model: none
```

---

## Stato del codice attuale (riferimento implementazione)

**Entry point rilevante:** `simulator.py` → `_try_fill_pending_entries()` (~riga 500)

```python
for plan in pending_plans:
    qty = float(plan.size_ratio)   # sempre 100% del plan
    fill = try_fill_limit_order_touch(qty=qty, ...)
    if fill is None:
        continue
    state.fills.append(fill)       # plan marcato come "eseguito"
    state.pending_size -= fill.qty
    state.open_size += fill.qty
```

**Tracking plan/fill:** usa `index >= len(state.fills)` per distinguere plan ancora pending da quelli eseguiti. Assume ogni plan è o tutto-fillato o non-fillato. Non esiste stato intermedio "parzialmente fillato, resto ancora pending".

**Fill model:** `fill_model.py` → `try_fill_limit_order_touch()` — ritorna `FillRecord | None`.
La qty ricevuta in input viene passata intatta al `FillRecord`.

---

## Approcci possibili (per priorità di implementazione)

### 1. `fixed_ratio` — V1 raccomandato

Il fill avviene ma con una frazione fissa della size pianificata.

```yaml
execution:
  partial_fill_model: fixed_ratio
  partial_fill_ratio: 0.8   # 0.0–1.0
```

**Comportamento:**
- Il plan viene marcato come eseguito con `qty * ratio` invece di `qty` piena
- Il residuo `qty * (1 - ratio)` rimane come `pending_size` e viene gestito dai timeout esistenti (`pending_timeout_hours`, `cancel_pending_on_timeout`)
- Nessuna modifica al tracking plan/fill — architettura invariata

**Dove modificare:**
- `policies/base.py` → `ExecutionPolicy`: aggiungere `partial_fill_model: str = "none"` e `partial_fill_ratio: float = 1.0`
- `fill_model.py` → nuova funzione `_apply_partial_fill(qty, policy) -> float` che riduce la qty
- `simulator.py` → `_try_fill_pending_entries`: applicare il ratio prima di chiamare `try_fill_limit_order_touch`

**Limiti:**
- Il residuo non fillato non genera un nuovo ordine pending al prezzo — si "disperde" nel `pending_size` e viene cancellato dal timeout
- Non modella il re-queuing (ordine che torna in coda e riprova la candela successiva)

**Refactor necessario:** nessuno. Modifica localizzata in 3 file.

---

### 2. `volume_proportional` — V2

Il fill ratio è proporzionale al volume della candela rispetto alla notional dell'ordine.

```yaml
execution:
  partial_fill_model: volume_proportional
  partial_fill_volume_cap: 0.1   # max 10% del volume candela usabile per l'ordine
```

**Comportamento:**
- `fill_ratio = min(1.0, candle.volume * cap / order_notional)`
- Ordini piccoli in mercati liquidi → fill quasi completo
- Ordini grandi o candele a basso volume → fill parziale

**Prerequisiti:**
- `Candle` deve esporre `volume: float` (verificare se già presente in `market/data_models.py`)
- Il provider di dati deve fornire il volume (Bybit OHLCV lo include sempre)

**Refactor necessario:** basso se `Candle.volume` esiste già, medio altrimenti.

---

### 3. `re_queue` — V3 (architettura più complessa)

Il residuo non fillato rimane come ordine vivo alla stessa candela successiva.

**Comportamento:**
- Fill parziale candela N → il residuo viene riprovato a candela N+1, N+2, ecc.
- Si cancella solo per timeout esplicito o per `cancel_averaging_pending_after`

**Prerequisiti architetturali:**
- Il tracking `index >= len(state.fills)` non regge più: servono stati per-plan (`PENDING`, `PARTIALLY_FILLED`, `FILLED`)
- `EntryPlan` deve portare `filled_qty: float = 0.0` e `remaining_qty: float`
- `_try_fill_pending_entries` deve iterare sui plan per `remaining_qty > 0` invece che per `index >= len(fills)`
- `state.fills` potrebbe dover accettare N fill per lo stesso plan

**Refactor necessario:** significativo — tocca `TradeState`, `EntryPlan`, `FillRecord`, `_try_fill_pending_entries`, e il report (fills_count, avg_entry_price).

---

## Interazioni con altri modelli

| Modello | Interazione con partial fill |
|---|---|
| `fee_model: fixed_bps` | La fee si calcola sulla qty effettivamente fillata — già corretto automaticamente perché la fee usa `fill.qty` |
| `slippage_model: fixed_bps` | Si applica al prezzo, indipendente dalla qty — nessuna interazione |
| `cancel_averaging_pending_after` | Cancella i pending dopo un TP hit — si applica anche al residuo non fillato da partial fill |
| `cancel_unfilled_pending_after` | Cancella se TP raggiunto prima di qualsiasi fill — interagisce: con partial fill ci può essere un fill minimo ma open_size bassa |
| `pending_timeout_hours` | Cancella il residuo naturalmente — è il cleanup mechanism di V1 |

---

## Prompt di implementazione (quando sarà il momento)

```
Implementa partial_fill_model: fixed_ratio nel simulatore.

Contesto: docs/DESIGN_partial_fill_model.md — sezione "Approccio 1".

File da toccare:
1. src/signal_chain_lab/policies/base.py
   → ExecutionPolicy: aggiungere partial_fill_model: str = "none" e partial_fill_ratio: float = 1.0

2. src/signal_chain_lab/engine/fill_model.py
   → aggiungere _apply_partial_fill(qty: float, policy: PolicyConfig) -> float
     logica: if model == "fixed_ratio": return qty * ratio; else: return qty

3. src/signal_chain_lab/engine/simulator.py → _try_fill_pending_entries
   → prima di chiamare fill_market_order / try_fill_limit_order_touch:
     effective_qty = _apply_partial_fill(qty, policy)
   → usare effective_qty invece di qty nelle chiamate fill

4. configs/policies/policy_template_full.yaml
   → decommentare e documentare partial_fill_model e partial_fill_ratio

Test da aggiungere: verifica che con ratio=0.8 e size_ratio=1.0, il fill risultante abbia qty=0.8
e pending_size residua venga gestita dal timeout.
```
