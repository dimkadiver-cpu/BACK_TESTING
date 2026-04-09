# Piano di implementazione GUI (allineamento a `docs/GUI_PRD.md`)

## Obiettivo
Allineare la GUI NiceGUI al PRD mantenendo **tutte le funzionalità già presenti e non in conflitto** (Download, Parse, preparazione market data, backtest base), e aggiungendo in modo incrementale le capacità mancanti nel Blocco 3.

## Stato attuale (as-is)

### Blocco 1 — Download
- Flusso credenziali Telegram + OTP + gestione sessione presente.
- Download storico con filtri data/topic presente.
- Selezione output DB e cancellazione DB scaricato presente.
- Summary DB finale presente.

### Blocco 2 — Parse
- Parse DB + replay operation rules presente.
- Filtro trader presente (Auto / trader_a / trader_b / trader_c / trader_d / trader_3).
- Export CSV opzionale presente.
- Quality report presente.
- Gate verso Backtest (`backtest_ready`) presente.

### Blocco 3 — Backtest
- Input DB + validazione esistenza presente.
- Policy selector limitato a `original_chain` e `signal_only`.
- Market data dir + modalità `existing_dir/new_dir` + preparazione plan/sync/validate presente.
- Timeframe, price basis, timeout presenti.
- Avvio backtest presente.
- Summary da log presente.

## Gap rispetto a `docs/GUI_PRD.md`
1. **Policy dinamiche da cartella** `configs/policies` (nel PRD è indicato path Windows equivalente).
2. **Editor policy**: modifica/salvataggio/clonazione policy da popup.
3. **Rilevazione multi-trader dal DB backtest** e selezione trader (uno/tutti) prima del run.
4. **Date range per trade backtestati** (Dal/Al).
5. **Limite numero trade** backtestabili.
6. **Configurazione report output** (cartella di salvataggio, default interna progetto).
7. **Link finale al report HTML** (non solo path artifact generico).

## Principi di compatibilità (vincolo richiesto)
- Non rimuovere feature esistenti di Download/Parse/Market data.
- Rendere i blocchi **indipendenti**: Download / Parse / Backtest devono poter essere usati anche separatamente, a condizione che l'input richiesto sia valido.
- Mantenere comportamento default attuale se i nuovi campi non vengono valorizzati.
- Implementare fallback robusti: in assenza di metadata/policy extra, la GUI continua a funzionare in modalità baseline.

## Nota architetturale aggiornata (su richiesta)
- Il flusso guidato a tab resta disponibile come percorso consigliato.
- Tuttavia, l'applicazione deve supportare anche uso non lineare:
  - Parse avviato su DB già esistente senza passare da Download.
  - Backtest avviato su DB già pronto senza passare da Parse nella stessa sessione GUI.
- I gate di abilitazione devono quindi basarsi su **validazione input** (esistenza DB, schema minimo, campi obbligatori), non sull'ordine di esecuzione dei tab.

## Piano di implementazione (incrementale)

### Fase 0 — Hardening e baseline tecnica
- Introdurre helper centrali lato GUI per:
  - discovery policy files;
  - introspezione DB (trader disponibili, range temporale);
  - risoluzione cartelle output report.
- Aggiungere logging strutturato nel pannello backtest per nuove opzioni passate al comando.

**Deliverable**
- Modulo utility dedicato (`src/signal_chain_lab/ui/blocks/backtest_support.py`).
- Nessun breaking change UI.

### Fase 1 — Policy dinamiche + editor popup
- Sostituire select statica con select popolata da file policy disponibili in `configs/policies`.
- Aggiungere pulsanti:
  - “Ricarica policy”;
  - “Modifica policy” (popup editor testo/JSON);
  - “Salva come nuova policy”.
- Validare sintassi policy prima del salvataggio.

**Compatibilità**
- Se la cartella policy è vuota/non valida, fallback a `original_chain` e `signal_only`.

### Fase 2 — Multi-trader detection e filtro backtest
- Alla selezione DB, leggere trader disponibili da tabelle parse/operational.
- Mostrare selector:
  - `all` (default);
  - singoli trader rilevati.
- Passare filtro trader al comando backtest (nuovo argomento CLI o wrapper lato script).

**Compatibilità**
- Se DB non supporta trader-level metadata, nascondere o disabilitare filtro e usare `all`.

