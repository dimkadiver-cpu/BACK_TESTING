# Signal Chain Lab — UX_REFERENCE definitivo

## Scopo

Questo documento definisce la UX target della GUI di Signal Chain Lab, riallineata al mockup fornito, alle note utente e alla struttura funzionale desiderata.

Questo file **non descrive semplicemente il codice attuale**: descrive il comportamento UX/UI da considerare come riferimento finale per il redesign del blocco GUI.

Principi guida:

- la GUI è composta da moduli indipendenti;
- il tab 3 unifica logicamente **Market Data** e **Backtesting**;
- il backtest non dipende dalla validazione completa del dataset, ma dalla **copertura richiesta**;
- nei punti in cui il codice attuale diverge, questo documento definisce il comportamento target;
- i campi e le scelte principali dell’utente devono essere ricordati tra riaperture della GUI.

---

## 1. Struttura generale

### 1.1 Architettura della GUI

La GUI è organizzata in 3 tab principali sempre accessibili:

1. **Download**
2. **Parse**
3. **Market Data & Backtest**

Non è un wizard. I tab non vengono bloccati in base allo stato degli altri moduli. Ogni blocco resta navigabile in modo indipendente.

### 1.2 Tab 3 — struttura interna

Il tab **Market Data & Backtest** è composto da:

1. **Contesto condiviso** collassabile
2. **Card contenitore** con due sub-tab:
   - **Market Data**
   - **Backtesting**

Questa è la struttura UX target anche se il codice attuale è ancora organizzato in pannelli separati.

### 1.3 Contesto condiviso

Il contesto condiviso è la base logica comune sia per Market Data sia per Backtesting.

Contiene:

- **DB parsato selezionato**
- **Trader filter**
- **Dal / Al**
- **Max trades**
- **Cartella Market Data**

Quando il contenitore è collassato deve mostrare una riga riassuntiva compatta, leggibile, con almeno:

- nome DB selezionato
- intervallo date attivo
- trader filter attivo
- cartella Market Data attiva

---

## 2. Persistenza dello stato UI tra sessioni

## 2.1 Obiettivo

La GUI deve ricordare l’ultima sessione utente anche dopo chiusura della GUI o riavvio dello script.

Devono essere persistiti almeno i seguenti valori:

- DB parsato selezionato
- cartella Market Data
- source/provider
- price basis
- download TF
- simulation TF
- detail TF
- data types
- buffer settings
- filtri Backtest
- policy selezionate
- cartella report
- validate mode
- opzione nuova directory / path nuova directory

## 2.2 Soluzione scelta

La persistenza va realizzata tramite **file JSON locale per utente**, esterno allo stato volatile della GUI.

Percorso consigliato:

- **Windows:** `%APPDATA%/SignalChainLab/ui_state.json`
- **Linux/macOS:** `~/.config/signal_chain_lab/ui_state.json`

## 2.3 Regole di salvataggio

- salvataggio automatico ad ogni modifica rilevante dei controlli principali;
- salvataggio anche alla chiusura pulita della GUI;
- caricamento automatico all’avvio;
- se un path salvato non esiste più, il valore resta mostrato ma marcato come non valido finché l’utente non lo corregge;
- il file di persistenza non deve contenere segreti sensibili non necessari.

## 2.4 Segreti e credenziali

La persistenza dello stato UI è separata dalla persistenza delle credenziali Telegram.

Le credenziali Telegram e la sessione Telethon possono continuare ad usare i meccanismi dedicati già previsti (`.env`, `.session`), mentre `ui_state.json` deve contenere solo stato di interfaccia e ultimi valori usati.

---

## 3. Tab 01 — Download

## 3.1 Scopo

Questo tab serve a scaricare i messaggi Telegram in un DB SQLite da usare poi nei moduli successivi.

## 3.2 Sezioni principali

### Sessione Telegram

Deve mostrare:

- stato sessione attiva/non attiva;
- path sessione attuale;
- possibilità di aprire il pannello credenziali/OTP.

Pannello credenziali:

