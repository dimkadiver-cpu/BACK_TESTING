# GUI — Stato Attuale vs PRD
**Versione:** 1.0  
**Data:** 2026-04-07  
**Riferimento PRD:** `PRD_consolidato_signal_chain_lab.md` §4.14, §4.15, §4.16, §4.18

---

## 1. Funzionamento attuale della GUI

### Struttura e avvio

La GUI è basata su NiceGUI, si avvia con:

```bash
python -m src.signal_chain_lab.ui.app
# oppure
python src/signal_chain_lab/ui/app.py
# porta: localhost:7777
```

`app.py` (59 righe) è un puro orchestratore: crea lo stato condiviso `UiState`, definisce il comando di streaming asincrono (`_run_streaming_command`), e renderizza i 3 tab chiamando i moduli `block_*.py`.

### Architettura moduli

```
src/signal_chain_lab/ui/
├── app.py                   ← entry point, orchestratore
├── blocks/
│   ├── block_download.py    ← tab 1: download Telegram
│   ├── block_parse.py       ← tab 2: parse + quality report
│   └── block_backtest.py    ← tab 3: scenario backtest
├── components/
│   ├── log_panel.py         ← pannello log riusabile (dark terminal)
│   └── quality_report.py    ← card metriche sintetiche parse
└── state.py                 ← UiState dataclass condivisa
```

### Stato condiviso (UiState)

`UiState` è un dataclass passato per riferimento a tutti e 3 i blocchi. Campi chiave:

| Campo | Default | Usato da |
|-------|---------|----------|
| `source_kind` | `"telegram"` | block_parse (skip replay se `"existing_db"`) |
| `chat_id`, `topic_id` | `""` | block_download |
| `date_from`, `date_to` | `""` | block_download |
| `full_history` | `True` | block_download |
| `download_media` | `False` | block_download |
| `downloaded_db_path` | `""` | block_download → block_parse |
| `parsed_db_path` | `""` | block_parse → block_backtest |
| `parser_profile` | `""` | block_parse |
| `trader_mapping_path` | `"configs/telegram_source_map.json"` | block_parse |
| `generate_parse_csv` | `False` | block_parse |
| `parse_reports_dir` | `"parser_test/reports"` | block_parse |
| `proceed_to_backtest` | `False` | block_parse → block_backtest |
| `policy_name` | `"original_chain"` | block_backtest |
| `market_data_dir` | `"data/market"` | block_backtest |
| `timeframe` | `"M1"` | block_backtest |
| `timeout_seconds` | `60` | block_backtest |
| `latest_artifact_path` | `""` | block_backtest |

`effective_db_path()` restituisce `parsed_db_path or downloaded_db_path`.

---

### Blocco 1 — Download (tab "1. Download")

**Cosa fa:**

1. Carica credenziali salvate da `parser_test/.env` (API_ID, API_HASH)
2. Mostra stato sessione Telethon (`parser_test/parser_test.session`)
3. Sezione espandibile "Credenziali / Autenticazione":
   - Input API_ID, API_HASH, numero telefono
   - Flusso OTP: "Invia OTP" → inserisci codice → "Conferma OTP"
   - Supporto 2FA: avvisa ma non gestisce (rimanda al terminale)
   - "Azzera sessione e credenziali": cancella `.session` e `.env`
4. Form download:
   - Chat ID, Topic ID opzionale (label "ID sorgente" aggiornata live)
   - Toggle "Scarica tutto lo storico" / date range (Dal / Al)
   - Radio "Solo testo" | "Testo + immagini"
   - Campo cartella output + "Sfoglia" (tkinter filedialog)
5. Pulsanti: "Esegui Download" / "Arresta Download" / "Elimina DB scaricato"
6. Al completamento: popola `state.downloaded_db_path`, mostra summary DB (conteggio messaggi, media, foto, blob)

**Comandi lanciati:**

```bash
python parser_test/scripts/import_history.py \
  --chat-id <chat_id> \
  --session parser_test/parser_test \
  --db-path parser_test/db/parser_test__chat_<chat>.sqlite3 \
  [--topic-id <topic>] [--from-date <date>] [--to-date <date>] [--download-media]
```

**Limitazioni attuali:**
- La sorgente è sempre Telegram — non esiste UI per selezionare "DB esistente" o dataset esportato
- `source_kind` è hardcoded a `"telegram"` in `_handle_download`; l'unico modo per usare `"existing_db"` è impostarlo manualmente nel codice o tramite un DB caricato direttamente nel Blocco 2

---

### Blocco 2 — Parse (tab "2. Parse")

**Cosa fa:**

1. Input DB sorgente (pre-popolato con `state.effective_db_path()`) + "Sfoglia"
2. Select trader filtro: Auto | trader_a | trader_b | trader_c | trader_d | trader_3
3. Input trader mapping (default `configs/telegram_source_map.json`)
4. Checkbox "Genera CSV report a fine parse"
5. Input cartella CSV report + "Sfoglia"
6. Pulsante "Esegui Parse + Chain Builder"

