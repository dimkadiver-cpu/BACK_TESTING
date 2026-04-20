# Signal Chain Lab — Riferimento UX

Documento tecnico che descrive in dettaglio ogni elemento della GUI: cosa rappresenta, da dove viene il dato, cosa scatena ogni azione. Da usare come guida per redesign, debugging UX, o onboarding di nuovi sviluppatori.

---

## Architettura generale

La GUI è una **singola applicazione NiceGUI** (porta 7777) con tre tab sequenziali ma **non bloccanti**:

```
Tab 01 · Download   →   Tab 02 · Parse   →   Tab 03 · Market & Backtest
```

Lo stato condiviso tra tutti i blocchi vive in **`UiState`** (`src/signal_chain_lab/ui/state.py`). È un dataclass mutabile passato per riferimento a tutti i blocchi al momento del render. Tutti i blocchi leggono e scrivono lo stesso oggetto in memoria.

**Il flusso dati sottostante:**

```
Telegram API
    ↓  (script: parser_test/scripts/import_history.py)
raw_messages (SQLite — tabella grezza)
    ↓  (script: parser_test/scripts/replay_parser.py)
parse_results (tabella con segnali classificati)
    ↓  (script: parser_test/scripts/replay_operation_rules.py)
signals + operational_signals (tabelle normalizzate per backtest)
    ↓  (script: scripts/run_policy_report.py o run_scenario.py)
artifacts/policy_reports/ o artifacts/scenarios/ (HTML + JSON)
```

Il DB SQLite è il **collante** tra tutti i blocchi. Il blocco Download lo crea, il blocco Parse lo riempie, il blocco Backtest lo legge.

---

## Stato condiviso (UiState)

Tutti i campi seguenti sono visibili e modificabili da più blocchi:

| Campo | Tipo | Default | Significato |
|---|---|---|---|
| `downloaded_db_path` | str | `""` | Path del DB creato dal Download. Ereditato come default dal Parse. |
| `parsed_db_path` | str | `""` | Path del DB usato nel Parse. Ereditato come default dal Backtest. |
| `effective_db_path()` | metodo | — | Restituisce `parsed_db_path` se esiste, altrimenti `downloaded_db_path`. |
| `chat_id` | str | `""` | Chat ID Telegram per il download. |
| `topic_id` | str | `""` | Topic ID opzionale (per supergroup con thread). |
| `date_from`, `date_to` | str | `""` | Periodo download. Vuoti se `full_history=True`. |
| `full_history` | bool | `True` | Se True, scarica tutto lo storico senza limiti di data. |
| `download_media` | bool | `False` | Se True, scarica anche le immagini insieme ai testi. |
| `db_output_dir` | str | `"parser_test/db"` | Cartella dove viene salvato il DB dopo il download. |
| `parser_profile` | str | `""` | Trader selezionato per il parse. Vuoto = Auto (rileva automaticamente). |
| `generate_parse_csv` | bool | `False` | Se True, genera CSV di report dopo il parse. |
| `parse_reports_dir` | str | `"parser_test/reports"` | Cartella dove vengono scritti i CSV. |
| `proceed_to_backtest` | bool | `False` | Flag che abilita il pulsante Backtest dopo un parse riuscito. |
| `backtest_policies` | list | `["original_chain","signal_only"]` | Policy selezionate per il backtest. |
| `backtest_trader_filter` | str | `"all"` | Trader filtro applicato al backtest. |
| `backtest_date_from/to` | str | `""` | Filtro data per il backtest (indipendente dal filtro download). |
| `backtest_max_trades` | int | `0` | Limite trade per il backtest. 0 = nessun limite. |
| `backtest_report_dir` | str | `""` | Cartella output report backtest. Vuoto = default automatico. |
| `market_data_dir` | str | `<project>/data/market` | Cartella locale cache OHLCV. |
| `market_data_mode` | str | `"existing_dir"` | `existing_dir` = riusa e integra / `new_dir` = rigenera da zero. |
| `market_data_prepare_mode` | str | `"SAFE"` | `SAFE` = pipeline completa con validation / `FAST` = salta validate full. |
| `market_data_source` | str | `"bybit"` | Sorgente dati di mercato: `bybit` (live) o `fixture` (file locali test). |
| `market_data_ready` | bool | `False` | True dopo prepare riuscito. Sblocca il run backtest immediato. |
| `market_data_checked` | bool | `False` | True solo se anche la validate full è stata eseguita (SAFE mode). |
| `market_validation_status` | str | `"needs_check"` | Stato interno: `needs_check`/`validated`/`gap_validated`/`ready_unvalidated`. |
| `market_validation_fingerprint` | str | `""` | Hash della richiesta corrente. Usato per il cache hit. |
| `timeframe` | str | `"1m"` | Timeframe OHLCV (es. `1m`, `5m`, `1h`). |
| `price_basis` | str | `"last"` | Base prezzo: `last` (standard) o `mark` (mark price derivati). |
| `timeout_seconds` | int | `60` | Timeout massimo per il run backtest. |
| `latest_artifact_path` | str | `""` | Path cartella con gli artifact dell'ultimo backtest. |
| `latest_html_report_path` | str | `""` | Path report HTML dell'ultimo backtest (se generato). |

