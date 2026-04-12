"""Render an ECharts candlestick chart from a trade chart payload dict."""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# JavaScript template — %%CHART_ID%% is replaced at render time.
# Written as a raw string to avoid f-string / JS brace conflicts.
# ---------------------------------------------------------------------------
_CHART_JS = r"""
(function () {
  'use strict';
  var chartEl  = document.getElementById('%%CHART_ID%%');
  var payloadEl = document.getElementById('%%CHART_ID%%_payload');
  if (!chartEl || !payloadEl) { return; }

  var payload   = JSON.parse(payloadEl.textContent || '{}');
  var candlesByTF   = payload.candles_by_timeframe || {};
  var levels        = payload.levels  || {entries: [], sl: [], tps: [], exit: []};
  var events        = payload.events  || [];
  var meta          = payload.meta    || {};
  var posSizePts    = payload.position_size_series  || [];
  var realizedPnlPts = payload.realized_pnl_series  || [];
  var currentTF     = meta.default_timeframe || Object.keys(candlesByTF)[0] || '';

  var chart = echarts.init(chartEl, null, {renderer: 'canvas'});

  // ---- colour palette per event kind ----------------------------------------
  var KIND_COLOR = {
    'FILL':          '#1d4ed8',   // blue
    'TP':            '#15803d',   // green
    'SL':            '#b91c1c',   // red
    'MOVE_SL':       '#c2410c',   // orange
    'PARTIAL_CLOSE': '#7c3aed',   // purple
    'CLOSE':         '#7c3aed',   // purple
    'CANCEL':        '#64748b'    // slate
  };
  var KIND_SYMBOL = {
    'FILL':          'circle',
    'TP':            'diamond',
    'SL':            'triangle',
    'MOVE_SL':       'rect',
    'PARTIAL_CLOSE': 'roundRect',
    'CLOSE':         'diamond',
    'CANCEL':        'triangle'
  };
  function kindColor(k)  { return KIND_COLOR[k]  || '#f59e0b'; }
  function kindSymbol(k) { return KIND_SYMBOL[k] || 'circle'; }

  // ---- series visibility state ----------------------------------------------
  var visibility = {
    levels:       true,
    events:       true,
    volume:       false,
    pos_size:     false,
    realized_pnl: false
  };

  // ---- data builders -------------------------------------------------------
  function buildCandleData(tf) {
    return (candlesByTF[tf] || []).map(function (c) {
      return [c[0], c[1], c[2], c[3], c[4]];
    });
  }
  function buildVolumeData(tf) {
    return (candlesByTF[tf] || []).map(function (c) {
      return [c[0], c[5] || 0, c[2] >= c[1] ? 1 : -1];
    });
  }
  function buildMarkLineData(levelList) {
    return (levelList || []).map(function (l) {
      return {yAxis: l.price, name: l.label};
    });
  }
  function buildScatterData() {
    return (events || []).map(function (e) {
      return {
        value:  [e.ts, e.price],
        name:   e.label || e.kind,
        kind:   e.kind,
        itemStyle: {
          color:       kindColor(e.kind),
          borderColor: '#ffffff',
          borderWidth: 1.5
        },
        symbol: kindSymbol(e.kind)
      };
    });
  }
  function buildStepData(pts) {
    return pts.map(function (p) { return [p[0], p[1]]; });
  }

  // ---- build full option ---------------------------------------------------
  function buildOption(tf) {
    var showLevels = visibility.levels;
    var showEvents = visibility.events;
    var showVol    = visibility.volume;
    var showPS     = visibility.pos_size;
    var showPnl    = visibility.realized_pnl;

    // Grids: main | optional bottom bar for volume
    var mainGridBottom = showVol ? 150 : 80;
    var grids = [
      {left: 80, right: 24, top: 56, bottom: mainGridBottom}
    ];
    var xAxes = [
      {type: 'time', scale: true, gridIndex: 0,
       axisLine: {lineStyle: {color: '#cbd5e1'}}, splitLine: {show: false}}
    ];
    var yAxes = [
      // main price axis
      {type: 'value', scale: true, gridIndex: 0, position: 'left',
       axisLine: {show: false}, splitLine: {lineStyle: {color: '#f1f5f9'}}},
      // secondary: position size / realized PnL (hidden labels if both off)
      {type: 'value', scale: true, gridIndex: 0, position: 'right',
       axisLine: {show: false}, splitLine: {show: false},
       axisLabel: {color: '#94a3b8', fontSize: 10},
       show: showPS || showPnl}
    ];

    if (showVol) {
      grids.push({left: 80, right: 24, top: 'auto', bottom: 40, height: 60});
      xAxes.push({type: 'time', scale: true, gridIndex: 1,
                  axisLine: {lineStyle: {color: '#cbd5e1'}}, splitLine: {show: false},
                  axisLabel: {show: false}});
      yAxes.push({type: 'value', scale: true, gridIndex: 1, position: 'left',
                  axisLabel: {show: false}, splitLine: {show: false}});
    }

    // scatter per-point symbol via callback
    var scatterData = buildScatterData();

    var series = [
      // ---- candlestick ----
      {
        id: 'candles', name: 'Candles', type: 'candlestick',
        data: buildCandleData(tf), barMaxWidth: 20,
        xAxisIndex: 0, yAxisIndex: 0,
        itemStyle: {
          color: '#15803d', color0: '#b91c1c',
          borderColor: '#15803d', borderColor0: '#b91c1c'
        }
      },
      // ---- levels (markLines) ----
      {
        id: 'entries', name: 'Entries', type: 'line', data: [],
        xAxisIndex: 0, yAxisIndex: 0, silent: true,
        markLine: !showLevels ? {} : {
          symbol: ['none', 'none'],
          lineStyle: {color: '#2563eb', type: 'dashed', width: 1.5},
          label: {formatter: '{b}  {c}', color: '#2563eb', fontSize: 11},
          data: buildMarkLineData(levels.entries)
        }
      },
      {
        id: 'sl_be', name: 'SL/BE', type: 'line', data: [],
        xAxisIndex: 0, yAxisIndex: 0, silent: true,
        markLine: !showLevels ? {} : {
          symbol: ['none', 'none'],
          lineStyle: {color: '#b91c1c', type: 'dashed', width: 1.5},
          label: {formatter: '{b}  {c}', color: '#b91c1c', fontSize: 11},
          data: buildMarkLineData(levels.sl)
        }
      },
      {
        id: 'tps', name: 'TPs', type: 'line', data: [],
        xAxisIndex: 0, yAxisIndex: 0, silent: true,
        markLine: !showLevels ? {} : {
          symbol: ['none', 'none'],
          lineStyle: {color: '#15803d', type: 'dashed', width: 1.5},
          label: {formatter: '{b}  {c}', color: '#15803d', fontSize: 11},
          data: buildMarkLineData(levels.tps)
        }
      },
      {
        id: 'exit', name: 'Exit', type: 'line', data: [],
        xAxisIndex: 0, yAxisIndex: 0, silent: true,
        markLine: !showLevels ? {} : {
          symbol: ['none', 'none'],
          lineStyle: {color: '#7c3aed', type: 'solid', width: 2},
          label: {formatter: '{b}  {c}', color: '#7c3aed', fontSize: 11},
          data: buildMarkLineData(levels.exit)
        }
      },
      // ---- events (scatter) ----
      {
        id: 'events', name: 'Events', type: 'scatter',
        data: showEvents ? scatterData : [],
        xAxisIndex: 0, yAxisIndex: 0,
        symbolSize: 11, z: 5,
        label: {
          show: showEvents, position: 'top',
          formatter: function (p) { return p.name; },
          fontSize: 10, color: '#0f172a'
        }
      },
      // ---- position size step line ----
      {
        id: 'pos_size', name: 'Position Size', type: 'line',
        data: showPS ? buildStepData(posSizePts) : [],
        xAxisIndex: 0, yAxisIndex: 1,
        step: 'end',
        symbol: 'none',
        lineStyle: {color: '#0284c7', width: 1.5, type: 'solid', opacity: 0.8},
        areaStyle: {color: 'rgba(2,132,199,.08)'},
        z: 2
      },
      // ---- realized PnL step line ----
      {
        id: 'realized_pnl', name: 'Realized PnL', type: 'line',
        data: showPnl ? buildStepData(realizedPnlPts) : [],
        xAxisIndex: 0, yAxisIndex: 1,
        step: 'end',
        symbol: 'none',
        lineStyle: {color: '#f59e0b', width: 1.5, type: 'solid', opacity: 0.9},
        z: 2
      }
    ];

    // ---- volume bar (optional grid) ----
    if (showVol) {
      series.push({
        id: 'volume', name: 'Volume', type: 'bar',
        data: buildVolumeData(tf),
        xAxisIndex: 1, yAxisIndex: 2,
        barMaxWidth: 20,
        itemStyle: {
          color: function (p) { return p.data[2] >= 0 ? 'rgba(21,128,61,.5)' : 'rgba(185,28,28,.5)'; }
        }
      });
    }

    return {
      animation: false,
      backgroundColor: '#ffffff',
      tooltip: {
        trigger: 'axis', axisPointer: {type: 'cross'},
        formatter: function (params) {
          var lines = [];
          for (var i = 0; i < params.length; i++) {
            var p = params[i];
            if (p.seriesType === 'candlestick' && p.data) {
              var d = p.data;
              lines.push('<b>' + echarts.format.formatTime('yyyy-MM-dd hh:mm', d[0]) + '</b>');
              lines.push('O:&nbsp;' + (+d[1]).toFixed(6) + '&ensp;C:&nbsp;' + (+d[2]).toFixed(6));
              lines.push('L:&nbsp;' + (+d[3]).toFixed(6) + '&ensp;H:&nbsp;' + (+d[4]).toFixed(6));
            } else if (p.seriesType === 'scatter' && p.data) {
              lines.push('<span style="color:' + p.color + '">&#9679;</span>&nbsp;' +
                p.name + '&nbsp;@&nbsp;' + (+p.data.value[1]).toFixed(6));
            } else if (p.seriesType === 'line' && p.data) {
              lines.push('<span style="color:' + p.color + '">&#9644;</span>&nbsp;' +
                p.seriesName + ':&nbsp;<b>' + (+p.data[1]).toFixed(4) + '</b>');
            }
          }
          return lines.join('<br/>');
        }
      },
      legend: {
        top: 6, itemGap: 14,
        data: [
          {name: 'Candles'},
          {name: 'Entries',       icon: 'line'},
          {name: 'SL/BE',         icon: 'line'},
          {name: 'TPs',           icon: 'line'},
          {name: 'Exit',          icon: 'line'},
          {name: 'Events',        icon: 'circle'},
          {name: 'Position Size', icon: 'line'},
          {name: 'Realized PnL',  icon: 'line'}
        ]
      },
      grid:  grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        {type: 'inside',  xAxisIndex: showVol ? [0,1] : [0], filterMode: 'weakFilter'},
        {type: 'slider',  xAxisIndex: showVol ? [0,1] : [0], bottom: 8, height: 28,
         borderColor: '#e2e8f0'}
      ],
      series: series
    };
  }

  // ---- initial render -------------------------------------------------------
  chart.setOption(buildOption(currentTF));

  // ---- timeframe switch -----------------------------------------------------
  function setTF(tf) {
    if (!(tf in candlesByTF)) { return; }
    currentTF = tf;
    chart.setOption({series: [{id: 'candles', data: buildCandleData(tf)}]});
    document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-tf') === tf);
    });
  }
  document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
    btn.addEventListener('click', function () { setTF(btn.getAttribute('data-tf')); });
  });

  // ---- reset zoom -----------------------------------------------------------
  var resetBtn = document.getElementById('%%CHART_ID%%-reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      chart.dispatchAction({type: 'dataZoom', start: 0, end: 100});
    });
  }

  // ---- toggle buttons -------------------------------------------------------
  function rebuildChart() {
    chart.setOption(buildOption(currentTF), {replaceMerge: ['series', 'grid', 'xAxis', 'yAxis']});
  }
  function wireToggle(btnId, key) {
    var btn = document.getElementById('%%CHART_ID%%-' + btnId);
    if (!btn) { return; }
    // initialise visual state
    btn.classList.toggle('active', visibility[key]);
    btn.addEventListener('click', function () {
      visibility[key] = !visibility[key];
      btn.classList.toggle('active', visibility[key]);
      rebuildChart();
    });
  }
  wireToggle('toggle-levels',   'levels');
  wireToggle('toggle-events',   'events');
  wireToggle('toggle-volume',   'volume');
  wireToggle('toggle-pos-size', 'pos_size');
  wireToggle('toggle-pnl',      'realized_pnl');

  // ---- resize ---------------------------------------------------------------
  window.addEventListener('resize', function () { chart.resize(); });
}());
"""


