# GUI Visual Gap Report

Data verifica: 2026-04-19

Oggetto del confronto:
- GUI reale NiceGUI: `src/signal_chain_lab/ui/app.py` e blocchi `src/signal_chain_lab/ui/blocks/*`
- Mockup di riferimento: `docs/GUI_UI_UX_Style/ui_mockup.html`

## Sintesi

La GUI attuale segue il mockup solo in parte.

Allineamenti già presenti:
- stessa palette base `--bg`, `--surface`, `--accent`, `--border`
- stessa famiglia tipografica IBM Plex Sans / IBM Plex Mono
- stessa larghezza concettuale del contenuto (`--panel-w: 980px`)
- card scure con bordo sottile e raggio piccolo
- tab principali `Download`, `Parse`, `Market Data & Backtest`
- presenza del pannello `Contesto condiviso`
- presenza di log panel in stile terminale

Scarti principali:
- header e navigazione non corrispondono al mockup
- la GUI reale usa componenti Quasar/NiceGUI standard, il mockup usa controlli custom
- la gerarchia visiva è più debole del mockup
- alcune icone/simboli risultano renderizzate male nel DOM live
- spacing, densità e consistenza dei controlli non sono ancora uniformi

Conclusione:
- stato attuale: `parzialmente conforme`
- livello di match visivo stimato: `55-65%`

## Limite della verifica

La GUI live è stata avviata e ispezionata via HTML servito su `http://127.0.0.1:7777/`, ma in questo ambiente il browser headless non riesce a produrre screenshot per limiti di permessi lato crash handler. Il giudizio quindi è basato su:
- sorgente del mockup
- CSS e DOM della GUI live
- componenti Python che generano la GUI

Non è una verifica pixel-perfect.

## Gap 1: Top Navigation

Mockup:
- navbar fissa in alto
- brand `SCL · Signal Chain Lab`
- tab integrati nella barra
- bordo inferiore continuo e look molto compatto

GUI reale:
- titolo H5 separato
- sottotitolo separato
- `q-tabs` sotto il titolo
- nessun brand inline nella nav

Impatto:
- è il delta visivo più evidente
- la GUI reale appare come app Quasar stilizzata, non come UI progettata ad hoc

Modifica necessaria:
- sostituire il blocco titolo + sottotitolo + tabs con una singola top bar custom
- introdurre una struttura equivalente a:
  - brand monospace a sinistra
  - tab 01/02/03 nella stessa riga
  - contenuto sotto con `padding-top` coerente con `--nav-h`

Priorità: alta

## Gap 2: Linguaggio dei controlli

Mockup:
- input custom con `background: var(--surface-2)`
- radio pill custom
- toggle custom
- select custom con caret coerente
- bottoni molto compatti e uniformi

GUI reale:
- molti controlli sono `q-input`, `q-btn`, `q-toggle`, `q-option-group`, `q-select`
- il tema base è corretto, ma l'impronta Quasar resta visibile

Impatto:
- il mockup sembra più preciso e più "editor-like"
- la GUI reale ha controlli eterogenei tra blocchi

Modifica necessaria:
- definire una skin completa per i componenti Quasar usati
- in alternativa, sostituire i punti più visibili con HTML/CSS custom tramite `ui.html`, `ui.element` o wrapper dedicati

Priorità: alta

## Gap 3: Gerarchia dell'header di sezione

Mockup:
- ogni card ha un header breve, compatto, con numero piccolo e titolo netto
- la sezione è riconoscibile a colpo d'occhio

GUI reale:
- l'impostazione esiste, ma non è uniforme in tutti i blocchi
- alcuni blocchi hanno più rumore visivo prima del contenuto principale

Impatto:
- percezione meno ordinata
- il flusso a step è meno leggibile

Modifica necessaria:
- standardizzare tutti gli header card con un componente unico:
  - numero step monospace piccolo
  - titolo sezione
  - eventuale stato badge a destra

Priorità: media

## Gap 4: Brand e copy dell'intestazione

Mockup:
- branding minimo ma preciso
- nessun titolo applicativo grande sopra i tab

GUI reale:
- `Signal Chain Lab - Sprint 9 GUI`
- `Workflow guidato: Download dati -> Parse dati -> Backtest`

Impatto:
- la GUI sembra più interna/temporanea
- il mockup invece sembra prodotto finito

Modifica necessaria:
- rimuovere il titolo H5 e il sottotitolo dal top-level
- spostare il concetto di workflow dentro la nav o dentro un badge discreto

Priorità: alta

## Gap 5: Contesto condiviso

Mockup:
- pannello collassabile ben integrato
- summary compatta e pulita
- labels e chip molto vicini al linguaggio del resto della UI

