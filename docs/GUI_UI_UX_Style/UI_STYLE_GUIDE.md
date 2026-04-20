# Signal Chain Lab — UI Style Guide

Documento di riferimento per replicare l'identità visiva di Signal Chain Lab in sessioni separate o nuovi artefatti.

---

## 1. Identità visiva

**Concept:** CLI Operator Console. Un'interfaccia per tecnici che lavorano con dati, non per utenti generici. Tono: preciso, denso, strumentale. Nessun gradiente viola, nessuna illustrazione, nessun card shadow morbido. Tutto misurabile, tutto controllabile.

**Ispirazione:** GitHub dark theme + terminale Unix + pannello di controllo industriale.

---

## 2. Design Tokens — CSS Variables

```css
:root {
  /* Surfaces */
  --bg:        #0d1117;   /* background pagina (quasi nero GitHub dark) */
  --surface:   #161b22;   /* card, pannelli principali */
  --surface-2: #1c2128;   /* card innestati, input bg */

  /* Bordi */
  --border:    #30363d;

  /* Testo */
  --text:      #e6edf3;   /* testo principale */
  --muted:     #8b949e;   /* label, placeholder, secondario */

  /* Accent semantici */
  --accent:    #58a6ff;   /* blu GitHub — CTA primari, link, focus ring */
  --ok:        #3fb950;   /* success, DONE, stato positivo */
  --wa:        #d29922;   /* warning, STALE, attenzione */
  --er:        #f85149;   /* error, danger, eliminazione */

  /* Log panel */
  --log-bg:    #010409;   /* sfondo terminale */
  --log-g:     #39d353;   /* testo terminale verde */

  /* Typography */
  --mono: 'IBM Plex Mono', 'Courier New', monospace;
  --sans: 'IBM Plex Sans', system-ui, sans-serif;

  /* Layout */
  --panel-w: 980px;       /* larghezza massima pannello centrale */
  --nav-h:   42px;        /* altezza tab nav */
  --radius:  6px;         /* border-radius globale */
}
```

---

## 3. Tipografia

### Font stack

```html
<!-- Nel <head> -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
```

| Uso | Font | Peso | Dimensione |
|---|---|---|---|
| Corpo generale | IBM Plex Sans | 400 | 13px |
| Label UI | IBM Plex Sans | 500 | 12px |
| Titoli sezione | IBM Plex Sans | 600 | 11px uppercase |
| Valori tecnici (prezzi, path, ID) | IBM Plex Mono | 400 | 12–13px |
| Log terminale | IBM Plex Mono | 400 | 12px |
| Bottoni | IBM Plex Sans | 500 | 12px |

### Regole

- **Valori numerici, path, ticker, timestamp → sempre `font-family: var(--mono)`**
- Titoli sezione: `text-transform: uppercase; letter-spacing: 0.06em; font-size: 10px; color: var(--muted)`
- Nessun font decorativo — coerenza mono+sans è l'unico sistema

---

## 4. Colori — Semantica e Uso

| Token | Valore | Quando usarlo |
|---|---|---|
| `--accent` | `#58a6ff` | Bottoni primari, link attivi, focus ring, tab attivo, badge RUNNING |
| `--ok` | `#3fb950` | Stato DONE, READY, successo, checkmark |
| `--wa` | `#d29922` | WARNING, STALE, attenzione non bloccante |
| `--er` | `#f85149` | ERROR, pulsanti danger, validazione fallita |
| `--muted` | `#8b949e` | Label, caption, placeholder, stato NOT_STARTED |
| `--text` | `#e6edf3` | Corpo principale |
| `--log-g` | `#39d353` | Solo testo nel log terminale |

**Regola:** usa `color-mix()` o `opacity: 0.15` per fondali semantici (`--accent` con 15% opacity per highlight).

---

## 5. Layout

### Struttura pagina