---

## Tab 01 — Download

**Scopo:** scaricare la cronologia messaggi di un canale/topic Telegram e salvarla in un DB SQLite locale.

**Script eseguito:** `parser_test/scripts/import_history.py`

**Output:** file `parser_test/db/parser_test__chat_<chat_id>[__topic_<topic_id>].sqlite3`

### Sezione: Credenziali Telegram (collassabile)

| Campo | Dato | Sorgente |
|---|---|---|
| **API_ID** | Numero intero (es. `12345678`) | Da https://my.telegram.org — sezione "API development tools" |
| **API_HASH** | Stringa hex 32 caratteri | Stesso URL di API_ID |
| **Numero telefono** | Es. `+39...` | Account Telegram dell'operatore |
| **Codice OTP** | 5 cifre arrivate via SMS/app | Inviato da Telegram al numero inserito |

**Persistenza credenziali:** vengono scritte in `parser_test/.env` come `TELEGRAM_API_ID=...` e `TELEGRAM_API_HASH=...`. Al successivo avvio vengono ricaricate automaticamente.

**Sessione Telethon:** dopo autenticazione OTP riuscita, viene creato `parser_test/parser_test.session` — un file binario Telethon che autentica le sessioni future senza OTP. La sezione credenziali si collassa automaticamente se la sessione è già presente.

**Flusso autenticazione:**
1. L'operatore inserisce API_ID + API_HASH + numero telefono
2. Click "Invia OTP" → la GUI si connette a Telegram e chiede l'invio del codice
3. Il codice arriva sul telefono → l'operatore lo inserisce in "Codice OTP"
4. Click "Conferma OTP" → sessione salvata, sezione collassa

**Bottone "Azzera sessione e credenziali":** elimina il file `.session` e rimuove API_ID/HASH dal `.env`. Utile per cambiare account.

### Sezione: Configurazione download

| Campo | Dato | Dove va |
|---|---|---|
| **Chat ID** | Numero negativo (es. `-1001234567890`) per supergroup, o `@username` | `state.chat_id` → `--chat-id` nello script |
| **Topic ID** | Numero intero del thread (opzionale) | `state.topic_id` → `--topic-id` nello script |
| **ID sorgente** (label) | Calcolato live: `chat_id/topic_id` o solo `chat_id` | Solo visualizzazione, non editabile |
| **Tutto lo storico** | Toggle boolean | Se attivo, nasconde i campi data |
| **Dal / Al** | Date nel formato `YYYY-MM-DD` (selettore nativo) | `state.date_from/date_to` → `--from-date`/`--to-date` |
| **Contenuto** | Radio: `Solo testo` / `Testo + immagini` | `state.download_media` → flag `--download-media` |
| **Cartella DB** | Path filesystem | `state.db_output_dir` → usato per costruire il path output |

**Nome file DB generato:** `parser_test__chat_<chat_id>[__topic_<topic_id>].sqlite3` — caratteri non alfanumerici vengono sostituiti da `_`.

### Post-download

Il log mostra un **riepilogo automatico** leggendo direttamente il DB appena creato:
- `raw_messages`: totale righe scaricate
- `rows_with_media`: righe con flag `has_media = 1`
- `blob_media`: righe con blob binario salvato (`media_blob IS NOT NULL`)
- `foto`: righe con `media_kind = 'photo'`
- `blob_immagine`: righe con blob immagine (`media_mime_type LIKE 'image/%'`)

**"Usa come DB attivo"** (pulsante post-download nel mockup, non ancora in produzione): scrive `state.downloaded_db_path` con il path del DB appena scaricato. Il campo DB del blocco Parse si popola di conseguenza tramite `effective_db_path()`.

