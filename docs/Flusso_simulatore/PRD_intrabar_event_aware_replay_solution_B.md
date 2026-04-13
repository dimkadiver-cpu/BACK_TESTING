# PRD — Replay intrabar event-aware per eliminare l’anacronia intra-candela (Soluzione B)

## 1. Scopo del documento

Definire requisiti, architettura, algoritmo, impatti e criteri di accettazione per introdurre nel simulatore un modello di **replay intrabar event-aware**, capace di applicare gli update del trader nel punto corretto dentro la candela, invece che sull’intera candela bucketizzata.

Questo PRD copre la **Soluzione B**:
- uso di un **child timeframe** per spezzare la parent candle contenente un evento;
- replay del mercato **prima** e **dopo** l’evento usando stati diversi;
- eliminazione del bias temporale per update intra-candela;
- mantenimento della natura deterministica e auditabile del simulatore.

---

## 2. Contesto e problema

Nel simulatore attuale il flusso è:

1. applicazione dell’evento al `TradeState`;
2. replay del segmento di mercato fino al prossimo evento.

L’inizio e la fine del segmento vengono allineati al timeframe principale della chain. Questo comporta che, se un update arriva nel mezzo di una candela, la candela che contiene quell’update venga valutata interamente con lo **stato nuovo**.

Esempio:
- timeframe chain = `1h`
- candela = `12:00–13:00`
- update `MOVE_STOP_TO_BE` alle `12:30`
- il motore può valutare l’intera candela `12:00` con stop già spostato a break-even

Questo introduce un’anacronia:
- prezzi avvenuti **prima** dell’evento vengono interpretati con regole valide **dopo** l’evento.

Il problema è particolarmente critico per:
- `MOVE_STOP`
- `MOVE_STOP_TO_BE`
- `CANCEL_PENDING`
- `ADD_ENTRY`
- `CLOSE_PARTIAL`
- `CLOSE_FULL`

L’effetto è un backtest semanticamente scorretto, soprattutto su timeframe ampi (`1h`, `4h`, `1d`) e su chain ricche di update operativi.

---

## 3. Decisione di prodotto

Il progetto adotta la **Soluzione B**:

> Quando un evento cade dentro una parent candle, il replay non deve più trattare quella candela come un blocco indivisibile. Deve invece usare un child timeframe per ricostruire l’ordine temporale tra mercato ed evento.

Semantica target:
- il mercato **prima** del timestamp evento usa lo **stato precedente**;
- l’evento viene applicato al timestamp reale;
- il mercato **dopo** il timestamp evento usa lo **stato aggiornato**.

Questa è la semantica corretta per un simulatore event-driven.

---

## 4. Obiettivi

### 4.1 Obiettivi principali
- Eliminare il bias temporale intra-candela.
- Rendere il simulatore coerente con il timestamp reale degli update.
- Riutilizzare l’infrastruttura intrabar già esistente dove possibile.
- Mantenere il simulatore deterministico, auditabile e ripetibile.
- Ridurre i casi in cui il backtest usa “stato futuro” per leggere “prezzo passato”.

### 4.2 Obiettivi secondari
- Preparare il motore a simulazioni più accurate senza passare a tick data.
- Ridurre falsi break-even, falsi stop, falsi cancel pending e falsi partial close.
- Esporre warning chiari quando i dati intrabar non sono disponibili.

---

## 5. Non obiettivi

Questo PRD **non** copre:
- simulazione tick-by-tick;
- ricostruzione order book;
- partial fill realistici basati su liquidità;
- slippage avanzato dipendente da profondità mercato;
- funding / fee / microstruttura;
- correzione di altri bug del simulatore non legati all’anacronia intra-candela.

---

## 6. Stato attuale rilevante

Il codice attuale dispone già di componenti utili:

1. **Simulator**
   - applica un evento e poi replaya il mercato a segmenti.

2. **MarketDataProvider**
   - supporta `get_range(...)` per il timeframe principale;
   - supporta `get_intrabar_range(...)` per ottenere child candles.

3. **IntrabarResolver**
   - oggi risolve solo collisioni `SL vs TP` dentro una candela;
   - usa child candles per decidere quale trigger arriva prima.