```
body (bg: var(--bg), font: var(--sans), 13px)
  └── .nav (fixed top, height: var(--nav-h), border-bottom: var(--border))
        └── .nav-inner (max-width: var(--panel-w), centrato, flex)
  └── .main (padding-top: var(--nav-h) + 1rem)
        └── .panel (max-width: var(--panel-w), margin: auto, padding: 0 1rem)
              └── blocchi verticali
```

### Nav orizzontale (tabs)

```html
<nav class="nav">
  <div class="nav-inner">
    <span class="brand">SCL</span>          <!-- brand monospace, accent color -->
    <button class="tab active" onclick="switchTab('t01')">01 · Download</button>
    <button class="tab" onclick="switchTab('t02')">02 · Parse</button>
    <button class="tab" onclick="switchTab('t03')">03 · Market & Backtest</button>
    <div class="nav-r">                     <!-- badge di stato a destra -->
      <span class="badge b-done">DL</span>
      <span class="badge b-ready">PA</span>
      <span class="badge b-running">MD</span>
      <span class="badge b-not">BT</span>
    </div>
  </div>
</nav>
```

```css
.nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  height: var(--nav-h);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
}
.nav-inner {
  max-width: var(--panel-w);
  width: 100%; margin: 0 auto;
  padding: 0 1rem;
  display: flex; align-items: center; gap: 2px;
}
.brand {
  font-family: var(--mono); font-size: 12px;
  color: var(--accent); margin-right: 1rem; opacity: 0.9;
}
.tab {
  padding: 0 14px; height: var(--nav-h);
  background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--muted); font: 500 12px var(--sans);
  cursor: pointer; transition: color .15s, border-color .15s;
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--text); border-bottom-color: var(--accent); }
.nav-r { margin-left: auto; display: flex; gap: 4px; align-items: center; }
```

---

## 6. Componenti

### 6.1 Card / Blocco

```html
<div class="card">
  <div class="card-hdr">
    <span class="card-title">NOME SEZIONE</span>
    <span class="badge b-done">DONE · 14:32</span>
  </div>
  <!-- contenuto -->
</div>
```

```css
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 12px;
  overflow: hidden;
}
.card-hdr {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.card-title {
  font-family: var(--sans); font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
}
```

### 6.2 Form grid

```html
<div class="fg">          <!-- form grid, 2 colonne -->
  <div class="frow">
    <label class="flabel">Label</label>
    <input class="finput" type="text" value="valore">
  </div>
  <div class="frow">
    <label class="flabel">Select</label>
    <select class="fsel">
      <option>opzione 1</option>
    </select>
  </div>
</div>
```

```css
.fg   { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 14px 16px; }
.frow { display: flex; flex-direction: column; gap: 4px; }
.flabel { font-size: 11px; font-weight: 500; color: var(--muted); }
.finput, .fsel {
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text);
  font: 13px var(--sans); padding: 5px 8px;
  outline: none; transition: border-color .15s;
}
.finput:focus, .fsel:focus { border-color: var(--accent); }
/* Valori tecnici (path, ID numerici): aggiungere font-family: var(--mono) */
.finput.mono { font-family: var(--mono); font-size: 12px; }
```

### 6.3 Bottoni

```html
<!-- Primario: azione principale del blocco -->
<button class="btn btn-primary">▶ Esegui</button>

<!-- Secondario: azione alternativa -->
<button class="btn btn-secondary">■ Arresta</button>

<!-- Danger: azione distruttiva -->
<button class="btn btn-danger">✕ Elimina</button>

<!-- Ghost: azione leggera (es. toggle, expand) -->
<button class="btn btn-ghost">↗ Apri report</button>
```

```css
.btn {
  padding: 5px 14px; border-radius: 4px;
  font: 500 12px var(--sans); cursor: pointer;
  border: 1px solid transparent; transition: opacity .15s, background .15s;
}
.btn:hover { opacity: .85; }
.btn-primary   { background: var(--accent); color: #000; border-color: var(--accent); }
.btn-secondary { background: transparent; color: var(--accent); border-color: var(--accent); }
.btn-danger    { background: transparent; color: var(--er); border-color: var(--er); }
.btn-ghost     { background: transparent; color: var(--muted); border-color: transparent; }
.btn-ghost:hover { color: var(--text); }
```