**"Elimina DB scaricato"**: chiama `Path.unlink()` sul file, azzera `state.downloaded_db_path`. Se lo stesso path era già in `parsed_db_path`, azzera anche quello.

---

## Tab 02 — Parse

**Scopo:** riprocessare un DB di messaggi grezzi attraverso il parser, applicare le operation rules, costruire le chain di segnali, e produrre un quality report per decidere se il DB è pronto per il backtest.

**Script eseguiti (3 fasi):**
1. `parser_test/scripts/replay_parser.py` — classifica ogni messaggio raw → `parse_results`
2. `parser_test/scripts/replay_operation_rules.py` — materializza `signals` e `operational_signals`
3. (In-process) `SignalChainBuilder.build_all_async()` + `validate_chain_for_simulation()` — costruisce chain e calcola il quality report

**Output principale:** tabelle `parse_results`, `signals`, `operational_signals` nel DB. Opzionale: CSV in `parser_test/reports/`.

### Campi

| Campo | Dato | Fonte default |
|---|---|---|
| **DB da parsare** | Path file `.sqlite3` | `state.effective_db_path()` — preferisce il DB parsato, poi quello scaricato |
| **Trader filtro** | Dropdown: Auto / trader_a / trader_b / trader_c / trader_d / trader_3 | `state.parser_profile` |
| **Genera CSV** | Toggle | `state.generate_parse_csv` |
| **Cartella CSV** | Path directory | `state.parse_reports_dir` (default `parser_test/reports`) |

**"Auto" (trader filtro vuoto):** il parser rileva automaticamente il trader in base al contenuto dei messaggi. Usare solo se il DB contiene messaggi di un solo trader o se si vuole riprocessare tutti.

**Selezionare un trader specifico:** forza tutti i messaggi ad essere trattati con il profilo di quel trader, ignorando la detection automatica. Utile per debug o DB mono-trader.

### Quality Report (generato post-parse)

Il report viene costruito **in-process** (non via script esterno) leggendo il DB appena aggiornato. Mostra:

| Metrica | Cosa misura |
|---|---|
| **Messaggi totali** | `COUNT(*) FROM parse_results` (filtrato per trader se selezionato) |
| **NEW_SIGNAL completi** | Segnali nuovi con `completeness = 'COMPLETE'` |
| **NEW_SIGNAL incompleti** | Segnali nuovi con `completeness != 'COMPLETE'` |
| **UPDATE** | Messaggi classificati come aggiornamenti a segnali precedenti |
| **UPDATE orfani** | UPDATE con target non risolto (nessun segnale corrispondente trovato) |
| **INFO_ONLY** | Messaggi informativi senza azioni di trading |
| **UNCLASSIFIED** | Messaggi non riconosciuti dal parser |
| **Chain totali** | Segnali ricostruiti come chain complete (via `SignalChainBuilder`) |
| **Chain simulabili** | Chain che passano la validation per il backtest |
| **Righe operational_signals** | Righe nella tabella usata dal backtest |
| **Backtest ready** | `True` se `operational_new_signal_rows > 0 AND len(chains) > 0` |
| **Top 5 warning** | Warning più frequenti da `parse_results.warning_text` + validation gaps |

**Il pulsante Backtest si abilita/disabilita** in base a `report.backtest_ready`. Se il DB non ha chain simulabili, il backtest è bloccato (non è un wizard lock UI, è una protezione logica).

---

## Tab 03 — Market & Backtest

Questo tab contiene due sezioni integrate ma distinte: la pipeline dei **market data** e il **run del backtest**. Le due sezioni condividono gli stessi filtri di contesto.

---

### Sezione A — Market Data

**Scopo:** costruire e/o verificare la cache locale OHLCV necessaria per il backtest. I dati di mercato non vengono scaricati in tempo reale durante il backtest: devono essere preparati in anticipo e messi in una cache locale.

**Pipeline in 4 fasi (da codice):**

