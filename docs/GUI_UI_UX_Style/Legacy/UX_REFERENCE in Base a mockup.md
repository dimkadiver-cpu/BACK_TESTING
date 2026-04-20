# Signal Chain Lab — Riferimento UX

Documento tecnico basato sul mockup `ui_mockup.html` v4. Descrive ogni elemento visibile nella GUI: layout, campi, dati rappresentati, provenienza, e comportamento interattivo.

---

## Struttura generale

```
Nav fissa (42px, max-width 980px centrata)
│
├── Tab 01 · Download
├── Tab 02 · Parse
└── Tab 03 · Market Data & Backtest
      ├── [Contesto condiviso — collassabile]
      └── Card con sub-tab
            ├── Market Data
            └── Backtesting
```

**Layout:** pagina singola con scroll verticale. Un solo tab visibile alla volta, gli altri nascosti (`display:none`). La nav è `position:fixed` e usa `backdrop-filter:blur` per rimanere leggibile durante lo scroll.

**Larghezza panel:** 980px max, centrato, padding 20px laterale.

**Non è un wizard:** tutti i tab sono sempre cliccabili, indipendentemente dallo stato degli altri.

---

## Nav — Barra di navigazione

```
SCL · Signal Chain Lab  |  01 Download  |  02 Parse  |  03 Market Data & Backtest
```

| Elemento | Tipo | Comportamento |
|---|---|---|
| **Brand** (`SCL · Signal Chain Lab`) | Label monospace | Non cliccabile. `SCL` in muted, `·` in accent, resto in muted. |
| **01 Download** | Tab button | Mostra `panel-download`, nasconde gli altri. Font monospace 11px. Il numero (`01`) è in overlay opacizzato. |
| **02 Parse** | Tab button | Mostra `panel-parse`. |
| **03 Market Data & Backtest** | Tab button | Mostra `panel-mktbt`. |

**Tab attivo:** bordo inferiore 2px `--accent`, testo `--accent`. **Tab inattivo:** testo `--muted`, hover → `--text2`.

---

## Tab 01 — Download

**Card unica** con titolo `01 · Download dati Telegram`.

### Sezione: Sessione Telegram

Mostra lo stato dell'autenticazione Telethon. Dati letti al caricamento.

| Elemento | Stato / Dato | Sorgente |
|---|---|---|
| **Badge sessione** `● Sessione attiva · parser_test/parser_test.session` | Verde (`sb-ok`) se il file `.session` esiste, ambra (`sb-no`) se assente | Filesystem: `parser_test/parser_test.session` |
| **Bottone "🔑 Modifica credenziali"** | Ghost button | Apre/chiude il pannello collassabile credenziali |

**Pannello credenziali (collassabile `.adv`):** titolo "Credenziali / OTP", chiuso di default se sessione attiva, aperto se sessione assente.

| Campo | Tipo | Dato |
|---|---|---|
| **API_ID** | Input monospace | Numero intero da https://my.telegram.org |
| **API_HASH** | Input password (oscurato) | Stringa hex 32 caratteri dallo stesso URL |
| **Telefono** | Input | Numero con prefisso internazionale (es. `+39...`) |
| **Codice OTP** | Input (nascosto finché non si clicca "Invia OTP") | 6 cifre ricevute via SMS/app Telegram |
| **✓ Conferma OTP** | Bottone primario small | Visibile solo dopo invio OTP |
| **📨 Invia OTP** | Bottone secondary small | Chiede il codice a Telegram e mostra la riga OTP |
| **✕ Azzera sessione** | Bottone danger small | Elimina `.session` e cancella credenziali dal `.env` |

### Sezione: Sorgente

| Campo | Tipo | Dato | Note |
|---|---|---|---|
| **Chat ID** | Input monospace | Es. `-1003722628653` (supergroup) o `@username` | Numero negativo per supergroup Telegram |
| **Topic ID** | Input monospace | Es. `8` (opzionale) | Numero del thread/topic nel supergroup |
| **ID sorgente** (chip read-only) | Path chip | Composto live: `chat_id/topic_id` oppure solo `chat_id` | Aggiornato in tempo reale al cambio degli input |

