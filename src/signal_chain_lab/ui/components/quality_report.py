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

        ui.label("Stato workflow").classes("text-body2")
        with ui.grid(columns=3).classes("w-full gap-x-8 gap-y-1"):
            ui.label("1. Parse:")
            ui.label("ok" if report.total_messages > 0 else "vuoto").classes(
                "text-positive" if report.total_messages > 0 else "text-negative"
            )
            ui.label(f"parse_results: {report.total_messages}")
            ui.label("2. Chain builder:")
            ui.label("ok" if report.total_signals > 0 else "non pronto").classes(
                "text-positive" if report.total_signals > 0 else "text-negative"
            )
            ui.label(f"chain ricostruite: {report.total_signals}")
            ui.label("3. Backtest:")
            ui.label("pronto" if report.backtest_ready else "bloccato").classes(
                "text-positive" if report.backtest_ready else "text-negative"
            )
            ui.label(
                f"signals={report.signals_rows}, operational={report.operational_signals_rows}, new_signal={report.operational_new_signal_rows}"
            )

        ui.separator()
        ui.label("Dettaglio dataset").classes("text-body2")
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
            ui.label(f"Righe signals: {report.signals_rows}")
            ui.label(f"Righe operational_signals: {report.operational_signals_rows}")
            ui.label(f"Operational NEW_SIGNAL: {report.operational_new_signal_rows}")
            ui.label(f"Backtest ready: {'si' if report.backtest_ready else 'no'}")

        if not report.backtest_ready:
            ui.separator()
            ui.label(
                "Il parse puo' essere completato anche senza ricostruzione catene. "
                "Per il backtest servono anche signals/operational_signals e almeno una chain ricostruibile."
            ).classes("text-negative")

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