```
Fase 1 — Planner   (scripts/plan_market_data.py)
  Legge il DB parsato → determina quali simboli e quali intervalli temporali
  sono necessari per il backtest con i filtri correnti.
  Output: artifacts/market_data/plan_market_data.json

Fase 2 — Sync      (scripts/sync_market_data.py)  [solo se ci sono gap]
  Confronta il piano con la cache locale → scarica i gap mancanti dalla
  sorgente (bybit o fixture).
  Output: artifacts/market_data/sync_market_data.json

Fase 3 — Gap Validate  (scripts/gap_validate_market_data.py)  [solo se ci sono gap]
  Verifica che i gap appena sincronizzati siano stati riempiti correttamente.
  Output: artifacts/market_data/gap_validate_market_data.json

Fase 4 — Validate full  (scripts/validate_market_data.py)  [solo in SAFE mode]
  Verifica la consistenza completa della cache locale contro il piano.
  Output: artifacts/market_data/validate_market_data.json
```

**Cache fingerprint:** ogni richiesta di prepare viene "firmata" con un hash che include DB path + filtri + timeframe + price_basis + source. Se il fingerprint corrisponde a un record PASS nell'indice di validazione (`artifacts/market_data/validation_index.json`), le fasi 1-4 vengono saltate interamente (cache hit).

### Campi Market Data

| Campo | Dato | Valore/Opzioni |
|---|---|---|
| **Cartella market data** | Path directory cache OHLCV locale | Default: `<project>/data/market` |
| **Modalità cartella** | Radio | `existing_dir`: usa e integra gap / `new_dir`: rigenera da zero |
| **Timeframe** | Input testo | Es. `1m`, `5m`, `15m`, `1h` — default `1m` |
| **Price basis** | Select | `last` (prezzo last standard) / `mark` (mark price, rilevante per futures) |
| **Market source** | Select | `bybit` (API Bybit live) / `fixture` (file locali per test) |
| **Timeout (s)** | Numero | Default 60s — limite per il run backtest (non per il prepare) |
| **Prepare mode** | Radio | `SAFE` (esegue tutte e 4 le fasi) / `FAST` (salta la fase 4 validate full) |

**Quando usare FAST:** quando si vuole velocizzare un ciclo di test e si è già convinti che la cache locale sia consistente. I dati sono comunque pronti per il backtest, ma manca la verifica finale di consistenza. La GUI mostra uno stato "pronti ma non validati in questa run".

**Quando usare SAFE:** in produzione o dopo modifiche ai filtri. Garantisce che la cache locale corrisponda esattamente a quanto richiesto dal DB con i filtri correnti.

### Stato market data (label inline)

La label `market_status` mostra lo stato corrente in testo:

| Testo | Condizione |
|---|---|
| "Market data da verificare" | Stato iniziale o dopo modifica di un input |
| "Market data: planner in esecuzione..." | Fase 1 in corso |
| "Market data: sync gap mancanti..." | Fase 2 in corso |
| "Market data: gap validation in corso..." | Fase 3 in corso |
| "Market data: validazione in corso..." | Fase 4 in corso |
| "Market data validati" | Pipeline SAFE completata, nessun gap |
| "Market data pronti, gap validati" | Pipeline SAFE completata, gap erano presenti ma ora validati |
| "Market data pronti ma non validati in questa run" | FAST mode completato |
| "Validation cache hit: ..." | Fingerprint trovato nell'indice PASS |

**Qualsiasi modifica a un input** (cartella, timeframe, price basis, source, prepare mode) chiama `_invalidate_market_readiness()` che azzera tutti i flag e riporta lo stato a "da verificare". Il backtest viene disabilitato automaticamente.

---

### Sezione B — Backtest

**Scopo:** eseguire il confronto tra una o più policy di trading sui segnali parsati, usando la cache OHLCV come dati di mercato.

**Script eseguiti:**
- **Policy singola:** `scripts/run_policy_report.py --policy <nome> ...`
- **Policy multiple:** `scripts/run_scenario.py --policies <p1> <p2> ...`

La distinzione è automatica: se è selezionata 1 policy, usa `run_policy_report.py` e salva in `artifacts/policy_reports/`; se ne sono selezionate 2+, usa `run_scenario.py` e salva in `artifacts/scenarios/`.

### Campi Backtest

| Campo | Dato | Fonte |
|---|---|---|
| **DB parsato** | Path file `.sqlite3` | `state.effective_db_path()` — editabile |
| **Policy** | Multi-select da file YAML in `configs/policies/` | Scoperte dinamicamente via `discover_policy_names()` |
| **Trader filtro** | Dropdown: Tutti / trader_a / ... | Scoperto dal DB via `discover_traders_from_db()` |
| **Dal / Al** | Date `YYYY-MM-DD` | Auto-popolate dalla data min/max nel DB via `discover_date_range_from_db()` |
| **Max trade** | Numero (0 = nessun limite) | `state.backtest_max_trades` |
| **Cartella report** | Path directory | Default auto: `artifacts/policy_reports` o `artifacts/scenarios` |

