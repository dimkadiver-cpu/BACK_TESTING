# Market DATA nel Blocco 3

Documento di revisione dettagliata e proposta di rifattorizzazione del processo Market Data,
con focus su GUI, planner, sync, validazione, provider runtime e coerenza con il simulatore.

*Contesto: repository BACK_TESTING · Ambito: Blocco 3 / Backtest · Lingua: ITA*

> **Sintesi esecutiva**
>
> La logica Market Data esiste già ma oggi è distribuita tra UI del Blocco 3, stato condiviso, script planner/sync/validate e provider runtime. La proposta è estrarre tutto in un sotto-blocco dedicato “Market DATA”, introdurre una preview leggibile dei simboli e dei periodi richiesti, rendere la validazione una scelta esplicita, separare il tempo di simulazione dal tempo di visualizzazione del chart, e preparare il sistema a una gestione multi-timeframe più efficiente (parent timeframe + detail timeframe).

# 1. Obiettivo del documento

Questo documento consolida lo stato attuale del processo Market Data, evidenzia i limiti principali e definisce una proposta operativa per ristrutturare il Blocco 3 della GUI. L’obiettivo non è solo migliorare l’interfaccia, ma anche rendere il processo più coerente con la logica del simulatore, più leggibile per l’utente e più estendibile in futuro.

# 2. Stato attuale: processo end-to-end

## 2.1 Sequenza attuale

1. L’utente seleziona il DB parsato nel Blocco 3.
1. Configura cartella market, modalità dataset, timeframe, basis, source e modalità SAFE/FAST.
1. La GUI costruisce una request Market Data e calcola un fingerprint per la cache di validazione.
1. Se trova una validazione PASS compatibile, considera i dati pronti e salta il lavoro.
1. Altrimenti lancia in sequenza planner, sync, gap validation e validate full (solo in SAFE).
1. Il backtest usa poi il provider parquet locale per leggere i dati e simulare la chain.
## 2.2 Componenti principali oggi coinvolti

| Area | Responsabilità attuale | File principali | Criticità |
| --- | --- | --- | --- |
| UI Backtest | Configura e lancia prepare/verify market data | block_backtest.py | Logica Market mescolata al Backtest |
| Stato condiviso | Persistenza opzioni e risultati intermedi | state.py | Molte variabili Market nello stato globale |
| Planner | Deriva simboli e finestre richieste dal DB | demand_scanner.py, coverage_planner.py, plan_market_data.py | Logica non ancora simulation-aware |
| Sync | Scarica e integra i gap mancanti | sync_market_data.py, bybit_downloader.py | Supporto reale limitato a OHLCV last/mark |
| Validation | Verifica schema, timestamp, duplicati, copertura | gap_validate_market_data.py, validate_market_data.py, validation.py | Validazione minima, non OHLC-strong |
| Runtime provider | Serve le candele al simulatore | bybit_parquet_provider.py | Legge solo i dati già preparati |

## 2.3 Modalità attuali

- Dataset: usa cartella esistente e integra i gap mancanti / prepara da capo in una nuova cartella.
- Validazione: SAFE (planner + sync + gap validation + validate full) / FAST (planner + sync + gap validation).
- Dati realmente supportati oggi: OHLCV basis last e mark.
- Source reale oggi: Bybit; esiste anche fixture per test.
# 3. Problemi rilevati

## 3.1 Problemi di UX e leggibilità

- La parte Market Data non è un sottosistema visibile e leggibile: è una porzione del Blocco 3.
- Manca una preview esplicita dei simboli rilevati e dei periodi richiesti prima del download.
- Il log è solo testuale; manca una progress bar con fasi e percentuali.
- La validazione non è presentata come scelta utente chiara.
## 3.2 Problemi di coerenza funzionale

