"""HTML writers for PRD-aligned policy and single-trade reports."""
from __future__ import annotations

import html
import json
from pathlib import Path

from src.signal_chain_lab.domain.results import EventLogEntry, TradeResult


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


def _base_styles() -> str:
    return """
<style>
:root{--bg:#f8fafc;--card:#ffffff;--text:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#0f766e;--blue:#1d4ed8;}
*{box-sizing:border-box}
body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text)}
.wrap{max-width:1200px;margin:0 auto;padding:24px}
h1{font-size:28px;margin:0 0 18px}
h2{font-size:20px;margin:0 0 14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin-bottom:18px;box-shadow:0 2px 10px rgba(15,23,42,.04)}
.sticky{position:sticky;top:0;z-index:20}
.grid-4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.metric{border:1px solid var(--line);border-radius:12px;padding:14px;background:#fff}
.metric .k{font-size:12px;color:var(--muted);margin-bottom:6px;text-transform:uppercase}
.metric .v{font-size:22px;font-weight:700}
.metric .v.small{font-size:16px}
details.card summary{cursor:pointer;font-weight:700;list-style:none}
details.card summary::-webkit-details-marker{display:none}
details.card summary:after{content:'Show';float:right;font-weight:600;color:var(--muted)}
details[open].card summary:after{content:'Hide'}
table{width:100%;border-collapse:collapse}
th,td{padding:11px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:14px;vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.th-sort{cursor:pointer;user-select:none}
.th-sort:hover{color:var(--blue)}
.badge{display:inline-block;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:700}
.ok{background:#dcfce7;color:#166534}.bad{background:#fee2e2;color:#991b1b}.muted{background:#e2e8f0;color:#334155}
.link{color:var(--blue);text-decoration:none;font-weight:600}
.note{color:var(--muted);font-size:13px}
.code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;white-space:pre-wrap;background:#f8fafc;border:1px solid var(--line);border-radius:12px;padding:14px}
button.inline-btn, a.inline-btn{border:1px solid var(--line);background:#fff;border-radius:10px;padding:7px 10px;font-size:13px;cursor:pointer;color:var(--blue);text-decoration:none}
dialog{border:none;border-radius:14px;padding:0;max-width:780px;width:92%;box-shadow:0 20px 60px rgba(2,6,23,.35)}
dialog::backdrop{background:rgba(15,23,42,.55)}
.dialog-head{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
.dialog-body{padding:18px}
.timeline{display:grid;gap:12px}
.ti{border:1px solid var(--line);border-radius:14px;padding:14px}
.ti-head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:10px}
.ti-meta{display:grid;grid-template-columns:180px 1fr;gap:8px;font-size:14px}
.ti-meta .lab{color:var(--muted)}
.footer-nav{margin-top:20px}
@media (max-width: 900px){.grid-4{grid-template-columns:repeat(2,minmax(0,1fr))}.ti-meta{grid-template-columns:1fr}}
</style>
<script>
function openText(id){ document.getElementById(id).showModal(); }
function closeText(id){ document.getElementById(id).close(); }
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
  const colByKey = { signal:0, symbol:1, side:2, status:3, pnl:5, warnings:6, created:8, closed:9 };
  const col = colByKey[key] ?? 8;
  rows.sort((a,b) => {
    const aCell = a.children[col];
    const bCell = b.children[col];
    if(["pnl","warnings","created","closed"].includes(key)){
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
  const table = document.getElementById("trade-results-table");
  if(!table) return;
  const rows = Array.from(table.querySelectorAll("tbody tr"));
  for (const row of rows){
    const symbolText = row.children[1]?.innerText?.trim().toLowerCase() || "";
    const statusText = row.children[3]?.innerText?.trim().toLowerCase() || "";
    const pnl = __numberValue(row.children[5]);
    const matchSymbol = !symbol || symbolText.includes(symbol);
    const matchStatus = status === "all" || statusText === status;
    let matchOutcome = true;
    if (outcome === "gain"){ matchOutcome = pnl > 0; }
    if (outcome === "loss"){ matchOutcome = pnl < 0; }
    if (outcome === "flat"){ matchOutcome = pnl === 0; }
    row.style.display = (matchSymbol && matchStatus && matchOutcome) ? "" : "none";
  }
}
</script>
"""


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


