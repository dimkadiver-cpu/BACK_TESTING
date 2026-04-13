# PRD — Revisione metriche simulatore e report generale con fee/funding

## Titolo
**Refactor del modello metriche trade/policy e integrazione costi operativi (fee, funding)**

## Contesto
L’attuale simulatore calcola correttamente un valore interno di PnL grezzo, ma nei report alcune metriche vengono presentate con naming ambiguo o semanticamente scorretto. In particolare, campi con suffisso `_pct` possono contenere valori non percentuali, e l’aggregazione cross-symbol del PnL grezzo può produrre letture fuorvianti.

Contestualmente, il report generale deve evolvere da una lettura “teorica” del risultato a una lettura “operativa reale”, includendo l’impatto di **fee** e **funding**.

---

## 1. Problema da risolvere

### 1.1 Ambiguità semantica del PnL attuale
Il simulatore produce oggi una misura interna assimilabile a:

```text
realized_pnl_raw = Σ (exit_price - entry_basis_price) * closed_size_fraction * direction
```

Questa misura:
- non è denaro reale
- non è percentuale
- non è direttamente confrontabile tra simboli con prezzi nominali diversi
- non deve essere usata come metrica principale di report

### 1.2 Naming fuorviante nei report
Alcuni campi attuali con suffisso `_pct` non rappresentano vere percentuali. Questo genera rischio di interpretazione errata da parte dell’utente finale e rende i confronti tra trade/policy poco affidabili.

### 1.3 Mancanza di separazione gross/net
Il report non distingue in modo formale:
- performance lorda del trade/policy
- impatto dei costi operativi
- performance netta finale

### 1.4 Mancata integrazione strutturata di fee e funding
Fee e funding devono entrare nel modello metriche come componenti esplicite del risultato netto, senza essere assorbite implicitamente o nascoste in valori aggregati non leggibili.

---

## 2. Obiettivo

Introdurre un modello metriche chiaro, coerente e leggibile che separi formalmente:

1. **metriche raw/debug**
2. **metriche percentuali corrette a livello trade**
3. **metriche aggregate policy**
4. **costi operativi espliciti: fee e funding**
5. **confronto obbligatorio tra gross e net nei report**

Il risultato finale deve permettere di rispondere chiaramente a tre domande:
- quanto funziona la logica del trade/policy al lordo
- quanto viene eroso o aiutato dai costi operativi
- quanto resta realmente al netto

---

## 3. Principi di design

### 3.1 Il PnL raw resta interno/diagnostico
Le metriche raw restano disponibili per audit, debug e verifiche interne, ma non sono la base principale dei report.

### 3.2 La metrica primaria del trade è percentuale e netta
La metrica principale del singolo trade diventa:

`trade_return_pct_net`

ovvero il rendimento percentuale reale del trade dopo costi.

### 3.3 Fee e funding sono separati
Fee e funding non devono essere fusi in un solo campo opaco. Devono essere esposti separatamente nel trade report e nel policy report.

### 3.4 Gross vs Net è parte del report, non una nota
Il confronto lordo/netto è obbligatorio perché serve a distinguere:
- bontà teorica della logica
- sostenibilità reale dopo costi

---

## 4. Nuovo modello metriche

### 4.1 Metriche raw/debug
Queste metriche restano nel motore e possono comparire in aree tecniche o diagnostiche.

- `realized_pnl_raw_gross`
- `realized_pnl_raw_net`
- `gross_profit_raw`
- `gross_loss_raw`
- `total_pnl_raw`
- `fees_total_raw`
- `funding_total_raw_net`

Queste metriche:
- non devono avere suffisso `_pct`
- non devono essere presentate come metrica principale di performance

### 4.2 Metriche del singolo trade
Queste sono le metriche ufficiali del trade report.

#### Metriche principali
- `trade_return_pct_gross`
- `trade_return_pct_net`

#### Metriche di costo
- `fees_total_raw`
- `funding_total_raw_net`

