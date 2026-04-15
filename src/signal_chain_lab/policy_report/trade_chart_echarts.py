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
  var chartEl   = document.getElementById('%%CHART_ID%%');
  var railEl    = document.getElementById('%%CHART_ID%%_rail');
  var payloadEl = document.getElementById('%%CHART_ID%%_payload');
  if (!chartEl || !payloadEl) { return; }

  var payload        = JSON.parse(payloadEl.textContent || '{}');
  var candlesByTF    = payload.candles_by_timeframe || {};
  var levels         = payload.levels  || {};
  var events         = payload.events  || [];
  var meta           = payload.meta    || {};
  var posSizePts     = payload.position_size_series  || [];
  var realizedPnlPts = payload.realized_pnl_series   || [];
  var currentTF      = meta.default_timeframe || Object.keys(candlesByTF)[0] || '';
  var fillsCount     = meta.fills_count || 0;

  var chart = echarts.init(chartEl, null, {renderer: 'canvas'});
  var railChart = railEl ? echarts.init(railEl, null, {renderer: 'canvas'}) : null;

  // ---- level line colours (must match LEVEL_SERIES keys below) --------------
  var LEVEL_COLOR = {
    'entries_planned': '#93c5fd',   // light blue dashed
    'entries_filled':  '#1d4ed8',   // solid blue
    'avg_entry':       '#0369a1',   // deeper blue (only when fills >= 2)
    'sl_initial':      '#fca5a5',   // light red dashed
    'sl_current':      '#b91c1c',   // solid red
    'tps':             '#15803d',   // green dashed
    'exit':            '#7c3aed'    // purple solid
  };

  // ---- event marker colours per kind ----------------------------------------
  var KIND_COLOR = {
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
    'SYSTEM_NOTE':   '#94a3b8'
  };
  var KIND_SYMBOL = {
    'FILL':          'circle',
    'TP':            'diamond',
    'SL':            'triangle',
    'MOVE_SL':       'rect',
    'BE':            'pin',
    'PARTIAL_CLOSE': 'roundRect',
    'CLOSE':         'diamond',
    'CANCEL':        'triangle',
    'EXPIRED':       'triangle',
    'TIMEOUT':       'triangle',
    'SYSTEM_NOTE':   'circle'
  };
  function kindColor(k)  { return KIND_COLOR[k]  || '#f59e0b'; }
  function kindSymbol(k) { return KIND_SYMBOL[k] || 'circle'; }

  // ---- granular visibility state --------------------------------------------
  // Canonical kind list — must match _classify_event_type() in html_writer.py
  var visibility = {
    // level lines
    entries_planned: true,
    entries_filled:  true,
    avg_entry:       true,   // conditional: only if fillsCount >= 2
    sl:              true,
    tps:             true,
    exit:            true,
    // event markers (per kind)
    ev_FILL:          true,
    ev_TP:            true,
    ev_SL:            true,
    ev_MOVE_SL:       true,
    ev_BE:            true,
    ev_CLOSE:         true,
    ev_PARTIAL_CLOSE: true,
    ev_CANCEL:        false,
    ev_EXPIRED:       true,
    ev_TIMEOUT:       true,
    ev_SYSTEM_NOTE:   true,
    event_rail:      true,
    // secondary overlays (existing toggles, unchanged)
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
      return {yAxis: l.price, name: l.label || ''};
    });
  }
  function buildMarkLineSeries(id, name, levelKey, color, lineType, show) {
    var data = show ? buildMarkLineData(levels[levelKey] || []) : [];
    return {
      id: id, name: name, type: 'line', data: [],
      xAxisIndex: 0, yAxisIndex: 0, silent: true,
      markLine: data.length === 0 ? {data: []} : {
        symbol: ['none', 'none'],
        lineStyle: {color: color, type: lineType, width: 1.5},
        label: {
          show: true,
          position: 'insideStartTop',
          formatter: '{b}',
          color: color,
          fontSize: 10,
          backgroundColor: 'rgba(255,255,255,0.82)',
          padding: [1, 4],
          borderRadius: 3
        },
        data: data
      }
    };
  }
  function buildScatterData() {
    return (events || []).filter(function (e) {
      var key = 'ev_' + e.kind;
      return visibility[key] !== false;
    }).map(function (e) {
      return {
        value:       [e.ts, e.price],
        name:        e.label || e.kind,
        kind:        e.kind,
        event_id:    e.event_id || null,
        summary:     e.summary || '',
        source:      e.source || '',
        return_pct:  e.return_pct != null ? e.return_pct : null,
        itemStyle:   {color: kindColor(e.kind), borderColor: '#ffffff', borderWidth: 1.5},
        symbol:      kindSymbol(e.kind)
      };
    });
  }
  function buildRailData() {
    var allowed = {'MOVE_SL':true, 'CANCEL':true, 'EXPIRED':true, 'TIMEOUT':true, 'SYSTEM_NOTE':true, 'BE':true};
    var grouped = {};
    var list = [];
    (events || []).forEach(function (e) {
      var k = e.kind || '';
      if (!allowed[k]) { return; }
      var key = String(e.ts);
      if (!grouped[key]) { grouped[key] = 0; }
      var lane = grouped[key];
      grouped[key] += 1;
      list.push({
        value: [e.ts, lane],
        name: e.label || k,
        kind: k,
        event_id: e.event_id || null,
        summary: e.summary || ''
      });
    });
    return list;
  }
  function buildStepData(pts) {
    return pts.map(function (p) { return [p[0], p[1]]; });
  }
  function buildRailOption() {
    return {
      animation: false,
      grid: {left: 80, right: 24, top: 8, bottom: 28},
      xAxis: {type: 'time', scale: true, axisLine: {lineStyle: {color: '#cbd5e1'}}, splitLine: {show: false}},
      yAxis: {
        type: 'value',
        min: -0.5,
        max: 4.5,
        interval: 1,
        axisLabel: {formatter: function (v) { return 'L' + (v + 1); }},
        splitLine: {show: false}
      },
      tooltip: {
        trigger: 'item',
        formatter: function (p) {
          if (!p || !p.data) { return ''; }
          var d = p.data;
          var ts = new Date(d.value[0]).toISOString().replace('T', ' ').slice(0, 19);
          return '<b>' + (d.kind || '') + '</b><br/>' + ts + '<br/>' + (d.summary || '');
        }
      },
      dataZoom: [
        {type: 'inside', xAxisIndex: [0], filterMode: 'none'},
        {type: 'slider', xAxisIndex: [0], bottom: 0, height: 18, borderColor: '#e2e8f0'}
      ],
      series: [{
        id: 'rail_events',
        type: 'scatter',
        data: buildRailData(),
        symbolSize: 11,
        itemStyle: {color: function (p) { return kindColor(p.data.kind); }},
      }]
    };
  }

  // ---- build full option ---------------------------------------------------
  function buildOption(tf) {
    var showVol  = visibility.volume;
    var showPS   = visibility.pos_size;
    var showPnl  = visibility.realized_pnl;
    var showAvgE = visibility.avg_entry && fillsCount >= 2;

    var mainGridBottom = showVol ? 150 : 80;
    var grids = [{left: 80, right: 24, top: 56, bottom: mainGridBottom}];
    var xAxes = [{type: 'time', scale: true, gridIndex: 0,
                  axisLine: {lineStyle: {color: '#cbd5e1'}}, splitLine: {show: false}}];
    var yAxes = [
      {type: 'value', scale: true, gridIndex: 0, position: 'left',
       axisLine: {show: false}, splitLine: {lineStyle: {color: '#f1f5f9'}}},
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
      // ---- level markLine series (one per level type) ----
      buildMarkLineSeries('lv_entries_planned', 'Entries (plan)', 'entries_planned',
        LEVEL_COLOR.entries_planned, 'dashed', visibility.entries_planned),
      buildMarkLineSeries('lv_entries_filled',  'Entries (fill)', 'entries_filled',
        LEVEL_COLOR.entries_filled,  'solid',  visibility.entries_filled),
      buildMarkLineSeries('lv_avg_entry',        'Avg Entry',      'avg_entry',
        LEVEL_COLOR.avg_entry,       'dashed', showAvgE),
      buildMarkLineSeries('lv_sl_initial',       'Initial SL',     'sl_initial',
        LEVEL_COLOR.sl_initial,      'dashed', visibility.sl),
      buildMarkLineSeries('lv_sl_current',       'Current SL',     'sl_current',
        LEVEL_COLOR.sl_current,      'solid',  visibility.sl),
      buildMarkLineSeries('lv_tps',              'TPs',            'tps',
        LEVEL_COLOR.tps,             'dashed', visibility.tps),
      buildMarkLineSeries('lv_exit',             'Exit',           'exit',
        LEVEL_COLOR.exit,            'solid',  visibility.exit),
      // ---- events scatter ----
      {
        id: 'events', name: 'Events', type: 'scatter',
        data: scatterData,
        xAxisIndex: 0, yAxisIndex: 0,
        symbolSize: 12, z: 5,
        label: {show: false}
      },
      // ---- position size / realized PnL overlays ----
      {
        id: 'pos_size', name: 'Position Size', type: 'line',
        data: showPS ? buildStepData(posSizePts) : [],
        xAxisIndex: 0, yAxisIndex: 1, step: 'end', symbol: 'none',
        lineStyle: {color: '#0284c7', width: 1.5, opacity: 0.8},
        areaStyle: {color: 'rgba(2,132,199,.08)'}, z: 2
      },
      {
        id: 'realized_pnl', name: 'Realized PnL', type: 'line',
        data: showPnl ? buildStepData(realizedPnlPts) : [],
        xAxisIndex: 0, yAxisIndex: 1, step: 'end', symbol: 'none',
        lineStyle: {color: '#f59e0b', width: 1.5, opacity: 0.9}, z: 2
      }
    ];

    if (showVol) {
      series.push({
        id: 'volume', name: 'Volume', type: 'bar',
        data: buildVolumeData(tf),
        xAxisIndex: 1, yAxisIndex: 2, barMaxWidth: 20,
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
            } else if (p.seriesType === 'scatter' && p.data && p.data.kind) {
              var ev = p.data;
              var ts  = new Date(ev.value[0]).toISOString().replace('T', ' ').slice(0, 19);
              lines.push('<b style="color:' + kindColor(ev.kind) + '">&#9679;&nbsp;' + (ev.name || ev.kind) + '</b>');
              lines.push('Time:&nbsp;' + ts);
              lines.push('Price:&nbsp;' + (+ev.value[1]).toFixed(6));
              if (ev.source) { lines.push('Source:&nbsp;' + ev.source); }
              if (ev.return_pct != null) {
                var sign = ev.return_pct >= 0 ? '+' : '';
                lines.push('Return:&nbsp;<b>' + sign + (+ev.return_pct).toFixed(2) + '%</b>');
              }
            } else if (p.seriesType === 'line' && p.data) {
              lines.push('<span style="color:' + p.color + '">&#9644;</span>&nbsp;' +
                p.seriesName + ':&nbsp;<b>' + (+p.data[1]).toFixed(4) + '</b>');
            }
          }
          return lines.length ? lines.join('<br/>') : '';
        }
      },
      legend: {show: false},
      grid:  grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        {type: 'inside',  xAxisIndex: showVol ? [0, 1] : [0], filterMode: 'weakFilter'},
        {type: 'slider',  xAxisIndex: showVol ? [0, 1] : [0], bottom: 8, height: 28,
         borderColor: '#e2e8f0'}
      ],
      series: series
    };
  }

  // ---- initial render -------------------------------------------------------
  chart.setOption(buildOption(currentTF));
  if (railChart) {
    railChart.setOption(buildRailOption());
    railEl.style.display = visibility.event_rail ? '' : 'none';
  }

  // ---- timeframe switch -----------------------------------------------------
  function setTF(tf) {
    if (!(tf in candlesByTF)) { return; }
    currentTF = tf;
    chart.setOption({series: [{id: 'candles', data: buildCandleData(tf)}]});
    document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-tf') === tf);
    });
    if (railChart) {
      railChart.setOption({series: [{id: 'rail_events', data: buildRailData()}]});
    }
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

  // ---- toggle buttons with optional timeline sync --------------------------
  function rebuildChart() {
    chart.setOption(buildOption(currentTF), {replaceMerge: ['series', 'grid', 'xAxis', 'yAxis']});
    if (railChart) {
      railChart.setOption({series: [{id: 'rail_events', data: buildRailData()}]});
      railEl.style.display = visibility.event_rail ? '' : 'none';
      railChart.resize();
    }
  }
  function wireToggle(btnId, key) {
    var btn = document.getElementById('%%CHART_ID%%-' + btnId);
    if (!btn) { return; }
    var timelineKind = btn.getAttribute('data-timeline-kind');
    btn.classList.toggle('active', !!visibility[key]);
    btn.addEventListener('click', function () {
      visibility[key] = !visibility[key];
      btn.classList.toggle('active', !!visibility[key]);
      rebuildChart();
      // sync timeline item visibility (1:1 mapping)
      if (timelineKind) {
        document.querySelectorAll('.ti-v2[data-kind="' + timelineKind + '"]').forEach(function (el) {
          el.style.display = visibility[key] ? '' : 'none';
        });
      }
    });
  }
  // level toggles
  wireToggle('toggle-entries-planned', 'entries_planned');
  wireToggle('toggle-entries-filled',  'entries_filled');
  wireToggle('toggle-avg-entry',       'avg_entry');
  wireToggle('toggle-sl',              'sl');
  wireToggle('toggle-tps',             'tps');
  wireToggle('toggle-exit',            'exit');
  // event marker toggles
  wireToggle('toggle-ev-fill',         'ev_FILL');
  wireToggle('toggle-ev-tp',           'ev_TP');
  wireToggle('toggle-ev-sl',           'ev_SL');
  wireToggle('toggle-ev-move-sl',      'ev_MOVE_SL');
  wireToggle('toggle-ev-close',        'ev_CLOSE');
  wireToggle('toggle-ev-partial',      'ev_PARTIAL_CLOSE');
  wireToggle('toggle-event-rail',      'event_rail');
  // secondary overlays
  wireToggle('toggle-volume',          'volume');
  wireToggle('toggle-pos-size',        'pos_size');
  wireToggle('toggle-pnl',             'realized_pnl');

  function focusEventById(eventId) {
    if (!eventId) { return; }
    var scatter = buildScatterData();
    var idx = -1;
    for (var i = 0; i < scatter.length; i++) {
      if (scatter[i].event_id === eventId) { idx = i; break; }
    }
    if (idx >= 0) {
      chart.dispatchAction({type: 'showTip', seriesId: 'events', dataIndex: idx});
    }
    if (railChart) {
      var rail = buildRailData();
      for (var j = 0; j < rail.length; j++) {
        if (rail[j].event_id === eventId) {
          railChart.dispatchAction({type: 'showTip', seriesId: 'rail_events', dataIndex: j});
          break;
        }
      }
    }
  }

  chart.on('click', function (params) {
    var evId = params && params.data ? params.data.event_id : null;
    if (evId) {
      window.dispatchEvent(new CustomEvent('trade-event-focus', {detail: {eventId: evId}}));
    }
  });
  if (railChart) {
    railChart.on('click', function (params) {
      var evId = params && params.data ? params.data.event_id : null;
      if (evId) {
        window.dispatchEvent(new CustomEvent('trade-event-focus', {detail: {eventId: evId}}));
      }
    });
  }
  window.addEventListener('trade-event-select', function (evt) {
    var evId = evt && evt.detail ? evt.detail.eventId : null;
    focusEventById(evId);
  });

  // sync zoom between price chart and event rail
  var syncing = false;
  chart.on('dataZoom', function () {
    if (!railChart || syncing) { return; }
    var opt = chart.getOption() || {};
    var dz = (opt.dataZoom || [])[0];
    if (!dz) { return; }
    syncing = true;
    railChart.dispatchAction({type: 'dataZoom', start: dz.start, end: dz.end});
    syncing = false;
  });
  if (railChart) {
    railChart.on('dataZoom', function () {
      if (syncing) { return; }
      var opt = railChart.getOption() || {};
      var dz = (opt.dataZoom || [])[0];
      if (!dz) { return; }
      syncing = true;
      chart.dispatchAction({type: 'dataZoom', start: dz.start, end: dz.end});
      syncing = false;
    });
  }

  // ---- resize ---------------------------------------------------------------
  window.addEventListener('resize', function () {
    chart.resize();
    if (railChart) { railChart.resize(); }
  });
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
    # (btn_id, label, default_on, timeline_kind)
    # timeline_kind: the data-kind value on .ti-v2 items to show/hide in sync (None = no sync)
    toggles: list[tuple[str, str, bool, str | None]] = [
        # ---- level lines ----
        ("toggle-entries-planned", "Entries (plan)", True,  None),
        ("toggle-entries-filled",  "Entries (fill)", True,  None),
        ("toggle-avg-entry",       "Avg Entry",      True,  None),
        ("toggle-sl",              "SL",             True,  "SL"),
        ("toggle-tps",             "TPs",            True,  "TP"),
        ("toggle-exit",            "Exit",           True,  "EXIT"),
        # ---- event markers ----
        ("toggle-ev-fill",         "Fills",          True,  "FILL"),
        ("toggle-ev-tp",           "TP events",      True,  "TP"),
        ("toggle-ev-sl",           "SL events",      True,  "SL"),
        ("toggle-ev-move-sl",      "SL moves",       True,  "MOVE_SL"),
        ("toggle-ev-close",        "Close",          True,  "EXIT"),
        ("toggle-ev-partial",      "Partial close",  True,  "PARTIAL_CLOSE"),
        ("toggle-event-rail",      "Event rail",     True,  None),
        # ---- secondary overlays ----
        ("toggle-volume",          "Volume",         False, None),
        ("toggle-pos-size",        "Pos Size",       False, None),
        ("toggle-pnl",             "Realized PnL",   False, None),
    ]
    parts: list[str] = []
    for btn_id, label, default_on, timeline_kind in toggles:
        active_cls = "active" if default_on else ""
        tl_attr = f" data-timeline-kind='{timeline_kind}'" if timeline_kind else ""
        parts.append(
            f"<button id='{chart_id}-{btn_id}' class='chart-toolbar-btn {active_cls}'"
            f" title='Toggle {label}'{tl_attr}>{label}</button>"
        )
    return "".join(parts)


def _build_fallback(payload: dict[str, object]) -> str:
    levels = payload.get("levels") or {}
    events = payload.get("events") or []

    rows_levels: list[str] = []
    for group_name, group_key in [
        ("Entries (plan)", "entries_planned"),
        ("Entries (fill)", "entries_filled"),
        ("Avg Entry",      "avg_entry"),
        ("Initial SL",     "sl_initial"),
        ("Current SL",     "sl_current"),
        ("TPs",            "tps"),
        ("Exit",           "exit"),
    ]:
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
        f"  <div id='{chart_id}_rail' style='width:100%;height:170px;min-height:120px;margin-top:8px'></div>\n"
        f"  <script type='application/json' id='{chart_id}_payload'>{payload_json}</script>\n"
        f"  <script>{js_code}</script>\n"
        "</div>\n"
    )
