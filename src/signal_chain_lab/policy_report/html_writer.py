"""HTML writers for PRD-aligned policy and single-trade reports."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult
from src.signal_chain_lab.market.data_models import Candle
from src.signal_chain_lab.policy_report.trade_chart_echarts import render_trade_chart_echarts
from src.signal_chain_lab.policy_report.trade_chart_payload import build_trade_chart_payload

if TYPE_CHECKING:
    from src.signal_chain_lab.policies.base import PolicyConfig
    from src.signal_chain_lab.policy_report.comparison_runner import ChangedTrade


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _fmt_percent(value: float | int | None, *, signed: bool = True, digits: int = 2) -> str:
    if value is None:
        return "-"
    number = float(value)
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.{digits}f}%"


def _fmt_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}"


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    hours = s // 3600
    minutes = (s % 3600) // 60
    return f"{hours}h {minutes}m"


def _fmt_timestamp(value: object) -> str:
    if value in (None, ""):
        return "-"
    text = str(value)
    return text.replace("T", " ").replace("+00:00", " UTC")


def _safe_dom_id(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"_", "-"}:
            safe.append(char)
        else:
            safe.append("_")
    return "".join(safe) or "item"


def _escape(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _badge_class_for_percent(value: float | int | None) -> str:
    if value is None:
        return "muted"
    number = float(value)
    if number > 0:
        return "ok"
    if number < 0:
        return "bad"
    return "muted"


def _badge_class_for_number(value: float | int | None) -> str:
    if value is None:
        return "muted"
    number = float(value)
    if number > 0:
        return "ok"
    if number < 0:
        return "bad"
    return "muted"


# ---------------------------------------------------------------------------
# Base styles + shared JS
# ---------------------------------------------------------------------------

def _base_styles() -> str:
    return """
