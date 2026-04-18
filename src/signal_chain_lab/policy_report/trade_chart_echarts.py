"""Render the ECharts chart used by the single-trade report."""
from __future__ import annotations

import json

_CHART_JS = r"""
(function () {
  'use strict';

  var chartEl = document.getElementById('%%CHART_ID%%');
  var railEl = document.getElementById('%%CHART_ID%%_rail');
  var payloadEl = document.getElementById('%%CHART_ID%%_payload');
  var legendEl = document.getElementById('%%CHART_ID%%-legend');
  if (!chartEl || !payloadEl) { return; }

  var payload = JSON.parse(payloadEl.textContent || '{}');
  var candlesByTF = payload.candles_by_timeframe || {};
  var events = payload.events || [];
  var legendItems = payload.legend_items || [];
  var meta = payload.meta || {};
  var chartTimezone = String(meta.chart_timezone || 'UTC');
  var levelSegments = payload.level_segments || [];
  var currentTF = meta.default_timeframe || Object.keys(candlesByTF)[0] || '';
  var fillsCount = meta.fills_count || 0;
  var focusStartTs = meta.focus_start_ts ? new Date(meta.focus_start_ts).getTime() : null;
  var focusEndTs = meta.focus_end_ts ? new Date(meta.focus_end_ts).getTime() : null;
  // Visibility keyed by PRD event_code (prefix 'ev_' matches legend_items key format)
  var visibility = {
    volume: false,
    event_rail: true,
    entries_planned: true,
    avg_entry: false,
    sl: true,
    tps: true,
    // chart markers — REQUIRED (PRD §9)
    ev_ENTRY_FILLED_INITIAL:     true,
    ev_ENTRY_FILLED_SCALE_IN:    true,
    ev_EXIT_PARTIAL_TP:          true,
    ev_EXIT_PARTIAL_MANUAL:      true,
    ev_EXIT_FINAL_TP:            true,
    ev_EXIT_FINAL_SL:            true,
    ev_EXIT_FINAL_MANUAL:        true,
    // chart markers — OPTIONAL_LIGHT (PRD §9)
    ev_EXIT_FINAL_TIMEOUT:       true,
    // rail-only — Section A, chart_marker_kind = NONE
    ev_SETUP_CREATED:            true,
    ev_ENTRY_ORDER_ADDED:        true,
    ev_STOP_MOVED:               true,
    ev_BREAK_EVEN_ACTIVATED:     true,
    ev_PENDING_CANCELLED_TRADER: true,
    ev_PENDING_CANCELLED_ENGINE: true,
    ev_PENDING_TIMEOUT:          true,
    // Section B — excluded from rail; off by default
    ev_IGNORED:                  false,
    ev_SYSTEM_NOTE:              false
  };

  var chart = echarts.init(chartEl, null, {renderer: 'canvas'});
  var railChart = railEl ? echarts.init(railEl, null, {renderer: 'canvas'}) : null;
  var hoverGuard = false;
  var currentViewport = null;
  var applyingOptions = false;
  var hasUserZoomed = false;
  var programmaticZoomEventsPending = 0;
  var railLaneSpacingPx = 32;
  var railBasePaddingPx = 44;
  var railMinHeightPx = 140;
  var railMaxHeightPx = 460;

  function formatChartDateTime(value) {
    if (value === null || value === undefined || value === '') { return '-'; }
    var d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) { return String(value); }
    try {
      return new Intl.DateTimeFormat('sv-SE', {
        timeZone: chartTimezone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      }).format(d).replace(',', '') + ' ' + chartTimezone;
    } catch (err) {
      return d.getUTCFullYear()
        + '-' + String(d.getUTCMonth() + 1).padStart(2, '0')
        + '-' + String(d.getUTCDate()).padStart(2, '0')
        + ' '
        + String(d.getUTCHours()).padStart(2, '0')
        + ':' + String(d.getUTCMinutes()).padStart(2, '0')
        + ':' + String(d.getUTCSeconds()).padStart(2, '0')
        + ' UTC';
    }
  }

  function formatChartAxis(value) {
    if (value === null || value === undefined || value === '') { return ''; }
    var d = new Date(value);
    if (Number.isNaN(d.getTime())) { return String(value); }
    try {
      return new Intl.DateTimeFormat('en-GB', {
        timeZone: chartTimezone,
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).format(d);
    } catch (err) {
      return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0');
    }
  }

  function kindColor(event) {
    return (event && event.marker_color) || '#475569';
  }

  function kindSymbol(event) {
    return (event && event.marker_symbol) || 'circle';
  }

  function isAggregatedTF(tf) {
    return !!tf && tf !== '1m';
  }

  function getCandleTimes(tf) {
    return (candlesByTF[tf] || []).map(function (c) { return c[0]; });
  }

  function getTfBounds(tf) {
    var times = getCandleTimes(tf);
    if (!times.length) { return null; }
    return {start: times[0], end: times[times.length - 1]};
  }

  function clampViewportToTf(viewport, tf) {
    var bounds = getTfBounds(tf);
    if (!bounds) { return null; }
    if (!viewport || viewport.start == null || viewport.end == null) {
      return {start: bounds.start, end: bounds.end};
    }
    var start = Math.max(bounds.start, Math.min(viewport.start, bounds.end));
    var end = Math.max(start, Math.min(viewport.end, bounds.end));
    return {start: start, end: end};
  }

  function buildInitialViewport(tf) {
    var bounds = getTfBounds(tf);
    if (!bounds) { return null; }
    return {start: bounds.start, end: bounds.end};
  }

  function snapTimestampToVisibleBucket(ts, tf) {
    if (!isAggregatedTF(tf)) { return ts; }
    var times = getCandleTimes(tf);
    if (!times.length) { return ts; }
    var bucket = times[0];
    for (var i = 0; i < times.length; i++) {
      if (times[i] > ts) { break; }
      bucket = times[i];
    }
    return bucket;
  }

  function buildCandleData(tf) {
    return (candlesByTF[tf] || []).map(function (c) { return [c[0], c[1], c[2], c[3], c[4]]; });
  }

  function buildVolumeData(tf) {
    return (candlesByTF[tf] || []).map(function (c) { return [c[0], c[5] || 0, c[2] >= c[1] ? 1 : -1]; });
  }

  function buildPriceEvents() {
    // PRD §9: REQUIRED → placement='chart', OPTIONAL_LIGHT → placement='chart_optional'
    // Both appear on the chart; OPTIONAL_LIGHT gets reduced opacity and smaller symbol.
    // NONE → placement='rail' or 'section_b' → never shown as chart marker.
    return events
      .filter(function (event) {
        return (event.placement === 'chart' || event.placement === 'chart_optional')
          && event.price !== null
          && event.price !== undefined
          && visibility['ev_' + event.kind] !== false;
      })
      .map(function (event) {
        var anchorTs = event.chart_anchor_mode === 'candle_snapped'
          ? snapTimestampToVisibleBucket(event.ts, currentTF)
          : event.ts;
        var isOptional = event.placement === 'chart_optional';
        return {
          value: [anchorTs, event.price],
          exact_ts: event.exact_ts,
          event_id: event.event_id,
          kind: event.kind,
          summary: event.summary,
          source: event.source,
          label: event.label,
          reason: event.reason,
          impact: event.impact || {},
          isOptional: isOptional,
          itemStyle: {
            color: kindColor(event),
            borderColor: '#ffffff',
            borderWidth: isOptional ? 1 : 1.5,
            opacity: isOptional ? 0.55 : 1
          },
          symbol: kindSymbol(event)
        };
      });
  }

  function buildRailData() {
    // PRD §7 Step 7: rail shows only Section A events (placement === 'rail').
    // Section B events (IGNORED, SYSTEM_NOTE) have placement === 'section_b' → excluded here.
    // Chart-marker events (placement === 'chart' / 'chart_optional') are not duplicated in rail.
    var laneOrder = [];
    var laneIndexByKey = {};
    return events
      .filter(function (event) {
        return event.placement !== 'section_b';
      })
      .map(function (event) {
        var anchorTs = event.chart_anchor_mode === 'candle_snapped'
          ? snapTimestampToVisibleBucket(event.ts, currentTF)
          : event.ts;
        var laneKey = String(event.lane_key || event.event_code || event.kind || 'event');
        if (laneIndexByKey[laneKey] === undefined) {
          laneIndexByKey[laneKey] = laneOrder.length;
          laneOrder.push(laneKey);
        }
        var lane = laneIndexByKey[laneKey] + 1;
        return {
          value: [anchorTs, lane],
          exact_ts: event.exact_ts,
          event_id: event.event_id,
          kind: event.kind,
          summary: event.summary,
          label: event.label,
          rail_label: event.rail_label || event.label,
          reason: event.reason,
          lane_key: laneKey,
          marker_color: event.marker_color,
          marker_symbol: event.marker_symbol
        };
      });
  }

  function captureViewportFromOption(option, tf) {
    var dataZoom = option && option.dataZoom ? option.dataZoom[0] : null;
    var bounds = getTfBounds(tf);
    if (!dataZoom || !bounds) { return null; }
    if (dataZoom.startValue != null && dataZoom.endValue != null) {
      return clampViewportToTf({
        start: Number(dataZoom.startValue),
        end: Number(dataZoom.endValue)
      }, tf);
    }
    var startPct = dataZoom.start != null ? Number(dataZoom.start) : 0;
    var endPct = dataZoom.end != null ? Number(dataZoom.end) : 100;
    var span = bounds.end - bounds.start;
    return clampViewportToTf({
      start: bounds.start + (span * startPct / 100),
      end: bounds.start + (span * endPct / 100)
    }, tf);
  }

  function applyViewport(viewport) {
    var activeViewport = clampViewportToTf(viewport || currentViewport || buildInitialViewport(currentTF), currentTF);
    if (!activeViewport) { return; }
    currentViewport = activeViewport;
    programmaticZoomEventsPending = railChart ? 2 : 1;
    chart.dispatchAction({
      type: 'dataZoom',
      startValue: activeViewport.start,
      endValue: activeViewport.end
    });
    if (railChart) {
      railChart.dispatchAction({
        type: 'dataZoom',
        startValue: activeViewport.start,
        endValue: activeViewport.end
      });
    }
  }

  function currentVisibleViewport() {
    if (!hasUserZoomed) {
      return clampViewportToTf(buildInitialViewport(currentTF), currentTF);
    }
    return clampViewportToTf(currentViewport || buildInitialViewport(currentTF), currentTF);
  }

  function computePriceAxisRange() {
    var candles = candlesByTF[currentTF] || [];
    if (!candles.length) { return null; }
    var viewport = currentVisibleViewport();
    var visible = candles.filter(function (c) {
      if (!viewport) { return true; }
      return c[0] >= viewport.start && c[0] <= viewport.end;
    });
    if (!visible.length) {
      visible = candles;
    }

    var lows = visible.map(function (c) { return Number(c[3]); }).filter(function (v) { return Number.isFinite(v); });
    var highs = visible.map(function (c) { return Number(c[4]); }).filter(function (v) { return Number.isFinite(v); });

    // Include visible level prices so off-candle targets/stops remain visible.
    var levelVisibility = {
      'ENTRY_LIMIT': visibility.entries_planned !== false,
      'ENTRY_MARKET': false,
      'AVG_ENTRY': visibility.avg_entry !== false,
      'SL': visibility.sl !== false,
      'TP': visibility.tps !== false
    };
    levelSegments.forEach(function (segment) {
      var segmentKind = String(segment && segment.kind ? segment.kind : '');
      if (!levelVisibility[segmentKind]) { return; }
      var tsStart = new Date(segment.ts_start).getTime();
      var tsEnd = new Date(segment.ts_end).getTime();
      if (Number.isNaN(tsStart) || Number.isNaN(tsEnd)) { return; }
      if (viewport && (tsEnd < viewport.start || tsStart > viewport.end)) { return; }
      var levelPrice = Number(segment.price);
      if (!Number.isFinite(levelPrice)) { return; }
      lows.push(levelPrice);
      highs.push(levelPrice);
    });

    if (!lows.length || !highs.length) { return null; }
    var minValue = Math.min.apply(null, lows);
    var maxValue = Math.max.apply(null, highs);
    if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) { return null; }
    var span = maxValue - minValue;
    var padding = span > 0 ? span * 0.08 : Math.max(Math.abs(maxValue) * 0.02, 0.0001);
    return {
      min: minValue - padding,
      max: maxValue + padding
    };
  }

  function makeLevelRenderItem(color) {
    return function (params, api) {
      var tsStart = api.value(0);
      var tsEnd = api.value(1);
      var price = api.value(2);
      var label = String(api.value(3) || '');
      var style = String(api.value(4) || 'dashed');
      var prevPrice = api.value(5);
      var ptStart = api.coord([tsStart, price]);
      var ptEnd = api.coord([tsEnd, price]);
      var x0 = ptStart[0];
      var x1 = ptEnd[0];
      var y = ptStart[1];
      var cs = params.coordSys;
      var lineDash = style === 'dashed' ? [6, 4] : [];
      var clip = {x: cs.x, y: cs.y, width: cs.width, height: cs.height};
      var children = [];

      if (prevPrice !== null && prevPrice !== undefined) {
        var prevPt = api.coord([tsStart, prevPrice]);
        children.push({
          type: 'line',
          shape: {x1: x0, y1: prevPt[1], x2: x0, y2: y},
          style: {stroke: color, lineWidth: 1.6, lineDash: lineDash},
          clipPath: {type: 'rect', shape: clip}
        });
      }

      children.push({
        type: 'line',
        shape: {x1: x0, y1: y, x2: x1, y2: y},
        style: {stroke: color, lineWidth: 1.6, lineDash: lineDash},
        clipPath: {type: 'rect', shape: clip}
      });

      var visibleX0 = Math.max(x0, cs.x);
      var visibleX1 = Math.min(x1, cs.x + cs.width);
      if (label && visibleX1 > visibleX0) {
        children.push({
          type: 'text',
          x: (visibleX0 + visibleX1) / 2,
          y: Math.max(cs.y + 10, Math.min(y - 6, cs.y + cs.height - 10)),
          style: {
            text: label,
            textAlign: 'center',
            textVerticalAlign: 'bottom',
            fill: color,
            fontSize: 10,
            backgroundColor: 'rgba(255,255,255,.9)',
            padding: [2, 4],
            borderRadius: 4
          }
        });
      }

      return {type: 'group', children: children};
    };
  }

  function buildLevelSeries() {
    var groups = {};
    levelSegments.forEach(function (segment) {
      groups[segment.kind] = groups[segment.kind] || [];
      groups[segment.kind].push(segment);
    });
    var kindVisibilityMap = {
      'ENTRY_LIMIT': 'entries_planned',
      'ENTRY_MARKET': 'entry_market',
      'AVG_ENTRY': 'avg_entry',
      'SL': 'sl',
      'TP': 'tps'
    };
    var colors = {
      'ENTRY_LIMIT': '#1d4ed8',
      'ENTRY_MARKET': '#7c3aed',
      'AVG_ENTRY': '#0891b2',
      'SL': '#b91c1c',
      'TP': '#15803d'
    };

    return Object.keys(groups).map(function (kind) {
      if (kind === 'AVG_ENTRY' && fillsCount < 2) { return null; }
      if (visibility[kindVisibilityMap[kind]] === false) { return null; }
      var segments = groups[kind];
      return {
        id: 'level_' + kind,
        name: kind,
        type: 'custom',
        renderItem: makeLevelRenderItem(colors[kind] || '#64748b'),
        encode: {
          x: [0, 1],
          y: 2,
          tooltip: [2]
        },
        xAxisIndex: 0,
        yAxisIndex: 0,
        z: 3,
        data: segments.map(function (segment, index) {
          var tsStart = new Date(segment.ts_start).getTime();
          var tsEnd = new Date(segment.ts_end).getTime();
          if (isAggregatedTF(currentTF)) {
            tsStart = snapTimestampToVisibleBucket(tsStart, currentTF);
            tsEnd = snapTimestampToVisibleBucket(tsEnd, currentTF);
          }
          var prevPrice = (kind === 'SL' && index > 0) ? segments[index - 1].price : null;
          return {
            value: [
              tsStart,
              tsEnd,
              segment.price,
              segment.label || kind,
              segment.style || 'dashed',
              prevPrice
            ],
            logical_start: segment.ts_start,
            logical_end: segment.ts_end,
            kind: segment.kind,
            label: segment.label
          };
        }),
        tooltip: {
          trigger: 'item',
          formatter: function (params) {
            var item = params.data || {};
            return '<b>' + (item.label || item.kind || '') + '</b><br/>'
              + 'Price: ' + Number(item.value[2]).toFixed(6) + '<br/>'
              + 'Range: ' + formatChartDateTime(item.logical_start) + ' → ' + formatChartDateTime(item.logical_end);
          }
        }
      };
    }).filter(Boolean);
  }

  function syncPointer(ts) {
    if (!ts || hoverGuard) { return; }
    hoverGuard = true;
    var axisValue = typeof ts === 'number' ? ts : new Date(ts).getTime();
    chart.dispatchAction({type: 'updateAxisPointer', xAxisIndex: 0, value: axisValue});
    if (railChart) {
      railChart.dispatchAction({type: 'updateAxisPointer', xAxisIndex: 0, value: axisValue});
    }
    hoverGuard = false;
  }

  function refreshPriceAxisRange() {
    var priceAxisRange = computePriceAxisRange();
    if (!priceAxisRange) { return; }
    chart.setOption({
      yAxis: [{
        min: priceAxisRange.min,
        max: priceAxisRange.max
      }]
    });
  }

  function buildChartOption() {
    var showVolume = !!visibility.volume;
    var priceAxisRange = computePriceAxisRange();
    var viewport = currentVisibleViewport();
    var zoomConfig = viewport ? {startValue: viewport.start, endValue: viewport.end} : {};
    var grids = [{left: 72, right: 24, top: 52, bottom: showVolume ? 144 : 76}];
    var xAxes = [{
      type: 'time',
      scale: true,
      min: viewport ? viewport.start : null,
      max: viewport ? viewport.end : null,
      axisLabel: {formatter: formatChartAxis},
      axisPointer: {show: true, snap: false},
      splitLine: {show: false}
    }];
    var yAxes = [{
      type: 'value',
      scale: true,
      min: priceAxisRange ? priceAxisRange.min : null,
      max: priceAxisRange ? priceAxisRange.max : null,
      splitLine: {lineStyle: {color: '#e2e8f0'}}
    }];
    var series = [{
      id: 'candles',
      name: 'Candles',
      type: 'candlestick',
      xAxisIndex: 0,
      yAxisIndex: 0,
      encode: {
        x: 0,
        y: [1, 2, 3, 4],
        tooltip: [1, 2, 3, 4]
      },
      data: buildCandleData(currentTF),
      itemStyle: {
        color: '#15803d',
        color0: '#b91c1c',
        borderColor: '#15803d',
        borderColor0: '#b91c1c'
      }
    }]
      .concat(buildLevelSeries())
      .concat([{
        id: 'price_events',
        name: 'Events',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        encode: {
          x: 0,
          y: 1,
          tooltip: [1]
        },
        symbolSize: function (val, params) {
          return (params.data && params.data.isOptional) ? 9 : 12;
        },
        z: 5,
        data: buildPriceEvents()
      }]);

    if (showVolume) {
      grids.push({left: 72, right: 24, height: 64, bottom: 38});
      xAxes.push({
        type: 'time',
        gridIndex: 1,
        min: viewport ? viewport.start : null,
        max: viewport ? viewport.end : null,
        axisLabel: {show: false},
        splitLine: {show: false}
      });
      yAxes.push({
        type: 'value',
        gridIndex: 1,
        axisLabel: {show: false},
        splitLine: {show: false}
      });
      series.push({
        id: 'volume',
        name: 'Volume',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        encode: {
          x: 0,
          y: 1,
          tooltip: [1]
        },
        data: buildVolumeData(currentTF),
        itemStyle: {
          color: function (params) {
            return params.data[2] >= 0 ? 'rgba(21,128,61,.5)' : 'rgba(185,28,28,.5)';
          }
        }
      });
    }

    return {
      animation: false,
      axisPointer: {
        link: [{xAxisIndex: 'all'}],
        label: {formatter: function (params) { return formatChartDateTime(params.value); }}
      },
      tooltip: {
        trigger: 'item',
        formatter: function (params) {
          var data = params.data || {};
          if (params.seriesType === 'candlestick' && params.data) {
            return '<b>' + formatChartDateTime(params.data[0]) + '</b><br/>'
              + 'O: ' + Number(params.data[1]).toFixed(6) + ' '
              + 'C: ' + Number(params.data[2]).toFixed(6) + '<br/>'
              + 'L: ' + Number(params.data[3]).toFixed(6) + ' '
              + 'H: ' + Number(params.data[4]).toFixed(6);
          }
          if (params.seriesId === 'price_events') {
            var impact = data.impact || {};
            return '<b style="color:' + kindColor(data) + '">' + (data.label || data.kind || '') + '</b><br/>'
              + 'Event time: ' + formatChartDateTime(data.exact_ts) + '<br/>'
              + 'Chart bucket: ' + formatChartDateTime(data.value[0]) + '<br/>'
              + 'Price: ' + Number(data.value[1]).toFixed(6) + '<br/>'
              + 'Summary: ' + (data.summary || '-') + '<br/>'
              + 'Source: ' + (data.source || '-') + '<br/>'
              + 'Position impact: ' + (impact.position != null ? impact.position : '-') + '<br/>'
              + 'Risk impact: ' + (impact.risk != null ? impact.risk : '-') + '<br/>'
              + 'Result impact: ' + (impact.result != null ? impact.result : '-');
          }
          return '';
        }
      },
      dataZoom: [
        Object.assign({type: 'inside', xAxisIndex: showVolume ? [0, 1] : [0], filterMode: 'weakFilter'}, zoomConfig),
        Object.assign({type: 'slider', xAxisIndex: showVolume ? [0, 1] : [0], bottom: 6, height: 24}, zoomConfig)
      ],
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      series: series
    };
  }

  function buildRailOption() {
    var railData = buildRailData();
    var laneCount = railData.reduce(function (maxLane, item) {
      return Math.max(maxLane, Number(item.value[1]) || 0);
    }, 0);
    var axisMin = 0;
    var axisMax = Math.max(laneCount + 0.5, 1.5);
    var viewport = currentVisibleViewport();
    return {
      animation: false,
      axisPointer: {
        link: [{xAxisIndex: 'all'}],
        label: {formatter: function (params) { return formatChartDateTime(params.value); }}
      },
      tooltip: {
        trigger: 'item',
        formatter: function (params) {
          var data = params.data || {};
          return '<b style="color:' + kindColor(data) + '">' + (data.rail_label || data.label || data.kind || '') + '</b><br/>'
            + 'Event time: ' + formatChartDateTime(data.exact_ts) + '<br/>'
            + 'Summary: ' + (data.summary || '-');
        }
      },
      grid: {left: 72, right: 24, top: 14, bottom: 52},
      xAxis: {
        type: 'time',
        min: viewport ? viewport.start : null,
        max: viewport ? viewport.end : null,
        axisLabel: {formatter: formatChartAxis, margin: 14},
        axisPointer: {show: true},
        splitLine: {show: false}
      },
      yAxis: {
        type: 'value',
        min: axisMin,
        max: axisMax,
        interval: 1,
        axisLabel: {show: false},
        axisTick: {show: false},
        axisLine: {show: false},
        splitLine: {
          show: true,
          lineStyle: {
            color: 'rgba(148, 163, 184, 0.26)',
            type: 'dashed',
            width: 1
          }
        }
      },
      dataZoom: [
        {type: 'inside', xAxisIndex: [0], filterMode: 'none'}
      ],
      series: [{
        id: 'rail_events',
        type: 'scatter',
        encode: {
          x: 0,
          y: 1,
          tooltip: [1]
        },
        data: railData,
        symbol: function (value, params) {
          return kindSymbol(params && params.data ? params.data : null);
        },
        symbolSize: 9,
        itemStyle: {color: function (params) { return kindColor(params.data); }},
        label: {
          show: true,
          position: 'top',
          distance: 4,
          color: '#334155',
          fontSize: 9,
          backgroundColor: 'rgba(255,255,255,0.82)',
          padding: [1, 4],
          borderRadius: 4,
          formatter: function (params) {
            var label = params && params.data ? params.data.rail_label : '';
            return label || '';
          }
        },
        emphasis: {
          label: {
            show: true
          }
        },
        z: 4
      }]
    };
  }

  function updateRailHeight() {
    if (!railEl || !railChart) { return; }
    var laneCount = buildRailData().reduce(function (maxLane, item) {
      return Math.max(maxLane, Number(item.value[1]) || 0);
    }, -1) + 1;
    var visibleLaneCount = Math.max(laneCount, 1);
    var height = Math.max(
      railMinHeightPx,
      Math.min(visibleLaneCount * railLaneSpacingPx + railBasePaddingPx, railMaxHeightPx)
    );
    railEl.style.height = height + 'px';
    railEl.style.minHeight = railMinHeightPx + 'px';
    railChart.resize();
  }

  function applyOptions() {
    if (!applyingOptions) {
      currentViewport = captureViewportFromOption(chart.getOption() || {}, currentTF) || currentViewport;
    }
    applyingOptions = true;
    chart.setOption(buildChartOption(), {replaceMerge: ['series', 'grid', 'xAxis', 'yAxis']});
    if (railChart) {
      if (visibility.event_rail) {
        railEl.style.display = '';
        updateRailHeight();
        railChart.setOption(buildRailOption(), {replaceMerge: ['series', 'xAxis', 'yAxis']});
        railChart.resize();
      } else {
        railEl.style.display = 'none';
      }
    }
    applyViewport(currentViewport);
    applyingOptions = false;
  }

  function buildLegend() {
    if (!legendEl) { return; }
    legendEl.innerHTML = '';
    legendItems.forEach(function (item) {
      var node = document.createElement('div');
      node.className = 'chart-legend-item' + (visibility[item.key] === false ? ' dimmed' : '');

      var swatch = document.createElement('span');
      if (item.shape === 'line') {
        swatch.className = 'chart-legend-swatch';
        if (item.line_style === 'dashed') {
          swatch.style.backgroundImage = 'repeating-linear-gradient(to right,' + item.color + ' 0,' + item.color + ' 4px,transparent 4px,transparent 7px)';
        } else {
          swatch.style.background = item.color;
          swatch.style.backgroundImage = 'none';
        }
      } else {
        var symbol = String(item.symbol || 'circle').toLowerCase();
        swatch.className = 'chart-legend-marker sym-' + symbol;
        swatch.style.background = item.color;
        swatch.style.setProperty('--marker-color', item.color);
      }
      var text = document.createElement('span');
      text.textContent = item.label;
      node.appendChild(swatch);
      node.appendChild(text);
      node.addEventListener('click', function () {
        visibility[item.key] = !(visibility[item.key] !== false);
        node.classList.toggle('dimmed', visibility[item.key] === false);
        applyOptions();
      });
      legendEl.appendChild(node);
    });
  }

  function focusEventById(eventId) {
    if (!eventId) { return; }
    var priceEvents = buildPriceEvents();
    var railEvents = buildRailData();
    priceEvents.forEach(function (event, index) {
      if (event.event_id === eventId) {
        syncPointer(event.exact_ts);
        chart.dispatchAction({type: 'showTip', seriesId: 'price_events', dataIndex: index});
      }
    });
    railEvents.forEach(function (event, index) {
      if (railChart && event.event_id === eventId) {
        syncPointer(event.exact_ts);
        railChart.dispatchAction({type: 'showTip', seriesId: 'rail_events', dataIndex: index});
      }
    });
  }

  function wireToolbarButton(id, key) {
    var node = document.getElementById('%%CHART_ID%%-' + id);
    if (!node) { return; }
    node.classList.toggle('active', !!visibility[key]);
    node.addEventListener('click', function () {
      visibility[key] = !visibility[key];
      node.classList.toggle('active', !!visibility[key]);
      applyOptions();
    });
  }

  wireToolbarButton('toggle-volume', 'volume');
  wireToolbarButton('toggle-event-rail', 'event_rail');

  document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (node) {
    node.addEventListener('click', function () {
      var option = chart.getOption() || {};
      currentViewport = captureViewportFromOption(option, currentTF) || currentViewport;
      currentTF = node.getAttribute('data-tf') || currentTF;
      currentViewport = clampViewportToTf(currentViewport || buildInitialViewport(currentTF), currentTF);
      document.querySelectorAll('.%%CHART_ID%%-tf').forEach(function (btn) {
        btn.classList.toggle('active', btn === node);
      });
      applyOptions();
    });
  });

  var resetBtn = document.getElementById('%%CHART_ID%%-reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      currentViewport = buildInitialViewport(currentTF);
      hasUserZoomed = false;
      applyViewport(currentViewport);
      refreshPriceAxisRange();
    });
  }

  chart.on('click', function (params) {
    var eventId = params && params.data ? params.data.event_id : null;
    if (eventId) {
      window.dispatchEvent(new CustomEvent('trade-event-focus', {detail: {eventId: eventId}}));
    }
  });
  chart.on('mouseover', function (params) {
    var eventId = params && params.data ? params.data.event_id : null;
    var exactTs = params && params.data ? params.data.exact_ts : null;
    if (exactTs) { syncPointer(exactTs); }
    if (eventId) {
      window.dispatchEvent(new CustomEvent('trade-event-hover', {detail: {eventId: eventId}}));
    }
  });
  if (railChart) {
    railChart.on('click', function (params) {
      var eventId = params && params.data ? params.data.event_id : null;
      if (eventId) {
        window.dispatchEvent(new CustomEvent('trade-event-focus', {detail: {eventId: eventId}}));
      }
    });
    railChart.on('mouseover', function (params) {
      var eventId = params && params.data ? params.data.event_id : null;
      var exactTs = params && params.data ? params.data.exact_ts : null;
      if (exactTs) { syncPointer(exactTs); }
      if (eventId) {
        window.dispatchEvent(new CustomEvent('trade-event-hover', {detail: {eventId: eventId}}));
      }
    });
  }

  window.addEventListener('trade-event-select', function (evt) {
    var eventId = evt && evt.detail ? evt.detail.eventId : null;
    focusEventById(eventId);
  });

  var syncingZoom = false;
  chart.on('dataZoom', function () {
    if (programmaticZoomEventsPending > 0) {
      var programmaticOption = chart.getOption() || {};
      currentViewport = captureViewportFromOption(programmaticOption, currentTF) || currentViewport;
      programmaticZoomEventsPending -= 1;
      return;
    }
    if (!railChart || syncingZoom || applyingOptions) { return; }
    var option = chart.getOption() || {};
    currentViewport = captureViewportFromOption(option, currentTF) || currentViewport;
    if (!currentViewport) { return; }
    hasUserZoomed = true;
    refreshPriceAxisRange();
    syncingZoom = true;
    railChart.dispatchAction({
      type: 'dataZoom',
      startValue: currentViewport.start,
      endValue: currentViewport.end
    });
    syncingZoom = false;
  });
  if (railChart) {
    railChart.on('dataZoom', function () {
      if (programmaticZoomEventsPending > 0) {
        var programmaticOption = railChart.getOption() || {};
        currentViewport = captureViewportFromOption(programmaticOption, currentTF) || currentViewport;
        programmaticZoomEventsPending -= 1;
        return;
      }
      if (syncingZoom || applyingOptions) { return; }
      var option = railChart.getOption() || {};
      currentViewport = captureViewportFromOption(option, currentTF) || currentViewport;
      if (!currentViewport) { return; }
      hasUserZoomed = true;
      refreshPriceAxisRange();
      syncingZoom = true;
      chart.dispatchAction({
        type: 'dataZoom',
        startValue: currentViewport.start,
        endValue: currentViewport.end
      });
      syncingZoom = false;
    });
  }

  buildLegend();
  applyOptions();

  window.addEventListener('resize', function () {
    chart.resize();
    if (railChart) { railChart.resize(); }
  });
}());
"""