4. **Chain metadata**
   - esiste già il concetto di `intrabar_child_timeframe`.

Quindi la base architetturale per la soluzione esiste già. Manca l’uso dell’intrabar per separare **mercato prima evento** da **mercato dopo evento**.

---

## 7. Problema da risolvere in termini funzionali

### PF-1
Dato un evento con timestamp interno a una parent candle, il simulatore deve distinguere i movimenti di prezzo avvenuti:
- prima dell’evento;
- dopo l’evento.

### PF-2
Gli update del trader non devono più avere effetto retroattivo sull’intera candela bucketizzata.

### PF-3
Il risultato finale deve restare deterministico a parità di:
- DB segnali;
- policy;
- market cache;
- child timeframe.

### PF-4
Quando i child candles non sono disponibili, il sistema non deve fallire silenziosamente: deve usare una policy di fallback esplicita e tracciabile.

---

## 8. Visione della soluzione

La soluzione introduce un nuovo livello di replay:

### 8.1 Parent timeframe
Resta il timeframe logico della chain (`1h`, `4h`, ecc.).
Serve per:
- identificare il contesto della chain;
- leggere i dati principali;
- mantenere compatibilità con il resto del simulatore.

### 8.2 Child timeframe
È un timeframe più fine (`5m`, `1m`, ecc.) usato solo quando necessario.
Serve per:
- spezzare temporalmente la parent candle che contiene uno o più eventi;
- fare replay con ordine corretto mercato/evento/mercato.

### 8.3 Replay event-aware
Quando un evento cade dentro una parent candle:
- si caricano i child candles della parent candle;
- si replayano i child candles precedenti all’evento con stato vecchio;
- si applica l’evento;
- si replayano i child candles successivi con stato nuovo.

---

## 9. Modello concettuale target

### 9.1 Regola base
Per ogni evento `E` con timestamp `tE`:

- il mercato con timestamp `< tE` deve essere valutato prima dell’evento;
- l’evento si applica a `tE`;
- il mercato con timestamp `>= tE` e appartenente alla stessa parent candle deve essere valutato dopo l’evento.

### 9.2 Semantica per child candle
Poiché una child candle è ancora OHLCV aggregata, la granularità non è perfetta. Però il modello è già molto più corretto della parent candle intera.

La regola proposta è:
- se l’evento cade esattamente sul boundary di una child candle, l’evento si considera attivo **da quella child candle in poi**;
- se l’evento cade nel mezzo di una child candle, si considera che:
  - i child candles precedenti siano sicuramente “prima evento”;
  - la child candle contenente l’evento sia **ambigua**.

Per questa child candle ambigua si definisce una policy esplicita, vedi sezione 13.

---

## 10. Architettura proposta

La soluzione introduce i seguenti blocchi logici.

### 10.1 Event-aware segment planner
Responsabilità:
- individuare se il segmento contiene eventi intra-parent-candle;
- determinare quali parent candles richiedono replay intrabar;
- produrre sotto-segmenti ordinati.

Output concettuale:
- `market_before_event`
- `event_application`
- `market_after_event`

### 10.2 Intrabar event replayer
Responsabilità:
- prendere parent candle + child candles + timestamp evento;
- dividere il replay in due fasi;
- applicare la stessa logica di fill / timeout / SL / TP a livello child.

### 10.3 Fallback policy manager
Responsabilità:
- definire cosa fare quando mancano i child candles;
- definire cosa fare quando l’evento cade dentro una child candle non ulteriormente risolvibile.

### 10.4 Audit metadata writer
Responsabilità:
- registrare nei log se è stato usato replay intrabar;
- registrare il child timeframe usato;
- registrare eventuale fallback;
- rendere leggibile la decisione nel report e nell’audit trail.

---

## 11. Strategia di integrazione col codice attuale

### 11.1 Principio
Non riscrivere il simulatore da zero.
Integrare la nuova logica dentro il replay corrente, preservando:
- `simulate_chain(...)`
- `apply_event(...)`
- `TradeState`
- `EventLogEntry`
- `MarketDataProvider`
- `IntrabarResolver` come componente riusabile o estendibile.

