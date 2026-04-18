"""NiceGUI entry point for Sprint 9: download -> parse -> backtest."""
from __future__ import annotations

import asyncio
import logging

from nicegui import ui
import nicegui.run as nicegui_run

from src.signal_chain_lab.ui.blocks.block_backtest import render_block_backtest
from src.signal_chain_lab.ui.blocks.block_download import render_block_download
from src.signal_chain_lab.ui.blocks.block_parse import render_block_parse
from src.signal_chain_lab.ui.blocks.market_data_panel import render_market_data_panel
from src.signal_chain_lab.ui.state import UiState

APP_STATE = UiState()


def _patch_nicegui_process_pool_setup() -> None:
    """Allow startup to continue when Windows blocks ProcessPool creation."""
    original_setup = nicegui_run.setup

    def _safe_setup() -> None:
        try:
            original_setup()
        except PermissionError as exc:
            logging.warning("NiceGUI process pool disabled: %s", exc)

    nicegui_run.setup = _safe_setup


async def _run_streaming_command(command: list[str], log_panel, process_started=None) -> int:
    log_panel.push(f"$ {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    if process_started is not None:
        process_started(process)
    assert process.stdout is not None
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        log_panel.push(line.decode("utf-8", errors="replace").rstrip())
    return await process.wait()


@ui.page("/")
def main_page() -> None:
    ui.label("Signal Chain Lab - Sprint 9 GUI").classes("text-h5")
    ui.label("Workflow guidato: Download dati -> Parse dati -> Backtest").classes("text-body2 text-grey-7")

    backtest_button_holder: list = []

    def _remember_active_tab(value: str | None) -> None:
        if value in {"download", "parse", "backtest"}:
            APP_STATE.active_tab = value

    with ui.tabs(value=APP_STATE.active_tab).classes("w-full") as tabs:
        ui.tab("download", label="1. Download")
        ui.tab("parse", label="2. Parse")
        ui.tab("backtest", label="3. Backtest")
    tabs.on("update:model-value", lambda e: _remember_active_tab(e.args))

    with ui.tab_panels(tabs, value=APP_STATE.active_tab).classes("w-full") as panels:
        with ui.tab_panel("download"):
            render_block_download(APP_STATE, run_streaming_command=_run_streaming_command)
        with ui.tab_panel("parse"):
            render_block_parse(
                APP_STATE,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=_run_streaming_command,
            )
        with ui.tab_panel("backtest"):
            ui.label("Blocco 3 - Backtest").classes("text-h6")
            render_market_data_panel(APP_STATE, run_streaming_command=_run_streaming_command)
            render_block_backtest(
                APP_STATE,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=_run_streaming_command,
            )
    panels.on("update:model-value", lambda e: _remember_active_tab(e.args))


def run() -> None:
    _patch_nicegui_process_pool_setup()
    ui.run(title="Signal Chain Lab GUI", reload=False, port=7777)


if __name__ in {"__main__", "__mp_main__"}:
    run()
