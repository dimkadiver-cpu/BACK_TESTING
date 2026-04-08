# PRD — Sottosistema di caricamento dati storici per backtesting

## 1. Scopo del documento

Definire requisiti, logica, flusso operativo e criteri di accettazione per il sottosistema di **acquisizione, pianificazione, caching, aggiornamento e validazione dei dati di mercato storici** usati dal motore di backtesting del progetto.

Questo PRD copre il **market data layer** necessario per produrre backtest con PnL reale e riutilizzabile nel tempo, con focus su:
- accuratezza elevata;
- dati gratuiti;
- riuso locale dei dataset;
- aggiornamento incrementale;
- compatibilità con più dataset segnali;
- supporto prioritario a **futures linear**.

---

## 2. Contesto e problema

Il progetto usa un backtesting event-driven basato su segnali e update provenienti da dataset strutturati. Per ottenere PnL reale non è sufficiente il replay degli eventi: serve un provider di dati storici di mercato che consenta di simulare fill, hit di SL/TP, break-even, parziali e timeout.

Il problema da risolvere non è semplicemente “scaricare dati storici”, ma scaricare **solo i dati necessari**, mantenerli in una struttura locale persistente, aggiornarli senza duplicazioni e renderli disponibili al simulatore in modo efficiente e deterministico.

---

## 3. Obiettivi di prodotto

### 3.1 Obiettivi principali
- Consentire backtest con PnL reale usando dati OHLCV storici gratuiti.
- Minimizzare download inutili tramite pianificazione basata sul DB segnali.
- Costruire un archivio locale incrementale riutilizzabile nel tempo.
- Supportare molte iterazioni di scenario e ottimizzazione sugli stessi dati.
- Gestire l’estensione del dataset quando arrivano nuovi segnali, nuovi simboli o nuovi periodi temporali.
- Fornire una base solida per il motore di simulazione e per future ottimizzazioni.

### 3.2 Obiettivi secondari
- Ridurre l’uso delle API e il rischio di rate limit.
- Consentire analisi ripetibili e deterministiche offline.
- Separare il più possibile il layer dati dal layer simulazione.

---

## 4. Non obiettivi

Il presente PRD **non** copre:
- la logica completa del motore di backtest;
- la logica di esecuzione ordini live;
- il costo trading, funding, slippage avanzato o commissioni reali multi-exchange;
- dati tick-level a pagamento;
- supporto iniziale a tutti i mercati contemporaneamente;
- un data lake universale dell’intero exchange.

---

## 5. Decisioni di prodotto già fissate

Sulla base delle scelte utente emerse:

- Priorità: **massima accuratezza**.
- Mercato prioritario: **futures linear**.
- Simboli da scaricare: **solo quelli presenti nel DB segnali**.
- Strategia dataset: **dataset lungo e aggiornabile nel tempo**.
- Granularità: **timeframe gratuito più fine sostenibile**.
- Momento di caricamento: **pianificazione iniziale (planner)**.
- Uso atteso: **molte iterazioni di ottimizzazione/backtest**.
- Vincolo forte: **non pagare per i dati**.
- Formato storage: guidato da efficienza, non da preferenze esterne.

---

## 6. Visione della soluzione

La soluzione sarà composta da quattro blocchi principali:

1. **Signal Demand Scanner**
   - legge il DB segnali;
   - individua simboli, timeframe necessari, date e durata potenziale delle chain.

2. **Coverage Planner**
   - converte i segnali in intervalli temporali richiesti;
   - applica buffer adattivi;
   - unisce intervalli vicini o sovrapposti;
   - produce un piano di copertura per simbolo/mercato/timeframe.

3. **Persistent Market Cache**
   - archivio locale incrementale in `data/market/`;
   - salva i dati in partizioni aggiornabili;
   - mantiene metadati di copertura e integrità.

4. **Downloader + Validator**
   - confronta piano richiesto con copertura già presente;
   - scarica solo i buchi mancanti;
   - valida il contenuto;
   - aggiorna manifest e indice di copertura.

---

## 7. Flusso end-to-end

### 7.1 Flusso logico
1. Lettura del DB segnali.
2. Estrazione delle chain e dei timestamp rilevanti.
3. Calcolo del fabbisogno dati per chain.
4. Merge degli intervalli per simbolo.
5. Confronto con archivio locale già presente.
6. Identificazione dei gap.
7. Download dei soli gap.
8. Validazione e persistenza.
9. Aggiornamento del manifest.
10. Esposizione dei dati al motore di backtest.

