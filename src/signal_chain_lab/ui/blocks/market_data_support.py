"""Helper utilities for the Market DATA panel — parsing stdout protocol and formatting."""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.signal_chain_lab.ui.state import MarketDataTypeState


@dataclass
class ProgressEvent:
    phase: str | None = None
    progress: int | None = None
    step: str | None = None
    summary: str | None = None


_PROTO_RE = re.compile(r"\b(PHASE|PROGRESS|STEP|SUMMARY)=(\S+)")


def parse_progress_line(line: str) -> ProgressEvent | None:
    """Parse a structured stdout line from market scripts into a ProgressEvent.

    Returns None when the line contains no protocol tokens.
    """
    matches = _PROTO_RE.findall(line)
    if not matches:
        return None
    event = ProgressEvent()
    for key, val in matches:
        if key == "PHASE":
            event.phase = val
        elif key == "PROGRESS":
            try:
                event.progress = int(val)
            except ValueError:
                pass
        elif key == "STEP":
            event.step = val
        elif key == "SUMMARY":
            event.summary = val
    return event


def format_coverage_summary(plan_json: dict) -> str:
    s = plan_json.get("summary", {})
    return (
        f"Simboli: {s.get('symbols', 0)} | "
        f"Intervalli: {s.get('required_intervals', 0)} | "
        f"Gap: {s.get('gaps', 0)}"
    )


def supported_data_type_labels(selected: MarketDataTypeState) -> list[str]:
    labels: list[str] = []
    if selected.ohlcv_last:
        labels.append("OHLCV last")
    if selected.ohlcv_mark:
        labels.append("OHLCV mark")
    if selected.funding_rate:
        labels.append("Funding rate")
    return labels


def roadmap_data_type_labels() -> list[str]:
    return [
        "Open interest",
        "Liquidations",
        "Bid/ask spread",
        "Order book",
    ]


def format_data_types_summary(selected: MarketDataTypeState) -> str:
    active = supported_data_type_labels(selected)
    if not active:
        return "Tipi dati attivi: nessuno selezionato"
    return "Tipi dati attivi: " + ", ".join(active)


def format_window_preview(plan_json: dict) -> str:
    symbols = plan_json.get("symbols", {})
    if not isinstance(symbols, dict) or not symbols:
        return "Finestre: nessun simbolo nel piano."

    preview_parts: list[str] = []
    detail_suffix = ""
    for idx, symbol in enumerate(sorted(symbols.keys())[:2]):
        basis_payload = symbols.get(symbol, {})
        if not isinstance(basis_payload, dict) or not basis_payload:
            continue
        first_entry = next(
            (entry for entry in basis_payload.values() if isinstance(entry, dict)),
            None,
        )
        if first_entry is None:
            continue
        execution = first_entry.get("execution_window", [])
        chart = first_entry.get("chart_window", [])
        download = first_entry.get("download_window", [])
        preview_parts.append(
            f"{symbol}: exec={len(execution)} chart={len(chart)} download={len(download)}"
        )
        if idx == 0:
            detail_suffix = _format_first_symbol_window_detail(
                symbol=symbol,
                execution=execution,
                chart=chart,
                download=download,
            )

    if not preview_parts:
        return "Finestre: nessun dettaglio disponibile."
    base = "Finestre: " + " | ".join(preview_parts)
    if detail_suffix:
        return f"{base} | {detail_suffix}"
    return base


def _format_first_symbol_window_detail(
    *,
    symbol: str,
    execution: list[dict],
    chart: list[dict],
    download: list[dict],
) -> str:
    def _bounds(intervals: list[dict]) -> str:
        if not intervals:
            return "n/a"
        first = intervals[0]
        last = intervals[-1]
        start = str(first.get("start", "n/a"))
        end = str(last.get("end", "n/a"))
        return f"{start}→{end}"

    return (
        f"{symbol} range "
        f"exec[{_bounds(execution)}] "
        f"chart[{_bounds(chart)}] "
        f"download[{_bounds(download)}]"
    )


def format_validation_summary(report_json: dict) -> str:
    s = report_json.get("summary", {})
    passed = s.get("pass", s.get("passed", 0))
    failed = s.get("fail", s.get("failed", 0))
    return f"Pass: {passed} | Fail: {failed}"


_PHASE_LABELS: dict[str, str] = {
    "discover": "Discovery",
    "planner": "Planner",
    "sync": "Sync",
    "gap_validate": "Gap Validation",
    "validate": "Validazione completa",
}


def map_phase_label(phase: str) -> str:
    return _PHASE_LABELS.get(phase.lower(), phase)