### Sezione: Periodo download

| Elemento | Tipo | Comportamento |
|---|---|---|
| **Scarica tutto lo storico** | Toggle | Se ON, nasconde la riga date (`#date-range`). Se OFF, mostra Dal/Al. |
| **Dal** | Input date (nativo) | Formato `YYYY-MM-DD`, color-scheme dark |
| **Al** | Input date (nativo) | Formato `YYYY-MM-DD` |
| **Contenuto** | Radio group | `Solo testo` / `Testo + immagini` — radio con stile pill, quello attivo ha bordo accent e bg accent-d |

### Sezione: Output

| Campo | Tipo | Default | Nota |
|---|---|---|---|
| **Cartella output DB** | Input monospace | `parser_test/db` | Path dove verrà salvato il file `.sqlite3` |
| **📁 Sfoglia** | Bottone secondary small | — | Apre dialog filesystem |

**Nome file generato automaticamente:** `parser_test__chat_<chat_id>[__topic_<topic_id>].sqlite3`. I caratteri non alfanumerici nel chat_id o topic_id vengono sostituiti da `_`.

### Sezione: Risultato download

Appare dopo download completato. Legge il DB appena creato e conta le righe.

| Card | Metrica | Sorgente dati |
|---|---|---|
| **Messaggi** (verde) | Totale righe in `raw_messages` | `SELECT COUNT(*) FROM raw_messages` |
| **Con media** | Righe con `has_media = 1` | `WHERE COALESCE(has_media,0) = 1` |
| **Image blob** | Righe con blob immagine salvato | `WHERE media_blob IS NOT NULL AND media_mime_type LIKE 'image/%'` |
| **DB size** | Dimensione file `.sqlite3` su disco | Filesystem |

Sotto la grid: chip monospace con il path completo del DB generato.

### Azioni

| Bottone | Tipo | Comportamento |
|---|---|---|
| **▶ Esegui Download** | Primary | Lancia `parser_test/scripts/import_history.py` in streaming. Apre il log. |
| **■ Arresta** | Secondary + danger outline | Invia `SIGTERM` al processo subprocess in corso |
| **✓ Usa come DB attivo** | Secondary small | Imposta il DB scaricato come sorgente per Parse e Backtest (`state.downloaded_db_path`) |
| **✕ Elimina DB** | Danger small | Cancella il file `.sqlite3` dal filesystem (`Path.unlink()`) |

### Log Download

```
$ [cmd] python3 parser_test/scripts/import_history.py --chat-id … --session … --db-path …
```

- Header: `$` in verde scuro, titolo "Log Download", badge exit (verde `✓ exit 0` o ambra con warning count)
- Body: `height: 176px`, `display:none` di default (collassato), `background: #010409`
- Colori righe: verde terminale `#39d353` standard, blu chiaro per il comando, verde scuro per progress, ambra per warning, rosso per errori
- Chevron `▸` → `▾` al toggle

---

## Tab 02 — Parse

**Card unica** con titolo `02 · Parse — Signal chain reconstruction`.

### Sezione: Database sorgente

| Campo | Tipo | Default | Nota |
|---|---|---|---|
| **File DB (.sqlite3)** | Input monospace | `state.effective_db_path()` — preferisce `parsed_db_path`, poi `downloaded_db_path` | Editabile manualmente o via Sfoglia |
| **📁 Sfoglia** | Bottone secondary small | — | Dialog filesystem per file `.sqlite3`/`.db` |

Sotto il campo: chip path con nome file e conteggio messaggi (es. `parser_test__chat_... · 4.281 messaggi`).

### Configurazione

| Campo | Tipo | Opzioni | Nota |
|---|---|---|---|
| **Trader profile** | Select | `Auto` (vuoto), `trader_3`, `trader_a`, `trader_b`, `trader_c`, `trader_d` | Vuoto = detection automatica dal contenuto dei messaggi |
| **Esporta CSV** | Toggle | ON/OFF | Se ON, genera CSV in `parser_test/reports/` dopo il parse |

