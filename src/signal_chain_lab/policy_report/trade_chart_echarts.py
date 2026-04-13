"""Render an ECharts candlestick chart from a trade chart payload dict."""
from __future__ import annotations

import json

_CHART_JS = r"""
(function () {
  'use strict';
  var chartEl = document.getElementById('%%CHART_ID%%');
  var payloadEl = document.getElementById('%%CHART_ID%%_payload');
  if (!chartEl || !payloadEl) { return; }

  var payload = JSON.parse(payloadEl.textContent || '{}');
  var candlesByTF = payload.candles_by_timeframe || {};
  var levels = payload.levels || {};
  var events = payload.events || [];
  var meta = payload.meta || {};
  var currentTF = meta.default_timeframe || Object.keys(candlesByTF)[0] || '';
  var chart = echarts.init(chartEl, null, { renderer: 'canvas' });

  var FAMILY_COLOR = {
    'SIGNAL': '#60a5fa',
    'FILL': '#1d4ed8',
    'UPDATE': '#c2410c',
    'TP': '#15803d',
    'SL': '#b91c1c',
    'PARTIAL_CLOSE': '#7c3aed',
    'CLOSE': '#7c3aed',
    'CANCEL': '#64748b',
    'EVENT': '#f59e0b'
  };
  var FAMILY_SYMBOL = {
    'SIGNAL': 'circle',
    'FILL': 'circle',
    'UPDATE': 'rect',
    'TP': 'diamond',
    'SL': 'triangle',
    'PARTIAL_CLOSE': 'roundRect',
    'CLOSE': 'diamond',
    'CANCEL': 'pin',
    'EVENT': 'circle'
  };
  var LEVEL_META = {
    entries:    { name: 'Entries',    color: '#2563eb', type: 'dashed', position: 'middle' },
    avg_entry:  { name: 'Avg Entry',  color: '#1d4ed8', type: 'solid',  position: 'middle' },
    initial_sl: { name: 'Initial SL', color: '#ef4444', type: 'dashed', position: 'start'  },
    last_sl:    { name: 'Last SL',    color: '#b91c1c', type: 'solid',  position: 'start'  },
    sl_history: { name: 'SL History', color: '#f97316', type: 'dotted', position: 'start'  },
    tps:        { name: 'TPs',        color: '#15803d', type: 'dashed', position: 'end'    },
    exit:       { name: 'Exit',       color: '#7c3aed', type: 'solid',  position: 'end'    }
  };

  var visibility = {
    entries: true,
    sl: true,
    tp: true,
    exit: true,
    sl_history: false,
    signal: true,
    fills: true,
    updates: true,
    outcomes: true,
    volume: false
  };

  function familyColor(name) { return FAMILY_COLOR[name] || '#f59e0b'; }
  function familySymbol(name) { return FAMILY_SYMBOL[name] || 'circle'; }

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
      return { yAxis: l.price, name: l.label };
    });
  }

  function buildLevelSeries(groupKey) {
    var cfg = LEVEL_META[groupKey];
    var data = buildMarkLineData(levels[groupKey] || []);
    var visible = false;
    if (groupKey === 'entries' || groupKey === 'avg_entry') { visible = visibility.entries; }
    else if (groupKey === 'initial_sl' || groupKey === 'last_sl') { visible = visibility.sl; }
    else if (groupKey === 'tps') { visible = visibility.tp; }
    else if (groupKey === 'exit') { visible = visibility.exit; }
    else if (groupKey === 'sl_history') { visible = visibility.sl_history; }

    return {
      id: groupKey,
      name: cfg.name,
      type: 'line',
      data: [],
      xAxisIndex: 0,
      yAxisIndex: 0,
      silent: true,
      markLine: !visible ? {} : {
        symbol: ['none', 'none'],
        lineStyle: { color: cfg.color, type: cfg.type, width: groupKey === 'last_sl' ? 2.4 : 1.6, opacity: 0.95 },
        label: { formatter: '{b}  {c}', color: cfg.color, fontSize: 11, position: cfg.position, backgroundColor: '#ffffff', padding: [2, 4], borderRadius: 4 },
        data: data
      }
    };
  }

  function eventVisible(family) {
    if (family === 'SIGNAL') { return visibility.signal; }
    if (family === 'FILL') { return visibility.fills; }
    if (family === 'UPDATE') { return visibility.updates; }
    return visibility.outcomes;
  }

  function eventSeries(family) {
    var points = events.filter(function (e) { return e.family === family && eventVisible(family); });
    return {
      id: 'event_' + family.toLowerCase(),
      name: family === 'PARTIAL_CLOSE' ? 'Outcomes' : (family === 'CLOSE' || family === 'CANCEL' || family === 'TP' || family === 'SL' ? 'Outcomes' : family.charAt(0) + family.slice(1).toLowerCase()),
      type: 'scatter',
      data: points.map(function (e) {
        return {
          value: [e.ts, e.price],
          labelText: e.label,
          eventType: e.event_type,
          source: e.source,
          status: e.status,
          reason: e.reason || '-',
          family: e.family,
          itemStyle: {
            color: familyColor(e.family),
            borderColor: '#ffffff',
            borderWidth: 1.5
          },
          symbol: familySymbol(e.family)
        };
      }),
      xAxisIndex: 0,
      yAxisIndex: 0,
      symbolSize: family === 'SIGNAL' ? 12 : 11,
      z: 5,
      label: {
        show: points.length > 0 && eventVisible(family),
        position: 'top',
        formatter: function (p) { return p.data.labelText; },
        fontSize: 10,
        color: '#0f172a',
        backgroundColor: 'rgba(255,255,255,.92)',
        padding: [2, 5],
        borderRadius: 4
      }
    };
  }

  function pad2(value) { return String(value).padStart(2, '0'); }
  function formatUtcDateTime(ts) {
    var dt = new Date(ts);
    return dt.getUTCFullYear() + '-' + pad2(dt.getUTCMonth() + 1) + '-' + pad2(dt.getUTCDate()) + ' ' + pad2(dt.getUTCHours()) + ':' + pad2(dt.getUTCMinutes()) + ' UTC';
  }
  function formatUtcAxis(ts, tf) {
    var dt = new Date(ts);
    var monthDay = pad2(dt.getUTCMonth() + 1) + '-' + pad2(dt.getUTCDate());
    var hourMinute = pad2(dt.getUTCHours()) + ':' + pad2(dt.getUTCMinutes());
    if (tf === '1d') { return monthDay; }
    if (tf === '4h' || tf === '1h') { return monthDay + '\n' + hourMinute; }
    return hourMinute;
  }

  function buildOption(tf) {
    var showVol = visibility.volume;
    var mainGridBottom = showVol ? 150 : 80;
    var grids = [{ left: 80, right: 24, top: 56, bottom: mainGridBottom }];
    var xAxes = [{
      type: 'time',
      scale: true,
      gridIndex: 0,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      splitLine: { show: false },
      axisLabel: { formatter: function (value) { return formatUtcAxis(value, tf); } }
    }];
    var yAxes = [{
      type: 'value',
      scale: true,
      gridIndex: 0,
      position: 'left',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f1f5f9' } }
    }];

    if (showVol) {
      grids.push({ left: 80, right: 24, top: 'auto', bottom: 40, height: 60 });
      xAxes.push({
        type: 'time',
        scale: true,
        gridIndex: 1,
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        splitLine: { show: false },
        axisLabel: { formatter: function (value) { return formatUtcAxis(value, tf); } }
      });
      yAxes.push({
        type: 'value',
        scale: true,
        gridIndex: 1,
        position: 'left',
        axisLabel: { show: false },
        splitLine: { show: false }
      });
    }

    var series = [{
      id: 'candles',
      name: 'Candles',
      type: 'candlestick',
      data: buildCandleData(tf),
      barMaxWidth: 20,
      xAxisIndex: 0,
      yAxisIndex: 0,
      itemStyle: {
        color: '#15803d',
        color0: '#b91c1c',
        borderColor: '#15803d',
        borderColor0: '#b91c1c'
      }
    }];

    ['entries', 'avg_entry', 'initial_sl', 'last_sl', 'sl_history', 'tps', 'exit'].forEach(function (key) {
      series.push(buildLevelSeries(key));
    });
    ['SIGNAL', 'FILL', 'UPDATE', 'TP', 'SL', 'PARTIAL_CLOSE', 'CLOSE', 'CANCEL', 'EVENT'].forEach(function (family) {
      series.push(eventSeries(family));
    });

    if (showVol) {
      series.push({
        id: 'volume',
        name: 'Volume',
        type: 'bar',
        data: buildVolumeData(tf),
        xAxisIndex: 1,
        yAxisIndex: 1,
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
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: function (params) {
          var lines = [];
          for (var i = 0; i < params.length; i++) {
            var p = params[i];
            if (p.seriesType === 'candlestick' && p.data) {
              var d = p.data;
              lines.push('<b>' + formatUtcDateTime(d[0]) + '</b>');
              lines.push('O:&nbsp;' + (+d[1]).toFixed(6) + '&ensp;C:&nbsp;' + (+d[2]).toFixed(6));
              lines.push('L:&nbsp;' + (+d[3]).toFixed(6) + '&ensp;H:&nbsp;' + (+d[4]).toFixed(6));
            } else if (p.seriesType === 'scatter' && p.data) {
              lines.push('<span style="color:' + p.color + '">&#9679;</span>&nbsp;<b>' + p.data.eventType + '</b>');
              lines.push('Source:&nbsp;' + p.data.source);
              lines.push('Status:&nbsp;' + p.data.status);
              lines.push('Price:&nbsp;' + (+p.data.value[1]).toFixed(6));
              if (p.data.reason && p.data.reason !== '-') { lines.push('Reason:&nbsp;' + p.data.reason); }
            }
          }
          return lines.join('<br/>');
        }
      },
      legend: {
        top: 6,
        itemGap: 14,
        data: [
          { name: 'Candles' },
          { name: 'Entries', icon: 'line' },
          { name: 'Avg Entry', icon: 'line' },
          { name: 'Initial SL', icon: 'line' },
          { name: 'Last SL', icon: 'line' },
          { name: 'SL History', icon: 'line' },
          { name: 'TPs', icon: 'line' },
          { name: 'Exit', icon: 'line' },
          { name: 'Signal', icon: 'circle' },
          { name: 'Fill', icon: 'circle' },
          { name: 'Update', icon: 'rect' },
          { name: 'Outcomes', icon: 'diamond' }
        ]
      },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        { type: 'inside', xAxisIndex: showVol ? [0, 1] : [0], filterMode: 'weakFilter' },
        { type: 'slider', xAxisIndex: showVol ? [0, 1] : [0], bottom: 8, height: 28, borderColor: '#e2e8f0' }
      ],
      series: series
    };
  }

  chart.setOption(buildOption(currentTF));

  function setTF(tf) {
    if (!(tf in candlesByTF)) { return; }
    currentTF = tf;
    chart.setOption({ series: [{ id: 'candles', data: buildCandleData(tf) }] });
    document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-tf') === tf);
    });
  }
  document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
    btn.addEventListener('click', function () { setTF(btn.getAttribute('data-tf')); });
  });

  var resetBtn = document.getElementById('%%CHART_ID%%-reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      chart.dispatchAction({ type: 'dataZoom', start: 0, end: 100 });
    });
  }

  function rebuildChart() {
    chart.setOption(buildOption(currentTF), { replaceMerge: ['series', 'grid', 'xAxis', 'yAxis'] });
  }
  function wireToggle(btnId, key) {
    var btn = document.getElementById('%%CHART_ID%%-' + btnId);
    if (!btn) { return; }
    btn.classList.toggle('active', visibility[key]);
    btn.addEventListener('click', function () {
      visibility[key] = !visibility[key];
      btn.classList.toggle('active', visibility[key]);
      rebuildChart();
    });
  }
  wireToggle('toggle-entries', 'entries');
  wireToggle('toggle-sl', 'sl');
  wireToggle('toggle-tp', 'tp');
  wireToggle('toggle-exit', 'exit');
  wireToggle('toggle-sl-history', 'sl_history');
  wireToggle('toggle-signal', 'signal');
  wireToggle('toggle-fills', 'fills');
  wireToggle('toggle-updates', 'updates');
  wireToggle('toggle-outcomes', 'outcomes');
  wireToggle('toggle-volume', 'volume');

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
        ("toggle-entries", "Entries", True),
        ("toggle-sl", "SL", True),
        ("toggle-tp", "TP", True),
        ("toggle-exit", "Exit", True),
        ("toggle-sl-history", "SL History", False),
        ("toggle-signal", "Signal", True),
        ("toggle-fills", "Fills", True),
        ("toggle-updates", "Updates", True),
        ("toggle-outcomes", "Outcomes", True),
        ("toggle-volume", "Volume", False),
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
    for group_name, group_key in [
        ("Entries", "entries"),
        ("Avg Entry", "avg_entry"),
        ("Initial SL", "initial_sl"),
        ("Last SL", "last_sl"),
        ("SL History", "sl_history"),
        ("TPs", "tps"),
        ("Exit", "exit"),
    ]:
        for item in (levels.get(group_key) or []):
            rows_levels.append(
                f"<tr><td>{group_name}</td><td>{item.get('label', '')}</td><td>{item.get('price', '')}</td></tr>"
            )

    rows_events: list[str] = []
    for ev in events:
        rows_events.append(
            f"<tr><td>{ev.get('family', '')}</td><td>{ev.get('event_type', '')}</td><td>{ev.get('price', '')}</td></tr>"
        )

    levels_table = (
        "<table><thead><tr><th>Group</th><th>Label</th><th>Price</th></tr></thead>"
        f"<tbody>{''.join(rows_levels) or '<tr><td colspan=3>-</td></tr>'}</tbody></table>"
    )
    events_table = (
        "<table><thead><tr><th>Family</th><th>Event</th><th>Price</th></tr></thead>"
        f"<tbody>{''.join(rows_events) or '<tr><td colspan=3>-</td></tr>'}</tbody></table>"
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

    tf_buttons = _build_tf_buttons(chart_id, timeframes, default_tf)
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
