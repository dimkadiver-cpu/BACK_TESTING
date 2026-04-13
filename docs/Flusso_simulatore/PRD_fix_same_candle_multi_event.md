# PRD — Fix simulatore per gestione multi-evento nella stessa candela

- **Progetto:** BACK_TESTING
- **Documento:** PRD_fix_same_candle_multi_event.md
- **Data:** 2026-04-13
- **Stato:** Proposta tecnica pronta per implementazione
- **Priorità:** Alta
- **Area:** `src/signal_chain_lab/engine/simulator.py`

---

## 1. Contesto

Nel simulatore del progetto `BACK_TESTING`, il motore replay di mercato processa le candele per aggiornare lo stato di una `TradeState` a partire da una `CanonicalChain` e da una `PolicyConfig`.

La struttura attuale del simulatore è coerente con il design generale del progetto:

- gli eventi della chain vengono ordinati per `(timestamp, sequence)`;
- il replay di mercato avviene tra un evento e il successivo;
- il simulatore usa detection di collisione SL/TP, risoluzione intrabar e applicazione degli eventi engine;
- dopo un TP parziale, possono essere applicate azioni post-TP come spostamento SL a break-even o cancellazione di entry pending.

Nel codice attuale sono già presenti i componenti chiave necessari:

- `_detect_sl_tp_collision(...)`
- `_resolve_collision(...)`
- `_apply_close_resolution(...)`
- `_handle_post_tp_partial_actions(...)`
- `TradeState` con campi come `open_size`, `pending_size`, `current_sl`, `tp_levels`, `next_tp_index`, `avg_entry_price`, `status`, `fills`.

---

## 2. Problema

### 2.1 Descrizione semplice

Il simulatore oggi gestisce **al massimo una collisione significativa per candela**.

In pratica:

1. controlla se nella candela corrente viene colpito SL o TP corrente;
2. applica la risoluzione trovata;
3. aggiorna lo stato del trade;
4. passa alla candela successiva.

Questo è scorretto quando **la stessa candela** contiene più eventi economicamente rilevanti, per esempio:

- TP1 e TP2 nella stessa candela;
- TP1 e, dopo spostamento dello SL a break-even, hit del nuovo SL nella stessa candela;
- TP parziale seguito da un secondo TP o da SL nella stessa candela;
- sequenze analoghe su posizioni short.

### 2.2 Radice del problema

L’architettura attuale del replay è di fatto **one-event-per-candle**.

Manca un ciclo interno che, dopo ogni modifica di stato su una candela, ri-esamini **la stessa candela** per verificare se esistono ulteriori collisioni ancora valide sul nuovo stato aggiornato.
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

---

## 3. Impatto

### 3.1 Impatto funzionale

Il bug può produrre risultati errati nei seguenti casi:

1. **Multi-TP sulla stessa candela**  
   Il simulatore chiude solo il primo TP e rimanda gli altri a candele successive, anche se il prezzo li aveva già raggiunti.

2. **Break-even post-TP non rivalutato sulla stessa candela**  
   Dopo TP1 il simulatore può spostare `current_sl` a `avg_entry_price`, ma non verifica di nuovo se quel nuovo SL era già stato colpito nella stessa candela.

3. **Sequenza intrabar incompleta dopo un partial close**  
   Se una candela include sia TP che SL, la logica attuale può risolvere il primo passaggio ma non rivalutare gli effetti della nuova configurazione del trade.

### 3.2 Impatto economico / analitico

Il bug altera la qualità del backtest e dei report:

- `realized_pnl` può risultare gonfiato o distorto;
- `close_reason` può essere scorretto;
- `fills_count` può essere incompleto;
- metriche come `MAE`, `MFE`, expectancy, win rate, profit factor e drawdown possono risultare meno affidabili;
- i report di policy e di singolo trade possono mostrare una storia operativa non coerente con la candela realmente percorsa dal prezzo.

### 3.3 Gravità

La gravità è **alta**, perché il bug colpisce direttamente la credibilità del motore di simulazione sui trade con:

- partial take profit;
- break-even automatico;
- più livelli TP;
- collisioni intrabar nella stessa candela.

---

## 4. Obiettivo