### 11.2 Approccio consigliato
Introdurre una nuova funzione, ad esempio concettualmente:

- `_replay_market_segment_event_aware(...)`

oppure:

- `_replay_parent_candle_with_event_boundary(...)`

La logica standard rimane per i casi semplici.
La logica nuova entra solo quando:
- `market_provider` esiste;
- `intrabar_child_timeframe` è configurato;
- almeno un evento cade dentro una parent candle.

### 11.3 Obiettivo di minimizzazione impatto
Evitare di cambiare la state machine.
La correzione deve stare soprattutto nel livello di orchestrazione del replay.

---

## 12. Algoritmo funzionale desiderato

## 12.1 Caso semplice: nessun evento intra-candela
Se gli eventi sono già allineati ai boundary del timeframe:
- usare il replay standard attuale.

## 12.2 Caso target: evento dentro la candela
Per una parent candle `P` e un evento `E` con timestamp interno a `P`:

1. recuperare child candles di `P`;
2. partizionare i child candles in:
   - `children_before`
   - `child_containing_event`
   - `children_after`
3. replayare `children_before` con stato vecchio;
4. gestire il `child_containing_event` secondo policy ambiguità;
5. applicare l’evento;
6. replayare `children_after` con stato nuovo.

### 12.3 Caso con più eventi nella stessa parent candle
Per `E1`, `E2`, `E3` dentro la stessa parent candle:

1. ordinare eventi per `(timestamp, sequence)`;
2. ordinare child candles per timestamp;
3. iterare:
   - replay child candles prima di `E1`;
   - gestire boundary di `E1`;
   - applicare `E1`;
   - replay child candles tra `E1` e `E2`;
   - gestire boundary di `E2`;
   - applicare `E2`;
   - replay child candles tra `E2` e `E3`;
   - ...

Questo mantiene la proprietà deterministica già presente nel motore.

---

## 13. Politica di ambiguità intra-child-candle

Questo è il punto chiave.

Anche col child timeframe, se un evento cade nel mezzo di una child candle, quella child candle resta aggregata. Serve una regola chiara.

### 13.1 Requisito
La policy deve essere:
- esplicita;
- configurabile;
- auditabile;
- deterministica.

### 13.2 Opzioni possibili

#### Modalità A — conservative_pre_event
La child candle contenente l’evento viene valutata interamente **prima** dell’evento.

Interpretazione:
- l’evento ha effetto dalla child candle successiva.

Pro:
- semplice;
- evita look-ahead.

Contro:
- ancora leggermente pessimistica.

#### Modalità B — conservative_post_event
La child candle contenente l’evento viene valutata interamente **dopo** l’evento.

Pro:
- massima reattività.

Contro:
- reintroduce parte del bias originario.

#### Modalità C — skip_ambiguous_child
La child candle contenente l’evento non viene usata per trigger operativi.
L’evento si applica al timestamp, ma SL/TP/fill su quella child candle vengono marcati come ambigui.

Pro:
- molto trasparente.

Contro:
- può lasciare “buchi semantici”.

### 13.3 Decisione consigliata
Per MVP della soluzione B, adottare:

> `conservative_pre_event`

cioè:
- la child candle che contiene l’evento viene interpretata con **stato vecchio**;
- l’evento diventa effettivo dalla child candle successiva.

Motivazione:
- evita look-ahead;
- elimina il problema grosso della parent candle intera;
- è coerente con un principio conservativo;
- è facile da spiegare e auditare.

### 13.4 Evoluzione futura
In una fase successiva si potrà aggiungere:
- modalità configurabili;
- eventuale split sintetico della child candle se si dispone di timeframe ancora più fine.

---

## 14. Requisiti funzionali

### RF-1 — Supporto replay intrabar event-aware
Il simulatore deve supportare replay del mercato a child timeframe per le parent candles che contengono eventi intra-candela.

### RF-2 — Applicazione corretta ordine temporale
Per gli eventi intra-candela il replay deve rispettare l’ordine:
- mercato precedente;
- evento;
- mercato successivo.

### RF-3 — Supporto multi-evento nella stessa parent candle
Il sistema deve gestire più eventi ordinati per `(timestamp, sequence)` nella stessa parent candle.