- API_ID
- API_HASH
- Telefono
- OTP (visibile dopo richiesta codice)
- bottone invio OTP
- bottone conferma OTP
- bottone reset sessione

### Sorgente

Campi:

- **Chat ID**
- **Topic ID** opzionale
- chip riassuntivo sorgente composto dinamicamente

### Periodo download

Controlli:

- toggle **Scarica tutto lo storico**
- se OFF: campi **Dal** e **Al**
- radio contenuto:
  - Solo testo
  - Testo + immagini

### Output

Campi:

- cartella output DB
- bottone Sfoglia

### Risultato download

Dopo il completamento deve mostrare almeno:

- numero messaggi
- numero messaggi con media
- numero image blob
- dimensione DB
- path DB creato

## 3.3 Azioni Download

Bottoni previsti:

- **Esegui Download**
- **Arresta**
- **Usa come DB attivo**
- **Elimina DB**

## 3.4 Log Download

Deve essere collassabile ed evidenziare:

- comando eseguito
- progress di scaricamento
- warning
- errori
- esito finale

---

## 4. Tab 02 — Parse

## 4.1 Scopo

Questo tab ricostruisce segnali e chain operative a partire dal DB Telegram scaricato.

## 4.2 Sezioni principali

### Database sorgente

Campi:

- file DB `.sqlite3`
- bottone Sfoglia
- chip riepilogo con nome file e conteggio messaggi

### Configurazione

Campi:

- **Trader profile**
- toggle **Esporta CSV**

### Stato modulo

Tre card informative:

- **Parse**
- **Chain Builder**
- **Backtest Readiness**

### Top warnings

Tabella compatta con:

- tipo warning
- count
- esempio

## 4.3 Azioni Parse

Bottoni previsti:

- **Esegui Parse**
- **Arresta**
- **Apri report qualità**
- **Esporta CSV**

## 4.4 Log Parse

Come nel Download, collassabile, con evidenza di:

- step del parser
- warning
- chain costruite
- risultato finale

---

## 5. Tab 03 — Contesto condiviso

## 5.1 Database segnali

Campo per selezione del DB parsato da usare nei moduli del tab 3.

Controlli:

- input path DB
- bottone Sfoglia

## 5.2 Filtri dataset

Controlli:

- **Trader filter**
- **Dal**
- **Al**
- **Max trades**

Questi filtri sono comuni a Market Data e Backtest.

## 5.3 Cartella Market Data

Controlli:

- path cartella Market Data
- bottone Sfoglia
- chip/notice con contenuto rilevato dalla cartella, se disponibile

La cartella Market Data è parte del contesto condiviso, non un parametro isolato del solo pannello Market Data.

---

## 6. Sub-tab Market Data

## 6.1 Scopo

Serve per:

- analizzare i simboli e gli intervalli necessari;
- verificare la copertura del dataset richiesto;
- scaricare i dati mancanti;
- validare il dataset quando richiesto;
- preparare il dataset per il backtest.

## 6.2 Controlli base

### Source / Provider

Opzioni target:

- `bybit`
- `fixture`

### Validate mode

Opzioni finali:

- **GAPs**
- **OFF**

Non devono comparire in UX finale opzioni `Full / Light / Off`.

### Semantica di Validate mode

#### OFF

`OFF` significa:

- planner + sync dei dati mancanti;
- nessuna validazione automatica;
- quindi, in pratica: **solo integrazione dei mancanti**.

#### GAPs

`GAPs` significa:

- planner + sync dei dati mancanti;
- `gap_validate`;
- **non** include `validate_full`.

### Price basis

Campo separato con opzioni:

- `last`
- `mark`

Il `price basis` resta concettualmente separato dai `data types`.

## 6.3 Download TF

Controllo multi-select.

Timeframe supportati a livello UX target:

- `1m`
- `5m`
- `15m`
- `30m`
- `1h`
- `2h`
- `4h`
- `6h`
- `12h`
- `1d`
- `1w`

Il trigger deve mostrare il riepilogo dei TF selezionati.