### 6.4 Badge di stato (BlockStatusBadge)

```html
<span class="badge b-not">—</span>          <!-- NOT_STARTED -->
<span class="badge b-ready">READY</span>
<span class="badge b-run">RUNNING</span>
<span class="badge b-done">DONE</span>
<span class="badge b-warn">WARNING</span>
<span class="badge b-stale">STALE</span>
<span class="badge b-err">ERROR</span>
```

```css
.badge {
  font: 500 10px var(--mono); padding: 2px 7px;
  border-radius: 10px; letter-spacing: .04em;
  display: inline-flex; align-items: center; gap: 4px;
}
.b-not   { background: rgba(139,148,158,.1); color: var(--muted); }
.b-ready { background: rgba( 63,185, 80,.12); color: var(--ok); border: 1px solid rgba(63,185,80,.3); }
.b-run   { background: rgba( 88,166,255,.12); color: var(--accent); border: 1px solid rgba(88,166,255,.3);
           animation: pulse-badge 1.8s ease-in-out infinite; }
.b-done  { background: rgba( 63,185, 80,.18); color: var(--ok); border: 1px solid rgba(63,185,80,.4); }
.b-warn  { background: rgba(210,153, 34,.12); color: var(--wa); border: 1px solid rgba(210,153,34,.3); }
.b-stale { background: transparent; color: var(--wa);
           border: 1px dashed rgba(210,153,34,.5); }
.b-err   { background: rgba(248, 81, 73,.12); color: var(--er); border: 1px solid rgba(248,81,73,.3); }

@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50%       { opacity: .5; }
}
```

### 6.5 Chip path (monospace troncato)

```html
<span class="path-chip" title="/percorso/completo/del/file.db">
  .../file.db
</span>
```

```css
.path-chip {
  font-family: var(--mono); font-size: 11px;
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 4px; padding: 2px 8px; color: var(--text);
  max-width: 280px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  display: inline-block; vertical-align: middle;
  cursor: default;
}
```

### 6.6 Log Panel (terminale)

```html
<div class="log-wrap">
  <div class="log-hdr" onclick="toggleLog(this)">
    <span>▸ Log</span>
    <button class="btn btn-ghost" style="font-size:10px">Pulisci</button>
  </div>
  <div class="log-body">
    <div class="log-panel" id="log-output">
      <div class="log-line">[14:32:01] Connessione avviata...</div>
      <div class="log-line log-ok">[14:32:02] ✓ Autenticazione riuscita</div>
      <div class="log-line log-warn">[14:32:05] ⚠ Timeout reconnect, retry 1/3</div>
      <div class="log-line log-err">[14:32:09] ✗ Connessione rifiutata</div>
    </div>
  </div>
</div>
```

```css
.log-wrap { border-top: 1px solid var(--border); }
.log-hdr {
  padding: 8px 16px;
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; font-size: 11px; color: var(--muted);
  user-select: none;
}
.log-hdr:hover { color: var(--text); }
.log-body { display: block; } /* display:none quando collassato */
.log-panel {
  background: var(--log-bg);
  border-top: 1px solid var(--border);
  height: 200px; overflow-y: auto;
  padding: 8px 12px;
  font-family: var(--mono); font-size: 12px;
}
.log-line      { color: var(--log-g); line-height: 1.6; white-space: pre-wrap; }
.log-line.log-ok   { color: var(--ok); }
.log-line.log-warn { color: var(--wa); }
.log-line.log-err  { color: var(--er); }
```

**JS toggle:**
```js
function toggleLog(hdr) {
  const body = hdr.nextElementSibling;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  hdr.querySelector('span').textContent = open ? '▸ Log' : '▾ Log';
}
```

### 6.7 Sezione Advanced (collassabile con chevron)

```html
<div class="adv-wrap">
  <div class="adv-hdr" onclick="toggleAdv(this)">
    <span>▸ Impostazioni avanzate</span>
  </div>
  <div class="adv-body" style="display:none">
    <!-- contenuto avanzato -->
  </div>
</div>
```