- Il planner usa open, last relevant update e status per stimare la finestra; non considera ancora in modo forte le esigenze del chart.
- Il timeframe configurato è usato sia per il download sia per il provider runtime, senza separare parent timeframe, detail timeframe e eventuale timeframe di visualizzazione.
- La validazione attuale protegge da file rotti o copertura insufficiente, ma non garantisce qualità OHLC forte né continuità interna completa.
- Il sistema non è ancora pronto a rappresentare in GUI tipi dati futuri (funding, open interest, liquidations, order book) senza una struttura più modulare.
## 3.3 Impatto sul simulatore

> **Osservazione chiave**
>
> Se il range Market Data è troppo corto, il problema non riguarda solo il chart. Il simulatore può non vedere TP/SL, non attivare azioni engine successive o non arrivare correttamente a un timeout. I comandi trader espliciti continuano a funzionare, ma la parte market-based della simulazione diventa incompleta.

# 4. Obiettivi della revisione

- Separare chiaramente Market Data da Backtest, pur mantenendo il sotto-blocco dentro Blocco 3.
- Rendere il workflow leggibile: DB → discovery → planning → sync → validation → readiness.
- Permettere all’utente di scegliere in modo chiaro se validare oppure no.
- Offrire una preview dei simboli e delle finestre richieste prima di scaricare.
- Preparare il sistema a una gestione multi-timeframe più efficiente.
- Introdurre una struttura che consenta in futuro nuovi tipi dati senza riscrivere l’intera UI.

# 5. Proposta di nuovo sotto-blocco “Market DATA”

## 5.1 Posizionamento UI

Il sotto-blocco Market DATA deve vivere all’interno del Blocco 3 ma come sezione collassabile autonoma, con lifecycle proprio. Il Backtest deve limitarsi a consumare uno stato sintetico: market_ready, validation_status, artifacts e preview.

## 5.2 Struttura consigliata della sezione

| Sezione | Contenuto | Azione utente | Output |
| --- | --- | --- | --- |
| Setup | Root market, dataset mode, validate mode, source, timeframe, buffer, tipo dati | Configura | Request pronta |
| Discovery | Simboli rilevati, finestre richieste, gap stimati, cache hit/miss | Analizza | Preview leggibile |
| Run | Planner, sync, gap validation, validate full | Prepara / Valida | Progress + log |
| Result | Artifacts, coverage summary, validation summary, readiness | Controlla stato | Market pronto |

## 5.3 Elementi UI da introdurre

- Sezione collassabile “Market DATA”.
- Progress bar globale con percentuale e fase corrente.
- Log dettagliato con righe strutturate per fase.
- Riepilogo numerico: simboli, intervalli richiesti, gap, cache hit, artifacts.
- Pulsanti distinti: Analizza, Prepara, Valida, Prepara + Valida.
# 6. Workflow proposto

1. Carico il DB parsato.
1. Analizzo i simboli presenti nel DB selezionato.
1. Analizzo i periodi richiesti per simbolo e mostro una preview.
1. Scelgo modalità dataset: integra gap su cartella esistente oppure prepara nuova cartella.
1. Scelgo modalità validazione: Full, Light oppure No validation / Trust existing.
1. Scelgo la logica buffer: Auto planner oppure Manuale.
1. Scelgo timeframe e tipo dati da preparare.
1. Lancio prepare e seguo l’avanzamento con progress bar e log.
1. Verifico il risultato finale e solo allora eseguo il backtest.
# 7. Opzioni utente raccomandate

## 7.1 Dataset

- Usa cartella esistente e integra i gap mancanti.
- Prepara da capo in una nuova cartella.
## 7.2 Validazione

| Modalità | Cosa fa | Uso consigliato |
| --- | --- | --- |
| Full | Planner + sync + gap validation + validate full | Run importanti, QA, baseline |
| Light | Planner + sync + gap validation | Uso quotidiano, iterazione rapida |
| Off / Trust existing | Riusa dataset esistente senza validazione completa | Power user, dataset già verificato |

