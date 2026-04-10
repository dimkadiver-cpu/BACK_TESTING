# PRD — Miglioramento performance flusso Backtest

## 1. Scopo

Questo PRD definisce un piano a fasi per velocizzare il flusso di backtest del progetto `BACK_TESTING` senza rompere l’architettura attuale:

- GUI Backtest
- Planner market data
- Sync market data
- Validate market data
- Runner scenario
- Simulator
- Report HTML / CSV

Obiettivo principale:

**ridurre il tempo totale di esecuzione del backtest e i ricalcoli inutili**, mantenendo affidabilità, leggibilità del codice e compatibilità con il flusso attuale.

---

## 2. Problema attuale

Il flusso corrente ha questi punti critici:

1. La preparazione dei market data può essere rifatta inutilmente.
2. La validazione market non è persistente in modo robusto rispetto a DB, filtri e impostazioni market.
3. Il confronto tra più policy lancia run separati, ripetendo caricamento DB, adattamento chain, inizializzazione provider e processi Python.
4. La validazione completa può essere costosa anche quando sono stati aggiunti solo pochi gap.
5. Il provider parquet può essere migliorato nella velocità di lookup.

---

## 3. Obiettivi di prodotto

### Obiettivi funzionali

- introdurre due modalità operative: **SAFE** e **FAST**
- riusare validazioni già eseguite quando il contesto market-data è identico
- evitare che il solo cambio di policy faccia rifare Planner / Sync / Validate
- ridurre il numero di run separati quando si testano più policy
- introdurre una **Gap Validation** incrementale per verificare solo i dati appena aggiunti

### Obiettivi non funzionali

- non rompere il flusso GUI esistente
- non rompere il formato degli artifact già usati da GUI e report
- mantenere codice leggibile e aderente allo stile del repo
- garantire tracciabilità delle decisioni nel log

---

## 4. Principi guida

1. **Non rifare lavoro già fatto**.
2. **Separare la validità dei market data dalla policy di simulazione**.
3. **Preferire ottimizzazioni incrementali e locali a refactor ampi**.
4. **Mantenere modalità SAFE come riferimento affidabile**.
5. **Usare FAST come acceleratore controllato, non come scorciatoia silenziosa**.

---

## 5. Ambito

### In scope

- GUI Backtest
- stato persistente della validazione market
- riuso intelligente di Planner / Sync / Validate
- esecuzione multi-policy in un solo run
- ottimizzazione provider parquet
- validazione incrementale dei gap
- benchmark e logging del flusso

### Out of scope

- riscrittura completa del simulatore
- cambio del formato principale di output dei report
- nuova architettura di orchestrazione jobs distribuiti
- parallelizzazione massiva cross-process del motore di simulazione

---

## 6. Modalità operative target

## 6.1 SAFE

Modalità affidabile.

Comportamento:

- se esiste una validazione `PASS` compatibile con la richiesta market attuale, il sistema la riusa
- altrimenti esegue:
  - Planner
  - Sync
  - Validate
  - Backtest

Uso consigliato:

- benchmark affidabili
- generazione report ufficiali
- primo run su nuovo dataset o nuovi filtri

## 6.2 FAST

Modalità veloce.

Comportamento:

- se esiste una validazione `PASS` compatibile, va direttamente al Backtest
- se non esiste:
  - esegue Planner
  - esegue Sync
  - salta Validate completa
  - esegue Backtest
- deve segnalare in modo esplicito che il run è partito senza validazione completa in quella esecuzione

Uso consigliato:

- iterazioni rapide
- confronto policy
- tuning operativo durante sviluppo

---

## 7. Chiave di riuso della validazione

La validazione market deve dipendere da una fingerprint persistente costruita almeno con:

- `db_path` assoluto
- `db_mtime`
- `db_size`
- `trader_filter`
- `date_from`
- `date_to`
- `market_data_dir` assoluto
- `timeframe`
- `price_basis`
- `market source`
- eventuale `schema_version`

La validazione market **non deve dipendere** da:

- policy
- report output dir
- timeout
- impostazioni puramente di reportistica

---

## 8. Piano a fasi

# Fase 1 — FAST / SAFE + validation cache persistente

## Obiettivo

Eliminare i ricalcoli inutili di Planner / Sync / Validate quando il contesto market-data non è cambiato.

## Deliverable

- selettore GUI `SAFE / FAST`
- fingerprint persistente della richiesta market-data
- file indice validazioni persistente, ad esempio:
  - `artifacts/market_data/validation_index.json`