### Sezione: Stato modulo

Tre stat card post-parse, lette dal DB e dall'esecuzione in-process:

| Card | Stato pill | Dati mostrati |
|---|---|---|
| **Parse** | `✓ ok` (verde) / `✗ error` (rosso) | Totale messaggi processati, segnali estratti |
| **Chain Builder** | `✓ ok` / `⚠ warning` / `✗ error` | Segnali `operational`, `incomplete` |
| **Backtest Readiness** | `✓ ok` / `⚠ warning` | Chain pronti per backtest, warning attivi |

**Backtest Readiness** è derivato da: `operational_new_signal_rows > 0 AND len(chains) > 0`. Se FALSE, il run del backtest è protetto (warning + notifica), anche se non blocca fisicamente il tab.

### Sezione: Top warnings

Tabella compatta (max 5 righe) con le anomalie più frequenti rilevate durante il parse:

| Colonna | Sorgente |
|---|---|
| **Tipo** | Chiave warning (es. `missing_sl`, `ambiguous_entry`, `unresolved_update`) |
| **Count** | Occorrenze in `parse_results.warning_text` + chain validation gaps |
| **Esempio** | Prima occorrenza — `msg_id` e descrizione |

I conteggi sono uniti da due counter: quello del parser (`parse_results.warning_text`) e quello del chain validator (`validation.warning_gaps + validation.fatal_gaps`).

### Azioni

| Bottone | Tipo | Comportamento |
|---|---|---|
| **▶ Esegui Parse** | Primary | Lancia 3 fasi in sequenza: `replay_parser.py` → `replay_operation_rules.py` → `_build_quality_report()` in-process |
| **■ Arresta** | Secondary + danger | Interrompe il subprocess corrente |
| **📊 Apri report qualità** | Secondary small | Apre l'artefatto HTML del quality report |
| **📥 Esporta CSV** | Secondary small | Lancia `export_reports_csv_v2()` sul DB corrente |

### Log Parse

Struttura identica al log Download. Header mostra warning count (es. `⚠ 75 warnings`).

```
$ python3 -m src.signal_chain_lab.parser.runner --profile trader_3 ...
[HH:MM:SS] Carico profilo trader_3 · 48 regole
[HH:MM:SS] Processando 3814 messaggi...
[HH:MM:SS] WARN: missing_sl @ msg_id 1823        ← ambra
[HH:MM:SS] Chain builder: 467 → 423 operational
[HH:MM:SS] ⚠ Completato con 75 warnings          ← ambra
```

---

## Tab 03 — Market Data & Backtest

Questo tab ha una struttura a due livelli:

1. **Contesto condiviso** (collassabile) — in cima, sempre visibile
2. **Card con sub-tab** — Market Data | Backtesting

---

### Contesto condiviso (collassabile)

Sezione `.shared-coll`, aperta di default (`class="shared-coll open"`).

**Header:** `▶ Contesto condiviso` con sottotitolo inline `DB · filtri · cartella Market Data`. Quando collassato, mostra una riga summary inline:

```
🗄 chat_3722628653.sqlite3  ·  Tutti · 2024-01-01→2024-12-31  ·  📂 market_data/bybit
```

**Quando aperto:** mostra 3 sottosezioni:

#### Database segnali

| Campo | Tipo | Default |
|---|---|---|
| **File DB** | Input monospace | `state.effective_db_path()` — stesso DB del Parse, editabile |
| **📁 Sfoglia** | Bottone secondary small | Dialog filesystem |

#### Filtri

| Campo | Tipo | Default | Nota |
|---|---|---|---|
| **Trader filter** | Select | `Tutti` / `trader_3` / `trader_a` / `trader_b` / … | Filtra i segnali inclusi nel run. Opzioni scoperte dal DB  in automatico, nel momento della selezione del bd. |
| **Dal** | Input date | Vuoto | Filtro data inizio backtest. Indipendente dal filtro Download. |
| **Al** | Input date | Vuoto | Filtro data fine backtest. |
| **Max trades** | Input number | `0` | 0 = nessun limite. Limita i segnali inclusi nel backtest. |

