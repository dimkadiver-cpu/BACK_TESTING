"""Blocco 2 — Parse dati.

Lancia replay_parser.py sul DB selezionato, costruisce le chain
canoniche, e produce il quality report sintetico. Sblocca Blocco 3
solo dopo parse completato con successo (checkpoint umano).
"""
from __future__ import annotations

import sys
from collections import Counter

from nicegui import ui

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.chain_builder import SignalChainBuilder
from src.signal_chain_lab.adapters.validators import validate_chain_for_simulation
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.components.quality_report import render_quality_report
from src.signal_chain_lab.ui.state import QualityReport, UiState


def _build_quality_report(db_path: str) -> QualityReport:
    chains = SignalChainBuilder.build_all(db_path=db_path)
    canonical = [adapt_signal_chain(chain) for chain in chains]

    warning_counter: Counter[str] = Counter()
    simulable = 0
    for chain in canonical:
        validation = validate_chain_for_simulation(chain)
        if validation.is_simulable:
            simulable += 1
        for gap in validation.warning_gaps + validation.fatal_gaps:
            warning_counter.update([gap.message])

    return QualityReport(
        total_signals=len(canonical),
        simulable_signals=simulable,
        top_warnings=warning_counter.most_common(5),
    )


async def _handle_parse(
    *,
    state: UiState,
    db_path: str,
    parser_profile: str,
    trader_mapping_path: str,
    log_panel: LogPanel,
    report_container,
    unlock_button,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    state.parser_profile = parser_profile.strip() or "trader_a"
    state.trader_mapping_path = trader_mapping_path.strip()
    state.parsed_db_path = db_path.strip()
    state.proceed_to_backtest = False
    log_panel.clear()

    if not state.parsed_db_path:
        ui.notify("Seleziona un DB prima del parse", color="negative")
        return

    command = [
        sys.executable,
        "parser_test/scripts/replay_parser.py",
        "--db-path",
        state.parsed_db_path,
        "--trader",
        state.parser_profile,
    ]
    rc = await run_streaming_command(command, log_panel)
    if rc != 0:
        ui.notify("Replay parser fallito: controlla log", color="negative")
        return

    report = _build_quality_report(state.parsed_db_path)
    with report_container:
        report_container.clear()
        render_quality_report(report)

    state.proceed_to_backtest = True
    unlock_button.enable()
    if backtest_button_holder:
        backtest_button_holder[0].enable()
    ui.notify("Parse completato. Ora puoi procedere al backtest.", color="positive")


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
        parse_db = ui.input("DB da parsare", value=state.effective_db_path())
        parser_profile = ui.input("Parser/Profile", value=state.parser_profile)
        trader_mapping = ui.input("Trader mapping", value=state.trader_mapping_path)
        block2_log = LogPanel(title="Log Parse")
        report_container = ui.column().classes("w-full")
        proceed_button = ui.button("Procedi al Backtest", on_click=lambda: ui.notify("Blocco 3 sbloccato"))
        proceed_button.disable()

        ui.button(
            "Esegui Parse + Chain Builder",
            on_click=lambda: _handle_parse(
                state=state,
                db_path=parse_db.value,
                parser_profile=parser_profile.value,
                trader_mapping_path=trader_mapping.value,
                log_panel=block2_log,
                report_container=report_container,
                unlock_button=proceed_button,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=run_streaming_command,
            ),
        )