**Bottone "Rileva" (accanto al trader filter):** lancia `discover_traders_from_db()` che fa una query sul DB e popola il dropdown con i trader reali presenti. Le date min/max vengono anche auto-popolate nei campi data.

**Differenza filtri Backtest vs filtri Download:**
- I filtri del Download controllano **quanti messaggi vengono scaricati da Telegram**
- I filtri del Backtest controllano **quanti trade vengono inclusi nel calcolo dei risultati**
- Sono indipendenti: si può scaricare tutto lo storico e fare backtest su un sottoinsieme specifico

### Policy

Le policy sono file YAML in `configs/policies/`. Ogni policy definisce le regole di gestione di una trade (quando entrare, quando uscire, come muovere lo stop, ecc.).

Il **Policy Studio** (pulsanti Modifica / Nuova) apre un dialog con editor YAML inline:
- **Modifica:** carica il YAML della prima policy selezionata, permette modifica e salvataggio sovrascrivendo il file originale oppure "Salva come nuova"
- **Nuova:** crea un nuovo file YAML partendo da un template (prima policy esistente), con nome validato `[a-z][a-z0-9_-]*`

**Ricarica:** rilegge la cartella `configs/policies/` e aggiorna il dropdown. Utile dopo aver aggiunto policy via terminale o editor esterno.

### Flusso completo al click "Esegui Backtest"

```
1. Valida input (DB path, policy selezionate, date coerenti)
2. Se market_data_ready = False:
   → esegue automaticamente _prepare_market_data() prima di procedere
3. Costruisce il comando (single/multi policy)
4. Esegue il comando con asyncio.wait_for(timeout=state.timeout_seconds)
5. Parsea il log per estrarre:
   - chains_selected=N  (righe che iniziano con questa key)
   - righe che matchano il regex summary (policy/pnl/win_rate/expectancy/trades/excluded)
   - scenario_html= o policy_report_html= (path del report HTML)
6. Renderizza la summary table con i risultati
7. Scrive un entry nel benchmark file (artifacts/market_data/backtest_benchmark.json)
```

### Summary Results (post-backtest)

Per ogni policy eseguita, il log viene parsato con regex per estrarre:

```
- <policy>: pnl=<float>, win_rate=<float>%, expectancy=<float>, trades=<int>, excluded=<int>
```

La tabella mostrata nella UI mostra questi valori. Il link "Apri report HTML" apre il file con `file://` URI direttamente nel browser.

---

## Interazioni tra blocchi

### Propagazione del DB

```
Block 1: scarica → state.downloaded_db_path = "/path/to/file.sqlite3"
Block 2: legge   → parse_db.value = state.effective_db_path()
                   (= downloaded_db_path se parsed_db_path è vuoto)
Block 2: parsata → state.parsed_db_path = "/path/to/file.sqlite3"
Block 3: legge   → backtest_db.value = state.effective_db_path()
                   (= parsed_db_path, preferito su downloaded_db_path)
```

### Abilitazione del Backtest

Il pulsante "Esegui Backtest" si abilita solo se:
- `db_path` esiste sul filesystem
- `market_data_dir` è stato inserito

Il flag `proceed_to_backtest` (impostato dal Parse) è usato internamente ma **non** blocca fisicamente il tab: l'utente può sempre aprire il Tab 03 e inserire un DB manualmente.

### Invalidazione market data

Ogni volta che cambiano: DB path, trader filter, date, max trades, cartella market, timeframe, price basis, source, prepare mode o modalità cartella → `_invalidate_market_readiness()` azzera lo stato e impone un nuovo ciclo di prepare prima del prossimo backtest.

---

## Artifact generati

