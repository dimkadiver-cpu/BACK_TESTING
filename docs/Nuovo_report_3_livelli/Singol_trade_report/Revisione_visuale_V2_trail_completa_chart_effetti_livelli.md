# Revisione visuale V2 — event rail, chart focalizzato su prezzo e livelli

> Documento derivato dal PRD master:
> `PRD_definitivo_sistemazione_eventi_single_trade_report.md`
> In caso di conflitto prevale sempre il PRD master.

## 1. Decisione aggiornata

La logica finale è:

- **Event rail** = cronologia sintetica degli eventi con effetto concreto sul trade;
- **Chart principale** = rappresentazione di prezzo, livelli e punti esecutivi rilevanti;
- **Sidebar / selected event summary** = dettaglio leggibile dell’evento selezionato;
- **Event list** = livello operativo principale, con sezioni A e B;
- **Audit drawer** = dettaglio tecnico completo, apribile solo dalla event list.

Questa scelta evita che chart e rail diventino copie della event list.

---

## 2. Principio guida

Il chart deve rispondere a questa domanda:

**Come si è mosso il prezzo e come sono cambiati i livelli del trade nel tempo?**

L’event rail deve rispondere a questa domanda:

**Quali sono gli eventi con impatto concreto che hanno cambiato il trade?**

La event list deve rispondere a questa domanda:

**Come leggo in modo ordinato sia gli eventi impattanti sia quelli non operativi?**

Quindi:

- la rail racconta solo la storia operativa essenziale;
- il chart mostra prezzo, livelli, fill, riduzioni e chiusure;
- gli eventi B restano nella event list sezione B e nell’audit;
- i cambi di stop e break-even si leggono soprattutto nella geometria delle linee.

---

## 3. Regole generali di rappresentazione

### 3.1 Event rail

L’event rail deve contenere solo gli eventi della **Sezione A**.

Ogni item deve avere:

- timestamp;
- label sintetica;
- source;
- stato selezionato;
- sincronizzazione con chart e event list.

L’event rail **non** deve aprire direttamente l’audit drawer.

### 3.2 Chart

Il chart deve mostrare sempre:

- candlestick;
- livelli attivi nel tempo;
- marker solo per eventi visivamente forti o esecutivi;
- effetti geometrici dei cambi di livello.

Il chart non deve diventare una seconda event list.

### 3.3 Eventi B

Gli eventi non operativi o informativi (`IGNORED`, `SYSTEM_NOTE`, post mortem, note tecniche) non devono entrare nella rail standard e non devono sporcare il chart standard.

Devono restare leggibili in:

- event list, sezione B;
- audit drawer.

---

## 4. Marker chart

### 4.1 Marker obbligatori

Devono avere marker esplicito:

- `ENTRY_FILLED_INITIAL`
- `ENTRY_FILLED_SCALE_IN`
- `EXIT_PARTIAL_TP`
- `EXIT_PARTIAL_MANUAL`
- `EXIT_FINAL_TP`
- `EXIT_FINAL_SL`
- `EXIT_FINAL_MANUAL`
- `EXIT_FINAL_TIMEOUT`

### 4.2 Marker opzionali leggeri

Possono avere marker leggero opzionale:

- `PENDING_CANCELLED_TRADER`
- `PENDING_CANCELLED_ENGINE`
- `PENDING_TIMEOUT`

### 4.3 Nessun marker dedicato

Non devono avere marker dedicato:

- `SETUP_CREATED`
- `ENTRY_ORDER_ADDED`
- `STOP_MOVED`
- `BREAK_EVEN_ACTIVATED`
- `IGNORED`
- `SYSTEM_NOTE`

---

## 5. Eventi che modificano solo la geometria

I seguenti eventi non devono generare marker chart indipendenti:

- `STOP_MOVED`
- `BREAK_EVEN_ACTIVATED`

Effetti ammessi:

- chiusura del vecchio segmento stop;
- apertura del nuovo segmento stop;
- elbow o continuità coerente;
- aggiornamento etichetta livello;
- eventuale cambio stile della linea.

Il loro significato principale deve emergere dalla linea, non da un punto-evento.

---

## 6. Comportamento evento per evento

### 6.1 `SETUP_CREATED`

**Rail:** sì.

**Chart:** nessun marker.

**Effetto visivo:** è il punto di partenza delle linee iniziali di `ENTRY`, `SL` e `TP`.

### 6.2 `ENTRY_ORDER_ADDED`

**Rail:** sì.

**Chart:** nessun marker.

**Effetto visivo:** fa comparire o estende una linea pending / una gamba entry pianificata.

### 6.3 `ENTRY_FILLED_INITIAL`

**Rail:** sì.

**Chart:** marker forte di fill.

**Effetto visivo:**

- apre realmente il trade;
- interrompe la linea pending della gamba fillata nel punto del fill;
- non deve lasciare quella stessa entry pending visibile oltre il fill.

