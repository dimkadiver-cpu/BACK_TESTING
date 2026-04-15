---
name: echarts-from-prd
description: >
  Generate complete, interactive ECharts 5.x charts from a PRD, specification, or
  natural language description. Use this skill whenever the user describes a chart,
  dashboard, or visualization they want — even vaguely ("show me X as a chart",
  "visualizza Y", "crea un grafico per Z", "voglio una dashboard con...", "make a
  chart that shows..."). Produces a standalone HTML file with embedded ECharts, no
  build tools or dependencies required. Covers all chart types: line, bar, candlestick,
  scatter, pie/donut, heatmap, radar, gauge, treemap, sankey, and mixed layouts.
  Trigger also when the user pastes a PRD section, a spec, or a table of data and
  asks to visualize it.
---

# ECharts from PRD

Generate interactive charts from any description or spec. Output: a standalone HTML
file that opens in any browser, no server or build step needed.

---

## Step 1 — Parse the PRD

Before writing any code, extract these answers from the description:

| Question | What to look for |
|---|---|
| **Chart type(s)** | line, bar, candlestick, scatter, pie, donut, heatmap, radar, gauge, treemap, funnel, sankey, mixed |
| **Data shape** | axes names, series names, numeric ranges, time axis vs category |
| **Interactivity** | tooltip, zoom, brush, legend toggle, click events, drill-down |
| **Layout** | single chart vs multi-panel, sidebar, tabs, responsive breakpoints |
| **Data source** | inline in prompt, CSV/JSON file, API, or placeholder/sample |
| **Style** | dark/light theme, color palette, branding |

If the PRD is ambiguous on chart type or data shape, pick the most natural fit and
note your assumption in a comment at the top of the generated HTML.

---

## Step 2 — Choose the right chart type

| Data pattern | Best type |
|---|---|
| Trend over time (continuous) | `line` with `xAxis.type: 'time'` |
| Comparison between categories | `bar` (vertical) or horizontal bar |
| OHLCV financial data | `candlestick` + volume bar (multi-grid) |
| Two numeric variables | `scatter` |
| Part-of-whole | `pie` / `radius: ['40%','70%']` for donut |
| Magnitude × 2 dimensions | `heatmap` + `visualMap` |
| Multi-metric profile | `radar` |
| Hierarchical proportions | `treemap` |
| Flow between nodes | `sankey` |
| Single KPI 0–100 | `gauge` |
| Mixed (e.g. line + bar) | multiple series, same grid |

For **financial / trading** data always use candlestick. For **time series with events**
overlay scatter markers on top of the line/candlestick.

---

## Step 3 — Generate the HTML file

Produce a **single self-contained HTML file**. Structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title><!-- chart title from PRD --></title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <style>
    /* --- reset + theme --- */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f8fafc; color: #0f172a; padding: 24px; }
    h1 { font-size: 1.25rem; font-weight: 600; margin-bottom: 4px; }
    .subtitle { font-size: 0.875rem; color: #64748b; margin-bottom: 24px; }
    .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
    .chart-wrap { width: 100%; }
    /* grid for multi-chart layouts */
    .charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; }
  </style>
</head>
<body>

  <h1><!-- title --></h1>
  <p class="subtitle"><!-- subtitle / description --></p>

  <!-- chart containers here -->

  <!-- data payload (safe: no brace conflicts) -->
  <script type="application/json" id="chart-data">
  { /* JSON data */ }
  </script>

  <!-- chart init -->
  <script>
  (function () {
    var data = JSON.parse(document.getElementById('chart-data').textContent);
    // ... chart logic ...
  })();
  </script>

</body>
</html>
```

**CDN vs local:** use the CDN (`cdn.jsdelivr.net/npm/echarts@5`) for standalone files.
If the user specifies a local asset path, use that instead.

---

## Step 4 — ECharts patterns by chart type

### Line / Area

```javascript
{
  animation: true,
  tooltip: { trigger: 'axis' },
  legend: { top: 8 },
  grid: { top: 50, right: 20, bottom: 50, left: 60 },
  xAxis: {
    type: 'time',          // or 'category' if labels are strings
    boundaryGap: false
  },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}' } },
  dataZoom: [
    { type: 'inside' },
    { type: 'slider', bottom: 8, height: 20 }
  ],
  series: [{
    name: 'Series A',
    type: 'line',
    smooth: false,
    data: data.points,     // [[timestamp_ms, value], ...] for time axis
    areaStyle: { opacity: 0.12 },
    lineStyle: { width: 2 }
  }]
}
```

### Bar (vertical / horizontal)

```javascript
// Vertical
{
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: { type: 'category', data: data.labels },
  yAxis: { type: 'value' },
  series: [{
    type: 'bar',
    data: data.values,
    // color per bar (positive/negative):
    itemStyle: { color: p => p.value >= 0 ? '#15803d' : '#b91c1c' }
  }]
}

