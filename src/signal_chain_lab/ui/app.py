"""NiceGUI entry point for Sprint 9: download -> parse -> backtest."""
from __future__ import annotations

import asyncio

from nicegui import ui

from src.signal_chain_lab.ui.blocks.block_backtest import render_block_backtest
from src.signal_chain_lab.ui.blocks.block_download import render_block_download
from src.signal_chain_lab.ui.blocks.block_parse import render_block_parse
from src.signal_chain_lab.ui.state import UiState

APP_STATE = UiState()


async def _run_streaming_command(command: list[str], log_panel) -> int:
    log_panel.push(f"$ {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
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
    ui.label("Workflow sequenziale: Download dati -> Parse dati -> Backtest").classes("text-body2 text-grey-7")

    # Holder condiviso: block_backtest vi inserisce il button handle;
    # block_parse lo legge al momento del click per abilitare il backtest.
    backtest_button_holder: list = []

    render_block_download(APP_STATE)
    render_block_parse(
        APP_STATE,
        backtest_button_holder=backtest_button_holder,
        run_streaming_command=_run_streaming_command,
    )
    render_block_backtest(
        APP_STATE,
        backtest_button_holder=backtest_button_holder,
        run_streaming_command=_run_streaming_command,
    )


def run() -> None:
    ui.run(title="Signal Chain Lab GUI", reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    run()
