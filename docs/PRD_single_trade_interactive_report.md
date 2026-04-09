# PRD — Single Trade Interactive HTML Report

## 1. Obiettivo

Integrare nel progetto `BACK_TESTING` un nuovo **report HTML di dettaglio del singolo trade** con **grafico interattivo candlestick** basato su **Apache ECharts**, utilizzando i **dati OHLCV del backtest** e gli **eventi operativi del trade**.

L’obiettivo è sostituire o affiancare l’attuale rappresentazione statica con una vista molto più utile per l’analisi operativa del singolo trade.

---

## 2. Problema attuale

Attualmente il sistema genera report HTML e artifact visuali, ma il dettaglio del trade non mostra ancora un **grafico di mercato interattivo** con:

- candele OHLCV
- livello di entry
- stop loss
- take profit
- break even
- eventi operativi del trade

Questo limita la leggibilità del trade e rende più difficile capire **come il mercato si sia mosso rispetto alla gestione operativa della posizione**.

---

## 3. Outcome atteso

Produrre un **Single Trade HTML Report** che mostri:

- andamento del mercato a candele
- overlay dei livelli operativi del trade
- marker degli eventi principali
- tooltip interattivi
- zoom e pan
- funzionamento completamente offline

---

## 4. Ambito

### In scope
Questa iniziativa copre **solo** il report di dettaglio del singolo trade.

Include:

- integrazione di **Apache ECharts**
- rendering di un **grafico candlestick**
- visualizzazione dei livelli operativi
- visualizzazione eventi del trade
- packaging offline degli asset necessari
- integrazione nel flusso di generazione report del repo

### Out of scope
Per questa fase restano fuori:

- scenario report / policy report aggregati
- dashboard multi-trade
- comparazione tra policies
- editor grafico/manuale di linee
- strumenti avanzati tipo drawing tools da piattaforma trading
- dipendenza da CDN esterne
- introduzione di QFChart

---

## 5. Scelta tecnologica

### Libreria scelta
**Apache ECharts**

### Motivazioni
ECharts è stata scelta perché:

- supporta nativamente i **candlestick chart**
- supporta bene **markLine**, **scatter**, **tooltip**, **zoom**, **annotazioni**
- è flessibile per overlay custom
- si integra facilmente in report HTML generati da Python
- può essere distribuita come file locale, quindi è adatta a report **offline**

### Librerie escluse
**QFChart** non viene adottata in questa fase perché aggiunge un layer intermedio non necessario sopra ECharts e complica l’integrazione senza portare vantaggi essenziali per il caso d’uso del report staticamente generato.

---

## 6. Utente e caso d’uso

### Utente principale
Operatore / analista che vuole ispezionare il risultato di un singolo trade simulato o backtestato.

### Caso d’uso principale
L’utente apre il report HTML del singolo trade e vuole vedere, in modo immediato:

- come si è mosso il prezzo
- dove si trovavano entry, SL, TP
- se e quando il trade è andato a break even
- quando si sono verificati eventi come fill, TP hit, SL hit, close
- il rapporto tra evoluzione del mercato e gestione del trade

---

## 7. Requisiti funzionali

### RF-1 — Report dedicato al singolo trade
Il sistema deve generare un report HTML dedicato al singolo trade.

### RF-2 — Grafico candlestick
Il report deve contenere un grafico interattivo candlestick basato su dati OHLCV.

### RF-3 — Visualizzazione livelli operativi
Il grafico deve mostrare almeno i seguenti livelli, se disponibili:

- Entry
- Stop Loss iniziale
- Take Profit 1
- Take Profit 2
- Take Profit 3
- Break Even
- eventuale exit finale
- eventuali livelli di averaging / secondary entry, se presenti nel trade

### RF-4 — Visualizzazione eventi operativi
Il grafico deve mostrare marker per gli eventi operativi principali, almeno:

- apertura / fill
- move SL to BE
- TP hit
- SL hit
- close finale
- eventuali close parziali
- eventuali cancel/invalidazione, se il flusso trade le prevede

### RF-5 — Tooltip interattivi
Passando il mouse su candela, livello o evento, il report deve mostrare tooltip leggibili con informazioni utili.

Esempi:
- timestamp
- prezzo
- tipo evento
- eventuale nota o label

### RF-6 — Zoom e pan
Il grafico deve supportare:

- zoom
- pan orizzontale
- ispezione locale della finestra trade