def _trade_summary_metrics(summary: dict[str, object]) -> str:
    return "".join(
        [
            f"<div class='metric'><div class='k'>Policy name</div><div class='v small'>{_escape(summary.get('policy_name'))}</div></div>",
            f"<div class='metric'><div class='k'>Total trades</div><div class='v'>{_escape(summary.get('trades_count'))}</div></div>",
            f"<div class='metric'><div class='k'>Win Rate</div><div class='v'>{_fmt_percent(summary.get('win_rate_pct'), signed=False)}</div></div>",
            f"<div class='metric'><div class='k'>Net Profit</div><div class='v'>{_fmt_percent(summary.get('net_profit_pct'))}</div></div>",
            f"<div class='metric'><div class='k'>Profit %</div><div class='v'>{_fmt_percent(summary.get('profit_pct'))}</div></div>",
            f"<div class='metric'><div class='k'>Loss %</div><div class='v'>{_fmt_percent(summary.get('loss_pct'))}</div></div>",
            f"<div class='metric'><div class='k'>Profit Factor</div><div class='v'>{_fmt_number(summary.get('profit_factor'))}</div></div>",
            f"<div class='metric'><div class='k'>Expectancy %</div><div class='v'>{_fmt_percent(summary.get('expectancy_pct'))}</div></div>",
            f"<div class='metric'><div class='k'>Max Drawdown %</div><div class='v'>{_fmt_percent(summary.get('max_drawdown_pct'), signed=False)}</div></div>",
            f"<div class='metric'><div class='k'>Avg Warnings / Trade</div><div class='v'>{_fmt_number(summary.get('avg_warnings_per_trade'))}</div></div>",
            f"<div class='metric'><div class='k'>Excluded Chains</div><div class='v'>{_escape(summary.get('chains_excluded'))}</div></div>",
        ]
    )