Introdurre nel replay di mercato una gestione corretta dei **multi-eventi sulla stessa candela**, in modo che il simulatore continui a rivalutare la candela corrente fino a quando:

- non esistono più collisioni valide sullo stato aggiornato;
- oppure il trade raggiunge uno stato terminale;
- oppure non esiste più posizione aperta da gestire.

---

## 5. Obiettivi specifici

1. Consentire la chiusura di più TP nella stessa candela quando il range della candela li attraversa realmente.
2. Consentire il rilevamento del nuovo SL aggiornato nella stessa candela dopo azioni post-TP.
3. Evitare di rinviare a candele successive eventi che appartengono logicamente alla candela corrente.
4. Mantenere il comportamento deterministico del simulatore.
5. Evitare loop infiniti o doppie esecuzioni spurie.
6. Minimizzare l’impatto architetturale sul resto del motore.

---

## 6. Non-obiettivi

Questo fix **non** introduce:

- orderbook-level realism;
- simulazione tick-by-tick;
- nuovo modello di fill parziale;
- nuovo modello di spread;
- nuova logica di intrabar beyond current resolver design;
- trailing stop avanzato non già previsto dalle policy.

Il fix deve restare coerente con l’architettura attuale candle-based + intrabar resolver già presente.

---

## 7. Stato attuale sintetico

### 7.1 Comportamento attuale

Per ogni candela, il motore oggi esegue sostanzialmente questa sequenza:

1. prova il fill di eventuali entry pending;
2. controlla timeout pending e timeout chain;
3. controlla una collisione SL/TP sullo stato corrente;
4. risolve la collisione;
5. applica la chiusura;
6. genera l’evento engine;
7. esegue eventuali azioni post-TP;
8. passa alla candela successiva.

### 7.2 Limite attuale

Dopo il punto 7 il simulatore **non rientra** su un nuovo controllo collisione della stessa candela.

---

## 8. Soluzione proposta

### 8.1 Idea base

Sostituire la logica attuale “una collisione per candela” con una logica **drain same-candle**:

> per ogni candela, dopo ogni modifica di stato che può cambiare il prossimo TP, lo SL corrente o la size aperta, il simulatore deve rivalutare la stessa candela finché non ci sono più collisioni valide.

### 8.2 Approccio architetturale

Dentro `_replay_market_segment(...)`, per ogni candela:

1. eseguire le operazioni pre-collisione come oggi;
2. introdurre un **inner loop** di rivalutazione sulla stessa candela;
3. uscire dal loop solo quando la candela è stata completamente “consumata” dal punto di vista logico.

### 8.3 Pseudoflusso proposto

```python
for candle in candles:
    _try_fill_pending_entries(...)

    check_pending_timeout(...)
    check_chain_timeout(...)

    while True:
        if state.status in TERMINAL_STATUSES:
            break

        if state.open_size <= 0:
            break

        collision = _detect_sl_tp_collision(state, candle)
        if collision is None:
            break

        resolution = _resolve_collision(...)

        tp_idx_before = state.next_tp_index
        open_size_before = state.open_size
        sl_before = state.current_sl
        status_before = state.status

        _apply_close_resolution(state, resolution)
        logs.append(apply_event(state, engine_event, policy=policy))

        if resolution.outcome == "tp_hit" and state.open_size > 0 and state.status not in TERMINAL_STATUSES:
            _handle_post_tp_partial_actions(..., tp_idx_hit=tp_idx_before)

        if state.status in TERMINAL_STATUSES:
            break

        if state.open_size <= 0:
            break

        progressed = (
            state.next_tp_index != tp_idx_before
            or state.open_size != open_size_before
            or state.current_sl != sl_before
            or state.status != status_before
        )

        if not progressed:
            raise SimulationInvariantError(...)

    last_replayed_candle_ts = candle.timestamp
```

---

## 9. Requisiti funzionali

### RF-1 — Gestione multi-TP sulla stessa candela

Se una candela attraversa più livelli TP in ordine coerente con il side della posizione, il simulatore deve poter processare più TP nella stessa candela fino a esaurimento dei livelli colpiti o chiusura della posizione.

### RF-2 — Rivalutazione dello SL aggiornato sulla stessa candela

