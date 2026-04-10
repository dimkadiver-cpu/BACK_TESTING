# PRD_REPORT v2 — Policy Report + Comparison Report

## 1. Obiettivo

Definire il sistema di reporting del backtest in modo coerente con due modalità operative:

1. **Run single-policy**
   - l’utente seleziona una sola policy;
   - il sistema esegue il backtest sul dataset scelto;
   - produce il **Policy Report** completo di quella policy.

2. **Run multi-policy**
   - l’utente seleziona due o più policy;
   - il sistema esegue il backtest sullo stesso dataset per tutte le policy selezionate;
   - produce:
     - un **Policy Report singolo per ciascuna policy**;
     - un **Comparison Report HTML sintetico** per confrontare le policy testate sullo stesso dataset.

Il report deve essere leggibile da umano, esportabile in HTML standalone e coerente con gli artifact strutturati CSV/JSON/YAML.

---

## 2. Modalità di esecuzione e output attesi

### 2.1 Single-policy run
Se l’utente seleziona **una sola policy**, il sistema deve produrre:

- `policy_report_complete.html`
- `policy_report.html`
- `policy_summary.json`
- `policy_summary.csv`
- `trade_results.csv`
- `excluded_chains.csv`
- `policy.yaml`
- `trades/<signal_id>/detail.html`
- eventuali artifact per-trade opzionali

### 2.2 Multi-policy run
Se l’utente seleziona **due o più policy**, il sistema deve produrre:

#### A. Un report singolo per ogni policy
Per ciascuna policy:
- directory dedicata;
- stessi artifact previsti per la single-policy run.

#### B. Un report di confronto tra policy
Artifact minimo:
- `comparison_report.html`

Artifact strutturati raccomandati:
- `comparison_summary.json`
- `comparison_summary.csv`

Nota di implementazione:
- il PRD richiede che la run multi-policy sia trattata come **una sola esecuzione logica** sul dataset;
- il parallelismo reale di esecuzione è un requisito desiderato di runtime/ottimizzazione, ma non deve cambiare il contratto degli output.

---

## 3. Comparison Report HTML

### 3.1 Scopo
Il **Comparison Report** deve essere un report sintetico per confrontare più policy testate sullo stesso dataset.

Non deve sostituire i singoli Policy Report.

### 3.2 Contenuto
Il report deve contenere:

#### A. Run metadata
- dataset name
- source DB
- date range
- trader filter
- timeframe
- price basis
- numero policy testate
- timestamp generazione

#### B. Comparison table
Una tabella comparativa con una riga per policy e colonne minime:

- Policy
- Trades
- Excluded chains
- Win rate %
- Net Profit %
- Profit %
- Loss %
- Profit factor
- Expectancy %
- Max drawdown %
- Avg warnings / trade
- Open Policy Report

#### C. Link ai singoli report
Ogni riga deve permettere di aprire il relativo **Policy Report**.

### 3.3 Regole UX
- il report deve essere **sintetico**;
- il focus è il confronto tabellare;
- nessun dettaglio per-trade dentro questo report;
- eventuali grafici sono secondari e opzionali.

---

## 4. Policy Report singolo

Il **Policy Report** resta il report centrale per analizzare una sola policy su un dataset.

### 4.1 Contenuti principali
Deve includere:

- Dataset metadata
- Metadata — policy.yaml values
- Policy Summary
- Excluded chains
- Trade results
- accesso ai Single Trade Report
- accesso ai report di chain/signal

### 4.2 Estensione richiesta
Oltre ai dati riassuntivi dataset-level, il Policy Report deve contenere o collegare chiaramente anche i **report di catena/signal**, così da consentire drill-down operativo completo.

Questo significa che dal Policy Report l’utente deve poter:
- vedere la lista dei trade simulati;
- aprire il dettaglio di ogni trade/signal;
- navigare in modo chiaro tra report principale e report di dettaglio.

---

## 5. Struttura del Policy Report

### 5.1 Titolo
Formato obbligatorio:

`Policy Report - <REPORT_NAME>`

### 5.2 Dataset metadata
Tipo: **collapsible**

Contenuti minimi:
- Dataset name
- Source DB
- Trader filter
- Date range
- Input mode
- Market provider
- Timeframe
- Price basis
- Selected chains
- Simulable chains
- Excluded chains
- Generated at
- Run ID

### 5.3 Metadata — policy.yaml values
Tipo: **collapsible**

Contenuti:
- configurazione caricata da `policy.yaml`;
- mostrata come tabella chiave/valore oppure YAML leggibile.

### 5.4 Policy Summary
Tipo: **sempre visibile**, preferibilmente sticky

