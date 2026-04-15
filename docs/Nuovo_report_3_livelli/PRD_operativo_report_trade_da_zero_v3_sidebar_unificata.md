# PRD operativo — Generatore report HTML di singolo trade da zero

## 1. Missione

Devi sviluppare **da zero** un generatore che produca un **report HTML di singolo trade**, offline-friendly, con approccio **chart-centric**.

Il risultato finale deve permettere a un utente di:

1. capire rapidamente come è andato il trade;
2. vedere il comportamento del prezzo rispetto a entry, stop, take profit ed eventi;
3. leggere in modo chiaro le decisioni di gestione del trade;
4. distinguere la vista operativa principale dalla vista audit/debug.

Questo documento è una **istruzione di implementazione**. Non è un documento descrittivo del prodotto: è la specifica che devi seguire per costruire il report.

---

## 2. Obiettivo concreto

Il sistema deve prendere in input i dati di un singolo trade e generare un report HTML completo composto da:

- grafico principale del trade;
- eventi rappresentati sul grafico e su event rail opzionale;
- sidebar con **lista eventi operativi unificata**;
- audit/debug separato e collassato di default.

La vista principale deve essere dominata dal **grafico**.  
La sidebar non deve contenere due blocchi distinti per `Selected event summary` e `Operational timeline`: deve invece contenere **un unico elenco eventi**, collassato di default, espandibile item per item, che svolge entrambe le funzioni.

---

## 3. Vincoli non negoziabili

Devi rispettare tutti questi vincoli:

1. **Il report deve funzionare offline**.
2. **Non usare CDN** nel prodotto finale.
3. **Non inventare dati mancanti**.
4. **Non falsare marker prezzo o livelli** quando il dato non esiste.
5. **Chart, rail, lista eventi sidebar e audit devono usare lo stesso modello canonico di evento**.
6. **I livelli devono essere segmenti temporali**, non linee statiche finali.
7. **La vista principale deve restare leggibile durante zoom e pan**.
8. **Audit/debug deve essere separato dalla lettura principale**.
9. **Il grafico deve essere la parte narrativa principale del trade**.
10. **Il report va costruito da zero**, senza riusare pattern del vecchio report che confliggono con questi requisiti.

---

## 4. Non devi fare

Non devi:

- riscrivere il motore di simulazione;
- cambiare la logica core del backtest;
- ridefinire PnL o metriche del simulatore;
- trasformare il report in dashboard multi-trade;
- trattare la timeline principale come dump del log tecnico;
- mischiare audit e lettura operativa principale.

---

## 7. Layout finale obbligatorio

Il report HTML deve avere questa struttura:

```text
Single Trade Report
├─ Hero compact
├─ Main analysis block
│  ├─ Price chart
│  ├─ Optional event rail
│  └─ Side panel
│      └─ Unified operational events list
└─ Audit drawer (collapsed by default)
```

### Note

- la lista eventi operativi deve stare nella sidebar, non come sezione sotto al grafico;
- la lista eventi unificata sostituisce sia `Selected event summary` sia `Operational timeline`;
- tra il blocco principale e l’audit deve essere presente un navigation menu che permetta di navigare tra i vari trade senza tornare alla pagina del report policy;
- sotto al blocco principale deve restare solo l’audit;
- audit deve essere separato e secondario.

---

## 9. Hero compact

Il blocco iniziale deve essere molto compatto e contenere solo dati essenziali.

### Campi obbligatori

- `symbol / side / status`
- `return % net`
- `return % gross`
- `costs total %`
- `fees total %`
- `funding net %`
- `R multiple`
- `MAE %`
- `MFE %`
- `duration`
- `warnings` solo se presenti

### Regole

- non inserire dati raw superflui;
- non mettere in hero dettagli tipo first fill / final exit / avg entry;
- il layout deve restare leggibile anche in viewport ridotti.

---

## 10. Blocco principale di analisi

## 10.1 Price chart

Il grafico è il componente dominante del report.

### Deve visualizzare

- candele OHLC;
- livelli operativi come segmenti temporali;
- eventi con price impact;
- volume opzionale;
- event rail opzionale;
- tooltip;
- zoom e pan;
- allineamento temporale coerente tra chart, rail e volume.