### 7.2 Flusso desiderato a runtime
- Il download non deve essere la modalità normale durante il backtest.
- Il backtest deve leggere **prevalentemente da cache locale**.
- Eventuali estensioni runtime devono essere eccezionali e controllate.

---

## 8. Requisiti funzionali

### RF-1 — Scansione dei simboli dal DB
Il sistema deve leggere il DB dei segnali e identificare con precisione:
- simbolo;
- mercato/logica di esecuzione attesa;
- timestamp di apertura segnale;
- timestamp dell’ultimo update disponibile;
- stato della chain;
- eventuali informazioni utili per inferire la durata prevista.

### RF-2 — Universo simboli derivato dal DB
Il sistema deve scaricare solo i simboli realmente presenti nei dataset segnali selezionati.

### RF-3 — Pianificazione temporale adattiva
Il sistema deve costruire finestre temporali per ciascuna chain usando una logica adattiva.

#### RF-3.1 — Chain con update completi
Per chain con update noti:
- `required_start = timestamp_open - pre_buffer`
- `required_end = timestamp_last_relevant_update + post_buffer`

#### RF-3.2 — Chain senza update o incomplete
Per chain incomplete il sistema deve stimare una finestra iniziale usando classi di durata configurabili.

#### RF-3.3 — Estensione automatica
Se un trade arriva al bordo della finestra disponibile e non è chiuso, il sistema deve poter richiedere un’estensione a blocchi temporali configurabili.

### RF-4 — Buffer adattivi configurabili
Il sistema deve supportare buffer temporali differenziati per classi di durata.

Valori iniziali consigliati:
- **intraday**: pre 12–24h, post 2–3 giorni;
- **swing**: pre 1–2 giorni, post 7–14 giorni;
- **position**: pre 3–5 giorni, post 21–45 giorni;
- **default sconosciuto**: pre 2 giorni, post 14 giorni.

### RF-5 — Merge intervalli per simbolo
Il sistema deve unire automaticamente gli intervalli temporali:
- sovrapposti;
- adiacenti;
- vicini entro una soglia configurabile.

Obiettivo: evitare micro-download frammentati.

### RF-6 — Confronto con copertura esistente
Il sistema deve mantenere un indice di copertura locale e confrontare il piano richiesto con i dati già disponibili per determinare i soli gap mancanti.

### RF-7 — Download incrementale
Il sistema deve scaricare solo:
- simboli mancanti;
- periodi mancanti;
- estensioni temporali mancanti.

### RF-8 — Archivio persistente locale
I dati devono essere mantenuti in una cache locale persistente, non temporanea.

### RF-9 — Granularità dati prioritaria
Il sistema deve usare come base un timeframe fine gratuito, considerato il riferimento principale per la simulazione.

### RF-10 — Derivazione opzionale timeframe aggregati
Il sistema può supportare la derivazione locale di timeframe superiori a partire da quello base, per evitare download multipli non necessari.

### RF-11 — Validazione dati scaricati
Dopo ogni download il sistema deve verificare almeno:
- ordinamento temporale;
- assenza di duplicati;
- struttura schema corretta;
- continuità minima attesa;
- presenza di dati nel range richiesto.

### RF-12 — Manifest di copertura
Il sistema deve mantenere un manifest che tracci:
- exchange;
- market type;
- timeframe;
- simbolo;
- intervalli coperti;
- stato validazione;
- timestamp ultimo aggiornamento;
- origine download.

### RF-13 — Supporto a nuovi dataset segnali
Quando viene analizzato un nuovo dataset segnali, il sistema deve essere in grado di:
- riutilizzare i dati già presenti;
- aggiungere simboli nuovi;
- aggiungere solo i periodi mancanti.

### RF-14 — Modalità offline-first
Una volta preparata la cache, il backtest deve poter operare offline rispetto alla fonte dati esterna, salvo update esplicito.

---

## 9. Requisiti non funzionali

### RNF-1 — Accuratezza
Il sistema deve privilegiare accuratezza e completezza dei dati rispetto alla velocità di bootstrap iniziale.

### RNF-2 — Ripetibilità
A parità di dataset segnali e cache locale validata, il piano di copertura e i dati forniti al simulatore devono essere deterministici.

### RNF-3 — Efficienza
Il sistema deve minimizzare download ridondanti e letture inutili.

### RNF-4 — Estendibilità
La soluzione deve essere facilmente estendibile a spot o altri mercati in fasi successive.

### RNF-5 — Tracciabilità
Ogni operazione di download/aggiornamento deve essere loggabile e riconducibile a un set di richieste esplicito.

### RNF-6 — Manutenibilità
La struttura deve restare comprensibile, ispezionabile e riparabile manualmente in caso di problemi.

---