Campi minimi obbligatori:
- Policy name
- Total trades
- Win rate %
- Net Profit %
- Profit %
- Loss %
- Profit factor
- Expectancy %
- Max drawdown %
- Avg warnings per trade
- Excluded chains count

Regole:
- tutte le metriche profit/loss mostrate in percentuale dove richiesto;
- nessuna equity curve aggregata in questa sezione;
- visualizzazione leggibile anche su schermi medi.

### 5.5 Excluded chains
Tipo: **collapsible**

Tabella con colonne:
- Signal ID
- Symbol
- Reason
- Note
- Original TEXT

Comportamento:
- `Original TEXT` apre popup/modal;
- il popup mostra il raw text Telegram disponibile.

### 5.6 Trade results
Tipo: **tabella principale sempre visibile**

Colonne obbligatorie:
- Signal ID
- Symbol
- Side
- Status
- Close reason
- Realized PnL %
- Warnings
- Ignored events
- Created
- Closed
- Detail

Regole:
- `Detail` apre il **Single Trade Report** della chain/signal corrispondente;
- `Realized PnL` deve avere resa percentuale chiara;
- la tabella deve restare leggibile anche con dataset grandi.

Requisiti raccomandati:
- ordinamento per colonna;
- filtro rapido per symbol / status / outcome;
- evidenziazione visiva gain/loss.

---

## 6. Single Trade Report — revisione

### 6.1 Obiettivo
Il Single Trade Report deve diventare il report operativo di dettaglio per una singola chain/signal.

### 6.2 Summary minimo
Campi minimi:
- Signal ID
- Symbol
- Side
- Status
- Close reason
- Realized PnL %
- Created
- Closed
- Warnings
- Ignored events
- Entries count
- Avg entry
- Max size
- Fees

### 6.3 Grafico
Il grafico deve essere:

- **interattivo**
- **reale**
- basato sui dati di mercato disponibili
- coerente con le impostazioni definite in GUI

Nota:
- la base interattiva può essere introdotta ora come primo step;
- ulteriori funzioni evolutive del grafico possono essere incrementate in futuro.

### 6.4 Requisiti minimi del grafico
Il grafico deve mostrare, quando disponibili:

- entry
- avg entry
- stop loss iniziale
- move to break even
- move stop successivi
- TP hit
- SL hit
- close

Le label `TP hit` e `SL hit` devono mostrare anche la percentuale.

---

## 7. Event Timeline — revisione

### 7.1 Regola generale
La timeline deve mostrare gli eventi operativi applicati in modo leggibile e utile al debug.

### 7.2 Nuovo comportamento per `NEW_SIGNAL`
Per l’evento `new signal`, il blocco timeline deve mostrare **i dati estratti**, in particolare:

- livelli entry
- stop loss
- take profits

Questi dati devono comparire **al posto** del generico campo `Price reference`.

### 7.3 Raw text
Il pulsante `Open raw telegram text` deve comparire **solo** per eventi che derivano da Telegram, cioè:

- segnali
- update

Non deve comparire per:
- eventi di engine
- eventi sintetici di mercato
- eventi di timeout/collisione/chiusura generati internamente dal simulatore

---

## 8. Normalizzazione del Signal ID

### 8.1 Problema
Il report non deve mostrare `Signal ID` ridondanti o duplicati nel prefisso trader.

Esempio indesiderato:
- `trader_c:trader_c:rm1571`

### 8.2 Requisito
Il sistema deve normalizzare il `Signal ID` in modo che sia:

- univoco,
- leggibile,
- non ridondante.

### 8.3 Regola consigliata
Se `attempt_key` contiene già il prefisso trader, il builder non deve aggiungerlo una seconda volta.

Output desiderato:
- `trader_c:rm1571`
oppure un altro formato unico concordato, ma sempre senza duplicazione.

---

## 9. Requisiti UX

### Comparison Report
- sintetico
- tabellare
- con link ai Policy Report

### Policy Report
- summary leggibile
- drill-down facile verso signal/trade reports

### Single Trade Report
- focalizzato sul singolo trade
- navigazione semplice verso il Policy Report
- grafico reale e interattivo
- timeline utile al debug

---

## 10. Acceptance criteria aggiornati

Il PRD è accettato se:

1. con **una policy** viene prodotto solo il relativo Policy Report;
2. con **due o più policy** vengono prodotti:
   - un Policy Report per ciascuna policy,
   - un Comparison Report sintetico;