```css
.adv-hdr {
  padding: 8px 16px;
  font-size: 11px; color: var(--muted);
  cursor: pointer; display: flex; align-items: center; gap: 6px;
  border-top: 1px solid var(--border);
  user-select: none;
}
.adv-hdr:hover { color: var(--text); }
.adv-body { padding: 0 16px 14px; }
```

### 6.8 Summary Cards (post-operazione)

```html
<div class="sum-grid">
  <div class="sum-card">
    <div class="sum-val">1 247</div>
    <div class="sum-key">Messaggi scaricati</div>
  </div>
  <div class="sum-card">
    <div class="sum-val ok">342</div>
    <div class="sum-key">Media inclusi</div>
  </div>
  <div class="sum-card sum-warn">
    <div class="sum-val wa">12</div>
    <div class="sum-key">Warning</div>
  </div>
</div>
```

```css
.sum-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; padding: 14px 16px; }
.sum-card {
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 4px; padding: 10px 12px; text-align: center;
}
.sum-val { font: 600 22px var(--mono); color: var(--text); }
.sum-val.ok { color: var(--ok); }
.sum-val.wa { color: var(--wa); }
.sum-val.er { color: var(--er); }
.sum-key { font-size: 10px; color: var(--muted); margin-top: 2px; text-transform: uppercase; letter-spacing: .04em; }
```

### 6.9 Toggle (checkbox stilizzata)

```html
<label class="toggle-wrap">
  <input type="checkbox" id="my-toggle">
  <span class="toggle-track"></span>
  <span class="toggle-label">Abilita opzione</span>
</label>
```

```css
.toggle-wrap { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.toggle-wrap input { display: none; }
.toggle-track {
  width: 32px; height: 18px; border-radius: 9px;
  background: var(--border); position: relative;
  transition: background .2s;
}
.toggle-track::after {
  content: ''; position: absolute;
  width: 12px; height: 12px; border-radius: 50%;
  background: var(--muted); top: 3px; left: 3px;
  transition: transform .2s, background .2s;
}
.toggle-wrap input:checked + .toggle-track { background: rgba(88,166,255,.3); }
.toggle-wrap input:checked + .toggle-track::after {
  transform: translateX(14px); background: var(--accent);
}
.toggle-label { font-size: 12px; color: var(--text); }
```

### 6.10 Multi-select dropdown (custom)

```html
<div class="ms-wrap" onclick="toggleMs('ms-policies')">
  <span id="ms-policies-lbl">original_chain, signal_only</span>
  <span style="color:var(--muted); font-size:10px">▼</span>
  <div class="ms-drop" id="ms-policies" style="display:none" onclick="event.stopPropagation()">
    <label class="ms-opt"><input type="checkbox" value="original_chain" checked> original_chain</label>
    <label class="ms-opt"><input type="checkbox" value="signal_only" checked> signal_only</label>
    <label class="ms-opt"><input type="checkbox" value="extended"> extended</label>
  </div>
</div>
```

```css
.ms-wrap {
  position: relative;
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 4px; padding: 5px 8px;
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; font: 12px var(--mono); color: var(--text);
  min-height: 30px;
}
.ms-drop {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 50;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 4px; padding: 6px;
}
.ms-opt {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 6px; border-radius: 3px;
  font-size: 12px; cursor: pointer; color: var(--text);
}
.ms-opt:hover { background: var(--surface-2); }
.ms-opt input { accent-color: var(--accent); }
```

### 6.11 Warning table compatta

```html
<table class="warn-table">
  <thead>
    <tr><th>MSG ID</th><th>Tipo warning</th><th>Dettaglio</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="mono">#1042</td>
      <td><span class="badge b-warn">MISSING_SL</span></td>
      <td>Stop loss assente nel segnale</td>
    </tr>
  </tbody>
</table>
```