Se dopo un TP parziale una regola post-TP aggiorna `current_sl`, il simulatore deve ricontrollare la stessa candela usando il nuovo valore di SL.

### RF-3 — Supporto simmetrico LONG / SHORT

La logica deve funzionare in modo simmetrico per posizioni LONG e SHORT.

### RF-4 — Mantenimento del comportamento terminale

Se durante la candela il trade diventa `CLOSED`, `CANCELLED`, `EXPIRED` o `INVALID`, il loop interno deve terminare immediatamente.

### RF-5 — Nessuna duplicazione artificiale di eventi

Il simulatore non deve generare due volte lo stesso evento logico se lo stato non è realmente avanzato.

### RF-6 — Determinismo invariato

A parità di input chain, policy, market data e resolver intrabar, il risultato deve restare deterministico.

---

## 10. Requisiti tecnici

### RT-1 — Modifica localizzata

La modifica deve essere concentrata principalmente in `src/signal_chain_lab/engine/simulator.py`, senza ridisegnare l’intera architettura del progetto.

### RT-2 — Riutilizzo dei componenti esistenti

La soluzione deve riutilizzare i componenti già presenti:

- `_detect_sl_tp_collision(...)`
- `_resolve_collision(...)`
- `_apply_close_resolution(...)`
- `_handle_post_tp_partial_actions(...)`
- `apply_event(...)`

### RT-3 — Garanzia di terminazione

Il loop interno deve avere una chiara garanzia di terminazione. A ogni iterazione deve avvenire almeno uno tra:

- riduzione di `open_size`;
- incremento di `next_tp_index`;
- cambiamento di `current_sl`;
- passaggio a stato terminale.

Se nessuna di queste condizioni avviene, il codice deve:

- loggare un errore di invariance;
- interrompere l’elaborazione della candela in modo controllato oppure sollevare un’eccezione interna dedicata in ambiente di test/debug.

### RT-4 — Sequencing coerente degli engine event

Gli engine event generati durante la stessa candela devono mantenere un ordine consistente e tracciabile nei log.

### RT-5 — Compatibilità con `last_replayed_candle_ts`

L’aggiornamento di `last_replayed_candle_ts` deve avvenire una sola volta per candela, al termine del drain della candela stessa.

---

## 11. Invarianti richieste

Il nuovo loop deve rispettare queste invarianti:

1. **Nessuna collisione su stato terminale**  
   Se `state.status` è terminale, `_detect_sl_tp_collision(...)` non deve più produrre collisioni.

2. **Nessuna collisione senza posizione aperta**  
   Se `state.open_size <= 0`, la candela non deve essere rivalutata per SL/TP.

3. **Monotonicità TP**  
   `next_tp_index` non deve mai diminuire.

4. **Monotonicità consumo posizione**  
   `open_size` non deve aumentare durante la gestione delle collisioni di chiusura.

5. **No silent no-op**  
   Ogni iterazione del loop interno deve produrre progresso osservabile oppure fallire in modo esplicito.

---

## 12. Casi d’uso principali da coprire

### Caso A — Multi-TP stessa candela

- LONG con TP1, TP2, TP3;
- una sola candela raggiunge TP1, TP2 e TP3;
- atteso: chiusure successive sulla stessa candela fino a esaurimento size o livelli.

### Caso B — TP1 + break-even + SL stesso candle

- LONG con `be_trigger = tp1`;
- la candela tocca TP1 e successivamente torna sotto `avg_entry_price`;
- atteso: chiusura parziale a TP1 e chiusura residua a BE nella stessa candela.

### Caso C — SHORT simmetrico

- SHORT con TP1/TP2 e SL;
- candela che percorre prima area TP e poi area SL oppure viceversa;
- atteso: comportamento coerente con resolver intrabar e nuovo loop same-candle.

### Caso D — TP finale sulla stessa candela

- dopo TP1 parziale, la stessa candela raggiunge anche TP finale;
- atteso: chiusura completa nella stessa candela.

### Caso E — Nessuna progressione

- scenario patologico in cui la collisione viene rilevata ma l’applicazione non modifica lo stato;
- atteso: errore di invariance o uscita protetta, non loop infinito.

---

## 13. Strategia di implementazione

### Step 1 — Refactor minimo del blocco collisione

