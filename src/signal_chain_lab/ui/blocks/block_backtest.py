"""Blocco 3 - Backtest."""
from __future__ import annotations

import asyncio
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
    timeout_seconds: int,
    log_panel: LogPanel,
    artifact_label,
    summary_container,
    run_streaming_command,
) -> None:
    import sys

    state.policy_name = policy_name.strip() or "original_chain"
    state.market_data_dir = market_data_dir.strip()
    state.timeframe = timeframe.strip()
    state.timeout_seconds = int(timeout_seconds)
    log_panel.clear()
    summary_container.clear()

    if not db_path.strip():
        ui.notify("Seleziona un DB parsato prima del backtest", color="negative")
        return
    if not state.market_data_dir:
        ui.notify("Seleziona la cartella market data", color="negative")
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

        with ui.row().classes("w-full gap-4"):
            timeframe = ui.input("Timeframe", value=state.timeframe).classes("flex-1")
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
                db_status.classes(remove="text-negative text-grey-6")
                db_status.classes(add="text-positive")
                run_backtest_button.enable()
            else:
                db_status.set_text("DB non trovato o non selezionato")
                db_status.classes(remove="text-positive")
                db_status.classes(add="text-negative")
                run_backtest_button.disable()

        run_backtest_button = ui.button("Esegui Backtest", on_click=_on_backtest_click)
        backtest_db._after_set = _refresh_backtest_button
        backtest_db.on("update:model-value", _refresh_backtest_button)
        _refresh_backtest_button()

    backtest_button_holder.append(run_backtest_button)
