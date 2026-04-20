# Signal Chain Lab — GUI Redesign Checklist

**Riferimento:** `IMPLEMENTATION_PLAN.md`  
**Data inizio:** 2026-04-19

---

## Fase 1 — Fondamenta

### 1.1 Theming globale (`app.py`)
- [ ] Sostituire `ui.colors()` con palette completa (accent, ok, wa, er, dark)
- [ ] Aggiungere `ui.add_head_html` con import IBM Plex Mono + Sans da Google Fonts
- [ ] Aggiungere CSS variables `:root` complete nel `<style>` iniettato
- [ ] Aggiungere CSS globale: scrollbar custom, focus-visible ring, body font
- [ ] Testare: la pagina carica con sfondo `#0d1117` e font IBM Plex Sans

### 1.2 Nuovo file `persistence.py`
- [ ] Creare `src/signal_chain_lab/ui/persistence.py`
- [ ] Implementare `get_state_path() -> Path` (cross-platform: APPDATA / .config)
- [ ] Implementare `load_ui_state() -> dict` (restituisce `{}` su errore/assenza)
- [ ] Implementare `save_ui_state(data: dict) -> None` (write atomico)
- [ ] Implementare `debounced_save()` con timer 500ms
- [ ] Test: salva + ricarica produce lo stesso dict

### 1.3 Aggiornare `state.py`
- [ ] Aggiungere `validate_mode: str = "Off"` (valori validi: "GAPs", "OFF")
- [ ] Aggiungere `new_dir_enabled: bool = False`
- [ ] Aggiungere `new_dir_path: str = ""`
- [ ] Rinominare buffer da ore a giorni (`pre_buffer_days`, `post_buffer_days`)
- [ ] Aggiungere `data_types_perp: bool = True`
- [ ] Aggiungere `data_types_spot: bool = False`
- [ ] Aggiungere `data_types_funding: bool = True`
- [ ] Aggiungere metodo `to_dict() -> dict`
- [ ] Aggiungere metodo `apply_saved(data: dict) -> None`
- [ ] Aggiungere metodo `validate_paths() -> list[str]`
- [ ] Deprecare/rimuovere `buffer_preset` e `market_data_mode` (existing/new)

---

## Fase 2 — Componenti condivisi

### 2.1 `status_badge.py` (nuovo)
- [ ] Creare `src/signal_chain_lab/ui/components/status_badge.py`
- [ ] Definire enum o costanti per stati: NOT_STARTED/READY/RUNNING/DONE/WARNING/STALE/ERROR
- [ ] Implementare `render_status_badge(status: str, label: str | None = None)`
- [ ] Iniettare CSS per ogni classe badge (colori, border, pulse animation)
- [ ] Test: visualizzare tutti e 7 gli stati e verificare colori

### 2.2 `log_panel.py` — allineamento stile
- [ ] Header log: aggiungere `$` prompt in colore `#238636`
- [ ] Header log: titolo in `var(--mono)` 10px
- [ ] Log body: background `#010409`, testo default `#39d353`
- [ ] Colori classi: `.warn` → `#d29922`, `.err` → `#f85149`, `.dim` → `#238636`
- [ ] Chevron: `▸` chiuso → `▾` aperto
- [ ] Altezza fissa 176px con overflow-y auto
- [ ] Test: aprire log Download e verificare stile

### 2.3 CSS globale form elements
- [ ] Aggiungere `.inp-mono` class per input monospace
- [ ] Aggiungere `.sec-lbl` per titoli sezione UPPERCASE
- [ ] Aggiungere `.path-chip` per chip path monospace
- [ ] Aggiungere `.notice.n-info` e `.notice.n-warn` per notice banner
- [ ] Aggiungere `.wc` per badge count warning nelle tabelle

---

## Fase 3 — Tab 1: Download