## 7.3 Buffer / finestra

La logica buffer non deve più essere solo nascosta nel planner. Va resa una scelta esplicita:

- AUTO: usa il planner adattivo attuale come baseline.
- MANUAL: permette di impostare pre-buffer e post-buffer in giorni, settimane o mesi.
- Preset rapidi opzionali: Intraday, Swing, Position, Custom.
## 7.4 Timeframe

Per evitare ambiguità future, i timeframe devono essere separati in tre concetti:

- Download TF / Base TF: dati da scaricare e memorizzare.
- Simulation TF / Parent TF: timeframe su cui il motore esegue la scansione principale.
- Detail TF / Child TF: timeframe più fine usato solo dove serve precisione.
## 7.5 Tipi di dati

| Tipo dato | Stato oggi | UI consigliata | Note |
| --- | --- | --- | --- |
| OHLCV last | Supportato | Toggle attivo | Base principale per trigger |
| OHLCV mark | Supportato | Toggle attivo | Utile per basis mark |
| Funding rate | Parzialmente predisposto | Voce roadmap/disabilitata | Manca wiring completo nel core |
| Open interest | Non supportato | Voce roadmap/disabilitata | Richiede downloader e provider nuovi |
| Liquidations | Non supportato | Voce roadmap/disabilitata | Non basta la sola UI |
| Bid/ask spread reale | Non supportato | Voce roadmap/disabilitata | Richiede modelli esecutivi nuovi |
| Order book | Non supportato | Voce roadmap/disabilitata | Richiede storage e simulator order-book-aware |
| Fees exchange | Parametro di policy | Sezione separata Cost Model | Non va nel gruppo Market DATA |

# 8. Revisione della logica di planning

## 8.1 Limite attuale

Oggi il planner sceglie il periodo da scaricare usando apertura chain, ultimo update rilevante e stato. Questo è utile ma non abbastanza: non tiene ancora conto della finestra necessaria per il chart, né consente all'utente di controllare esplicitamente il buffer.

## 8.2 Obiettivo del nuovo planner

- Diventare chart-aware: scaricare abbastanza dati per mostrare livelli e contesto nel report.
- Separare execution window e chart window.
- Rendere il buffer una scelta esplicita dell’utente: AUTO (planner adattivo) oppure MANUAL (pre-buffer e post-buffer configurabili con preset Intraday / Swing / Position / Custom).

## 8.3 Regola proposta per la finestra chart

- La chart window deve includere un pre-buffer e un post-buffer visuale indipendenti dalla sola execution window.
- La finestra finale da scaricare è l’unione di execution window e chart window.
- Questo evita casi in cui il simulatore è quasi corretto ma il chart taglia i livelli TP/SL.
# 9. Simulazione più veloce e più accurata

Per ottenere velocità e precisione insieme, la direzione consigliata è una simulazione gerarchica: parent timeframe per la scansione veloce e child timeframe più fine solo nelle barre candidate.

## 9.1 Modello consigliato

- Parent TF: 15m o 1h come scansione principale.
- Child TF: 1m per risolvere i casi dove la barra parent potrebbe contenere un evento operativo.
- Discesa al child solo se la barra parent tocca livelli rilevanti o contiene un evento trader intra-bar.
## 9.2 Barre candidate

- Possibile touch di una entry pending.
- Possibile touch dello SL corrente.
- Possibile touch del TP corrente.
- Possibile collisione SL/TP.
- Presenza di un update trader dentro la barra parent.
- Presenza di confini temporali importanti (timeout, cambio stato, ecc.).
> **Principio operativo**
>
> Il timeframe maggiore non deve decidere l’esecuzione finale. Deve solo escludere rapidamente le barre inerti. Il timeframe più fine decide fill, TP, SL e ordine degli eventi nei casi ambigui o sensibili.

# 10. Proposta di refactor tecnico

## 10.1 Nuovi moduli consigliati