#### Metriche qualitative
- `mae_pct`
- `mfe_pct`
- `r_multiple`
- `time_to_fill`
- `time_in_trade`
- `fills_count`
- `close_reason`

### 4.3 Metriche aggregate della policy
Queste sono le metriche ufficiali del report generale.

#### Principali nette
- `trades_count`
- `win_rate_net`
- `avg_trade_return_pct_net`
- `median_trade_return_pct_net`
- `expectancy_pct_net`
- `profit_factor_net`
- `avg_r_multiple`
- `median_r_multiple`

#### Secondarie lorde
- `avg_trade_return_pct_gross`
- `median_trade_return_pct_gross`
- `expectancy_pct_gross`
- `profit_factor_gross`

#### Diagnostiche costi
- `fees_total_raw`
- `fees_avg_raw`
- `funding_total_raw_net`
- `funding_avg_raw_net`
- `avg_cost_drag_pct`
- `gross_positive_to_net_negative_count`
- `gross_positive_to_net_negative_pct`
- `trades_with_funding_count`
- `trades_with_funding_pct`

---

## 5. Formule ufficiali

### 5.1 Notional investito
Per rendere confrontabili i trade cross-symbol, le metriche percentuali devono essere normalizzate sul notional effettivamente entrato.

```text
invested_notional = Σ(entry_fill_price * entry_fill_size_fraction)
```

Il denominatore deve usare solo le entry effettivamente fillate.

### 5.2 PnL lordo
```text
pnl_gross_raw = risultato economico del trade prima di fee e funding
```

Operativamente, può derivare dal calcolo già esistente, purché sia semanticamente rinominato come valore raw lordo.

### 5.3 PnL netto
```text
pnl_net_raw = pnl_gross_raw - fees_total_raw + funding_total_raw_net
```

Dove:
- `fees_total_raw` è normalmente negativo come impatto economico
- `funding_total_raw_net` può essere positivo o negativo

### 5.4 Rendimento percentuale lordo
```text
trade_return_pct_gross = pnl_gross_raw / invested_notional * 100
```

### 5.5 Rendimento percentuale netto
```text
trade_return_pct_net = pnl_net_raw / invested_notional * 100
```

Questa è la metrica principale del singolo trade.

### 5.6 Cost drag percentuale
```text
cost_drag_pct = trade_return_pct_gross - trade_return_pct_net
```

Serve per misurare quanto i costi hanno eroso il risultato.

### 5.7 R-multiple
```text
initial_r_pct = abs(entry_reference - initial_sl) / entry_reference * 100
r_multiple = trade_return_pct_net / initial_r_pct
```

---

## 6. Regole di naming

### 6.1 Regola generale
Nessun campo con suffisso `_pct` può contenere valori raw.

### 6.2 Regola gross/net
Ogni metrica di performance che può esistere in due versioni deve avere naming esplicito:
- `_gross`
- `_net`

### 6.3 Regola raw
Le metriche non normalizzate devono avere suffisso `_raw`.

---

## 7. Campi da deprecare o rinominare

### Deprecare
- `return_pct` se usato come expectancy implicita o metrica ambigua
- `gross_profit_pct`
- `gross_loss_pct`
- `net_profit_pct`

### Sostituire con
- `avg_trade_return_pct_net`
- `expectancy_pct_net`
- `gross_profit_raw`
- `gross_loss_raw`
- `total_pnl_raw`

---

## 8. Integrazione fee e funding nel trade report

### 8.1 Obiettivo
Il trade report deve mostrare chiaramente:
- rendimento lordo
- costi
- rendimento netto finale

### 8.2 Campi da mostrare
#### Sezione risultato
- `trade_return_pct_net`
- `trade_return_pct_gross`
- `pnl_net_raw`
- `pnl_gross_raw`

#### Sezione costi
- `fees_total_raw`
- `funding_total_raw_net`
- `cost_drag_pct`

#### Sezione qualità trade
- `mae_pct`
- `mfe_pct`
- `r_multiple`
- `time_to_fill`
- `time_in_trade`
- `fills_count`
- `close_reason`

