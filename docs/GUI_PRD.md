# GUI 

## 1. Funzionamento vsluto della GUI

### Struttura e avvio

La GUI è basata su NiceGUI, si avvia con:

```bash
python -m src.signal_chain_lab.ui.app
# oppure
python src/signal_chain_lab/ui/app.py
# porta: localhost:7777
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
### Blocco 2 — Parse (tab "2. Parse")

**Cosa fa:**

1. Input DB sorgente (pre-popolato con `state.effective_db_path()`) + "Sfoglia"
3. Select trader filtro: Auto | trader_a | trader_b | trader_c | trader_d | trader_3
4. Campo date range / limit per il parse
5. Input trader mapping (default `configs/telegram_source_map.json`)
6. Checkbox "Genera CSV report a fine parse"
7. Input cartella CSV report + "Sfoglia"
8. Pulsante "Esegui Parse + Chain Builder"
9. Al completamento: genera un link che mi apre il folder con report generate




**Quality Report mostrato:**

| Metrica | Descrizione |
|---------|-------------|
| Messaggi totali | count da `parse_results` |
| NEW_SIGNAL (tot / completi / incompleti) | da `parse_results.message_type + completeness` |
| UPDATE (tot / orfani) | orfano = "unresolved update target" in warning_text |
| INFO_ONLY, UNCLASSIFIED | da `parse_results.message_type` |
| Chain simulabili / non simulabili | da `validate_chain_for_simulation()` |
| Top 5 warnings | union di warning chain + warning parse, most_common(5) |



---

### Blocco 3 — Backtest (tab "3. Backtest dedicato a solo Backtesing")

**Cosa fa:**

1. Input DB parsato + "Sfoglia" (con validazione live: etichetta "DB valido" / "DB non trovato")
2. Select policy: `original_chain` | `signal_only`
3. Input cartella market data + "Sfoglia"
4. Se la cartella e selezionata deve e 
5. Input timeframe + numero timeout (secondi)
6. Pulsante "Esegui Backtest" (disabilitato finché DB non trovato o parse non completato)
7. Al completamento: genera il report secondo il PRD_REPORT.md
8. Al completamento: genera un link che mi apre il folder con report generate

da fare:

1. Aggiungere menu a tendina che mi permette sciegliere le policy per simulatore da cartella "C:\Back_Testing\configs\policies"
2. Aggiungere la posibilita configurazione di modifica della polici slezionata, con posibilita di salvarlo, o creare uno nuovo in un popup.
3. Verfica automatica di del db slezionato per Multitraider e deve permette di selezionare qual trader usare per backtesting o tutti.
4. Aggiungere date range (Dal / Al) per trade da becktestare
5. Aggiungere la limitazione de numero di trade da bektesting
7. Posibilta di configurare il report:
   a. Dove Salvarlo (indicare la cartella) lasciare di defauilt una cartella interna del progetto.
8. Unavolta termninato il baktesting deve comparire il link che apre il report HTML

### Blocco 4 — Ottimizazione - da definire inseguito




