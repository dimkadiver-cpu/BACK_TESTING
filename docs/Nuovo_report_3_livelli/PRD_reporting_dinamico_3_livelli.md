# PRD — Sistema di reporting dinamico a 3 livelli

## 1. Obiettivo

Definire un sistema di reporting HTML dinamico, navigabile e coerente, basato su 3 livelli:

1. `comparison_report`
2. `single_policy_report`
3. `single_trade_report`

Il sistema deve permettere:
- confronto tra più policy sotto lo stesso contesto di analisi;
- analisi dinamica e filtrabile di una singola policy;
- navigazione fino al dettaglio del singolo trade;
- persistenza dello stato di sessione durante la navigazione tra i report;
- correzione locale dei riepiloghi tramite esclusione manuale di trade anomali, senza alterare i dati sorgente.



### Vincolo importante
Il `single_trade_report` è già coperto da PRD specifico e **non deve essere modificato da questo PRD**.

---

## 3. Scope

### In scope
- ridefinizione funzionale del `comparison_report`;
- ridefinizione funzionale del `single_policy_report`;
- modello di navigazione tra report;
- gestione filtri, stato di sessione e contesto di confronto;
- definizione di tabella trade, metriche e metadati;
- comportamento dinamico lato client sui report HTML.

### Out of scope
- redesign del `single_trade_report`;
- modifica del modello dati sorgente del simulatore;
- modifica del formato sorgente di `trade_result.csv`, `policy_summary.*`, `comparison_summary.*`, salvo eventuali campi aggiuntivi necessari e compatibili;
- modifica dei calcoli del backtest in sé.

---

## 4. Architettura concettuale

Il sistema è organizzato su 3 livelli.

### 4.1 `comparison_report`
Livello alto.

Scopo:
- confrontare più policy;
- mostrare metadati di run;
- mostrare metriche aggregate derivate dai singoli `single_policy_report`;
- applicare un **comparison context** globale e coerente a tutte le policy confrontate.

### 4.2 `single_policy_report`
Livello intermedio.

Scopo:
- riassumere i trade di una singola policy;
- mostrare metadati e valori di `policy.yaml`;
- permettere filtro dinamico dei trade;
- permettere esclusione manuale locale di trade dal calcolo;
- permettere il salvataggio dei soli filtri Core come `comparison context` globale.

### 4.3 `single_trade_report`
Livello basso.

Scopo:
- mostrare il dettaglio del singolo trade.

Vincolo:
- **non modificare la struttura logica e funzionale del report trade**;
- il report deve solo restare navigabile dal `single_policy_report`.

---

## 5. Regole fondamentali di dominio

### 5.1 Comparison context
Il `comparison context` è un contesto globale di confronto applicato nel `comparison_report`.

È salvabile a partire dal `single_policy_report`.

Contiene **solo filtri Core**, cioè filtri semplici, strutturati e riapplicabili su tutte le policy:
- `date range`
- `trader`
- `symbol`
- `side`
- `trade status`

### 5.2 Filtri locali
Nel `single_policy_report` sono ammessi filtri aggiuntivi, ma restano **solo locali**.

Filtri locali approvati:
- `side`
- `close reason`
- `outcome`

Valori `outcome`:
- `All`
- `gain`
- `loss`
- `flat`

Questi filtri:
- aggiornano il report locale;
- **non** vengono esportati nel `comparison context`;
- **non** influenzano il `comparison_report`.

### 5.3 Esclusione manuale trade
Nel `single_policy_report` l’utente può escludere manualmente uno o più trade dal calcolo.

Questa funzione:
- è **locale** al report policy;
- è **temporanea**;
- vale **solo nella sessione** del report;
- **non** modifica i dati sorgente;
- **non** altera file CSV/JSON/HTML generati a monte;
- serve solo a correggere riepiloghi locali in caso di trade evidentemente anomali o fuorvianti.

### 5.4 Segnali esclusi
La lista dei segnali esclusi nel `single_policy_report` deve riferirsi a:
- segnali/catene **esclusi dal processo**;
- quindi non simulati, con motivo.

Non devono essere confusi con:
- trade simulati ma esclusi manualmente dal calcolo in sessione.

---

## 6. Navigazione tra i livelli

### 6.1 Flusso previsto
Flusso principale:

1. apertura `comparison_report`
2. selezione/apertura di una policy
3. apertura `single_policy_report`
4. eventuale apertura di uno specifico trade
5. apertura `single_trade_report`
6. navigazione di ritorno preservando il contesto di sessione

### 6.2 Comportamento `comparison_report` → `single_policy_report`
Quando si apre un `single_policy_report` dal `comparison_report`:
- i filtri Core del `comparison context` devono arrivare **già compilati**;
- devono restare **modificabili**;
- i filtri locali restano locali alla policy.

### 6.3 Comportamento `single_policy_report` → `comparison_report`
Quando dal `single_policy_report` si salva un nuovo `comparison context`:
- si salvano **solo** i filtri Core;
- il `comparison_report` deve usare il nuovo context;
- i filtri locali non vengono esportati;
- le esclusioni manuali non vengono esportate.

### 6.4 Comportamento `single_policy_report` → `single_trade_report`
Ogni trade deve avere un accesso esplicito al relativo report di dettaglio.

Il report trade deve aprirsi senza perdere:
- policy di provenienza;
- contesto di navigazione utile al ritorno.

---

## 7. Persistenza dello stato

### 7.1 Tipo di persistenza
La persistenza deve essere di **sessione**.

Approccio richiesto:
- usare `sessionStorage` lato client;
- **non** usare `localStorage` come comportamento standard.

Motivazione:
- lo stato deve restare valido durante la sessione di lavoro;
- non deve contaminare aperture future di run/report diversi.

### 7.2 Chiave logica di sessione
Lo stato deve essere isolato per run/report set.

Chiave logica suggerita:
- identificatore derivato dalla cartella radice del report oppure da un `reportSessionKey` esplicito.

### 7.3 Stato globale
Da persistere globalmente per sessione/report:
- policy selezionate nel `comparison_report`;
- `comparison context` corrente.

### 7.4 Stato locale per policy
Da persistere separatamente per ogni policy:
- filtri locali attivi;
- eventuali valori correnti dei Core filters nel report policy;
- ordinamento corrente della trade list;
- insieme dei trade esclusi manualmente;
- eventuale stato tabellare utile alla UX.

### 7.5 Stato del report trade
Il `single_trade_report` non deve introdurre uno stato proprio complesso.

Deve però preservare:
- origine di navigazione;
- possibilità di ritorno coerente al `single_policy_report`.

---

## 8. `comparison_report` — requisiti

## 8.1 Scopo
Il report di confronto deve:
- mostrare metadati della run;
- confrontare più policy;
- restare sintetico;
- aggiornarsi dinamicamente in base al `comparison context`;
- evidenziare la policy migliore e i migliori valori per metrica.

## 8.2 Metadati
I metadati da mostrare:
- Timeframe bel backtest
- Price basis
- Market provider
- Generated (data)
- Date range dei dati testati


## 8.3 Comparison context visibile
In alto il report deve mostrare il `comparison context` come contesto visibile.

In aggiunta deve mostrare:
- badge sintetico `filter active` quando è attivo un contesto non vuoto;
- dettaglio espandibile o tooltip del contenuto del context.

Il badge non sostituisce i metadati di contesto: li integra.

## 8.4 Colonne della tabella di confronto
Mantenere tutte le colonne presenti nell’esempio attuale di confronto, **tranne**:
- `Policy`
- `Trades` numero di trades
- `Excluded` numero di trades esclusi
- `Win rate`
- `Net Profit`
- `Profit`      
- `Loss`	
- `Profit factor`
- `Fee %`
- `Funding %`
- `Total costs %`



## 8.5 Logica del confronto
Le metriche di confronto devono essere ricalcolate/filtrate coerentemente con il `comparison context` attivo.

Il confronto non deve usare:
- filtri locali della policy;
- esclusioni manuali della trade list. ?????

## 8.6 Evidenziazione migliori policy / metriche
Seguire la logica visiva del redesign.

Richiesto:
- tag `Best` sotto il nome policy migliore;
- highlight delle celle migliori per metrica.

Regola semantica:
- metriche dove un valore più alto è migliore: evidenziare il massimo;
- metriche di costo: evidenziare il minimo.

---

## 9. `single_policy_report` — requisiti

## 9.1 Scopo
Il report policy deve:
- essere riassuntivo dei trade analizzati;
- essere dinamico;
- mostrare contatori essenziali e metriche cumulative base;
- permettere analisi filtrata della trade list;
- permettere esclusioni manuali locali dal calcolo;
- mostrare segnali esclusi dal processo;
- esporre `policy.yaml values`.

