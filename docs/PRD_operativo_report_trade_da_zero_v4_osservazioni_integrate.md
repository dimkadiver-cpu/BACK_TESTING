# PRD operativo — Generatore report HTML di singolo trade da zero (v4, osservazioni integrate)

## 1. Missione

Devi sviluppare **da zero** un generatore che produca un **report HTML di singolo trade**, offline-friendly, con approccio **chart-centric**.

Usa skills/echarts-from-prd/

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
11. **Le interazioni legend non devono resettare o alterare implicitamente il range di zoom corrente**.
12. **I livelli non devono sparire quando il viewport entra nel mezzo del segmento**.
13. **Le etichette livello devono essere realmente renderizzate sul chart**, non solo disponibili via nome serie o tooltip.
14. **A timeframe aggregati, gli eventi prezzo devono poter seguire il bucket candle visibile**, mantenendo nel tooltip il timestamp reale dell’evento.

---

## 4. Non devi fare

Non devi:

- riscrivere il motore di simulazione;
- cambiare la logica core del backtest;
- ridefinire PnL o metriche del simulatore;
- trasformare il report in dashboard multi-trade;
- trattare la timeline principale come dump del log tecnico;
- mischiare audit e lettura operativa principale;
- usare il click sulla legend per fare un rebuild completo del chart se questo cambia zoom, pan o scala in modo non richiesto.

---

## 5. Stack e riferimenti implementativi

Per il rendering chart devi usare le capacità native di **Apache ECharts**.

### Riferimenti ammessi e consigliati

- documentazione ufficiale ECharts: `https://echarts.apache.org/`
- esempio di riferimento stilistico per la legend e per il look generale del chart: `https://echarts.apache.org/examples/en/editor.html?c=candlestick-sh`
- skill interna di progetto: `C:\Back_Testing\skills\echarts-chart-builder`

### Regola

Le funzionalità non banali richieste in questo PRD devono essere implementate usando primitive robuste di ECharts, preferendo:

- `custom series`
- `renderItem`
- gestione esplicita di clipping viewport
- sincronizzazione controllata degli assi
- gestione non distruttiva degli aggiornamenti di visibilità

---

## 6. Layout finale obbligatorio

Il report HTML deve avere questa struttura:

```text
Single Trade Report
├─ Hero compact
├─ Main analysis block
│  ├─ Price chart
│  ├─ Optional event rail
│  └─ Side panel
│      └─ Unified operational events list
├─ Trade navigation menu
└─ Audit drawer (collapsed by default)
```

### Note

- la lista eventi operativi deve stare nella sidebar, non come sezione sotto al grafico;
- la lista eventi unificata sostituisce sia `Selected event summary` sia `Operational timeline`;
- tra il blocco principale e l’audit deve essere presente un navigation menu che permetta di navigare tra i vari trade senza tornare alla pagina del report policy;
- sotto al blocco principale deve restare solo il navigation menu e poi l’audit;
- audit deve essere separato e secondario.

---

## 7. Hero compact

Il blocco iniziale deve essere molto compatto.

### Titolo obbligatorio

Il titolo principale della hero deve mostrare solo:

- `signal_id`

### Esempio

- `signal_id: trader_a:rm2319`

### Regola di non ridondanza

Non duplicare nel titolo informazioni già presenti in card o chip come:

- symbol
- side
- status

### Campi obbligatori nelle metric card / hero body

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

## 8. Blocco principale di analisi

### 8.1 Price chart

Il grafico è il componente dominante del report.

### Deve visualizzare

- candele OHLC;
- livelli operativi come segmenti temporali;
- eventi con price impact;
- volume opzionale;
- event rail opzionale;
- tooltip;
- zoom e pan;
- allineamento temporale coerente tra chart, rail e volume;
- guida verticale comune di hover/selezione tra chart e rail.

### Requisiti critici

- il tempo delle candele deve usare il timestamp dichiarato dai dati, non reinterpretazioni dipendenti dal browser;
- i componenti temporali allineati devono condividere la stessa coordinata X;
- durante zoom/pan non devono comparire disallineamenti tra prezzo, rail, volume e livelli;
- quando un evento è selezionato o hoverato su rail o chart, deve comparire una **guida verticale comune** che renda evidente l’allineamento temporale tra i pannelli.

