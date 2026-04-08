"""Blocco 3 - Backtest."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from nicegui import ui

from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SUMMARY_RE = re.compile(
    r"^- (?P<policy>[^:]+): pnl=(?P<pnl>[-+]?\d+(?:\.\d+)?), "
    r"win_rate=(?P<win_rate>[-+]?\d+(?:\.\d+)?%), "
    r"expectancy=(?P<expectancy>[-+]?\d+(?:\.\d+)?), "
    r"trades=(?P<trades>\d+), excluded=(?P<excluded>\d+)"
)


def _can_enable_backtest(*, db_path: str) -> bool:
    return bool(db_path.strip()) and Path(db_path.strip()).exists()


def _market_plan_summary(plan_path: Path) -> dict[str, int]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    return {
        "symbols": int(summary.get("symbols", 0)),
        "required_intervals": int(summary.get("required_intervals", 0)),
        "gaps": int(summary.get("gaps", 0)),
    }


def _set_market_status(label, *, text: str, positive: bool | None = None) -> None:
    label.set_text(text)
    label.classes(remove="text-positive text-negative text-grey-6")
    if positive is True:
        label.classes(add="text-positive")
    elif positive is False:
        label.classes(add="text-negative")
    else:
        label.classes(add="text-grey-6")


def _invalidate_market_readiness(*, state: UiState, status_label, summary_label) -> None:
    state.market_data_ready = False
    state.market_data_checked = False
    state.market_data_gap_count = 0
    state.latest_market_plan_path = ""
    state.latest_market_sync_report_path = ""
    state.latest_market_validation_report_path = ""
    _set_market_status(status_label, text="Market data da verificare", positive=None)
    summary_label.set_text(
        "La cartella verra' analizzata prima del backtest. Se mancano intervalli, la GUI eseguira' plan/sync/validate."
    )


async def _browse_backtest_db(output_input) -> None:
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
                title="Seleziona il DB parsato",
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
    if hasattr(output_input, "_after_set"):
        output_input._after_set()


async def _browse_market_dir(output_input) -> None:
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
                title="Seleziona la cartella market data",
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


def _extract_summary_lines(log_panel: LogPanel) -> tuple[str | None, list[dict[str, str]]]:
    lines = log_panel.lines()
    chains_selected: str | None = None
    summaries: list[dict[str, str]] = []
    for line in lines:
        if line.startswith("chains_selected="):
            chains_selected = line.split("=", 1)[1].strip()
            continue
        match = _SUMMARY_RE.match(line.strip())
        if match:
            summaries.append(match.groupdict())
    return chains_selected, summaries


def _render_backtest_summary(*, container, chains_selected: str | None, summaries: list[dict[str, str]], artifact_path: str) -> None:
    with container:
        container.clear()
        with ui.card().classes("w-full"):
            ui.label("Report Backtest").classes("text-subtitle2")
            if chains_selected is not None:
                ui.label(f"Chain selezionate: {chains_selected}")
            if artifact_path:
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
    policy_name: str,
    market_data_dir: str,
    timeframe: str,
    price_basis: str,
    timeout_seconds: int,
    log_panel: LogPanel,
    market_status_label,
    market_summary_label,
    artifact_label,
    summary_container,
    run_streaming_command,
) -> None:
    import sys

    state.policy_name = policy_name.strip() or "original_chain"
    state.market_data_dir = market_data_dir.strip()
    state.timeframe = timeframe.strip() or "1m"
    state.price_basis = price_basis.strip() or "last"
    state.timeout_seconds = int(timeout_seconds)
    log_panel.clear()
    summary_container.clear()

    if not db_path.strip():
        ui.notify("Seleziona un DB parsato prima del backtest", color="negative")
        return
    if not state.market_data_dir:
        ui.notify("Seleziona la cartella market data", color="negative")
        return

    if not state.market_data_ready:
        ui.notify("Preparo/verifico prima la cache market data", color="warning")
        market_ready = await _prepare_market_data(
            state=state,
            db_path=db_path,
            market_data_dir=state.market_data_dir,
            timeframe=state.timeframe,
            price_basis=state.price_basis,
            log_panel=log_panel,
            status_label=market_status_label,
            summary_label=market_summary_label,
            run_streaming_command=run_streaming_command,
            silent=False,
        )
        if not market_ready:
            return

    command = [
        sys.executable,
        "scripts/run_scenario.py",
        "--policy",
        f"{state.policy_name},signal_only",
        "--db-path",
        db_path,
        "--market-dir",
        state.market_data_dir,
        "--price-basis",
        state.price_basis,
        "--timeframe",
        state.timeframe,
    ]

    try:
        rc = await asyncio.wait_for(
            run_streaming_command(command, log_panel),
            timeout=state.timeout_seconds,
        )
    except TimeoutError:
        ui.notify("Timeout backtest raggiunto", color="negative")
        return

    if rc != 0:
        ui.notify("Backtest fallito: controlla log", color="negative")
        return

    state.latest_artifact_path = "artifacts/scenarios"
    artifact_label.set_text(f"Artifact: {state.latest_artifact_path}")
    chains_selected, summaries = _extract_summary_lines(log_panel)
    _render_backtest_summary(
        container=summary_container,
        chains_selected=chains_selected,
        summaries=summaries,
        artifact_path=state.latest_artifact_path,
    )
    ui.notify("Backtest completato", color="positive")


async def _prepare_market_data(
    *,
    state: UiState,
    db_path: str,
    market_data_dir: str,
    timeframe: str,
    price_basis: str,
    log_panel: LogPanel,
    status_label,
    summary_label,
    run_streaming_command,
    silent: bool,
) -> bool:
    import sys

    db_path = db_path.strip()
    market_root = Path(market_data_dir.strip())
    timeframe = timeframe.strip() or "1m"
    price_basis = price_basis.strip() or "last"

    if not db_path:
        ui.notify("Seleziona un DB parsato prima di preparare i market data", color="negative")
        return False
    if not market_data_dir.strip():
        ui.notify("Seleziona la cartella market data", color="negative")
        return False
    if not Path(db_path).exists():
        ui.notify("DB parsato non trovato", color="negative")
        return False

    state.market_data_dir = str(market_root)
    state.timeframe = timeframe
    state.price_basis = price_basis

    if state.market_data_mode == "existing_dir" and not market_root.exists():
        ui.notify("La cartella market data selezionata non esiste", color="negative")
        _set_market_status(status_label, text="Market data non pronti: cartella inesistente", positive=False)
        return False

    market_root.mkdir(parents=True, exist_ok=True)
    mode_label = (
        "usa cartella esistente e integra i gap mancanti"
        if state.market_data_mode == "existing_dir"
        else "prepara da capo in una cartella dedicata"
    )
    log_panel.push("Fase market 1/3 - Planner: analisi copertura richiesta dal DB.")
    log_panel.push(f"Market data: modalita' selezionata -> {mode_label}.")
    log_panel.push(f"Market data: root locale -> {market_root}")
    log_panel.push(f"Market data: timeframe={timeframe}, basis primaria={price_basis}")
    _set_market_status(status_label, text="Market data: planner in esecuzione...", positive=None)

    plan_path = Path("artifacts/market_data/plan_market_data.json")
    sync_path = Path("artifacts/market_data/sync_market_data.json")
    validate_path = Path("artifacts/market_data/validate_market_data.json")

    plan_command = [
        sys.executable,
        "scripts/plan_market_data.py",
        "--db-path",
        db_path,
        "--market-dir",
        str(market_root),
        "--timeframe",
        timeframe,
        "--bases",
        "last,mark",
        "--output",
        str(plan_path),
    ]
    rc = await run_streaming_command(plan_command, log_panel)
    if rc != 0 or not plan_path.exists():
        ui.notify("Planner market data fallito", color="negative")
        _set_market_status(status_label, text="Market data: planner fallito", positive=False)
        return False

    plan_summary = _market_plan_summary(plan_path)
    state.latest_market_plan_path = str(plan_path)
    state.market_data_gap_count = plan_summary["gaps"]
    log_panel.push(
        "Fase market 1/3 - Planner: completata. "
        f"simboli={plan_summary['symbols']}, intervalli={plan_summary['required_intervals']}, gap={plan_summary['gaps']}."
    )
    log_panel.push(f"Artifact planner: {plan_path}")
    summary_label.set_text(
        f"Planner: simboli={plan_summary['symbols']}, intervalli={plan_summary['required_intervals']}, gap={plan_summary['gaps']}."
    )

    if plan_summary["gaps"] > 0:
        log_panel.push("Fase market 2/3 - Sync: avvio integrazione gap mancanti.")
        log_panel.push(
            f"Market data: trovati {plan_summary['gaps']} gap. Avvio sync incrementale sulla cache locale."
        )
        _set_market_status(status_label, text="Market data: sync gap mancanti...", positive=None)
        sync_command = [
            sys.executable,
            "scripts/sync_market_data.py",
            "--plan-file",
            str(plan_path),
            "--db-path",
            db_path,
            "--market-dir",
            str(market_root),
            "--output",
            str(sync_path),
        ]
        rc = await run_streaming_command(sync_command, log_panel)
        if rc != 0 or not sync_path.exists():
            ui.notify("Sync market data fallito", color="negative")
            _set_market_status(status_label, text="Market data: sync fallito", positive=False)
            return False
        state.latest_market_sync_report_path = str(sync_path)
        log_panel.push(f"Fase market 2/3 - Sync: completata. Artifact sync: {sync_path}")
    else:
        log_panel.push("Fase market 2/3 - Sync: nessun gap trovato, step saltato.")
        log_panel.push("Market data: nessun gap trovato, sync non necessario.")

    log_panel.push("Fase market 3/3 - Validate: verifica consistenza cache locale.")
    _set_market_status(status_label, text="Market data: validazione in corso...", positive=None)
    validate_command = [
        sys.executable,
        "scripts/validate_market_data.py",
        "--plan-file",
        str(plan_path),
        "--market-dir",
        str(market_root),
        "--output",
        str(validate_path),
    ]
    rc = await run_streaming_command(validate_command, log_panel)
    if rc != 0 or not validate_path.exists():
        ui.notify("Validazione market data fallita", color="negative")
        _set_market_status(status_label, text="Market data: validazione fallita", positive=False)
        return False

    state.latest_market_validation_report_path = str(validate_path)
    log_panel.push(f"Fase market 3/3 - Validate: completata. Artifact validate: {validate_path}")
    state.market_data_ready = True
    state.market_data_checked = True
    if plan_summary["gaps"] > 0:
        _set_market_status(
            status_label,
            text=f"Market data pronti: integrati {plan_summary['gaps']} gap e validati",
            positive=True,
        )
    else:
        _set_market_status(status_label, text="Market data pronti: cache gia' completa e validata", positive=True)

    summary_label.set_text(
        "Artifacts market data: "
        f"plan={state.latest_market_plan_path}, "
        f"sync={state.latest_market_sync_report_path or '-'}, "
        f"validate={state.latest_market_validation_report_path}"
    )
    log_panel.push("Market data: cache pronta per il backtest.")
    if not silent:
        ui.notify("Market data pronti per il backtest", color="positive")
    return True


def render_block_backtest(
    state: UiState,
    *,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    """Renderizza il Blocco 3 - Backtest."""
    with ui.card().classes("w-full"):
        ui.label("Blocco 3 - Backtest").classes("text-h6")

        with ui.row().classes("w-full items-end gap-2"):
            backtest_db = ui.input("DB parsato", value=state.effective_db_path()).classes("flex-1")
            db_status = ui.label("").classes("text-caption")

            async def _on_browse_backtest_db() -> None:
                await _browse_backtest_db(backtest_db)

            ui.button("Sfoglia", on_click=_on_browse_backtest_db, icon="folder_open")

        policy_name = ui.select(
            options={
                "original_chain": "original_chain",
                "signal_only": "signal_only",
            },
            value=state.policy_name,
            label="Policy baseline",
        ).classes("w-full")

        with ui.row().classes("w-full items-end gap-2"):
            market_data_dir = ui.input("Cartella market data", value=state.market_data_dir).classes("flex-1")

            async def _on_browse_market_dir() -> None:
                await _browse_market_dir(market_data_dir)

            ui.button("Sfoglia", on_click=_on_browse_market_dir, icon="folder_open")

        market_data_mode = ui.radio(
            {
                "existing_dir": "Usa cartella esistente e integra i gap mancanti",
                "new_dir": "Prepara da capo in una nuova cartella",
            },
            value=state.market_data_mode,
        ).props("inline")
        market_mode_hint = ui.label("").classes("text-caption text-grey-7")
        market_status = ui.label("").classes("text-caption text-grey-6")
        market_summary = ui.label("").classes("text-caption text-grey-7")

        with ui.row().classes("w-full gap-4"):
            timeframe = ui.input("Timeframe (es. 1m)", value=state.timeframe).classes("flex-1")
            price_basis = ui.select(
                options={"last": "last (standard)", "mark": "mark (mark price)"},
                value=state.price_basis,
                label="Price basis",
            ).classes("flex-1")
            timeout_seconds = ui.number("Timeout (s)", value=state.timeout_seconds, min=5, step=5).classes("flex-1")

        block3_log = LogPanel(title="Log Backtest")
        artifact_label = ui.label(f"Artifact: {state.latest_artifact_path or '-'}")
        summary_container = ui.column().classes("w-full")

        async def _on_backtest_click() -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            if resolved_db_path != backtest_db.value:
                backtest_db.value = resolved_db_path
                backtest_db.update()
                _refresh_backtest_button()
            await _handle_backtest(
                state=state,
                db_path=resolved_db_path,
                policy_name=policy_name.value,
                market_data_dir=market_data_dir.value,
                timeframe=timeframe.value,
                price_basis=price_basis.value,
                timeout_seconds=int(timeout_seconds.value),
                log_panel=block3_log,
                market_status_label=market_status,
                market_summary_label=market_summary,
                artifact_label=artifact_label,
                summary_container=summary_container,
                run_streaming_command=run_streaming_command,
            )

        async def _on_prepare_market_data() -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            if resolved_db_path != backtest_db.value:
                backtest_db.value = resolved_db_path
                backtest_db.update()
            block3_log.clear()
            summary_container.clear()
            ready = await _prepare_market_data(
                state=state,
                db_path=resolved_db_path,
                market_data_dir=market_data_dir.value,
                timeframe=timeframe.value,
                price_basis=price_basis.value,
                log_panel=block3_log,
                status_label=market_status,
                summary_label=market_summary,
                run_streaming_command=run_streaming_command,
                silent=False,
            )
            if ready:
                _refresh_backtest_button()

        def _refresh_market_mode_hint(*_) -> None:
            state.market_data_mode = market_data_mode.value
            if market_data_mode.value == "existing_dir":
                market_mode_hint.set_text(
                    "La cartella indicata viene controllata contro il DB; se mancano periodi, la GUI li aggiunge prima del run."
                )
            else:
                market_mode_hint.set_text(
                    "La cartella puo' essere nuova o vuota: il planner costruisce la cache richiesta dal DB e poi la valida."
                )
            _invalidate_market_readiness(state=state, status_label=market_status, summary_label=market_summary)
            _refresh_backtest_button()

        def _on_market_inputs_change(*_) -> None:
            _invalidate_market_readiness(state=state, status_label=market_status, summary_label=market_summary)
            _refresh_backtest_button()

        def _refresh_backtest_button(*_) -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            has_market_dir = bool(market_data_dir.value.strip())
            if _can_enable_backtest(db_path=resolved_db_path) and has_market_dir:
                db_status.set_text("DB valido")
                db_status.classes(remove="text-negative text-grey-6")
                db_status.classes(add="text-positive")
                run_backtest_button.enable()
            elif _can_enable_backtest(db_path=resolved_db_path) and not has_market_dir:
                db_status.set_text("DB valido ma cartella market data non selezionata")
                db_status.classes(remove="text-positive")
                db_status.classes(add="text-negative")
                run_backtest_button.disable()
            else:
                db_status.set_text("DB non trovato o non selezionato")
                db_status.classes(remove="text-positive")
                db_status.classes(add="text-negative")
                run_backtest_button.disable()

        run_backtest_button = ui.button("Esegui Backtest", on_click=_on_backtest_click)
        ui.button("Prepara / verifica market data", on_click=_on_prepare_market_data, color="secondary")
        backtest_db._after_set = _refresh_backtest_button
        backtest_db.on("update:model-value", _refresh_backtest_button)
        market_data_dir.on("update:model-value", _on_market_inputs_change)
        timeframe.on("update:model-value", _on_market_inputs_change)
        price_basis.on("update:model-value", _on_market_inputs_change)
        market_data_mode.on("update:model-value", _refresh_market_mode_hint)
        _refresh_market_mode_hint()
        _refresh_backtest_button()

    backtest_button_holder.append(run_backtest_button)