Isolare il blocco di gestione collisione in una routine interna leggibile, senza cambiare comportamento esterno.

### Step 2 — Introduzione inner loop

Inserire un ciclo `while` per rivalutare la stessa candela fino a esaurimento collisioni.

### Step 3 — Progress guard

Aggiungere una guardia esplicita di progresso per evitare loop infiniti.

### Step 4 — Test di regressione

Aggiungere test dedicati per multi-TP, BE same-candle, short symmetry, e guardia no-progress.

### Step 5 — Validazione reportistica

Verificare che `TradeResult`, `EventLogEntry` e report HTML/CSV riflettano la nuova sequenza eventi corretta.

---

## 14. Test plan richiesto

### 14.1 Unit test

1. `_detect_sl_tp_collision(...)` su stato aggiornato nella stessa candela.
2. `_handle_post_tp_partial_actions(...)` con trigger BE su TP1.
3. guardia di progresso quando non cambia nessuna variabile chiave.

### 14.2 Integration test simulator

1. **LONG / multi-TP same candle**
2. **LONG / TP1 + BE + SL same candle**
3. **SHORT / TP + SL same candle**
4. **final TP same candle after partial**
5. **nessun loop infinito**

### 14.3 Regression test report

Verificare che i report mostrino:

- `close_reason` coerente;
- timeline eventi coerente;
- PnL finale coerente con la nuova sequenza;
- eventuale numero di fill / close aggiornato correttamente.

---

## 15. Criteri di accettazione

Il fix sarà considerato accettato quando saranno verificati tutti i seguenti punti:

1. una candela che attraversa più TP produce più chiusure coerenti nella stessa candela;
2. un nuovo SL impostato dopo TP viene rivalutato subito sulla stessa candela;
3. non si osservano loop infiniti;
4. il comportamento LONG e SHORT è simmetrico;
5. i log eventi restano ordinati e leggibili;
6. il simulatore resta deterministico;
7. i test di regressione dedicati passano.

---

## 16. Rischi e attenzioni

### Rischio 1 — Doppio conteggio eventi

Se il loop non separa bene “collisione già consumata” da “collisione nuova”, si rischia di duplicare close o log.

**Mitigazione:** progress guard + controllo rigoroso di `next_tp_index`, `open_size`, `status`.

### Rischio 2 — Sequencing ambiguo di eventi same-candle

Più eventi engine sulla stessa candela potrebbero rendere meno chiaro il sequencing nei log.

**Mitigazione:** mantenere sequencing derivato da `sequence_seed` con offset coerente o meccanismo equivalente stabile.

### Rischio 3 — Bug nascosti nei report

Il report single trade potrebbe non aspettarsi più chiusure nella stessa candela.

**Mitigazione:** regression test su rendering timeline e dettaglio trade.

### Rischio 4 — Assunzioni implicite nei test vecchi

Test esistenti potrebbero incorporare il comportamento errato attuale come baseline implicita.

**Mitigazione:** aggiornare solo i test che formalizzano il bug, mantenendo invariati gli altri scenari.

---

## 17. Decisione progettuale proposta

Si propone di implementare il fix come:

- **modifica core del simulatore**, non feature flag;
- **refactor minimo**, non redesign completo;
- **comportamento corretto by default**, perché il comportamento attuale è logicamente errato e impatta l’affidabilità del backtest.

---

## 18. Deliverable attesi

1. patch su `simulator.py`;
2. eventuale eccezione/guard interna per no-progress;
3. test unit + integration;
4. aggiornamento eventuale della documentazione tecnica del simulatore;
5. verifica report policy e single trade su fixture dedicate.

---

## 19. Sintesi finale

Il problema non è un dettaglio minore di UX del report, ma un difetto strutturale del replay di mercato: la stessa candela può contenere più eventi economicamente rilevanti, mentre il simulatore oggi ne consuma uno solo.

Il fix corretto è introdurre una logica di **rivalutazione iterativa della stessa candela** fino a esaurimento delle collisioni valide sullo stato aggiornato.

Questa modifica è localizzabile, compatibile con l’architettura attuale e necessaria per rendere più affidabili PnL, close_reason, timeline e metriche aggregate del backtest.