```css
.warn-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.warn-table th {
  text-align: left; padding: 6px 12px;
  font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .06em; color: var(--muted);
  border-bottom: 1px solid var(--border);
}
.warn-table td { padding: 6px 12px; border-bottom: 1px solid rgba(48,54,61,.5); }
.warn-table tr:last-child td { border-bottom: none; }
.warn-table .mono { font-family: var(--mono); }
```

### 6.12 Results table (backtest)

```html
<table class="res-table">
  <thead>
    <tr>
      <th>Policy</th><th>Trades</th><th>Excl.</th>
      <th>PnL %</th><th>Win rate</th><th>Expectancy</th><th></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="mono">original_chain</td>
      <td class="mono">247</td>
      <td class="mono wa">12</td>
      <td class="mono ok">+18.4%</td>
      <td class="mono">62%</td>
      <td class="mono">0.74</td>
      <td><button class="btn btn-ghost" style="font-size:10px">📄 report</button></td>
    </tr>
  </tbody>
</table>
```

```css
/* Stessa base di .warn-table, aggiunte classi colore celle */
.res-table .ok { color: var(--ok); }
.res-table .wa { color: var(--wa); }
.res-table .er { color: var(--er); }
```

---

## 7. Patterns di interazione

### Sezioni collassabili
- **Regola:** tutte le sezioni advanced, log panel, e shared-context sono collassabili
- **Chevron:** `▸` chiuso → `▾` aperto (testo, no icone SVG)
- **Animazione:** nessuna — `display:none/block` è intenzionale, zero delay

### Campi condizionali
```js
// Mostra/nascondi in base a valore select
document.getElementById('mode-sel').addEventListener('change', function() {
  document.getElementById('extra-fields').style.display =
    this.value === 'manual' ? 'grid' : 'none';
});
```

### Focus ring
```css
*:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

### Scrollbar personalizzata
```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted); }
```

---

## 8. Scheletro HTML completo

```html
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Signal Chain Lab</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    /* incolla qui: CSS variables (sezione 2) + tutti i componenti (sezione 6) */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { font-size: 13px; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      min-height: 100vh;
    }
  </style>
</head>
<body>

  <!-- Nav fissa -->
  <nav class="nav">
    <div class="nav-inner">
      <span class="brand">SCL</span>
      <button class="tab active">Tab 1</button>
      <button class="tab">Tab 2</button>
      <div class="nav-r">
        <span class="badge b-not">—</span>
      </div>
    </div>
  </nav>

  <!-- Contenuto principale -->
  <main class="main">
    <div class="panel">

      <!-- Blocco -->
      <div class="card">
        <div class="card-hdr">
          <span class="card-title">Nome blocco</span>
          <span class="badge b-ready">READY</span>
        </div>
        <div class="fg">
          <!-- campi form -->
        </div>
        <div class="card-ftr">
          <button class="btn btn-primary">▶ Esegui</button>
          <button class="btn btn-secondary">■ Arresta</button>
        </div>
        <!-- log panel -->
        <div class="log-wrap">
          <div class="log-hdr" onclick="toggleLog(this)">
            <span>▸ Log</span>
          </div>
          <div class="log-body" style="display:none">
            <div class="log-panel"></div>
          </div>
        </div>
      </div>

    </div>
  </main>

  <script>
    function toggleLog(hdr) {
      const body = hdr.nextElementSibling;
      const open = body.style.display !== 'none';
      body.style.display = open ? 'none' : 'block';
      hdr.querySelector('span').textContent = open ? '▸ Log' : '▾ Log';
    }
    function toggleAdv(hdr) {
      const body = hdr.nextElementSibling;
      const open = body.style.display !== 'none';
      body.style.display = open ? 'none' : 'block';
      hdr.querySelector('span').textContent =
        open ? '▸ Impostazioni avanzate' : '▾ Impostazioni avanzate';
    }
  </script>
