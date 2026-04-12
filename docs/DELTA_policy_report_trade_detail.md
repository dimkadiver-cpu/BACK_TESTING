# Delta completo — miglioramento Policy Report e Trade Detail

## 1. Decisioni bloccate

Queste restano fissate e non vanno rimesse in discussione:

- non toccare la chiave trade / signal id
- il blocco “Metadata - policy.yaml values” resta com’è
- il report deve ragionare quasi solo in percentuale sul capitale ipotetico
- i valori assoluti non sono focus UI
- il chart del trade detail resta espresso in prezzo, perché candele, entry, SL e TP vivono su asse prezzo

---

## 2. Obiettivo del delta

Rendere i report più utili per:

- capire velocemente la qualità di una policy
- leggere il risultato dei trade in termini di impatto % sul capitale
- separare meglio:
  - performance
  - execution
  - qualità/sicurezza della simulazione
- migliorare leggibilità, confronto e drill-down senza cambiare inutilmente la struttura già buona

---

## 3. Principio di misura

### 3.1 Regola principale
La UI deve esporre principalmente metriche in % del capitale ipotetico.

### 3.2 Regola pratica consigliata
Per la prima versione operativa:

- `initial_capital` = capitale ipotetico configurato
- `trade_impact_pct = realized_pnl / initial_capital * 100`
- `policy_return_pct = cumulative_realized_pnl / initial_capital * 100`

### 3.3 Motivazione
Questo approccio:

- è semplice da capire
- è stabile
- rende confrontabili i trade tra loro
- rende confrontabili le policy
- evita che simboli “più grandi” pesino visivamente solo per dimensione nominale

### 3.4 Evoluzione futura opzionale
In una V2 si può introdurre una modalità compound:

- trade % su `equity_before_trade`
- policy % su equity progressiva

Per ora non è prioritaria.

---

## 4. Delta completo — Policy Report

### 4.1 Struttura generale
La struttura alta può restare simile, ma il contenuto va reso più analitico.

Ordine consigliato:

1. titolo report
2. dataset metadata
3. metadata policy.yaml values
4. policy summary potenziato
5. grafici principali
6. excluded chains
7. trade results
8. link ai single trade report

### 4.2 Summary cards da mostrare
Le card principali devono essere orientate a percentuali e qualità della policy.

#### Card principali
- Total Return %
- Max Drawdown %
- Expectancy %
- Win Rate %
- Profit Factor
- Average Trade Impact %
- Median Trade Impact %
- Best Trade %
- Worst Trade %

#### Card secondarie utili
- trades count
- closed trades %
- expired trades %
- ignored events count
- warnings count

### 4.3 Cosa togliere dal focus
Non vanno eliminate per forza dai dati interni, ma non devono dominare la UI:

- total PnL assoluto
- drawdown assoluto
- contribution assoluta
- summary nominale in quote currency

### 4.4 Grafici da introdurre
Questa è la parte più importante del delta.

#### 1. Equity curve in %
Curva cumulativa dell’impatto della policy sul capitale ipotetico.

#### 2. Underwater / drawdown in %
Grafico separato o sovrapposto per leggere la profondità e la durata dei drawdown.

#### 3. Distribuzione dei trade return %
Istogramma o bins dei ritorni % dei trade.

Serve per capire:
- dispersione
- asimmetria
- concentrazione delle perdite
- presenza di outlier

#### 4. Contribution by symbol in %
Bar chart ordinato per simbolo.

Ogni simbolo deve mostrare:
- contributo cumulativo %
- numero trade
- win rate opzionale per simbolo

#### 5. Close reason distribution
Distribuzione per:
- TP
- SL
- manual/forced close
- expired
- cancelled
- other

#### 6. Duration vs trade return %
Scatter:
- asse X = durata trade
- asse Y = return %
- colore = close reason

Questo aiuta a vedere:
- se i trade lunghi sono inefficaci
- se la policy perde soprattutto su determinate durate
- se esistono cluster di comportamento

### 4.5 Tabella “Trade Results” da migliorare
La tabella resta centrale, ma con colonne più utili.

