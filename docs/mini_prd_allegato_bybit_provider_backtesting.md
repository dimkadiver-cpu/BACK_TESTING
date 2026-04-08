# Mini PRD Allegato — Provider storico Bybit per backtesting

## 1. Scopo

Definire in modo sintetico la decisione di usare **Bybit** come provider storico canonico per il backtesting dei segnali destinati a esecuzione su Bybit, e descrivere il flusso minimo richiesto per acquisire, validare e salvare i dati storici necessari.

---

## 2. Problema

Usare dati storici di un exchange diverso da quello di esecuzione può introdurre incongruenze operative, ad esempio:

- ordine eseguito su Bybit ma non su un altro exchange;
- SL/TP colpiti in momenti diversi;
- divergenze dovute a **Last Price**, **Mark Price** o **Index Price**;
- differenze nel comportamento del trigger e del lifecycle del trade.

Per questo motivo, se i segnali sono valutati per utilizzo reale su Bybit, il backtest deve usare dati storici Bybit come sorgente primaria.

---

## 3. Decisione di prodotto

### Decisione principale
Il progetto adotterà **Bybit** come **provider storico canonico** per il backtesting ufficiale dei segnali destinati a Bybit.

### Decisione secondaria
Eventuali altri provider potranno essere usati solo come:
- confronto statistico separato;
- benchmark esterno;
- fallback non canonico.

Questi run dovranno essere etichettati esplicitamente come **non exchange-faithful**.

---

## 4. Obiettivi

- Aumentare la fedeltà del backtest rispetto all’esecuzione reale su Bybit.
- Supportare correttamente trigger basati su Last / Mark / Index Price.
- Creare una cache locale incrementale riusabile nel tempo.
- Evitare dipendenza da dati a pagamento.
- Ridurre il rischio di risultati fuorvianti dovuti a mismatch cross-exchange.

---

## 5. Ambito

### Incluso
- acquisizione di candele storiche Bybit;
- supporto a futures linear;
- supporto a last price e mark price;
- storage locale partizionato;
- validazione minima dei dataset;
- uso dei dati da parte del backtester.

### Escluso
- tick data;
- order book replay;
- simulazione microstrutturale completa;
- live trading;
- funding/slippage avanzati nella prima fase.

---

## 6. Fonti dati Bybit da supportare

Il sistema deve supportare almeno questi endpoint/logiche:

1. **Kline standard**
   - usato per prezzo di mercato “last”

2. **Mark Price Kline**
   - usato quando i trigger o la logica operativa dipendono dal mark price

3. **Index Price Kline** (opzionale in prima fase)
   - da introdurre se richiesto da regole specifiche

4. **Funding history** (opzionale fase successiva)
   - per estendere il realismo del PnL sui perpetual

---

## 7. Requisiti funzionali minimi

### RF-1 — Provider canonico
Il sistema deve poter scaricare dati storici da Bybit per strumenti `linear`.

### RF-2 — Supporto basi prezzo
Il sistema deve distinguere almeno:
- `last`
- `mark`

### RF-3 — Pianificazione da DB segnali
Il download deve essere pianificato in base a:
- simboli presenti nel DB;
- intervalli temporali richiesti dalle chain;
- buffer temporali configurabili.

### RF-4 — Download incrementale
Il sistema deve scaricare solo:
- simboli mancanti;
- periodi mancanti;
- estensioni mancanti.

### RF-5 — Storage locale
I dati devono essere salvati in cache locale persistente.

### RF-6 — Validazione minima
Ogni batch scaricato deve essere verificato per:
- ordinamento timestamp;
- deduplica;
- copertura del range richiesto;
- schema coerente.

### RF-7 — Configurazione esplicita del trigger
Il backtester deve poter configurare esplicitamente la price basis:
- `last`
- `mark`

---

## 8. Requisiti non funzionali

- Accuratezza prioritaria rispetto alla velocità iniziale
- Ripetibilità dei run
- Offline-first dopo la sincronizzazione
- Estendibilità ad altri provider senza cambiare il backtester
- Tracciabilità del dataset usato per ciascun run

---

## 9. Struttura storage minima consigliata

```text
data/
  market/
    bybit/
      futures_linear/
        1m/
          BTCUSDT/
            2025-01.last.parquet
            2025-01.mark.parquet
            2025-02.last.parquet
            2025-02.mark.parquet
    manifests/
      coverage_index.json
      download_log.json
```

---

## 10. Flusso operativo minimo

1. Leggere il DB segnali
2. Estrarre simboli e intervalli necessari
3. Calcolare i gap rispetto alla cache locale
4. Scaricare i dati Bybit mancanti
5. Validare e salvare in Parquet
6. Aggiornare il manifest
7. Eseguire il backtest leggendo solo dalla cache locale

---

## 11. Regole di utilizzo nel backtesting

### Modalità ufficiale
Per i run ufficiali:
- exchange storico = Bybit
- trigger basis dichiarata
- niente fallback automatico a provider esterni

### Modalità comparativa
Per run sperimentali:
- consentito usare altri provider
- il risultato deve essere etichettato come comparativo, non canonico

---

## 12. Rischi principali

- copertura storica incompleta in alcuni periodi/simboli;
- rate limit API;
- differenze tra last e mark se non modellate correttamente;
- dataset incompleti o duplicati;
- errata interpretazione dei trigger del segnale.

---

## 13. Criteri di accettazione

Il mini-PRD si considera soddisfatto quando:

1. Il sistema scarica correttamente dati Bybit per simboli `linear`.
2. Il sistema salva separatamente dati `last` e `mark`.
3. Il planner scarica solo i periodi mancanti.
4. Il backtester può scegliere la price basis da usare.
5. Un run ufficiale Bybit non dipende da dati Binance o altri exchange.
6. La cache locale può essere riutilizzata su run successivi.

---

## 14. Decisione finale

Per il progetto, il backtesting ufficiale dei segnali destinati a Bybit userà:

- **Bybit come provider storico principale**
- **futures linear come mercato prioritario**
- **supporto almeno a last + mark price**
- **cache locale incrementale**
- **nessun fallback silenzioso a exchange diversi**
