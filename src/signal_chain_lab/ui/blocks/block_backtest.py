"""Blocco 3 - Backtest."""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from nicegui import ui

from src.signal_chain_lab.ui.blocks.backtest_observability import (
    append_benchmark_entry,
    compute_benchmark_snapshot,
)
from src.signal_chain_lab.ui.blocks.backtest_support import (
    discover_policy_names,
    find_html_report,
    load_policy_yaml,
    market_backtest_gate,
    policies_dir_path,
    save_policy_yaml,
)
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.file_dialogs import ask_directory
from src.signal_chain_lab.ui.persistence import debounced_save
from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_BENCHMARK_PATH = Path("artifacts/market_data/backtest_benchmark.json")
_SUMMARY_RE = re.compile(
    r"^- (?P<policy>[^:]+): pnl=(?P<pnl>[-+]?\d+(?:\.\d+)?), "
    r"win_rate=(?P<win_rate>[-+]?\d+(?:\.\d+)?%), "
    r"expectancy=(?P<expectancy>[-+]?\d+(?:\.\d+)?), "
    r"trades=(?P<trades>\d+), excluded=(?P<excluded>\d+)"
)
_POLICY_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_TF_OPTIONS_BT = {"1m": "1m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1D"}


class _BacktestCtx:
    process: object = None  # asyncio.subprocess.Process | None
    stop_requested: bool = False


_backtest_ctx = _BacktestCtx()


def _can_enable_backtest(*, db_path: str) -> bool:
    return bool(db_path.strip()) and Path(db_path.strip()).exists()


def _market_backtest_gate(state: UiState) -> tuple[bool, str, str]:
    """Backward-compatible wrapper around the shared coverage gate."""
    return market_backtest_gate(state)


