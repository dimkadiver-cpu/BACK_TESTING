# Allegato PRD — Integrazioni di Prodotto, Policy Operative e GUI Launcher
**Documento:** appendice integrativa al PRD principale `Signal Chain Backtesting Lab`  
**Versione:** annex-1  
**Generata:** 2026-04-05

---

## A1. Scopo dell’allegato

Questo allegato integra il PRD principale con requisiti aggiuntivi necessari per allineare il prodotto alla richiesta utente finale.

Il PRD principale definisce correttamente il core del simulatore event-driven, il modello dati, il replay, le policy di gestione e la struttura degli artifact. Questo allegato aggiunge invece in forma esplicita i requisiti di prodotto che devono essere considerati vincolanti per la progettazione e lo sviluppo.

In particolare, questo allegato formalizza:

1. il workflow completo orientato al **test dei segnali**
2. il supporto a sorgenti dati operative reali
3. la gestione modulare del parser con possibilità di riuso e modifica semplice
4. i requisiti della GUI come **pannello di configurazione e lancio**
5. le variabili configurabili ufficiali delle policy
6. la semantica estesa degli ordini pending
7. i requisiti di packaging e deploy futuri
8. gli acceptance criteria di prodotto mancanti nel documento principale

Questo allegato **non sostituisce** il PRD principale. Lo estende.

---

## A2. Concetto principale del prodotto

Il concetto principale del prodotto è il **test dei segnali**.

Il sistema non deve essere impostato come semplice motore statistico astratto, né come framework generico di backtesting basato su indicatori. Il suo scopo è verificare l’efficacia di segnali e catene operative ottenute da fonti reali, già parse o da parsare, ricostruendo e simulando il loro comportamento in diverse configurazioni operative.

L’oggetto principale di lavoro è quindi uno dei seguenti:

1. **solo segnale iniziale**
2. **segnale iniziale con update significativi**
3. **catena operativa completa**

L’obiettivo funzionale del prodotto è permettere di:

- acquisire dati da una sorgente reale
- applicare o riapplicare parser modulari
- costruire o verificare la chain
- simulare la chain con policy diverse
- generare output strutturati per analisi successive

---

## A3. Workflow di prodotto ufficiale

Il workflow ufficiale del prodotto deve essere il seguente.

### A3.1 Fase 1 — Acquisizione dati
Il sistema deve supportare l’acquisizione di dati da una o più delle seguenti sorgenti:

- canale Telegram
- topic di un canale Telegram
- chat
- dataset o DB già esistente

Nota di progetto:
- il fatto che parte dell’ingestione esista già non elimina questo requisito
- il sistema deve comunque prevedere la possibilità di selezionare, configurare e lanciare l’acquisizione o la rilettura del dataset da interfaccia operativa o pipeline configurata

### A3.2 Fase 2 — Applicazione parser
Il sistema deve consentire l’applicazione del parser per estrarre:

- segnali iniziali
- update operativi
- riferimenti utili alla ricostruzione della chain

Il parser deve essere modulare e riusabile.

Il sistema deve supportare:
- parser già esistenti
- eventuale sviluppo di parser nuovi per trader specifici
- aggiornamento di vocabolario, alias e regole di riconoscimento
- riuso rapido di parser esistenti tramite duplicazione o copia configurata

### A3.3 Fase 2.1 — Costruzione o verifica della chain
Il sistema deve supportare dataset di diversi tipi:

- dataset con catene complete
- dataset con solo segnale iniziale
- dataset single-trader
- dataset multi-trader
- dataset con attribuzione trader già risolta
- dataset con attribuzione trader da verificare

Il sistema deve poter:
- costruire la chain
- verificare la chain esistente
- classificare i casi non simulabili o incompleti

### A3.4 Fase 3 — Simulazione
Il sistema deve supportare la simulazione su:

- solo segnali
- segnali + update significativi
- chain complete
- configurazioni policy diverse applicate allo stesso dataset

La simulazione deve essere parametrica e configurabile.

### A3.5 Fase 4 — Output
Il sistema deve generare output strutturati e auditabili, senza richiedere che la GUI mostri analisi avanzate.