## 10. Struttura storage proposta

### 10.1 Struttura directory

```text
/data/
  market/
    <exchange>/
      futures_linear/
        <base_timeframe>/
          <SYMBOL>/
            2025-01.parquet
            2025-02.parquet
            2025-03.parquet
      spot/
        <base_timeframe>/
          <SYMBOL>/
            ...
    manifests/
      coverage_index.json
      download_log.json
      validation_log.json
```

### 10.2 Motivazione
Questa struttura consente:
- aggiunta facile di mesi mancanti;
- separazione per exchange/mercato/timeframe;
- riuso pulito dei dataset;
- verifica più semplice della copertura;
- riduzione del rischio di corruzione di un monolite unico.

### 10.3 Formato file
Formato consigliato: **Parquet**.

Motivazioni:
- compressione efficiente;
- lettura rapida;
- schema consistente;
- adatto a partizionamento temporale.

CSV può essere ammesso solo come fallback/debug, non come storage primario.

---

## 11. Manifest e indice di copertura

### 11.1 Coverage index
Il `coverage_index.json` deve rappresentare almeno:
- exchange;
- market_type;
- timeframe;
- symbol;
- lista di partizioni disponibili;
- intervalli coperti consolidati;
- ultimo aggiornamento;
- stato validazione.

### 11.2 Download log
Il `download_log.json` deve tracciare:
- job id;
- richiesta originaria;
- simboli coinvolti;
- range richiesti;
- range realmente scaricati;
- esito;
- errori;
- timestamp.

### 11.3 Validation log
Il `validation_log.json` deve tracciare:
- file validati;
- controlli effettuati;
- warning;
- eventuali mismatch o gap.

---

## 12. Algoritmo di pianificazione richiesto

### 12.1 Input
Input minimo:
- dataset segnali selezionato;
- configurazione exchange/market/timeframe;
- regole di buffer;
- soglia merge intervalli;
- configurazione estensione finestra.

### 12.2 Output
Output del planner:
- lista simboli richiesti;
- per simbolo, lista intervalli necessari;
- per simbolo, lista intervalli mancanti dopo confronto con cache;
- piano finale di download.

### 12.3 Pseudoflusso planner
1. Carica chain dal DB.
2. Per ogni chain, calcola `required_start` e `required_end`.
3. Raggruppa per simbolo.
4. Esegui merge intervalli.
5. Carica coverage locale.
6. Sottrai intervalli già coperti.
7. Produci lista gap.
8. Restituisci piano finale.

---

## 13. Regole di buffer e durata trade

### 13.1 Classificazione durata
Il sistema dovrebbe supportare una classificazione della durata in una delle seguenti classi:
- intraday;
- swing;
- position;
- unknown.

### 13.2 Fonti per la classificazione
Ordine suggerito:
1. metadati espliciti presenti nel segnale;
2. evidenza derivata dalla chain storica;
3. configurazione per canale/trader;
4. fallback `unknown`.

### 13.3 Regole default
Valori iniziali:
- intraday: pre 1 giorno, post 3 giorni;
- swing: pre 2 giorni, post 14 giorni;
- position: pre 5 giorni, post 30 giorni;
- unknown: pre 2 giorni, post 14 giorni.

### 13.4 Estensione progressiva
Se a fine finestra il trade è ancora aperto:
- estendi di un blocco configurabile;
- ripeti fino a chiusura o fino a limite massimo configurato.

---

## 14. Fonte dati gratuita

### 14.1 Vincolo
Il sistema deve essere progettato per usare **fonti dati gratuite**, accettando i limiti tipici di:
- profondità storica;
- granularità disponibile;
- rate limit;
- stabilità della API.

### 14.2 Obiettivo architetturale
Il sistema non deve dipendere da un provider unico a livello concettuale. Deve essere possibile sostituire il downloader mantenendo invariati:
- planner;
- storage;
- manifest;
- interfaccia verso il simulatore.

---

## 15. Interfacce applicative richieste

### 15.1 Comando di pianificazione
Un comando deve permettere di generare un piano senza scaricare nulla.

Esempio concettuale:
- `plan-market-data --dataset <id> --market futures_linear --timeframe <tf>`

Output atteso:
- simboli richiesti;
- intervalli richiesti;
- gap rispetto alla cache;
- stima volume download.

### 15.2 Comando di sync
Un comando deve eseguire il download dei gap e aggiornare la cache.

### 15.3 Comando di validazione
Un comando deve verificare consistenza e copertura della cache.

### 15.4 Comando di report coverage
Un comando deve mostrare in modo leggibile:
- copertura per simbolo;
- buchi residui;
- ultima sincronizzazione.