async def _browse_report_dir(output_input) -> None:
    selected = ask_directory(
        initialdir=_PROJECT_ROOT / "artifacts",
        title="Seleziona la cartella report output",
        mustexist=False,
    )
    if not selected:
        ui.notify("Selezione cartella annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()


def _extract_summary_lines(
    log_panel: LogPanel,
) -> tuple[str | None, list[dict[str, str]], str | None]:
    lines = log_panel.lines()
    chains_selected: str | None = None
    summaries: list[dict[str, str]] = []
    html_path: str | None = None
    for line in lines:
        if line.startswith("chains_selected="):
            chains_selected = line.split("=", 1)[1].strip()
            continue
        if line.startswith("scenario_html="):
            html_path = line.split("=", 1)[1].strip()
            continue
        if line.startswith("policy_report_html="):
            html_path = line.split("=", 1)[1].strip()
            continue
        match = _SUMMARY_RE.match(line.strip())
        if match:
            summaries.append(match.groupdict())
    return chains_selected, summaries, html_path


def _build_single_policy_command(*, db_path: str, state: UiState, output_dir: str) -> list[str]:
    import sys

    runtime_tf = state.market.simulation_tf or state.market.download_tf
    command = [
        sys.executable,
        "scripts/run_policy_report.py",
        "--policy",
        state.backtest_policies[0],
        "--db-path",
        db_path,
        "--market-dir",
        state.market.market_data_dir,
        "--price-basis",
        state.market.price_basis,
        "--timeframe",
        runtime_tf,
    ]
    if state.backtest_trader_filter and state.backtest_trader_filter != "all":
        command += ["--trader-id", state.backtest_trader_filter]
    if state.backtest_date_from:
        command += ["--date-from", state.backtest_date_from]
    if state.backtest_date_to:
        command += ["--date-to", state.backtest_date_to]
    if state.backtest_max_trades > 0:
        command += ["--max-trades", str(state.backtest_max_trades)]
    command += ["--output-dir", output_dir]
    return command


def _build_multi_policy_command(*, db_path: str, state: UiState, output_dir: str) -> list[str]:
    import sys

    runtime_tf = state.market.simulation_tf or state.market.download_tf
    command = [
        sys.executable,
        "scripts/run_scenario.py",
        "--policies",
        *state.backtest_policies,
        "--db-path",
        db_path,
        "--market-dir",
        state.market.market_data_dir,
        "--price-basis",
        state.market.price_basis,
        "--timeframe",
        runtime_tf,
    ]
    if state.backtest_trader_filter and state.backtest_trader_filter != "all":
        command += ["--trader-id", state.backtest_trader_filter]
    if state.backtest_date_from:
        command += ["--date-from", state.backtest_date_from]
    if state.backtest_date_to:
        command += ["--date-to", state.backtest_date_to]
    if state.backtest_max_trades > 0:
        command += ["--max-trades", str(state.backtest_max_trades)]
    command += ["--output-dir", output_dir]
    return command


def _results_table_html(summaries: list[dict[str, str]], html_path: str | None = None) -> str:
    if not summaries:
        return (
            '<span style="font-family:var(--mono);font-size:11px;color:var(--muted)">'
            "- nessun run eseguito -</span>"
        )

    th = (
        "background:var(--surface-2);color:var(--muted);font-size:9px;font-weight:600;"
        "text-transform:uppercase;letter-spacing:.08em;padding:6px 10px;text-align:left;"
        "border-bottom:1px solid var(--border-s)"
    )
    td = (
        "padding:6px 10px;font-family:var(--mono);font-size:11px;color:var(--text2);"
        "border-bottom:1px solid var(--border-s)"
    )
    td_c = td + ";text-align:center"
    report_cell = '<span style="font-size:11px;color:var(--muted)">-</span>'
    if html_path and Path(html_path).exists():
        report_url = Path(html_path).resolve().as_uri()
        report_cell = (
            f'<a href="{report_url}" target="_blank" '
            'style="font-size:11px;color:var(--accent);text-decoration:none">Apri</a>'
        )

    header = (
        f'<tr><th style="{th}">Policy</th><th style="{th}">Trades</th>'
        f'<th style="{th}">Excluded</th><th style="{th}">PnL %</th>'
        f'<th style="{th}">Win rate</th><th style="{th}">Expectancy</th>'
        f'<th style="{th}">Report</th></tr>'
    )
    rows = "".join(
        f'<tr>'
        f'<td style="{td}">{item["policy"]}</td>'
        f'<td style="{td_c}">{item["trades"]}</td>'
        f'<td style="{td_c}">{item["excluded"]}</td>'
        f'<td style="{td_c}">{item["pnl"]}</td>'
        f'<td style="{td_c}">{item["win_rate"]}</td>'
        f'<td style="{td_c}">{item["expectancy"]}</td>'
        f'<td style="{td_c}">{report_cell}</td>'
        f"</tr>"
        for item in summaries
    )
    return (
        f'<table class="res-tbl" style="width:100%;border-collapse:collapse;'
        f'background:var(--surface-2);border:1px solid var(--border-s);">'
        f"<thead>{header}</thead><tbody>{rows}</tbody></table>"
    )


def _validate_policy_name(policy_name: str) -> bool:
    return bool(_POLICY_NAME_RE.match(policy_name))


def _open_fs_target(target: str) -> None:
    import os

    if hasattr(os, "startfile"):
        os.startfile(target)
    else:
        os.system(f'xdg-open "{target}"')


async def _handle_backtest(
    *,
    state: UiState,
    db_path: str,
    policies: list[str],
    trader_filter: str,
    date_from_str: str,
    date_to_str: str,
    max_trades: int,
    report_dir: str,
    timeout_seconds: int,
    log_panel: LogPanel,
    run_streaming_command,
    process_started=None,
) -> tuple[list[dict[str, str]], str | None]:
    from datetime import datetime as _dt

    run_t0 = time.perf_counter()
    policies_clean = [p.strip() for p in policies if p.strip()]
    if not policies_clean:
        ui.notify("Seleziona almeno una policy prima del backtest", color="negative")
        return [], None

    date_from_clean = date_from_str.strip()
    date_to_clean = date_to_str.strip()
    if date_from_clean:
        try:
            _dt.fromisoformat(date_from_clean)
        except ValueError:
            ui.notify("Formato 'Dal' non valido: usa YYYY-MM-DD", color="negative")
            return [], None
    if date_to_clean:
        try:
            _dt.fromisoformat(date_to_clean)
        except ValueError:
            ui.notify("Formato 'Al' non valido: usa YYYY-MM-DD", color="negative")
            return [], None
    if date_from_clean and date_to_clean and _dt.fromisoformat(date_from_clean) > _dt.fromisoformat(date_to_clean):
        ui.notify("'Dal' deve essere <= 'Al'", color="negative")
        return [], None

    state.backtest_policies = policies_clean
    state.backtest_trader_filter = trader_filter or "all"
    state.backtest_date_from = date_from_clean
    state.backtest_date_to = date_to_clean
    state.backtest_max_trades = max(0, int(max_trades))
    state.backtest_report_dir = report_dir.strip()
    state.timeout_seconds = int(timeout_seconds)

    if not db_path.strip():
        ui.notify("Seleziona un DB parsato prima del backtest", color="negative")
        return [], None

    allowed, market_message, market_style = market_backtest_gate(state)
    log_panel.clear()
    log_panel.push(f"[check] {market_message}")
    if not allowed:
        ui.notify(market_message, color="negative")
        return [], None
    if market_style == "warning":
        ui.notify(market_message, color="warning")

    is_single_policy = len(state.backtest_policies) == 1
    effective_report_dir = state.backtest_report_dir or (
        "artifacts/policy_reports" if is_single_policy else "artifacts/scenarios"
    )
    command = (
        _build_single_policy_command(db_path=db_path, state=state, output_dir=effective_report_dir)
        if is_single_policy
        else _build_multi_policy_command(db_path=db_path, state=state, output_dir=effective_report_dir)
    )
    if is_single_policy:
        log_panel.push(f"--- Backtest single-policy: {state.backtest_policies[0]} ---")
    else:
        log_panel.push(f"--- Backtest multi-policy: {', '.join(state.backtest_policies)} ---")

    backtest_t0 = time.perf_counter()
    try:
        rc = await asyncio.wait_for(
            run_streaming_command(command, log_panel, process_started),
            timeout=state.timeout_seconds,
        )
    except TimeoutError:
        ui.notify("Timeout backtest", color="negative")
        return [], None

    if rc != 0:
        ui.notify("Backtest fallito: controlla log", color="negative")
        return [], None

    backtest_elapsed = time.perf_counter() - backtest_t0
    state.latest_artifact_path = effective_report_dir
    _, summaries, html_path = _extract_summary_lines(log_panel)
    if not html_path:
        report_dir_path = Path(effective_report_dir)
        latest_html = find_html_report(report_dir_path)
        html_path = str(latest_html) if latest_html else None
    state.latest_html_report_path = html_path or ""

    total_elapsed = time.perf_counter() - run_t0
    log_panel.push(f"Timing backtest: {backtest_elapsed:.2f}s")
    log_panel.push(f"Timing run totale: {total_elapsed:.2f}s")

    benchmark_entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "validate_mode": state.market.validate_mode,
        "policy_count": len(state.backtest_policies),
        "policies": state.backtest_policies,
        "market_validation_status": state.market.market_validation_status,
        "market_timing_seconds": state.market.market_prepare_total_seconds,
        "backtest_seconds": round(backtest_elapsed, 3),
        "total_seconds": round(total_elapsed, 3),
    }
    benchmark_payload = append_benchmark_entry(_BENCHMARK_PATH, benchmark_entry)
    snapshot = compute_benchmark_snapshot(benchmark_payload)
    if snapshot:
        pairs = [f"{key}={value:.2f}s" for key, value in snapshot.items()]
        log_panel.push("Benchmark snapshot: " + ", ".join(pairs))

    ui.notify("Backtest completato", color="positive")
    return summaries, html_path