Gli output possono includere:
- event log
- trade result
- scenario result
- comparison result
- trial result optimizer
- export tecnici

---

## A4. Requisiti di acquisizione dati

### A4.1 Sorgenti supportate
Il prodotto deve supportare come sorgenti di input almeno:

- canale Telegram
- topic di canale Telegram
- chat
- DB esistente
- dataset esportato

### A4.2 Modalità operativa
Il sistema deve consentire di:

- selezionare la sorgente
- impostare i parametri minimi di acquisizione o lettura
- lanciare l’acquisizione o rilettura
- salvare l’output nel formato previsto dal sistema

### A4.3 Verifica di funzionalità già esistenti
Se l’ingestione o parte di essa esiste già nel progetto, il prodotto deve prevedere una fase di verifica funzionale esplicita per confermare almeno:

- supporto canale Telegram
- supporto topic Telegram
- supporto chat
- coerenza della persistenza raw
- coerenza dei collegamenti necessari a parser e chain builder

---

## A5. Requisiti di parser management

### A5.1 Obiettivo
Il parser deve essere trattato come componente modulare, riusabile e facilmente adattabile.

### A5.2 Requisiti minimi
Il prodotto deve consentire almeno:

- selezione di un parser esistente
- duplicazione di un parser o profilo parser esistente
- modifica di vocabolario, alias o regole semplici
- test rapido del parser su testo campione
- salvataggio della configurazione parser aggiornata

### A5.3 Requisito di semplicità operativa
Le modifiche semplici al parser devono essere possibili senza dover rifattorizzare il core applicativo.

Questo include almeno uno dei seguenti approcci:
- duplicazione di un parser/profilo esistente
- modifica di file di configurazione/vocabolario
- incolla o editing guidato di configurazione parser

### A5.4 Limite di questo requisito
Questo requisito non implica che l’intero parser debba essere completamente editabile via GUI nel MVP. Implica però che il prodotto debba essere progettato per consentire riuso e modifica rapida di parser e vocabolario senza interventi invasivi sul core.

---

## A6. Requisiti dataset e chain builder

### A6.1 Dataset supportati
Il sistema deve gestire esplicitamente almeno questi tipi di dataset:

- chain-complete
- signal-only
- single-trader
- multi-trader
- trader-attributed
- trader-to-be-validated

### A6.2 Funzioni richieste
Il prodotto deve consentire di:

- costruire una chain a partire dai dati disponibili
- verificare una chain già presente
- classificare i gap del dataset
- determinare se una chain è simulabile

### A6.3 Esiti minimi
Per ogni dataset o chain, il sistema deve poter stabilire almeno:

- simulabile / non simulabile
- chain completa / incompleta
- signal-only nativo / signal-only derivato
- trader attribuito / trader ambiguo
- warning principali

---

## A7. Requisiti GUI ufficiali

### A7.1 Ruolo della GUI
La GUI del sistema deve avere funzione esclusivamente operativa.

La GUI deve essere un **pannello di configurazione e lancio**.

La GUI **non** deve essere progettata come:
- dashboard analitica
- sistema di reportistica
- interfaccia di audit dettagliato
- viewer principale dei risultati avanzati

### A7.2 Cosa deve permettere la GUI
La GUI deve consentire solo:

- selezione sorgenti o dataset
- configurazione parser
- configurazione chain builder
- configurazione policy e variabili di simulazione
- scelta della funzione o pipeline da lanciare
- avvio di run singole, batch, confronti o export
- salvataggio/caricamento preset di configurazione

### A7.3 Cosa può mostrare la GUI
La GUI può mostrare esclusivamente:

- configurazione corrente
- stato del job
- esito sintetico
- warning essenziali
- log operativo minimo
- percorso o riferimento agli artifact generati

### A7.4 Cosa non deve mostrare la GUI MVP
La GUI MVP non deve includere come requisito centrale:

- report di trade dettagliati
- report scenario leggibili in UI
- timeline completa eventi come vista primaria
- dashboard statistiche
- confronto visuale avanzato tra policy
- report HTML embedded

I risultati dettagliati devono esistere come artifact di backend, export o file tecnici separati.