### Allineamento visivo `block_download.py`
- [ ] Titolo card: `"01 · Download dati Telegram"` (numero muted monospace)
- [ ] Sessione: chip `sb-ok` verde con `●` quando attiva, `sb-no` giallo quando inattiva
- [ ] Bottone credenziali: ghost `"🔑 Modifica credenziali"`
- [ ] Pannello credenziali: dentro collapsible `.adv` (chiuso di default)
- [ ] Chat ID: input con font monospace
- [ ] Topic ID: input con font monospace
- [ ] Chip sorgente: `path-chip` con valore `chat_id/topic_id`
- [ ] Toggle "Scarica tutto lo storico": nasconde date range quando ON
- [ ] Contenuto: radio-group stilizzati (Solo testo / Testo + immagini)
- [ ] Risultato download: `sum-grid` 4 card (Messaggi / Con media / Image blob / DB size)
- [ ] Path DB creato: `path-chip` con icona `🗄`
- [ ] Bottone primario: `"▶ Esegui Download"`
- [ ] Bottone stop: `"■ Arresta"` (secondary+danger)
- [ ] Bottone usa come attivo: `"✓ Usa come DB attivo"` (secondary small)
- [ ] Bottone elimina: `"✕ Elimina DB"` (danger small)
- [ ] Log panel: stile aggiornato (fase 2.2)

---

## Fase 4 — Tab 2: Parse

### Allineamento visivo `block_parse.py`
- [ ] Titolo card: `"02 · Parse — Signal chain reconstruction"`
- [ ] DB sorgente: path-chip con conteggio messaggi sotto l'input
- [ ] Trader profile + toggle Esporta CSV: stessa riga, toggle a destra
- [ ] Status cards: griglia `st-cards` 3 colonne (Parse / Chain Builder / Backtest Readiness)
- [ ] Ogni status card: titolo UPPERCASE 9px + pill `sp-ok`/`sp-wa`/`sp-no` + detail 10px mono
- [ ] Top warnings: tabella con colonne Tipo / Count / Esempio
- [ ] Count: badge `wc` arancione
- [ ] Bottone primario: `"▶ Esegui Parse"`
- [ ] Bottone stop: `"■ Arresta"` (secondary+danger)
- [ ] Bottoni secondari: `"📊 Apri report qualità"` / `"📥 Esporta CSV"` (secondary small)
- [ ] Log panel: stile aggiornato

---

## Fase 5 — Tab 3: Shared Context

### Nuovo file `shared_context.py`
- [ ] Creare `src/signal_chain_lab/ui/blocks/shared_context.py`
- [ ] Implementare `render_shared_context(state: UiState)`
- [ ] Struttura collassabile: aperto di default
- [ ] Header: icona ▶/▾ + "Contesto condiviso" + subtitle muted
- [ ] Summary riga compatta (visibile quando chiuso): `🗄 db · filtri · 📂 market_dir`
- [ ] Body sezione DB segnali: input path + Sfoglia
- [ ] Body sezione filtri: row con Trader filter / Dal / Al / Max trades
- [ ] Body sezione Cartella Market Data: input + Sfoglia + path-chip rilevato + notice "rilevato: ..."
- [ ] On toggle chiuso: aggiornare summary con valori attuali
- [ ] Wire: tutte le modifiche aggiornano APP_STATE + debounced_save

### Integrazione in `app.py`
- [ ] Tab 3 mostra `shared_context` prima della card container
- [ ] Card container ha sub-tab Market Data / Backtesting
- [ ] Sub-tab Market Data: primo di default
- [ ] Layout: `panel on` con `padding-top: calc(nav-h + 20px)`

---

## Fase 6 — Sub-tab Market Data

### Modifiche `market_data_panel.py`