### Requisiti critici

- il tempo delle candele deve usare il timestamp dichiarato dai dati, non reinterpretazioni dipendenti dal browser;
- i componenti temporali allineati devono condividere la stessa coordinata X;
- durante zoom/pan non devono comparire disallineamenti tra prezzo, rail, volume e livelli.

---

## 10.2 Side panel

Il side panel deve contenere solo:

1. `Unified operational events list`

### Regole

- nessun blocco KPI pesante;
- nessuna duplicazione inutile dell’hero;
- la lista eventi unificata deve sostituire sia il vecchio `Selected event summary` sia la vecchia `Operational timeline`;
- cliccando un evento sul chart o sulla rail, il relativo item nella lista deve essere evidenziato e poter essere aperto;
- cliccando un item nella lista, l’evento corrispondente deve essere evidenziato sul chart o sulla rail;
- non deve esistere una timeline operativa separata sotto il grafico.

---

## 11. Toggle obbligatori

Sulla stessa riga della selezione timeframe (dal piu basso al piu alto) devono esistere solo questi toggle principali:

- `Volume`
- `Event rail`
---

## 12. Legend obbligatoria

Sotto la riga dei toggle deve esserci una `Legend`.

La legend deve svolgere una doppia funzione:

1. spiegare il significato visivo di livelli ed eventi;
2. permettere di attivare/disattivare la visualizzazione delle categorie sul chart.

### Esempi attesi

- linea TP con label visiva coerente;
- linea Entry;
- marker TP hit;
- marker stop hit;
- marker entry fill;
- marker final exit.

La legenda deve essere leggibile, non tagliata, coerente coi colori e forme reali usati sul grafico.

---

## 13. Event rail opzionale

La event rail è un componente separato, attivabile via toggle (attivo di default).

### Requisiti obbligatori

- deve poter essere nascosta;
- deve seguire lo stesso asse temporale del grafico;
- deve aggiornarsi con zoom e pan;
- deve distribuire gli eventi in lane separate per ridurre collisioni;
- deve usare simboli coerenti per categoria.

### Eventi tipicamente da mettere sulla rail

- `SL_MOVED`
- `BE_ACTIVATED`
- `CANCELLED`
- `EXPIRED`
- `TIMEOUT`
- `SYSTEM_NOTE`
- eventi di gestione o sistema non direttamente eseguiti a prezzo

---

## 14. Modello canonico degli eventi

Tutti i componenti UI devono leggere lo stesso modello evento canonico.

### Schema minimo richiesto

```json
{
  "id": "string",
  "ts": "ISO datetime",
  "phase": "SETUP | ENTRY | MANAGEMENT | EXIT | POST_MORTEM",
  "class": "STRUCTURAL | MANAGEMENT | RESULT | AUDIT",
  "subtype": "string",
  "title": "string",
  "price_anchor": 0.0,
  "source": "TRADER | ENGINE | SYSTEM",
  "impact": {
    "position": "optional",
    "risk": "optional",
    "result": "optional"
  },
  "summary": "string",
  "raw_text": "optional",
  "details": {}
}
```

### Regola fondamentale

Non sono ammesse versioni diverse dello stesso evento tra chart, rail, lista eventi sidebar e audit.

---

## 15. Tassonomia minima degli eventi

Il normalizzatore deve supportare almeno questi subtype canonici:

- `SIGNAL_CREATED`
- `ENTRY_PLANNED`
- `ENTRY_FILLED`
- `SCALE_IN_FILLED`
- `MARKET_ENTRY_FILLED`
- `SL_SET`
- `SL_MOVED`
- `BE_ACTIVATED`
- `TP_ARMED`
- `TP_HIT`
- `PARTIAL_EXIT`
- `FINAL_EXIT`
- `SL_HIT`
- `CANCELLED`
- `EXPIRED`
- `TIMEOUT`
- `IGNORED`
- `SYSTEM_NOTE`

Puoi aggiungere subtype extra, ma questi non possono mancare.

---

## 16. Regole obbligatorie per i livelli