#### Colonne base consigliate
- Signal ID
- Symbol
- Side
- Status
- Close reason
- Trade impact %
- Cum. equity % after trade
- Created
- Closed
- Detail

#### Colonne estese opzionali
- MAE %
- MFE %
- Capture ratio %
- Time to fill
- Total duration
- Updates applied
- Warnings
- Ignored events
- Fill resolution mode / simulation confidence

#### UX tabella
Va aggiunto:

- ordinamento per colonna
- filtri rapidi
- ricerca per signal/symbol
- possibilità di mostrare/nascondere colonne
- evidenziazione visiva dei trade migliori/peggiori

### 4.6 Excluded Chains
La sezione va mantenuta, ma migliorata nella leggibilità.

Per ogni chain esclusa mostrare:

- Signal ID
- Symbol
- Reason
- Note
- Original text apribile in popup/modal

Miglioria utile:
- raggruppamento per `reason`
- conteggio per reason
- filtro rapido per reason

### 4.7 Comparison report tra policy
Quando ci sono 2+ policy, il comparison report deve essere più utile e meno solo “tabella riassuntiva”.

#### Da introdurre
- delta cards tra policy
- evidenziazione della policy vincente per metrica
- classifica per:
  - return %
  - drawdown %
  - expectancy %
  - win rate %
- tabella “changed trades only”
- link diretti al single trade detail per ogni policy

#### Changed trades only
Questa tabella è molto importante.

Per ogni trade che cambia tra policy:
- Signal ID
- Symbol
- policy A result %
- policy B result %
- delta %
- close reason A/B
- link a dettaglio A
- link a dettaglio B

---

## 5. Delta completo — Trade Detail

### 5.1 Obiettivo
Il trade detail deve diventare una vista operativa chiara:

- cosa è successo sul prezzo
- come è stato gestito il trade
- quale impatto % ha avuto sul capitale
- quanto era favorevole/sfavorevole il trade rispetto al risultato finale

### 5.2 Summary iniziale da rifare
La summary sopra il chart deve essere più compatta e orientata a KPI.

#### Gruppo Performance
- Trade impact %
- Capture ratio %
- Close reason

#### Gruppo Excursions
- MAE %
- MFE %
- eventuale MFE captured %

#### Gruppo Execution
- first fill price
- final exit price
- fills count
- partial closes count
- updates applied

#### Gruppo Timing
- time to first fill
- total duration
- bars in trade

### 5.3 Chart del trade
Il chart resta in prezzo, ma va arricchito semanticamente.

#### Elementi da mantenere
- candlestick
- zoom / pan
- tooltip
- linee entry / SL / TP / BE
- layer toggle

#### Elementi da aggiungere
- distinzione visiva tra:
  - initial SL
  - moved SL
  - BE
  - final exit
- evidenziazione del periodo in cui il trade è attivo
- marker evento distinti per:
  - fill
  - partial TP
  - move SL
  - close partial
  - final close
  - cancel / expire

#### Toggle consigliati
- show/hide levels
- show/hide event labels
- show/hide execution markers
- show/hide volume
- show/hide position size overlay
- show/hide realized pnl overlay

### 5.4 Overlay analitici opzionali molto utili
Questi sono i migliori upgrade del trade chart.

#### Position size step line
Linea a gradini su asse secondario:
- 0
- apertura
- eventuali riduzioni
- chiusura finale

#### Realized PnL step line
Sempre su asse secondario, utile per leggere come evolve il risultato del trade.

#### Planned vs actual
Dove possibile distinguere:
- entry pianificata
- fill effettivo
- exit effettiva

### 5.5 Event Timeline da migliorare
La timeline deve smettere di essere solo descrittiva e diventare più “delta-oriented”.

Per ogni evento mostrare:

- timestamp
- tipo evento
- origine evento
- label leggibile
- note / reason
- prezzo evento, se disponibile
- impatto sullo stato

#### Delta di stato da mostrare quando disponibili
- `position_size: before -> after`
- `realized_pnl_pct: before -> after`
- `current_sl: before -> after`
- `next_tp_index: before -> after`
- `status: before -> after`

