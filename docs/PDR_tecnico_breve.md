PRD tecnico breve — Rewrite completo chart single trade report
1. Obiettivo

Sostituire completamente il grafico attuale del Single Trade Report con un nuovo chart basato su Apache ECharts, senza riuso del renderer SVG/JS esistente.

Il nuovo chart deve essere:

indipendente dal vecchio codice
offline
multi-timeframe
navigabile con controlli nativi ECharts
adatto a mostrare candele reali, livelli operativi ed eventi trade
2. Decisione architetturale

Approccio scelto: full rewrite.

Non si deve fare refactor del chart esistente.
Non si deve mantenere compatibilità col vecchio renderer.
Non si deve lasciare un doppio percorso “vecchio + nuovo”.

Il vecchio chart viene considerato legacy e deve essere rimosso dal flusso del single trade report.

3. Ambito
In scope
riscrittura completa del chart del file detail.html
integrazione di echarts.min.js locale
supporto multi-timeframe
candlestick chart nativo
tooltip nativo
dataZoom nativo
overlay di Entry / SL / TP / Exit / BE
marker eventi operativi
toggle visuale dei layer
fallback leggibile se i dati OHLCV mancano
Out of scope
modifiche sostanziali al policy_report.html aggregato
refactor del chart equity curve legacy
confronto multi-trade
indicatori tecnici
volume subplot
CDN esterne
compatibilità con il vecchio chart custom
4. Stato attuale da superare

Attualmente il single trade report contiene un chart custom scritto in html_writer.py, con:

rendering SVG manuale
zoom custom
tooltip custom
logica annotazioni mescolata al renderer
switch timeframe custom

Questa implementazione va rimossa dal layer del single trade report e sostituita integralmente.

5. Architettura target

Nuova struttura:

src/signal_chain_lab/policy_report/
  html_writer.py
  trade_chart_payload.py
  trade_chart_echarts.py
  assets/
    echarts.min.js
Responsabilità
trade_chart_payload.py

Costruisce un payload JSON puro per il chart.

Responsabilità:

serializzazione candele per timeframe
estrazione livelli operativi
estrazione eventi chartabili
definizione timeframe default
normalizzazione timestamp in epoch ms
trade_chart_echarts.py

Renderizza il chart ECharts a partire dal payload.

Responsabilità:

container HTML
toolbar timeframe
toggle layer
script di inizializzazione ECharts
option config
resize handler
fallback “no candles”
html_writer.py

Resta il compositore della pagina HTML del single trade report.

Responsabilità:

summary card
chart section
timeline eventi
link di ritorno

Non deve più contenere logica di rendering chart.

6. File da modificare
A. src/signal_chain_lab/policy_report/html_writer.py

Interventi richiesti:

rimuovere _chart_html(...)
rimuovere _chart_html_multi_tf(...)
rimuovere JS e SVG custom associati
ridurre il CSS chart-specific al minimo necessario
usare il nuovo renderer ECharts
B. src/signal_chain_lab/policy_report/runner.py

Interventi richiesti:

lasciare invariato il caricamento candele multi-timeframe
copiare echarts.min.js negli artifact del report
passare il path asset al single trade report writer
C. Nuovo src/signal_chain_lab/policy_report/trade_chart_payload.py

Da creare.

D. Nuovo src/signal_chain_lab/policy_report/trade_chart_echarts.py

Da creare.

E. Nuovo asset src/signal_chain_lab/policy_report/assets/echarts.min.js

Da aggiungere al repo.

7. Sorgenti dati

Il nuovo chart deve usare soltanto dati reali già disponibili nel flusso report:

TradeResult
EventLogEntry
Candle
candles_by_timeframe

Non introdurre dataset demo o mock come fonte primaria del report.

8. Payload chart target

Formato richiesto:

{
  "meta": {
    "signal_id": "abc",
    "symbol": "BTCUSDT",
    "side": "LONG",
    "policy_name": "default",
    "default_timeframe": "1m"
  },
  "candles_by_timeframe": {
    "1m": [
      [1710000000000, 100.0, 103.0, 99.0, 105.0, 1200.0]
    ],
    "5m": []
  },
  "levels": {
    "entries": [
      { "label": "Entry 1", "price": 101.5 }
    ],
    "sl": [
      { "label": "Initial SL", "price": 98.0 },
      { "label": "Break Even", "price": 101.5 }
    ],
    "tps": [
      { "label": "TP1", "price": 104.0 },
      { "label": "TP2", "price": 108.0 }
    ],
    "exit": [
      { "label": "Final Exit", "price": 103.2 }
    ]
  },
  "events": [
    {
      "ts": 1710000300000,
      "price": 101.5,
      "kind": "FILL",
      "label": "Entry filled"
    }
  ]
}
9. Regole di costruzione del payload
9.1 Candles

Per ogni timeframe disponibile:

[ts_ms, open, close, low, high, volume]

Ordine obbligatorio per ECharts candlestick:

open
close
low
high
9.2 Levels

Suddividere i livelli in gruppi separati:

entries
sl
tps
exit

Non produrre un unico blocco indistinto di annotazioni.

9.3 Events

Ogni evento chartabile deve avere:

timestamp
prezzo
kind
label

Eventi tipici:

FILL
MOVE_SL_BE
TP_HIT
SL_HIT
PARTIAL_CLOSE
CLOSE
CANCEL
10. Requisiti UX del nuovo chart

Il nuovo chart deve offrire:

10.1 Cambio timeframe

Toolbar con pulsanti timeframe disponibili:

1m
5m
15m
1h
4h
1d

Il cambio timeframe deve ricaricare solo la serie candlestick e preservare il resto della pagina.

10.2 Navigazione nativa

Usare solo strumenti nativi ECharts:

dataZoom tipo inside
dataZoom tipo slider
axisPointer tipo cross
10.3 Tooltip

Tooltip nativo axis-based con:

timestamp candela
O/H/L/C
eventuali eventi vicini
livelli rilevanti nel punto
10.4 Toggle layer

Devono essere disattivabili almeno questi gruppi:

Entries
SL / BE
TPs
Exit
Events
10.5 Reset

Pulsante reset zoom/view.

11. Strategia di rendering ECharts

Serie consigliate:

candlestick → prezzo
line → entries
line → SL / BE
line → TPs
line → exit
scatter → eventi
Nota importante

Non usare una sola markLine monolitica per tutto.
I gruppi devono essere separati per permettere toggle e gestione pulita.

12. Regole implementative rigide
Da fare
separare payload e renderer
usare asset locale
mantenere il chart indipendente dal vecchio codice
prevedere fallback leggibile
usare funzioni piccole e testabili
Da non fare
non estendere _chart_html
non estendere _chart_html_multi_tf
non riusare il vecchio SVG
non mantenere vecchi zoom/tooltip custom
non introdurre fallback al chart legacy
non usare CDN
non mischiare logica dominio e logica rendering nella stessa funzione
13. Fallback richiesto

Se non ci sono candele disponibili per nessun timeframe:

la pagina detail.html deve generarsi comunque
al posto del chart deve apparire una card leggibile:
“No market candles available for this trade”
mostrare comunque livelli ed eventi in forma tabellare o sintetica

Nessun crash. Nessun grafico vuoto ambiguo.

14. Criteri di accettazione

La feature è accettata se:

detail.html usa solo il nuovo renderer ECharts
il vecchio renderer chart del single trade è rimosso
il report funziona offline
il timeframe switch funziona
dataZoom inside + slider funziona
tooltip nativo funziona
Entries / SL / TPs / Events possono essere nascosti/mostrati
eventi operativi compaiono come marker
in assenza di candele compare fallback leggibile
policy_report.html continua a linkare correttamente il detail.html
15. Piano di implementazione
Fase 1 — Rimozione legacy
eliminare il vecchio renderer chart da html_writer.py
ripulire CSS/JS chart legacy
Fase 2 — Payload
introdurre trade_chart_payload.py
serializzare candles, levels, events
Fase 3 — Renderer
introdurre trade_chart_echarts.py
implementare chart ECharts con toolbar e layer toggle
Fase 4 — Asset offline
aggiungere echarts.min.js
copiare asset negli artifact
Fase 5 — Integrazione finale
collegare write_single_trade_html_report(...)
verificare output detail.html