Tutti i livelli devono essere rappresentati come **segmenti temporali reali**.

### Regola generale

Ogni segmento:

- inizia nel momento in cui il livello diventa valido;
- termina quando viene colpito, sostituito, invalidato o quando il trade termina.

Ogni segmento deve essere coerente con il viewport e con l’asse temporale corrente.

### Requisiti comuni

- visibile durante zoom e pan;
- sincronizzato con le candele;
- non deve sparire o rompersi senza motivo;
- deve avere etichetta leggibile e tooltip coerente.

---

## 17. Regole per tipo di livello

### 17.1 Entry limit

- colore: blu;
- stile: tratteggiato;
- parte dal `SIGNAL_CREATED` o dall’evento che introduce il livello;
- se il livello viene fillato, il segmento termina in quel timestamp;
- ogni entry deve essere distinguibile dalle altre.

### 17.2 Entry market

- colore: viola;
- stile: tratteggiato;
- usata per entry market o fill immediati;
- se non ha senso un segmento reale, è ammesso il solo marker evento;
- se successivamente compare average entry, la rappresentazione può terminare nel momento in cui il livello medio diventa la rappresentazione dominante.

### 17.3 Stop loss

- colore: rosso;
- stile: tratteggiato;
- il primo stop parte dal setup;
- ogni aggiornamento stop chiude il segmento precedente e ne apre uno nuovo;
- la storia dello stop deve restare leggibile.

### 17.4 Take profit

- colore: verde;
- stile: tratteggiato;
- ogni TP parte quando viene armato o definito;
- termina quando viene colpito, invalidato, rimosso o quando il trade termina;
- i TP multipli devono essere distinti e identificabili.

### 17.5 Average entry

- deve apparire solo se ci sono almeno 2 fill;
- se c’è un solo fill, non deve essere disegnata;
- deve restare visibile per la durata del trade dopo la sua validazione;
- stile coerente ma distinto dalle entry normali.

---

## 18. Regole obbligatorie per etichette dei livelli

Le etichette dei livelli devono:

- stare visivamente al centro del segmento quando possibile;
- muoversi in modo coerente con la navigazione del chart;
- usare il colore della categoria del livello;
- restare leggibili;
- avere tooltip dedicato con almeno tipo livello e prezzo.

Non devono risultare tagliate in condizioni di uso normali.

---

## 19. Eventi da mostrare direttamente sul chart prezzo

Questi eventi devono essere ancorati a tempo e prezzo sulle candele:

- `ENTRY_FILLED`
- `SCALE_IN_FILLED`
- `MARKET_ENTRY_FILLED`
- `TP_HIT`
- `SL_HIT`
- `PARTIAL_EXIT`
- `FINAL_EXIT`

---

## 20. Eventi da mostrare preferibilmente sulla rail

Questi eventi devono andare preferibilmente sulla event rail:

- `SL_MOVED`
- `BE_ACTIVATED`
- `CANCELLED`
- `EXPIRED`
- `TIMEOUT`
- `SYSTEM_NOTE`

Se alcuni di essi hanno anche un prezzo utile, puoi gestire una vista ibrida, ma senza creare confusione sul chart.

---

## 21. Gestione collisioni

Quando più eventi condividono timestamp vicini o uguali:

- evitare sovrapposizioni illeggibili sul prezzo;
- usare lane dedicate sulla rail;
- usare stacking o offset controllato sul chart solo se necessario;
- evitare label tagliate o sovrapposte in modo irrecuperabile.

La leggibilità prevale sulla densità visiva.

---

## 22. Tooltip e selezione evento

## 22.1 Tooltip evento

Ogni evento selezionabile deve mostrare almeno:

- tipo evento;
- timestamp;
- prezzo, se esiste;
- summary sintetica;
- effetti essenziali su posizione, rischio o risultato.

## 22.2 Lista eventi operativi unificata in sidebar

Quando l’utente clicca un evento sul chart o sulla rail, la sidebar deve identificare l’item corrispondente nella **lista eventi operativi unificata**.

La lista deve:

- portare in vista l’item, se necessario;
- evidenziare chiaramente l’evento selezionato;
- poter aprire automaticamente l’item selezionato.