## 9.2 Metadati
Mostrare i metadati presenti:
- Dataset Name
- Dataset Name
- Period
- Market Provider
- Timeframe
- Price Basis
- Selected Chains

In aggiunta mostrare una sezione:
- `Metadata — policy.yaml values`naturalmente collossata

Questa sezione deve esporre i valori utili letti da `policy.yaml` in modo leggibile.

## 9.3 Contatori base
Mostrare i seguenti contatori:
- `Simulated chains`
- `Excluded signals`
- `Closed`
- `Expired`

Questi contatori devono riflettere il dataset policy in modo coerente con il report.

## 9.4 Metriche cumulative base
Mostrare almeno:
- `Numero trades included in calculation`
- `Win rate`
- `Gross %`
- `Net %`
- `Fee %`
- `Funding %`
- `Total costs %`
- `Final Cum Equity`
- `Avg R`
- `Best Trade % Net`
- `Worst Trade % Net`
- `Profit Factor`

Regole:
- le metriche devono aggiornarsi con i filtri attivi;
- le metriche devono aggiornarsi con le esclusioni manuali attive;
- `Gross %` = prima dei costi;
- `Net %` = dopo i costi;
- `Total costs %` = `Fee % + Funding %`;
- `Best/Worst Trade % Net` devono considerare solo i trade attualmente inclusi;
- `Profit Factor` deve considerare solo i trade attualmente inclusi.

## 9.5 Filtri
### 9.5.1 Core filters
Filtri Core, salvabili come `comparison context`:
- `date range`
- `trader` se disponibile
- `side`
- `symbol`
- `trade status`

### 9.5.2 Local filters
Filtri locali aggiuntivi, non salvabili nel `comparison context`:
- `side`
- `close reason`
- `outcome`

### 9.5.3 Regola di salvataggio
L’azione “save as comparison context” deve esportare solo i Core filters.

## 9.6 Lista segnali esclusi
Mostrare la lista dei segnali/catene esclusi dal processo.

La lista deve essere chiaramente separata dalla trade list simulata.     
Deve indicare il motivo della esclusione. Deve avere pulsante o link che mostri testo originale del messaggio raw.

---

## 10. Trade list del `single_policy_report`

## 10.1 Scopo
La trade list è il punto operativo principale del report policy.

Deve permettere:
- ispezione rapida dei trade;
- ordinamento dinamico;
- esclusione/inclusione dal calcolo;
- accesso al report trade di dettaglio.

## 10.2 Colonne richieste
La tabella deve includere:
- `Include`
- `Signal ID`
- `Symbol`
- `Side`
- `Trade Status`
- `Close Reason`
- `Net %`
- `Gross %`
- `Warn`
- `Cum Equity`
- `R`
- `Detail`

## 10.3 Colonna `Include`
La colonna `Include` deve contenere una checkbox.

Semantica:
- `checked` = trade incluso nel calcolo;
- `unchecked` = trade escluso dal calcolo.

Effetti:
- aggiornamento immediato delle metriche cumulative del `single_policy_report`;
- nessuna modifica ai dati sorgente.

## 10.4 Colonna `Detail`
La colonna `Detail` deve contenere l’azione esplicita per aprire il `single_trade_report`.

Non demandare questa funzione al click sull’intera riga.

## 10.5 Stato visivo dei trade esclusi manualmente
I trade esclusi manualmente devono:
- restare visibili in tabella;
- avere opacità ridotta;
- non contribuire ai riepiloghi;
- essere spostati in fondo alla lista.

## 10.6 Ordinamento dinamico colonne
I titoli colonna devono essere cliccabili.

### 10.6.1 Colonne numeriche
Per colonne numeriche (`Net %`, `Gross %`, `Cum Equity`, `R`, e ogni altra numerica):
- primo click = ordinamento migliore → peggiore
- header evidenziato in verde
- secondo click = ordinamento peggiore → migliore
- header evidenziato in rosso
- terzo click = ritorno all’ordine di default

### 10.6.2 Colonne testuali/categoriali
Per colonne testuali/categoriali (`Signal ID`, `Symbol`, `Side`, `Trade Status`, `Close Reason`):
- primo click = crescente
- secondo click = decrescente
- terzo click = ritorno all’ordine di default

