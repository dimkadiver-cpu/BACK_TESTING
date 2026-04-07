"""Blocco 1 — Download dati.

Gestisce la selezione della sorgente (DB esistente o Telegram)
e predispone il path del DB per i blocchi successivi.
"""
from __future__ import annotations

from pathlib import Path

from nicegui import ui

from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.state import UiState


async def _handle_download(
    *,
    state: UiState,
    source_kind: str,
    db_path_input: str,
    chat_id: str,
    date_from: str,
    date_to: str,
    log_panel: LogPanel,
    db_output_label,
) -> None:
    state.source_kind = source_kind
    state.chat_id = chat_id.strip()
    state.date_from = date_from.strip()
    state.date_to = date_to.strip()
    log_panel.clear()

    if source_kind == "existing_db":
        state.downloaded_db_path = db_path_input.strip()
        db_output_label.set_text(f"DB output: {state.downloaded_db_path or '(vuoto)'}")
        log_panel.push("Sorgente DB esistente selezionata: nessun download necessario.")
        return

    output_db = Path("parser_test/db") / f"parser_test__chat_{state.chat_id or 'unknown'}.sqlite3"
    output_db.parent.mkdir(parents=True, exist_ok=True)
    state.downloaded_db_path = str(output_db)

    log_panel.push("Modalita Telegram: placeholder operativo per integrazione ingestione live.")
    log_panel.push(f"chat_id={state.chat_id}, range={state.date_from} -> {state.date_to}")
    log_panel.push(f"DB target predisposto: {state.downloaded_db_path}")
    db_output_label.set_text(f"DB output: {state.downloaded_db_path}")


def render_block_download(state: UiState) -> None:
    """Renderizza il Blocco 1 — Download dati."""
    with ui.card().classes("w-full"):
        ui.label("Blocco 1 - Download dati").classes("text-h6")
        source_kind = ui.select(
            options={"telegram": "Telegram", "existing_db": "DB esistente"},
            value=state.source_kind,
            label="Sorgente",
        )
        chat_id = ui.input("chat_id", value=state.chat_id)
        with ui.row().classes("w-full"):
            date_from = ui.input("date_from (YYYY-MM-DD)", value=state.date_from)
            date_to = ui.input("date_to (YYYY-MM-DD)", value=state.date_to)
        db_path_input = ui.input("Path DB (se sorgente = DB esistente)", value=state.downloaded_db_path)
        db_output_label = ui.label("DB output: -")
        block1_log = LogPanel(title="Log Download")
        ui.button(
            "Esegui Download",
            on_click=lambda: _handle_download(
                state=state,
                source_kind=source_kind.value,
                db_path_input=db_path_input.value,
                chat_id=chat_id.value,
                date_from=date_from.value,
                date_to=date_to.value,
                log_panel=block1_log,
                db_output_label=db_output_label,
            ),
        )