- riuso di validazione `PASS` già compatibile
- log chiaro dei cache hit

## Requisiti

- cambiare solo policy **non** invalida la validazione market
- cambiare solo report dir **non** invalida la validazione market
- cambiare DB, filtri o market settings invalida correttamente il riuso
- il riuso sopravvive al riavvio della GUI

## Criteri di accettazione

- primo run SAFE esegue prepare completo
- secondo run SAFE identico riusa la validazione senza rifare gli step
- cambio policy non fa rifare Validate
- cambio filtro data invalida il riuso

## Priorità

**Altissima**

## Stato

- [x] **FASE 1 completata** (2026-04-10)

---

# Fase 2 — Single-run multi-policy

## Obiettivo

Evitare run separati per ciascuna policy quando si vuole confrontare più policy sullo stesso dataset.

## Stato attuale

La GUI lancia un run per policy, mentre il motore sottostante supporta già una lista di policy.

## Deliverable

- aggiornamento del runner CLI o introduzione di un entrypoint che accetti più policy
- lettura DB, chain building, adattamento e inizializzazione provider eseguiti una sola volta
- generazione artifact compatibili con summary GUI e report

## Requisiti

- mantenere compatibilità con report HTML e CSV
- mantenere identificabilità separata dei risultati per policy
- non rompere l’uso con singola policy

## Criteri di accettazione

- selezionando 3 policy, il sistema esegue un solo run logico
- i risultati restano separati per policy
- il tempo totale è inferiore rispetto a 3 run separati

## Priorità

**Alta**

---

# Fase 3 — Ottimizzazione BybitParquetProvider

## Obiettivo

Ridurre il costo di lettura e ricerca delle candele storiche durante la simulazione.

## Problema

Il provider attuale cache-a bene i dati, ma alcune ricerche possono restare troppo lineari su dataset grandi.

## Deliverable

- miglior lookup per timestamp
- miglior retrieval dei range temporali
- eventuale uso di `bisect` o indice timestamp -> posizione
- mantenimento completo dell’interfaccia pubblica esistente

## Requisiti

- nessuna modifica al layout dei parquet
- nessuna modifica all’API usata dal simulatore
- compatibilità totale con timeframe e basis attuali

## Criteri di accettazione

- riduzione misurabile del tempo di `get_candle()` / `get_range()` su dataset medi e grandi
- nessuna regressione funzionale nei test del simulatore

## Priorità

**Alta**

---

# Fase 4 — Gap Validation incrementale

## Obiettivo

Introdurre una validazione specifica dei gap appena sincronizzati, evitando di rifare ogni volta la validazione completa su tutta la cache.

## Motivazione

Oggi la validazione completa è utile ma potenzialmente costosa. Se il Sync ha aggiunto solo pochi intervalli, conviene validare subito quei soli intervalli nuovi.

## Deliverable

- nuova fase di **Gap Validation** dopo il Sync
- verifica mirata dei soli gap appena riempiti
- registrazione del risultato in artifact dedicato, ad esempio:
  - `artifacts/market_data/gap_validate_market_data.json`
- integrazione con SAFE e FAST

## Logica target

### In SAFE

- se serve un nuovo Sync:
  - Planner
  - Sync
  - Gap Validation
  - eventuale Validate completa solo se necessaria per conferma finale o bootstrap iniziale
- se esiste già una validazione completa compatibile, si può riusare direttamente

### In FAST

- se serve un nuovo Sync:
  - Planner
  - Sync
  - Gap Validation
  - Backtest
- no Validate completa, salvo richiesta esplicita

## Requisiti

- la gap validation deve usare il piano dei gap effettivamente sincronizzati
- non deve “inventare” copertura oltre ai gap richiesti
- deve poter marcare come `FAIL` un gap non scritto correttamente
- non deve sostituire in automatico la validazione completa storica se il prodotto decide che SAFE richiede ancora una validate full iniziale

## Casi d’uso

1. Cache quasi completa, mancano 2 intervalli su BTCUSDT -> sync di quei 2 gap -> validazione solo di quei 2 gap
2. Cambio date filter con piccolo allargamento -> validazione solo della nuova estensione
3. Primo bootstrap su cartella vuota -> può essere richiesto anche controllo completo finale

## Criteri di accettazione