#### Controlli nuovi / modificati
- [ ] Validate mode: select con opzioni "Off" e "Gaps" (rimuovere "Full" e "Light")
- [ ] Price basis: campo separato (select `last` / `mark`), non dentro data types
- [ ] Download TF: multi-select custom con tutti i TF supportati (1m/5m/15m/30m/1h/2h/4h/6h/12h/1d/1w)
- [ ] Data types: multi-select con Perp (abilitato), Funding rate (abilitato), Spot/OI/Liq/OB/Spread (ROADMAP disabilitati)
- [ ] Buffer: unità giorni (label "Pre buffer (d)", "Post buffer (d)")
- [ ] Buffer preset: rimosso dalla UI
- [ ] Nuova directory: toggle ON/OFF (non dropdown), input condizionale visibile solo quando ON

#### Controlli da spostare a Backtesting
- [ ] Simulation TF: rimosso da Market Data
- [ ] Detail TF: rimosso da Market Data

#### Sezione Coverage (nuova)
- [ ] Aggiungere sezione "Coverage" con griglia 4 colonne
- [ ] Simboli: valore aggiornato dopo Analizza (default `—`)
- [ ] Intervalli req.: valore aggiornato dopo Analizza
- [ ] Gap: valore aggiornato, colore `--wa` se > 0
- [ ] Copertura %: valore aggiornato, colore `--ok`/`--wa` in base a soglia

#### Azioni
- [ ] Bottone `"🔍 Analizza"` (primary): esegue solo plan, aggiorna Coverage
- [ ] Bottone `"⬇ Prepara"` (secondary): plan + sync + gap_validate se GAPs
- [ ] Bottone `"✓ Valida"` (secondary): validate_full solo su non ancora validati
- [ ] Bottone `"■ Arresta"` (secondary+danger): termina processo
- [ ] Rimuovere bottone `"Prepara + Valida"`
- [ ] Rimuovere bottoni funding separati (sync/validate funding) dalla barra azioni principale

#### Log
- [ ] Log Market Data con stile aggiornato ($ prompt, colori)

---

## Fase 7 — Sub-tab Backtesting

### Modifiche `block_backtest.py`

#### Notice
- [ ] Notice info in cima: `"ℹ Price basis e Market source sono rilevati automaticamente dalla cartella Market Data."`

#### Riga 1
- [ ] Policy multi-select (invariato, solo stile)
- [ ] Timeout: label `"Timeout (m)"`, input numerico, conversione × 60 al momento esecuzione
- [ ] Report output dir + bottone Sfoglia

#### Riga 2 (nuova)
- [ ] Aggiungere Simulation TF (select: 1m/5m/15m) — spostato da Market Data
- [ ] Aggiungere Detail TF (select: 1m/5m/15m) — spostato da Market Data
- [ ] Price basis: display-only con label `"· auto da market dir"`, non editabile
- [ ] Market source: display-only con label `"· auto da market dir"`, non editabile

#### Policy Studio
- [ ] Collapsible `.adv`, chiuso di default
- [ ] Editor YAML con stile `.yaml` (bg log-bg, syntax highlighting colori)
- [ ] Bottoni: Salva / Salva come nuova / + Nuova policy / ↺ Ricarica lista

#### Azioni
- [ ] `"▶ Esegui Backtest"` (primary)
- [ ] `"■ Arresta"` (secondary+danger)
- [ ] `"📄 Apri report HTML"` (secondary, disabilitato finché non disponibile)
- [ ] `"📂 Artifact dir"` (secondary, disabilitato finché non disponibile)

#### Risultati
- [ ] Stato iniziale: placeholder `"— nessun run eseguito —"` in monospace muted
- [ ] Dopo run: tabella `res-tbl` con colonne Policy / Trades / Excluded / PnL % / Win rate / Expectancy / Report
- [ ] Celle PnL: colore `--ok` se positivo, `--er` se negativo
- [ ] Link report: clickable `"📄 apri"` colore accent
- [ ] Rimuovere card summary attuali