### RF-4 — Riutilizzo della logica di trigger
La logica di:
- fill entry;
- timeout;
- collisioni SL/TP;
- post-TP actions

must be reusable anche a livello child candle, evitando duplicazione incontrollata.

### RF-5 — Configurazione child timeframe
Ogni chain o scenario deve poter indicare un `intrabar_child_timeframe` valido.

### RF-6 — Fallback esplicito
Se il child timeframe non è disponibile, il sistema deve:
- usare fallback esplicito;
- registrare warning;
- non degradare silenziosamente senza audit trail.

### RF-7 — Audit trail esteso
Ogni decisione intrabar deve poter essere ricostruita dai log.

### RF-8 — Compatibilità con simulator attuale
Se la funzione intrabar event-aware è disabilitata o non configurata, il simulatore deve poter continuare a usare il comportamento legacy.

---

## 15. Requisiti non funzionali

### RNF-1 — Determinismo
A parità di input e market data, il risultato deve essere identico ad ogni esecuzione.

### RNF-2 — Trasparenza
Ogni fallback o decisione ambigua deve essere tracciabile.

### RNF-3 — Compatibilità retroattiva
La modifica non deve rompere il flusso standard di simulazione per dataset e report esistenti.

### RNF-4 — Performance controllata
L’uso del child timeframe deve avvenire solo dove necessario, non su tutto il dataset indiscriminatamente.

### RNF-5 — Estendibilità
La soluzione deve preparare eventuali evoluzioni future:
- child timeframe dinamico;
- policy di ambiguità multiple;
- analisi di sensibilità.

---

## 16. Configurazione proposta

### 16.1 Config flags minime
Aggiungere configurazioni esplicite, ad esempio concettualmente:

```yaml
intrabar:
  event_aware_replay_enabled: true
  child_timeframe: 5m
  same_child_event_policy: conservative_pre_event
  fallback_mode: warn_and_use_parent_logic
```

### 16.2 Semantica
- `event_aware_replay_enabled`
  - abilita la nuova logica.

- `child_timeframe`
  - timeframe inferiore usato per parent candles con eventi intra-candela.

- `same_child_event_policy`
  - regola per la child candle che contiene l’evento.

- `fallback_mode`
  - comportamento quando i child candles non sono disponibili.

### 16.3 Compatibilità
Se esiste già `chain.metadata.intrabar_child_timeframe`, la policy deve poterlo:
- usare come override per-chain;
- oppure derivare da config scenario/policy.

---

## 17. Fallback e degradazione controllata

### 17.1 Caso: child timeframe non configurato
Comportamento:
- usare replay standard parent candle;
- emettere warning tecnico;
- incrementare un contatore warning sulla chain.

### 17.2 Caso: child candles mancanti o incompleti
Comportamento:
- usare fallback configurato;
- segnare che la chain è stata simulata con precisione ridotta.

### 17.3 Caso: evento dentro child candle ambigua
Comportamento default:
- `conservative_pre_event`
- loggare motivo e candle coinvolta.

### 17.4 Divieto di fallback silenzioso
In nessun caso il sistema deve degradare senza:
- warning;
- metadata;
- traccia nei log.

---

## 18. Impatti sui componenti

### 18.1 engine/simulator.py
Impatto alto.
Da modificare per:
- introdurre segmentazione event-aware;
- distinguere replay parent standard da replay intrabar;
- gestire più eventi dentro la stessa parent candle.

### 18.2 market/data_models.py e provider concreti
Impatto medio.
Necessario verificare che i provider:
- restituiscano child candles in modo affidabile;
- coprano esattamente la parent candle richiesta;
- mantengano timestamp coerenti.

### 18.3 market/intrabar_resolver.py
Impatto medio.
Possibili opzioni:
- riuso parziale dell’attuale resolver;
- estensione per supportare `event boundary resolution`;
- separazione tra:
  - `SL/TP collision resolver`
  - `event boundary replay helper`

### 18.4 report / audit trail
Impatto medio.
I report dovrebbero poter mostrare:
- se il replay intrabar è stato usato;
- child timeframe;
- fallback usati;
- numero di eventi intra-candela risolti.

---