// Horizontal — swap xAxis/yAxis:
// xAxis: { type: 'value' }
// yAxis: { type: 'category', data: labels }
```

### Candlestick + Volume (financial)

```javascript
// Data format: [timestamp_ms, open, close, low, high]
// NOTE: ECharts order is open/close/low/high (not standard OHLC)
{
  animation: false,
  tooltip: {
    trigger: 'axis', axisPointer: { type: 'cross' },
    formatter: function(params) {
      var c = params[0];
      return `${new Date(c.axisValue).toLocaleDateString()}<br/>
              O: ${c.data[1]}  H: ${c.data[4]}  L: ${c.data[3]}  C: ${c.data[2]}`;
    }
  },
  grid: [
    { top: '5%', height: '62%', left: 70, right: 20 },
    { top: '72%', height: '18%', left: 70, right: 20 }
  ],
  xAxis: [
    { type: 'time', gridIndex: 0, scale: true },
    { type: 'time', gridIndex: 1, scale: true }
  ],
  yAxis: [
    { gridIndex: 0, scale: true, splitArea: { show: true } },
    { gridIndex: 1, name: 'Vol', splitLine: { show: false } }
  ],
  dataZoom: [
    { type: 'inside', xAxisIndex: [0, 1] },
    { type: 'slider',  xAxisIndex: [0, 1], bottom: 4, height: 20 }
  ],
  series: [
    {
      type: 'candlestick',
      xAxisIndex: 0, yAxisIndex: 0,
      data: data.candles,
      itemStyle: {
        color: '#15803d', color0: '#b91c1c',
        borderColor: '#15803d', borderColor0: '#b91c1c'
      }
    },
    {
      type: 'bar',
      xAxisIndex: 1, yAxisIndex: 1,
      data: data.volume,
      itemStyle: { color: '#94a3b8' }
    }
  ]
}
```

### Scatter

```javascript
{
  tooltip: {
    formatter: p => `${p.data[2]}<br/>X: ${p.data[0]}<br/>Y: ${p.data[1]}`
  },
  xAxis: { type: 'value', name: data.xLabel, scale: true },
  yAxis: { type: 'value', name: data.yLabel, scale: true },
  series: [{
    type: 'scatter',
    data: data.points,    // [[x, y, label], ...]
    symbolSize: function(v) { return v[3] ? v[3] : 8; },  // optional size dim
    itemStyle: { opacity: 0.75 }
  }]
}
```

### Pie / Donut

```javascript
{
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { orient: 'vertical', right: '5%', top: 'center' },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],   // remove inner radius for pie (not donut)
    center: ['40%', '50%'],
    data: data.items,          // [{name, value}, ...]
    label: { formatter: '{b}\n{d}%' },
    emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' } }
  }]
}
```

### Heatmap

```javascript
{
  tooltip: { formatter: p => `${p.data[0]} / ${p.data[1]}: ${p.data[2]}` },
  grid: { top: 30, right: 80, bottom: 60, left: 60 },
  xAxis: { type: 'category', data: data.xLabels, splitArea: { show: true } },
  yAxis: { type: 'category', data: data.yLabels, splitArea: { show: true } },
  visualMap: {
    min: data.min, max: data.max,
    calculable: true, orient: 'vertical', right: 0, top: 'center',
    inRange: { color: ['#b91c1c', '#f8fafc', '#15803d'] }
  },
  series: [{
    type: 'heatmap',
    data: data.cells,    // [[xi, yi, value], ...]
    label: { show: true, formatter: p => p.data[2].toFixed(1) }
  }]
}
```

### Radar

```javascript
{
  tooltip: {},
  radar: {
    indicator: data.axes.map(a => ({ name: a.name, max: a.max })),
    shape: 'circle'
  },
  series: [{
    type: 'radar',
    data: data.series.map(s => ({
      name: s.name,
      value: s.values,
      areaStyle: { opacity: 0.15 }
    }))
  }]
}
```

### Gauge

```javascript
{
  series: [{
    type: 'gauge',
    startAngle: 200, endAngle: -20,
    min: 0, max: 100,
    radius: '80%',
    pointer: { length: '60%', width: 6 },
    progress: { show: true, width: 14 },
    detail: { formatter: '{value}%', fontSize: 28, offsetCenter: [0, '30%'] },
    data: [{ value: data.value, name: data.label }]
  }]
}
```

---

## Step 5 — Interactivity standard

Always include unless the PRD says static:

```javascript
// 1. Resize handler (every chart)
window.addEventListener('resize', function () { chart.resize(); });