</body>
</html>
```

---

## 9. Trasposizione in NiceGUI (Python)

La GUI reale usa NiceGUI che wrappa Quasar/Vue.js. Corrispondenze principali:

| HTML/CSS pattern | NiceGUI equivalente |
|---|---|
| `.card` | `ui.card()` con `.classes('bg-[#161b22] border border-[#30363d]')` |
| `.finput` | `ui.input()` con `.classes('font-mono text-xs')` e `ui.colors(primary='#58a6ff')` |
| `.fsel` | `ui.select()` |
| `.btn-primary` | `ui.button().props('color=primary')` + colore accento in `ui.colors()` |
| `.log-panel` | `ui.log()` — già con `bg-slate-950 text-emerald-300` in `log_panel.py` |
| Collapsible | `ui.expansion()` con `.classes(...)` |
| Toggle | `ui.switch()` |
| Badge stato | `ui.badge()` con colori semantici o `ui.label()` stilizzata |
| Card summary | `ui.card()` innestata con `ui.label()` per valore + descrizione |
| Chip path | `ui.chip()` con `.classes('font-mono text-xs')` |

**Impostare la palette globale in NiceGUI:**
```python
# In app.py, prima di ui.run()
ui.colors(
    primary='#58a6ff',
    secondary='#30363d',
    accent='#3fb950',
    positive='#3fb950',
    negative='#f85149',
    warning='#d29922',
    info='#58a6ff',
    dark='#161b22',
)
```

**CSS globale iniettato:**
```python
ui.add_head_html("""
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --surface-2: #1c2128;
    --border: #30363d; --text: #e6edf3; --muted: #8b949e;
    --accent: #58a6ff; --ok: #3fb950; --wa: #d29922; --er: #f85149;
    --log-bg: #010409; --log-g: #39d353;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'IBM Plex Sans', system-ui, sans-serif;
  }
  body { font-family: var(--sans); }
  .q-card { background: var(--surface) !important; }
</style>
""")
```

---

## 10. Checklist per nuovi artefatti

Quando crei un nuovo componente, schermata o mockup con lo stesso stile:

- [ ] Background pagina `#0d1117`
- [ ] Card/pannelli `#161b22` con border `#30363d`
- [ ] Font IBM Plex Mono per valori tecnici (numeri, path, ticker, ID)
- [ ] Font IBM Plex Sans per tutto il resto
- [ ] Accent `#58a6ff` per primari e focus ring
- [ ] Nessun gradiente — colori piatti con lievi variazioni di opacità
- [ ] Titoli sezione in UPPERCASE 10px muted con letter-spacing
- [ ] Bottoni: primario filled, secondario outline, danger outline rosso
- [ ] Log panel: `#010409` bg, `#39d353` testo, altezza fissa 200px, collassabile
- [ ] Tutti i path come chip monospace troncati con tooltip
- [ ] Sezioni avanzate sempre collassabili con chevron `▸`/`▾`
- [ ] Scrollbar sottile (6px) personalizzata

---

## 11. Prompt di partenza per sessioni separate

Copia questo blocco come contesto iniziale in una nuova sessione Claude:

```
Stai lavorando su Signal Chain Lab, un tool Python con NiceGUI.
Stile visivo: CLI operator console, GitHub dark palette.

CSS variables da usare sempre:
--bg:#0d1117  --surface:#161b22  --surface-2:#1c2128
--border:#30363d  --text:#e6edf3  --muted:#8b949e
--accent:#58a6ff  --ok:#3fb950  --wa:#d29922  --er:#f85149
--log-bg:#010409  --log-g:#39d353

Font: IBM Plex Mono (valori tecnici/monospace) + IBM Plex Sans (UI)
Bottoni: primario=filled accent, secondario=outline accent, danger=outline rosso
Card: surface bg + border border + radius 6px
Log panel: log-bg, testo log-g, 200px, collassabile
Badge stati: NOT_STARTED(muted) READY(ok) RUNNING(accent+pulse) DONE(ok) WARNING(wa) STALE(wa dashed) ERROR(er)
Path: chip monospace troncato con tooltip
Sezioni avanzate: sempre collassabili con ▸/▾

Riferimento mockup: ui_mockup.html nella root del worktree.
```

---

*Versione: 1.0 — generato il 2026-04-19*
