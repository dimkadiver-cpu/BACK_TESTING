"""Quality report card for parser + chain-builder synthetic metrics."""
from __future__ import annotations

from nicegui import ui

from src.signal_chain_lab.ui.state import QualityReport


def render_quality_report(report: QualityReport) -> None:
    """Render a compact report card with key parse-chain readiness figures."""
    with ui.card().classes("w-full"):
        ui.label("Report sintetico").classes("text-subtitle2")
        with ui.row().classes("gap-8"):
            ui.label(f"Segnali totali: {report.total_signals}")
            ui.label(f"Simulabili: {report.simulable_signals}")
        ui.separator()
        ui.label("Top warnings")
        if not report.top_warnings:
            ui.label("Nessun warning rilevante").classes("text-grey-6")
            return
        for warning, count in report.top_warnings:
            ui.label(f"• {warning}: {count}")