// 2. Legend toggle — free, built-in (just set legend: {})

// 3. Tooltip on all charts
tooltip: { trigger: 'axis' }   // for line/bar
tooltip: { trigger: 'item' }   // for pie/scatter

// 4. DataZoom for time series and candlestick (always)
dataZoom: [{ type: 'inside' }, { type: 'slider' }]

// 5. Toolbox (download PNG, zoom, restore) — optional but useful
toolbox: {
  feature: {
    saveAsImage: { title: 'Save PNG' },
    dataZoom: {},
    restore: {}
  }
}
```

---

## Step 6 — Sample / placeholder data

If the PRD has no real data, generate realistic placeholder data that matches the
domain. Label it clearly:

```html
<!-- NOTE: using sample data — replace with real data source -->
<script type="application/json" id="chart-data">
{ "note": "sample data", ... }
</script>
```

Rules for good sample data:
- Use realistic scales (stock prices ~100–200, percentages –20 to +30, counts 0–1000)
- Time axis: generate last 90 days from today using `Date.now()`
- At least 30 points for line/scatter, 8–12 for bar/pie
- Include some variation (not all same value)

```javascript
// Helper: generate N days of sample time-series
function sampleTimeSeries(n, startValue, volatility) {
  var result = [], v = startValue, now = Date.now();
  for (var i = n; i >= 0; i--) {
    result.push([now - i * 86400000, parseFloat(v.toFixed(2))]);
    v += (Math.random() - 0.48) * volatility;
  }
  return result;
}
```

---

## Step 7 — Multi-chart dashboard layout

For dashboards with multiple charts:

```html
<div class="dashboard">
  <div class="chart-full">         <!-- full width -->
    <div class="card">
      <h3>Main Chart</h3>
      <div id="chart-main" style="height:360px"></div>
    </div>
  </div>
  <div class="charts-grid">        <!-- 2-column grid -->
    <div class="card">
      <h3>Chart A</h3>
      <div id="chart-a" style="height:260px"></div>
    </div>
    <div class="card">
      <h3>Chart B</h3>
      <div id="chart-b" style="height:260px"></div>
    </div>
  </div>
</div>

<style>
.chart-full { margin-bottom: 16px; }
.charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; }
@media (max-width: 700px) { .charts-grid { grid-template-columns: 1fr; } }
</style>
```

Initialize all charts then batch-resize:
```javascript
var allCharts = [chartMain, chartA, chartB];
window.addEventListener('resize', function () { allCharts.forEach(c => c.resize()); });
```

---

## Output checklist

Before delivering the file:

- [ ] Single `.html` file, opens in browser without any server
- [ ] ECharts loaded via CDN (or local path if specified)
- [ ] `animation: false` on heavy datasets (>500 points), `true` otherwise
- [ ] Tooltip active on every chart
- [ ] Resize handler on every chart
- [ ] DataZoom on every time series or candlestick
- [ ] Assumptions about ambiguous PRD items commented at top of file
- [ ] Placeholder data labelled as such if real data not provided
- [ ] File saved as `<descriptive-name>.html` in the working directory

---

## Quick reference — chart type selector

```
PRD says "trend / over time"         → line
PRD says "compare categories"        → bar
PRD says "OHLC / price / candles"    → candlestick
PRD says "distribution / histogram"  → bar with bucketed data
PRD says "correlation / two vars"    → scatter
PRD says "share / proportion / %"    → pie or donut
PRD says "matrix / intensity"        → heatmap
PRD says "profile / spider / radar"  → radar
PRD says "KPI / single number"       → gauge
PRD says "hierarchy / tree"          → treemap
PRD says "flow / pipeline"           → sankey
PRD says "multiple KPIs"             → dashboard (multi-chart layout)
```