### RF-7 — Finestra temporale del grafico
Il grafico deve mostrare una finestra di candele coerente con il trade, includendo:

- un buffer prima dell’apertura
- il periodo di vita del trade
- un buffer finale dopo la chiusura, quando utile

### RF-8 — Funzionamento offline
Il report deve funzionare senza connessione internet.

### RF-9 — Asset locali
Il file JS di ECharts non deve essere caricato da CDN, ma deve essere:

- incluso localmente negli asset del report
oppure
- incorporato nel report secondo la strategia scelta dal progetto

### RF-10 — Integrazione nel flusso esistente
La generazione del nuovo report deve integrarsi nel sistema attuale del repo senza rompere gli artifact esistenti.

### RF-11 — Compatibilità con dati mancanti
Se alcuni livelli o eventi non sono disponibili, il report deve comunque generarsi mostrando solo gli elementi realmente presenti.

### RF-12 — Fallback leggibile
In caso di dati OHLCV mancanti o incompleti, il report deve restituire una vista HTML valida con messaggio esplicito e senza crash.

---

## 8. Requisiti dati

### 8.1 Dati di input minimi per il chart
Per ogni trade il renderer deve poter ricevere almeno:

- `signal_id`
- `symbol`
- `timeframe`
- lista di candele OHLCV
- timestamp apertura trade
- timestamp chiusura trade
- livelli operativi
- lista eventi operativi

### 8.2 Struttura dati consigliata
Esempio logico del payload:

```json
{
  "meta": {
    "signal_id": "abc123",
    "symbol": "BTCUSDT",
    "policy_name": "default_policy",
    "timeframe": "5m"
  },
  "candles": [
    {
      "ts": 1710000000000,
      "open": 100.0,
      "high": 105.0,
      "low": 99.0,
      "close": 103.0,
      "volume": 1200.0
    }
  ],
  "levels": [
    { "kind": "ENTRY", "price": 101.5, "label": "Entry" },
    { "kind": "SL", "price": 98.0, "label": "Initial SL" },
    { "kind": "TP1", "price": 104.0, "label": "TP1" },
    { "kind": "TP2", "price": 108.0, "label": "TP2" },
    { "kind": "BE", "price": 101.5, "label": "Break Even" }
  ],
  "events": [
    { "ts": 1710000300000, "price": 101.5, "kind": "FILL", "label": "Entry filled" },
    { "ts": 1710000600000, "price": 104.0, "kind": "TP1_HIT", "label": "TP1 hit" },
    { "ts": 1710000900000, "price": 101.5, "kind": "MOVE_SL_BE", "label": "SL moved to BE" },
    { "ts": 1710001200000, "price": 101.5, "kind": "CLOSE", "label": "Closed at BE" }
  ]
}
```

### 8.3 Fonte dati
I dati OHLCV devono provenire dal flusso di backtest/replay già presente nel progetto, tramite il layer che lavora con:

- market provider
- candele di mercato
- segnali / chain di eventi

Il report trade-detail deve usare questa sorgente, non un dataset fittizio scollegato dal backtest.

---

## 9. UI/UX del report

### 9.1 Sezione chart
Il report deve avere una sezione prominente con il grafico del trade.

### 9.2 Elementi visivi consigliati
- candele mercato
- linee orizzontali per livelli
- marker distinti per eventi
- legenda minima
- tooltip leggibili
- eventualmente colori differenziati per:
  - entry
  - SL
  - TP
  - BE
  - close

### 9.3 Comportamenti desiderati
- hover sulle candele
- hover/click sugli eventi
- zoom locale
- reset zoom

### 9.4 Layout
Il grafico deve essere pensato per essere leggibile in desktop browser.

---

## 10. Requisiti non funzionali

### RNF-1 — Offline first
Il report deve aprirsi e funzionare anche senza internet.

### RNF-2 — Nessuna dipendenza runtime esterna
Nessuna libreria JS deve dipendere da caricamento remoto.

### RNF-3 — Robustezza
Il report non deve fallire se mancano alcuni eventi o livelli.

### RNF-4 — Manutenibilità
La logica di rendering chart deve essere isolata in un modulo dedicato, non dispersa in stringhe HTML duplicate.

### RNF-5 — Integrazione pulita
La modifica deve essere compatibile con la struttura attuale dei report del progetto.

### RNF-6 — Espandibilità
La soluzione deve permettere in futuro di aggiungere:
- volume subplot
- indicatori
- più overlay
- sincronizzazione con timeline eventi