---

## A8. Moduli minimi della GUI

La GUI deve essere articolata in moduli operativi minimi.

### A8.1 Modulo Data Source / Import
Funzioni minime:
- selezione sorgente
- parametri di acquisizione o lettura
- avvio import o rilettura

### A8.2 Modulo Parser Management
Funzioni minime:
- selezione parser
- duplicazione parser
- modifica vocabolario/configurazione
- test rapido parser
- salvataggio configurazione

### A8.3 Modulo Chain Builder
Funzioni minime:
- scelta modalità costruzione/verifica chain
- opzioni single-trader / multi-trader
- scelta dataset signal-only o chain-complete
- avvio costruzione o verifica

### A8.4 Modulo Simulation Setup
Funzioni minime:
- selezione dataset
- selezione policy
- configurazione variabili
- scelta modalità simulazione

### A8.5 Modulo Execution
Funzioni minime:
- lancia simulazione singola
- lancia simulazione batch
- lancia confronto scenari
- lancia optimizer
- lancia export tecnico

### A8.6 Modulo System / Deploy Settings
Funzioni minime:
- percorsi locali
- impostazioni ambiente
- parametri build/package
- future impostazioni licenza/abilitazione

---

## A9. Politica generale sulle variabili configurabili

### A9.1 Obiettivo
Le variabili configurabili della policy devono controllare la logica operativa della simulazione.

### A9.2 Regola generale
Devono entrare nella policy soprattutto le variabili che modificano il comportamento della chain.

Devono invece restare fuori dal set iniziale di ottimizzazione o fuori dal core MVP le variabili che modificano prevalentemente:
- intensità del rischio
- scala economica
- realismo exchange-specific avanzato

### A9.3 Esempio importante: leverage
Il parametro `leverage` non deve essere trattato come variabile centrale della policy MVP né come parametro dello search space iniziale dell’optimizer.

Motivazione:
- modifica soprattutto sizing e distribuzione del rischio
- non modifica in modo primario la logica della chain
- appartiene al layer `risk / portfolio` delle fasi successive

Nel MVP può essere ignorato oppure mantenuto solo come metadato o parametro opzionale del blocco `risk`.

---

## A10. Matrice ufficiale delle variabili configurabili di policy

### A10.1 Struttura generale
La policy deve restare organizzata almeno nei seguenti blocchi:

- `entry`
- `tp`
- `sl`
- `updates`
- `pending`
- `risk`
- `execution`

### A10.2 Variabili MVP obbligatorie o fortemente consigliate

#### Blocco `entry`
- `use_original_entries`
- `entry_allocation`
- `max_entries_to_use`
- `allow_add_entry_updates`

#### Blocco `tp`
- `use_original_tp`
- `use_tp_count`
- `tp_distribution`

#### Blocco `sl`
- `use_original_sl`
- `break_even_mode`
- `be_trigger`
- `move_sl_with_trader`

#### Blocco `updates`
- `apply_move_stop`
- `apply_close_partial`
- `apply_close_full`
- `apply_cancel_pending`
- `apply_add_entry`
- `partial_close_fallback_pct`

#### Blocco `pending`
- `pending_timeout_hours`
- `chain_timeout_hours`
- `cancel_pending_on_timeout`
- `cancel_unfilled_if_tp1_reached_before_fill`
- `cancel_averaging_pending_after_tp1`

#### Blocco `execution`
- `latency_ms`
- `slippage_model`
- `fill_touch_guaranteed`

### A10.3 Variabili esplicitamente rinviate
Le seguenti variabili non sono richieste nel MVP come parte stabile del core:

- `cancel_unfilled_if_tp2_reached_before_fill`
- `cancel_remaining_pending_after_first_fill`
- `cancel_all_pending_after_partial_close`
- `cancel_all_pending_after_break_even`
- `be_offset`
- `risk_percent`
- `fixed_notional`
- `max_leverage`
- modelli avanzati di slippage
- partial fills probabilistici
- funding
- liquidation

### A10.4 Search space iniziale optimizer
Lo search space iniziale dell’optimizer deve restare ristretto.

