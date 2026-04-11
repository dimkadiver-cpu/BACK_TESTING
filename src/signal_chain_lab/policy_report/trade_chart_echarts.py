"""Render an ECharts candlestick chart from a trade chart payload dict."""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# JavaScript template – uses %%CHART_ID%% as the placeholder so we can keep
# the code as a plain Python string without f-string brace-escaping noise.
# ---------------------------------------------------------------------------
_CHART_JS = r"""
(function () {
  'use strict';
  var chartEl = document.getElementById('%%CHART_ID%%');
  var payloadEl = document.getElementById('%%CHART_ID%%_payload');
  if (!chartEl || !payloadEl) { return; }

  var payload = JSON.parse(payloadEl.textContent || '{}');
  var candlesByTF = payload.candles_by_timeframe || {};
  var levels    = payload.levels  || {entries: [], sl: [], tps: [], exit: []};
  var events    = payload.events  || [];
  var meta      = payload.meta    || {};
  var currentTF = meta.default_timeframe || Object.keys(candlesByTF)[0] || '';

  var chart = echarts.init(chartEl, null, {renderer: 'canvas'});

  // ---- data builders -------------------------------------------------------
  function buildCandleData(tf) {
    // payload row: [ts_ms, open, close, low, high, volume]
    // ECharts candlestick: [time, open, close, low, high]
    return (candlesByTF[tf] || []).map(function (c) {
      return [c[0], c[1], c[2], c[3], c[4]];
    });
  }

  function buildMarkLineData(levelList) {
    return (levelList || []).map(function (l) {
      return {yAxis: l.price, name: l.label};
    });
  }

  function buildScatterData(evts) {
    return (evts || []).map(function (e) {
      return {value: [e.ts, e.price], name: e.label || e.kind};
    });
  }

  // ---- option builder ------------------------------------------------------
  function buildOption(tf) {
    return {
      animation: false,
      backgroundColor: '#ffffff',
      tooltip: {
        trigger: 'axis',
        axisPointer: {type: 'cross'},
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
            }
          }
          return lines.join('<br/>');
        }
      },
      legend: {
        top: 6,
        itemGap: 16,
        data: [
          {name: 'Candles'},
          {name: 'Entries',  icon: 'line'},
          {name: 'SL/BE',    icon: 'line'},
          {name: 'TPs',      icon: 'line'},
          {name: 'Exit',     icon: 'line'},
          {name: 'Events',   icon: 'circle'}
        ]
      },
      grid: {left: 80, right: 24, top: 56, bottom: 80},
      xAxis: {
        type: 'time',
        scale: true,
        axisLine: {lineStyle: {color: '#cbd5e1'}},
        splitLine: {show: false}
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLine: {show: false},
        splitLine: {lineStyle: {color: '#f1f5f9'}}
      },
      dataZoom: [
        {type: 'inside',  xAxisIndex: 0, filterMode: 'weakFilter'},
        {type: 'slider',  xAxisIndex: 0, bottom: 8, height: 28, borderColor: '#e2e8f0'}
      ],
      series: [
        {
          id: 'candles',
          name: 'Candles',
          type: 'candlestick',
          data: buildCandleData(tf),
          barMaxWidth: 20,
          itemStyle: {
            color:        '#15803d',
            color0:       '#b91c1c',
            borderColor:  '#15803d',
            borderColor0: '#b91c1c'
          }
        },
        {
          id: 'entries',
          name: 'Entries',
          type: 'line',
          data: [],
          silent: true,
          markLine: {
            symbol: ['none', 'none'],
            lineStyle: {color: '#2563eb', type: 'dashed', width: 1.5},
            label: {formatter: '{b}  {c}', color: '#2563eb', fontSize: 11},
            data: buildMarkLineData(levels.entries)
          }
        },
        {
          id: 'sl_be',
          name: 'SL/BE',
          type: 'line',
          data: [],
          silent: true,
          markLine: {
            symbol: ['none', 'none'],
            lineStyle: {color: '#b91c1c', type: 'dashed', width: 1.5},
            label: {formatter: '{b}  {c}', color: '#b91c1c', fontSize: 11},
            data: buildMarkLineData(levels.sl)
          }
        },
        {
          id: 'tps',
          name: 'TPs',
          type: 'line',
          data: [],
          silent: true,
          markLine: {
            symbol: ['none', 'none'],
            lineStyle: {color: '#15803d', type: 'dashed', width: 1.5},
            label: {formatter: '{b}  {c}', color: '#15803d', fontSize: 11},
            data: buildMarkLineData(levels.tps)
          }
        },
        {
          id: 'exit',
          name: 'Exit',
          type: 'line',
          data: [],
          silent: true,
          markLine: {
            symbol: ['none', 'none'],
            lineStyle: {color: '#7c3aed', type: 'solid', width: 2},
            label: {formatter: '{b}  {c}', color: '#7c3aed', fontSize: 11},
            data: buildMarkLineData(levels.exit)
          }
        },
        {
          id: 'events',
          name: 'Events',
          type: 'scatter',
          data: buildScatterData(events),
          symbolSize: 10,
          z: 5,
          label: {
            show: true,
            position: 'top',
            formatter: function (p) { return p.name; },
            fontSize: 10,
            color: '#0f172a'
          },
          itemStyle: {color: '#f59e0b', borderColor: '#ffffff', borderWidth: 1.5}
        }
      ]
    };
  }

  // Initial render
  chart.setOption(buildOption(currentTF));

  // ---- timeframe switch ----------------------------------------------------
  function setTF(tf) {
    if (!(tf in candlesByTF)) { return; }
    currentTF = tf;
    // Only replace the candlestick data; markLines / events stay intact
    chart.setOption({series: [{id: 'candles', data: buildCandleData(tf)}]});
    document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-tf') === tf);
    });
  }

  document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
    btn.addEventListener('click', function () { setTF(btn.getAttribute('data-tf')); });
  });

  // ---- reset zoom ----------------------------------------------------------
  var resetBtn = document.getElementById('%%CHART_ID%%-reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      chart.dispatchAction({type: 'dataZoom', start: 0, end: 100});
    });
  }

  // ---- resize --------------------------------------------------------------
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
        "<p style='font-size:16px;font-weight:700;margin-bottom:8px'>No market candles available for this trade</p>"
        "<p class='note'>Market data was not loaded for this signal. "
        "Levels and events are shown in tabular form below.</p>"
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
    candles_by_tf: dict[str, list[object]] = payload.get("candles_by_timeframe") or {}  # type: ignore[assignment]

    if not candles_by_tf:
        return _build_fallback(payload)

    meta = payload.get("meta") or {}
    default_tf: str | None = meta.get("default_timeframe")  # type: ignore[assignment]
    timeframes = list(candles_by_tf.keys())

    tf_buttons = _build_tf_buttons(chart_id, timeframes, default_tf)
    payload_json = json.dumps(payload, ensure_ascii=False)
    js_code = _CHART_JS.replace("%%CHART_ID%%", chart_id)

    return (
        f"<script src='{asset_path}'></script>\n"
        "<div class='chart-wrap'>\n"
        "  <div class='chart-toolbar'>\n"
        f"    {tf_buttons}\n"
        f"    <button id='{chart_id}-reset' class='chart-toolbar-btn' style='margin-left:auto'>Reset zoom</button>\n"
        "  </div>\n"
        f"  <div id='{chart_id}' style='width:100%;height:480px;min-height:320px'></div>\n"
        f"  <script type='application/json' id='{chart_id}_payload'>{payload_json}</script>\n"
        f"  <script>{js_code}</script>\n"
        "</div>\n"
    )