### Requisiti implementativi obbligatori per i livelli

I livelli non devono essere resi come semplici serie `line` a due punti che spariscono se gli endpoint escono dal viewport.

Devi usare una delle seguenti strategie robuste:

- `custom series` con `renderItem`;
- clipping esplicito del segmento contro il viewport corrente;
- layer dedicato che mantenga visibile il tratto di segmento che interseca il range visualizzato.

La soluzione scelta deve garantire che il livello resti visibile anche quando il viewport taglia il segmento nel mezzo.

### Requisiti implementativi obbligatori per il tooltip dei livelli

Il passaggio del cursore sui livelli deve attivare un tooltip affidabile.

Per ottenerlo, devi usare una soluzione robusta, per esempio:

- custom layer dedicato ai segmenti;
- hit-area invisibile ma interattiva;
- rendering custom che gestisce direttamente hit test e tooltip.

Non è accettabile affidarsi solo al tooltip asse globale se questo rende inaffidabile il tooltip sui livelli.

### Requisiti implementativi obbligatori per cambio timeframe

Quando il timeframe passa da `1m` a timeframe aggregati come `15m` o `1h`, gli eventi ancorati a prezzo devono supportare una **modalità candle-snapped per TF aggregati**.

### Regola

Per timeframe aggregati:

- il marker grafico deve essere ancorato al bucket candle visibile corrispondente;
- il tooltip deve continuare a mostrare il **timestamp reale** dell’evento;
- l’utente non deve percepire che il marker “galleggia fuori candela” in modo incoerente.

---

### 8.2 Side panel

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

## 9. Toggle obbligatori

Sulla stessa riga della selezione timeframe, ordinata **dal più basso al più alto**, devono esistere solo questi toggle principali:

- `Volume`
- `Event rail`

### Regole

- nessun toggle `Focus`;
- nessun toggle `Management`;
- nessun toggle `Audit`;
- il cambio visibilità via legend non deve resettare il range corrente di zoom.

---

## 10. Legend obbligatoria

Sotto la riga dei toggle deve esserci una `Legend`.

La legend deve svolgere una doppia funzione:

1. spiegare il significato visivo di livelli ed eventi;
2. permettere di attivare/disattivare la visualizzazione delle categorie sul chart.

### Requisiti stilistici

La legend deve richiamare il linguaggio visivo dell’esempio ECharts `candlestick-sh`, ma essere personalizzata secondo questo PRD.

### Esempi attesi

- `--- TP LEVELS`
- `--- SL`
- `--- ENTRY LIMIT`
- `--- MARKET ENTRY`
- marker `TP hit`
- marker `SL hit`
- marker `Entry filled`
- marker `Final exit`

### Regole

- la legenda deve essere leggibile, non tagliata, coerente coi colori e forme reali usati sul grafico;
- il click sulla legend deve cambiare solo la visibilità delle categorie richieste;
- il click sulla legend **non deve causare redraw completo distruttivo** del chart;
- il click sulla legend **non deve modificare implicitamente lo zoom corrente**, salvo il normale ricalcolo controllato del contenuto visibile.

---

## 11. Event rail opzionale

La event rail è un componente separato, attivabile via toggle, attivo di default.

### Requisiti obbligatori

- deve poter essere nascosta;
- deve seguire lo stesso asse temporale del grafico;
- deve aggiornarsi con zoom e pan;
- deve distribuire gli eventi in lane separate per ridurre collisioni;
- deve usare simboli coerenti per categoria;
- deve partecipare alla guida verticale comune di hover/selezione con il chart.

### Eventi tipicamente da mettere sulla rail

- `SL_MOVED`
- `BE_ACTIVATED`
- `CANCELLED`
- `EXPIRED`
- `TIMEOUT`
- `SYSTEM_NOTE`
- eventi di gestione o sistema non direttamente eseguiti a prezzo

---

