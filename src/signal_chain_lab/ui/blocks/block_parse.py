"""Blocco 2 — Parse dati.

Lancia replay_parser.py sul DB selezionato, costruisce le chain
canoniche, e produce il quality report sintetico. Sblocca Blocco 3
solo dopo parse completato con successo (checkpoint umano).
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from nicegui import ui

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.chain_builder import SignalChainBuilder
from src.signal_chain_lab.adapters.validators import validate_chain_for_simulation
from parser_test.reporting.report_export import export_reports_csv_v2
from src.signal_chain_lab.parser.trader_profiles.registry import canonicalize_trader_code
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.components.quality_report import render_quality_report
from src.signal_chain_lab.ui.state import QualityReport, UiState


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_TRADER_OPTIONS = {
    "": "Auto",
    "trader_a": "trader_a",
    "trader_b": "trader_b",
    "trader_c": "trader_c",
    "trader_d": "trader_d",
    "trader_3": "trader_3",
}


async def _browse_parse_db(output_input) -> None:
    def _pick_file() -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            return ""

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected_file = filedialog.askopenfilename(
                initialdir=str(_PROJECT_ROOT),
                title="Seleziona il DB da parsare",
                filetypes=[("SQLite DB", "*.sqlite3 *.db"), ("All files", "*.*")],
            )
        finally:
            root.destroy()
        return selected_file or ""

    selected = await asyncio.to_thread(_pick_file)
    if not selected:
        ui.notify("Selezione file annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()


async def _browse_reports_dir(output_input) -> None:
    def _pick_directory() -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            return ""

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected_dir = filedialog.askdirectory(
                initialdir=str(_PROJECT_ROOT),
                title="Seleziona la cartella CSV report",
                mustexist=False,
            )
        finally:
            root.destroy()
        return selected_dir or ""

    selected = await asyncio.to_thread(_pick_directory)
    if not selected:
        ui.notify("Selezione cartella annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()


def _resolve_output_dir(value: str) -> Path:
    path = Path(value.strip() or "parser_test/reports")
    return path if path.is_absolute() else (_PROJECT_ROOT / path).resolve()


def _safe_count(conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> int:
    try:
        row = conn.execute(query, params).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0]) if row else 0


async def _build_quality_report(db_path: str, trader_id: str) -> QualityReport:
    chains = await SignalChainBuilder.build_all_async(db_path=db_path)
    canonical = [adapt_signal_chain(chain) for chain in chains]

    warning_counter: Counter[str] = Counter()
    simulable = 0
    for chain in canonical:
        validation = validate_chain_for_simulation(chain)
        if validation.is_simulable:
            simulable += 1
        for gap in validation.warning_gaps + validation.fatal_gaps:
            warning_counter.update([gap.message])

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        trader_filter_sql = ""
        params: list[object] = []
        if trader_id.strip():
            trader_filter_sql = "WHERE COALESCE(pr.resolved_trader_id, '') = ?"
            params.append(trader_id.strip())

        rows = conn.execute(
            f"""
            SELECT
              pr.message_type AS message_type,
              COALESCE(pr.completeness, '') AS completeness,
              COALESCE(pr.warning_text, '') AS warning_text
            FROM parse_results pr
            {trader_filter_sql}
            """,
            params,
        ).fetchall()
        signals_rows = _safe_count(conn, "SELECT COUNT(*) FROM signals")
        operational_rows = _safe_count(conn, "SELECT COUNT(*) FROM operational_signals")
        operational_new_signal_rows = _safe_count(
            conn,
            "SELECT COUNT(*) FROM operational_signals WHERE message_type = 'NEW_SIGNAL'",
        )

    message_type_counter: Counter[str] = Counter()
    parse_warning_counter: Counter[str] = Counter()
    new_signal_complete = 0
    new_signal_incomplete = 0
    update_orphan_count = 0

    for row in rows:
        message_type = str(row["message_type"] or "UNCLASSIFIED")
        warning_text = str(row["warning_text"] or "").strip()
        completeness = str(row["completeness"] or "").strip().upper()
        message_type_counter.update([message_type])

        if message_type == "NEW_SIGNAL":
            if completeness == "COMPLETE":
                new_signal_complete += 1
            else:
                new_signal_incomplete += 1
        if message_type == "UPDATE" and "unresolved update target" in warning_text.lower():
            update_orphan_count += 1

        for part in [item.strip() for item in warning_text.split("|") if item.strip()]:
            parse_warning_counter.update([part])

    top_warnings = (warning_counter + parse_warning_counter).most_common(5)
    backtest_ready = operational_new_signal_rows > 0 and len(canonical) > 0
    return QualityReport(
        trader_id=trader_id.strip(),
        total_messages=len(rows),
        new_signal_count=message_type_counter["NEW_SIGNAL"],
        new_signal_complete=new_signal_complete,
        new_signal_incomplete=new_signal_incomplete,
        update_count=message_type_counter["UPDATE"],
        update_orphan_count=update_orphan_count,
        info_only_count=message_type_counter["INFO_ONLY"],
        unclassified_count=message_type_counter["UNCLASSIFIED"],
        total_signals=len(canonical),
        simulable_signals=simulable,
        non_simulable_signals=max(len(canonical) - simulable, 0),
        signals_rows=signals_rows,
        operational_signals_rows=operational_rows,
        operational_new_signal_rows=operational_new_signal_rows,
        backtest_ready=backtest_ready,
        top_warnings=top_warnings,
    )


async def _handle_parse(
    *,
    state: UiState,
    db_path: str,
    parser_profile: str,
    trader_mapping_path: str,
    generate_csv: bool,
    reports_dir: str,
    log_panel: LogPanel,
    report_container,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    state.parser_profile = canonicalize_trader_code(parser_profile.strip()) or ""
    state.trader_mapping_path = trader_mapping_path.strip()
    state.generate_parse_csv = generate_csv
    state.parse_reports_dir = reports_dir.strip() or "parser_test/reports"
    state.parsed_db_path = db_path.strip()
    state.proceed_to_backtest = False
    state.latest_reports_dir = ""
    log_panel.clear()
    if backtest_button_holder:
        backtest_button_holder[0].disable()

    if not state.parsed_db_path:
        ui.notify("Seleziona un DB prima del parse", color="negative")
        return

    log_panel.push("Fase 1/3 - Parse: avvio replay_parser.py (riprocessamento DB selezionato).")
    command = [
        sys.executable,
        "parser_test/scripts/replay_parser.py",
        "--db-path",
        state.parsed_db_path,
    ]
    if state.parser_profile:
        command += ["--trader", state.parser_profile]
    rc = await run_streaming_command(command, log_panel)
    if rc != 0:
        ui.notify("Replay parser fallito: controlla log", color="negative")
        return
    log_panel.push("Fase 1/3 - Parse: completata.")
    log_panel.push("Fase 2/3 - Operation rules: materializzo signals/operational_signals.")

    command = [
        sys.executable,
        "parser_test/scripts/replay_operation_rules.py",
        "--db-path",
        state.parsed_db_path,
    ]
    if state.parser_profile:
        command += ["--trader", state.parser_profile]
    rc = await run_streaming_command(command, log_panel)
    if rc != 0:
        ui.notify("Replay operation rules fallito: controlla log", color="negative")
        return

    reports_dir_resolved = _resolve_output_dir(state.parse_reports_dir)
    if state.generate_parse_csv:
        updated = await asyncio.to_thread(
            export_reports_csv_v2,
            db_path=state.parsed_db_path,
            reports_dir=reports_dir_resolved,
            trader=state.parser_profile or None,
        )
        state.latest_reports_dir = str(reports_dir_resolved)
        total_rows = sum(item.row_count for item in updated)
        log_panel.push(f"CSV generati in: {reports_dir_resolved}")
        log_panel.push(f"File aggiornati: {len(updated)} / righe scritte: {total_rows}")

    log_panel.push("Fase 3/3 - Chain builder: costruzione report di ricostruzione catene.")
    report = await _build_quality_report(state.parsed_db_path, state.parser_profile)
    with report_container:
        report_container.clear()
        render_quality_report(report, reports_dir=state.latest_reports_dir)

    state.proceed_to_backtest = report.backtest_ready
    if backtest_button_holder:
        if report.backtest_ready:
            backtest_button_holder[0].enable()
        else:
            backtest_button_holder[0].disable()

    if report.backtest_ready:
        log_panel.push(
            "Fase 3/3 - Chain builder: OK, trovate chain ricostruibili."
        )
        log_panel.push("Backtest: DB pronto.")
        ui.notify("Parse completato. Ora puoi procedere al backtest.", color="positive")
    else:
        log_panel.push(
            "Fase 3/3 - Chain builder: nessuna chain ricostruibile trovata."
        )
        log_panel.push("Backtest: bloccato finche' il DB non diventa backtestabile.")
        ui.notify(
            "Parse completato, ma il DB non contiene ancora chain backtestabili.",
            color="warning",
        )


def render_block_parse(
    state: UiState,
    *,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    """Renderizza il Blocco 2 — Parse dati.

    Args:
        state: stato condiviso dell'applicazione.
        backtest_button_holder: lista mutabile [button] riempita da render_block_backtest
            dopo il rendering; il lambda di click la legge al momento dell'esecuzione.
        run_streaming_command: callable async (command, log_panel) → int condiviso con app.py.
    """
    with ui.card().classes("w-full"):
        ui.label("Blocco 2 - Parse dati").classes("text-h6")
        with ui.row().classes("w-full items-end gap-2"):
            parse_db = ui.input("DB da parsare", value=state.effective_db_path()).classes("flex-1")

            async def _on_browse_parse_db() -> None:
                await _browse_parse_db(parse_db)

            ui.button("Sfoglia", on_click=_on_browse_parse_db, icon="folder_open")
        ui.label("Il DB selezionato verra' sempre riprocessato (parser + operation rules).").classes(
            "text-caption text-grey-7"
        )
        parser_profile = ui.select(
            options=_TRADER_OPTIONS,
            value=state.parser_profile,
            label="Trader filtro",
        ).classes("w-full")
        trader_mapping = ui.input("Trader mapping", value=state.trader_mapping_path)
        generate_csv = ui.checkbox("Genera CSV report a fine parse", value=state.generate_parse_csv)
        with ui.row().classes("w-full items-end gap-2"):
            reports_dir = ui.input("Cartella CSV report", value=state.parse_reports_dir).classes("flex-1")

            async def _on_browse_reports_dir() -> None:
                await _browse_reports_dir(reports_dir)

            ui.button("Sfoglia", on_click=_on_browse_reports_dir, icon="folder_open")
        block2_log = LogPanel(title="Log Parse")
        report_container = ui.column().classes("w-full")

        async def _on_parse_click() -> None:
            resolved_db_path = parse_db.value.strip() or state.effective_db_path()
            if resolved_db_path != parse_db.value:
                parse_db.value = resolved_db_path
                parse_db.update()
            await _handle_parse(
                state=state,
                db_path=resolved_db_path,
                parser_profile=parser_profile.value,
                trader_mapping_path=trader_mapping.value,
                generate_csv=bool(generate_csv.value),
                reports_dir=reports_dir.value,
                log_panel=block2_log,
                report_container=report_container,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=run_streaming_command,
            )

        ui.button("Esegui Parse + Chain Builder", on_click=_on_parse_click)