## 6.4 Data types

Modello concettuale finale:

- `Perp`
- `Spot`
- `Funding rate`

La logica `OHLCV last / OHLCV mark / Funding rate` non è la UX target finale.

`last/mark` devono restare una scelta separata nel campo **Price basis**.

### Data types roadmap

Le voci future possono esistere come roadmap disabilitata, ma non devono essere presentate come dati già supportati nel flusso operativo principale se non lo sono realmente.

## 6.5 Buffer mode

Il controllo resta:

- `auto`
- `manual`

Se `manual`, devono comparire campi di buffer con unità in **giorni**, non in ore.

Quindi la UX finale usa buffer in giorni.

I preset eventuali presenti nel codice attuale non fanno parte del mockup finale a meno di reintroduzione esplicita futura.

## 6.6 Nuova directory

Il controllo finale deve essere un **toggle**, non una coppia radio.

Semantica:

- OFF → usa la cartella Market Data esistente e integra i dati mancanti lì;
- ON → scarica/prepara i dati in una nuova directory specificata dall’utente.

Quando il toggle è ON, devono comparire:

- input path nuova directory
- bottone Sfoglia

## 6.7 Coverage

La sezione Coverage deve esistere nel sub-tab Market Data.

Metriche minime:

- **Simboli**
- **Intervalli richiesti**
- **Gap**
- **Copertura %**

Questa sezione è centrale perché il gating del backtest dipende dalla copertura richiesta.

## 6.8 Azioni Market Data

Bottoni finali previsti:

- **Analizza**
- **Prepara**
- **Valida**
- **Arresta**

### Semantica azioni

#### Analizza

Esegue solo l’analisi/planner e aggiorna la sezione Coverage.

#### Prepara

Esegue:

- planner
- sync dei dati mancanti
- eventuale `gap_validate` se `Validate mode = GAPs`

`Prepara` **non** esegue `validate_full`.

#### Valida

Esegue la validazione del dataset selezionato, ma **solo sui dati non ancora validati**.

#### Arresta

Interrompe il processo in corso.

## 6.9 Validate full

`validate_full` esiste come azione separata richiamata dal bottone **Valida**.

Deve partire:

- quando l’utente clicca **Valida**;
- oppure quando in futuro un flusso esplicito lo richiederà.

Non deve essere implicito dentro `GAPs`.

## 6.10 Bottoni esclusi dal design finale

Il bottone **Prepara + Valida** non fa parte della UX finale.

---

## 7. Sub-tab Backtesting

## 7.1 Scopo

Serve a lanciare il backtest sulle chain filtrate, usando il dataset Market Data già disponibile o sufficientemente coperto.

## 7.2 Notice iniziale

Il sub-tab deve ricordare che:

- **Market source**
- **Price basis**

sono auto-rilevati dalla cartella Market Data.

## 7.3 Policy

Controllo multi-select per le policy.

Regola operativa:

- **1 policy** → run singolo
- **2 o più policy** → confronto/scenario

## 7.4 Timeout

L’unità UX finale è in **minuti**, non in secondi.

Label target:

- `Timeout (m)`

## 7.5 Report output dir

Campo selezionabile con bottone Sfoglia.

Il path deve essere persistito tra sessioni.

## 7.6 Parametri simulazione

Questi campi appartengono al sub-tab **Backtesting**, non a Market Data:

- **Simulation TF**
- **Detail TF**

Questa collocazione segue il mockup finale.

## 7.7 Market source / Price basis nel Backtesting

Nel Backtesting devono comparire come campi **solo display** auto-rilevati dalla cartella Market Data.

Quindi:

- sono visibili all’utente come informazione;
- non sono controlli editabili nel pannello Backtesting;
- l’utente li gestisce indirettamente dal contesto/Market Data, non da qui.

## 7.8 Policy Studio

Può restare come sezione collassabile interna al sub-tab Backtesting.

Funzioni previste:

- visualizzare/editare YAML della policy;
- salvare;
- salvare come nuova;
- creare nuova policy;
- ricaricare lista.