> ⚠ Questi filtri sono **indipendenti** da quelli del Download. Il Download filtra i messaggi scaricati da Telegram; questi filtri determinano quali trade vengono inclusi nel calcolo.

#### Cartella Market Data

| Campo | Tipo | Default |
|---|---|---|
| **Path cartella** | Input monospace | `data/market` |
| **📁 Sfoglia** | Bottone secondary small | Dialog filesystem |

Sotto il campo: chip path (`📂 data/market/bybit`) + notice info con il contenuto rilevato nella cartella (es. `Spot · Perp · Funding · bybit · 1h,4h,1d · last,mark`).

---

### Sub-tab: Market Data

#### Riga configurazione base

| Campo | Tipo | Opzioni | Nota |
|---|---|---|---|
| **Source / Provider** | Select | `bybit` / `fixture` | `bybit` = API Bybit live; `fixture` = file locali per test |
| **Validate mode** | Select | `Full` / `Light` / `Off` | Controlla la profondità di validazione della cache OHLCV |
| **Price basis** | Select | `last` / `mark` | `last` = prezzo last standard; `mark` = mark price (rilevante per futures/derivati) |

**Validate mode — dettaglio:**
- `Gaps` — esegue planner + sync + gap validation (fasi 1-3), salta il validate full.
- `Off` — nessuna validazione. Usa la cache esistente così com'è.

#### Download TF (multi-select)

Multi-select custom (`.ms-wrap`). Seleziona i timeframe da scaricare/mantenere nella cache.

| Opzioni | Default selezionati |
|---|---|
| 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w | `1h`, `4h`, `1d` |

Il trigger mostra i valori selezionati compattati (es. `1h, 4h, 1d`). Dropdown con scroll, max-height 260px.

#### Data types (multi-select)

Multi-select per i tipi di dati da scaricare/mantenere.

| Opzione | Stato |
|---|---|
| Perpetual (Perp) | Selezionabile ✓ |
| Funding rate | Selezionabile ✓ |
| Spot| Disabilitato — badge `ROADMAP` |
| Open interest | Disabilitato — badge `ROADMAP` |
| Liquidations | Disabilitato — badge `ROADMAP` |
| Order book | Disabilitato — badge `ROADMAP` |
| Bid/ask spread | Disabilitato — badge `ROADMAP` |

Default selezionati: `Spot, Perpetual, Funding rate`.

#### Buffer mode

| Campo | Tipo | Comportamento |
|---|---|---|
| **Buffer mode** | Select: `auto` / `manual` | Se `manual`, appaiono due campi aggiuntivi |
| **Pre buffer (h)** | Input number, default `48` | Visibile solo se `manual`. Ore di dati prima del segnale. |
| **Post buffer (h)** | Input number, default `24` | Visibile solo se `manual`. Ore di dati dopo il segnale. |

In modalità `auto` i buffer vengono calcolati automaticamente dalla pipeline in base ai segnali presenti.

#### Nuova directory (toggle)

Toggle `Nuova directory (scarica in nuova cartella)`. Se ON, appare un campo path + Sfoglia per specificare la cartella di destinazione della nuova cache. Se OFF (default), la pipeline lavora sulla cartella Market Data del contesto condiviso.

#### Sezione: Coverage

Quattro card numeriche mostrate dopo l'analisi (Analizza / Prepara):

| Card | Valore | Colore |
|---|---|---|
| **Simboli** | Numero simboli trovati nel DB per il periodo | Default |
| **Intervalli req.** | Intervalli temporali necessari calcolati dal planner | Default |
| **Gap** | Intervalli mancanti nella cache locale | Ambra se > 0 |
| **Copertura %** | Percentuale cache disponibile sul totale richiesto | Default |