#### Gating coverage-only
- [ ] Modificare `backtest_support.py`: rimuovere blocco hard su `market_ready`
- [ ] Aggiungere check copertura pre-run: legge `APP_STATE.market.gap_count` e `APP_STATE.market.coverage_pct`
- [ ] Log check: `"[check] Copertura dataset: {pct}% · {gap_count} gap · run consentito"`
- [ ] Bloccare solo se copertura = 0% e dati richiesti assenti
- [ ] Warning non bloccante se copertura < 100%

---

## Fase 8 — Persistenza

### Wiring `app.py`
- [ ] All'avvio: `saved = load_ui_state()` → `APP_STATE.apply_saved(saved)`
- [ ] Alla chiusura: `app.on_shutdown(lambda: save_ui_state(APP_STATE.to_dict()))`

### Wiring per blocco
- [ ] Download: chat_id, topic_id, date_from, date_to, full_history, download_media, db_output_dir
- [ ] Parse: parser_profile, generate_parse_csv, parse_reports_dir
- [ ] Shared context: db_path, trader_filter, date_from, date_to, max_trades, market_data_dir
- [ ] Market Data: source_provider, validate_mode, price_basis, download_tf, data_types, buffer_mode, pre_buffer_days, post_buffer_days, new_dir_enabled, new_dir_path
- [ ] Backtesting: backtest_policies, timeout (minuti), report_dir, simulation_tf, detail_tf

### Feedback path non validi
- [ ] Al load: chiamare `APP_STATE.validate_paths()`
- [ ] Per ogni path non valido: aggiungere bordo `--er` al relativo input
- [ ] Tooltip o label sotto: `"percorso non trovato"`
- [ ] Non cancellare il valore

---

## Fase 9 — QA

### Test funzionali
- [ ] Download: esecuzione completa → DB creato e visualizzato
- [ ] Parse: esecuzione completa → quality report con 3 card
- [ ] Market Data → Analizza → Coverage grid aggiornata
- [ ] Market Data → Prepara (mode=GAPs) → gap_validate eseguito
- [ ] Market Data → Prepara (mode=OFF) → solo sync, no gap_validate
- [ ] Market Data → Valida → validate_full eseguito
- [ ] Backtest run singola policy → tabella con 1 riga
- [ ] Backtest run 2 policy → tabella con 2 righe
- [ ] Shared context collassabile: apri/chiudi → summary corretta
- [ ] Persistenza: chiudere app → riaprire → tutti i valori ripristinati
- [ ] Persistenza: cancellare manualmente un file salvato nel path → campo marcato non valido
- [ ] Timeout 5 minuti → internamente 300s passati al runner
- [ ] Validate mode OFF → backtest consentito senza validazione
- [ ] Gating: market con 0 simboli richiesti → backtest bloccato con messaggio

### Test visivi (confronto con ui_mockup.html)
- [ ] Nav fissa con border-bottom indicator: tab attivo accent, altri muted
- [ ] Sfondo pagina `#0d1117`
- [ ] Card: `#161b22` border `#30363d` radius 6px
- [ ] Font monospace per path, ticker, ID, valori numerici
- [ ] Log panel: bg `#010409`, testo verde `#39d353`
- [ ] Log panel header: `$` prompt + titolo + chevron
- [ ] Badge RUNNING: pulse animation
- [ ] Bottone primario: filled `#58a6ff` con testo scuro
- [ ] Bottone secondary: outline `#30363d`
- [ ] Bottone danger: outline rosso `#f85149`
- [ ] Multi-select TF: dropdown con checkbox custom
- [ ] Coverage: griglia 4 colonne compatta
- [ ] Risultati backtest: tabella non card
- [ ] Shared context chiuso: summary riga monospace compatta
- [ ] Collapsible: chevron ▶/▾ senza CSS transition (display:none immediato)
- [ ] Scrollbar: 5px, thumb `#30363d`

---

## Legenda stato

```
- [ ]  Da fare
- [x]  Completato
- [~]  In corso
- [!]  Bloccato / problema
- [-]  Saltato / non applicabile
```

---

*Aggiornare questo file al completamento di ogni task.*  
*Documento generato: 2026-04-19*
