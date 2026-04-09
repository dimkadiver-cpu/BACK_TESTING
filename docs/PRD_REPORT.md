Mini PRD — Policy Report Template
1. Obiettivo

Definire un template standard per il Policy Report che permetta di:

analizzare una singola policy su un dataset di segnali/trade
mostrare il riepilogo principale in modo immediato
approfondire solo quando serve, tramite sezioni a scomparsa
accedere ai Single Trade Report completi per il debug operativo

Il report deve essere leggibile da umano, esportabile in HTML e coerente con gli artifact CSV/JSON/YAML prodotti dalla simulazione.

2. Scope

Il Policy Report copre una sola policy eseguita su un dataset.

Include:

metadati dataset
valori configurati della policy (policy.yaml)
summary della policy
excluded chains
trade results
collegamenti ai report di dettaglio dei singoli trade

Non include:

confronto tra policy diverse
scenario comparison
equity curve aggregata
3. Struttura del report
3.1 Titolo

Formato:

Policy Report - <REPORT_NAME>

Esempio:

Policy Report - trader_a_Q1_2026_BE_after_TP1

3.2 Sezioni
A. Dataset metadata

Tipo: collapsible / a scomparsa

Contiene informazioni sul dataset usato, ad esempio:

dataset name
source database
trader filter
date range
selected chains count
simulated chains count
excluded chains count
generation timestamp
B. Metadata — policy.yaml values

Tipo: collapsible / a scomparsa

Mostra i valori caricati da policy.yaml.

Obiettivo:

rendere visibile la configurazione usata nella run
facilitare audit e riproducibilità

Può essere mostrata:

come tabella chiave/valore
oppure come blocco YAML leggibile
C. Policy Summary

Tipo: fixed / fisso, sempre visibile

È la sezione principale del report.

Campi minimi:

Policy name
Total trades
Win rate %
Net Profit %
Profit %
Loss %
Profit factor
Expectancy %
Max drawdown %
Avg warnings per trade
Excluded chains count

Note:

tutte le metriche profit/loss richieste devono essere mostrate in percentuale
questa sezione non deve contenere grafici equity
D. Excluded chains

Tipo: collapsible / a scomparsa

Mostra le chain escluse dalla simulazione.

Colonne richieste:

Signal ID
Symbol
Reason
Note
Original TEXT

Comportamento:

cliccando Original TEXT si apre un piccolo popup / modal
il popup mostra il testo originale raw del messaggio Telegram (telegram_RAW)

Obiettivo:

capire rapidamente perché una chain è stata esclusa
verificare il messaggio originale senza uscire dal report
E. Trade results

Tipo: tabella principale

Mostra i trade effettivamente simulati.

Colonne richieste:

Signal ID
Symbol
Side
Status
Close reason
Realized PnL %
Warnings
Ignored events
Created
Closed
Detail

Comportamento:

Realized PnL deve essere mostrato in percentuale
cliccando Detail, l’utente apre il Single Trade Report completo relativo a quel trade
4. Single Trade Report collegato

Ogni riga della tabella Trade results deve poter aprire un report dedicato del singolo trade.

Requisiti minimi del Single Trade Report
titolo con Signal ID, Symbol, Side
summary del trade
Realized PnL %
grafico realistico a candlestick
marker di:
entry
avg entry
stop loss
break even move
TP hit
SL hit
close
nelle label TP hit / SL hit deve comparire anche la percentuale di guadagno/perdita
Event Timeline

La sezione Event Timeline deve mostrare gli eventi operativi applicati.

Per segnali e update operativi usati, aggiungere:

Original TEXT

Comportamento:

cliccando Original TEXT, si apre popup/modal con il testo raw originale Telegram

Obiettivo:

collegare sempre l’azione simulata al messaggio sorgente
5. File output previsti

Il template deve essere compatibile con i seguenti artifact:

policy_report_complete.html
policy_summary.json
policy_summary.csv
trade_results.csv
excluded_chains.csv
policy.yaml
trades/<signal_id>/detail.html

Opzionale:

immagini PNG del grafico trade
JSON strutturato del dettaglio trade
6. Requisiti UX
Collapsible sections

Devono essere collapsible:

Dataset metadata
Metadata — policy.yaml values
Excluded chains
Popup / modal

Devono supportare popup/modal per:

Original TEXT nelle excluded chains
Original TEXT negli eventi del Single Trade Report
Navigazione
dalla tabella trade si apre il dettaglio singolo trade
il dettaglio deve essere facilmente navigabile e leggibile anche standalone
7. Requisiti dati

Il report deve poter essere generato anche se:

alcune chain sono escluse
alcuni trade hanno warning
alcuni eventi sono ignorati
non tutti i campi opzionali della policy sono presenti

Il report non deve fallire se:

manca una nota
manca il raw text per un evento non operativo
alcuni campi YAML sono null o default
8. Acceptance criteria

Il template è accettato se:

Il titolo segue il formato Policy Report - <REPORT_NAME>
Policy Summary è sempre visibile
Dataset quality non è presente
Equity curve non è presente
Net Profit, Profit, Loss, Realized PnL sono mostrati in percentuale
Excluded chains contiene il campo Original TEXT con popup funzionante
Trade results contiene la colonna Detail
Detail apre un Single Trade Report completo
Nel Single Trade Report, Event Timeline mostra Original TEXT per segnali/update operativi usati
Il grafico del single trade è a candlestick e mostra le label con percentuali su TP hit / SL hit
9. Non-goals

Questo template non deve:

confrontare più policy
sostituire lo Scenario Report
mostrare metriche aggregate multi-policy
usare equity curve come elemento principale
10. Sintesi finale

Il Policy Report deve essere il report centrale per valutare una singola policy, con:

summary immediato
configurazione visibile
elenco esclusioni
tabella trade
accesso rapido al dettaglio operativo di ogni trade

Se vuoi, lo trasformo subito in un file Markdown pronto da scaricare.