### 10.6.3 Ordine di default
L’ordine di default deve essere stabile e coerente con il report generato.

Non usare un ordine casuale.

---

## 11. Regole di consistenza tra report

### 11.1 Cosa passa al `comparison_report`
Passano solo:
- policy selezionate;
- `comparison context` Core.

### 11.2 Cosa non passa al `comparison_report`
Non devono passare:
- filtri locali di singola policy;
- esclusioni manuali dei trade;
- stato di sort della trade list.

### 11.3 Cosa deve essere chiaro in UI
L’utente deve poter capire facilmente la differenza tra:
- `comparison context` globale;
- filtri locali del `single_policy_report`;
- esclusioni manuali temporanee dal calcolo.

Questi tre meccanismi non devono essere confusi.

---

## 12. Reset e controlli di stato

## 12.1 Reset nel `comparison_report`
Servire un’azione di reset del `comparison context`.

Effetto:
- rimuove il context globale;
- non tocca lo stato locale di sessione già memorizzato nelle singole policy.

## 12.2 Reset nel `single_policy_report`
Servire almeno:
- reset dei filtri locali;
- reset delle esclusioni manuali;
- facoltativamente reset completo della vista policy.

---

## 13. Requisiti UX

### 13.1 Principi
Il sistema deve essere:
- leggibile;
- navigabile;
- coerente tra livelli;
- chiaramente dinamico;
- esplicito sulle condizioni che influenzano i numeri mostrati.

### 13.2 Comparison report
Il `comparison_report` deve restare sintetico.

Non introdurre complessità visiva non necessaria.

### 13.3 Policy report
Il `single_policy_report` può essere più operativo e interattivo.

I blocchi chiave devono essere facilmente distinguibili:
- metadati;
- policy.yaml values;
- filtri;
- metriche base;
- trade list;
- segnali esclusi.

### 13.4 Trade report
Il `single_trade_report` resta invariato.

---

## 14. Requisiti tecnici di implementazione

### 14.1 Tecnologia attesa
Implementazione prevista come report HTML statici con logica client-side.

Ammessi:
- HTML
- CSS
- JavaScript vanilla o leggero layer utility

Non è richiesto introdurre framework complessi se non strettamente necessario.

### 14.2 Dati
Il sistema deve leggere e usare i dati già prodotti dal pipeline/report generator attuale, per quanto possibile.

Eventuali arricchimenti devono essere compatibili con la struttura esistente.

### 14.3 Compatibilità file-based
I report devono restare usabili come output navigabile su filesystem locale.

Il comportamento dinamico lato client non deve richiedere backend applicativo dedicato.

---

## 15. Acceptance criteria

Il lavoro sarà considerato corretto se:

1. esistono e restano navigabili i 3 livelli di report;
2. il `single_trade_report` non viene ridefinito da questo lavoro;
3. il `comparison_report` applica un `comparison context` globale con soli filtri Core;
4. il `single_policy_report` consente filtri Core e filtri locali separati;
5. il `single_policy_report` consente esclusione manuale dei trade dal calcolo via checkbox;
6. le esclusioni manuali non alterano dati sorgente né confronto globale;
7. la trade list ha le colonne concordate e il comportamento di sort concordato;
8. il `comparison_report` mantiene il layout logico del redesign con:
   - context visibile in alto;
   - badge `filter active`;
   - tag `Best`;
   - highlight migliori celle;
9. il `single_policy_report` mostra contatori, metriche cumulative base, lista segnali esclusi e `policy.yaml values`;
10. lo stato di sessione è preservato durante la navigazione tra report.

---

## 16. Non-obiettivi espliciti

Questo PRD non richiede:
- riscrittura del motore di backtesting;
- revisione del dettaglio trade;
- introduzione di grafici nel `single_policy_report`;
- memorizzazione persistente cross-session;
- sincronizzazione con server o backend.

---

## 17. Nota finale di implementazione

Il sistema richiesto non è una semplice cosmetica del report attuale.

È una riorganizzazione funzionale che mantiene la struttura file-based esistente, ma introduce:
- stato di sessione;
- navigazione coerente;
- confronto globale contestualizzato;
- analisi locale flessibile della singola policy;
- separazione netta tra confronto globale, filtri locali ed esclusioni manuali.