3. il Comparison Report contiene una tabella confrontabile e un link al report della policy;
4. il Policy Report contiene anche accesso ai report di chain/signal;
5. il Single Trade Report usa un grafico reale e interattivo, compatibilmente con il market data disponibile;
6. nella Event Timeline del `new signal` compaiono entry, SL e TP estratti;
7. `Open raw telegram text` compare solo per eventi Telegram;
8. il `Signal ID` non contiene duplicazioni tipo `trader_c:trader_c:...`.

---

## 11. Non-goals

Questo sistema di reporting non deve:
- sostituire la logica di simulazione;
- confondere report di confronto con report di singola policy;
- usare il report di confronto per mostrare dettaglio per-trade;
- presentare come “reale” un grafico sintetico.

---

# Delta da colmare

## A. Priorità alta

### A1. Multi-policy run: produrre anche i singoli Policy Report
**Stato attuale**
- la run multi-policy produce un report scenario/confronto aggregato;
- non produce automaticamente anche un Policy Report completo per ciascuna policy.

**Target**
- per ogni policy selezionata, creare una directory dedicata con tutti gli artifact del Policy Report;
- poi creare il `comparison_report.html` che punta a questi report.

**Output attesi**
- `artifacts/comparison/<run_id>/comparison_report.html`
- `artifacts/comparison/<run_id>/<policy_name>/policy_report.html`
- relativi CSV/JSON/YAML per ogni policy

### A2. Fix Signal ID duplicato
**Problema**
- possibile costruzione ridondante del tipo `trader_c:trader_c:rm1571`.

**Target**
- normalizzare il builder per evitare la doppia prefissazione del trader.

**Regola minima**
- se `attempt_key` inizia già con `trader_id:`, non aggiungerlo di nuovo.

### A3. Event Timeline: raw text solo per eventi Telegram
**Problema**
- il pulsante `Open raw telegram text` può comparire anche per eventi generati internamente dal motore.

**Target**
- mostrare il pulsante solo per eventi con origine Telegram/trader;
- non mostrarlo per eventi `ENGINE` o altri eventi sintetici.

### A4. NEW_SIGNAL: mostrare entry / SL / TP estratti
**Problema**
- il `new signal` usa un riferimento prezzo troppo generico.

**Target**
- sostituire `Price reference` con i dati estratti realmente utili:
  - entry
  - stop loss
  - take profits

---

## B. Priorità media

### B1. Comparison Report sintetico definitivo
**Target**
- tabella chiara con metriche principali;
- link al report della policy;
- eventuali grafici solo secondari.

### B2. Policy Report: collegamento chiaro ai report chain/signal
**Target**
- rendere esplicita la navigazione dal livello dataset al livello trade/signal.

### B3. Trade table UX
**Target**
- sorting;
- filtri;
- migliore leggibilità su dataset grandi.

---

## C. Priorità evolutiva

### C1. Single Trade chart reale e interattivo
**Stato attuale desiderato**
- il target è un grafico reale con base market data.

**Target finale**
- candlestick reali;
- overlay entry/SL/TP/BE/close;
- interazione base;
- coerenza con impostazioni GUI.

### C2. Evoluzione del grafico
**Futuro**
- aggiungere funzioni incrementali senza cambiare il contratto del report:
  - zoom e pan;
  - tooltip avanzati;
  - toggle marker;
  - selezione timeframe grafico;
  - evidenziazione eventi timeline sul grafico.

---

## D. Piano operativo consigliato

### Fase 1 — Allineamento output e naming
- produrre Policy Report per ogni policy nella run multi-policy;
- creare Comparison Report dedicato;
- fissare naming directory/file.

### Fase 2 — Correzioni funzionali immediate
- fix Signal ID;
- filtrare correttamente `Open raw telegram text`;
- migliorare `NEW_SIGNAL` nella timeline.

### Fase 3 — UX e drill-down
- migliorare tabella trade;
- rendere più chiari i link ai report di dettaglio.

### Fase 4 — Grafico reale/interattivo
- introdurre base grafica reale;
- poi incrementare le funzioni interattive.

---

## E. Sintesi finale

Il sistema di reporting desiderato deve comportarsi così:

- **1 policy selezionata** → produce il **Policy Report** completo della policy;
- **2 o più policy selezionate** → produce:
  - i **Policy Report singoli** per ogni policy,
  - un **Comparison Report HTML sintetico** con tabella comparativa e link ai report;
- il **Policy Report** resta il report principale per analizzare una policy;
- il **Single Trade Report** diventa il report operativo di dettaglio con grafico reale/interattivo come target evolutivo;
- la timeline deve essere più utile al debug:
  - `NEW_SIGNAL` con livelli estratti,
  - raw text solo per eventi Telegram,
  - niente rumore da eventi interni del motore.
