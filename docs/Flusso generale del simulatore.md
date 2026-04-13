  Flusso generale del simulatore                                                                                                               
                                                                                                                                               
  1. Entry Points (scripts/)                                                                                                                   
                                                                                                                                               
  ┌──────────────────────────┬─────────────────────────────────────────────────────┐                                                           
  │          Script          │                        Scopo                        │                                                           
  ├──────────────────────────┼─────────────────────────────────────────────────────┤                                                           
  │ run_single_chain.py      │ Debug di una singola chain per signal_id            │                                                           
  ├──────────────────────────┼─────────────────────────────────────────────────────┤
  │ run_policy_report.py     │ Report aggregato su tutto il dataset per una policy │
  ├──────────────────────────┼─────────────────────────────────────────────────────┤
  │ run_comparison_report.py │ Confronto tra più policy (≥2) sullo stesso dataset  │
  └──────────────────────────┴─────────────────────────────────────────────────────┘

  ---
  2. Costruzione delle chain (adapters/)

  chain_builder.py legge SQLite e ricostruisce le chain in 3 passi:
  1. Carica tutti i NEW_SIGNAL → mappa op_signal_id → ChainedMessage
  2. Carica tutti gli UPDATE → li collega al NEW_SIGNAL via resolved_target_ids (fallback: reply_to_message_id)
  3. Assembla oggetti SignalChain per attempt_key

  chain_adapter.py converte SignalChain → CanonicalChain:
  - NEW_SIGNAL → OPEN_SIGNAL
  - Intent aggiornamento → eventi canonici (MOVE_STOP, CLOSE_PARTIAL, ADD_ENTRY, ecc.)
  - Update non riconosciuti → metadata.skipped_updates

  ---
  3. Core simulator (engine/simulator.py)

  CanonicalChain + PolicyConfig
          ↓
  [per ogni evento in ordine (timestamp, sequence)]
          ↓
      apply_event()          ← state machine transition
          ↓
      _replay_market_segment()   ← solo se market_provider disponibile
          ├─ _try_fill_pending_entries()   ← fill limit/market
          ├─ check_pending_timeout()       ← cancella pending scaduto
          ├─ check_chain_timeout()         ← forza chiusura chain
          └─ _detect_sl_tp_collision()     ← SL/TP hit → close + post-TP actions
          ↓
  (list[EventLogEntry], TradeState finale)

  ---
  4. Componenti chiave

  State Machine (state_machine.py)
  Gestisce le transizioni di stato: NEW → PENDING → ACTIVE → PARTIALLY_CLOSED → CLOSED/EXPIRED

  Fill Model (fill_model.py)
  - Market order: fill a candle.open + latency + slippage
  - Limit order: fill se candle.low ≤ price (LONG) o candle.high ≥ price (SHORT)
  - Calcola fee per fill

  Timeout Manager (timeout_manager.py)
  - pending_timeout_hours: cancella ordini non eseguiti
  - chain_timeout_hours: forza chiusura intera chain → status EXPIRED

  ---
  5. Policy (configs/policies/*.yaml)

  La policy controlla interamente il comportamento:
  - entry: quante entry usare, pesi, tipo (limit/market/ladder)
  - tp: distribuzione close per TP (equal o table per conteggio)
  - sl: SL originale o break-even automatico dopo TP1
  - updates: quali intent del trader applicare (move_stop, close_partial, ecc.)
  - pending: timeout, cancel averaging dopo TP
  - execution: latency, slippage, fee

  ---
  6. Output

  - EventLogEntry: audit trail completo con snapshot stato prima/dopo ogni evento
  - TradeResult: PnL, MAE/MFE, time-to-fill, fills_count, close_reason
  - ScenarioResult: aggregati sul dataset (win_rate, profit_factor, drawdown, expectancy)

  ---
  Punto critico: il simulatore è completamente deterministico — l'ordine (timestamp, sequence) degli eventi garantisce risultati riproducibili.
   Il market provider è opzionale: senza di esso non ci sono fill, ma la simulazione degli intent del trader funziona comunque.

  Punti critici del simulatore                                                                                                                 
                                                                                                                                               
  1. Divisione responsabilità PnL — design intenzionale ma fragile                                                                             
                                                                                                                                               
  _apply_close_resolution (simulator.py) calcola e realizza il PnL prima di chiamare apply_event. Lo state machine poi gestisce le transizioni
  di stato (open_size, status, closed_at) ma non ri-calcola il PnL perché gli eventi engine non portano close_price nel payload:               
                                                                                                                                               
  # _build_engine_close_event — nessun close_price                                                                                             
  payload={"reason": "tp_hit", "raw_text": "..."}

  # state_machine.py CLOSE_FULL handler
  close_price = event.payload.get("close_price")
  if close_price is not None:          # ← None per eventi engine → nessun double-count
      _realize_pnl_for_close(...)

  Funziona, ma è implicito. Un domani se qualcuno aggiunge close_price all'evento engine, il PnL viene doppiato silenziosamente.

  ---
  2. Multi-TP su singola candela — bug latente

  # simulator.py:384
  collision = _detect_sl_tp_collision(state=state, candle=candle)
  # ... processa TP1, incrementa next_tp_index ...
  if state.status in {CLOSED, CANCELLED, EXPIRED, INVALID}:
      break
  # ← se status = PARTIALLY_CLOSED, loop avanza alla candela SUCCESSIVA

  _detect_sl_tp_collision controlla solo tp_levels[next_tp_index]. Se una singola candela copre sia TP1 che TP2 (range ampio), solo TP1 viene
  processato. TP2 viene rilevato sulla candela successiva, il che può non esistere mai se la successiva è fuori segmento.

  ---
  3. Index assumption in _try_fill_pending_entries — fragile

  # simulator.py:504-508
  pending_plans = [
      plan for index, plan in enumerate(state.entries_planned)
      if index >= len(state.fills) ...
  ]

  Assume che i fill avvengano nello stesso ordine di entries_planned. Se un limit order a index=2 viene toccato prima di quello a index=1 (es.
  range di entry con prezzi distanti), l'iterazione è comunque in ordine e il fill viene appeso a state.fills — quindi funziona. Ma se
  entries_planned viene modificato via ADD_ENTRY (inserisce in append), un fill fuori ordine romperebbe il mapping silenziosamente.

  ---
  4. Anacronia di segmento — limitazione nota

  # simulator.py:336-337
  if next_event_ts is not None and candle.timestamp >= _floor_to_timeframe(next_event_ts, timeframe):
      break

  Se un MOVE_STOP arriva alle 12:30 su timeframe 1h, la candela delle 12:00 (che copre 12:00–13:00) viene esclusa dal segmento corrente. Nel
  segmento successivo, viene riprocessata con il nuovo SL già applicato. Significa che i trigger SL/TP della candela 12:00 usano lo stop
  aggiornato anche se il messaggio è arrivato a metà candela.

  ---
  5. Fallback created_at is None — segmento vuoto silenzioso

  # simulator.py:328-329
  chain_timeout_at = (
      state.created_at + timedelta(hours=policy.pending.chain_timeout_hours)
      if state.created_at is not None
      else segment_start_bucket   # ← timeout = inizio segmento → nessuna candela processata
  )

  Se created_at è None (chain malformata), chain_timeout_at == segment_start_bucket, l'intervallo è vuoto e il segmento non processa nulla
  senza errori o warning.

  ---
  Riepilogo impatto

  ┌─────┬────────────────┬─────────────────────────────────────┬─────────────┐
  │  #  │      Tipo      │               Impatto               │ Silenzioso? │
  ├─────┼────────────────┼─────────────────────────────────────┼─────────────┤
  │ 1   │ Design fragile │ Medio (futura regressione)          │ Sì          │
  ├─────┼────────────────┼─────────────────────────────────────┼─────────────┤
  │ 2   │ Bug latente    │ Alto (PnL errato su range ampi)     │ Sì          │
  ├─────┼────────────────┼─────────────────────────────────────┼─────────────┤
  │ 3   │ Fragile        │ Basso (in pratica corretto)         │ Sì          │
  ├─────┼────────────────┼─────────────────────────────────────┼─────────────┤
  │ 4   │ Limitazione    │ Basso (noto, inerente alle candele) │ Sì          │
  ├─────┼────────────────┼─────────────────────────────────────┼─────────────┤
  │ 5   │ Bug difensivo  │ Medio (chain silenziosamente vuota) │ Sì          │
  └─────┴────────────────┴─────────────────────────────────────┴─────────────┘



Problema 1:
● Ora ho il quadro completo. Il problema del PnL è più profondo di quanto sembri.
                                      
  ---                                                                                     
  Il PnL: né % né assoluto
                                                                                                                                               
  Formula effettiva (simulator.py + state_machine.py)
                                                                                                                                               
  realized_pnl += (exit_price - avg_entry_price) * close_qty * direction
                                         
  Dove close_qty = open_size * close_fraction e open_size è accumulato da size_ratio (somma = 1.0 per trade).

  Unità reale: Δprezzo × fraction_dimensionless → es. BTC da 45000→45450 con close_qty=1.0 → PnL = 450

  Non è dollari reali (manca la qty in asset), non è % (manca la divisione per il prezzo di entrata).

  ---
  Bug di naming nel runner (runner.py:114, 175, 333)

  return_pct = (total_pnl / trades_count)   # ← è l'expectancy, non una %
  "gross_profit_pct": gross_profit,          # ← è PnL assoluto, non %
  "gross_loss_pct": -gross_loss_abs,         # ← idem
  "net_profit_pct": float(aggregated["total_pnl"]),  # ← total_pnl rinominato _pct

  Campi nominati _pct che contengono valori in Δprezzo × qty_fraction. Nessun errore di calcolo — ma chiunque legga il report li interpreta
  come percentuali.

  ---
  trade_impact_pct — capital-relative, non trade-relative

  # trade_report.py:78
  trade_impact_pct = state.realized_pnl / initial_capital * 100.0

  Misura quanto ogni trade sposta il capitale totale (es. "questo trade ha fatto +0.45% del capitale"), non il rendimento del trade in sé.
  Richiede --initial-capital, altrimenti è None.

  ---
  Problema strutturale: aggregazione cross-symbol

  BTC: entry=45,000 → exit=45,450 → move +1% → realized_pnl = 450
  ETH: entry=2,500  → exit=2,525  → move +1% → realized_pnl = 25

  total_pnl = 475  ← somma incomparabile

  Stesso rendimento percentuale (1%), ma il BTC pesa 18× di più nell'aggregazione solo perché costa di più. Il total_pnl in ScenarioResult
  somma questi valori eterogenei senza normalizzazione.

  ---
  Le uniche metriche % reali (runner.py:161-169)

  if initial_capital and initial_capital > 0:
      total_return_pct = total_pnl / initial_capital * 100.0
      max_drawdown_pct = _compute_max_drawdown(realized) / initial_capital * 100.0
      expectancy_pct = expectancy / initial_capital * 100.0

  Queste sono corrette ma condizionate a --initial-capital. Senza quel parametro, tutti i valori _pct sono None o numeri mal-nominati.

  ---
  Riepilogo

  ┌──────────────────┬───────────────────────────┬──────────────────────────────────────────────┐
  │      Campo       │  Cosa contiene in realtà  │                  Corretto?                   │
  ├──────────────────┼───────────────────────────┼──────────────────────────────────────────────┤
  │ realized_pnl     │ Δprezzo × size_fraction   │ Calcolato correttamente, semantica implicita │
  ├──────────────────┼───────────────────────────┼──────────────────────────────────────────────┤
  │ return_pct       │ Stesso di expectancy      │ Nome sbagliato                               │
  ├──────────────────┼───────────────────────────┼──────────────────────────────────────────────┤
  │ gross_profit_pct │ Somma PnL grezzo          │ Nome sbagliato                               │
  ├──────────────────┼───────────────────────────┼──────────────────────────────────────────────┤
  │ net_profit_pct   │ total_pnl rinominato      │ Nome sbagliato                               │
  ├──────────────────┼───────────────────────────┼──────────────────────────────────────────────┤
  │ trade_impact_pct │ pnl / capital * 100       │ Corretto ma opzionale                        │
  ├──────────────────┼───────────────────────────┼──────────────────────────────────────────────┤
  │ total_return_pct │ total_pnl / capital * 100 │ Corretto ma opzionale                        │
  └──────────────────┴───────────────────────────┴──────────────────────────────────────────────┘

  Vuoi che sistemi i naming o aggiungiamo una metrica pnl_pct_from_entry vera per trade?


  Problema 2: 
  ● Analizziamo il codice esatto del loop candele e tracciamo lo scenario problema.                                                              
                                                                
  Read 1 file (ctrl+o to expand)                                                                                                               
                                                                                                                                               
● Ora ho tutti i pezzi. Tracciamo il bug con precisione.                                                                                       
                                                                                                                                               
  ---                                                                                                                                          
  Problema 2: multi-TP su singola candela — analisi completa                                                                                   
                                                                                                                                               
  Struttura del loop (simulator.py:334–439)                                                                                                    
                                                                                                                                               
  for candle in candles:               # ← una iterazione = una candela
      _try_fill_pending_entries(...)     
      # ... timeout checks ...

      collision = _detect_sl_tp_collision(state, candle)
      if collision is None:
          continue                     # ← candela pulita → avanti

      resolution = _resolve_collision(...)
      _apply_close_resolution(state, resolution)   # ← PnL + next_tp_index++
      apply_event(state, engine_event, ...)        # ← open_size ridotto

      _handle_post_tp_partial_actions(...)         # ← BE move, cancel pending

      if state.status in {CLOSED, CANCELLED, ...}:
          break
      # ← se PARTIALLY_CLOSED: cade nel for → CANDELA SUCCESSIVA

  _detect_sl_tp_collision controlla solo tp_levels[next_tp_index] — un livello alla volta, riga 115:

  tp_price = state.tp_levels[min(state.next_tp_index, len(state.tp_levels) - 1)]

  Dopo un TP parziale, next_tp_index viene incrementato ma la stessa candela non viene ri-esaminata.

  ---
  Scenario A — multi-TP nella stessa candela

  Posizione LONG, 3 TP: TP1=44500, TP2=45000, TP3=45500
  Candela: open=44000, low=43800, high=45600

  ┌───────────────┬────────────────────────┬───────────┬───────────────────────────────┐
  │  Iterazione   │        Candela         │ Controllo │           Risultato           │
  ├───────────────┼────────────────────────┼───────────┼───────────────────────────────┤
  │ t=100         │ high=45600 ≥ TP1=44500 │ TP1 hit   │ PnL parziale, next_tp_index=1 │
  ├───────────────┼────────────────────────┼───────────┼───────────────────────────────┤
  │ → loop avanza │                        │           │                               │
  ├───────────────┼────────────────────────┼───────────┼───────────────────────────────┤
  │ t=200         │ candela successiva...  │ TP2 check │ Solo se high ≥ 45000          │
  └───────────────┴────────────────────────┴───────────┴───────────────────────────────┘

  TP2 e TP3 che erano già nel range di t=100 vengono processati sulla candela t=200, t=300 — se mai arrivano a quei prezzi. Se il mercato
  scende tra t=100 e t=200, vengono persi per sempre.

  ---
  Scenario B — SL hit post-BE nella stessa candela (più pericoloso)

  Policy: be_trigger = "tp1"  → dopo TP1, sposta SL a avg_entry_price
  Posizione LONG: entry=44000, SL=43000, TP1=44500, TP2=45000
  Candela: open=44000, low=43200, high=45200

  Cosa succede:
  1. _detect_sl_tp_collision: high=45200 ≥ TP1=44500 → TP1 hit
  2. _apply_close_resolution: chiude fraction a TP1, next_tp_index=1
  3. _handle_post_tp_partial_actions: be_trigger TP1 → state.current_sl = 44000 (avg_entry)
  4. Check terminal → PARTIALLY_CLOSED → loop avanza alla candela successiva

  Cosa avrebbe dovuto succedere:
  Stessa candela, low=43200 < new_sl=44000 → SL hit → chiusura del residuo a 44000.

  Il simulatore non ri-verifica il nuovo SL sulla stessa candela. La posizione rimane aperta con un SL a 44000 che è stato già violato.

  Impatto sul PnL: il residuo rimane aperto fino a quando una candela successiva tocca 44000, che potrebbe non accadere mai se il mercato
  rimbalza — gonfiando artificialmente il profitto.

  ---
  Scenario C — TP1 non-finale + SL hit sulla stessa candela

  Posizione SHORT: entry=45000, SL=45500, TP1=44500, TP2=44000
  Candela: open=45000, low=43800, high=45600

  1. _detect_sl_tp_collision: controlla tp_levels[0]=44500 e sl=45500
    - tp_hit = low=43800 ≤ 44500 → True
    - sl_hit = high=45600 ≥ 45500 → True
  2. _resolve_collision: entrambi hit → intrabar resolution o fallback SL
  3. Se intrabar dice SL prima → chiude tutto correttamente
  4. Se intrabar dice TP1 prima → partial close, next_tp_index=1, loop avanza
  5. Candela successiva: il SL potrebbe essere già nel passato, non rilevato

  La logica intrabar per SL vs TP1 viene invocata. Ma dopo TP1 partial, il SL originale rimane nel payload — il codice non ri-controlla lo
  stesso candle per SL vs TP2.

  ---
  Radice del problema

  Il loop candele ha un'architettura one-event-per-candle. Processa al massimo una risoluzione (SL o TP) per iterazione, poi passa alla candela
   successiva. Non esiste un inner loop che ri-esamini la stessa candela dopo una modifica di stato.

  Fix minimo

  Sostituire il singolo check con un ciclo interno sulla stessa candela:

  # dopo _try_fill_pending_entries(...)

  while state.status not in {TradeStatus.CLOSED, TradeStatus.CANCELLED, ...}:
      collision = _detect_sl_tp_collision(state, candle)
      if collision is None:
          break

      resolution = _resolve_collision(...)
      _apply_close_resolution(state, resolution)
      apply_event(state, engine_event, ...)

      if resolution.outcome == "tp_hit" and not is_full_close:
          _handle_post_tp_partial_actions(...)
      else:
          break  # SL o full close → esci

  last_replayed_candle_ts = candle.timestamp

  Questo risolverebbe A, B e C. L'unico rischio è un loop infinito se _detect_sl_tp_collision non converge — ma con next_tp_index che avanza o
  open_size che si azzera ad ogni iterazione, è garantita la terminazione.

Problema 3:

Ho tutto. Il problema è preciso.                                                                                                             
                                                                                                                                               
  ---                                                                                                                                          
  Problema 3: pending_plans — analisi completa                                                                                                 
                                                                                                                                               
  Il filtro incriminato (simulator.py:504–506)                                                                                                 
                                                                                                                                               
  pending_plans = [                                                                                                                            
      plan for index, plan in enumerate(state.entries_planned)
      if index >= len(state.fills) and (plan.price is not None or plan.order_type == "market")
  ]

  Assunzione implicita: fills[i] corrisponde sempre a entries_planned[i].
  Non c'è nessun legame esplicito tra i due — niente ID, niente flag filled, niente tracking. Il codice usa la posizione come proxy
  dell'identità.

  ---
  Perché funziona normalmente

  Per una LONG ladder [E1=44500, E2=44000, E3=43500] il prezzo scende e tocca i livelli in ordine: E1 prima, E2 dopo, E3 per ultimo. fills
  cresce nello stesso ordine di entries_planned. Il filtro funziona per coincidenza.

  ---
  Quando si rompe — scenario ADD_ENTRY

  ADD_ENTRY fa append in fondo alla lista (state_machine.py:508):

  state.entries_planned.append(EntryPlan(...))

  Se il trader manda un ADD_ENTRY con prezzo più alto delle entry già presenti:

  entries_planned iniziale: [E1(limit=44000), E2(limit=43500)]
  fills = []

  Evento ADD_ENTRY a 44500
  → entries_planned = [E1(44000), E2(43500), E3(44500)]
                        idx=0       idx=1       idx=2  ← appeso in fondo

  Candela successiva: low=43800, high=44600

  Per LONG try_fill_limit_order_touch → touched = candle.low <= limit_price:
  E1(44000): low=43800 <= 44000 → FILL ✓
  E2(43500): low=43800 <= 43500 → No
  E3(44500): low=43800 <= 44500 → FILL ✓

  Stato dopo la candela:
  fills = [fill_E1, fill_E3]   len = 2

  Chiamata successiva:
  pending_plans = [
      plan for index, plan in enumerate(entries_planned)
      if index >= len(fills)   # >= 2
  ]
  # → solo entries_planned[2] = E3  ← già fillata!

  Risultato:
  - E3 viene fillata di nuovo (doppio fill)
  - E2 viene saltata per sempre — len(fills) avanzerà a 3, superando l'indice 1 di E2

  Stato finale corrotto:
  fills = [fill_E1, fill_E3, fill_E3_bis]
  open_size = size_E1 + size_E3 + size_E3    ← E3 doppiata
  avg_entry_price                              ← distorta
  pending_size scende a 0                      ← E2 mai consumata

  ---
  Perché source_event_sequence non salva

  FillRecord ha source_event_sequence impostato da plan.sequence:

  # state_machine.py:454
  sequence=event.sequence,   # ← uguale per tutti i piani dell'OPEN_SIGNAL

  Tutti i piani dell'OPEN_SIGNAL hanno lo stesso sequence. Non è un identificatore univoco per piano — non si può usare per distinguere quale
  piano è stato fillato.

  ---
  Quando si rompe — scenario entry_prices non ordinati

  Se il parser produce entry in ordine inverso rispetto al fill order:

  LONG, entry_prices = [43500, 44000]   # parser ordina dal più basso
  entries_planned = [E1(43500), E2(44000)]

  Candela: low=43600, high=44200
  - E1(43500): low=43600 > 43500 → NOT touched
  - E2(44000): low=43600 <= 44000 → FILL ✓

  fills = [fill_E2]   len=1
  → pending_plans = [E2]  (index 1 >= 1)
  → E2 fillata di nuovo
  → E1 saltata per sempre

  ---
  Root cause in una riga

  EntryPlan non ha un campo filled: bool. L'identità di un piano è il suo indice posizionale, che è stabile solo se i fill avvengono in ordine
  stretto di entries_planned.

  ---
  Fix minimale

  Aggiungere filled: bool = False a EntryPlan e marcarlo al momento del fill:

  # trade_state.py
  class EntryPlan(BaseModel):
      role: Literal["primary", "averaging"]
      order_type: Literal["market", "limit", "unknown"]
      price: float | None = None
      size_ratio: float
      label: str | None = None
      sequence: int | None = None
      activation_ts: datetime | None = None
      filled: bool = False          # ← aggiunta

  # simulator.py _try_fill_pending_entries
  pending_plans = [
      plan for plan in state.entries_planned
      if not plan.filled and (plan.price is not None or plan.order_type == "market")
  ]
  ...
  if fill is not None:
      plan.filled = True            # ← marca prima di append
      state.fills.append(fill)
      ...

  Il filtro diventa O(n) sulla lista anziché O(1) sull'indice, ma con al massimo 5–10 entry per trade il costo è trascurabile.


    Problema 4: anacronia di segmento — analisi completa                                                                                         
                                                                                                                                               
  Il meccanismo (simulate_chain:45–63)                                                                                                         
                                                                                                                                               
  for index, event in enumerate(events): 
      logs.append(apply_event(state, event, policy=policy))  # ← 1. stato aggiornato

      _replay_market_segment(
          segment_start=event.timestamp,     # ← 2. candele da event.timestamp in poi
          next_event_ts=next_event_ts,
          last_replayed_candle_ts=...,
      )

  L'evento viene applicato prima del replay del suo segmento. Il segmento parte dal bucket della candela che contiene event.timestamp.

  _floor_to_timeframe(12:30, "1h") = 12:00

  Quindi la candela delle 12:00 (che copre 12:00–13:00) viene processata con lo stato post-evento anche se l'evento è arrivato alle 12:30.

  ---
  Perché la candela di confine viene sempre processata nel segmento successivo

  Segmento 1 (prima del MOVE_STOP alle 12:30):
  # segment_end = _floor_to_timeframe(12:30, "1h") = 12:00
  if candle.timestamp >= 12:00:
      break   # ← candela 12:00 esclusa
  last_replayed_candle_ts = 11:00

  Segmento 2 (dopo MOVE_STOP):
  segment_start_bucket = _floor_to_timeframe(12:30) = 12:00
  # candela 12:00: timestamp=12:00 > last_replayed=11:00 → NON saltata
  # processed con stato post-evento

  La candela delle 12:00 viene elaborata una sola volta, ma con il nuovo SL già attivo, anche per la parte precedente le 12:30.

  ---
  Scenari di distorsione

  A — MOVE_STOP (stop più stretto) mid-candela
  SL originale = 43000 → messaggio 12:30 → nuovo SL = 44000
  Candela 12:00: low = 43500

  Realtà:          12:00–12:30 con SL=43000 → low=43500 > 43000 → NON colpito
                   12:30–13:00 con SL=44000 → low=43500 < 44000 → SL HIT a 44000

  Simulatore:      candela 12:00 intera con SL=44000 → SL HIT a 44000
  Risultato corretto per caso, ma per le ragioni sbagliate. Se il low fosse stato 43800 (< 44000 ma > 43000), il simulatore segna SL HIT ma in
  realtà sarebbe stato colpito solo nella seconda metà della candela — il timing del close è sbagliato di fino a 59 minuti.

  B — MOVE_STOP_TO_BE mid-candela, low sotto entry
  Entry = 44000, messaggio BE alle 12:30 → new SL = 44000
  Candela 12:00: low = 43700 (il low avviene alle 12:15, prima del BE)

  Realtà:          12:00–12:30 con SL=43000 → low=43700 → NON colpito
                   12:30–13:00 con SL=44000 → low NON raggiunge 44000 → trade aperto

  Simulatore:      candela 12:00 con SL=44000 → low=43700 < 44000 → SL HIT
  Il trade viene chiuso a breakeven quando in realtà sarebbe rimasto aperto. Falso stop.

  C — CANCEL_PENDING mid-candela
  Entry limit a 44000, messaggio cancel alle 12:30
  Candela 12:00: low=43800 <= 44000 → avrebbe fillato alle ~12:05

  Realtà:          fill alle 12:05, poi cancel alle 12:30 → posizione aperta fino a cancel

  Simulatore:      candela 12:00 processata con pending_size=0 → nessun fill
  Una fill reale viene persa. Il trade non viene mai eseguito.

  ---
  Direzione della distorsione per tipo di evento

  ┌───────────────────────┬───────────────────────────────────────┬───────────────────┐
  │        Evento         │   Effetto sulla candela di confine    │     Direzione     │
  ├───────────────────────┼───────────────────────────────────────┼───────────────────┤
  │ MOVE_STOP più stretto │ SL anticipato di max 1 timeframe      │ Più pessimistico  │
  ├───────────────────────┼───────────────────────────────────────┼───────────────────┤
  │ MOVE_STOP_TO_BE       │ SL anticipato di max 1 timeframe      │ Più pessimistico  │
  ├───────────────────────┼───────────────────────────────────────┼───────────────────┤
  │ MOVE_STOP più largo   │ SL posticipato → hit mancato          │ Più ottimistico   │
  ├───────────────────────┼───────────────────────────────────────┼───────────────────┤
  │ CANCEL_PENDING        │ Fill mancata sulla candela            │ Miss conservativo │
  ├───────────────────────┼───────────────────────────────────────┼───────────────────┤
  │ CLOSE_PARTIAL         │ Posizione ridotta su tutta la candela │ PnL ridotto       │
  └───────────────────────┴───────────────────────────────────────┴───────────────────┘

  La distorsione è sistematica, non casuale — non si annulla tra i trade.

  ---
  Impatto per timeframe

  ┌───────────┬────────────────────────┬────────────────────────────┐
  │ Timeframe │ Finestra anacronia max │      Impatto pratico       │
  ├───────────┼────────────────────────┼────────────────────────────┤
  │ 1m        │ 59 secondi             │ Trascurabile               │
  ├───────────┼────────────────────────┼────────────────────────────┤
  │ 1h        │ 59 minuti              │ Moderato su asset volatili │
  ├───────────┼────────────────────────┼────────────────────────────┤
  │ 4h        │ 3h 59m                 │ Significativo              │
  ├───────────┼────────────────────────┼────────────────────────────┤
  │ 1d        │ 23h 59m                │ Molto significativo        │
  └───────────┴────────────────────────┴────────────────────────────┘

  ---
  Non è un bug — è una scelta di design con conseguenze note

  Non c'è un fix pulito senza dati sub-candela. Le opzioni sono:

  1. Usare 1m come timeframe base — riduce la finestra a < 60s, praticamente irrilevante
  2. Documentare la limitazione — ogni evento del trader è applicato alla granularità del timeframe, non al secondo esatto
  3. Fix parziale per MOVE_STOP_TO_BE — l'unico caso pericoloso (falso stop): confrontare il low della candela con il vecchio SL prima di
  applicare il BE, processando la prima metà con lo stato precedente

  La scelta attuale (candela di confine sempre nel segmento post-evento) è consistente e riproducibile — due run identiche danno sempre lo
  stesso risultato. Il problema è che il risultato potrebbe non riflettere la realtà su timeframe alti.


   Problema 5: created_at is None — analisi completa                                                                                            
                                                                                                                                               
  La catena di creazione del timestamp                                                                                                         
                                                                                                                                               
  DB: raw_messages.message_ts                                                                                                                
      ↓ _parse_ts()                      
  ChainedMessage.message_ts
      ↓ chain_builder.py:527
  SignalChain.open_ts
      ↓ chain_adapter.py:208
  CanonicalChain.created_at: datetime          ← NON nullable (Pydantic required)
      ↓ (non copiato in build_initial_state)
  TradeState.created_at: datetime | None = None  ← nullable, default None
      ↓ _apply_open_signal (state_machine.py:480)
  state.created_at = event.timestamp           ← impostato solo dopo OPEN_SIGNAL

  ---
  Il gap: build_initial_state non copia chain.created_at

  def build_initial_state(chain: CanonicalChain, policy: PolicyConfig) -> TradeState:
      return TradeState(
          signal_id=chain.signal_id,
          trader_id=chain.trader_id,
          symbol=chain.symbol,
          side=chain.side,
          status=TradeStatus.NEW,
          input_mode=chain.input_mode,
          policy_name=policy.name,
          # ← created_at non impostato → rimane None
      )

  state.created_at è None finché apply_event(OPEN_SIGNAL) non viene chiamato. In simulate_chain questo avviene nella stessa iterazione del loop
   — quindi per una chain valida il problema non si presenta mai in produzione.

  ---
  Perché è comunque un problema

  1. I fallback silenziosi producono risultati sbagliati senza alcun segnale

  _replay_market_segment (riga 326–329):
  chain_timeout_at = (
      state.created_at + timedelta(hours=policy.pending.chain_timeout_hours)
      if state.created_at is not None
      else segment_start_bucket          # ← fallback silenzioso
  )
  segment_end = min(chain_timeout_at, metadata.end)

  Se created_at is None: chain_timeout_at = segment_start_bucket = segment_end.
  get_range(symbol, tf, start, start) → lista vuota.
  Il segmento finale non processa nessuna candela. Nessuna eccezione, nessun warning, nessun log.

  2. Tutti i meccanismi di timeout vengono disabilitati in cascata

  # timeout_manager.py
  def check_pending_timeout(state, now, policy, sequence):
      if state.pending_size <= 0 or state.created_at is None:
          return None          # ← silenzioso

  def check_chain_timeout(state, now, policy, sequence):
      if state.created_at is None:
          return None          # ← silenzioso

  # simulator.py _apply_terminal_timeout_if_due:467
  if state.created_at is None:
      return last_replayed_candle_ts   # ← silenzioso

  Se state.created_at fosse None, il trade resterebbe PENDING/ACTIVE con realized_pnl=0.0, verrebbe incluso nei trade_results, e diluerebbe
  tutte le metriche aggregate.

  3. Inconsistenza di tipo tra i modelli

  CanonicalChain.created_at:  datetime        # required, garantito da Pydantic
  TradeState.created_at:      datetime | None # nullable, default None

  Il contratto del dominio garantisce che created_at esiste. Il modello dello stato non lo riflette.

  ---
  Scenario di fallimento reale

  Il validator (validators.py) blocca chain senza OPEN_SIGNAL con GapSeverity.FATAL. Quindi in produzione il branch else segment_start_bucket
  non viene mai raggiunto.

  Ma il problema esiste in questi casi:

  ┌──────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┐
  │                           Caso                           │                              Come si manifesta                              │
  ├──────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Test che chiama simulate_chain direttamente senza runner │ Chain valida ma state.created_at=None se OPEN_SIGNAL manca nel test fixture │
  ├──────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Codice futuro che bypassa il validator                   │ Trade silenziosamente mai chiuso                                            │
  ├──────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Mutation bug che azzera created_at                       │ Tutti i timeout disabilitati, PnL=0 nel report                              │
  ├──────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Chain creata programmaticamente con solo UPDATE events   │ Nessun errore, stato PENDING permanente                                     │
  └──────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────┘

  ---
  Root cause in una frase

  TradeState.created_at è dichiarato datetime | None ma concettualmente è datetime garantito — l'informazione esiste in
  CanonicalChain.created_at fin dall'inizio e non viene copiata.

  ---
  Fix minimale

  Copiare chain.created_at in build_initial_state:

  def build_initial_state(chain: CanonicalChain, policy: PolicyConfig) -> TradeState:
      return TradeState(
          signal_id=chain.signal_id,
          trader_id=chain.trader_id,
          symbol=chain.symbol,
          side=chain.side,
          status=TradeStatus.NEW,
          input_mode=chain.input_mode,
          policy_name=policy.name,
          created_at=chain.created_at,   # ← aggiunta
      )

  Poi rendere non-nullable in TradeState:
  created_at: datetime          # era: datetime | None = None

  Rimuovere tutti i guard if state.created_at is None (ora dead code), trasformando i fallback silenziosi in errori espliciti se mai qualcosa
  va storto.
