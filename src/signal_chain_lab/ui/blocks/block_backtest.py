"""Blocco 3 — Backtest.

Lancia run_scenario.py sul DB parsato con la policy selezionata
e produce gli artifact di scenario. Disabilitato finché Blocco 2
non ha completato il parse con successo (checkpoint umano S9.8).
"""
from __future__ import annotations

import asyncio

from nicegui import ui

from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.state import UiState


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
    run_streaming_command,
) -> None:
    import sys

    state.policy_name = policy_name.strip() or "original_chain"
    state.market_data_dir = market_data_dir.strip()
    state.timeframe = timeframe.strip()
    state.timeout_seconds = int(timeout_seconds)
    log_panel.clear()

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
    ui.notify("Backtest completato", color="positive")


def render_block_backtest(
    state: UiState,
    *,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    """Renderizza il Blocco 3 — Backtest.

    Inserisce il button handle in ``backtest_button_holder[0]`` subito dopo
    la creazione, così il lambda di Blocco 2 può abilitarlo al parse completato.

    Args:
        state: stato condiviso dell'applicazione.
        backtest_button_holder: lista mutabile vuota in ingresso; viene riempita
            con il button handle prima che la funzione ritorni.
        run_streaming_command: callable async (command, log_panel) → int condiviso con app.py.
    """
    with ui.card().classes("w-full"):
        ui.label("Blocco 3 - Backtest").classes("text-h6")
        backtest_db = ui.input("DB parsato", value=state.effective_db_path())
        policy_name = ui.input("Policy", value=state.policy_name)
        market_data_dir = ui.input("Market data dir", value=state.market_data_dir)
        with ui.row():
            timeframe = ui.input("Timeframe", value=state.timeframe)
            timeout_seconds = ui.number("Timeout (s)", value=state.timeout_seconds, min=5, step=5)
        block3_log = LogPanel(title="Log Backtest")
        artifact_label = ui.link("Artifact: -", target="#")
        run_backtest_button = ui.button(
            "Esegui Backtest",
            on_click=lambda: _handle_backtest(
                state=state,
                db_path=backtest_db.value,
                policy_name=policy_name.value,
                market_data_dir=market_data_dir.value,
                timeframe=timeframe.value,
                timeout_seconds=int(timeout_seconds.value),
                log_panel=block3_log,
                artifact_label=artifact_label,
                run_streaming_command=run_streaming_command,
            ),
        )
        run_backtest_button.disable()

    # Espone il button handle al Blocco 2 tramite il holder condiviso
    backtest_button_holder.append(run_backtest_button)