---

## 16. Regole di interazione con il backtester

### 16.1 Separazione di responsabilità
Il backtester non deve essere responsabile del download dati come flusso principale.

### 16.2 Input al backtester
Il backtester deve ricevere un provider che legga dal market store locale.

### 16.3 Gestione mancanza dati
Se una chain richiede dati non presenti:
- comportamento di default: errore esplicito o esclusione controllata con warning;
- comportamento opzionale: richiesta estensione guidata.

---

## 17. Error handling

Il sistema deve gestire esplicitamente:
- simbolo non disponibile sulla fonte dati;
- partizioni corrotte;
- rate limit;
- gap temporali inaspettati;
- incongruenze schema;
- dati duplicati;
- copertura insufficiente per una chain.

Ogni errore deve produrre:
- log tecnico;
- stato job;
- possibilità di retry controllato.

---

## 18. Metriche di qualità del sottosistema

### Metriche minime
- percentuale chain completamente coperte;
- percentuale download riutilizzati da cache;
- numero simboli unici coperti;
- numero gap rilevati;
- numero gap risolti;
- tempo medio di pianificazione;
- tempo medio di sync;
- volume dati scaricato per dataset;
- tasso di validazione passata/fallita.

---

## 19. Criteri di accettazione

Il sottosistema sarà considerato accettato quando:

### CA-1
Dato un dataset segnali, il sistema produce una lista corretta di simboli richiesti.

### CA-2
Per ogni simbolo, il sistema costruisce correttamente gli intervalli temporali necessari usando regole adattive.

### CA-3
Intervalli sovrapposti o vicini vengono fusi correttamente.

### CA-4
Il sistema identifica correttamente i gap rispetto alla cache locale.

### CA-5
Il sistema scarica soltanto i gap mancanti, senza duplicare i dati già presenti.

### CA-6
I file scaricati vengono validati e registrati nel manifest.

### CA-7
Un secondo run sullo stesso dataset non deve riscaricare partizioni già coperte.

### CA-8
Un nuovo dataset con simboli aggiuntivi deve causare il download solo dei nuovi simboli o dei nuovi periodi.

### CA-9
Il backtester deve poter usare la cache locale senza dipendere da download live obbligatori.

### CA-10
Le chain fuori copertura devono essere rilevate e riportate in modo esplicito.

---

## 20. Priorità di rilascio

### Fase 1 — MVP funzionale
- scansione DB;
- planner;
- merge intervalli;
- storage locale per simbolo/mese;
- manifest base;
- downloader incrementale;
- validazione minima;
- provider locale per backtest.

### Fase 2 — Hardening
- estensione automatica finestre;
- report coverage;
- validazione avanzata;
- retry/rate limit management;
- derivazione timeframe superiori.

### Fase 3 — Evoluzione
- supporto spot;
- più fonti dati gratuite;
- politiche di ricostruzione automatica cache;
- metriche avanzate e dashboard.

---

## 21. Rischi principali

- Dati gratuiti con copertura storica insufficiente.
- Rate limit o instabilità del provider.
- Ambiguità nel classificare intraday/swing/position.
- Partizioni incomplete o corrotte.
- Complessità crescente del manifest se non ben progettato.
- Divergenza tra fabbisogno reale del simulatore e dati effettivamente pianificati.

---

## 22. Assunzioni

- Il DB segnali contiene informazioni sufficienti per derivare simbolo e timestamp di apertura.
- Esiste o verrà creato un formato chain sufficientemente stabile per derivare finestre temporali.
- Il motore di backtest userà un market provider leggente da storage locale.
- La granularità gratuita disponibile sarà adeguata per una simulazione abbastanza accurata del PnL.

---

## 23. Decisione finale di prodotto

Il progetto adotterà un sottosistema di market data con queste proprietà:

- **planner iniziale basato sul DB**;
- **cache locale persistente incrementale**;
- **download solo dei gap mancanti**;
- **supporto prioritario a futures linear**;
- **timeframe base fine e gratuito**;
- **finestre adattive per durata trade**;
- **storage partizionato per simbolo e periodo**;
- **manifest di copertura e validazione**.

Questa architettura è la soluzione raccomandata per un backtesting accurato, riutilizzabile, economico e scalabile rispetto ai futuri dataset segnali.

---

## 24. Prossimo artefatto consigliato

Dopo l’approvazione di questo PRD, il documento successivo da produrre dovrebbe essere un **Technical Blueprint** con:
- moduli Python;
- classi;
- schema file;
- interfacce provider;
- formato manifest;
- CLI commands;
- piano di implementazione a fasi.