L’item selezionato nella lista sostituisce funzionalmente il vecchio `Selected event summary`:  
la **vista espansa dell’item** è il dettaglio dell’evento selezionato.

### Scopo

La lista deve essere sintetica, leggibile e utile alla lettura operativa del trade.

### Requisiti strutturali

- deve elencare tutti gli eventi principali del trade, ordinati temporalmente;
- ogni item deve essere **collassato di default**;
- ogni item deve essere **apribile al click**;
- selezionando un evento dal chart o dalla rail, l’item corrispondente nella lista deve aprirsi o evidenziarsi;
- cliccando un item della lista si deve poter evidenziare l’evento corrispondente sul chart o sulla rail.

### Ogni item deve mostrare almeno in vista collassata

- timestamp;
- label evento;
- descrizione umana breve;
- 1–3 chip effetto, per esempio:
  - size
  - sl
  - avg entry
  - realized %
  - close reason

### Vista espansa: cosa deve mostrare

Quando l’item viene aperto, deve mostrare solo i dati davvero pertinenti a quell’evento, per esempio:

- titolo evento;
- timestamp;
- source;
- summary;
- prezzo o livello coinvolto, se presente;
- impatto su posizione / rischio / risultato;
- link o bottone per aprire il testo completo del messaggio sorgente, se disponibile.

### Vista base: cosa non deve mostrare

Non mostrare in vista base:

- dump completi di `requested_action`;
- dump completi di `executed_action`;
- reason code tecnici verbosi;
- state delta completi;
- payload raw completi dell’engine.

### Dettagli specifici richiesti

#### Setup
Deve mostrare, se pertinenti:
- symbol;
- side;
- tipo di entry e relativi livelli;
- allocazione o size prevista, se disponibile;
- stop loss iniziale;
- livelli TP;
- pulsante `Raw Message Text` se esiste testo sorgente del trader.

#### Update operativi
Devono mostrare, se pertinenti:
- provenienza (`TRADER`, `ENGINE`, `SYSTEM`);
- eventuale livello o modifica operativa;
- pulsante `Raw Message Text` per update trader se disponibile;
- altri dettagli strettamente utili alla lettura.

### Regola di comportamento consigliata

Per mantenere leggibilità, è raccomandato che sia aperto un solo item alla volta.  
L’apertura di un nuovo item può chiudere automaticamente quello precedente.


## 24. Audit drawer

Deve esistere una sezione separata, collassata di default.

### Può contenere

- payload completi evento;
- requested/executed action;
- state delta completo;
- eventi ignored/system/debug;
- valori tecnici e campi raw.

### Regole

- non deve competere visivamente con la vista principale;
- deve essere chiaramente una vista secondaria;
- deve essere utile per audit e debug.

---

## 25. Interazione tra componenti

Devi implementare una relazione chiara tra chart, rail e **lista eventi unificata** nella sidebar.

### Comportamenti obbligatori

- click evento chart → evidenzia il relativo item nella lista sidebar e ne apre, se previsto, la vista espansa;
- click evento rail → evidenzia il relativo item nella lista sidebar e ne apre, se previsto, la vista espansa;
- click item lista → evidenzia evento corrispondente sul chart o sulla rail;
- hover opzionale → highlight morbido.

### Divieti

- i toggle del grafico non devono nascondere implicitamente la lista eventi;
- non creare dipendenze opache tra componenti;
- non usare stati UI che rendano poco prevedibile cosa è visibile e cosa no.

---

## 26. Requisiti tecnici di navigazione chart

Il grafico deve supportare almeno:

- zoom in/out;
- pan orizzontale;
- reset view;
- tooltip;
- persistenza visiva di livelli e segmenti durante la navigazione;
- allineamento temporale con rail e volume.

### Requisito critico

Durante zoom e pan:

- i livelli devono restare coerenti con il tratto temporale visibile;
- non devono sembrare fissi rispetto al viewport;
- non devono desincronizzarsi dalle candele.

---

## 27. Robustezza e degradazione elegante

Il generatore deve gestire correttamente almeno questi casi:

