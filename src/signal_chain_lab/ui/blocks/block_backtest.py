"""Blocco 3 - Backtest."""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from nicegui import ui
from src.signal_chain_lab.ui.blocks.backtest_support import (
    discover_date_range_from_db,
    discover_policy_names,
    discover_traders_from_db,
    load_policy_yaml,
    policies_dir_path,
    save_policy_yaml,
)
from src.signal_chain_lab.ui.blocks.backtest_observability import (
    append_benchmark_entry,
    compute_benchmark_snapshot,
)
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.file_dialogs import ask_directory, ask_open_filename
from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SUMMARY_RE = re.compile(
    r"^- (?P<policy>[^:]+): pnl=(?P<pnl>[-+]?\d+(?:\.\d+)?), "
    r"win_rate=(?P<win_rate>[-+]?\d+(?:\.\d+)?%), "
    r"expectancy=(?P<expectancy>[-+]?\d+(?:\.\d+)?), "
    r"trades=(?P<trades>\d+), excluded=(?P<excluded>\d+)"
)
_BENCHMARK_PATH = Path("artifacts/market_data/backtest_benchmark.json")


def _can_enable_backtest(*, db_path: str) -> bool:
    return bool(db_path.strip()) and Path(db_path.strip()).exists()


async def _browse_backtest_db(output_input) -> None:
    selected = ask_open_filename(
        initialdir=_PROJECT_ROOT,
        title="Seleziona il DB parsato",
        filetypes=[("SQLite DB", "*.sqlite3 *.db"), ("All files", "*.*")],
    )
    if not selected:
        ui.notify("Selezione file annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()
    if hasattr(output_input, "_after_set"):
        output_input._after_set()


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


def _render_backtest_summary(
    *,
    container,
    chains_selected: str | None,
    summaries: list[dict[str, str]],
    artifact_path: str,
    html_path: str | None = None,
) -> None:
    from pathlib import Path as _Path

    with container:
        container.clear()
        with ui.card().classes("w-full"):
            ui.label("Report Backtest").classes("text-subtitle2")
            if chains_selected is not None:
                ui.label(f"Chain selezionate: {chains_selected}")
            if html_path and _Path(html_path).exists():
                ui.link(
                    "Apri report HTML",
                    target=_Path(html_path).resolve().as_uri(),
                    new_tab=True,
                ).classes("text-primary text-caption")
            elif artifact_path:
                ui.label(f"Artifact: {artifact_path}").classes("text-caption text-grey-7")

            if not summaries:
                ui.label("Nessun riepilogo policy trovato nel log.").classes("text-grey-6")
                return

            for item in summaries:
                with ui.card().classes("w-full bg-slate-50"):
                    ui.label(item["policy"]).classes("text-body1")
                    with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-1"):
                        ui.label(f"Trades: {item['trades']}")
                        ui.label(f"Escluse: {item['excluded']}")
                        ui.label(f"PnL: {item['pnl']}")
                        ui.label(f"Win rate: {item['win_rate']}")
                        ui.label(f"Expectancy: {item['expectancy']}")


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
    artifact_label,
    summary_container,
    run_streaming_command,
) -> None:
    from datetime import datetime as _dt

    run_t0 = time.perf_counter()
    policies_clean = [p.strip() for p in policies if p.strip()]
    if not policies_clean:
        ui.notify("Seleziona almeno una policy prima del backtest", color="negative")
        return

    date_from_clean = date_from_str.strip()
    date_to_clean = date_to_str.strip()
    if date_from_clean:
        try:
            _dt.fromisoformat(date_from_clean)
        except ValueError:
            ui.notify("Formato 'Dal' non valido: usa YYYY-MM-DD", color="negative")
            return
    if date_to_clean:
        try:
            _dt.fromisoformat(date_to_clean)
        except ValueError:
            ui.notify("Formato 'Al' non valido: usa YYYY-MM-DD", color="negative")
            return
    if date_from_clean and date_to_clean:
        if _dt.fromisoformat(date_from_clean) > _dt.fromisoformat(date_to_clean):
            ui.notify("'Dal' deve essere <= 'Al'", color="negative")
            return

    state.backtest_policies = policies_clean
    state.backtest_trader_filter = trader_filter or "all"
    state.backtest_date_from = date_from_clean
    state.backtest_date_to = date_to_clean
    state.backtest_max_trades = max(0, int(max_trades))
    state.backtest_report_dir = report_dir.strip()
    state.timeout_seconds = int(timeout_seconds)
    log_panel.clear()
    summary_container.clear()

    if not db_path.strip():
        ui.notify("Seleziona un DB parsato prima del backtest", color="negative")
        return

    if not state.market.market_ready:
        ui.notify(
            "Market data non pronti: usa il pannello Market DATA (in alto) per preparare i dati prima del backtest.",
            color="negative",
        )
        return

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
            run_streaming_command(command, log_panel),
            timeout=state.timeout_seconds,
        )
    except TimeoutError:
        ui.notify("Timeout backtest", color="negative")
        return
    if rc != 0:
        ui.notify("Backtest fallito: controlla log", color="negative")
        return
    backtest_elapsed = time.perf_counter() - backtest_t0

    state.latest_artifact_path = effective_report_dir
    artifact_label.set_text(f"Artifact: {state.latest_artifact_path}")
    chains_selected, summaries, html_path = _extract_summary_lines(log_panel)
    state.latest_html_report_path = html_path or ""
    _render_backtest_summary(
        container=summary_container,
        chains_selected=chains_selected,
        summaries=summaries,
        artifact_path=state.latest_artifact_path,
        html_path=html_path,
    )
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
        pairs = [f"{k}={v:.2f}s" for k, v in snapshot.items()]
        log_panel.push("Benchmark snapshot: " + ", ".join(pairs))
    ui.notify("Backtest completato", color="positive")