def _build_tf_buttons(chart_id: str, timeframes: list[str], default_tf: str | None) -> str:
    parts: list[str] = []
    for timeframe in timeframes:
        active = "active" if timeframe == default_tf else ""
        parts.append(
            f"<button type='button' class='chart-toolbar-btn {chart_id}-tf {active}' data-tf='{timeframe}'>{timeframe}</button>"
        )
    return "".join(parts)


def _build_toggle_buttons(chart_id: str) -> str:
    toggles = [
        ("toggle-volume", "Volume", False),
        ("toggle-event-rail", "Event rail", True),
    ]
    return "".join(
        f"<button id='{chart_id}-{button_id}' class='chart-toolbar-btn {'active' if enabled else ''}'>{label}</button>"
        for button_id, label, enabled in toggles
    )


def _build_fallback(payload: dict[str, object]) -> str:
    events = payload.get("events") or []
    rows = "".join(
        "<tr>"
        f"<td>{event.get('label', '')}</td>"
        f"<td>{event.get('placement', '')}</td>"
        f"<td>{event.get('summary', '')}</td>"
        "</tr>"
        for event in events
    ) or "<tr><td colspan='3'>-</td></tr>"
    return (
        "<div class='card'>"
        "<p class='note'>No market candles available</p>"
        "</div>"
        "<div class='card'>"
        "<h2>Events</h2>"
        "<table><thead><tr><th>Event</th><th>Placement</th><th>Summary</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "</div>"
    )