Sorgente: `artifacts/market_data/plan_market_data.json` — campo `summary.symbols`, `summary.required_intervals`, `summary.gaps`.

#### Azioni Market Data

| Bottone | Comportamento |
|---|---|
| **🔍 Analizza** | Esegue solo il Planner (fase 1). Aggiorna la sezione Coverage. Non scarica nulla. |
| **⬇ Prepara** | Esegue Planner + Sync + [Gap Validate (fase 3 in base alle impostazioni Gap/Off)]. Non valida. |
| **✓ Valida** | Esegue la Validate full (fase 4). Richiede che Prepara sia già stato eseguito. ||
| **■ Arresta** | Interrompe il processo corrente |

#### Log Market Data

```
$ python3 -m src.signal_chain_lab.market_data.runner --source bybit --validate Full ...
[HH:MM:SS] Carico configurazione...
[HH:MM:SS] Analisi: 37 simboli, 148 intervalli
[HH:MM:SS] Gap rilevati: 12                       ← ambra
[HH:MM:SS] Avvio sync gap...
[HH:MM:SS] ✓ Market data pronti                   ← verde
```

---

### Sub-tab: Backtesting

#### Notice informativa

Box blu in cima: `ℹ Price basis e Market source sono rilevati automaticamente dalla cartella Market Data.` Ricorda all'operatore che quei due parametri non vanno inseriti manualmente nel backtest.

#### Riga 1 — Configurazione principale

| Campo | Tipo | Default | Nota |
|---|---|---|---|
| **Policy** | Multi-select (`.ms-wrap`) | `original_chain, signal_only` | Lista scoperta dinamicamente da `configs/policies/`. 1 policy → single run; 2+ → scenario comparison. |
| **Timeout (s)** | Input number | `60` | Limite temporale del subprocess backtest. Superato → notifica di errore. |
| **Report output dir** | Input monospace | `artifacts/scenarios` | Cartella dove vengono salvati HTML e JSON del run. |
| **📁** | Ghost button | — | Sfoglia per la cartella report |

#### Riga 2 — Parametri simulazione

| Campo | Tipo | Default | Nota |
|---|---|---|---|
| **Simulation TF** | Select | `1m` | Timeframe principale della simulazione (risoluzione dei tick). |
| **Detail TF / childs** | Select | `1m` | Timeframe di dettaglio per analisi interne. |
| **Price basis** | Select | `last · rilevato` | Read-mostly — rilevato dalla cartella Market Data. Modificabile manualmente. |
| **Market source** | Select | `bybit · rilevato` | Read-mostly — rilevato dalla cartella Market Data. Modificabile manualmente. |

I campi "rilevati" mostrano il badge `· auto da market dir` in accent color accanto alla label, per segnalare che il valore è stato inferito automaticamente.

#### Policy Studio (collassabile)

Sezione `.adv` collassabile con header `Policy Studio — editor YAML · Modifica · Nuova`.

**Quando aperto:**
- Area YAML con syntax highlight minimale (chiavi in rosso-arancio, valori in blu chiaro, commenti in muted)
- Mostra il YAML della prima policy selezionata nel multi-select

| Azione | Comportamento |
|---|---|
| **💾 Salva** | Sovrascrive il file YAML con il contenuto dell'editor |
| **Salva come nuova...** | Apre dialog con campo nome (validazione `[a-z][a-z0-9_-]*`), salva come nuovo file |
| **+ Nuova policy** | Apre editor vuoto con template dalla prima policy esistente |
| **↺ Ricarica lista** | Rilegge `configs/policies/` e aggiorna il multi-select |

#### Azioni Backtest

| Bottone | Tipo | Comportamento |
|---|---|---|
| **▶ Esegui Backtest** | Primary | Avvia il run. Se la cache market data non è pronta, esegue prima Prepara+Valida automaticamente. |
| **■ Arresta** | Secondary + danger | Interrompe il subprocess |
| **📄 Apri report HTML** | Secondary small, `disabled` fino al completamento | Apre il file HTML con URI `file://` nel browser |
| **📂 Artifact dir** | Secondary small, `disabled` fino al completamento | Apre la cartella degli artifact |