**Flusso esecuzione:**
- Se `source_kind == "existing_db"`: salta `replay_parser.py`, va diretto al chain builder
- Altrimenti: lancia `replay_parser.py` in streaming
- Se "Genera CSV": chiama `export_reports_csv_v2()` in thread separato
- Costruisce `QualityReport` via `SignalChainBuilder` + `validate_chain_for_simulation`
- Abilita il pulsante Backtest nel Blocco 3 tramite `backtest_button_holder[0].enable()`

**Quality Report mostrato:**

| Metrica | Descrizione |
|---------|-------------|
| Messaggi totali | count da `parse_results` |
| NEW_SIGNAL (tot / completi / incompleti) | da `parse_results.message_type + completeness` |
| UPDATE (tot / orfani) | orfano = "unresolved update target" in warning_text |
| INFO_ONLY, UNCLASSIFIED | da `parse_results.message_type` |
| Chain simulabili / non simulabili | da `validate_chain_for_simulation()` |
| Top 5 warnings | union di warning chain + warning parse, most_common(5) |

**Limitazioni attuali:**
- Nessun campo date range / limit per il parse (il PRD lo prevede)
- Il pulsante di sblocco Blocco 3 non ha un CTA esplicito ("Procedi al Backtest →") — il blocco si abilita implicitamente dopo il parse
- Non c'è loop iterativo esplicito in UI (l'utente deve tornare manualmente al tab 2 per rieseguire)

---

### Blocco 3 — Backtest (tab "3. Backtest")

**Cosa fa:**

1. Input DB parsato + "Sfoglia" (con validazione live: etichetta "DB valido" / "DB non trovato")
2. Select policy: `original_chain` | `signal_only`
3. Input cartella market data + "Sfoglia"
4. Input timeframe + numero timeout (secondi)
5. Pulsante "Esegui Backtest" (disabilitato finché DB non trovato o parse non completato)

**Flusso esecuzione:**

```bash
python scripts/run_scenario.py \
  --policy <policy>,signal_only \
  --db-path <db_path> \
  --market-dir <market_data_dir>
```

Al completamento: parsing del log per estrarre `chains_selected` e righe summary policy, rendering card risultati (policy / trades / escluse / PnL / win_rate / expectancy).

**Limitazioni attuali:**
- `--market-dir` è passato ma ignorato nel CLI (`_ = Path(args.market_dir)` — Gap G15): nessun market provider istanziato → tutte le chain restano PENDING, PnL=0
- Policy selezionabile solo tra `original_chain` e `signal_only` (nessuna policy custom dalla GUI)
- Nessun date range applicabile al dataset prima del backtest (filtro solo in CLI via `--date-from`/`--date-to`)
- Nessuna visualizzazione artifact (HTML, CSV) con link cliccabile dall'UI

---

## 2. Confronto con il PRD

### §4.14 — Workflow ufficiale a 3 blocchi

| Requisito PRD | Stato | Note |
|---|---|---|
| 3 blocchi sequenziali con checkpoint umano dopo blocco 2 | ✅ | Tab separati, backtest bloccato fino a parse completato |
| Blocco 1 sempre abilitato | ✅ | Tab "Download" sempre accessibile |
| Blocco 2 abilitato quando esiste DB raw | ⚠️ parziale | Il campo DB è pre-popolato ma non c'è controllo che esista prima di eseguire |
| Blocco 3 abilitato dopo conferma esplicita utente | ⚠️ parziale | Si abilita automaticamente dopo parse OK, senza conferma esplicita dell'utente |
| DB persistenti: si può rieseguire qualsiasi blocco | ✅ | I path restano in `UiState`, si può tornare ai tab |
| Loop iterativo Blocco 2 è il caso normale | ✅ strutturalmente | Ma non c'è CTA "Riesegui parse con nuovo profilo" |

### §4.15 — Requisiti acquisizione dati

| Requisito PRD | Stato | Note |
|---|---|---|
| Sorgente: canale Telegram | ✅ | Implementato con auth OTP completo |
| Sorgente: topic di canale Telegram | ✅ | Campo topic-id opzionale |
| Sorgente: chat | ✅ | chat-id generico |
| Sorgente: DB esistente | ❌ | `source_kind="existing_db"` esiste nel codice ma nessun selettore UI nel Blocco 1 |
| Sorgente: dataset esportato | ❌ | Non implementato |
| Supporto 2FA Telegram | ❌ | Avvisa solo, rimanda al terminale |

### §4.16 — Parser management

| Requisito PRD | Stato | Note |
|---|---|---|
| Selezione parser/profilo esistente | ✅ | Dropdown nel Blocco 2 |
| Duplicazione profilo parser | ❌ | Rinviato post-MVP (G10) |
| Modifica vocabolario/alias/regole | ❌ | Rinviato post-MVP (G10) |
| Test rapido parser su testo campione | ❌ | Rinviato post-MVP (G10) |
| Salvataggio configurazione parser | ❌ | Rinviato post-MVP (G10) |