### 6.4 `ENTRY_FILLED_SCALE_IN`

**Rail:** sì.

**Chart:** marker forte di fill.

**Effetto visivo:**

- aumenta la posizione;
- interrompe la linea pending della gamba fillata nel punto del fill;
- aggiorna il prezzo medio e la struttura reale della posizione.

### 6.5 `STOP_MOVED`

**Rail:** sì.

**Chart:** nessun marker.

**Effetto visivo:** chiude il segmento stop precedente e apre il successivo.

### 6.6 `BREAK_EVEN_ACTIVATED`

**Rail:** sì.

**Chart:** nessun marker.

**Effetto visivo:** converte la linea stop al livello BE / entry.

### 6.7 `EXIT_PARTIAL_TP`

**Rail:** sì.

**Chart:** marker forte.

**Effetto visivo:** riduce la posizione; il TP colpito si arresta; i livelli residui continuano se ancora validi.

### 6.8 `EXIT_PARTIAL_MANUAL`

**Rail:** sì.

**Chart:** marker forte.

**Effetto visivo:** riduce la posizione senza fingere un TP hit.

### 6.9 `EXIT_FINAL_TP`

**Rail:** sì.

**Chart:** marker forte.

**Effetto visivo:** chiude tutte le linee residue del trade.

### 6.10 `EXIT_FINAL_SL`

**Rail:** sì.

**Chart:** marker forte.

**Effetto visivo:** arresta la linea stop nel punto hit e chiude il trade.

### 6.11 `EXIT_FINAL_MANUAL`

**Rail:** sì.

**Chart:** marker forte.

**Effetto visivo:** chiude tutte le linee residue senza fingere TP o SL.

### 6.12 `PENDING_CANCELLED_*`

**Rail:** sì.

**Chart:** marker leggero opzionale.

**Effetto visivo:** rimuove i livelli pending coinvolti.

### 6.13 `PENDING_TIMEOUT`

**Rail:** sì.

**Chart:** marker leggero opzionale.

**Effetto visivo:** rimuove i livelli pending scaduti.

### 6.14 `IGNORED` / `SYSTEM_NOTE`

**Rail:** no.

**Chart:** nessun marker.

**Effetto visivo:** nessun impatto sui livelli.

Sono visibili in event list sezione B e in audit drawer.

---

## 7. Regola definitiva dei livelli dinamici

### 7.1 Entry plan lines

Le linee di entry pianificata esistono solo finché il piano è attivo.

Una singola linea pending di entry si interrompe quando quella gamba viene:

- fillata;
- cancellata;
- scaduta;
- resa irrilevante dalla chiusura finale.

### 7.2 Average Entry line

La `Average Entry line` rappresenta la posizione reale media, non il piano teorico.

Regole:

- con una sola entry fillata può restare nascosta di default;
- dal secondo fill eseguito in poi deve comparire automaticamente;
- deve durare per tutto il trade aperto;
- deve aggiornarsi a ogni nuovo scale-in che cambia il prezzo medio;
- deve terminare all’`EXIT_FINAL_*`.

### 7.3 Stop line

La linea stop è segmentata nel tempo.

Ogni `STOP_MOVED` o `BREAK_EVEN_ACTIVATED` chiude un segmento e ne apre un altro.

### 7.4 TP lines

Ogni TP resta vivo finché viene colpito o finché la posizione termina in altro modo.

### 7.5 Exit finale

Un `EXIT_FINAL_*` deve chiudere tutte le linee residue del trade.

---

## 8. Priorità visuali del chart

Il chart builder deve rispettare queste priorità:

1. livelli e continuità prima dei marker;
2. pochi marker, ma semanticamente forti;
3. `STOP_MOVED` e `BREAK_EVEN_ACTIVATED` leggibili dalla linea;
4. `IGNORED` e `SYSTEM_NOTE` fuori dal chart standard;
5. `OPTIONAL_LIGHT` secondari rispetto ai `REQUIRED`;
6. la distinzione tra **linee di piano** e **linee di posizione reale** deve restare leggibile.

---

## 9. Sincronizzazione UX

- click su marker chart → apre/evidenzia la card corrispondente nella event list;
- click su item rail → apre/evidenzia la card corrispondente nella event list;
- la sidebar mostra il selected event summary;
- l’audit drawer si apre soltanto dal pulsante `AUDIT` nella card event list.

---

## 10. Decisione finale

La rappresentazione corretta è:

- **rail operativa** per gli eventi con effetto concreto;
- **chart focalizzato** su prezzo, livelli e punti esecutivi forti;
- **event list** come lettura primaria degli eventi A e B;
- **stop / BE** rappresentati come geometria e non come marker;
- **audit drawer** come contenitore tecnico completo, aperto solo dalla event list.