#### Sezione: Risultati

**Prima di un run:** placeholder vuoto `— nessun run eseguito —`.

**Dopo run completato:** tabella risultati:

| Colonna | Sorgente | Nota |
|---|---|---|
| **Policy** | Nome della policy eseguita | Da `state.backtest_policies` |
| **Trades** | Numero trade simulati | Parsato dal log: `trades=N` |
| **Excluded** | Trade esclusi dalla simulazione | Parsato dal log: `excluded=N` |
| **PnL %** | Rendimento percentuale | Parsato dal log: `pnl=N`. Verde se positivo, rosso se negativo. |
| **Win rate** | Percentuale trade vincenti | Parsato dal log: `win_rate=N%` |
| **Expectancy** | R-multiplo medio per trade | Parsato dal log: `expectancy=N`. Verde se > 0. |
| **Report** | Link `📄 apri` | Apre il report HTML singolo per quella policy |

Il log viene parsato con regex:
```
- <policy>: pnl=<float>, win_rate=<float>%, expectancy=<float>, trades=<int>, excluded=<int>
```

**Azioni post-run:**
- `btn-rpt` e `btn-art` si abilitano automaticamente al completamento del run
- La tabella risultati appare (`#bt-results`) e il placeholder scompare (`#bt-empty`)

#### Log Backtest

```
$ python3 -m src.signal_chain_lab.backtest.runner --policies original_chain signal_only ...
[HH:MM:SS] Carico policy: original_chain, signal_only
[HH:MM:SS] 423 segnali operativi
[HH:MM:SS] Simulazione in corso...
[HH:MM:SS] 312 trades simulati · 23 esclusi
[HH:MM:SS] ✓ Backtest completato                  ← verde
[HH:MM:SS] Report: artifacts/scenarios/scenario_20241210.html
```

---

## Sistema interattivo — comportamenti JS

### Cambio tab

```js
switchTab(id, btn)
// Nasconde tutti i .panel, mostra #panel-{id}
// Rimuove .on da tutti i .tab-btn, aggiunge .on al btn cliccato
// Chiude tutti i .ms-wrap.open (multi-select aperti)
```

### Cambio sub-tab (interno al Tab 03)

```js
switchSub(id, btn)
// Nasconde tutti i .sub-panel, mostra #sub-{id}
// Rimuove/aggiunge .on sui .sub-btn
```

### Contesto condiviso toggle

```js
toggleShared()
// Toggle .open su #ctx-shared
// Mostra/nasconde #ctx-summary (riga summary compatta nell'header)
```

### Log toggle

```js
toggleLog(head)
// Toggle class .h sul .log-body (display:none)
// Cambia chevron ▸ / ▾
```

### Collapsible (.adv)

```js
toggleAdv(id)
// Toggle .open sull'elemento — CSS gestisce display dell'adv-body e rotazione dell'adv-ico
```

### Toggle visibilità elemento

```js
toggleEl(id, show)
// Setta display del #id: '' (visibile) o 'none'
// Usato da: full_history toggle → nasconde #date-range
//           tog-newdir → mostra #newdir-field
```

### Buffer mode condizionale

```js
toggleBuf()
// Legge value di #buf-mode
// Se 'manual': mostra #pre-buf e #post-buf
// Altrimenti: nasconde entrambi
```

### Multi-select

```js
toggleMs(id)   // Toggle .open sul .ms-wrap — un solo aperto alla volta
msT(item, wid) // Toggle .checked sull'item, aggiorna la label del trigger
updateMsVal(wid) // Rilegge tutti i .checked e scrive il testo nel .mv
```

**Chiusura automatica:** click fuori da qualsiasi `.ms-wrap` chiude tutti i dropdown (listener su `document`).

### Simulazione log (mockup only)

```js
simLog(logId, key)  // Scrive righe pre-definite con delay 600ms
stopLog(logId)      // Cancella i timer, scrive riga "■ Esecuzione arrestata"
simBt()             // Log backtest + abilita btn-rpt/btn-art + mostra #bt-results
```