def _build_tf_buttons(chart_id: str, timeframes: list[str], default_tf: str | None) -> str:
    buttons: list[str] = []
    for tf in timeframes:
        active = "active" if tf == default_tf else ""
        buttons.append(
            f"<button type='button' class='chart-toolbar-btn {chart_id}-tf {active}' data-tf='{tf}'>{tf}</button>"
        )
    return "".join(buttons)


def _build_toggle_buttons(chart_id: str) -> str:
    toggles = [
        ("toggle-levels",   "Levels",    True),
        ("toggle-events",   "Events",    True),
        ("toggle-volume",   "Volume",    False),
        ("toggle-pos-size", "Pos Size",  False),
        ("toggle-pnl",      "Realized PnL", False),
    ]
    parts: list[str] = []
    for key, label, default_on in toggles:
        active_cls = "active" if default_on else ""
        parts.append(
            f"<button id='{chart_id}-{key}' class='chart-toolbar-btn {active_cls}' title='Toggle {label}'>{label}</button>"
        )
    return "".join(parts)


def _build_fallback(payload: dict[str, object]) -> str:
    levels = payload.get("levels") or {}
    events = payload.get("events") or []

    rows_levels: list[str] = []
    for group_name, group_key in [("Entries", "entries"), ("SL/BE", "sl"), ("TPs", "tps"), ("Exit", "exit")]:
        for item in (levels.get(group_key) or []):
            rows_levels.append(
                f"<tr><td>{group_name}</td><td>{item.get('label', '')}</td>"
                f"<td>{item.get('price', '')}</td></tr>"
            )

    rows_events: list[str] = []
    for ev in events:
        rows_events.append(
            f"<tr><td>{ev.get('kind', '')}</td><td>{ev.get('label', '')}</td>"
            f"<td>{ev.get('price', '')}</td></tr>"
        )

    levels_table = (
        "<table><thead><tr><th>Group</th><th>Label</th><th>Price</th></tr></thead>"
        f"<tbody>{''.join(rows_levels) or '<tr><td colspan=3>—</td></tr>'}</tbody></table>"
    )
    events_table = (
        "<table><thead><tr><th>Kind</th><th>Label</th><th>Price</th></tr></thead>"
        f"<tbody>{''.join(rows_events) or '<tr><td colspan=3>—</td></tr>'}</tbody></table>"
    )

    return (
        "<div class='card' style='text-align:center;padding:32px'>"
        "<p style='font-size:16px;font-weight:700;margin-bottom:8px'>No market candles available</p>"
        "<p class='note'>Levels and events are shown in tabular form below.</p>"
        "</div>"
        "<div class='card'><h2>Levels</h2>"
        f"{levels_table}</div>"
        "<div class='card'><h2>Events</h2>"
        f"{events_table}</div>"
    )