<style>
:root{
  --bg:#f8fafc;--card:#ffffff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;
  --accent:#0f766e;--blue:#1d4ed8;--green:#15803d;--red:#b91c1c;--orange:#c2410c;
}
*{box-sizing:border-box}
body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text)}
.wrap{max-width:1280px;margin:0 auto;padding:24px}
h1{font-size:28px;margin:0 0 18px}
h2{font-size:18px;margin:0 0 12px;font-weight:700}
h3{font-size:14px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:0 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin-bottom:18px;box-shadow:0 2px 10px rgba(15,23,42,.04)}
.sticky{position:sticky;top:0;z-index:20}
.grid-4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.metric{border:1px solid var(--line);border-radius:12px;padding:14px;background:#fff}
.metric .k{font-size:11px;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em}
.metric .v{font-size:22px;font-weight:700}
.metric .v.small{font-size:16px}
.metric .v.ok{color:var(--green)}
.metric .v.bad{color:var(--red)}
.metric-group{margin-bottom:18px}
.metric-group-title{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:8px;padding-left:2px}
details.card summary{cursor:pointer;font-weight:700;list-style:none}
details.card summary::-webkit-details-marker{display:none}
details.card summary:after{content:'Show';float:right;font-weight:600;color:var(--muted)}
details[open].card summary:after{content:'Hide'}
table{width:100%;border-collapse:collapse}
th,td{padding:10px 9px;border-bottom:1px solid var(--line);text-align:left;font-size:13px;vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.th-sort{cursor:pointer;user-select:none}
.th-sort:hover{color:var(--blue)}
.badge{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:700}
.ok{background:#dcfce7;color:#166534}.bad{background:#fee2e2;color:#991b1b}.muted{background:#e2e8f0;color:#334155}
.ok-text{color:var(--green);font-weight:700}
.bad-text{color:var(--red);font-weight:700}
.link{color:var(--blue);text-decoration:none;font-weight:600}
.note{color:var(--muted);font-size:13px}
.code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;white-space:pre-wrap;background:#f8fafc;border:1px solid var(--line);border-radius:12px;padding:14px}
button.inline-btn, a.inline-btn{border:1px solid var(--line);background:#fff;border-radius:10px;padding:7px 10px;font-size:13px;cursor:pointer;color:var(--blue);text-decoration:none}
dialog{border:none;border-radius:14px;padding:0;max-width:780px;width:92%;box-shadow:0 20px 60px rgba(2,6,23,.35)}
dialog::backdrop{background:rgba(15,23,42,.55)}
.dialog-head{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
.dialog-body{padding:18px}
.timeline{display:grid;gap:10px}
.timeline-item{border:1px solid var(--line);border-radius:14px;background:#fff;overflow:hidden}
.timeline-item[open]{box-shadow:0 6px 24px rgba(15,23,42,.06)}
.timeline-item summary{list-style:none;cursor:pointer;padding:12px 14px}
.timeline-item summary::-webkit-details-marker{display:none}
.tl-row{display:grid;grid-template-columns:84px 1.2fr 132px 116px 1fr;gap:10px;align-items:center}
.tl-time{font-size:12px;font-weight:700;color:var(--muted)}
.tl-main{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
.tl-event{font-size:14px;font-weight:800}
.tl-requested,.tl-reason{font-size:12px;color:var(--muted);font-weight:600}
.tl-pills{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.ti-body{border-top:1px solid var(--line);background:#fcfdff;padding:14px}
.ti-body-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ti-panel{border:1px solid var(--line);border-radius:12px;background:#fff;padding:12px}
.ti-panel h3{margin:0 0 10px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.ti-meta{display:grid;grid-template-columns:140px 1fr;gap:6px 10px;font-size:13px}
.ti-meta .lab{color:var(--muted)}
.ti-delta{display:flex;gap:6px;flex-wrap:wrap}
.ti-delta-item{font-size:12px;background:#f1f5f9;border-radius:999px;padding:4px 9px}
.ti-delta-item .dlab{color:var(--muted);margin-right:3px}
.chart-wrap{border:1px solid var(--line);border-radius:14px;padding:10px;background:#fff}
.chart-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.chart-toolbar-btn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:4px 9px;cursor:pointer;font-size:13px}
.chart-toolbar-btn.active{background:#dbeafe;border-color:#93c5fd;color:#1e3a8a;font-weight:700}
.footer-nav{margin-top:20px}
.charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
.charts-full{margin-bottom:18px}
/* extended column toggles
   col 5=Net%  col6=Gross%  col7=CumEq%  col8=MAE%  col9=MFE%  col10=Capture%
   col11=Fees  col12=R  col13=Warn  col14=Created  col15=Closed  col16=Detail
   nth-child is 1-based so col5 → nth-child(6), col6 → nth-child(7), etc. */
#trade-results-table.hide-gross   td:nth-child(7), #trade-results-table.hide-gross   th:nth-child(7){display:none}
#trade-results-table.hide-cumEq   td:nth-child(8), #trade-results-table.hide-cumEq   th:nth-child(8){display:none}
#trade-results-table.hide-mae     td:nth-child(9), #trade-results-table.hide-mae     th:nth-child(9){display:none}
#trade-results-table.hide-mfe     td:nth-child(10),#trade-results-table.hide-mfe     th:nth-child(10){display:none}
#trade-results-table.hide-capture td:nth-child(11),#trade-results-table.hide-capture th:nth-child(11){display:none}
#trade-results-table.hide-fees    td:nth-child(12),#trade-results-table.hide-fees    th:nth-child(12){display:none}
#trade-results-table.hide-r       td:nth-child(13),#trade-results-table.hide-r       th:nth-child(13){display:none}
/* excluded chains filter */
.excl-reason-bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
.excl-badge{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:700;cursor:pointer;border:1px solid transparent}
.excl-badge.active{border-color:var(--accent);outline:2px solid var(--accent)}
/* event timeline source/status labels */
.ti-src-trader{display:inline-block;font-size:11px;font-weight:700;color:#166534;background:#dcfce7;border-radius:999px;padding:3px 8px}
.ti-src-system{display:inline-block;font-size:11px;color:#4338ca;background:#eef2ff;border-radius:999px;padding:3px 8px}
.ti-status-applied{display:inline-block;font-size:11px;font-weight:700;color:#166534;background:#dcfce7;border-radius:999px;padding:3px 8px}
.ti-status-generated{display:inline-block;font-size:11px;font-weight:700;color:#9a3412;background:#ffedd5;border-radius:999px;padding:3px 8px}
.ti-status-ignored,.ti-status-rejected{display:inline-block;font-size:11px;font-weight:700;color:#991b1b;background:#fee2e2;border-radius:999px;padding:3px 8px}
@media(max-width:900px){
  .grid-4{grid-template-columns:repeat(2,minmax(0,1fr))}
  .grid-3{grid-template-columns:repeat(2,minmax(0,1fr))}
  .tl-row{grid-template-columns:1fr}
  .tl-pills{justify-content:flex-start}
  .ti-body-grid{grid-template-columns:1fr}
  .ti-meta{grid-template-columns:1fr}
  .charts-grid{grid-template-columns:1fr}
}
</style>
<script>
function openText(id){ document.getElementById(id).showModal(); }
function closeText(id){ document.getElementById(id).close(); }
// ---- trade table sort ----
let __tradeSortState = { key: "created", dir: "desc" };
function __textValue(cell){
  return (cell?.dataset?.sort || cell?.innerText || "").trim().toLowerCase();
}
function __numberValue(cell){
  const raw = (cell?.dataset?.sort || cell?.innerText || "0").replace("%","").replace(",",".").trim();
  const val = Number(raw);
  return Number.isFinite(val) ? val : 0;
}
function __sortTradeRows(){
  const table = document.getElementById("trade-results-table");
  if(!table) return;
  const body = table.querySelector("tbody");
  if(!body) return;
  const rows = Array.from(body.querySelectorAll("tr"));
  const key = __tradeSortState.key;
  const dir = __tradeSortState.dir === "asc" ? 1 : -1;
  const colByKey = {
    signal:0, symbol:1, side:2, status:3, close_reason:4,
    impact:5, gross:6, cum_equity:7, mae:8, mfe:9, capture:10,
    fees:11, r:12, warnings:13, created:14, closed:15
  };
  const numericKeys = new Set(["impact","gross","cum_equity","mae","mfe","capture","fees","r","warnings","created","closed"]);
  const col = colByKey[key] ?? 11;
  rows.sort((a,b) => {
    const aCell = a.children[col];
    const bCell = b.children[col];
    if(numericKeys.has(key)){
      return (__numberValue(aCell) - __numberValue(bCell)) * dir;
    }
    return __textValue(aCell).localeCompare(__textValue(bCell)) * dir;
  });
  for (const row of rows){ body.appendChild(row); }
}
function sortTradeTable(key){
  if (__tradeSortState.key === key){
    __tradeSortState.dir = __tradeSortState.dir === "asc" ? "desc" : "asc";
  } else {
    __tradeSortState.key = key;
    __tradeSortState.dir = "asc";
  }
  __sortTradeRows();
}
function applyTradeFilters(){
  const symbol = (document.getElementById("trade-filter-symbol")?.value || "").trim().toLowerCase();
  const status = (document.getElementById("trade-filter-status")?.value || "all").trim().toLowerCase();
  const outcome = (document.getElementById("trade-filter-outcome")?.value || "all").trim().toLowerCase();
  const reason = (document.getElementById("trade-filter-reason")?.value || "all").trim().toLowerCase();
  const table = document.getElementById("trade-results-table");
  if(!table) return;
  const rows = Array.from(table.querySelectorAll("tbody tr"));
  for (const row of rows){
    const symbolText = row.children[1]?.innerText?.trim().toLowerCase() || "";
    const statusText = row.children[3]?.innerText?.trim().toLowerCase() || "";
    const reasonText = row.children[4]?.innerText?.trim().toLowerCase() || "";
    const impact = __numberValue(row.children[5]);
    const matchSymbol = !symbol || symbolText.includes(symbol);
    const matchStatus = status === "all" || statusText === status;
    const matchReason = reason === "all" || reasonText.includes(reason);
    let matchOutcome = true;
    if (outcome === "gain"){ matchOutcome = impact > 0; }
    if (outcome === "loss"){ matchOutcome = impact < 0; }
    if (outcome === "flat"){ matchOutcome = impact === 0; }
    row.style.display = (matchSymbol && matchStatus && matchOutcome && matchReason) ? "" : "none";
  }
}
// ---- extended column toggles ----
function toggleTradeCol(colClass, btn){
  var table = document.getElementById("trade-results-table");
  if(!table) return;
  // toggle returns true if class was ADDED (column now hidden)
  if(table.classList.toggle(colClass)){
    btn.classList.remove("active");
  } else {
    btn.classList.add("active");
  }
}
// ---- excluded chains filter ----
function filterExcluded(reason, badge){
  const tbody = document.getElementById("excluded-chains-tbody");
  if(!tbody) return;
  const rows = Array.from(tbody.querySelectorAll("tr"));
  for(const row of rows){
    const r = row.dataset.reason || "";
    row.style.display = (reason === "all" || r === reason) ? "" : "none";
  }
  document.querySelectorAll(".excl-badge").forEach(b => b.classList.remove("active"));
  if(badge) badge.classList.add("active");
}
</script>
"""


# ---------------------------------------------------------------------------
# Metadata tables
# ---------------------------------------------------------------------------

def _dataset_metadata_table(dataset_metadata: dict[str, object]) -> str:
    rows = []
    for key, value in dataset_metadata.items():
        rows.append(f"<tr><td>{_escape(key)}</td><td>{_escape(value)}</td></tr>")
    return "".join(rows)


def _policy_values_table(policy_values: dict[str, object]) -> str:
    rows = []
    for key, value in policy_values.items():
        rows.append(
            "<tr>"
            f"<td>{_escape(key)}</td>"
            f"<td><span class='code' style='padding:0;border:none;background:transparent'>{_escape(value)}</span></td>"
            "</tr>"
        )
    return "".join(rows)


# ---------------------------------------------------------------------------
# Policy summary cards
# ---------------------------------------------------------------------------

def _metric_card(label: str, value: str, color_class: str = "") -> str:
    v_class = f"v {color_class}".strip()
    small = " small" if len(value) > 10 else ""
    return (
        f"<div class='metric'>"
        f"<div class='k'>{_escape(label)}</div>"
        f"<div class='{v_class}{small}'>{value}</div>"
        "</div>"
    )


def _trade_summary_metrics(summary: dict[str, object]) -> str:
    # ── Sezione 1: metriche nette principali (sempre visibili) ────────────────
    avg_net = summary.get("avg_trade_return_pct_net")
    med_net = summary.get("median_trade_return_pct_net")
    exp_net = summary.get("expectancy_pct_net")
    pf_net  = summary.get("profit_factor_net")
    wr_pct  = summary.get("win_rate_pct")
    best    = summary.get("best_trade_pct")
    worst   = summary.get("worst_trade_pct")
    avg_r   = summary.get("avg_r_multiple")
    med_r   = summary.get("median_r_multiple")
    dd_pct  = summary.get("max_drawdown_pct")

    primary: list[str] = [
        _metric_card("Avg Return % Net", _fmt_percent(avg_net), _badge_class_for_percent(avg_net)),
        _metric_card("Median Return % Net", _fmt_percent(med_net), _badge_class_for_percent(med_net)),
        _metric_card("Expectancy % Net", _fmt_percent(exp_net), _badge_class_for_percent(exp_net)),
        _metric_card("Win Rate %", _fmt_percent(wr_pct, signed=False), ""),
        _metric_card("Profit Factor Net", _fmt_number(pf_net), ""),
        _metric_card("Avg R-Multiple", _fmt_number(avg_r) if avg_r is not None else "-", _badge_class_for_number(avg_r)),
        _metric_card("Median R-Multiple", _fmt_number(med_r) if med_r is not None else "-", _badge_class_for_number(med_r)),
        _metric_card("Best Trade % Net", _fmt_percent(best), "ok"),
        _metric_card("Worst Trade % Net", _fmt_percent(worst), "bad"),
        _metric_card("Max Drawdown %", f"-{abs(float(dd_pct)):.2f}%" if dd_pct is not None else "-",
                     "bad" if dd_pct and float(dd_pct) > 0 else "muted"),
    ]

    secondary: list[str] = [
        _metric_card("Total Trades", str(summary.get("trades_count", "-")), ""),
        _metric_card("Closed", str(summary.get("closed_trades_count", "-")), ""),
        _metric_card("Expired", str(summary.get("expired_trades_count", "-")), "muted" if summary.get("expired_trades_count") else ""),
        _metric_card("Cancelled", str(summary.get("cancelled_trades_count", "-")), "muted" if summary.get("cancelled_trades_count") else ""),
        _metric_card("Excluded Chains", str(summary.get("chains_excluded", "-")), ""),
        _metric_card("Avg Warnings", _fmt_number(summary.get("avg_warnings_per_trade")), ""),
    ]

    primary_html = f"<div class='grid-4'>{''.join(primary)}</div>"
    secondary_html = f"<div style='margin-top:12px'><div class='grid-4'>{''.join(secondary)}</div></div>"
    return primary_html + secondary_html


# ---------------------------------------------------------------------------
# Gross vs Net comparison table
# ---------------------------------------------------------------------------

def _gross_vs_net_table(summary: dict[str, object]) -> str:
    """Sezione 2 PRD: tabella comparativa gross / net / delta costi."""
    metrics = [
        ("Avg Trade Return %",  "avg_trade_return_pct_gross",    "avg_trade_return_pct_net"),
        ("Median Trade Return %","median_trade_return_pct_gross", "median_trade_return_pct_net"),
        ("Expectancy %",        "expectancy_pct_gross",          "expectancy_pct_net"),
        ("Profit Factor",       "profit_factor_gross",           "profit_factor_net"),
    ]
    rows: list[str] = []
    for label, gross_key, net_key in metrics:
        g = summary.get(gross_key)
        n = summary.get(net_key)
        delta: float | None = None
        if g is not None and n is not None:
            delta = float(n) - float(g)
        g_str = _fmt_percent(g) if g is not None else "-"
        n_str = _fmt_percent(n) if n is not None else "-"
        d_str = _fmt_percent(delta) if delta is not None else "-"
        d_cls = _badge_class_for_percent(delta)
        rows.append(
            f"<tr><td><strong>{_escape(label)}</strong></td>"
            f"<td>{g_str}</td>"
            f"<td>{n_str}</td>"
            f"<td><span class='badge {d_cls}'>{d_str}</span></td>"
            "</tr>"
        )
    return (
        "<div class='card'>"
        "<h2>Gross vs Net</h2>"
        "<div style='overflow-x:auto'>"
        "<table>"
        "<thead><tr><th>Metric</th><th>Gross</th><th>Net</th><th>Delta (costi)</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        "</div>"
    )


def _cost_breakdown_section(summary: dict[str, object]) -> str:
    """Sezione 3 PRD: diagnostica costi (fee e funding)."""
    fees_total  = summary.get("fees_total_raw")
    fees_avg    = summary.get("fees_avg_raw")
    fund_total  = summary.get("funding_total_raw_net")
    fund_avg    = summary.get("funding_avg_raw_net")
    drag        = summary.get("avg_cost_drag_pct")

    cards = "".join([
        _metric_card("Total Fees (raw)", _fmt_number(fees_total, 6) if fees_total is not None else "-", "bad" if fees_total and float(fees_total) != 0 else "muted"),
        _metric_card("Avg Fees per Trade (raw)", _fmt_number(fees_avg, 6) if fees_avg is not None else "-", ""),
        _metric_card("Total Funding Net (raw)", _fmt_number(fund_total, 6) if fund_total is not None else "-", _badge_class_for_number(fund_total)),
        _metric_card("Avg Funding per Trade (raw)", _fmt_number(fund_avg, 6) if fund_avg is not None else "-", _badge_class_for_number(fund_avg)),
        _metric_card("Avg Cost Drag %", _fmt_percent(drag) if drag is not None else "-", "bad" if drag and float(drag) > 0 else "muted"),
    ])
    return (
        "<div class='card'>"
        "<h2>Cost Breakdown</h2>"
        f"<div class='grid-4'>{cards}</div>"
        "</div>"
    )


def _cost_sensitivity_section(summary: dict[str, object]) -> str:
    """Sezione 4 PRD: cost sensitivity — trade che cambiano segno gross→net."""
    gp_nn_count = summary.get("gross_positive_to_net_negative_count", 0)
    gp_nn_pct   = summary.get("gross_positive_to_net_negative_pct")
    fw_count    = summary.get("trades_with_funding_count", 0)
    fw_pct      = summary.get("trades_with_funding_pct")

    cards = "".join([
        _metric_card(
            "Gross+ → Net− count",
            str(gp_nn_count),
            "bad" if gp_nn_count and int(gp_nn_count) > 0 else "muted",
        ),
        _metric_card(
            "Gross+ → Net− %",
            _fmt_percent(gp_nn_pct, signed=False) if gp_nn_pct is not None else "-",
            "bad" if gp_nn_pct and float(gp_nn_pct) > 0 else "muted",
        ),
        _metric_card(
            "Trades with Funding",
            str(fw_count),
            "muted",
        ),
        _metric_card(
            "Trades with Funding %",
            _fmt_percent(fw_pct, signed=False) if fw_pct is not None else "-",
            "muted",
        ),
    ])
    note = (
        "<p class='note' style='margin-top:8px'>"
        "Gross+→Net−: trade con rendimento lordo positivo diventato negativo dopo costi. "
        "Identifica la fragilità reale della policy ai costi operativi."
        "</p>"
    )
    return (
        "<div class='card'>"
        "<h2>Cost Sensitivity</h2>"
        f"<div class='grid-4'>{cards}</div>"
        f"{note}"
        "</div>"
    )


# ---------------------------------------------------------------------------
# Policy charts (ECharts — embedded in policy_report.html)
# JS uses a payload element to avoid f-string/JS brace conflicts (same pattern as
# trade_chart_echarts.py).
# ---------------------------------------------------------------------------

_POLICY_CHARTS_JS = r"""
<script>
(function () {
  'use strict';
  var payload = JSON.parse(document.getElementById('policy-charts-payload').textContent || '{}');
  var eqLabels   = payload.eq_labels   || [];
  var eqValues   = payload.eq_values   || [];
  var ddValues   = payload.dd_values   || [];
  var distValues = payload.dist_values || [];
  var crValues   = payload.cr_values   || [];
  var symLabels  = payload.sym_labels  || [];
  var symData    = payload.sym_data    || [];

  function safeInit(id) {
    var el = document.getElementById(id);
    return el ? echarts.init(el, null, {renderer: 'canvas'}) : null;
  }

  // --- Equity Curve ---
  var chartEq = safeInit('chart-equity');
  if (chartEq && eqValues.length > 0) {
    chartEq.setOption({
      animation: false, backgroundColor: '#ffffff',
      tooltip: {trigger: 'axis', formatter: function (p) {
        return p[0].name + '<br/><b>' + (p[0].value >= 0 ? '+' : '') + p[0].value.toFixed(3) + '%</b>';
      }},
      grid: {left: 60, right: 16, top: 16, bottom: 40},
      xAxis: {type: 'category', data: eqLabels, axisLabel: {show: false}, axisLine: {lineStyle: {color: '#e2e8f0'}}},
      yAxis: {type: 'value', axisLabel: {formatter: '{value}%'}, splitLine: {lineStyle: {color: '#f1f5f9'}}},
      series: [{
        type: 'line', data: eqValues, smooth: false,
        lineStyle: {color: '#0f766e', width: 2},
        areaStyle: {color: {type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{offset: 0, color: 'rgba(15,118,110,.18)'}, {offset: 1, color: 'rgba(15,118,110,0)'}]}},
        symbol: 'none',
        markLine: {silent: true, lineStyle: {color: '#94a3b8', type: 'dashed'}, data: [{yAxis: 0}]}
      }]
    });
  }

  // --- Drawdown ---
  var chartDd = safeInit('chart-drawdown');
  if (chartDd && ddValues.length > 0) {
    chartDd.setOption({
      animation: false, backgroundColor: '#ffffff',
      tooltip: {trigger: 'axis', formatter: function (p) {
        return p[0].name + '<br/>DD: <b>-' + p[0].value.toFixed(3) + '%</b>';
      }},
      grid: {left: 60, right: 16, top: 16, bottom: 40},
      xAxis: {type: 'category', data: eqLabels, axisLabel: {show: false}, axisLine: {lineStyle: {color: '#e2e8f0'}}},
      yAxis: {type: 'value', inverse: true, axisLabel: {formatter: '{value}%'}, splitLine: {lineStyle: {color: '#f1f5f9'}}},
      series: [{
        type: 'line', data: ddValues, smooth: false,
        lineStyle: {color: '#b91c1c', width: 1.5},
        areaStyle: {color: {type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{offset: 0, color: 'rgba(185,28,28,.22)'}, {offset: 1, color: 'rgba(185,28,28,0)'}]}},
        symbol: 'none'
      }]
    });
  }

  // --- Distribution ---
  var chartDist = safeInit('chart-dist');
  if (chartDist && distValues.length > 0) {
    var minV = distValues[0], maxV = distValues[distValues.length - 1];
    var binCount = Math.min(20, Math.max(5, Math.ceil(Math.sqrt(distValues.length))));
    var step = (maxV - minV) / binCount || 1;
    var bins = [], counts = new Array(binCount).fill(0);
    for (var b = 0; b < binCount; b++) { bins.push(+(minV + b * step).toFixed(3)); }
    distValues.forEach(function (v) {
      var idx = Math.min(binCount - 1, Math.floor((v - minV) / step));
      counts[idx]++;
    });
    chartDist.setOption({
      animation: false, backgroundColor: '#ffffff',
      tooltip: {trigger: 'axis', formatter: function (p) {
        return p[0].axisValue + '%<br/><b>' + p[0].value + ' trades</b>';
      }},
      grid: {left: 40, right: 16, top: 16, bottom: 40},
      xAxis: {type: 'category', data: bins.map(function (b) { return b.toFixed(2); }), axisLabel: {formatter: '{value}%'}},
      yAxis: {type: 'value', splitLine: {lineStyle: {color: '#f1f5f9'}}},
      series: [{
        type: 'bar', data: counts,
        itemStyle: {color: function (p) { return counts[p.dataIndex] > 0 && bins[p.dataIndex] >= 0 ? '#15803d' : '#b91c1c'; }}
      }]
    });
  }

  // --- Symbol Contribution ---
  var chartSym = safeInit('chart-symbol');
  if (chartSym && symLabels.length > 0) {
    chartSym.setOption({
      animation: false, backgroundColor: '#ffffff',
      tooltip: {trigger: 'axis', formatter: function (p) {
        return p[0].name + '<br/>' + (p[0].value >= 0 ? '+' : '') + p[0].value.toFixed(6);
      }},
      grid: {left: 80, right: 16, top: 16, bottom: 40},
      xAxis: {type: 'value', splitLine: {lineStyle: {color: '#f1f5f9'}}},
      yAxis: {type: 'category', data: symLabels, axisLabel: {fontSize: 11}},
      series: [{
        type: 'bar', data: symData,
        itemStyle: {color: function (p) { return symData[p.dataIndex] >= 0 ? '#15803d' : '#b91c1c'; }}
      }]
    });
  }

  // --- Close Reason (pie) ---
  var chartReason = safeInit('chart-reason');
  if (chartReason && crValues.length > 0) {
    chartReason.setOption({
      animation: false, backgroundColor: '#ffffff',
      tooltip: {trigger: 'item', formatter: '{b}: {c} ({d}%)'},
      legend: {bottom: 0, itemGap: 8, textStyle: {fontSize: 11}},
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
        data: crValues,
        label: {show: true, formatter: '{b}\n{c}', fontSize: 11},
        itemStyle: {borderRadius: 6}
      }]
    });
  }

  window.addEventListener('resize', function () {
    [chartEq, chartDd, chartDist, chartSym, chartReason].forEach(function (c) { if (c) c.resize(); });
  });
}());
</script>
"""


def _render_policy_charts(summary: dict[str, object]) -> str:
    """Build all aggregate charts for the policy report."""
    equity_curve: list = summary.get("equity_curve_pct") or []  # type: ignore[assignment]
    drawdown_data: list = summary.get("drawdown_pct") or []  # type: ignore[assignment]
    close_reason_dist: dict = summary.get("close_reason_distribution") or {}  # type: ignore[assignment]
    symbol_contrib: dict = summary.get("symbol_contribution") or {}  # type: ignore[assignment]

    # Reconstruct per-trade % from cumulative equity deltas
    trade_results_pct: list[float] = []
    if len(equity_curve) >= 2:
        prev = 0.0
        for point in equity_curve:
            curr = float(point.get("equity_pct", prev))
            trade_results_pct.append(round(curr - prev, 4))
            prev = curr
    elif len(equity_curve) == 1:
        trade_results_pct = [float(equity_curve[0].get("equity_pct", 0))]

    has_equity = bool(equity_curve)
    has_close_reason = bool(close_reason_dist)
    has_symbol = bool(symbol_contrib)

    if not has_equity and not has_close_reason and not has_symbol:
        return ""

    sym_names = list(symbol_contrib.keys())
    sym_pnl = [
        round(float(symbol_contrib[s].get("cumulative_pnl", 0)), 6)
        if isinstance(symbol_contrib[s], dict) else 0
        for s in sym_names
    ]

    # All data goes into a single JSON payload element — no f-string JS needed
    payload = {
        "eq_labels":   [p.get("signal_id", str(i)) for i, p in enumerate(equity_curve)],
        "eq_values":   [p.get("equity_pct", 0) for p in equity_curve],
        "dd_values":   [p.get("drawdown_pct", 0) for p in drawdown_data],
        "dist_values": sorted(trade_results_pct),
        "cr_values":   [{"name": k, "value": v} for k, v in close_reason_dist.items()],
        "sym_labels":  sym_names,
        "sym_data":    sym_pnl,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    # Build HTML containers
    parts: list[str] = ["<div class='card'><h2>Analytics Charts</h2>"]

    if has_equity:
        parts.append(
            "<div class='charts-full'>"
            "<h3>Equity Curve %</h3>"
            "<div class='chart-wrap'><div id='chart-equity' style='width:100%;height:260px'></div></div>"
            "</div>"
            "<div class='charts-grid'>"
            "<div><h3>Drawdown %</h3>"
            "<div class='chart-wrap'><div id='chart-drawdown' style='width:100%;height:220px'></div></div></div>"
            "<div><h3>Trade Return Distribution %</h3>"
            "<div class='chart-wrap'><div id='chart-dist' style='width:100%;height:220px'></div></div></div>"
            "</div>"
        )

    row2: list[str] = []
    if has_symbol:
        row2.append(
            "<div><h3>Contribution by Symbol</h3>"
            "<div class='chart-wrap'><div id='chart-symbol' style='width:100%;height:260px'></div></div></div>"
        )
    if has_close_reason:
        row2.append(
            "<div><h3>Close Reason Distribution</h3>"
            "<div class='chart-wrap'><div id='chart-reason' style='width:100%;height:260px'></div></div></div>"
        )
    if row2:
        parts.append(f"<div class='charts-grid'>{''.join(row2)}</div>")

    parts.append("</div>")  # close .card

    # Inject data payload then static JS
    parts.append(
        f"<script type='application/json' id='policy-charts-payload'>{payload_json}</script>"
    )
    parts.append(_POLICY_CHARTS_JS)

    return "".join(parts)


# ---------------------------------------------------------------------------
# Excluded chains table
# ---------------------------------------------------------------------------

def _excluded_table(excluded_chains: list[dict[str, str]]) -> tuple[str, str, str]:
    """Return (reason_bar_html, rows_html, dialogs_html)."""
    rows: list[str] = []
    dialogs: list[str] = []

    # Count by reason for the badge bar
    from collections import Counter
    reason_counts: Counter[str] = Counter()
    for item in excluded_chains:
        reason_counts[item.get("reason") or "unknown"] += 1

    # Build reason badge bar
    badge_items = [
        f"<span class='excl-badge active badge muted' onclick=\"filterExcluded('all',this)\">All ({len(excluded_chains)})</span>"
    ]
    for reason_val, count in sorted(reason_counts.items()):
        badge_items.append(
            f"<span class='excl-badge badge bad' onclick=\"filterExcluded('{_escape(reason_val)}',this)\">"
            f"{_escape(reason_val)} ({count})</span>"
        )
    reason_bar = f"<div class='excl-reason-bar'>{''.join(badge_items)}</div>"

    for index, item in enumerate(excluded_chains):
        dialog_id = f"excluded_raw_{index}"
        raw_text = item.get("original_text") or "-"
        item_reason = _escape(item.get("reason") or "unknown")
        rows.append(
            f"<tr data-reason='{item_reason}'>"
            f"<td>{_escape(item.get('signal_id'))}</td>"
            f"<td>{_escape(item.get('symbol'))}</td>"
            f"<td><span class='badge bad'>{item_reason}</span></td>"
            f"<td>{_escape(item.get('note'))}</td>"
            f"<td><button class='inline-btn' onclick=\"openText('{dialog_id}')\">View raw text</button></td>"
            "</tr>"
        )
        dialogs.append(
            f"""
    <dialog id="{dialog_id}">
      <div class="dialog-head">
        <strong>{_escape(item.get('signal_id'))} - Original TEXT</strong>
        <button class="inline-btn" onclick="closeText('{dialog_id}')">Close</button>
      </div>
      <div class="dialog-body">
        <pre class="code">{_escape(raw_text)}</pre>
      </div>
    </dialog>
"""
        )
    return reason_bar, "".join(rows), "".join(dialogs)


# ---------------------------------------------------------------------------
# Trade results table
# ---------------------------------------------------------------------------

def _trade_results_table(
    trade_results: list[TradeResult],
    trade_detail_links: dict[str, str] | None,
) -> str:
    rows: list[str] = []
    for trade in trade_results:
        detail_href = "#"
        detail_label = "-"
        if trade_detail_links and trade.signal_id in trade_detail_links:
            detail_href = trade_detail_links[trade.signal_id]
            detail_label = "Detail"

        # col 5: Net Return % (primary)
        net_v = trade.trade_return_pct_net
        if net_v is not None:
            net_cell = (
                f"<td data-sort='{net_v:.8f}'>"
                f"<span class='badge {_badge_class_for_percent(net_v)}'>{_fmt_percent(net_v)}</span>"
                "</td>"
            )
        else:
            # fallback to raw realized_pnl when not yet filled
            raw_v = trade.realized_pnl
            net_cell = (
                f"<td data-sort='{raw_v:.8f}'>"
                f"<span class='badge {_badge_class_for_number(raw_v)}'>{_fmt_number(raw_v, 4)}</span>"
                "</td>"
            )

        # col 6: Gross Return % (toggle)
        gross_v = trade.trade_return_pct_gross
        gross_cell = (
            f"<td data-sort='{gross_v:.8f}'>"
            f"<span class='badge {_badge_class_for_percent(gross_v)}'>{_fmt_percent(gross_v)}</span>"
            "</td>"
            if gross_v is not None
            else "<td data-sort='-9999'>-</td>"
        )

        cum_eq = trade.cum_equity_after_trade_pct
        mae_v  = trade.mae_pct
        mfe_v  = trade.mfe_pct
        cap_v  = trade.capture_ratio_pct
        fees_v = trade.fees_total_raw
        r_v    = trade.r_multiple

        rows.append(
            "<tr>"
            f"<td style='font-size:12px'>{_escape(trade.signal_id)}</td>"
            f"<td>{_escape(trade.symbol)}</td>"
            f"<td>{_escape(trade.side)}</td>"
            f"<td>{_escape(trade.status)}</td>"
            f"<td>{_escape(trade.close_reason or '-')}</td>"
            + net_cell
            + gross_cell +
            f"<td data-sort='{cum_eq if cum_eq is not None else -9999}'>{_fmt_percent(cum_eq) if cum_eq is not None else '-'}</td>"
            f"<td data-sort='{mae_v if mae_v is not None else 0}'>{_fmt_percent(mae_v) if mae_v is not None else '-'}</td>"
            f"<td data-sort='{mfe_v if mfe_v is not None else 0}'>{_fmt_percent(mfe_v) if mfe_v is not None else '-'}</td>"
            f"<td data-sort='{cap_v if cap_v is not None else -9999}'>{_fmt_percent(cap_v) if cap_v is not None else '-'}</td>"
            f"<td data-sort='{fees_v:.8f}'>{_fmt_number(fees_v, 6) if fees_v else '-'}</td>"
            f"<td data-sort='{r_v if r_v is not None else -9999}'>{_fmt_number(r_v) if r_v is not None else '-'}</td>"
            f"<td data-sort='{trade.warnings_count}'>{trade.warnings_count}</td>"
            f"<td data-sort='{trade.created_at or ''}'>{_escape(_fmt_timestamp(trade.created_at))}</td>"
            f"<td data-sort='{trade.closed_at or ''}'>{_escape(_fmt_timestamp(trade.closed_at))}</td>"
            f"<td><a class='link' href='{_escape(detail_href)}'>{_escape(detail_label)}</a></td>"
            "</tr>"
        )
    return "".join(rows)


# ---------------------------------------------------------------------------
# Event timeline helpers
# ---------------------------------------------------------------------------

def _event_price_reference(entry: EventLogEntry) -> str:
    state_after = entry.state_after
    avg_entry = state_after.get("avg_entry_price")
    current_sl = state_after.get("current_sl")
    tp_levels = state_after.get("tp_levels") or []
    parts: list[str] = []
    if avg_entry is not None:
        parts.append(f"avg_entry={_fmt_number(avg_entry, 4)}")
    if current_sl is not None:
        parts.append(f"sl={_fmt_number(current_sl, 4)}")
    if tp_levels:
        first_tp = tp_levels[0]
        parts.append(f"tp={_fmt_number(first_tp, 4)}")
    return " | ".join(parts) if parts else "-"


def _event_extracted_signal_levels(entry: EventLogEntry) -> str:
    state_after = entry.state_after or {}
    parts: list[str] = []
    entries = state_after.get("entries_planned") or []
    if isinstance(entries, list) and entries:
        entry_prices = [item.get("price") for item in entries if isinstance(item, dict)]
        clean_entries = [price for price in entry_prices if isinstance(price, int | float)]
        if clean_entries:
            parts.append("entry=" + ", ".join(_fmt_number(value, 4) for value in clean_entries))
    current_sl = state_after.get("current_sl")
    if isinstance(current_sl, int | float):
        parts.append(f"sl={_fmt_number(current_sl, 4)}")
    tp_levels = state_after.get("tp_levels") or []
    if isinstance(tp_levels, list) and tp_levels:
        clean_tps = [tp for tp in tp_levels if isinstance(tp, int | float)]
        if clean_tps:
            parts.append("tp=" + ", ".join(_fmt_number(value, 4) for value in clean_tps))
    return " | ".join(parts) if parts else "-"


def _is_telegram_event(entry: EventLogEntry) -> bool:
    return (entry.source or "").lower() == "trader"


def _display_side(value: str | None) -> str:
    normalized = (value or "").upper()
    if normalized in {"BUY", "LONG"}:
        return "LONG"
    if normalized in {"SELL", "SHORT"}:
        return "SHORT"
    return normalized or "-"


def _display_event_name(value: str | None) -> str:
    normalized = (value or "").upper()
    if normalized == "OPEN_SIGNAL":
        return "NEW_SIGNAL"
    return normalized or "-"


def _status_badge_class(entry: EventLogEntry) -> str:
    return f"ti-status-{entry.processing_status.value.lower()}"


def _fills_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    fills = state.get("fills") or []
    return [item for item in fills if isinstance(item, dict)]


def _fill_label(fill: dict[str, Any], *, index: int) -> str:
    plan_id = str(fill.get("plan_id") or "")
    if ":E" in plan_id:
        return f"FILL {plan_id.split(':E')[-1]}"
    return f"FILL {index + 1}"


def _is_material_engine_event(entry: EventLogEntry) -> bool:
    before = entry.state_before or {}
    after = entry.state_after or {}
    before_fills = len(_fills_from_state(before))
    after_fills = len(_fills_from_state(after))
    event_name = (entry.event_type or "").upper()
    reason = (entry.reason or "").lower()
    if (entry.source or "").lower() != "engine":
        return False
    if after_fills > before_fills:
        return True
    if entry.processing_status.value.lower() == "generated":
        return True
    if event_name in {"CLOSE_FULL", "CLOSE_PARTIAL", "CANCEL_PENDING"}:
        return True
    if "tp" in event_name.lower() or "sl" in event_name.lower():
        return True
    if "tp" in reason or "sl" in reason or "timeout" in reason or "filled" in reason:
        return True
    return False


def _new_signal_details(entry: EventLogEntry) -> dict[str, str]:
    state_after = entry.state_after or {}
    entries = state_after.get("entries_planned") or []
    fills = _fills_from_state(state_after)
    entry_prices = [
        _fmt_number(item.get("price"), 4)
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("price"), (int, float))
    ]
    order_types = {
        str(item.get("order_type")).upper()
        for item in entries
        if isinstance(item, dict) and item.get("order_type")
    }
    entry_type = ", ".join(sorted(order_types)) if order_types else "-"
    if len(entries) <= 1:
        entry_structure = "ONE_SHOT"
    elif len(entries) == 2:
        entry_structure = "TWO_STEP"
    else:
        entry_structure = "LADDER"
    tp_count = len([value for value in (state_after.get("tp_levels") or []) if isinstance(value, (int, float))])
    return {
        "Entry type": entry_type,
        "Entry structure": entry_structure,
        "Planned entries": str(len(entries)),
        "Filled entries": str(len(fills)),
        "TP count": str(tp_count),
        "Stop loss": _fmt_number(state_after.get("current_sl"), 4),
        "Entry prices": ", ".join(entry_prices) if entry_prices else "-",
    }


def _timeline_fill_rows(entry: EventLogEntry) -> list[dict[str, str]]:
    before_fills = _fills_from_state(entry.state_before or {})
    after_fills = _fills_from_state(entry.state_after or {})
    if len(after_fills) <= len(before_fills):
        return []

    rows: list[dict[str, str]] = []
    for idx, fill in enumerate(after_fills[len(before_fills):], start=len(before_fills)):
        fill_ts = fill.get("timestamp")
        rows.append(
            {
                "timestamp": _fmt_timestamp(fill_ts or entry.timestamp),
                "event_name": _fill_label(fill, index=idx),
                "requested_action": "FILL",
                "reason": str(fill.get("plan_id") or "order_filled"),
                "status": "applied",
                "event_price": _fmt_number(fill.get("price"), 6),
                "qty": _fmt_number(fill.get("qty"), 4),
                "source": "engine",
            }
        )
    return rows


def _state_delta_html(before: dict, after: dict, initial_capital: float | None) -> str:
    """Build delta-of-state pills for the event timeline."""
    items: list[str] = []

    def _delta_pill(label: str, b: object, a: object, fmt_fn=None) -> str:
        if b is None and a is None:
            return ""
        fb = fmt_fn(b) if fmt_fn and b is not None else ("-" if b is None else str(b))
        fa = fmt_fn(a) if fmt_fn and a is not None else ("-" if a is None else str(a))
        if fb == fa:
            return ""
        return (
            f"<span class='ti-delta-item'>"
            f"<span class='dlab'>{_escape(label)}</span>"
            f"{_escape(fb)} → {_escape(fa)}"
            "</span>"
        )

    # position size
    pb = before.get("open_size")
    pa = after.get("open_size")
    items.append(_delta_pill("size", pb, pa, lambda v: _fmt_number(v, 4)))

    # avg entry
    ab = before.get("avg_entry_price")
    aa = after.get("avg_entry_price")
    items.append(_delta_pill("avg", ab, aa, lambda v: _fmt_number(v, 4)))

    # pending size
    qpb = before.get("pending_size")
    qpa = after.get("pending_size")
    items.append(_delta_pill("pending", qpb, qpa, lambda v: _fmt_number(v, 4)))

    # realized PnL %
    if initial_capital and initial_capital > 0:
        rpb = before.get("realized_pnl")
        rpa = after.get("realized_pnl")
        def _as_pct(v):
            return _fmt_percent(float(v) / initial_capital * 100, digits=3) if v is not None else "-"
        items.append(_delta_pill("realized %", rpb, rpa, _as_pct))
    else:
        rpb = before.get("realized_pnl")
        rpa = after.get("realized_pnl")
        items.append(_delta_pill("realized_pnl", rpb, rpa, lambda v: _fmt_number(v, 4)))

    # current SL
    slb = before.get("current_sl")
    sla = after.get("current_sl")
    items.append(_delta_pill("sl", slb, sla, lambda v: _fmt_number(v, 4)))

    # status
    sb = before.get("status")
    sa = after.get("status")
    items.append(_delta_pill("status", sb, sa))

    # next_tp_index
    tpb = before.get("next_tp_index")
    tpa = after.get("next_tp_index")
    items.append(_delta_pill("tp_idx", tpb, tpa))

    filled = [x for x in items if x]
    if not filled:
        return ""
    return f"<div class='ti-delta'>{''.join(filled)}</div>"


# ---------------------------------------------------------------------------
# Single trade chart
# ---------------------------------------------------------------------------

def _render_chart(
    trade: TradeResult,
    event_log: list[EventLogEntry],
    candles_by_timeframe: dict[str, list[Candle]],
    echarts_asset_path: str,
) -> str:
    payload = build_trade_chart_payload(trade, event_log, candles_by_timeframe)
    chart_id = _safe_dom_id(f"chart_{trade.signal_id}")
    return render_trade_chart_echarts(payload, chart_id=chart_id, asset_path=echarts_asset_path)


# ---------------------------------------------------------------------------
# Single trade HTML report
# ---------------------------------------------------------------------------

def write_single_trade_html_report(
    *,
    trade: TradeResult,
    event_log: list[EventLogEntry],
    candles_by_timeframe: dict[str, list[Candle]] | None = None,
    output_path: str | Path,
    back_link_href: str = "../../policy_report.html",
    echarts_asset_path: str = "../../assets/echarts.min.js",
    prev_link: str | None = None,
    next_link: str | None = None,
    trade_index: int | None = None,
    trades_total: int | None = None,
    initial_capital: float | None = None,
) -> Path:
    # --- Group 1: Risultato (net/gross/cost) ---
    net_v   = trade.trade_return_pct_net
    gross_v = trade.trade_return_pct_gross
    drag_v  = trade.cost_drag_pct
    r_v     = trade.r_multiple

    perf_cards = "".join([
        _metric_card(
            "Return % Net",
            _fmt_percent(net_v) if net_v is not None else _fmt_number(trade.realized_pnl, 4),
            _badge_class_for_percent(net_v) if net_v is not None else _badge_class_for_number(trade.realized_pnl),
        ),
        _metric_card(
            "Return % Gross",
            _fmt_percent(gross_v) if gross_v is not None else "-",
            _badge_class_for_percent(gross_v),
        ),
        _metric_card(
            "Cost Drag %",
            _fmt_percent(drag_v, signed=False) if drag_v is not None else "-",
            "bad" if drag_v and float(drag_v) > 0 else "muted",
        ),
        _metric_card(
            "R-Multiple",
            _fmt_number(r_v) if r_v is not None else "-",
            _badge_class_for_number(r_v),
        ),
        _metric_card("Close Reason", _escape(trade.close_reason or "-"), ""),
        _metric_card("Status", _escape(trade.status), ""),
    ])

    # --- Group 2: Costi ---
    cost_cards = "".join([
        _metric_card("Fees Total (raw)", _fmt_number(trade.fees_total_raw, 6), "bad" if trade.fees_total_raw > 0 else "muted"),
        _metric_card("Funding Net (raw)", _fmt_number(trade.funding_total_raw_net, 6), _badge_class_for_number(trade.funding_total_raw_net)),
        _metric_card("PnL Net (raw)", _fmt_number(trade.pnl_net_raw, 6) if trade.pnl_net_raw is not None else "-", _badge_class_for_number(trade.pnl_net_raw)),
        _metric_card("PnL Gross (raw)", _fmt_number(trade.pnl_gross_raw, 6) if trade.pnl_gross_raw is not None else "-", _badge_class_for_number(trade.pnl_gross_raw)),
        _metric_card("Invested Notional", _fmt_number(trade.invested_notional, 4) if trade.invested_notional is not None else "-", ""),
        _metric_card("Initial R %", _fmt_percent(trade.initial_r_pct, signed=False) if trade.initial_r_pct is not None else "-", "muted"),
    ])

    # --- Group 3: Excursions ---
    excursion_cards = "".join([
        _metric_card(
            "MAE %",
            _fmt_percent(trade.mae_pct) if trade.mae_pct is not None else _fmt_number(trade.mae, 4),
            "bad" if (trade.mae_pct or trade.mae or 0) < 0 else "muted",
        ),
        _metric_card(
            "MFE %",
            _fmt_percent(trade.mfe_pct) if trade.mfe_pct is not None else _fmt_number(trade.mfe, 4),
            "ok" if (trade.mfe_pct or trade.mfe or 0) > 0 else "muted",
        ),
        _metric_card(
            "Capture Ratio %",
            _fmt_percent(trade.capture_ratio_pct) if trade.capture_ratio_pct is not None else "-",
            _badge_class_for_percent(trade.capture_ratio_pct),
        ),
        _metric_card("Cum. Equity % After", _fmt_percent(trade.cum_equity_after_trade_pct) if trade.cum_equity_after_trade_pct is not None else "-", _badge_class_for_percent(trade.cum_equity_after_trade_pct)),
    ])

    # --- Group 4: Execution ---
    execution_cards = "".join([
        _metric_card("First Fill Price", _fmt_number(trade.first_fill_price, 4), ""),
        _metric_card("Final Exit Price", _fmt_number(trade.final_exit_price, 4), ""),
        _metric_card("Fills Count", str(trade.fills_count), ""),
        _metric_card("Partial Closes", str(trade.partial_closes_count), ""),
        _metric_card("Updates Applied", str(trade.updates_applied_count), ""),
        _metric_card("Avg Entry", _fmt_number(trade.avg_entry_price, 4), ""),
    ])

    # --- Group 5: Timing ---
    timing_cards = "".join([
        _metric_card("Time to Fill", _fmt_duration(trade.time_to_fill_seconds), ""),
        _metric_card("Total Duration", _fmt_duration(trade.duration_seconds), ""),
        _metric_card("Created", _escape(_fmt_timestamp(trade.created_at)), ""),
        _metric_card("Closed", _escape(_fmt_timestamp(trade.closed_at)), ""),
    ])

    # --- Group 6: Trade Identity ---
    identity_cards = "".join([
        _metric_card("Signal ID", _escape(trade.signal_id), ""),
        _metric_card("Symbol", _escape(trade.symbol), ""),
        _metric_card("Side", _escape(_display_side(trade.side)), ""),
        _metric_card("Warnings", str(trade.warnings_count), "bad" if trade.warnings_count else "muted"),
        _metric_card("Ignored Events", str(trade.ignored_events_count), ""),
        _metric_card("Fees (raw)", _fmt_number(trade.fees_paid, 6), ""),
    ])

    # --- Event Timeline ---
    timeline_blocks: list[str] = []
    dialogs: list[str] = []
    for index, entry in enumerate(event_log):
        dialog_id = _safe_dom_id(f"raw_{trade.signal_id}_{index}")
        raw_button = "-"
        if entry.raw_text and _is_telegram_event(entry):
            raw_button = f"<button class='inline-btn' onclick=\"openText('{dialog_id}')\">Open raw telegram text</button>"
            dialogs.append(
                f"""
    <dialog id="{dialog_id}">
      <div class="dialog-head">
        <strong>{_escape(trade.signal_id)} — {_escape(_display_event_name(entry.event_type))}</strong>
        <button class="inline-btn" onclick="closeText('{dialog_id}')">Close</button>
      </div>
      <div class="dialog-body">
        <pre class="code">{_escape(entry.raw_text)}</pre>
      </div>
    </dialog>
"""
            )

        event_name = _display_event_name(entry.event_type)
        state_delta = _state_delta_html(entry.state_before, entry.state_after, initial_capital)

        # Source badge
        src = (entry.source or "").lower()
        if src == "trader":
            src_badge = f"<span class='ti-src-trader'>trader</span>"
        elif src:
            src_badge = f"<span class='ti-src-system'>{_escape(entry.source)}</span>"
        else:
            src_badge = ""

        open_attr = " open" if _is_material_engine_event(entry) else ""
        body_sections: list[str] = []
        event_meta = [
            f"<div class='lab'>Requested action</div><div>{_escape(entry.requested_action or '-')}</div>",
            f"<div class='lab'>Status</div><div>{_escape(entry.processing_status.value)}</div>",
            f"<div class='lab'>Reason code</div><div>{_escape(entry.reason or '-')}</div>",
            f"<div class='lab'>Event price</div><div>{_fmt_number(entry.price_reference, 6) if entry.price_reference is not None else '-'}</div>",
        ]
        if entry.raw_text and _is_telegram_event(entry) and event_name != "NEW_SIGNAL":
            event_meta.append(f"<div class='lab'>Raw TEXT</div><div>{raw_button}</div>")

        body_sections.append(
            "<div class='ti-panel'><h3>Event details</h3>"
            f"<div class='ti-meta'>{''.join(event_meta)}</div></div>"
        )

        if event_name == "NEW_SIGNAL":
            signal_rows = []
            for label, value in _new_signal_details(entry).items():
                signal_rows.append(f"<div class='lab'>{_escape(label)}</div><div>{_escape(value)}</div>")
            signal_rows.append(
                f"<div class='lab'>Extracted levels</div><div>{_escape(_event_extracted_signal_levels(entry))}</div>"
            )
            body_sections.append(
                "<div class='ti-panel'><h3>Signal extracted</h3>"
                f"<div class='ti-meta'>{''.join(signal_rows)}</div>"
                f"{raw_button if entry.raw_text and _is_telegram_event(entry) else ''}"
                "</div>"
            )
        else:
            body_sections.append(
                "<div class='ti-panel'><h3>Reference snapshot</h3>"
                f"<div class='ti-meta'>"
                f"<div class='lab'>Price reference</div><div>{_escape(_event_price_reference(entry))}</div>"
                f"<div class='lab'>Executed action</div><div>{_escape(entry.executed_action or '-')}</div>"
                f"</div></div>"
            )

        timeline_blocks.append(
            f"""
        <details class="timeline-item"{open_attr}>
          <summary>
            <div class="tl-row">
              <div class="tl-time">{_escape(_fmt_timestamp(entry.timestamp))}</div>
              <div class="tl-main"><span class="tl-event">{_escape(event_name)}</span>{src_badge}</div>
              <div class="tl-requested">{_escape(entry.requested_action or '-')}</div>
              <div><span class="{_escape(_status_badge_class(entry))}">{_escape(entry.processing_status.value.upper())}</span></div>
              <div class="tl-pills">{state_delta}</div>
            </div>
            <div class="tl-row" style="margin-top:8px;grid-template-columns:84px 1.2fr 132px 116px 1fr">
              <div></div>
              <div class="tl-reason">reason: {_escape(entry.reason or '-')}</div>
              <div class="tl-requested">source: {_escape(entry.source or '-')}</div>
              <div class="tl-requested">exec: {_escape(entry.executed_action or '-')}</div>
              <div></div>
            </div>
          </summary>
          <div class="ti-body">
            <div class="ti-body-grid">
              {''.join(body_sections)}
            </div>
          </div>
        </details>
"""
        )

        for fill_index, fill_row in enumerate(_timeline_fill_rows(entry)):
            timeline_blocks.append(
                f"""
        <details class="timeline-item" open>
          <summary>
            <div class="tl-row">
              <div class="tl-time">{_escape(fill_row["timestamp"])}</div>
              <div class="tl-main"><span class="tl-event">{_escape(fill_row["event_name"])}</span><span class='ti-src-system'>engine</span></div>
              <div class="tl-requested">FILL</div>
              <div><span class="ti-status-applied">APPLIED</span></div>
              <div class="tl-pills">
                <span class="ti-delta-item"><span class="dlab">qty</span>{_escape(fill_row["qty"])}</span>
                <span class="ti-delta-item"><span class="dlab">price</span>{_escape(fill_row["event_price"])}</span>
              </div>
            </div>
            <div class="tl-row" style="margin-top:8px;grid-template-columns:84px 1.2fr 132px 116px 1fr">
              <div></div>
              <div class="tl-reason">reason: {_escape(fill_row["reason"])}</div>
              <div class="tl-requested">source: engine</div>
              <div class="tl-requested">exec: FILL</div>
              <div></div>
            </div>
          </summary>
          <div class="ti-body">
            <div class="ti-body-grid">
              <div class="ti-panel">
                <h3>Fill detected by simulator</h3>
                <div class="ti-meta">
                  <div class="lab">Event type</div><div>FILL</div>
                  <div class="lab">Price</div><div>{_escape(fill_row["event_price"])}</div>
                  <div class="lab">Quantity</div><div>{_escape(fill_row["qty"])}</div>
                  <div class="lab">Plan</div><div>{_escape(fill_row["reason"])}</div>
                </div>
              </div>
            </div>
          </div>
        </details>
"""
            )

    # Full HTML
    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(trade.signal_id)} - Single Trade Report</title>
{_base_styles()}
</head>
<body>
<div class="wrap">
  <h1>Single Trade — {_escape(trade.signal_id)}</h1>

  <div class="card">
    <h2>Performance — Net / Gross</h2>
    <div class="grid-4">{perf_cards}</div>
  </div>

  <div class="card">
    <h2>Costi e PnL raw</h2>
    <div class="grid-4">{cost_cards}</div>
  </div>

  <div class="grid-2" style="margin-bottom:18px">
    <div class="card" style="margin:0">
      <h2>Excursions</h2>
      <div class="grid-2">{excursion_cards}</div>
    </div>
    <div class="card" style="margin:0">
      <h2>Timing</h2>
      <div class="grid-2">{timing_cards}</div>
    </div>
  </div>

  <div class="card">
    <h2>Execution</h2>
    <div class="grid-4">{execution_cards}</div>
  </div>

  <details class="card">
    <summary>Identity &amp; metadata</summary>
    <div style="margin-top:12px"><div class="grid-4">{identity_cards}</div></div>
  </details>

  <div class="card">
    <h2>Price Chart</h2>
    <div class="note" style="margin-bottom:10px">Candlestick chart in price. Use timeframe buttons and legend toggles to navigate.</div>
    {_render_chart(trade, event_log, candles_by_timeframe or {}, echarts_asset_path)}
  </div>

  <div class="card">
    <h2>Event Timeline</h2>
    <div class="note" style="margin-bottom:10px">Each row shows state changes (delta pills) when available.</div>
    <div class="timeline">{''.join(timeline_blocks)}</div>
  </div>

  <div class="footer-nav" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    {f'<a class="inline-btn" href="{_escape(prev_link)}" title="Previous trade">&larr; Prev</a>' if prev_link else '<span class="inline-btn" style="opacity:.35;cursor:default">&larr; Prev</span>'}
    <a class="inline-btn" href="{_escape(back_link_href)}">&#8801; Summary{f' ({trade_index}/{trades_total})' if trade_index is not None and trades_total is not None else ''}</a>
    {f'<a class="inline-btn" href="{_escape(next_link)}" title="Next trade">Next &rarr;</a>' if next_link else '<span class="inline-btn" style="opacity:.35;cursor:default">Next &rarr;</span>'}
  </div>

  {''.join(dialogs)}
</div></body></html>
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Policy HTML report
# ---------------------------------------------------------------------------

def write_policy_html_report(
    *,
    summary: dict[str, object],
    trade_results: list[TradeResult],
    excluded_chains: list[dict[str, str]],
    dataset_metadata: dict[str, object],
    policy_values: dict[str, object],
    output_path: str | Path,
    trade_detail_links: dict[str, str] | None = None,
    title: str = "Policy Report",
) -> Path:
    excluded_reason_bar, excluded_rows, excluded_dialogs = _excluded_table(excluded_chains)
    charts_html = _render_policy_charts(summary)
    gross_vs_net_html = _gross_vs_net_table(summary)
    cost_breakdown_html = _cost_breakdown_section(summary)
    cost_sensitivity_html = _cost_sensitivity_section(summary)

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
{_base_styles()}
</head>
<body>
<div class="wrap">
  <h1>{_escape(title)}</h1>

  <details class="card">
    <summary>Dataset metadata</summary>
    <div style="margin-top:14px">
      <table><tbody>{_dataset_metadata_table(dataset_metadata)}</tbody></table>
    </div>
  </details>

  <details class="card">
    <summary>Metadata - policy.yaml values</summary>
    <div style="margin-top:14px">
      <table><tbody>{_policy_values_table(policy_values)}</tbody></table>
    </div>
  </details>

  <div class="card sticky">
    <h2>Policy Summary</h2>
    {_trade_summary_metrics(summary)}
  </div>

  <script src="assets/echarts.min.js"></script>
  {charts_html}

  {gross_vs_net_html}
  {cost_breakdown_html}
  {cost_sensitivity_html}

  <details class="card">
    <summary>Excluded chains ({len(excluded_chains)})</summary>
    <div style="margin-top:14px">
      {excluded_reason_bar}
      <table>
        <thead><tr><th>Signal ID</th><th>Symbol</th><th>Reason</th><th>Note</th><th>Original TEXT</th></tr></thead>
        <tbody id="excluded-chains-tbody">{excluded_rows}</tbody>
      </table>
    </div>
  </details>

  <div class="card">
    <h2>Trade Results</h2>
    <div class="note" style="margin-bottom:12px">Click headers to sort. Colonne aggiuntive nascoste di default — usa i toggle per mostrarle.</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
      <span class="note" style="margin-right:2px">Colonne:</span>
      <button class="chart-toolbar-btn active" onclick="toggleTradeCol('hide-gross',this)">Gross%</button>
      <button class="chart-toolbar-btn active" onclick="toggleTradeCol('hide-cumEq',this)">Cum.Equity%</button>
      <button class="chart-toolbar-btn active" onclick="toggleTradeCol('hide-mae',this)">MAE%</button>
      <button class="chart-toolbar-btn active" onclick="toggleTradeCol('hide-mfe',this)">MFE%</button>
      <button class="chart-toolbar-btn active" onclick="toggleTradeCol('hide-capture',this)">Capture%</button>
      <button class="chart-toolbar-btn active" onclick="toggleTradeCol('hide-fees',this)">Fees</button>
      <button class="chart-toolbar-btn active" onclick="toggleTradeCol('hide-r',this)">R</button>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
      <input id="trade-filter-symbol" type="text" placeholder="Filter symbol" style="border:1px solid #e2e8f0;border-radius:10px;padding:7px 10px;min-width:180px" oninput="applyTradeFilters()">
      <select id="trade-filter-status" style="border:1px solid #e2e8f0;border-radius:10px;padding:7px 10px" onchange="applyTradeFilters()">
        <option value="all">Status: all</option>
        <option value="closed">closed</option>
        <option value="open">open</option>
        <option value="cancelled">cancelled</option>
        <option value="expired">expired</option>
      </select>
      <select id="trade-filter-outcome" style="border:1px solid #e2e8f0;border-radius:10px;padding:7px 10px" onchange="applyTradeFilters()">
        <option value="all">Outcome: all</option>
        <option value="gain">gain</option>
        <option value="loss">loss</option>
        <option value="flat">flat</option>
      </select>
      <select id="trade-filter-reason" style="border:1px solid #e2e8f0;border-radius:10px;padding:7px 10px" onchange="applyTradeFilters()">
        <option value="all">Close reason: all</option>
        <option value="tp">tp</option>
        <option value="sl">sl</option>
        <option value="manual">manual</option>
        <option value="expired">expired</option>
        <option value="cancelled">cancelled</option>
      </select>
    </div>
    <div style="overflow-x:auto">
    <table id="trade-results-table" class="hide-gross hide-cumEq hide-mae hide-mfe hide-capture hide-fees hide-r">
      <thead><tr>
        <th class="th-sort" onclick="sortTradeTable('signal')">Signal ID</th>
        <th class="th-sort" onclick="sortTradeTable('symbol')">Symbol</th>
        <th class="th-sort" onclick="sortTradeTable('side')">Side</th>
        <th class="th-sort" onclick="sortTradeTable('status')">Status</th>
        <th class="th-sort" onclick="sortTradeTable('close_reason')">Close Reason</th>
        <th class="th-sort" onclick="sortTradeTable('impact')">Net %</th>
        <th class="th-sort" onclick="sortTradeTable('gross')">Gross %</th>
        <th class="th-sort" onclick="sortTradeTable('cum_equity')">Cum. Equity %</th>
        <th class="th-sort" onclick="sortTradeTable('mae')">MAE %</th>
        <th class="th-sort" onclick="sortTradeTable('mfe')">MFE %</th>
        <th class="th-sort" onclick="sortTradeTable('capture')">Capture %</th>
        <th class="th-sort" onclick="sortTradeTable('fees')">Fees</th>
        <th class="th-sort" onclick="sortTradeTable('r')">R</th>
        <th class="th-sort" onclick="sortTradeTable('warnings')">Warn</th>
        <th class="th-sort" onclick="sortTradeTable('created')">Created</th>
        <th class="th-sort" onclick="sortTradeTable('closed')">Closed</th>
        <th>Detail</th>
      </tr></thead>
      <tbody>{_trade_results_table(trade_results, trade_detail_links)}</tbody>
    </table>
    </div>
  </div>

  {excluded_dialogs}
</div>
<script>__sortTradeRows();</script>
</body></html>
"""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def flatten_policy_values(policy_values: dict[str, object]) -> dict[str, object]:
    flat: dict[str, object] = {}

    def walk(prefix: str, value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                walk(next_prefix, nested)
            return
        if isinstance(value, list):
            flat[prefix] = json.dumps(value, ensure_ascii=False)
            return
        flat[prefix] = value

    walk("", policy_values)
    return flat


# ---------------------------------------------------------------------------
# Comparison report
# ---------------------------------------------------------------------------

_COMPARISON_METRICS: list[tuple[str, str, bool]] = [
    # (key, label, higher_is_better)
    ("avg_trade_return_pct_net",  "Avg Return % Net",     True),
    ("expectancy_pct_net",        "Expectancy % Net",     True),
    ("win_rate_pct",              "Win Rate %",           True),
    ("profit_factor_net",         "Profit Factor Net",    True),
    ("avg_r_multiple",            "Avg R-Multiple",       True),
    ("max_drawdown_pct",          "Max Drawdown %",       False),
    ("avg_cost_drag_pct",         "Avg Cost Drag %",      False),
    ("best_trade_pct",            "Best Trade % Net",     True),
    ("worst_trade_pct",           "Worst Trade % Net",    True),
    ("trades_count",              "Trades",               False),
]


def _ranking_table(
    delta_metrics: dict[str, dict[str, object]],
    policy_names: list[str],
) -> str:
    rows: list[str] = []
    for key, label, higher_better in _COMPARISON_METRICS:
        values = {p: delta_metrics[p].get(key) for p in policy_names}
        # Find best
        valid = {p: v for p, v in values.items() if v is not None}
        best_policy = None
        if valid:
            if higher_better:
                best_policy = max(valid, key=lambda p: float(valid[p]))  # type: ignore[arg-type]
            else:
                best_policy = min(valid, key=lambda p: float(valid[p]))  # type: ignore[arg-type]

        cells = [f"<td><strong>{_escape(label)}</strong></td>"]
        for p in policy_names:
            v = values.get(p)
            is_best = p == best_policy
            if v is None:
                cell_val = "-"
            elif isinstance(v, float):
                cell_val = f"{v:+.3f}" if key.endswith("_pct") or key == "profit_factor" else f"{v:.1f}"
            else:
                cell_val = str(v)
            cls = "ok-text" if is_best else ""
            cells.append(f"<td class='{cls}'>{cell_val}{'★' if is_best else ''}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(rows)


def _delta_cards_row(
    delta_metrics: dict[str, dict[str, object]],
    policy_names: list[str],
) -> str:
    """One column of metric cards per policy."""
    cols: list[str] = []
    for pname in policy_names:
        m = delta_metrics[pname]
        tr_pct = m.get("total_return_pct")
        dd_pct = m.get("max_drawdown_pct")
        pf = m.get("profit_factor")
        wr = m.get("win_rate_pct")
        cards = "".join([
            _metric_card("Total Return %", _fmt_percent(tr_pct), _badge_class_for_percent(tr_pct)),
            _metric_card("Max Drawdown %",
                         f"-{abs(float(dd_pct)):.2f}%" if dd_pct is not None else "-",
                         "bad" if dd_pct and float(dd_pct) > 0 else "muted"),
            _metric_card("Profit Factor", _fmt_number(pf), ""),
            _metric_card("Win Rate %", _fmt_percent(wr, signed=False), ""),
        ])
        cols.append(
            f"<div class='card' style='margin:0'>"
            f"<h3>{_escape(pname)}</h3>"
            f"<div class='grid-2'>{cards}</div>"
            "</div>"
        )
    n = len(cols)
    grid_cols = f"repeat({n}, minmax(0,1fr))"
    return (
        f"<div style='display:grid;grid-template-columns:{grid_cols};gap:14px;margin-bottom:18px'>"
        + "".join(cols)
        + "</div>"
    )


def _changed_trades_table(
    changed_trades: list[ChangedTrade],
    policy_names: list[str],
    initial_capital: float | None,
) -> str:
    if not changed_trades:
        return "<p class='note'>No changed trades detected between policies.</p>"
    rows: list[str] = []
    for ct in changed_trades:
        cells = [
            f"<td style='font-size:12px'>{_escape(ct.signal_id)}</td>",
            f"<td>{_escape(ct.symbol)}</td>",
        ]
        for pname in policy_names:
            tr = ct.results.get(pname)
            link = ct.detail_links.get(pname)
            if tr is None:
                cells.append("<td>-</td><td>-</td><td>-</td>")
                continue
            if initial_capital and initial_capital > 0 and tr.trade_impact_pct is not None:
                pnl_str = _fmt_percent(tr.trade_impact_pct)
                cls = _badge_class_for_percent(tr.trade_impact_pct)
            else:
                pnl_str = _fmt_number(tr.realized_pnl, 4)
                cls = _badge_class_for_number(tr.realized_pnl)
            reason_str = _escape(tr.close_reason or "-")
            detail_anchor = (
                f"<a class='link' href='{_escape(link)}'>Detail</a>"
                if link else "-"
            )
            cells.append(
                f"<td><span class='badge {cls}'>{pnl_str}</span></td>"
                f"<td>{reason_str}</td>"
                f"<td>{detail_anchor}</td>"
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(rows)


def write_comparison_html_report(
    *,
    policies: list[PolicyConfig],
    summaries_by_policy: dict[str, dict[str, object]],
    delta_metrics: dict[str, dict[str, object]],
    changed_trades: list[ChangedTrade],
    output_path: str | Path,
    dataset_metadata: dict[str, object] | None = None,
    initial_capital: float | None = None,
    title: str = "Policy Comparison Report",
) -> Path:
    policy_names = [p.name for p in policies]
    n = len(policy_names)

    # Per-policy summary links
    policy_links = "".join(
        f"<a class='inline-btn' href='{_escape(pname)}/policy_report.html'>{_escape(pname)}</a> "
        for pname in policy_names
    )

    # Ranking table header
    header_cells = "<th>Metric</th>" + "".join(
        f"<th>{_escape(p)}</th>" for p in policy_names
    )

    # Changed trades table header
    ct_header_policy_cols = "".join(
        f"<th colspan='3'>{_escape(p)}</th>" for p in policy_names
    )
    ct_sub_header = "".join(
        "<th>Result</th><th>Close Reason</th><th>Detail</th>"
        for _ in policy_names
    )

    changed_count = len(changed_trades)

    # Dataset metadata rows
    meta_rows = ""
    for k, v in (dataset_metadata or {}).items():
        meta_rows += f"<tr><td>{_escape(k)}</td><td>{_escape(v)}</td></tr>"

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title)}</title>
{_base_styles()}
</head>
<body>
<div class="wrap">
  <h1>{_escape(title)}</h1>
  <p class="note" style="margin-bottom:18px">Comparing {n} policies on the same dataset.
     Navigate to each policy: {policy_links}</p>

  <details class="card">
    <summary>Dataset metadata</summary>
    <div style="margin-top:14px">
      <table><tbody>{meta_rows}</tbody></table>
    </div>
  </details>

  <div class="card">
    <h2>Performance Cards</h2>
    {_delta_cards_row(delta_metrics, policy_names)}
  </div>

  <div class="card">
    <h2>Ranking by Metric</h2>
    <p class="note" style="margin-bottom:10px">&#9733; marks the best policy per metric.</p>
    <div style="overflow-x:auto">
    <table>
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{_ranking_table(delta_metrics, policy_names)}</tbody>
    </table>
    </div>
  </div>

  <div class="card">
    <h2>Changed Trades ({changed_count})</h2>
    <p class="note" style="margin-bottom:10px">Trades where close reason or PnL sign differs between policies.</p>
    <div style="overflow-x:auto">
    <table>
      <thead>
        <tr><th rowspan="2">Signal ID</th><th rowspan="2">Symbol</th>{ct_header_policy_cols}</tr>
        <tr>{ct_sub_header}</tr>
      </thead>
      <tbody>{_changed_trades_table(changed_trades, policy_names, initial_capital)}</tbody>
    </table>
    </div>
  </div>

</div></body></html>
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path