## 19. Metadata e audit trail richiesti

Per ogni chain andrebbero esposti campi come:

- `intrabar_event_aware_used: bool`
- `intrabar_child_timeframe_used: str | null`
- `intrabar_event_boundaries_count: int`
- `intrabar_ambiguous_boundaries_count: int`
- `intrabar_fallbacks_used: int`
- `intrabar_fallback_reasons: list[str]`

Per ogni evento o log entry rilevante:
- `boundary_resolution_mode`
- `parent_candle_ts`
- `child_candle_ts`
- `applied_before_or_after_event`
- `fallback_used`

Obiettivo: rendere la simulazione spiegabile in fase di debug e nei report HTML.

---

## 20. Algoritmo tecnico ad alto livello

### 20.1 Pseudoflusso

1. ordinare eventi per `(timestamp, sequence)`;
2. iterare sui segmenti temporali;
3. per ciascuna parent candle:
   - se non contiene boundary evento, replay standard;
   - se contiene boundary evento, replay intrabar;
4. nel replay intrabar:
   - caricare child candles;
   - trovare child candles prima/dopo ciascun evento;
   - replay mercato prima evento;
   - applicare evento;
   - replay mercato dopo evento;
5. per ogni child candle, riutilizzare la logica esistente di:
   - fill;
   - timeout;
   - SL/TP;
   - post-TP engine actions.

### 20.2 Invariante da mantenere
Non deve mai accadere che una child candle precedente all’evento venga valutata con stato successivo all’evento.

---

## 21. Strategia di implementazione consigliata

### Fase 1 — Refactor di appoggio
Obiettivo:
- estrarre la logica di replay per singola candle in una funzione riusabile.

Esempio concettuale:
- `_process_market_candle(...)`
- `_process_market_child_candle(...)`

Serve per evitare duplicazione tra replay standard e replay intrabar.

### Fase 2 — Supporto event-aware su una sola parent candle
Obiettivo:
- implementare replay corretto di una parent candle con un solo evento interno.

### Fase 3 — Supporto multi-evento nella stessa parent candle
Obiettivo:
- gestire n eventi ordinati nella stessa parent candle.

### Fase 4 — Audit e reporting
Obiettivo:
- esporre metadata e warning in report / output scenario.

### Fase 5 — Hardening
Obiettivo:
- benchmark prestazioni;
- casi limite;
- retrocompatibilità.

---

## 22. Test richiesti

### 22.1 Test unitari minimi

#### TU-1 — Move stop intra-candela
Scenario:
- parent `1h`
- child `5m`
- stop aggiornato a metà parent candle

Atteso:
- i child candles precedenti usano vecchio stop;
- i successivi usano nuovo stop.

#### TU-2 — Cancel pending intra-candela
Atteso:
- fill prima dell’evento ancora possibili;
- fill dopo evento non più possibili.

#### TU-3 — Add entry intra-candela
Atteso:
- nuova entry attiva solo dopo il boundary evento.

#### TU-4 — Close partial intra-candela
Atteso:
- il close non influisce retroattivamente sui child candles precedenti.

#### TU-5 — Più eventi nella stessa parent candle
Atteso:
- ordine deterministico secondo `(timestamp, sequence)`.

#### TU-6 — Evento dentro child candle ambigua
Atteso:
- applicazione della policy `conservative_pre_event`.

#### TU-7 — Child timeframe non disponibile
Atteso:
- fallback esplicito;
- warning;
- nessun crash.

### 22.2 Test di regressione

#### TR-1
Chain senza eventi intra-candela devono produrre risultati invariati rispetto a prima.

#### TR-2
Chain con eventi esattamente sul boundary della candela devono produrre comportamento coerente e stabile.

#### TR-3
La presenza della nuova feature disabilitata non deve alterare il comportamento legacy.

### 22.3 Test end-to-end
Usare fixture dedicate con:
- stessa chain simulata in modalità legacy;
- stessa chain simulata in modalità event-aware;
- confronto di log e PnL.

---

## 23. Criteri di accettazione

### CA-1
Un update intra-parent-candle non deve più influenzare retroattivamente il mercato precedente al suo timestamp.