Parametri iniziali consentiti:
- `entry.entry_allocation`
- `tp.use_tp_count`
- `tp.tp_distribution`
- `sl.be_trigger`
- `pending.pending_timeout_hours`

Le altre variabili devono essere prima stabilizzate come configurazioni scenario-driven e solo successivamente, se necessario, rese ottimizzabili.

---

## A11. Semantica estesa degli ordini pending

### A11.1 Ruolo del blocco `pending`
Il blocco `pending` della policy deve governare il comportamento automatico del motore sugli ordini pendenti.

Regola architetturale:
- il blocco `updates` governa l’applicazione degli update dichiarati dal trader
- il blocco `pending` governa le regole automatiche engine-driven relative agli ordini non ancora eseguiti o residui

### A11.2 Timeout pending
Il sistema deve supportare almeno una regola di timeout configurabile per ordini pending non eseguiti.

Variabili minime richieste:
- `pending_timeout_hours`
- `cancel_pending_on_timeout`

Semantica:
- se un ordine pending non viene eseguito entro `pending_timeout_hours`, il motore deve poterlo cancellare automaticamente
- l’evento deve essere auditabile in `event_log`
- l’esito deve riflettersi nello stato della chain

### A11.3 Cancellazione pending prima del fill se il mercato ha già raggiunto TP1
Il sistema deve supportare regole automatiche per cancellare ordini pending non ancora eseguiti quando il mercato ha già raggiunto `TP1` prima del fill.

Variabile minima richiesta:
- `cancel_unfilled_if_tp1_reached_before_fill`

Semantica:
- la regola si applica solo a ordini ancora pending e mai fillati
- la cancellazione è engine-driven
- deve essere loggata come azione distinta e auditabile
- il comportamento deve essere policy-driven

### A11.4 Cancellazione dell’averaging pending dopo TP1
Il sistema deve supportare la cancellazione automatica di ordini averaging ancora pending quando:

- la prima entry è già stata eseguita
- la posizione risulta attiva
- una entry averaging resta pending
- il mercato raggiunge `TP1`

Variabile minima richiesta:
- `cancel_averaging_pending_after_tp1`

Semantica:
- la regola si applica solo a ordini residui classificati come averaging/additional entry
- non deve cancellare ordini già eseguiti
- deve essere registrata come evento engine-driven auditabile

### A11.5 Distinzione tra `CANCEL_PENDING` trader-driven e cancellazioni automatiche
Il sistema deve distinguere chiaramente tra:

1. `CANCEL_PENDING` richiesto dal trader come evento del dataset
2. cancellazione automatica dei pending generata dal motore in base alla policy

Regola:
- i due casi non devono essere fusi semanticamente
- nel log devono essere distinguibili almeno per `source`
- la richiesta trader e l’azione realmente eseguita devono restare auditabili separatamente

### A11.6 Set minimo pending MVP
Nel MVP il blocco `pending` deve supportare almeno:

- `pending_timeout_hours`
- `chain_timeout_hours`
- `cancel_pending_on_timeout`
- `cancel_unfilled_if_tp1_reached_before_fill`
- `cancel_averaging_pending_after_tp1`

---

## A12. Configurazione di policy di riferimento

Il sistema deve supportare una policy di riferimento almeno equivalente alla seguente.

```yaml
policy:
  name: "original_chain"

  entry:
    use_original_entries: true
    entry_allocation: [0.7, 0.3]
    max_entries_to_use: 2
    allow_add_entry_updates: false

  tp:
    use_original_tp: true
    use_tp_count: 3
    tp_distribution: [0.5, 0.3, 0.2]

  sl:
    use_original_sl: true
    break_even_mode: "initial_entry"
    be_trigger: "tp1"
    move_sl_with_trader: true

  updates:
    apply_move_stop: true
    apply_close_partial: true
    apply_close_full: true
    apply_cancel_pending: true
    apply_add_entry: false
    partial_close_fallback_pct: 0.5

  pending:
    pending_timeout_hours: 12
    chain_timeout_hours: 168
    cancel_pending_on_timeout: true
    cancel_unfilled_if_tp1_reached_before_fill: true
    cancel_averaging_pending_after_tp1: true

  execution:
    latency_ms: 500
    slippage_model: "none"
    fill_touch_guaranteed: true
```