### Fase 3 — Filtri temporali e limite trade
- Aggiungere campi `Dal`, `Al`, `Max trades` nel blocco Backtest.
- Validazioni:
  - formato data;
  - `Dal <= Al`;
  - limite positivo.
- Trasmettere opzioni al runner backtest.

**Compatibilità**
- Campi vuoti = comportamento corrente (nessun filtro).

### Fase 4 — Configurazione report output + link HTML
- Aggiungere campo “Cartella report” (default interno progetto, es. `artifacts/scenarios`).
- Passare directory output al comando backtest.
- A fine run, identificare report HTML principale e mostrare link cliccabile (`ui.link`) per apertura cartella/file.

**Compatibilità**
- Se report HTML non trovato, mostrare path artifact come fallback attuale.

### Fase 5 — QA, regressione e documentazione ✅ COMPLETATA 2026-04-09

`docs/GUI_PRD.md` aggiornato con nuovi campi UiState.

#### Protocollo test manuale — 3 percorsi

**Percorso A — flusso completo standard**
1. Avvia app: `python -m src.signal_chain_lab.ui.app`
2. Blocco 3: inserisci DB parsato esistente → verifica che "Rileva" popoli trader e date
3. Policy: verifica che il select mostri tutte le policy in `configs/policies/` (esclusi template)
4. Esegui con impostazioni default → verifica log, summary e link HTML al report
5. Atteso: `artifacts/scenarios/scenario_report.html` cliccabile nel summary

**Percorso B — DB multi-trader con filtri**
1. Usa un DB con almeno 2 trader → "Rileva" → seleziona un trader specifico
2. Imposta `Dal` e `Al` su un sottoinsieme del range rilevato
3. Imposta `Max trade = 5`
4. Esegui → verifica nel log: `chains_selected=N` con N ≤ 5 e solo il trader selezionato
5. Atteso: nessun errore anche se i campi filtro riducono le chain a 0 (run_scenario lo gestisce)

**Percorso C — policy custom + cartella report personalizzata**
1. Apri "Modifica" su una policy → modifica un campo numerico → "Salva"
2. Crea nuova policy via "Nuova" con nome `test_custom` → verifica che appaia nel select dopo "Ricarica"
3. Seleziona 2 policy inclusa `test_custom`
4. Imposta "Cartella report output" su una cartella personalizzata (es. `artifacts/test_run`)
5. Esegui → verifica che il report HTML sia creato nella cartella custom e il link sia corretto

#### Regressions da verificare
- Download e Parse funzionano invariati (nessuna modifica ai blocchi 1 e 2)
- Con filtri vuoti / policy di default il comportamento è identico al pre-Fase 0
- `--output-dir artifacts/scenarios` (default) produce gli stessi artifact di prima

## Ordine consigliato delle modifiche codice
1. `src/signal_chain_lab/ui/state.py`
   - nuovi campi di stato per policy file, trader filter, backtest date range, max trades, report dir, report html path.
2. `src/signal_chain_lab/ui/blocks/block_backtest.py`
   - refactor in sezioni: input model, validation, command builder, UI rendering.
3. `scripts/run_scenario.py` (o wrapper dedicato)
   - accettare nuovi argomenti senza rompere CLI esistente.
4. eventuale nuovo modulo
   - parsing/salvataggio policy e DB introspection.
5. docs
   - aggiornamento istruzioni operative.

## Definition of Done (DoD)
- Le funzioni già presenti continuano a funzionare senza regressioni.
- Tutti i punti “da fare” del Blocco 3 nel PRD sono coperti.
- Ogni nuova opzione UI ha validazione e fallback.
- Backtest termina con link report HTML quando disponibile.
- Piano test eseguito e documentato.

## Rischi e mitigazioni
- **Rischio:** formato policy eterogeneo/non validabile.
  - **Mitigazione:** validatore soft + fallback baseline.
- **Rischio:** DB con schema variabile tra ambienti.
  - **Mitigazione:** introspezione con query robuste e fallback UI.
- **Rischio:** argomenti CLI nuovi non supportati negli script.
  - **Mitigazione:** introdurre compat layer o wrapper senza cambiare comportamento default.

## Prossimo step operativo
Partire da **Fase 0 + Fase 1** in una singola iterazione breve (PR piccolo), poi procedere con Fase 2–4 in PR successivi per ridurre rischio regressione.