def render_block_backtest(
    state: UiState,
    *,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    """Renderizza la sezione Backtest di Blocco 3 (senza Market DATA)."""
    def _invalidate_market_context_if_needed() -> None:
        if state.market.market_ready or state.market.market_validation_status != "needs_check":
            state.market.mark_needs_check()

    def _sync_selected_db_to_state(db_path: str) -> None:
        clean = db_path.strip()
        if clean == state.parsed_db_path:
            return
        state.parsed_db_path = clean
        _invalidate_market_context_if_needed()

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

    with ui.card().classes("w-full"):
        ui.label("Backtest").classes("text-h6")

        with ui.row().classes("w-full items-end gap-2"):
            backtest_db = ui.input("DB parsato", value=state.effective_db_path()).classes("flex-1")
            db_status = ui.label("").classes("text-caption")

            async def _on_browse_backtest_db() -> None:
                await _browse_backtest_db(backtest_db)

            ui.button("Sfoglia", on_click=_on_browse_backtest_db, icon="folder_open")

        # --- Policy selector ---
        def _build_policy_options() -> dict[str, str]:
            names = discover_policy_names()
            return {n: n for n in names}

        with ui.row().classes("w-full items-center gap-2"):
            ui.label("Policy da eseguire").classes("text-caption text-grey-8")
            ui.button(
                "Ricarica", icon="refresh", color="secondary",
                on_click=lambda: _on_reload_policies(),
            ).props("dense flat")
            ui.button(
                "Modifica", icon="edit", color="secondary",
                on_click=lambda: _on_edit_policy(),
            ).props("dense flat")
            ui.button(
                "Nuova", icon="add", color="secondary",
                on_click=lambda: _on_new_policy(),
            ).props("dense flat")
        ui.label(f"Cartella policy: {policies_dir_path()}").classes("text-caption text-grey-6")

        policy_select = ui.select(
            options=_build_policy_options(),
            value=[p for p in state.backtest_policies if p in _build_policy_options()],
            label="Policy",
            multiple=True,
        ).classes("w-full")
        ui.label(
            "Seleziona una o piu' policy. Se ne scegli più di una, il confronto viene eseguito in un unico run."
        ).classes("text-caption text-grey-6")

        def _on_reload_policies() -> None:
            opts = _build_policy_options()
            policy_select.options = opts
            current = policy_select.value if isinstance(policy_select.value, list) else []
            policy_select.value = [v for v in current if v in opts] or list(opts.keys())[:2]
            policy_select.update()
            ui.notify(f"Policy ricaricate: {len(opts)} trovate", color="info")

        def _on_edit_policy() -> None:
            selected = policy_select.value if isinstance(policy_select.value, list) else []
            if not selected:
                ui.notify("Seleziona almeno una policy da modificare", color="warning")
                return
            policy_to_edit = selected[0]
            content = load_policy_yaml(policy_to_edit)
            if not content:
                ui.notify(f"File YAML per '{policy_to_edit}' non trovato", color="warning")
                return

            with ui.dialog() as dlg, ui.card().classes("min-w-[640px] w-full"):
                ui.label(f"Editor policy: {policy_to_edit}").classes("text-subtitle2")
                editor = ui.textarea(value=content).classes("w-full font-mono").style(
                    "height:420px; font-size:12px; white-space:pre"
                )

                def _save_overwrite() -> None:
                    try:
                        import yaml as _yaml
                        _yaml.safe_load(editor.value)
                    except Exception as exc:
                        ui.notify(f"YAML non valido: {exc}", color="negative")
                        return
                    save_policy_yaml(policy_to_edit, editor.value)
                    ui.notify(f"Policy '{policy_to_edit}' salvata", color="positive")
                    dlg.close()

                def _open_save_as_dialog() -> None:
                    with ui.dialog() as dlg2, ui.card():
                        ui.label("Salva come nuova policy").classes("text-subtitle2")
                        name_input = ui.input(
                            "Nome policy (es. be_after_tp2)",
                            placeholder="solo lettere, cifre, _ e -",
                        ).classes("w-full")

                        def _confirm_save_as() -> None:
                            import re as _re
                            new_name = name_input.value.strip()
                            if not new_name:
                                ui.notify("Inserisci un nome", color="warning")
                                return
                            if not _re.match(r'^[a-z][a-z0-9_-]*$', new_name):
                                ui.notify(
                                    "Nome non valido: usa solo lettere minuscole, cifre, _ e -",
                                    color="warning",
                                )
                                return
                            try:
                                import yaml as _yaml
                                _yaml.safe_load(editor.value)
                            except Exception as exc:
                                ui.notify(f"YAML non valido: {exc}", color="negative")
                                return
                            path = save_policy_yaml(new_name, editor.value)
                            ui.notify(f"Policy '{new_name}' salvata in {path}", color="positive")
                            dlg2.close()
                            dlg.close()
                            _on_reload_policies()

                        with ui.row():
                            ui.button("Salva", on_click=_confirm_save_as)
                            ui.button("Annulla", on_click=dlg2.close)
                    dlg2.open()

                with ui.row().classes("gap-2 mt-2"):
                    ui.button("Salva", on_click=_save_overwrite)
                    ui.button("Salva come nuova...", on_click=_open_save_as_dialog)
                    ui.button("Chiudi", on_click=dlg.close)
            dlg.open()

        def _on_new_policy() -> None:
            template_names = discover_policy_names()
            template_content = load_policy_yaml(template_names[0]) if template_names else ""

            with ui.dialog() as dlg, ui.card().classes("min-w-[640px] w-full"):
                ui.label("Nuova policy").classes("text-subtitle2")
                name_input = ui.input(
                    "Nome policy (es. my_custom)",
                    placeholder="solo lettere, cifre, _ e -",
                ).classes("w-full")
                editor = ui.textarea(value=template_content).classes("w-full font-mono").style(
                    "height:400px; font-size:12px; white-space:pre"
                )

                def _save_new() -> None:
                    import re as _re
                    new_name = name_input.value.strip()
                    if not new_name:
                        ui.notify("Inserisci un nome", color="warning")
                        return
                    if not _re.match(r'^[a-z][a-z0-9_-]*$', new_name):
                        ui.notify(
                            "Nome non valido: usa solo lettere minuscole, cifre, _ e -",
                            color="warning",
                        )
                        return
                    try:
                        import yaml as _yaml
                        _yaml.safe_load(editor.value)
                    except Exception as exc:
                        ui.notify(f"YAML non valido: {exc}", color="negative")
                        return
                    path = save_policy_yaml(new_name, editor.value)
                    ui.notify(f"Policy '{new_name}' salvata in {path}", color="positive")
                    dlg.close()
                    _on_reload_policies()

                with ui.row().classes("gap-2 mt-2"):
                    ui.button("Salva nuova policy", on_click=_save_new)
                    ui.button("Annulla", on_click=dlg.close)
            dlg.open()

        # --- Filtri dataset ---
        def _refresh_trader_select(db_path: str) -> None:
            db_path = db_path.strip()
            traders = discover_traders_from_db(db_path)
            opts: dict[str, str] = {"all": "Tutti i trader"}
            opts.update({t: t for t in traders})
            trader_select.options = opts
            if trader_select.value not in opts:
                trader_select.value = "all"
            trader_hint.set_text(
                f"{len(traders)} trader trovati" if traders else "Nessun trader rilevato"
            )
            trader_select.update()

            min_date, max_date = discover_date_range_from_db(db_path)
            if min_date and not date_from_input.value:
                date_from_input.value = min_date
                date_from_input.update()
            if max_date and not date_to_input.value:
                date_to_input.value = max_date
                date_to_input.update()
            _sync_dataset_filters_to_state(
                trader_filter=trader_select.value or "all",
                date_from=date_from_input.value or "",
                date_to=date_to_input.value or "",
                max_trades=int(max_trades_input.value or 0),
            )

        with ui.expansion("Filtri dataset", icon="filter_list").classes("w-full"):
            with ui.row().classes("w-full gap-4 items-end"):
                trader_select = ui.select(
                    options={"all": "Tutti i trader"},
                    value=state.backtest_trader_filter or "all",
                    label="Trader",
                ).classes("flex-1")
                trader_hint = ui.label("").classes("text-caption text-grey-6 self-center")
                ui.button(
                    "Rileva",
                    icon="search",
                    color="secondary",
                    on_click=lambda: _refresh_trader_select(backtest_db.value),
                ).props("dense flat")

            with ui.row().classes("w-full gap-4 mt-2"):
                date_from_input = ui.input(
                    "Dal (YYYY-MM-DD)", value=state.backtest_date_from,
                    placeholder="es. 2024-01-01",
                ).classes("flex-1")
                date_to_input = ui.input(
                    "Al (YYYY-MM-DD)", value=state.backtest_date_to,
                    placeholder="es. 2024-12-31",
                ).classes("flex-1")
                max_trades_input = ui.number(
                    "Max trade (0 = tutti)", value=state.backtest_max_trades, min=0, step=10,
                ).classes("flex-1")

            ui.label(
                "Campi vuoti = nessun filtro. Max trade = 0 significa nessun limite."
            ).classes("text-caption text-grey-6 mt-1")

        # --- Timeout e report dir ---
        with ui.row().classes("w-full gap-4"):
            timeout_seconds = ui.number("Timeout (s)", value=state.timeout_seconds, min=5, step=5).classes("flex-1")

        with ui.row().classes("w-full items-end gap-2"):
            report_dir_input = ui.input(
                "Cartella report output",
                value=state.backtest_report_dir,
                placeholder="default: artifacts/scenarios",
            ).classes("flex-1")
            ui.label("Lascia vuoto per il default (artifacts/scenarios).").classes(
                "text-caption text-grey-6 self-center"
            )

            async def _on_browse_report_dir() -> None:
                await _browse_report_dir(report_dir_input)

            ui.button("Sfoglia", on_click=_on_browse_report_dir, icon="folder_open")

        # Market readiness indicator (read-only, managed by Market DATA panel)
        market_status_info = ui.label("").classes("text-caption text-grey-6")

        def _refresh_market_status_info() -> None:
            if state.market.market_ready:
                market_status_info.set_text(
                    f"Market data: {state.market.market_validation_status} — pronti per il backtest."
                )
                market_status_info.classes(remove="text-negative text-grey-6", add="text-positive")
            else:
                market_status_info.set_text(
                    "Market data non pronti: usa il pannello Market DATA (sopra) per preparare i dati."
                )
                market_status_info.classes(remove="text-positive", add="text-grey-6")

        _refresh_market_status_info()

        block3_log = LogPanel(title="Log Backtest")
        artifact_label = ui.label(f"Artifact: {state.latest_artifact_path or '-'}")
        summary_container = ui.column().classes("w-full")

        async def _on_backtest_click() -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            if resolved_db_path != backtest_db.value:
                backtest_db.value = resolved_db_path
                backtest_db.update()
                _refresh_backtest_button()
            _sync_selected_db_to_state(resolved_db_path)
            selected_policies = (
                policy_select.value
                if isinstance(policy_select.value, list)
                else ([policy_select.value] if policy_select.value else [])
            )
            _sync_dataset_filters_to_state(
                trader_filter=trader_select.value or "all",
                date_from=date_from_input.value or "",
                date_to=date_to_input.value or "",
                max_trades=int(max_trades_input.value or 0),
            )
            _refresh_market_status_info()
            await _handle_backtest(
                state=state,
                db_path=resolved_db_path,
                policies=selected_policies,
                trader_filter=trader_select.value or "all",
                date_from_str=date_from_input.value,
                date_to_str=date_to_input.value,
                max_trades=int(max_trades_input.value or 0),
                report_dir=report_dir_input.value,
                timeout_seconds=int(timeout_seconds.value),
                log_panel=block3_log,
                artifact_label=artifact_label,
                summary_container=summary_container,
                run_streaming_command=run_streaming_command,
            )

        def _refresh_backtest_button(*_) -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            if _can_enable_backtest(db_path=resolved_db_path):
                db_status.set_text("DB valido")
                db_status.classes(remove="text-negative text-grey-6", add="text-positive")
                run_backtest_button.enable()
            else:
                db_status.set_text("DB non trovato o non selezionato")
                db_status.classes(remove="text-positive", add="text-negative")
                run_backtest_button.disable()

        run_backtest_button = ui.button("Esegui Backtest", on_click=_on_backtest_click)

        def _on_db_path_change(*_) -> None:
            _sync_selected_db_to_state(backtest_db.value.strip() or state.effective_db_path())
            _refresh_backtest_button()
            _refresh_trader_select(backtest_db.value.strip() or state.effective_db_path())

        def _on_filters_change(*_) -> None:
            _sync_dataset_filters_to_state(
                trader_filter=trader_select.value or "all",
                date_from=date_from_input.value or "",
                date_to=date_to_input.value or "",
                max_trades=int(max_trades_input.value or 0),
            )

        backtest_db._after_set = _on_db_path_change
        backtest_db.on("update:model-value", _on_db_path_change)
        trader_select.on("update:model-value", _on_filters_change)
        date_from_input.on("update:model-value", _on_filters_change)
        date_to_input.on("update:model-value", _on_filters_change)
        max_trades_input.on("update:model-value", _on_filters_change)
        _refresh_backtest_button()
        if state.db_exists():
            _refresh_trader_select(state.effective_db_path())

    backtest_button_holder.append(run_backtest_button)