def render_block_backtest(
    state: UiState,
    *,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    """Render the Backtesting sub-tab of Tab 3."""

    def _persist() -> None:
        debounced_save(state.to_dict())

    def _build_policy_options() -> dict[str, str]:
        return {name: name for name in discover_policy_names()}

    def _invalidate_market_context_if_needed() -> None:
        if state.market.market_ready or state.market.market_validation_status != "needs_check":
            state.market.mark_needs_check()

    def _sync_selected_db_to_state(db_path: str) -> None:
        clean = db_path.strip()
        if clean == state.parsed_db_path:
            return
        state.parsed_db_path = clean
        _invalidate_market_context_if_needed()
        _persist()

    def _sync_dataset_filters_to_state(*, trader_filter: str, date_from: str, date_to: str, max_trades: int) -> None:
        new_trader = trader_filter or "all"
        new_from = date_from.strip()
        new_to = date_to.strip()
        new_max = max(0, int(max_trades))
        changed = (
            state.backtest_trader_filter != new_trader
            or state.backtest_date_from != new_from
            or state.backtest_date_to != new_to
            or state.backtest_max_trades != new_max
        )
        state.backtest_trader_filter = new_trader
        state.backtest_date_from = new_from
        state.backtest_date_to = new_to
        state.backtest_max_trades = new_max
        if changed:
            _invalidate_market_context_if_needed()
            _persist()

    with ui.column().style("padding:16px 20px;gap:16px").classes("w-full block-shell"):
        with ui.row().classes("section-head"):
            ui.label("04").classes("section-step")
            ui.label("· Backtesting").style(
                "font-family:var(--sans);font-size:15px;font-weight:600;color:var(--text)"
            )

        ui.html(
            '<div style="background:var(--accent-d);border:1px solid var(--accent);'
            'border-radius:var(--rs);padding:8px 12px;font-size:12px;color:var(--text2)">'
            "ℹ Price basis e Market source sono rilevati automaticamente dalla cartella Market Data."
            "</div>"
        )

        ui.html('<div class="sec-lbl">Policy</div>')
        with ui.row().classes("w-full items-center gap-2"):
            policy_select = ui.select(
                options=_build_policy_options(),
                value=[p for p in state.backtest_policies if p in _build_policy_options()],
                label="Policy da eseguire",
                multiple=True,
            ).classes("flex-1")
            ui.button("↻", on_click=lambda: _on_reload_policies()).props("flat dense").style(
                "font-family:var(--mono);color:var(--muted)"
            )

        with ui.row().classes("w-full gap-4 items-end"):
            timeout_minutes = ui.number(
                "Timeout (m)",
                value=max(1, state.timeout_seconds // 60),
                min=1,
                step=1,
            ).classes("w-28")
            report_dir_input = ui.input(
                "Report output dir",
                value=state.backtest_report_dir,
                placeholder="default: artifacts/scenarios",
            ).classes("flex-1 inp-mono")
            report_dir_hint = ui.label("").style("font-size:11px;color:var(--er)")

            async def _on_browse_report_dir() -> None:
                await _browse_report_dir(report_dir_input)
                _on_report_dir_change()

            ui.button("Sfoglia", on_click=_on_browse_report_dir, icon="folder_open")

        with ui.row().classes("w-full gap-4"):
            sim_tf_select = ui.select(
                options=_TF_OPTIONS_BT,
                value=state.market.simulation_tf if state.market.simulation_tf in _TF_OPTIONS_BT else "1m",
                label="Simulation TF",
            ).classes("flex-1")
            detail_tf_select = ui.select(
                options=_TF_OPTIONS_BT,
                value=state.market.detail_tf if state.market.detail_tf in _TF_OPTIONS_BT else "1m",
                label="Detail TF / childs",
            ).classes("flex-1")
            ui.input(
                label="Price basis · auto da market dir",
                value=state.market.price_basis,
            ).props("readonly").classes("flex-1 inp-mono").style("color:var(--muted)")
            ui.input(
                label="Market source · auto da market dir",
                value=state.market.market_data_source,
            ).props("readonly").classes("flex-1 inp-mono").style("color:var(--muted)")

        def _on_tf_change(*_) -> None:
            state.market.simulation_tf = sim_tf_select.value or "1m"
            state.market.detail_tf = detail_tf_select.value or "1m"
            _persist()

        sim_tf_select.on("update:model-value", _on_tf_change)
        detail_tf_select.on("update:model-value", _on_tf_change)

        current_policy_input = {"name": ""}
        with ui.expansion("Policy Studio", icon="tune").classes("w-full").style(
            "border:1px solid var(--border-s);border-radius:var(--rs);background:var(--surface-2)"
        ):
            ui.label(str(policies_dir_path())).classes("path-chip")
            with ui.row().classes("w-full gap-4 items-end"):
                policy_editor_select = ui.select(
                    options=_build_policy_options(),
                    value=(state.backtest_policies[0] if state.backtest_policies else None),
                    label="Policy editor",
                ).classes("flex-1")
                new_policy_name_input = ui.input(
                    "Nuova policy",
                    placeholder="solo lettere, cifre, _ e -",
                ).classes("flex-1 inp-mono")
            policy_editor = ui.textarea().classes("w-full inp-mono").style(
                "height:320px;font-size:12px;white-space:pre"
            )

            def _load_policy_into_editor(policy_name: str | None) -> None:
                if not policy_name:
                    current_policy_input["name"] = ""
                    policy_editor.value = ""
                    policy_editor.update()
                    return
                current_policy_input["name"] = policy_name
                policy_editor.value = load_policy_yaml(policy_name)
                policy_editor.update()

            def _validate_yaml(text: str) -> None:
                import yaml

                yaml.safe_load(text)

            def _save_policy(policy_name: str) -> None:
                if not _validate_policy_name(policy_name):
                    ui.notify("Nome policy non valido", color="warning")
                    return
                try:
                    _validate_yaml(policy_editor.value)
                except Exception as exc:  # pragma: no cover - UI validation path
                    ui.notify(f"YAML non valido: {exc}", color="negative")
                    return
                save_policy_yaml(policy_name, policy_editor.value)
                current_policy_input["name"] = policy_name
                _on_reload_policies(select_name=policy_name)
                policy_editor_select.value = policy_name
                policy_editor_select.update()
                ui.notify(f"Policy '{policy_name}' salvata", color="positive")

            def _save_current_policy() -> None:
                if not current_policy_input["name"]:
                    ui.notify("Seleziona una policy da salvare", color="warning")
                    return
                _save_policy(current_policy_input["name"])

            def _save_as_new_policy() -> None:
                _save_policy(new_policy_name_input.value.strip())

            def _new_policy_from_template() -> None:
                template_names = discover_policy_names()
                current_policy_input["name"] = ""
                policy_editor.value = load_policy_yaml(template_names[0]) if template_names else ""
                policy_editor.update()
                policy_editor_select.value = None
                policy_editor_select.update()

            def _on_reload_policies(*, select_name: str | None = None) -> None:
                opts = _build_policy_options()
                policy_select.options = opts
                selected = policy_select.value if isinstance(policy_select.value, list) else []
                policy_select.value = [value for value in selected if value in opts] or list(opts.keys())[:2]
                policy_select.update()

                policy_editor_select.options = opts
                target_name = select_name or current_policy_input["name"] or next(iter(opts), None)
                if target_name in opts:
                    policy_editor_select.value = target_name
                    _load_policy_into_editor(target_name)
                else:
                    policy_editor_select.value = None
                    _load_policy_into_editor(None)
                policy_editor_select.update()
                ui.notify(f"Policy ricaricate: {len(opts)} trovate", color="info")

            policy_editor_select.on("update:model-value", lambda e: _load_policy_into_editor(e.value))
            _load_policy_into_editor(policy_editor_select.value)

            with ui.row().classes("gap-2 q-mt-sm"):
                ui.button("Salva", on_click=_save_current_policy).props("dense outline")
                ui.button("Salva come nuova", on_click=_save_as_new_policy).props("dense outline")
                ui.button("Nuova policy", on_click=_new_policy_from_template).props("dense outline")
                ui.button("Ricarica lista", on_click=lambda: _on_reload_policies()).props("dense outline")

        _, init_msg, init_style = market_backtest_gate(state)
        gate_colors = {
            "positive": "var(--ok)",
            "warning": "var(--wa)",
            "grey": "var(--muted)",
            "error": "var(--er)",
        }
        market_status_html = ui.html(
            f'<span style="font-family:var(--mono);font-size:11px;color:{gate_colors.get(init_style, "var(--muted)")}">'
            f"● {init_msg}</span>"
        )

        def _refresh_market_status() -> None:
            _, msg, style = market_backtest_gate(state)
            color = gate_colors.get(style, "var(--muted)")
            market_status_html.set_content(
                f'<span style="font-family:var(--mono);font-size:11px;color:{color}">● {msg}</span>'
            )

        def _refresh_path_validity() -> None:
            report_path = report_dir_input.value.strip()
            report_invalid = bool(report_path) and not Path(report_path).exists()
            report_dir_input.style(f"border-color:{'var(--er)' if report_invalid else 'var(--border)'}")
            report_dir_hint.set_text("percorso non trovato" if report_invalid else "")

        ui.html('<div class="sec-lbl" style="margin-top:4px">Risultati</div>')
        results_html = ui.html(_results_table_html([]))

        block3_log = LogPanel(title="Log Backtest")

        async def _on_backtest_click() -> None:
            resolved_db_path = state.effective_db_path().strip()
            _sync_selected_db_to_state(resolved_db_path)

            selected_policies = (
                policy_select.value if isinstance(policy_select.value, list)
                else ([policy_select.value] if policy_select.value else [])
            )
            _sync_dataset_filters_to_state(
                trader_filter=state.backtest_trader_filter or "all",
                date_from=state.backtest_date_from or "",
                date_to=state.backtest_date_to or "",
                max_trades=int(state.backtest_max_trades or 0),
            )
            state.timeout_seconds = max(1, int(timeout_minutes.value or 1)) * 60
            _persist()

            def _bind_process(proc) -> None:
                _backtest_ctx.process = proc

            _backtest_ctx.stop_requested = False
            _refresh_market_status()
            summaries, html_path = await _handle_backtest(
                state=state,
                db_path=resolved_db_path,
                policies=selected_policies,
                trader_filter=state.backtest_trader_filter or "all",
                date_from_str=state.backtest_date_from,
                date_to_str=state.backtest_date_to,
                max_trades=int(state.backtest_max_trades or 0),
                report_dir=report_dir_input.value,
                timeout_seconds=state.timeout_seconds,
                log_panel=block3_log,
                run_streaming_command=run_streaming_command,
                process_started=_bind_process,
            )
            _backtest_ctx.process = None
            results_html.set_content(_results_table_html(summaries, html_path))
            _refresh_market_status()

        def _on_stop_backtest() -> None:
            if _backtest_ctx.process is None:
                ui.notify("Nessun backtest in corso", color="warning")
                return
            _backtest_ctx.stop_requested = True
            block3_log.push("Richiesta arresto backtest...")
            try:
                _backtest_ctx.process.terminate()
            except ProcessLookupError:
                pass
            ui.notify("Arresto backtest richiesto", color="warning")

        def _open_html_report() -> None:
            report_path = state.latest_html_report_path
            if not report_path or not Path(report_path).exists():
                ui.notify("Nessun report HTML disponibile", color="warning")
                return
            _open_fs_target(str(Path(report_path).resolve()))

        def _open_artifact_dir() -> None:
            artifact_path = state.latest_artifact_path
            if not artifact_path:
                ui.notify("Nessun artifact disponibile", color="warning")
                return
            target = Path(artifact_path)
            resolved = str(target.resolve() if target.is_dir() else target.parent.resolve())
            _open_fs_target(resolved)

        with ui.row().classes("gap-2"):
            run_backtest_button = ui.button("▶ Esegui Backtest", on_click=_on_backtest_click).props("color=primary")
            ui.button("■ Arresta", on_click=_on_stop_backtest).style(
                "color:var(--er);border-color:var(--er)"
            ).props("outline")
            ui.button("📄 Apri report HTML", on_click=_open_html_report).props("outline")
            ui.button("📂 Artifact dir", on_click=_open_artifact_dir).props("outline")

        def _refresh_backtest_button(*_) -> None:
            resolved_db_path = state.effective_db_path().strip()
            if _can_enable_backtest(db_path=resolved_db_path):
                run_backtest_button.enable()
            else:
                run_backtest_button.disable()

        def _on_report_dir_change(*_) -> None:
            state.backtest_report_dir = report_dir_input.value.strip()
            _refresh_path_validity()
            _persist()

        def _on_policy_change(*_) -> None:
            selected = policy_select.value if isinstance(policy_select.value, list) else []
            state.backtest_policies = [item for item in selected if item]
            _persist()

        timeout_minutes.on(
            "update:model-value",
            lambda *_: (
                setattr(state, "timeout_seconds", max(1, int(timeout_minutes.value or 1)) * 60),
                _persist(),
            ),
        )
        report_dir_input.on("update:model-value", _on_report_dir_change)
        policy_select.on("update:model-value", _on_policy_change)

        _refresh_backtest_button()
        _refresh_path_validity()

    backtest_button_holder.append(run_backtest_button)