def render_trade_chart_echarts(
    payload: dict[str, object],
    *,
    chart_id: str,
    asset_path: str,
) -> str:
    """Return an HTML fragment containing the ECharts chart or a readable fallback."""
    candles_by_tf: dict = payload.get("candles_by_timeframe") or {}

    if not candles_by_tf:
        return _build_fallback(payload)

    meta = payload.get("meta") or {}
    default_tf: str | None = meta.get("default_timeframe")
    timeframes = list(candles_by_tf.keys())

    tf_buttons  = _build_tf_buttons(chart_id, timeframes, default_tf)
    tog_buttons = _build_toggle_buttons(chart_id)
    payload_json = json.dumps(payload, ensure_ascii=False)
    js_code = _CHART_JS.replace("%%CHART_ID%%", chart_id)

    return (
        f"<script src='{asset_path}'></script>\n"
        "<div class='chart-wrap'>\n"
        "  <div class='chart-toolbar' style='flex-wrap:wrap;gap:6px'>\n"
        f"    {tf_buttons}\n"
        f"    <span style='width:1px;background:#e2e8f0;align-self:stretch;margin:0 4px'></span>\n"
        f"    {tog_buttons}\n"
        f"    <button id='{chart_id}-reset' class='chart-toolbar-btn' style='margin-left:auto'>Reset zoom</button>\n"
        "  </div>\n"
        f"  <div id='{chart_id}' style='width:100%;height:520px;min-height:320px'></div>\n"
        f"  <script type='application/json' id='{chart_id}_payload'>{payload_json}</script>\n"
        f"  <script>{js_code}</script>\n"
        "</div>\n"
    )