| Nuovo modulo | Scopo | Contenuto suggerito |
| --- | --- | --- |
| ui/blocks/market_data_panel.py | UI dedicata Market DATA | Setup, Discovery, Run, Result, progress bar, log, preview |
| ui/blocks/market_data_support.py | Helpers UI e orchestrazione | Parsing stdout, progress, mapping fasi, formatting summary |
| market/planning/* | Planner evoluto | Execution window, chart window, buffer manuale con preset |
| market/runtime_config.py | Configurazione runtime coerente | Download TF, simulation TF, detail TF, basis, source |

## 10.2 Revisione dello stato UI

- Raggruppare gli attributi Market Data in una sotto-struttura o dataclass dedicata.
- Separare opzioni di setup, risultati discovery, risultati validation e stato readiness.
- Ridurre il numero di variabili Market sparse nella dataclass principale UiState.
## 10.3 Protocollo log e progress

Tutti gli script Market dovrebbero emettere un protocollo stdout standardizzato, ad esempio:

PHASE=discover | planner | sync | gap_validate | validate
PROGRESS=37
STEP=12/31
SUMMARY=...

La GUI legge queste righe, aggiorna la barra percentuale, mostra la fase corrente e continua ad appendere il log testuale integrale.

## 10.4 Azioni file-per-file

| File | Intervento | Priorità |
| --- | --- | --- |
| ui/blocks/block_backtest.py | Estrarre la parte Market DATA in un panel dedicato e lasciare al Backtest solo il consumo di market_ready | Alta |
| ui/state.py | Introdurre una sotto-struttura MarketState | Alta |
| ui/app.py | Nuova composizione del Blocco 3 senza cambiare il tab workflow generale | Media |
| market/planning/coverage_planner.py | Supportare execution window, chart window e buffer manuale | Alta |
| scripts/plan_market_data.py | Accettare parametri aggiuntivi di buffer (mode, pre/post days, preset) | Alta |
| scripts/sync_market_data.py | Uniformare output progressivo | Media |
| scripts/gap_validate_market_data.py | Uniformare output progressivo | Media |
| scripts/validate_market_data.py | Uniformare output e valutare validazione incrementale | Alta |
| market/planning/validation.py | Rafforzare controlli OHLC e continuità interna | Alta |

# 11. Criteri di accettazione

- L’utente vede una sezione Market DATA collassabile, separata e autosufficiente dentro Blocco 3.
- Prima del download è disponibile una preview dei simboli e delle finestre richieste.
- L’utente può scegliere chiaramente la modalità di validazione.
- La GUI mostra una progress bar e una fase corrente leggibile.
- Il processo produce un riepilogo finale con artifacts, coverage e validation status.
- Il planner garantisce una finestra sufficiente per il chart tramite buffer manuale configurabile (AUTO / MANUAL con preset).
- La struttura consente in futuro di aggiungere nuovi tipi dati senza riscrivere il flusso base.
# 12. Roadmap consigliata

1. Fase 1 – Refactor UI: estrazione del sotto-blocco Market DATA, progress bar, preview discovery, nuove opzioni chiare.
1. Fase 2 – Planner evoluto: execution window, chart window, buffer manuale con preset.
1. Fase 3 – Validazione rafforzata: controlli OHLC, continuità interna, severity più ricca, modalità incrementale.
1. Fase 4 – Multi-timeframe intelligente: parent TF + child TF selettivo.
1. Fase 5 – Estensioni future: funding, open interest, liquidations, spread, order book, profilo fee separato.
# Conclusione

La revisione proposta non è un semplice restyling della GUI. È una riorganizzazione del processo Market Data come sottosistema autonomo, in grado di dialogare meglio con il planner, con la validazione e con il simulatore. La priorità iniziale dovrebbe essere: estrarre la UI dedicata, rendere visibile la discovery, chiarire le modalità di validazione e correggere la logica di planning per supportare sia il motore sia il chart.