## 7.9 Azioni Backtest

Bottoni finali previsti, come da mockup:

- **Esegui Backtest**
- **Arresta**
- **Apri report HTML**
- **Artifact dir**

## 7.10 Risultati Backtest

La forma finale dei risultati deve essere **tabellare**, non a card summary.

Colonne target:

- **Policy**
- **Trades**
- **Excluded**
- **PnL %**
- **Win rate**
- **Expectancy**
- **Report**

La tabella deve essere compatta e leggibile e permettere l’apertura rapida del report corrispondente.

---

## 8. Gating del Backtest

## 8.1 Regola finale

Il backtest deve usare gating **copertura-only**, non blocco rigido su `market_ready`.

## 8.2 Significato operativo

Quando l’utente clicca **Esegui Backtest**, il sistema deve:

1. verificare la copertura richiesta del dataset;
2. mostrare log/check dedicato;
3. se la copertura è sufficiente, consentire il run anche se il dataset non è stato validato completamente;
4. bloccare il run solo se restano gap mancanti incompatibili con la copertura richiesta.

## 8.3 Conseguenze UX

- la validazione completa non è prerequisito assoluto per il backtest;
- `market_ready` non deve essere l’unico gate bloccante lato UX;
- il controllo rilevante da esporre all’utente è la **copertura effettiva**.

---

## 9. Log e osservabilità

## 9.1 Regole generali

Ogni blocco operativo deve avere log dedicato:

- Download
- Parse
- Market Data
- Backtest

## 9.2 Requisiti UX dei log

I log devono essere:

- collassabili;
- leggibili;
- con evidenza chiara di comando, progress, warning, errori, esito finale;
- coerenti nel layout tra i moduli.

## 9.3 Market Data

Nel blocco Market Data il log deve essere sufficientemente dettagliato per mostrare:

- analisi simboli;
- intervalli richiesti;
- gap trovati;
- sync in corso;
- eventuale gap validation;
- eventuale validate full;
- esito finale.

## 9.4 Backtest

Nel blocco Backtest il log deve mostrare almeno:

- policy caricate;
- numero trade simulati;
- eventuali esclusi;
- PnL / win rate / expectancy se disponibili;
- path report/artifact finali.

---

## 10. Elementi esplicitamente esclusi dalla UX finale

Questi elementi non fanno parte del riferimento UX finale:

- `Validate mode = Full / Light / Off`
- bottone `Prepara + Valida`
- collocazione di `Simulation TF` / `Detail TF` nel pannello Market Data
- modello concettuale `OHLCV last / OHLCV mark / Funding rate` come sostituto dei data types UX
- timeout in secondi come unità UI finale
- gating del backtest basato unicamente su `market_ready`
- risultati presentati solo come card summary al posto della tabella finale

---

## 11. Riepilogo decisioni finali

### Market Data

- Validate mode finale: **GAPs / OFF**
- `GAPs` include `gap_validate` ma **non** `validate_full`
- `OFF` significa **solo sync mancanti**
- bottone `Prepara + Valida`: **assente**
- data types finali: **Perp / Spot / Funding rate**
- `last/mark`: **separati** in `Price basis`
- buffer: **giorni**
- nuova directory: **toggle**

### Backtesting

- `Simulation TF` e `Detail TF`: **nel Backtesting**
- timeout: **minuti**
- gating: **copertura-only**
- `Market source` / `Price basis` nel Backtesting: **solo display**
- risultati: **tabella mockup**
- bottoni finali: **come da mockup**

### Persistenza

- stato UI salvato in **JSON locale per utente**
- caricamento automatico all’avvio
- persistenza separata dalle credenziali Telegram

---

## 12. Nota finale di implementazione

Questo file può essere usato come riferimento diretto per:

- rifacimento della GUI;
- riallineamento di `UX_REFERENCE.md` del repo;
- apertura task di implementazione UI/UX;
- controllo di conformità tra mockup, codice e comportamento target.

Se il codice attuale diverge da questo documento, fa fede questo documento come riferimento UX target.