- trade senza fill;
- trade con singolo fill;
- trade con multi-fill e average entry;
- trade con solo close finale;
- trade con timeout / expired / cancel;
- eventi senza prezzo ancorabile;
- più eventi nello stesso timestamp;
- livelli mancanti o ricostruibili solo parzialmente;
- candele mancanti ai bordi del range.

### Regola generale

In presenza di dati incompleti:

- non inventare;
- non creare elementi falsi;
- mostrare solo ciò che è giustificato dai dati;
- degradare la UI con eleganza;
- loggare l’anomalia se utile.

---

## 28. Qualità visiva richiesta

Il report deve risultare:

- compatto;
- leggibile a colpo d’occhio;
- poco ridondante;
- chiaro anche con trade ricchi di eventi;
- coerente durante zoom e navigazione;
- più orientato alla lettura del trade che al debug del motore.

---

## 29. Piano di implementazione richiesto

Segui queste fasi:

### Fase 1 — Normalizzazione eventi
Obiettivo:
- produrre un solo modello canonico riusabile ovunque.

### Fase 2 — Costruzione segmenti livelli
Obiettivo:
- trasformare entry, SL, TP e average entry in intervalli temporali reali.

### Fase 3 — Payload chart e rail
Obiettivo:
- produrre payload robusti e coerenti con il modello canonico.

### Fase 4 — Lista eventi operativi unificata
Obiettivo:
- costruire un unico componente sidebar per la lettura operativa degli eventi, separato dall’audit tecnico.

### Fase 5 — Renderer HTML/CSS/JS
Obiettivo:
- costruire il report finale offline-friendly.

### Fase 6 — Test e validazione
Obiettivo:
- verificare i casi principali e i casi limite.

---

## 30. Test case minimi obbligatori

Devi verificare almeno questi scenari:

1. trade con 1 fill e più TP parziali;
2. trade con 2+ fill e average entry dinamica;
3. trade chiuso in stop loss;
4. trade con BE e successivo stop hit;
5. trade scaduto o timeout;
6. trade cancellato senza fill;
7. trade con update ravvicinati nello stesso timestamp o nella stessa finestra candle.

---

## 31. Criteri di accettazione funzionale

Il lavoro è accettato solo se tutte queste condizioni sono vere:

1. il grafico è il fulcro del report;
2. `Volume` e `Event rail` funzionano in modo indipendente;
3. non esistono toggle `Focus`, `Management`, `Audit`;
4. i livelli sono segmenti temporali reali;
5. SL, TP ed entry seguono la logica temporale richiesta;
6. average entry appare solo con 2+ fill;
7. la rail evita collisioni distruttive;
8. le etichette non risultano tagliate in condizioni standard;
9. zoom e pan mantengono allineati chart, rail e livelli;
10. il side panel mostra una sola **lista eventi operativi unificata**;
11. la lista eventi è in sidebar, collassata di default, sintetica ed espandibile;
12. la vista espansa dell’item selezionato sostituisce funzionalmente il vecchio `Selected event summary`;
13. sotto al blocco principale resta solo l’audit, separato e collassato;
14. il report funziona offline.

---

## 32. Criteri di successo finali

Il lavoro è riuscito se, aprendo `detail.html`, un utente riesce a:

1. capire il trade guardando prima il grafico;
2. chiarire i passaggi operativi leggendo la lista eventi unificata nella sidebar;
3. aprire l’audit solo quando serve;
4. percepire che il report rappresenta davvero la simulazione, non un mock decorativo.

---

## 33. Deliverable richiesti

Alla fine devi consegnare:

1. codice del generatore;
2. moduli helper separati, se presenti;
3. asset frontend locali;
4. esempio reale di report generato;
5. breve documentazione d’uso;
6. elenco casi limite gestiti;
7. differenze rispetto al report precedente, ma solo come nota finale separata.

---

## 34. Istruzione finale di comportamento

Quando c’è un conflitto tra:

- completezza del log tecnico
- chiarezza della lettura del trade

devi dare priorità alla **chiarezza della lettura del trade nella vista principale**.

L’audit tecnico deve restare disponibile, ma separato.