---

## 9. Integrazione fee e funding nel report generale

### 9.1 Struttura report generale

#### Sezione 1 — Summary principale
Mostrare solo metriche nette principali:
- `trades_count`
- `win_rate_net`
- `avg_trade_return_pct_net`
- `median_trade_return_pct_net`
- `expectancy_pct_net`
- `profit_factor_net`
- `avg_r_multiple`
- `median_r_multiple`

#### Sezione 2 — Gross vs Net
Tabella comparativa per:
- average trade return %
- median trade return %
- expectancy %
- profit factor

Con colonne:
- gross
- net
- delta costi

#### Sezione 3 — Cost breakdown
- `fees_total_raw`
- `fees_avg_raw`
- `funding_total_raw_net`
- `funding_avg_raw_net`
- `avg_cost_drag_pct`

#### Sezione 4 — Cost sensitivity
- `gross_positive_to_net_negative_count`
- `gross_positive_to_net_negative_pct`
- `trades_with_funding_count`
- `trades_with_funding_pct`

#### Sezione 5 — Trade results table
Per ogni trade:
- signal id
- symbol
- side
- status
- close reason
- gross return %
- net return %
- fees
- funding
- MAE %
- MFE %
- R
- detail link

---

## 10. Interpretazione attesa del report

Il report generale deve consentire di distinguere chiaramente tre casi:

### Caso A
**Gross buono, Net buono**  
La policy è sana sia teoricamente sia operativamente.

### Caso B
**Gross buono, Net debole o negativo**  
La logica è valida ma i costi operativi la rendono fragile o non sostenibile.

### Caso C
**Gross già debole**  
Il problema è nella logica della policy, non nei costi.

---

## 11. Compatibilità e migrazione

### 11.1 Backward compatibility
I vecchi campi possono essere mantenuti temporaneamente solo per compatibilità interna, ma:
- non devono essere usati nel rendering principale
- devono essere marcati come deprecated
- devono essere sostituiti progressivamente nei template report

### 11.2 Migrazione report
Il rendering dei report HTML deve essere aggiornato per:
- usare il nuovo naming
- mostrare net come metrica primaria
- relegare raw/debug in sezioni tecniche o nascoste

---

## 12. Acceptance criteria

### AC-1
Nessun campo con suffisso `_pct` contiene valori raw.

### AC-2
Due trade con stesso rendimento percentuale ma simboli con prezzi nominali diversi producono metriche `%` comparabili.

### AC-3
`trade_return_pct_net` è inferiore o uguale a `trade_return_pct_gross` salvo casi in cui il funding netto sia favorevole e compensi parzialmente o totalmente le fee.

### AC-4
Fee e funding sono visibili come campi separati sia nel trade report sia nel report generale.

### AC-5
Il blocco principale del report generale usa metriche nette e non metriche raw.

### AC-6
Il report generale include una tabella “Gross vs Net”.

### AC-7
Il report generale include una sezione di diagnostica costi con almeno:
- `gross_positive_to_net_negative_count`
- `gross_positive_to_net_negative_pct`
- `trades_with_funding_count`
- `trades_with_funding_pct`

### AC-8
Le metriche aggregate della policy sono calcolate a partire da `trade_return_pct_net` e non da `total_pnl_raw`.

---

## 13. Esclusioni attuali
Questa revisione non introduce ancora un vero modello di capitale/equity portfolio-level. Restano quindi fuori da questa fase:
- sizing reale in valuta/base asset
- equity curve realistica di portafoglio
- total return % su capitale reale
- max drawdown % basato su equity reale

Queste parti potranno essere affrontate in una fase successiva con un capital model dedicato.

---

## 14. Decisione finale di prodotto
Per questa fase, il simulatore viene formalmente trattato come:

**simulatore di ritorni normalizzati per trade/policy, con costi operativi integrati**,  
e non ancora come simulatore completo di equity/capitale reale.