GUI reale:
- il pannello esiste ed è una delle parti più vicine al mockup
- restano però differenze nei controlli interni e nella pulizia dell'header

Impatto:
- basso rispetto agli altri gap

Modifica necessaria:
- conservare la struttura attuale
- rifinire:
  - header del pannello
  - pulsanti `Sfoglia`
  - densità e allineamento dei campi

Priorità: media

## Gap 6: Spacing e densità

Mockup:
- spacing molto controllato
- bottoni piccoli
- campi ravvicinati ma leggibili
- altezza dei blocchi abbastanza omogenea

GUI reale:
- alcuni blocchi sono più alti e ariosi del necessario
- le altezze dei controlli non sono sempre coerenti
- il mix `q-mt-*`, `gap-*`, `padding` inline e classi genera densità variabile

Impatto:
- la UI perde compattezza
- il flusso verticale è meno efficiente

Modifica necessaria:
- introdurre un set di spacing tokens interni per la GUI
- standardizzare:
  - padding card
  - distanza tra gruppi
  - altezza input
  - altezza bottoni
  - margini dei log panel

Priorità: alta

## Gap 7: Sezioni secondarie e sub-tab

Mockup:
- sub-tab `Market Data` e `Backtesting` molto integrate nel card shell
- look da secondary nav minimale

GUI reale:
- le sub-tab esistono e usano già `.sub-nav`
- sono abbastanza vicine al mockup

Impatto:
- gap limitato

Modifica necessaria:
- piccole rifiniture:
  - peso font
  - spaziatura tab
  - bordi e padding container

Priorità: bassa

## Gap 8: Log panel

Mockup:
- log panel molto coerente con un terminale embedded
- header, collapsing e colori semantici ben leggibili

GUI reale:
- concetto corretto e già vicino
- alcune etichette e simboli non sono ancora puliti

Impatto:
- basso-medio

Modifica necessaria:
- uniformare header log
- sostituire simboli problematici con testo ASCII o icone affidabili
- controllare altezza fissa e padding interno

Priorità: media

## Gap 9: Icone e simboli corrotti

GUI reale osservata nel DOM:
- comparsa di `?`, `??`, `¦` al posto di alcune icone/emoji

Impatto:
- degrada immediatamente la qualità percepita
- fa sembrare la GUI instabile o incompleta

Possibile causa:
- uso di emoji o caratteri Unicode in punti che non stanno renderizzando bene nel percorso NiceGUI/Quasar/encoding

Modifica necessaria:
- sostituire emoji e caratteri decorativi fragili con:
  - testo puro ASCII
  - icone Quasar affidabili
  - HTML entity solo se controllata

Priorità: molto alta

## Gap 10: Coerenza cross-block

Mockup:
- tutti i blocchi parlano la stessa lingua

GUI reale:
- `Download`, `Parse`, `Market Data`, `Backtest` sono coerenti solo in parte
- ci sono differenze di stile introdotte localmente nei vari file blocco

Impatto:
- interfaccia meno solida e meno rifinita

Modifica necessaria:
- estrarre componenti condivisi:
  - section header
  - primary/secondary/danger button styling
  - input row pattern
  - path chip
  - panel shell
  - log shell

Priorità: alta

## Ordine di intervento consigliato

1. Correggere tutti i simboli corrotti e rimuovere emoji fragili.
2. Rifare la top navigation per farla combaciare al mockup.
3. Uniformare bottoni, input, select, toggle e radio.
4. Standardizzare spacing e header di card.
5. Rifinire `Contesto condiviso`, sub-tab e log panel.
6. Consolidare i pattern condivisi in componenti riusabili.

## File più probabili da toccare

- `src/signal_chain_lab/ui/app.py`
- `src/signal_chain_lab/ui/components/log_panel.py`
- `src/signal_chain_lab/ui/components/status_badge.py`
- `src/signal_chain_lab/ui/blocks/block_download.py`
- `src/signal_chain_lab/ui/blocks/block_parse.py`
- `src/signal_chain_lab/ui/blocks/shared_context.py`
- `src/signal_chain_lab/ui/blocks/market_data_panel.py`
- `src/signal_chain_lab/ui/blocks/block_backtest.py`

## Criterio di accettazione proposto

La GUI reale può essere considerata visivamente allineata al mockup quando:
- la top bar è visivamente equivalente
- non restano controlli con look Quasar evidente nei punti principali
- numerazione step, card header, bottoni e input sono uniformi
- non compaiono simboli corrotti
- `Download`, `Parse`, `Market Data`, `Backtest` sembrano parti della stessa applicazione
- un confronto visivo a colpo d'occhio non evidenzia più differenze strutturali importanti
