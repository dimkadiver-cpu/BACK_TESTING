---
name: echarts-chart-builder
description: >
  Build interactive ECharts 5.x charts for the backtesting system (signal_chain_lab).
  Use this skill whenever the user asks to create, extend, or modify charts, graphs,
  or visualizations — including candlestick charts, equity curves, drawdown charts,
  return distributions, heatmaps, scatter plots, or any other chart type. Applies
  both when writing new Python generators and when extending existing HTML reports.
  Trigger even if the user just says "voglio un grafico", "add a chart", "visualizza
  i dati", or describes a chart type without explicitly mentioning ECharts.
---

# ECharts Chart Builder — signal_chain_lab

## Infrastruttura esistente

ECharts 5.x è già integrato nel progetto. Non installare nulla di nuovo.

```
src/signal_chain_lab/policy_report/
├── assets/echarts.min.js              ← libreria ECharts (1007KB, locale)
├── trade_chart_echarts.py             ← renderer candlestick per singolo trade
├── trade_chart_payload.py             ← builder JSON payload per candlestick
└── html_writer.py                     ← policy report con equity/drawdown/distribution
```

Il CDN non va usato: tutti i report usano il file locale. Percorso relativo dall'HTML generato:
- Da `policy_report/`: `assets/echarts.min.js`
- Da `policy_report/trades/`: `../../assets/echarts.min.js`

---

## Pattern fondamentale: Payload + Init separati

**Usa sempre questo pattern.** Separa i dati dal rendering per evitare conflitti con le f-string Python e le parentesi graffe JS.

```html
<!-- 1. Dati come JSON sicuro -->
<script type="application/json" id="my-chart-payload">
{"labels": ["Jan","Feb","Mar"], "values": [1.2, -0.5, 3.1]}
</script>

<!-- 2. Rendering separato -->
<div id="my-chart" style="width:100%;height:300px"></div>

<script>
(function () {
  var payload = JSON.parse(document.getElementById('my-chart-payload').textContent);
  var chart = echarts.init(document.getElementById('my-chart'), null, {renderer: 'canvas'});
  chart.setOption({
    animation: false,
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: payload.labels },
    yAxis: { type: 'value' },
    series: [{ type: 'line', data: payload.values }]
  });
  window.addEventListener('resize', function () { chart.resize(); });
})();
</script>
```

In Python, genera il JSON payload così (sicuro con f-string):
```python
import json

payload = {"labels": labels, "values": values}
payload_json = json.dumps(payload, ensure_ascii=False)

html = f"""
<script type="application/json" id="chart-payload">{payload_json}</script>
<div id="my-chart" style="width:100%;height:300px"></div>
<script>
(function () {{
  var payload = JSON.parse(document.getElementById('chart-payload').textContent);
  // ... chart init ...
}})();
</script>
"""
```

Le doppie graffe `{{` e `}}` nel blocco JS sono escape delle f-string.

---

## Palette colori standard

Usa questi colori per coerenza con i report esistenti:

```python
# Livelli di prezzo
LEVEL_COLORS = {
    'entries_planned': '#93c5fd',   # azzurro chiaro, dashed
    'entries_filled':  '#1d4ed8',   # blu solido
    'avg_entry':       '#0369a1',   # blu scuro
    'sl_initial':      '#fca5a5',   # rosso chiaro, dashed
    'sl_current':      '#b91c1c',   # rosso solido
    'tps':             '#15803d',   # verde dashed
    'exit':            '#7c3aed',   # viola solido
}

# Tipi di evento
EVENT_COLORS = {
    'FILL':          '#1d4ed8',
    'TP':            '#15803d',
    'SL':            '#b91c1c',
    'MOVE_SL':       '#c2410c',
    'BE':            '#f59e0b',
    'PARTIAL_CLOSE': '#7c3aed',
    'CLOSE':         '#7c3aed',
    'CANCEL':        '#64748b',
    'EXPIRED':       '#64748b',
    'TIMEOUT':       '#475569',
    'SYSTEM_NOTE':   '#94a3b8',
}

# CSS custom properties del tema HTML
CSS_THEME = """
--bg: #f8fafc;
--card: #ffffff;
--text: #0f172a;
--muted: #64748b;
--line: #e2e8f0;
--accent: #0f766e;
--blue: #1d4ed8;
--green: #15803d;
--red: #b91c1c;
"""
```

---

## Tipi di grafico — configurazioni pronte

### Candlestick con overlays

Il tipo principale del sistema. Dati: `[timestamp_ms, open, close, low, high]`  
**Nota ECharts:** l'ordine è `[open, close, low, high]`, non OHLC standard.

```javascript
series: [{
  type: 'candlestick',
  data: candleData,  // [[ts, open, close, low, high], ...]
  itemStyle: {
    color: '#15803d',        // bullish (close > open)
    color0: '#b91c1c',       // bearish
    borderColor: '#15803d',
    borderColor0: '#b91c1c'
  }
}]
```

Livelli di prezzo come markLine (non serie separate):
```javascript
{
  type: 'line',
  markLine: {
    silent: true,
    symbol: 'none',
    data: levels.map(lv => ({
      yAxis: lv.price,
      label: { formatter: lv.label, position: 'end' },
      lineStyle: { color: lv.color, type: 'dashed', width: 1 }
    }))
  }
}
```