- dopo Sync, i gap nuovi vengono verificati in modo mirato
- se la gap validation fallisce, il backtest SAFE non parte
- FAST può partire solo secondo le regole definite, ma con warning esplicito se manca validazione completa
- il tempo della gap validation è inferiore alla validate completa su cache ampia

## Priorità

**Alta**

---

# Fase 5 — Osservabilità, benchmark e UX

## Obiettivo

Rendere il flusso misurabile e comprensibile all’utente.

## Deliverable

- tempi per ogni fase nel log:
  - Planner
  - Sync
  - Gap Validation
  - Validate full
  - Backtest
- status GUI migliorati, ad esempio:
  - `Market data validati`
  - `Market data pronti, gap validati`
  - `Market data pronti ma non validati in questa run`
  - `Market data da verificare`
- benchmark comparativi FAST vs SAFE
- benchmark single-policy vs multi-policy

## Criteri di accettazione

- il log deve rendere chiaro cosa è stato riusato e cosa è stato ricalcolato
- l’utente deve capire se il run usa dati validati o no

## Priorità

**Media**

---

## 9. Dipendenze logiche tra fasi

Ordine consigliato di implementazione:

1. Fase 1
2. Fase 2
3. Fase 4
4. Fase 3
5. Fase 5

Nota:
- la Fase 4 può essere anticipata rispetto alla Fase 3 se il bisogno principale è ridurre il costo della validazione
- la Fase 3 può venire prima se il collo di bottiglia dominante risulta essere il provider parquet

---

## 10. Artifact e persistenza previsti

### Nuovi artifact suggeriti

- `artifacts/market_data/validation_index.json`
- `artifacts/market_data/gap_validate_market_data.json`

### Artifact già esistenti da preservare

- `plan_market_data.json`
- `sync_market_data.json`
- `validate_market_data.json`
- artifact scenario/report esistenti

---

## 11. Rischi

### Rischio 1 — Riuso errato della validazione

Mitigazione:
- fingerprint robusta con DB metadata + filtri + market settings

### Rischio 2 — Complessità eccessiva nella GUI

Mitigazione:
- solo due modalità chiare: FAST e SAFE
- messaggi di stato espliciti

### Rischio 3 — Gap Validation non sufficiente in alcuni scenari

Mitigazione:
- mantenere possibilità di Validate completa in SAFE
- introdurre regole chiare su quando la validazione completa resta obbligatoria

### Rischio 4 — Regressioni nei report multi-policy

Mitigazione:
- preservare il formato degli artifact attesi dalla GUI
- aggiungere test manuali e automatici sui casi multi-policy

---

## 12. KPI di successo

- riduzione del tempo medio del secondo run sullo stesso dataset
- riduzione del tempo medio confronto multi-policy
- riduzione del tempo medio di prepare market dopo piccoli gap sync
- assenza di regressioni funzionali nel simulatore

---

## 13. Test manuali minimi richiesti

### Test A — SAFE primo run

- nuovo DB o nuovi filtri
- atteso: Planner + Sync + Gap Validation + eventuale Validate full + Backtest

### Test B — SAFE secondo run identico

- nessuna modifica a DB/filtri/market settings
- atteso: riuso validazione esistente, niente ricalcolo inutile

### Test C — cambio solo policy

- stesso DB, stessi filtri, market invariato
- atteso: nessuna nuova validazione market

### Test D — cambio date filter

- stesso DB, finestra temporale diversa
- atteso: invalidazione corretta del riuso, Sync dei nuovi gap, relativa validazione

### Test E — FAST senza validate completa

- nessuna validazione compatibile preesistente
- atteso: Planner + Sync + Gap Validation + Backtest, con messaggio chiaro che la validate full è stata saltata

### Test F — multi-policy

- selezione di più policy
- atteso: singolo run logico, risultati distinti per policy

---

## 14. Decisioni consigliate

1. Implementare subito **Fase 1**
2. Implementare dopo **Fase 2**
3. Inserire **Gap Validation** come punto 4 centrale dell’evoluzione
4. Posticipare ottimizzazioni più profonde del simulatore finché non si misurano i veri colli di bottiglia

---

## 15. Esito atteso finale

Al termine del piano, il sistema dovrà comportarsi così:

- se il contesto market non cambia, non rifà controlli inutili
- se cambiano solo le policy, il backtest riparte subito
- se mancano solo pochi dati, valida solo quei gap
- il confronto tra policy diventa più rapido
- il provider parquet risponde meglio su dataset ampi
- l’utente capisce chiaramente quanto il run è affidabile e quanto è stato accelerato