Questo rende molto più chiaro cosa ha realmente fatto ogni update.

### 5.6 Testo originale
Va mantenuta e migliorata la possibilità di vedere il testo originale.

#### Per il segnale iniziale
- raw telegram text in popup/modal

#### Per gli update operativi
- raw update text in popup/modal

#### Per eventi interni motore
- reason code tecnico
- label leggibile per utente

### 5.7 Navigazione tra trade detail
Da aggiungere:

- prev / next trade
- prev / next winning trade
- prev / next losing trade
- ritorno rapido alla tabella filtered del policy report
- confronto tra stesso trade su due policy, se disponibile

---

## 6. Delta dati necessario

Per supportare bene i report, servono più dati già pronti nel payload finale.

### 6.1 Campi trade-level da aggiungere o valorizzare
- `trade_impact_pct`
- `cum_equity_after_trade_pct`
- `mae_pct`
- `mfe_pct`
- `capture_ratio_pct`
- `time_to_fill_seconds`
- `total_duration_seconds`
- `bars_in_trade`
- `updates_applied_count`
- `fills_count`
- `partial_closes_count`
- `first_fill_price`
- `final_exit_price`
- `close_reason_normalized`
- `fill_resolution_mode`
- `simulation_confidence`
- `warnings_count`
- `ignored_events_count`

### 6.2 Campi event-level utili
- `event_price`
- `position_size_before`
- `position_size_after`
- `realized_pnl_pct_before`
- `realized_pnl_pct_after`
- `current_sl_before`
- `current_sl_after`
- `status_before`
- `status_after`
- `source_type`
- `reason_code`
- `raw_text_ref`

---

## 7. Regole UI/UX

### 7.1 Linguaggio del report
Il report deve parlare in modo coerente:

- performance = percentuale
- prezzo = valore mercato
- execution = eventi/stato
- metadata = come oggi

### 7.2 Colori e semantica
Colori coerenti e stabili:

- verde = positivo / TP
- rosso = negativo / SL
- blu = entry / setup
- arancio = update / modifica gestione
- grigio = metadata / neutro / disabled

### 7.3 Densità informativa
Principio:

- overview sintetica in alto
- dettaglio apribile sotto
- informazioni tecniche solo quando servono

---

## 8. Cose da lasciare invariate

- chiave trade / signal handling
- blocco metadata `policy.yaml values`
- concetto generale di policy report
- concetto generale di trade detail interattivo
- uso del chart prezzo per il dettaglio trade

---

## 9. Priorità di implementazione

### Fase 1 — linguaggio e metriche
- introdurre/valorizzare tutte le metriche %
- sostituire il focus della UI da assoluto a percentuale
- uniformare naming e label

### Fase 2 — Policy Report
- nuove summary cards
- equity %
- drawdown %
- distribution %
- symbol contribution %
- trade table migliorata

### Fase 3 — Trade Detail
- summary KPI in %
- timeline con delta di stato
- overlay size / pnl
- popup raw text

### Fase 4 — Comparison report
- delta tra policy
- changed trades only
- navigazione incrociata tra policy e trade detail

---

## 10. Criteri di accettazione

Il delta è considerato completato quando:

1. il policy report espone come focus principale metriche in %
2. il trade detail mostra il trade come impatto % sul capitale
3. il chart del trade resta leggibile in prezzo ma il summary è in %
4. il metadata block resta invariato
5. la tabella trade supporta analisi più ricca e drill-down
6. il confronto multi-policy evidenzia differenze reali e non solo totali aggregati
7. MAE/MFE/capture diventano leggibili o chiaramente assenti se non ancora valorizzati

---

## 11. Sintesi finale

La revisione completa va in questa direzione:

- meno nominale
- più percentuale
- più analisi della qualità della policy
- più leggibilità del singolo trade
- più chiarezza tra performance, execution e simulazione

Il cuore del delta è questo:

- policy report = performance in %
- trade detail = chart in prezzo + KPI in %
- metadata = invariato
- confronto policy = basato su delta reali, non solo su tabella statica