## 12. Modello canonico degli eventi

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
  "reason": "optional",
  "details": {},
  "visual": {
    "color_key": "optional",
    "lane_key": "optional",
    "chart_anchor_mode": "exact | candle_snapped"
  },
  "relations": {
    "parent_event_id": "optional",
    "derived_from_policy": false,
    "sequence_group": "optional"
  }
}
```

### Regola fondamentale

Non sono ammesse versioni diverse dello stesso evento tra chart, rail, lista eventi sidebar e audit.

---

## 13. Tassonomia minima degli eventi

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

## 14. Ordinamento obbligatorio degli eventi nella events list

La lista eventi unificata in sidebar deve seguire questo ordine:

1. **prima il Setup**;
2. poi tutti gli altri eventi in ordine cronologico;
3. in caso di movimenti automatici derivati dalla policy, l’evento principale deve comparire prima dell’evento derivato collegato.

### Esempio obbligatorio

Se viene colpito un TP e subito dopo la policy sposta lo stop a BE:

- prima mostra `TP_HIT` o `PARTIAL_EXIT`;
- poi mostra `BE_ACTIVATED` o `SL_MOVED` derivato.

### Regola

La relazione tra evento principale e derivato deve essere evidente nella struttura dati e nella UI.

---

## 15. Regole obbligatorie per i livelli

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

## 16. Regole per tipo di livello

### 16.1 Entry limit

- colore: blu;
- stile: tratteggiato;
- parte dal `SIGNAL_CREATED` o dall’evento che introduce il livello;
- se il livello viene fillato, il segmento termina in quel timestamp;
- ogni entry deve essere distinguibile dalle altre.

### 16.2 Entry market

- colore: viola;
- stile: tratteggiato;
- usata per entry market o fill immediati;
- se non ha senso un segmento reale, è ammesso il solo marker evento;
- se successivamente compare average entry, la rappresentazione può terminare nel momento in cui il livello medio diventa la rappresentazione dominante.

### 16.3 Stop loss

- colore: rosso;
- stile: tratteggiato;
- il primo stop parte dal setup;
- la linea dello stop iniziale deve estendersi fino al momento di fine trade, `SL_HIT` o cambio livello;
- quando il livello stop cambia, la rappresentazione **non deve sembrare una linea che si interrompe e ricomincia altrove senza continuità visiva**;
- al timestamp del cambio livello, la linea deve fare un **angolo / gomito** verso il nuovo livello e poi continuare sul nuovo prezzo;
- il primo tratto deve avere didascalia `Stop Loss initial`;
- i successivi tratti devono avere didascalia `New Stop Loss 1`, `New Stop Loss 2`, eccetera.

### 16.4 Take profit

- colore: verde;
- stile: tratteggiato;
- ogni TP parte quando viene armato o definito;
- termina quando viene colpito, invalidato, rimosso o quando il trade termina;
- i TP multipli devono essere distinti e identificabili.

### 16.5 Average entry

- deve apparire solo se ci sono almeno 2 fill;
- se c’è un solo fill, non deve essere disegnata;
- deve restare visibile per la durata del trade dopo la sua validazione;
- stile coerente ma distinto dalle entry normali.

---

## 17. Regole obbligatorie per etichette dei livelli

Le etichette dei livelli devono:

- stare visivamente al centro del segmento quando possibile;
- muoversi in modo coerente con la navigazione del chart;
- usare il colore della categoria del livello;
- restare leggibili;
- avere tooltip dedicato con almeno tipo livello e prezzo.

### Requisito implementativo obbligatorio

Le etichette dei livelli devono essere rese tramite **custom series che disegna insieme linea + testo**, oppure tramite soluzione equivalente che garantisca:

- reale centratura della didascalia sul tratto visibile;
- persistenza durante zoom e pan;
- clipping corretto nel viewport.

Non è accettabile contare solo su `seriesName`, su tooltip o su label serie standard se questi non garantiscono centratura e persistenza.

---

## 18. Eventi da mostrare direttamente sul chart prezzo

Questi eventi devono essere ancorati a tempo e prezzo sulle candele:

- `ENTRY_FILLED`
- `SCALE_IN_FILLED`
- `MARKET_ENTRY_FILLED`
- `TP_HIT`
- `SL_HIT`
- `PARTIAL_EXIT`
- `FINAL_EXIT`

### Regola per timeframe aggregati

Per timeframe aggregati, questi eventi devono usare `chart_anchor_mode = candle_snapped`, mantenendo nel tooltip l’orario reale di esecuzione.

---

## 19. Eventi da mostrare preferibilmente sulla rail

Questi eventi devono andare preferibilmente sulla event rail:

- `SL_MOVED`
- `BE_ACTIVATED`
- `CANCELLED`
- `EXPIRED`
- `TIMEOUT`
- `SYSTEM_NOTE`

Se alcuni di essi hanno anche un prezzo utile, puoi gestire una vista ibrida, ma senza creare confusione sul chart.

---

## 20. Gestione collisioni

Quando più eventi condividono timestamp vicini o uguali:

- evitare sovrapposizioni illeggibili sul prezzo;
- usare lane dedicate sulla rail;
- usare stacking o offset controllato sul chart solo se necessario;
- evitare label tagliate o sovrapposte in modo irrecuperabile.

La leggibilità prevale sulla densità visiva.

---

## 21. Tooltip e selezione evento

### 21.1 Tooltip evento

Ogni evento selezionabile deve mostrare almeno:

- tipo evento;
- timestamp;
- prezzo, se esiste;
- summary sintetica;
- effetti essenziali su posizione, rischio o risultato.

### 21.2 Tooltip livelli

Ogni livello selezionabile deve mostrare almeno:

- tipo livello;
- prezzo;
- intervallo temporale del tratto visibile o del segmento logico;
- eventuale indice o nome umano (`TP1`, `Entry 2`, `New Stop Loss 1`).

### 21.3 Guida verticale comune rail/chart

Quando un evento è selezionato o hoverato:

- deve essere possibile mostrare una linea verticale comune tra chart e rail;
- la guida deve chiarire l’allineamento temporale;
- la guida non deve alterare il contenuto o il viewport.

---

## 22. Lista eventi operativi unificata in sidebar

Quando l’utente clicca un evento sul chart o sulla rail, la sidebar deve identificare l’item corrispondente nella **lista eventi operativi unificata**.

La lista deve:

- portare in vista l’item, se necessario;
- evidenziare chiaramente l’evento selezionato;
- poter aprire automaticamente l’item selezionato.

L’item selezionato nella lista sostituisce funzionalmente il vecchio `Selected event summary`.
La **vista espansa dell’item** è il dettaglio dell’evento selezionato.

### Requisiti strutturali

- deve elencare tutti gli eventi principali del trade, ordinati secondo la regola del capitolo 14;
- ogni item deve essere **collassato di default**;
- ogni item deve essere **apribile al click**;
- selezionando un evento dal chart o dalla rail, l’item corrispondente nella lista deve aprirsi o evidenziarsi;
- cliccando un item della lista si deve poter evidenziare l’evento corrispondente sul chart o sulla rail.

### Comportamento consigliato

Per mantenere leggibilità, è raccomandato che sia aperto un solo item alla volta.
L’apertura di un nuovo item può chiudere automaticamente quello precedente.

---

## 23. Aspetto visivo degli item nella lista sidebar

Ogni item deve introdurre un elemento visivo che richiami il colore dell’evento sul chart o sulla rail.

### Mappatura colori obbligatoria

- verde per `TP hit`
- rosso per `SL hit`
- blu per `Entry Filled`
- viola per `Market Entry Filled`
- arancione per `Full Close` o `Partial Close`
- giallo per eventi tecnici come `Expired`

### Regola

Il codice colore deve essere coerente tra:

- marker chart
- marker rail
- item sidebar
- eventuale badge o barra laterale dell’item

---

## 24. Dati rappresentati negli item della lista sidebar

### Forma compatta: solo info essenziali

Ogni item, in forma collassata, deve mostrare almeno:

#### Header

- titolo semplificato umano, per esempio:
  - `SETUP OPENED`
  - `TAKE PROFIT 1 HIT`
  - `STOP LOSS HIT`
  - `FULL CLOSE`
  - `PARTIAL CLOSE`
  - `ENTRY 1 FILLED`
  - `MARKET ENTRY FILLED`
  - `MOVE STOP`
  - `ADD ENTRY`
- time

#### Corpo compatto

Mostra solo i dettagli essenziali più rilevanti per quel tipo evento.

---

### 24.1 TP hit / SL hit

Mostrare:

- `Source`
- `Level/Price`
- `Position impact`
- `PnL % realizzato`
- `Reason` derivato da engine

### 24.2 Setup

Mostrare:

- `Symbol`
- `Side`
- `Entry levels + Type (Limit/Market) + qty in % della posizione`
- `Stop loss`
- `Take Profits`
- `Risk`, se estratto
- pulsante o link `Raw Message Text` che apre popup o vista dedicata

### 24.3 Move Stop

Mostrare:

- `Source`
- `New Level/Price`
- pulsante o link `Raw Message Text` se disponibile

### 24.4 Close Full / Close Partial

Evento dichiarativo derivato da messaggio e/o engine policy.

Mostrare:

- `Source`
- `Level/Price di chiusura`
- `Quantità in %`
- `Position impact`
- `PnL % realizzato`
- pulsante o link `Raw Message Text` se disponibile

### 24.5 ENTRY N. FILLED / MARKET ENTRY FILLED

Mostrare:

- `Source`
- `Level/Price di filled`
- `Position impact`
- `Reason` derivato da engine

### 24.6 Altri eventi

Per gli altri eventi, mostrare solo le informazioni strettamente essenziali e realmente utili alla lettura.

### Regola generale

Non trasformare gli item in dump tecnici.

---

## 25. Audit drawer

Deve esistere una sezione separata, collassata di default.

### Scopo

L’audit drawer deve essere tecnico, ma leggibile.
Non deve essere la discarica JSON del report.

### Regole di rappresentazione

Nel drawer devi:

- mostrare campi leggibili in tabella o card;
- lasciare il JSON raw solo dentro un sotto-toggle tipo `Raw payload`;
- per `details`, mostrare key/value umani e usare JSON solo per oggetti annidati complessi.

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

## 26. Interazione tra componenti

Devi implementare una relazione chiara tra chart, rail e **lista eventi unificata** nella sidebar.

### Comportamenti obbligatori

- click evento chart → evidenzia il relativo item nella lista sidebar e ne apre, se previsto, la vista espansa;
- click evento rail → evidenzia il relativo item nella lista sidebar e ne apre, se previsto, la vista espansa;
- click item lista → evidenzia evento corrispondente sul chart o sulla rail;
- hover evento chart o rail → può evidenziare l’item corrispondente in modo morbido;
- selezione o hover evento → può attivare la guida verticale comune tra chart e rail.

### Divieti

- i toggle del grafico non devono nascondere implicitamente la lista eventi;
- non creare dipendenze opache tra componenti;
- non usare stati UI che rendano poco prevedibile cosa è visibile e cosa no.

---

## 27. Requisiti tecnici di navigazione chart

Il grafico deve supportare almeno:

- zoom in/out;
- pan orizzontale;
- reset view;
- tooltip;
- persistenza visiva di livelli e segmenti durante la navigazione;
- allineamento temporale con rail e volume.

### Requisiti critici

Durante zoom e pan:

- i livelli devono restare coerenti con il tratto temporale visibile;
- non devono sembrare fissi rispetto al viewport;
- non devono desincronizzarsi dalle candele;
- il cambio visibilità via legend non deve resettare il range corrente;
- la scala non deve cambiare in modo imprevedibile per effetto di redraw distruttivi.

---

## 28. Robustezza e degradazione elegante

Il generatore deve gestire correttamente almeno questi casi:

- trade senza fill;
- trade con singolo fill;
- trade con multi-fill e average entry;
- trade con solo close finale;
- trade con timeout / expired / cancel;
- eventi senza prezzo ancorabile;
- più eventi nello stesso timestamp;
- livelli mancanti o ricostruibili solo parzialmente;
- candele mancanti ai bordi del range;
- eventi prezzo che devono degradare da `exact` a `candle-snapped` nei timeframe aggregati.

### Regola generale

In presenza di dati incompleti:

- non inventare;
- non creare elementi falsi;
- mostrare solo ciò che è giustificato dai dati;
- degradare la UI con eleganza;
- loggare l’anomalia se utile.

---

## 29. Qualità visiva richiesta

Il report deve risultare:

- compatto;
- leggibile a colpo d’occhio;
- poco ridondante;
- chiaro anche con trade ricchi di eventi;
- coerente durante zoom e navigazione;
- più orientato alla lettura del trade che al debug del motore.

---

## 30. Piano di implementazione richiesto

Segui queste fasi:

### Fase 1 — Normalizzazione eventi
Obiettivo:
- produrre un solo modello canonico riusabile ovunque;
- modellare esplicitamente relazioni parent/derived tra eventi.

### Fase 2 — Costruzione segmenti livelli
Obiettivo:
- trasformare entry, SL, TP e average entry in intervalli temporali reali;
- implementare il comportamento a gomito per lo stop loss.

### Fase 3 — Renderer livelli custom
Obiettivo:
- usare `custom series` / `renderItem` per segmenti, tooltip e didascalie centrali.

### Fase 4 — Payload chart, rail e snapping TF
Obiettivo:
- produrre payload robusti e coerenti con il modello canonico;
- introdurre `candle-snapped` per TF aggregati.

### Fase 5 — Lista eventi operativi unificata
Obiettivo:
- costruire un unico componente sidebar per la lettura operativa degli eventi, separato dall’audit tecnico.

### Fase 6 — Audit drawer leggibile
Obiettivo:
- rappresentare campi tecnici in modo leggibile, con raw JSON solo in sotto-toggle.

### Fase 7 — Test e validazione
Obiettivo:
- verificare i casi principali e i casi limite.

---

## 31. Test case minimi obbligatori

Devi verificare almeno questi scenari:

1. trade con 1 fill e più TP parziali;
2. trade con 2+ fill e average entry dinamica;
3. trade chiuso in stop loss;
4. trade con BE e successivo stop hit;
5. trade scaduto o timeout;
6. trade cancellato senza fill;
7. trade con update ravvicinati nello stesso timestamp o nella stessa finestra candle;
8. trade con cambio timeframe `1m -> 15m -> 1h` e verifica dello snapping marker;
9. trade con più cambi stop e verifica del comportamento a gomito;
10. click legend senza alterazione del range zoom corrente;
11. hover sui livelli con tooltip affidabile;
12. zoom in mezzo a segmenti lunghi senza scomparsa dei livelli.

---

## 32. Criteri di accettazione funzionale

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
13. sotto al blocco principale resta solo il navigation menu e poi l’audit, separato e collassato;
14. il report funziona offline;
15. il click sulla legend non resetta il range di zoom corrente;
16. i livelli non spariscono quando il viewport taglia il segmento;
17. i livelli hanno tooltip affidabile;
18. le didascalie dei livelli sono visibili e centrate sul tratto;
19. nei timeframe aggregati gli eventi prezzo non risultano visivamente fuori candela in modo incoerente;
20. l’audit drawer mostra dati leggibili e il raw JSON solo come livello secondario.

---

## 33. Criteri di successo finali

Il lavoro è riuscito se, aprendo `detail.html`, un utente riesce a:

1. capire il trade guardando prima il grafico;
2. chiarire i passaggi operativi leggendo la lista eventi unificata nella sidebar;
3. aprire l’audit solo quando serve;
4. percepire che il report rappresenta davvero la simulazione, non un mock decorativo.

---

## 34. Deliverable richiesti

Alla fine devi consegnare:

1. codice del generatore;
2. moduli helper separati, se presenti;
3. asset frontend locali;
4. esempio reale di report generato;
5. breve documentazione d’uso;
6. elenco casi limite gestiti;
7. differenze rispetto al report precedente, ma solo come nota finale separata.

---

## 35. Istruzione finale di comportamento

Quando c’è un conflitto tra:

- completezza del log tecnico
- chiarezza della lettura del trade

devi dare priorità alla **chiarezza della lettura del trade nella vista principale**.

L’audit tecnico deve restare disponibile, ma separato.