def render_trade_chart_echarts(
    payload: dict[str, object],
    *,
    chart_id: str,
    asset_path: str,
) -> str:
    candles_by_timeframe: dict[str, list[object]] = payload.get("candles_by_timeframe") or {}
    if not candles_by_timeframe:
        return _build_fallback(payload)

    meta = payload.get("meta") or {}
    default_timeframe: str | None = meta.get("default_timeframe")
    timeframes = list(candles_by_timeframe.keys())
    payload_json = json.dumps(payload, ensure_ascii=False)
    js_code = _CHART_JS.replace("%%CHART_ID%%", chart_id)

    return (
        f"<script src='{asset_path}'></script>"
        "<div class='card chart-wrap'>"
        "<div class='chart-toolbar' style='flex-wrap:wrap;gap:6px'>"
        f"{_build_tf_buttons(chart_id, timeframes, default_timeframe)}"
        "<span style='width:1px;background:#e2e8f0;align-self:stretch;margin:0 4px'></span>"
        f"{_build_toggle_buttons(chart_id)}"
        f"<button id='{chart_id}-reset' class='chart-toolbar-btn' style='margin-left:auto'>Reset zoom</button>"
        "</div>"
        f"<div id='{chart_id}-legend' class='chart-legend'></div>"
        f"<div id='{chart_id}' style='width:100%;height:540px;min-height:340px'></div>"
        f"<div id='{chart_id}_rail' style='width:100%;height:168px;min-height:120px;margin-top:8px'></div>"
        f"<script type='application/json' id='{chart_id}_payload'>{payload_json}</script>"
        f"<script>{js_code}</script>"
        "</div>"
    )
