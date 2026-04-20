"""Blocco 2 — Parse dati.

Lancia replay_parser.py sul DB selezionato, costruisce le chain
canoniche, e produce il quality report sintetico. Sblocca Blocco 3
solo dopo parse completato con successo (checkpoint umano).
"""
from __future__ import annotations

import asyncio
import os
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
from src.signal_chain_lab.ui.file_dialogs import ask_directory, ask_open_filename
from src.signal_chain_lab.ui.persistence import debounced_save
from src.signal_chain_lab.ui.state import QualityReport, UiState


class _ParseCtx:
    process: asyncio.subprocess.Process | None = None
    stop_requested: bool = False


_parse_ctx = _ParseCtx()


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
    selected = ask_open_filename(
        initialdir=_PROJECT_ROOT,
        title="Seleziona il DB da parsare",
        filetypes=[("SQLite DB", "*.sqlite3 *.db"), ("All files", "*.*")],
    )
    if not selected:
        ui.notify("Selezione file annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()


async def _browse_reports_dir(output_input) -> None:
    selected = ask_directory(
        initialdir=_PROJECT_ROOT,
        title="Seleziona la cartella CSV report",
        mustexist=False,
    )
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


def _reset_derived_tables(db_path: str, trader_id: str) -> tuple[int, int]:
    with sqlite3.connect(db_path) as conn:
        if trader_id.strip():
            params = (trader_id.strip(),)
            operational_deleted = conn.execute(
                "DELETE FROM operational_signals WHERE trader_id = ?",
                params,
            ).rowcount
            signals_deleted = conn.execute(
                "DELETE FROM signals WHERE trader_id = ?",
                params,
            ).rowcount
        else:
            operational_deleted = conn.execute("DELETE FROM operational_signals").rowcount
            signals_deleted = conn.execute("DELETE FROM signals").rowcount
        conn.commit()
    return int(operational_deleted or 0), int(signals_deleted or 0)


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
    generate_csv: bool,
    reports_dir: str,
    log_panel: LogPanel,
    report_container,
    backtest_button_holder: list,
    run_streaming_command,
    process_started=None,
) -> None:
    state.parser_profile = canonicalize_trader_code(parser_profile.strip()) or ""
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
    rc = await run_streaming_command(command, log_panel, process_started)
    if rc != 0:
        ui.notify("Replay parser fallito: controlla log", color="negative")
        return
    log_panel.push("Fase 1/3 - Parse: completata.")
    log_panel.push("Fase 2/3 - Operation rules: materializzo signals/operational_signals.")
    operational_deleted, signals_deleted = await asyncio.to_thread(
        _reset_derived_tables,
        state.parsed_db_path,
        state.parser_profile,
    )
    log_panel.push(
        "Pulizia tabelle derivate completata: "
        f"operational_signals={operational_deleted}, signals={signals_deleted}."
    )

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


def _get_message_count(db_path: str) -> int | None:
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM raw_messages").fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None


def _open_dir(path: str) -> None:
    p = Path(path)
    if not p.exists():
        ui.notify("Cartella non trovata", color="warning")
        return
    target = str(p) if p.is_dir() else str(p.parent)
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        os.system(f'open "{target}"')
    else:
        os.system(f'xdg-open "{target}"')


def _stop_parse(log_panel: LogPanel) -> None:
    if _parse_ctx.process is None:
        ui.notify("Nessun parse in corso", color="warning")
        return
    _parse_ctx.stop_requested = True
    log_panel.push("Richiesta arresto parse...")
    try:
        _parse_ctx.process.terminate()
    except ProcessLookupError:
        pass
    ui.notify("Arresto parse richiesto", color="warning")


def _status_card_html(title: str, pill: str, pill_ok: bool, detail: str) -> str:
    pill_style = (
        "background:var(--ok-d);color:var(--ok);border:1px solid var(--ok)"
        if pill_ok
        else "background:var(--er-d);color:var(--er);border:1px solid var(--er)"
    )
    return (
        f'<div style="background:var(--surface-2);border:1px solid var(--border-s);'
        f'border-radius:var(--rs);padding:10px 14px">'
        f'<div style="font-size:9px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:.1em;color:var(--muted);margin-bottom:6px">{title}</div>'
        f'<span style="display:inline-flex;align-items:center;font-family:var(--mono);'
        f'font-size:10px;font-weight:600;padding:2px 8px;border-radius:var(--rs);'
        f'text-transform:uppercase;letter-spacing:.06em;{pill_style}">{pill}</span>'
        f'<div style="font-family:var(--mono);font-size:10px;color:var(--muted);'
        f'margin-top:6px">{detail}</div>'
        f'</div>'
    )


