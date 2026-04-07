"""NiceGUI entry point for Sprint 9: download -> parse -> backtest."""
from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
import sys

from nicegui import ui

from src.signal_chain_lab.adapters.chain_adapter import adapt_signal_chain
from src.signal_chain_lab.adapters.chain_builder import SignalChainBuilder
from src.signal_chain_lab.adapters.validators import validate_chain_for_simulation
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.components.quality_report import render_quality_report
from src.signal_chain_lab.ui.state import QualityReport, UiState

APP_STATE = UiState()


async def _run_streaming_command(command: list[str], log_panel: LogPanel) -> int:
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


async def _handle_download(
    *,
    source_kind: str,
    db_path_input: str,
    chat_id: str,
    date_from: str,
    date_to: str,
    log_panel: LogPanel,
    db_output_label,
) -> None:
    APP_STATE.source_kind = source_kind
    APP_STATE.chat_id = chat_id.strip()
    APP_STATE.date_from = date_from.strip()
    APP_STATE.date_to = date_to.strip()
    log_panel.clear()

    if source_kind == "existing_db":
        APP_STATE.downloaded_db_path = db_path_input.strip()
        db_output_label.set_text(f"DB output: {APP_STATE.downloaded_db_path or '(vuoto)'}")
        log_panel.push("Sorgente DB esistente selezionata: nessun download necessario.")
        return

    output_db = Path("parser_test/db") / f"parser_test__chat_{APP_STATE.chat_id or 'unknown'}.sqlite3"
    output_db.parent.mkdir(parents=True, exist_ok=True)
    APP_STATE.downloaded_db_path = str(output_db)

    log_panel.push("Modalita Telegram: placeholder operativo per integrazione ingestione live.")
    log_panel.push(f"chat_id={APP_STATE.chat_id}, range={APP_STATE.date_from} -> {APP_STATE.date_to}")
    log_panel.push(f"DB target predisposto: {APP_STATE.downloaded_db_path}")
    db_output_label.set_text(f"DB output: {APP_STATE.downloaded_db_path}")


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
    db_path: str,
    parser_profile: str,
    trader_mapping_path: str,
    log_panel: LogPanel,
    report_container,
    unlock_button,
    backtest_button,
) -> None:
    APP_STATE.parser_profile = parser_profile.strip() or "trader_a"
    APP_STATE.trader_mapping_path = trader_mapping_path.strip()
    APP_STATE.parsed_db_path = db_path.strip()
    APP_STATE.proceed_to_backtest = False
    log_panel.clear()

    if not APP_STATE.parsed_db_path:
        ui.notify("Seleziona un DB prima del parse", color="negative")
        return

    command = [
        sys.executable,
        "parser_test/scripts/replay_parser.py",
        "--db-path",
        APP_STATE.parsed_db_path,
        "--trader",
        APP_STATE.parser_profile,
    ]
    rc = await _run_streaming_command(command, log_panel)
    if rc != 0:
        ui.notify("Replay parser fallito: controlla log", color="negative")
        return

    report = _build_quality_report(APP_STATE.parsed_db_path)
    with report_container:
        report_container.clear()
        render_quality_report(report)

    APP_STATE.proceed_to_backtest = True
    unlock_button.enable()
    backtest_button.enable()
    ui.notify("Parse completato. Ora puoi procedere al backtest.", color="positive")


async def _handle_backtest(
    *,
    db_path: str,
    policy_name: str,
    market_data_dir: str,
    timeframe: str,
    timeout_seconds: int,
    log_panel: LogPanel,
    artifact_label,
) -> None:
    APP_STATE.policy_name = policy_name.strip() or "original_chain"
    APP_STATE.market_data_dir = market_data_dir.strip()
    APP_STATE.timeframe = timeframe.strip()
    APP_STATE.timeout_seconds = int(timeout_seconds)
    log_panel.clear()

    command = [
        sys.executable,
        "scripts/run_scenario.py",
        "--policy",
        f"{APP_STATE.policy_name},signal_only",
        "--db-path",
        db_path,
        "--market-dir",
        APP_STATE.market_data_dir,
    ]

    try:
        rc = await asyncio.wait_for(_run_streaming_command(command, log_panel), timeout=APP_STATE.timeout_seconds)
    except TimeoutError:
        ui.notify("Timeout backtest raggiunto", color="negative")
        return

    if rc != 0:
        ui.notify("Backtest fallito: controlla log", color="negative")
        return

    APP_STATE.latest_artifact_path = "artifacts/scenarios"
    artifact_label.set_text(f"Artifact: {APP_STATE.latest_artifact_path}")
    ui.notify("Backtest completato", color="positive")