Events (FILL, TP, SL, ecc.) come scatter sul candlestick:
```javascript
{
  type: 'scatter',
  coordinateSystem: 'cartesian2d',
  data: events.map(e => [e.ts, e.price]),
  symbolSize: 10,
  itemStyle: { color: (params) => EVENT_COLORS[params.data[2]] || '#94a3b8' },
  tooltip: {
    formatter: (params) => `${params.data[3]}<br/>${params.data[4]}`
  }
}
```

DataZoom per candlestick (sempre):
```javascript
dataZoom: [
  { type: 'inside', xAxisIndex: [0], filterMode: 'weakFilter' },
  { type: 'slider',  xAxisIndex: [0], height: 20, bottom: 5 }
]
```

### Equity curve

```javascript
{
  animation: false,
  tooltip: { trigger: 'axis', formatter: params => `Trade ${params[0].dataIndex + 1}<br/>${params[0].value.toFixed(2)}%` },
  grid: { top: 30, right: 20, bottom: 40, left: 60 },
  xAxis: { type: 'category', data: labels, axisLabel: { show: false } },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
  series: [{
    type: 'line',
    data: values,
    smooth: false,
    areaStyle: { opacity: 0.15 },
    lineStyle: { color: '#0f766e', width: 2 },
    itemStyle: { color: '#0f766e' }
  }]
}
```

### Drawdown

```javascript
series: [{
  type: 'line',
  data: drawdownValues,
  areaStyle: { color: '#fca5a5', opacity: 0.4 },
  lineStyle: { color: '#b91c1c', width: 1.5 },
  itemStyle: { color: '#b91c1c' }
}]
```

### Distribution histogram (return %)

```javascript
{
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: bucketLabels },
  yAxis: { type: 'value', name: 'Count' },
  series: [{
    type: 'bar',
    data: bucketCounts.map((v, i) => ({
      value: v,
      itemStyle: { color: midpoints[i] >= 0 ? '#15803d' : '#b91c1c' }
    }))
  }]
}
```

Calcolo bucket in Python:
```python
import math

def build_histogram(values: list[float], n_buckets: int = 20) -> dict:
    min_v, max_v = min(values), max(values)
    width = (max_v - min_v) / n_buckets
    buckets = [0] * n_buckets
    for v in values:
        idx = min(int((v - min_v) / width), n_buckets - 1)
        buckets[idx] += 1
    labels = [f"{min_v + i * width:.1f}%" for i in range(n_buckets)]
    mids = [min_v + (i + 0.5) * width for i in range(n_buckets)]
    return {"labels": labels, "counts": buckets, "midpoints": mids}
```

### Donut / Pie (close reason distribution)

```javascript
{
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { orient: 'vertical', right: 10 },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],
    data: items,  // [{name: 'TP_HIT', value: 42}, ...]
    label: { formatter: '{b}\n{d}%' }
  }]
}
```

### Heatmap mensile (P&L per mese × anno)

```javascript
{
  tooltip: { formatter: p => `${p.data[1]}/${p.data[0]}: ${p.data[2].toFixed(2)}%` },
  visualMap: {
    min: -10, max: 10,
    calculable: true,
    inRange: { color: ['#b91c1c', '#f8fafc', '#15803d'] }
  },
  xAxis: { type: 'category', data: months },   // ['Jan','Feb',...]
  yAxis: { type: 'category', data: years },
  series: [{
    type: 'heatmap',
    data: data,   // [[year_idx, month_idx, pnl_pct], ...]
    label: { show: true, formatter: p => p.data[2].toFixed(1) }
  }]
}
```

### Scatter MAE/MFE (efficienza entrata/uscita)

```javascript
{
  tooltip: { formatter: p => `${p.data[3]}<br/>MAE: ${p.data[0].toFixed(2)}%<br/>MFE: ${p.data[1].toFixed(2)}%<br/>R: ${p.data[2].toFixed(2)}` },
  xAxis: { name: 'MAE %', type: 'value' },
  yAxis: { name: 'MFE %', type: 'value' },
  series: [{
    type: 'scatter',
    data: trades.map(t => [t.mae_pct, t.mfe_pct, t.r_multiple, t.signal_id]),
    symbolSize: 8,
    itemStyle: { color: p => p.data[2] >= 0 ? '#15803d' : '#b91c1c', opacity: 0.7 }
  }]
}
```

---

## Multi-panel layout (grid multipli)

Per candlestick + volume su pannelli separati:

```javascript
grid: [
  { top: '5%',  height: '55%', left: 70, right: 20 },   // main chart
  { top: '65%', height: '15%', left: 70, right: 20 },   // volume
  { top: '82%', height: '12%', left: 70, right: 20 }    // event rail
],
xAxis: [
  { gridIndex: 0, type: 'time' },
  { gridIndex: 1, type: 'time' },
  { gridIndex: 2, type: 'time' }
],
yAxis: [
  { gridIndex: 0, scale: true },
  { gridIndex: 1, name: 'Vol' },
  { gridIndex: 2, name: 'Events', show: false }
],
dataZoom: [
  { xAxisIndex: [0, 1, 2], type: 'inside' },
  { xAxisIndex: [0, 1, 2], type: 'slider', bottom: 0, height: 20 }
]
```