---

## A13. Output e artifact

### A13.1 Regola generale
Il sistema deve produrre artifact strutturati e auditabili anche se la GUI non li espone direttamente come viste avanzate.

### A13.2 Artifact minimi
Il sistema deve poter generare almeno:

- `event_log`
- `trade_result`
- `scenario_result`
- export tecnici strutturati

### A13.3 Ruolo degli artifact
Gli artifact devono costituire la fonte di verità analitica del sistema.

La GUI può limitarsi a mostrare:
- stato del job
- esito sintetico
- warning minimi
- percorso output

---

## A14. Packaging, installazione e deploy

### A14.1 Obiettivo
Il prodotto deve essere progettato in modo da poter essere successivamente distribuito e installato su:

- altro PC
- server
- ambiente operativo separato dal contesto di sviluppo

### A14.2 Requisiti iniziali
Anche se il packaging finale non è parte del bootstrap tecnico immediato, il PRD deve considerare fin da subito:

- build distribuibile
- configurazione ambiente separabile
- percorsi e dipendenze gestibili
- possibilità futura di attivazione o licenza

### A14.3 Licenze / abilitazione
Il sistema di verifica, abilitazione o licenza è esplicitamente considerato una fase successiva.

Tuttavia il prodotto deve essere progettato in modo da non impedire l’introduzione futura di:
- attivazione per macchina
- licenze d’uso
- verifica abilitazione server-side o offline

---

## A15. Acceptance criteria di prodotto aggiuntivi

Il PRD principale deve considerarsi integrato dai seguenti acceptance criteria.

### A15.1 Acquisizione
Il sistema soddisfa il requisito se consente di configurare e lanciare la lettura o acquisizione da almeno una delle sorgenti previste e se l’architettura supporta in modo esplicito:

- canale Telegram
- topic di canale Telegram
- chat
- DB/dataset esistente

### A15.2 Parser
Il sistema soddisfa il requisito se consente il riuso di parser esistenti e la modifica rapida di parser/vocabolario senza richiedere modifiche invasive al core.

### A15.3 Chain building
Il sistema soddisfa il requisito se sa distinguere almeno:

- chain complete
- signal-only
- simulabile / non simulabile
- trader assegnato / ambiguo

### A15.4 GUI
Il sistema soddisfa il requisito GUI se fornisce una interfaccia operativa che consente di configurare e lanciare le funzioni senza imporre viste analitiche avanzate.

### A15.5 Policy
Il sistema soddisfa il requisito policy se supporta almeno il set minimo di variabili definito in questo allegato e se le regole pending sono controllate da policy, non hardcoded.

### A15.6 Pending
Il sistema soddisfa il requisito pending se gestisce almeno:

- timeout pending
- cancellazione pending su timeout
- cancellazione pending non fillato dopo raggiungimento TP1
- cancellazione averaging pending dopo TP1
- distinzione tra `CANCEL_PENDING` trader-driven e cancellation engine-driven

### A15.7 Output
Il sistema soddisfa il requisito output se genera artifact strutturati separati dalla GUI e utilizzabili per audit o analisi successive.

### A15.8 Deploy
Il sistema soddisfa il requisito architetturale di prodotto se è predisposto a packaging e installazione futura fuori dall’ambiente di sviluppo.

---

## A16. Priorità di implementazione suggerita

Ordine suggerito delle integrazioni di questo allegato:

1. verifica ingestione già esistente
2. parser reuse / parser management minimo
3. chain builder verification
4. policy variables MVP
5. pending semantics MVP
6. GUI launcher minimale
7. artifact/export consolidati
8. packaging/deploy readiness

---

## A17. Regola finale di interpretazione

In caso di conflitto apparente tra PRD principale e presente allegato, si applica la seguente regola:

- il PRD principale resta la fonte primaria per il core simulativo, il modello eventi e gli artifact
- il presente allegato integra e rende vincolanti i requisiti di prodotto, GUI operativa, parser modulari, variabili di policy e pending semantics non ancora esplicitati a sufficienza nel documento principale