def _excluded_table(excluded_chains: list[dict[str, str]]) -> tuple[str, str]:
    rows: list[str] = []
    dialogs: list[str] = []
    for index, item in enumerate(excluded_chains):
        dialog_id = f"excluded_raw_{index}"
        raw_text = item.get("original_text") or "-"
        rows.append(
            "<tr>"
            f"<td>{_escape(item.get('signal_id'))}</td>"
            f"<td>{_escape(item.get('symbol'))}</td>"
            f"<td><span class='badge bad'>{_escape(item.get('reason'))}</span></td>"
            f"<td>{_escape(item.get('note'))}</td>"
            f"<td><button class='inline-btn' onclick=\"openText('{dialog_id}')\">Open raw telegram text</button></td>"
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
    return "".join(rows), "".join(dialogs)


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
        rows.append(
            "<tr>"
            f"<td>{_escape(trade.signal_id)}</td>"
            f"<td>{_escape(trade.symbol)}</td>"
            f"<td>{_escape(trade.side)}</td>"
            f"<td>{_escape(trade.status)}</td>"
            f"<td>{_escape(trade.close_reason)}</td>"
            f"<td data-sort='{trade.realized_pnl:.8f}'><span class='badge {_badge_class_for_percent(trade.realized_pnl)}'>{_fmt_percent(trade.realized_pnl)}</span></td>"
            f"<td data-sort='{trade.warnings_count}'>{trade.warnings_count}</td>"
            f"<td>{trade.ignored_events_count}</td>"
            f"<td data-sort='{trade.created_at or ''}'>{_escape(_fmt_timestamp(trade.created_at))}</td>"
            f"<td data-sort='{trade.closed_at or ''}'>{_escape(_fmt_timestamp(trade.closed_at))}</td>"
            f"<td><a class='link' href='{_escape(detail_href)}'>{_escape(detail_label)}</a></td>"
            "</tr>"
        )
    return "".join(rows)


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
    if normalized == "MOVE_STOP_TO_BE":
        return "UPDATE"
    if normalized == "MOVE_STOP":
        return "UPDATE"
    return normalized or "-"


def _event_outcome_labels(event_log: list[EventLogEntry]) -> set[str]:
    labels: set[str] = set()
    for entry in event_log:
        name = (entry.event_type or "").upper()
        if "TP" in name:
            labels.add(name)
        if "SL" in name:
            labels.add(name)
        executed = (entry.executed_action or "").upper()
        if "TP" in executed:
            labels.add(executed)
        if "SL" in executed:
            labels.add(executed)
    return labels


def _synthetic_candles(trade: TradeResult, event_log: list[EventLogEntry]) -> list[dict[str, float | str]]:
    anchors: list[float] = []
    state0 = event_log[0].state_after if event_log else {}
    for plan in state0.get("entries_planned") or []:
        price = plan.get("price")
        if isinstance(price, int | float):
            anchors.append(float(price))
    avg_entry = trade.avg_entry_price
    if avg_entry is not None:
        anchors.append(float(avg_entry))
    state_last = event_log[-1].state_after if event_log else {}
    current_sl = state_last.get("current_sl")
    if isinstance(current_sl, int | float):
        anchors.append(float(current_sl))
    for tp in state_last.get("tp_levels") or []:
        if isinstance(tp, int | float):
            anchors.append(float(tp))

    base = sum(anchors) / len(anchors) if anchors else 100.0
    candles: list[dict[str, float | str]] = []
    total = max(len(event_log), 6)
    for index in range(total):
        drift = ((index - (total / 2)) / max(total, 1)) * (base * 0.02)
        open_price = base + drift
        close_price = open_price + ((-1) ** index) * (base * 0.003)
        high_price = max(open_price, close_price) + (base * 0.004)
        low_price = min(open_price, close_price) - (base * 0.004)
        if event_log:
            event_idx = min(index, len(event_log) - 1)
            stamp = _fmt_timestamp(event_log[event_idx].timestamp)
            label = stamp[11:16] if len(stamp) >= 16 else stamp
            if total > len(event_log):
                label = f"T{index + 1}"
        else:
            label = str(index + 1)
        candles.append(
            {
                "label": label,
                "open": open_price,
                "close": close_price,
                "high": high_price,
                "low": low_price,
            }
        )
    return candles


def _chart_svg(trade: TradeResult, event_log: list[EventLogEntry]) -> str:
    candles = _synthetic_candles(trade, event_log)
    prices = [float(item[key]) for item in candles for key in ("high", "low")]
    prices.extend(
        float(value)
        for value in [trade.avg_entry_price]
        if value is not None
    )
    if event_log:
        last_state = event_log[-1].state_after
        prices.extend(float(tp) for tp in last_state.get("tp_levels") or [] if isinstance(tp, int | float))
        current_sl = last_state.get("current_sl")
        if isinstance(current_sl, int | float):
            prices.append(float(current_sl))
    if not prices:
        prices = [100.0, 101.0]

    width = 940
    height = 380
    left = 58
    top = 24
    bottom = 332
    right = 916

    min_price = min(prices)
    max_price = max(prices)
    span = (max_price - min_price) or 1.0

    def map_y(price: float) -> float:
        ratio = (price - min_price) / span
        return bottom - (ratio * (bottom - top))

    parts = [f"<svg viewBox='0 0 {width} {height}' width='100%' height='auto' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='{_escape(f'{trade.signal_id} - {trade.symbol} {trade.side}')}'>"]
    parts.append(f"<rect x='0' y='0' width='{width}' height='{height}' fill='#ffffff'/>")
    for idx in range(6):
        price = max_price - ((span / 5) * idx)
        y = map_y(price)
        parts.append(f"<line x1='{left}' y1='{y:.2f}' x2='{right}' y2='{y:.2f}' stroke='#e5e7eb' stroke-width='1'/>")
        parts.append(f"<text x='50' y='{y + 4:.2f}' text-anchor='end' font-size='12' fill='#6b7280'>{price:.2f}</text>")

    candle_step = (right - left) / max(len(candles), 1)
    candle_width = max(10.0, candle_step * 0.45)
    for idx, candle in enumerate(candles):
        x = left + candle_step * idx + (candle_step / 2)
        open_y = map_y(float(candle["open"]))
        close_y = map_y(float(candle["close"]))
        high_y = map_y(float(candle["high"]))
        low_y = map_y(float(candle["low"]))
        color = "#16a34a" if float(candle["close"]) >= float(candle["open"]) else "#dc2626"
        rect_y = min(open_y, close_y)
        rect_h = max(abs(close_y - open_y), 2.0)
        parts.append(f"<line x1='{x:.2f}' y1='{high_y:.2f}' x2='{x:.2f}' y2='{low_y:.2f}' stroke='{color}' stroke-width='2'/>")
        parts.append(f"<rect x='{x - (candle_width / 2):.2f}' y='{rect_y:.2f}' width='{candle_width:.2f}' height='{rect_h:.2f}' fill='{color}' rx='1'/>")
        parts.append(f"<text x='{x:.2f}' y='362' text-anchor='middle' font-size='12' fill='#6b7280'>{_escape(candle['label'])}</text>")

    annotations: list[tuple[str, float, str, str]] = []
    outcome_labels = _event_outcome_labels(event_log)
    if event_log:
        first_state = event_log[0].state_after
        entries = first_state.get("entries_planned") or []
        for idx, plan in enumerate(entries[:3]):
            price = plan.get("price")
            if isinstance(price, int | float):
                annotations.append((f"Entry {idx + 1}", float(price), "#2563eb" if idx == 0 else "#1d4ed8", "0"))
        if trade.avg_entry_price is not None:
            annotations.append(("Avg Entry", float(trade.avg_entry_price), "#0f766e", "0"))
        current_sl = event_log[-1].state_after.get("current_sl")
        if isinstance(current_sl, int | float):
            sl_hit = any("SL" in item for item in outcome_labels) or (trade.close_reason or "").lower() == "sl"
            label = "SL hit" if sl_hit else "SL initial"
            pnl = trade.realized_pnl if sl_hit else 0.0
            annotations.append((f"{label} ({_fmt_percent(pnl)})" if "SL hit" in label else label, float(current_sl), "#b91c1c", "0"))
        realized_hit_label_added = False
        tp_levels = event_log[-1].state_after.get("tp_levels") or []
        for idx, tp in enumerate(tp_levels):
            if isinstance(tp, int | float):
                label = f"TP{idx + 1}"
                suffix = ""
                hit_name = f"TP{idx + 1}"
                tp_hit = any(hit_name in item for item in outcome_labels)
                if tp_hit and trade.realized_pnl is not None and not realized_hit_label_added:
                    suffix = f" hit ({_fmt_percent(trade.realized_pnl)})"
                    realized_hit_label_added = True
                annotations.append((f"{label}{suffix}", float(tp), "#15803d", "0"))

    for idx, (label, price, color, _) in enumerate(annotations):
        y = map_y(price)
        x_start = left + 20 + (idx % 2) * 80
        box_width = min(180, 12 + (len(label) * 6.8))
        parts.append(f"<line x1='{x_start:.2f}' y1='{y:.2f}' x2='{right}' y2='{y:.2f}' stroke='{color}' stroke-dasharray='5 4' stroke-width='1.5'/>")
        parts.append(f"<rect x='{x_start + 8:.2f}' y='{y - 17:.2f}' width='{box_width:.2f}' height='22' rx='6' fill='white' stroke='{color}' stroke-width='1.2'/>")
        parts.append(f"<text x='{x_start + 16:.2f}' y='{y - 2:.2f}' font-size='12' fill='{color}' font-weight='600'>{_escape(label)}</text>")
        parts.append(f"<circle cx='{x_start:.2f}' cy='{y:.2f}' r='4' fill='{color}'/>")

    parts.append(f"<text x='{left}' y='16' font-size='15' font-weight='700' fill='#111827'>{_escape(f'{trade.signal_id} - {trade.symbol} {trade.side}')}</text>")
    parts.append("</svg>")
    return "".join(parts)


def write_single_trade_html_report(
    *,
    trade: TradeResult,
    event_log: list[EventLogEntry],
    output_path: str | Path,
    back_link_href: str = "../../policy_report_complete.html",
) -> Path:
    summary_cards = "".join(
        [
            f"<div class='metric'><div class='k'>Signal ID</div><div class='v'>{_escape(trade.signal_id)}</div></div>",
            f"<div class='metric'><div class='k'>Symbol</div><div class='v'>{_escape(trade.symbol)}</div></div>",
            f"<div class='metric'><div class='k'>Side</div><div class='v'>{_escape(_display_side(trade.side))}</div></div>",
            f"<div class='metric'><div class='k'>Status</div><div class='v'>{_escape(trade.status)}</div></div>",
            f"<div class='metric'><div class='k'>Close reason</div><div class='v'>{_escape(trade.close_reason or '-')}</div></div>",
            f"<div class='metric'><div class='k'>Realized PnL %</div><div class='v'>{_fmt_percent(trade.realized_pnl)}</div></div>",
            f"<div class='metric'><div class='k'>Created</div><div class='v small'>{_escape(_fmt_timestamp(trade.created_at))}</div></div>",
            f"<div class='metric'><div class='k'>Closed</div><div class='v small'>{_escape(_fmt_timestamp(trade.closed_at))}</div></div>",
            f"<div class='metric'><div class='k'>Warnings</div><div class='v'>{trade.warnings_count}</div></div>",
            f"<div class='metric'><div class='k'>Ignored events</div><div class='v'>{trade.ignored_events_count}</div></div>",
            f"<div class='metric'><div class='k'>Entries count</div><div class='v'>{trade.entries_count}</div></div>",
            f"<div class='metric'><div class='k'>Avg entry</div><div class='v'>{_fmt_number(trade.avg_entry_price, 4)}</div></div>",
            f"<div class='metric'><div class='k'>Max size</div><div class='v'>{_fmt_number(trade.max_position_size, 2)}</div></div>",
            f"<div class='metric'><div class='k'>Fees</div><div class='v'>{_fmt_percent(trade.fees_paid)}</div></div>",
        ]
    )

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
        <strong>{_escape(trade.signal_id)} - Original TEXT</strong>
        <button class="inline-btn" onclick="closeText('{dialog_id}')">Close</button>
      </div>
      <div class="dialog-body">
        <pre class="code">{_escape(entry.raw_text)}</pre>
      </div>
    </dialog>
"""
            )
        timeline_blocks.append(
            f"""
        <div class="ti">
          <div class="ti-head">
            <div><strong>{_escape(_display_event_name(entry.event_type))}</strong></div>
            <div class="note">{_escape(_fmt_timestamp(entry.timestamp))}</div>
          </div>
          <div class="ti-meta">
            <div class="lab">Requested action</div><div>{_escape(entry.requested_action or '-')}</div>
            <div class="lab">Executed action</div><div>{_escape(entry.executed_action or '-')}</div>
            <div class="lab">Status</div><div>{_escape(entry.processing_status.value)}</div>
            <div class="lab">{_escape('Extracted levels' if _display_event_name(entry.event_type) == 'NEW_SIGNAL' else 'Price reference')}</div>
            <div>{_escape(_event_extracted_signal_levels(entry) if _display_event_name(entry.event_type) == 'NEW_SIGNAL' else _event_price_reference(entry))}</div>
            <div class="lab">Original TEXT</div><div>{raw_button}</div>
          </div>
        </div>
"""
        )

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(trade.signal_id)} - Single Trade Report</title>
{_base_styles()}
</head>
<body>
<div class="wrap">
  <h1>Single Trade Report - {_escape(trade.signal_id)}</h1>
  <div class="card">
    <h2>Trade Summary</h2>
    <div class="grid-4">{summary_cards}</div>
  </div>
  <div class="card">
    <h2>Price Chart</h2>
    <div class="note" style="margin-bottom:10px">Candlestick-style view with operational overlays. Hit labels are shown only when detected in the event timeline.</div>
    {_chart_svg(trade, event_log)}
  </div>
  <div class="card">
    <h2>Event Timeline</h2>
    <div class="timeline">{''.join(timeline_blocks)}</div>
  </div>
  <div class="footer-nav">
    <a class="inline-btn" href="{_escape(back_link_href)}">Back to Policy Report</a>
  </div>
  {''.join(dialogs)}
</div></body></html>
"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path


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
    excluded_rows, excluded_dialogs = _excluded_table(excluded_chains)
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
    <div class="grid-4">{_trade_summary_metrics(summary)}</div>
  </div>

  <details class="card">
    <summary>Excluded chains</summary>
    <div style="margin-top:14px">
      <table>
        <thead><tr><th>Signal ID</th><th>Symbol</th><th>Reason</th><th>Note</th><th>Original TEXT</th></tr></thead>
        <tbody>{excluded_rows}</tbody>
      </table>
    </div>
  </details>

  <div class="card">
    <h2>Trade results</h2>
    <div class="note" style="margin-bottom:12px">Use filters and clickable headers to navigate quickly on large datasets. The Detail column opens the chain/signal report for drill-down.</div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
      <input id="trade-filter-symbol" type="text" placeholder="Filter symbol" style="border:1px solid #e2e8f0;border-radius:10px;padding:8px 10px;min-width:200px" oninput="applyTradeFilters()">
      <select id="trade-filter-status" style="border:1px solid #e2e8f0;border-radius:10px;padding:8px 10px" onchange="applyTradeFilters()">
        <option value="all">Status: all</option>
        <option value="closed">closed</option>
        <option value="open">open</option>
        <option value="cancelled">cancelled</option>
        <option value="expired">expired</option>
      </select>
      <select id="trade-filter-outcome" style="border:1px solid #e2e8f0;border-radius:10px;padding:8px 10px" onchange="applyTradeFilters()">
        <option value="all">Outcome: all</option>
        <option value="gain">gain</option>
        <option value="loss">loss</option>
        <option value="flat">flat</option>
      </select>
    </div>
    <table id="trade-results-table">
      <thead><tr><th class="th-sort" onclick="sortTradeTable('signal')">Signal ID</th><th class="th-sort" onclick="sortTradeTable('symbol')">Symbol</th><th class="th-sort" onclick="sortTradeTable('side')">Side</th><th class="th-sort" onclick="sortTradeTable('status')">Status</th><th>Close reason</th><th class="th-sort" onclick="sortTradeTable('pnl')">Realized PnL %</th><th class="th-sort" onclick="sortTradeTable('warnings')">Warnings</th><th>Ignored events</th><th class="th-sort" onclick="sortTradeTable('created')">Created</th><th class="th-sort" onclick="sortTradeTable('closed')">Closed</th><th>Detail</th></tr></thead>
      <tbody>{_trade_results_table(trade_results, trade_detail_links)}</tbody>
    </table>
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