---

## 11. Architettura proposta

### 11.1 Strategia generale
Introdurre un nuovo renderer dedicato al report trade-detail, con responsabilità separate:

1. raccolta dati trade + OHLCV
2. costruzione payload JSON chart
3. rendering HTML
4. distribuzione asset locali ECharts

### 11.2 Moduli consigliati
Esempio di struttura:

```text
src/signal_chain_lab/reports/
  trade_detail_report.py
  echarts_embed.py
  assets/
    echarts.min.js
```

### 11.3 Responsabilità moduli

#### `trade_detail_report.py`
- costruisce il report HTML del singolo trade
- compone sezione metadata + sezione chart + eventuali dettagli evento

#### `echarts_embed.py`
- converte payload Python in struttura JS/JSON per ECharts
- genera option config del candlestick chart
- genera overlay livelli ed eventi

#### `assets/echarts.min.js`
- bundle locale necessario al funzionamento offline

---

## 12. Strategia di rendering chart

### 12.1 Serie principali
Il chart deve usare almeno:

- `candlestick` per il prezzo
- `scatter` o `markPoint` per eventi
- `markLine` per i livelli statici o semi-statici

### 12.2 Overlay consigliati
- Entry → linea orizzontale
- SL → linea orizzontale
- TP1 / TP2 / TP3 → linee orizzontali
- BE → linea orizzontale
- Fill / TP hit / Close → marker evento

### 12.3 Estensioni opzionali future
- volume subplot
- evidenziazione della durata del trade
- area colorata durante finestra trade attiva
- pannello laterale eventi sincronizzato

---

## 13. Integrazione con il repo

### 13.1 Principio
Non deve essere alterata in modo distruttivo la generazione degli artifact attuali.

### 13.2 Strategia consigliata
Aggiungere il nuovo report trade-detail come artifact nuovo o come sostituto controllato del vecchio HTML statico del dettaglio trade.

### 13.3 Compatibilità
L’implementazione deve convivere con:
- flusso di replay/backtest esistente
- risultati di simulazione esistenti
- eventuali export già in uso

---

## 14. Criteri di accettazione

La feature è accettata se:

1. viene generato un file HTML di dettaglio trade apribile localmente
2. il file mostra un grafico candlestick interattivo
3. il grafico visualizza correttamente:
   - entry
   - SL
   - TP disponibili
   - BE se presente
   - close / eventi principali
4. il report funziona offline
5. gli asset JS necessari sono locali
6. il report non crasha in assenza di alcuni livelli/eventi
7. il risultato è integrato nel flusso del repo e non come demo esterna

---

## 15. Rischi e punti di attenzione

### R-1 — Dati OHLCV non ancora esposti al report
Il rischio principale è che il flusso attuale di reporting non serializzi ancora la finestra candele necessaria al chart trade-detail.

### R-2 — Allineamento temporale
Occorre garantire che:
- timestamp eventi
- timestamp candele
- timezone/timeframe
siano coerenti.

### R-3 — Complessità crescente
Se la logica chart finisce direttamente nei template HTML, il codice diventa difficile da mantenere.

### R-4 — Dati incompleti
Trade particolari potrebbero non avere tutti i livelli disponibili; il renderer deve gestire questi casi in modo elegante.

---

## 16. Fasi consigliate

### Fase 1 — V1 trade chart
- integrazione ECharts locale
- grafico candlestick
- entry / SL / TP / BE / close
- marker eventi base
- report HTML offline

### Fase 2 — Miglioramenti UX
- legenda più ricca
- tooltip migliorati
- reset zoom
- layout più rifinito

### Fase 3 — Estensioni future
- volume
- indicatori
- sync con timeline eventi
- collegamenti bidirezionali tra evento e punto sul grafico

---

## 17. Decisioni prese

- Il focus è **solo sul trade-detail**
- La libreria scelta è **Apache ECharts**
- Il report deve essere **offline**
- **No CDN**
- **No QFChart**
- Il grafico deve mostrare **mercato + livelli trade + eventi trade**

---

## 18. Sintesi finale

Il progetto deve introdurre un **Single Trade Interactive HTML Report** che permetta di leggere in modo visivo e operativo il comportamento del trade sul mercato reale/backtestato, mostrando candele, livelli di gestione e principali eventi, con integrazione pulita nel repo e pieno supporto offline.