| Artifact | Path | Generato da | Contenuto |
|---|---|---|---|
| DB messaggi grezzi | `parser_test/db/*.sqlite3` | Block 1 - Download | `raw_messages` table |
| DB parsato | stesso file SQLite | Block 2 - Parse | `parse_results`, `signals`, `operational_signals` |
| Plan market data | `artifacts/market_data/plan_market_data.json` | Fase 1 Prepare | Lista simboli e intervalli necessari |
| Sync report | `artifacts/market_data/sync_market_data.json` | Fase 2 Prepare | Risultato download gap |
| Gap validate report | `artifacts/market_data/gap_validate_market_data.json` | Fase 3 Prepare | Verifica gap sincronizzati |
| Validate report | `artifacts/market_data/validate_market_data.json` | Fase 4 Prepare (SAFE only) | Verifica consistenza cache completa |
| Validation index | `artifacts/market_data/validation_index.json` | Fine Prepare | Indice fingerprint → PASS/FAIL per cache hit |
| Policy report HTML | `artifacts/policy_reports/<nome>/` | Backtest (policy singola) | Report interattivo per una policy |
| Scenario HTML | `artifacts/scenarios/<nome>/` | Backtest (multi-policy) | Report comparativo tra policy |
| Benchmark JSON | `artifacts/market_data/backtest_benchmark.json` | Fine Backtest | Storico timing di tutti i run |
| CSV parse reports | `parser_test/reports/*.csv` | Block 2 - Parse (opzionale) | Dati parse in formato tabellare |

---

## Log panel — cosa aspettarsi

Ogni blocco ha il suo log panel terminale. I log vengono scritti in streaming durante l'esecuzione degli script.

### Pattern di log rilevanti

**Block 1 (Download):**
```
Avvio download da -1001234567890/8
Periodo: 2024-01-01 -> 2024-06-30
Sessione Telegram: parser_test/parser_test.session
DB destinazione: parser_test/db/parser_test__chat_...sqlite3
Verifica DB: messaggi=1247, righe_con_media=312, ...
```

**Block 2 (Parse):**
```
Fase 1/3 - Parse: avvio replay_parser.py
Fase 1/3 - Parse: completata.
Fase 2/3 - Operation rules: materializzo signals/operational_signals
Pulizia tabelle derivate completata: operational_signals=450, signals=210
Fase 3/3 - Chain builder: costruzione report di ricostruzione catene
Backtest: DB pronto.
```

**Block 3 (Market Data):**
```
Fase market 1/4 - Planner: analisi copertura
Market data: timeframe=1m, basis primaria=last
Market data: source=bybit
Fase market 1/4 - Planner: completata. simboli=12, intervalli=8640, gap=240
Fase market 2/4 - Sync: avvio integrazione gap mancanti
Fase market 3/4 - Gap Validation: verifica mirata dei gap
Fase market 4/4 - Validate: verifica consistenza cache  [solo SAFE]
Validation index aggiornato: artifacts/market_data/validation_index.json
```

**Block 3 (Backtest):**
```
--- Backtest multi-policy / comparison report: original_chain, signal_only ---
chains_selected=247
- original_chain: pnl=18.4, win_rate=62.0%, expectancy=0.74, trades=247, excluded=12
- signal_only: pnl=11.2, win_rate=58.0%, expectancy=0.52, trades=247, excluded=8
scenario_html=artifacts/scenarios/run_20240419/report.html
Timing fase Backtest: 12.34s
Benchmark snapshot: avg_backtest=12.34s, avg_prepare=4.20s
```

---

## Errori comuni e cosa significano nella UI

| Messaggio UI | Causa | Azione |
|---|---|---|
| "Sessione Telegram non trovata" | File `.session` assente | Autenticare con API_ID + OTP |
| "API_ID o API_HASH non validi" | Credenziali errate o non salvate | Verificare su my.telegram.org |
| "Seleziona un DB parsato prima del backtest" | `effective_db_path()` vuoto | Selezionare un DB manualmente o eseguire Parse |
| "Seleziona almeno una policy" | Lista policy vuota | Selezionare almeno una policy dal dropdown |
| "DB parsato non trovato" | Il file non esiste più sul filesystem | Re-eseguire Download o selezionare un DB esistente |
| "La cartella market data selezionata non esiste" | `existing_dir` mode con path inesistente | Creare la cartella o cambiare modalità a `new_dir` |
| "Timeout backtest" | Esecuzione ha superato `timeout_seconds` | Aumentare il timeout o ridurre i trade/policy |
| "Parse completato, ma il DB non contiene ancora chain backtestabili" | `backtest_ready = False` dopo parse | Controllare il quality report: se ci sono 0 chain simulabili, il DB è probabilmente malformato o il trader è sbagliato |
| "FAST mode: market data pronti senza validazione" | Prepare mode = FAST | Normale in FAST mode — non è un errore |

---

*Versione: 1.0 — generato il 2026-04-19*