def _warnings_table_html(top_warnings: list[tuple[str, int]]) -> str:
    if not top_warnings:
        return '<span style="font-family:var(--mono);font-size:11px;color:var(--muted)">— nessun warning</span>'
    rows = "".join(
        f'<tr>'
        f'<td style="padding:3px 8px;color:var(--text2);font-family:var(--mono);font-size:11px">{msg[:60]}</td>'
        f'<td style="padding:3px 8px;text-align:center">'
        f'<span style="background:var(--wa-d);color:var(--wa);border:1px solid var(--wa);'
        f'border-radius:var(--rs);padding:1px 6px;font-family:var(--mono);font-size:10px">{cnt}</span>'
        f'</td>'
        f'</tr>'
        for msg, cnt in top_warnings
    )
    return (
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="text-align:left;padding:3px 8px;font-size:9px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:.1em;color:var(--muted)">Tipo / Warning</th>'
        f'<th style="padding:3px 8px;font-size:9px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:.1em;color:var(--muted)">Count</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
    )


def render_block_parse(
    state: UiState,
    *,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    """Renderizza il Blocco 2 — Parse dati."""
    def _persist() -> None:
        debounced_save(state.to_dict())

    with ui.card().style(
        "background:var(--surface);border:1px solid var(--border);"
        "border-radius:var(--r);padding:18px"
    ).classes("w-full block-card"):

        # ── title ─────────────────────────────────────────────────────────
        with ui.row().style("align-items:baseline;gap:8px;margin-bottom:12px"):
            ui.html('<span style="font-family:var(--mono);font-size:11px;color:var(--muted)">02</span>')
            ui.label("· Parse — Signal chain reconstruction").style(
                "font-family:var(--sans);font-size:15px;font-weight:600;color:var(--text)"
            )

        # ── DB source ─────────────────────────────────────────────────────
        ui.html('<div class="sec-lbl">Database sorgente</div>')
        with ui.row().classes("w-full items-end gap-2"):
            parse_db = ui.input(
                "Path DB SQLite", value=state.effective_db_path()
            ).classes("flex-1 inp-mono")

            async def _on_browse_parse_db() -> None:
                await _browse_parse_db(parse_db)
                _refresh_db_chip()

            ui.button("Sfoglia", on_click=_on_browse_parse_db, icon="folder_open")

        db_chip = ui.html("").style("margin-top:4px")

        def _refresh_db_chip() -> None:
            path = parse_db.value.strip()
            count = _get_message_count(path) if path and Path(path).exists() else None
            count_txt = f" · {count:,} messaggi" if count is not None else ""
            name = Path(path).name if path else "—"
            invalid = bool(path) and not Path(path).exists()
            parse_db.style(f"border-color:{'var(--er)' if invalid else 'var(--border)'}")
            db_chip.set_content(
                f'<span class="path-chip">🗄 {name}{count_txt}</span>'
            )

        def _on_parse_db_change(*_) -> None:
            state.parsed_db_path = parse_db.value.strip()
            _refresh_db_chip()
            _persist()

        parse_db.on("update:model-value", _on_parse_db_change)
        _refresh_db_chip()

        # ── trader filter + CSV toggle (same row) ─────────────────────────
        with ui.row().classes("w-full items-center gap-4 q-mt-sm"):
            parser_profile = ui.select(
                options=_TRADER_OPTIONS,
                value=state.parser_profile,
                label="Trader profile",
            ).classes("flex-1")
            generate_csv = ui.switch("Esporta CSV", value=state.generate_parse_csv)

        # ── reports dir ───────────────────────────────────────────────────
        with ui.row().classes("w-full items-end gap-2 q-mt-sm"):
            reports_dir = ui.input(
                "Cartella CSV report", value=state.parse_reports_dir
            ).classes("flex-1 inp-mono")
            reports_dir_hint = ui.label("").style("font-size:11px;color:var(--er)")

            async def _on_browse_reports_dir() -> None:
                await _browse_reports_dir(reports_dir)
                _on_reports_dir_change()

            ui.button("Sfoglia", on_click=_on_browse_reports_dir, icon="folder_open")

        def _on_reports_dir_change(*_) -> None:
            state.parse_reports_dir = reports_dir.value.strip() or "parser_test/reports"
            invalid = bool(reports_dir.value.strip()) and not Path(reports_dir.value.strip()).exists()
            reports_dir.style(f"border-color:{'var(--er)' if invalid else 'var(--border)'}")
            reports_dir_hint.set_text("percorso non trovato" if invalid else "")
            _persist()

        # ── status cards (3 col) ──────────────────────────────────────────
        ui.html('<div class="sec-lbl" style="margin-top:16px;margin-bottom:8px">Stato pipeline</div>')
        with ui.grid(columns=3).classes("w-full gap-3") as _st_grid:
            st_parse = ui.html(_status_card_html("Parse", "not started", False, "—"))
            st_chain = ui.html(_status_card_html("Chain Builder", "not started", False, "—"))
            st_bt = ui.html(_status_card_html("Backtest Readiness", "not started", False, "—"))

        def _update_status_cards(report: QualityReport) -> None:
            st_parse.set_content(_status_card_html(
                "Parse", "ok" if report.total_messages > 0 else "vuoto",
                report.total_messages > 0,
                f"{report.total_messages:,} msg · {report.new_signal_count} NS · {report.update_count} UPD",
            ))
            st_chain.set_content(_status_card_html(
                "Chain Builder", "ok" if report.total_signals > 0 else "n/a",
                report.total_signals > 0,
                f"{report.total_signals} chain · {report.simulable_signals} simulabili",
            ))
            st_bt.set_content(_status_card_html(
                "Backtest Readiness", "pronto" if report.backtest_ready else "bloccato",
                report.backtest_ready,
                f"op_signals={report.operational_signals_rows} · ns={report.operational_new_signal_rows}",
            ))

        # ── top warnings ──────────────────────────────────────────────────
        ui.html('<div class="sec-lbl" style="margin-top:16px;margin-bottom:6px">Top warnings</div>')
        warnings_html = ui.html(_warnings_table_html([]))

        def _update_warnings(report: QualityReport) -> None:
            warnings_html.set_content(_warnings_table_html(report.top_warnings))

        # ── action buttons ────────────────────────────────────────────────
        async def _on_parse_click() -> None:
            if _parse_ctx.process is not None:
                ui.notify("Parse già in corso", color="warning")
                return
            resolved_db_path = parse_db.value.strip() or state.effective_db_path()
            if resolved_db_path != parse_db.value:
                parse_db.value = resolved_db_path
                parse_db.update()

            def _bind_process(proc) -> None:
                _parse_ctx.process = proc

            await _handle_parse(
                state=state,
                db_path=resolved_db_path,
                parser_profile=parser_profile.value,
                generate_csv=bool(generate_csv.value),
                reports_dir=reports_dir.value,
                log_panel=block2_log,
                report_container=_report_sink,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=run_streaming_command,
                process_started=_bind_process,
            )
            _parse_ctx.process = None
            _parse_ctx.stop_requested = False
            # refresh status if report was produced
            if state.parsed_db_path:
                try:
                    report = await _build_quality_report(state.parsed_db_path, state.parser_profile)
                    _update_status_cards(report)
                    _update_warnings(report)
                    _refresh_db_chip()
                except Exception:
                    pass

        async def _on_export_csv() -> None:
            db = parse_db.value.strip() or state.effective_db_path()
            if not db:
                ui.notify("Nessun DB selezionato", color="warning")
                return
            resolved = _resolve_output_dir(reports_dir.value)
            try:
                updated = await asyncio.to_thread(
                    export_reports_csv_v2,
                    db_path=db,
                    reports_dir=resolved,
                    trader=parser_profile.value or None,
                )
                ui.notify(f"CSV esportati: {len(updated)} file", color="positive")
                state.latest_reports_dir = str(resolved)
            except Exception as exc:
                ui.notify(f"Errore export CSV: {exc}", color="negative")

        with ui.row().classes("gap-2 q-mt-md"):
            ui.button("Esegui Parse", on_click=_on_parse_click).props("color=primary")
            ui.button(
                "Arresta",
                on_click=lambda: _stop_parse(block2_log),
            ).style("color:var(--er);border-color:var(--er)").props("outline")
            ui.button(
                "Apri report qualita",
                on_click=lambda: _open_dir(state.latest_reports_dir or reports_dir.value),
            ).props("outline")
            ui.button("Esporta CSV", on_click=_on_export_csv).props("outline")

        # ── log ───────────────────────────────────────────────────────────
        block2_log = LogPanel(title="Log Parse")

        # sink for legacy report_container references in _handle_parse
        _report_sink = ui.column().classes("w-full").style("display:none")
        parser_profile.on(
            "update:model-value",
            lambda *_: (setattr(state, "parser_profile", parser_profile.value or ""), _persist()),
        )
        generate_csv.on(
            "update:model-value",
            lambda *_: (setattr(state, "generate_parse_csv", bool(generate_csv.value)), _persist()),
        )
        reports_dir.on("update:model-value", _on_reports_dir_change)
        _on_reports_dir_change()
