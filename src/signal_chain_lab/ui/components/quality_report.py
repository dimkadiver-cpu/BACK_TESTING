"""Quality report card for parser + chain-builder metrics."""
from __future__ import annotations

from nicegui import ui

from src.signal_chain_lab.ui.state import QualityReport


def render_quality_report(report: QualityReport, *, reports_dir: str = "") -> None:
    """Render a richer parser quality report."""
    with ui.card().classes("w-full"):
        ui.label("Report Qualita Dataset").classes("text-subtitle2")
        if report.trader_id:
            ui.label(f"Trader: {report.trader_id}").classes("text-caption text-grey-7")

        with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-1"):
            ui.label(f"Messaggi totali: {report.total_messages}")
            ui.label(f"NEW_SIGNAL completi: {report.new_signal_complete}")
            ui.label(f"NEW_SIGNAL: {report.new_signal_count}")
            ui.label(f"NEW_SIGNAL incompleti: {report.new_signal_incomplete}")
            ui.label(f"UPDATE: {report.update_count}")
            ui.label(f"UPDATE orfani: {report.update_orphan_count}")
            ui.label(f"INFO_ONLY: {report.info_only_count}")
            ui.label(f"Chain simulabili: {report.simulable_signals}")
            ui.label(f"UNCLASSIFIED: {report.unclassified_count}")
            ui.label(f"Chain non simulabili: {report.non_simulable_signals}")

        ui.separator()
        ui.label("Top warnings").classes("text-body2")
        if not report.top_warnings:
            ui.label("Nessun warning rilevante").classes("text-grey-6")
        else:
            for warning, count in report.top_warnings:
                ui.label(f"- {warning}: {count}")

        if reports_dir:
            ui.separator()
            ui.label(f"CSV: {reports_dir}").classes("text-caption text-grey-7")