---

## Mappa dati — da dove vengono i valori

| Campo UI | Sorgente dati | Quando viene popolato |
|---|---|---|
| Badge sessione Telegram | Filesystem: `parser_test/parser_test.session` | Al caricamento della pagina |
| Chip path DB (Download) | `state.downloaded_db_path` | Dopo download completato |
| Chip info DB (Parse) | Query su `raw_messages`: `COUNT(*)` | Al caricamento del DB nel campo |
| Stat cards Parse | `parse_results`, `signals`, `operational_signals` | Dopo parse completato (in-process) |
| Top warnings | `parse_results.warning_text` + chain validator | Dopo parse completato |
| Coverage (Market Data) | `artifacts/market_data/plan_market_data.json` → `summary` | Dopo "Analizza" o "Prepara" |
| Trader filter (Tab 03) | Query sul DB: `DISTINCT trader_id FROM operational_signals` | Al click "Rileva" o auto-popolato |
| Date Dal/Al (Tab 03) | Query sul DB: `MIN/MAX(date)` | Auto-popolate al cambio DB |
| Policy list | Filesystem: `configs/policies/*.yaml` | `discover_policy_names()` al caricamento / "Ricarica" |
| Results table | Parsing del log con regex | Al completamento del run backtest |
| Path chip Market Data | `state.market_data_dir` | Valore inserito nel campo |
| Notice contenuto rilevato | Scan della cartella `data/market/` | Dopo selezione/conferma della cartella |

---

## Artefatti prodotti

| Artefatto | Path | Prodotto da | Contenuto |
|---|---|---|---|
| DB messaggi grezzi | `parser_test/db/parser_test__chat_<id>.sqlite3` | Tab 01 — Download | Tabella `raw_messages` |
| DB parsato | stesso file | Tab 02 — Parse | `parse_results`, `signals`, `operational_signals` |
| Planner plan | `artifacts/market_data/plan_market_data.json` | Analizza / Prepara | Simboli e intervalli necessari |
| Sync report | `artifacts/market_data/sync_market_data.json` | Prepara (se gap > 0) | Gap sincronizzati |
| Gap validate | `artifacts/market_data/gap_validate_market_data.json` | Prepara (se gap > 0) | Verifica gap sincronizzati |
| Validate report | `artifacts/market_data/validate_market_data.json` | Prepara + Valida / SAFE | Consistenza cache completa |
| Validation index | `artifacts/market_data/validation_index.json` | Fine Prepara+Valida | Cache fingerprint → PASS/FAIL |
| Policy report | `artifacts/policy_reports/<policy>/` | Backtest 1 policy | HTML + JSON per una policy |
| Scenario report | `artifacts/scenarios/<nome>/` | Backtest 2+ policy | HTML comparativo tra policy |
| Benchmark log | `artifacts/market_data/backtest_benchmark.json` | Fine ogni backtest | Storico timing di tutti i run |
| CSV report | `parser_test/reports/*.csv` | Tab 02 — Parse (opz.) | Dati parse in formato tabellare |

---

## Nota: Validate mode vs Prepare mode

Il mockup mostra **due controlli distinti**:

| Controllo | Dove | Opzioni | Funzione |
|---|---|---|---|
| **Validate mode** | Sub-tab Market Data | Full / Light / Off | Profondità di validazione della cache OHLCV |
| **Prepare mode** | Sub-tab Market Data | SAFE / FAST | Pipeline di preparazione (include o esclude il validate full) |

Nel codice attuale (`block_backtest.py`), esiste solo `prepare_mode` con valori `SAFE`/`FAST`. Il campo `Validate mode: Full/Light/Off` è una **funzionalità pianificata** non ancora implementata come campo separato. Attualmente la logica è: `SAFE` ≈ validate `Full`, `FAST` ≈ validate `Light/Off`.

---

*Versione: 2.0 — basato su ui_mockup.html v4 — generato il 2026-04-19*