@ui.page("/")
def main_page() -> None:
    ui.label("Signal Chain Lab - Sprint 9 GUI").classes("text-h5")
    ui.label("Workflow sequenziale: Download dati -> Parse dati -> Backtest").classes("text-body2 text-grey-7")

    with ui.card().classes("w-full"):
        ui.label("Blocco 1 - Download dati").classes("text-h6")
        source_kind = ui.select(
            options={"telegram": "Telegram", "existing_db": "DB esistente"},
            value=APP_STATE.source_kind,
            label="Sorgente",
        )
        chat_id = ui.input("chat_id", value=APP_STATE.chat_id)
        with ui.row().classes("w-full"):
            date_from = ui.input("date_from (YYYY-MM-DD)", value=APP_STATE.date_from)
            date_to = ui.input("date_to (YYYY-MM-DD)", value=APP_STATE.date_to)
        db_path_input = ui.input("Path DB (se sorgente = DB esistente)", value=APP_STATE.downloaded_db_path)
        db_output_label = ui.label("DB output: -")
        block1_log = LogPanel(title="Log Download")
        ui.button(
            "Esegui Download",
            on_click=lambda: _handle_download(
                source_kind=source_kind.value,
                db_path_input=db_path_input.value,
                chat_id=chat_id.value,
                date_from=date_from.value,
                date_to=date_to.value,
                log_panel=block1_log,
                db_output_label=db_output_label,
            ),
        )

    with ui.card().classes("w-full"):
        ui.label("Blocco 2 - Parse dati").classes("text-h6")
        parse_db = ui.input("DB da parsare", value=APP_STATE.effective_db_path())
        parser_profile = ui.input("Parser/Profile", value=APP_STATE.parser_profile)
        trader_mapping = ui.input("Trader mapping", value=APP_STATE.trader_mapping_path)
        block2_log = LogPanel(title="Log Parse")
        report_container = ui.column().classes("w-full")
        proceed_button = ui.button("Procedi al Backtest", on_click=lambda: ui.notify("Blocco 3 sbloccato"))
        proceed_button.disable()

        ui.button(
            "Esegui Parse + Chain Builder",
            on_click=lambda: _handle_parse(
                db_path=parse_db.value,
                parser_profile=parser_profile.value,
                trader_mapping_path=trader_mapping.value,
                log_panel=block2_log,
                report_container=report_container,
                unlock_button=proceed_button,
                backtest_button=run_backtest_button,
            ),
        )

    with ui.card().classes("w-full"):
        ui.label("Blocco 3 - Backtest").classes("text-h6")
        backtest_db = ui.input("DB parsato", value=APP_STATE.effective_db_path())
        policy_name = ui.input("Policy", value=APP_STATE.policy_name)
        market_data_dir = ui.input("Market data dir", value=APP_STATE.market_data_dir)
        with ui.row():
            timeframe = ui.input("Timeframe", value=APP_STATE.timeframe)
            timeout_seconds = ui.number("Timeout (s)", value=APP_STATE.timeout_seconds, min=5, step=5)
        block3_log = LogPanel(title="Log Backtest")
        artifact_label = ui.link("Artifact: -", target="#")
        run_backtest_button = ui.button(
            "Esegui Backtest",
            on_click=lambda: _handle_backtest(
                db_path=backtest_db.value,
                policy_name=policy_name.value,
                market_data_dir=market_data_dir.value,
                timeframe=timeframe.value,
                timeout_seconds=int(timeout_seconds.value),
                log_panel=block3_log,
                artifact_label=artifact_label,
            ),
        )
        run_backtest_button.disable()


def run() -> None:
    ui.run(title="Signal Chain Lab GUI", reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    run()