---

## Visibility toggles

Pattern già usato in `trade_chart_echarts.py` — stato centralizzato + rebuild option:

```javascript
var vis = {
  entries: true,
  sl: true,
  tps: true,
  volume: false,
  posSize: false
};

function buildSeries() {
  var s = [mainCandleSeries];
  if (vis.entries) s.push(entriesMarkLineSeries);
  if (vis.sl)      s.push(slMarkLineSeries);
  if (vis.tps)     s.push(tpsMarkLineSeries);
  if (vis.volume)  s.push(volumeBarSeries);
  return s;
}

function redraw() { chart.setOption({ series: buildSeries() }, { replaceMerge: ['series'] }); }

document.querySelectorAll('[data-toggle]').forEach(btn => {
  btn.addEventListener('click', function() {
    var key = this.dataset.toggle;
    vis[key] = !vis[key];
    this.classList.toggle('active', vis[key]);
    redraw();
  });
});
```

---

## Fonti dati disponibili

### TradeResult (da CSV)
File: `artifacts/<run>/trade_results.csv`  
Campi chiave: `signal_id`, `symbol`, `side`, `trade_return_pct_net`, `r_multiple`,
`mae_pct`, `mfe_pct`, `capture_ratio_pct`, `created_at`, `closed_at`,
`cum_equity_after_trade_pct`, `close_reason`, `initial_r_pct`

```python
import csv
from pathlib import Path

def load_trade_results(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))
```

### EventLogEntry (da JSON-L)
File: `artifacts/<run>/event_log.jsonl`  
Campi: `timestamp`, `signal_id`, `event_type`, `price_reference`,
`state_before`, `state_after`

```python
import json

def load_event_log(path: Path) -> list[dict]:
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]
```

### Payload candlestick
Costruito da `trade_chart_payload.build_trade_chart_payload()` — restituisce dict con
`candles_by_timeframe`, `levels`, `events`, `meta`, `position_size_series`, `realized_pnl_series`.

---

## Struttura file Python consigliata

Per un nuovo tipo di grafico, crea un modulo in `policy_report/`:

```python
# src/signal_chain_lab/policy_report/mae_mfe_chart.py
from __future__ import annotations
import json
from pathlib import Path


def build_mae_mfe_payload(trade_results: list[dict]) -> dict:
    """Prepara i dati per lo scatter MAE/MFE."""
    return {
        "trades": [
            [float(t["mae_pct"]), float(t["mfe_pct"]),
             float(t["r_multiple"]), t["signal_id"]]
            for t in trade_results
            if t["mae_pct"] and t["mfe_pct"]
        ]
    }


def render_mae_mfe_chart(trade_results: list[dict], chart_id: str = "chart-mae-mfe") -> str:
    """Restituisce HTML string con il chart embedded."""
    payload = build_mae_mfe_payload(trade_results)
    payload_json = json.dumps(payload, ensure_ascii=False)

    return f"""
<script type="application/json" id="{chart_id}-payload">{payload_json}</script>
<div id="{chart_id}" style="width:100%;height:360px"></div>
<script>
(function () {{
  var payload = JSON.parse(document.getElementById('{chart_id}-payload').textContent);
  var chart = echarts.init(document.getElementById('{chart_id}'), null, {{renderer: 'canvas'}});
  chart.setOption({{
    animation: false,
    tooltip: {{
      formatter: function(p) {{
        return p.data[3] + '<br/>MAE: ' + p.data[0].toFixed(2) + '%<br/>MFE: ' + p.data[1].toFixed(2) + '%<br/>R: ' + p.data[2].toFixed(2);
      }}
    }},
    xAxis: {{ name: 'MAE %', type: 'value', nameLocation: 'end' }},
    yAxis: {{ name: 'MFE %', type: 'value', nameLocation: 'end' }},
    series: [{{
      type: 'scatter',
      data: payload.trades,
      symbolSize: 8,
      itemStyle: {{
        color: function(p) {{ return p.data[2] >= 0 ? '#15803d' : '#b91c1c'; }},
        opacity: 0.7
      }}
    }}]
  }});
  window.addEventListener('resize', function () {{ chart.resize(); }});
}})();
</script>
"""
```

---

## Checklist prima di consegnare un chart

- [ ] ECharts caricato da `assets/echarts.min.js` (percorso relativo corretto)
- [ ] Payload separato dal rendering (pattern `<script type="application/json">`)
- [ ] `animation: false` (performance su dataset grandi)
- [ ] `window.addEventListener('resize', ...)` per responsività
- [ ] `renderer: 'canvas'` nell'init (non SVG, per performance)
- [ ] Tooltip attivo con formatter descrittivo
- [ ] Colori dalla palette standard del progetto
- [ ] Timestamps come epoch-ms (non stringhe ISO) per assi temporali
- [ ] DataZoom per candlestick e serie temporali lunghe