### §4.18 — GUI: struttura file e componenti

| Elemento PRD | Stato | Note |
|---|---|---|
| `app.py` entry point | ✅ | 59 righe, orchestratore puro |
| `block_download.py` | ✅ | Implementato |
| `block_parse.py` | ✅ | Implementato |
| `block_backtest.py` | ✅ | Implementato |
| `log_panel.py` | ✅ | Implementato |
| `quality_report.py` | ✅ | Implementato |
| `preset_manager.py` | ❌ | Previsto dalla struttura PRD, non creato |
| Form impostazioni per blocco | ✅ | |
| Pulsante esecuzione per blocco | ✅ | |
| Log in tempo reale per blocco | ✅ | Streaming asincrono riga per riga |
| Esito sintetico al completamento | ✅ blocco 2 | Quality report; blocco 3 ha solo card PnL sintetica |

### §4.18 — Blocco 1 specifico

| Campo PRD | Stato | Note |
|---|---|---|
| Selezione sorgente: Telegram \| DB esistente | ❌ | Solo Telegram; nessun selettore UI sorgente |
| chat-id | ✅ | |
| topic-id | ✅ | |
| date range | ✅ | Toggle full history / dal-al |
| limit | ❌ | Non implementato (non c'è `--limit` in import_history.py) |
| session | ✅ | Gestita con OTP flow |
| Log: messaggi scaricati, duplicati, path DB | ⚠️ parziale | Mostra path e summary DB ma non esplicita i duplicati |

### §4.18 — Blocco 2 specifico

| Campo PRD | Stato | Note |
|---|---|---|
| Selezione DB sorgente | ✅ | Input + Sfoglia |
| Selezione parser/profilo | ✅ | Select dropdown |
| Trader mapping | ✅ | Input |
| Date range | ❌ | Non implementato nel blocco parse |
| Limit | ❌ | Non implementato |
| Report sintetico N segnali, N simulabili, top warnings | ✅ | Quality report completo |
| Pulsante "Procedi al Backtest →" esplicito | ⚠️ | Il backtest si sblocca automaticamente, senza CTA esplicita separata |

### §4.18 — Blocco 3 specifico

| Campo PRD | Stato | Note |
|---|---|---|
| Selezione DB parsato | ✅ | Input + Sfoglia + validazione live |
| Selezione policy (original / signal_only / custom) | ⚠️ | Solo original_chain e signal_only; nessuna policy custom selezionabile |
| Market data dir | ✅ UI | Il campo esiste ma il valore è ignorato dal CLI (Gap G15) |
| Timeframe | ✅ UI | Campo presente; non ancora usato dal provider |
| Timeout | ✅ | Implementato con `asyncio.wait_for` |

### §4.18 — Cosa la GUI non deve includere (vincoli rispettati)

| Vincolo PRD | Rispettato |
|---|---|
| No report trade dettagliati inline | ✅ |
| No dashboard statistiche | ✅ |
| No confronto visuale avanzato tra policy | ✅ |
| No timeline eventi come vista primaria | ✅ |
| No HTML report embedded | ✅ |

---

## 3. Gap da colmare — riepilogo priorità

### Gap bloccanti (output backtest non reale)

| Gap | Impatto | File | Riferimento |
|---|---|---|---|
| **G15** Market provider non cablato in `run_scenario.py` | Critico — PnL sempre 0 | `scripts/run_scenario.py:58` | Incremento D |

### Gap funzionali GUI non implementati

| Gap | Priorità | Riferimento |
|---|---|---|
| Selettore sorgente Blocco 1: Telegram \| DB esistente | Alta | PRD §4.15, §4.18 |
| Campo `--limit` in download e parse | Media | PRD §4.18 |
| Date range nel Blocco 2 (filter per parse) | Media | PRD §4.18 |
| Policy custom selezionabile nel Blocco 3 | Media | PRD §4.18 |
| Link artifact cliccabili dopo backtest (HTML, CSV) | Bassa | PRD §4.18 |
| CTA esplicita "Procedi al Backtest →" separata | Bassa | PRD §4.14 |
| `preset_manager.py` salva/carica configurazioni | Bassa | PRD §4.18 struttura file |
| Supporto 2FA Telegram in-UI | Bassa | PRD §4.15 |

### Gap rinviati post-MVP (G10)

Parser management completo (§4.16): duplicazione profilo, modifica vocabolario, test su testo campione, salvataggio configurazione.

---

## 4. Note operative

**Avvio GUI:**
```bash
pip install -e ".[gui]"
python -m src.signal_chain_lab.ui.app
# → http://localhost:7777
```

**DB di test disponibile:** `parser_test/db/s9_fixture.sqlite3` (3 chain simulabili: BTCUSDT, ETHUSDT, SOLUSDT, trader_a)

**Comportamento atteso con fixture DB senza market data:**
- Blocco 3 esegue senza errori
- 3 chain selezionate, 0 escluse
- PnL = 0, status = PENDING su tutte (per design — Gap G15)
- 4 artifact generati in `artifacts/scenarios/`