### CA-2
Il simulatore deve usare il child timeframe solo sulle parent candles che lo richiedono.

### CA-3
Più eventi nella stessa parent candle devono essere gestiti correttamente e in modo deterministico.

### CA-4
La child candle contenente l’evento deve seguire una policy configurata e visibile nei log.

### CA-5
In assenza di child candles, il sistema deve degradare con warning esplicito e audit trail.

### CA-6
Le chain senza eventi intra-candela non devono subire regressioni di risultato.

### CA-7
I report e/o gli output di debug devono rendere visibile se è stato usato il replay intrabar event-aware.

---

## 24. Rischi principali

### R-1 — Complessità del replay
Il codice del simulator può diventare più complesso e difficile da mantenere.

Mitigazione:
- estrarre funzioni riusabili;
- separare chiaramente replay standard e replay intrabar.

### R-2 — Performance
Su dataset grandi, il child timeframe può aumentare molto il numero di candles processate.

Mitigazione:
- usare intrabar solo dove necessario;
- evitare replay child globale.

### R-3 — Ambiguità residua
Anche il child timeframe non elimina tutta l’ambiguità se l’evento cade nel mezzo della child candle.

Mitigazione:
- policy esplicita;
- warning e metadata.

### R-4 — Dati child mancanti
Il market store può non avere copertura child sufficiente.

Mitigazione:
- integrazione con planner/sync market data;
- fallback controllato.

---

## 25. Impatto sul sottosistema market data

La soluzione B richiede che il market layer possa fornire, quando necessario:
- parent candles;
- child candles coerenti nello stesso intervallo temporale.

Conseguenze operative:
- il planner/sync dati deve considerare anche il child timeframe per i periodi rilevanti;
- la cache deve poter coprire timeframe multipli oppure derivare il parent da un base timeframe fine;
- la validazione dati deve verificare anche la coerenza parent/child quando la feature è attiva.

Questo punto collega direttamente il PRD attuale al PRD sul market data incrementale.

---

## 26. Impatto sui report e sulla UX di analisi

Nei report di policy e trade detail è utile aggiungere indicatori come:
- `Intrabar event-aware replay: ON/OFF`
- `Child timeframe used: 5m`
- `Event boundaries resolved: N`
- `Fallbacks used: N`
- `Ambiguous same-child boundaries: N`

Nel single trade report, idealmente, la timeline eventi dovrebbe poter segnalare:
- update intra-candela;
- modalità con cui è stato applicato;
- eventuali warning di precisione ridotta.

---

## 27. Decisioni tecniche consigliate

### DT-1
Non modificare la state machine come sede principale della correzione.

### DT-2
Centralizzare la correzione nel livello di replay/orchestrazione del mercato.

### DT-3
Riutilizzare il più possibile la logica già esistente per fill/timeout/collisioni.

### DT-4
Adottare come default `same_child_event_policy = conservative_pre_event`.

### DT-5
Introdurre metadata e warning come parte integrante della feature, non come extra futuro.

---

## 28. Priorità di rilascio

### Release 1 — MVP corretto
- replay intrabar event-aware per singolo evento dentro parent candle;
- policy `conservative_pre_event`;
- fallback espliciti;
- audit metadata base.

### Release 2 — Multi-evento robusto
- supporto n eventi nella stessa parent candle;
- reportistica migliorata;
- test di regressione completi.

### Release 3 — Evoluzione
- modalità alternative per child candle ambigua;
- analisi sensibilità;
- possibile ottimizzazione performance.

---

## 29. Definizione di completamento

La soluzione B sarà considerata completata quando:
- il simulatore non applicherà più update intra-candela in modo retroattivo sulla parent candle intera;
- il replay userà child candles per rispettare il vero ordine temporale mercato/evento;
- i fallback saranno espliciti e auditabili;
- il comportamento sarà stabile, deterministico e testato.

---

## 30. Prossimo artefatto consigliato

Dopo approvazione di questo PRD, il documento successivo consigliato è un:

**Technical Blueprint / Implementation Plan**

contenente:
- funzioni da introdurre o rifattorizzare;
- patch plan per `simulator.py`;
- schema dei nuovi metadata;
- piano test step-by-step;
- prompt operativo per Codex.
