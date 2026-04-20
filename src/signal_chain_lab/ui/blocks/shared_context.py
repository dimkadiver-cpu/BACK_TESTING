"""Shared context panel for Tab 3: DB, filters, market data directory."""
from __future__ import annotations

from pathlib import Path

from nicegui import ui

from src.signal_chain_lab.ui.blocks.backtest_support import (
    discover_date_range_from_db,
    discover_traders_from_db,
)
from src.signal_chain_lab.ui.file_dialogs import ask_directory, ask_open_filename
from src.signal_chain_lab.ui.persistence import debounced_save
from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _detect_market_content(dir_path: str) -> str:
    path = Path(dir_path)
    if not path.exists():
        return "cartella non trovata"

    parquet_files = list(path.rglob("*.parquet"))
    if not parquet_files:
        sub_dirs = [child for child in path.iterdir() if child.is_dir()]
        if not sub_dirs:
            return "cartella vuota"
        return f"{len(sub_dirs)} sotto-cartelle rilevate"

    timeframes: set[str] = set()
    symbols: set[str] = set()
    for parquet_file in parquet_files:
        for part in parquet_file.parts:
            if part in {"1m", "5m", "15m", "1h", "4h", "1d", "3d", "1w"}:
                timeframes.add(part)
        if parquet_file.parent.name.endswith("USDT"):
            symbols.add(parquet_file.parent.name)

    tf_text = ", ".join(sorted(timeframes)) if timeframes else "-"
    symbols_text = f"{len(symbols)} simboli" if symbols else "simboli n/d"
    return f"{len(parquet_files)} file parquet | TF: {tf_text} | {symbols_text}"


def _build_summary(state: UiState) -> str:
    db_name = Path(state.parsed_db_path).name if state.parsed_db_path else "-"
    trader = state.backtest_trader_filter if state.backtest_trader_filter not in {"", "all"} else "Tutti"
    date_from = state.backtest_date_from or ""
    date_to = state.backtest_date_to or ""
    date_text = f"{date_from or '...'} -> {date_to or '...'}" if (date_from or date_to) else "Tutte le date"
    market_dir = Path(state.market.market_data_dir).name if state.market.market_data_dir else "-"
    return f"DB {db_name} &nbsp;|&nbsp; {trader} | {date_text} &nbsp;|&nbsp; MKT {market_dir}"


def render_shared_context(state: UiState) -> None:
    """Render the collapsible shared context panel for Tab 3."""

    expanded_state = {"open": True}
    initial_db_path = state.parsed_db_path or state.downloaded_db_path
    initial_traders = discover_traders_from_db(initial_db_path)
    trader_options = {"all": "Tutti i trader"}
    trader_options.update({trader: trader for trader in initial_traders})
    initial_trader_value = state.backtest_trader_filter or "all"
    if initial_trader_value not in trader_options:
        initial_trader_value = "all"

    def _persist() -> None:
        debounced_save(state.to_dict())

    def _invalidate_market_context_if_needed() -> None:
        if state.market.market_ready or state.market.market_validation_status != "needs_check":
            state.market.mark_needs_check()

    with ui.card().style(
        "background:var(--surface);border:1px solid var(--border);"
        "border-radius:var(--r);padding:0;margin-bottom:12px"
    ).classes("w-full"):
        summary_html = ui.html("").style(
            "font-family:var(--mono);font-size:11px;color:var(--muted);margin-left:8px"
        )

        def _refresh_summary() -> None:
            summary_html.set_content(_build_summary(state))

        _refresh_summary()

        body_ref: list = []

        def _toggle_body() -> None:
            expanded_state["open"] = not expanded_state["open"]
            is_open = expanded_state["open"]
            chevron.set_text("v" if is_open else ">")
            if body_ref:
                body_ref[0].set_visibility(is_open)
            summary_html.set_visibility(not is_open)

        with ui.row().style(
            "align-items:center;gap:8px;padding:10px 16px;"
            "border-bottom:1px solid var(--border-s);cursor:pointer"
        ).on("click", _toggle_body):
            chevron = ui.label("v").style(
                "font-family:var(--mono);font-size:11px;color:var(--muted);user-select:none"
            )
            ui.label("Contesto condiviso").style(
                "font-family:var(--sans);font-size:13px;font-weight:600;color:var(--text)"
            )
            ui.label("DB | filtri | cartella Market Data").style(
                "font-size:11px;color:var(--muted)"
            )
            summary_html

        with ui.column().style("padding:16px 20px;gap:12px").classes("w-full") as body:
            body_ref.append(body)

            ui.html('<div class="sec-lbl">Database segnali</div>')
            with ui.row().classes("w-full items-end gap-2"):
                db_input = ui.input(
                    "Path DB SQLite",
                    value=state.parsed_db_path or state.downloaded_db_path,
                ).classes("flex-1 inp-mono")
                db_hint = ui.label("").style("font-size:11px;color:var(--er)")

                async def _browse_db() -> None:
                    selected = ask_open_filename(
                        initialdir=_PROJECT_ROOT,
                        title="Seleziona DB segnali",
                        filetypes=[("SQLite DB", "*.sqlite3 *.db"), ("All files", "*.*")],
                    )
                    if not selected:
                        return
                    db_input.value = selected
                    db_input.update()
                    _on_db_change_value(selected)

                ui.button("Sfoglia", on_click=_browse_db, icon="folder_open")

            with ui.row().classes("w-full gap-3"):
                trader_select = ui.select(
                    options=trader_options,
                    value=initial_trader_value,
                    label="Trader filter",
                ).classes("flex-1")
                trader_hint = ui.label("").style("font-size:11px;color:var(--muted);padding-top:8px")
                ui.element("div").classes("flex-1")
                ui.element("div").classes("flex-1")

            with ui.row().classes("w-full gap-3"):
                date_from_input = ui.input("Dal", value=state.backtest_date_from).props("type=date").classes("flex-1")
                date_to_input = ui.input("Al", value=state.backtest_date_to).props("type=date").classes("flex-1")
                max_trades_input = ui.number(
                    "Max trades",
                    value=state.backtest_max_trades,
                    min=0,
                    step=1,
                ).classes("w-28")

            ui.html('<div class="sec-lbl">Cartella Market Data</div>')
            with ui.row().classes("w-full items-end gap-2"):
                market_input = ui.input(
                    "Cartella Market Data",
                    value=state.market.market_data_dir,
                ).classes("flex-1 inp-mono")
                market_hint = ui.label("").style("font-size:11px;color:var(--er)")

                async def _browse_market_dir() -> None:
                    selected = ask_directory(
                        initialdir=_PROJECT_ROOT,
                        title="Seleziona cartella Market Data",
                        mustexist=True,
                    )
                    if not selected:
                        return
                    market_input.value = selected
                    market_input.update()
                    _on_market_change_value(selected)

                ui.button("Sfoglia", on_click=_browse_market_dir, icon="folder_open")

            market_chip = ui.html("").style("margin-top:4px")

            def _refresh_db_validity() -> None:
                invalid = bool(db_input.value.strip()) and not Path(db_input.value.strip()).exists()
                db_input.style(f"border-color:{'var(--er)' if invalid else 'var(--border)'}")
                db_hint.set_text("percorso non trovato" if invalid else "")

            def _refresh_market_chip() -> None:
                path = market_input.value.strip()
                content = _detect_market_content(path) if path else "-"
                invalid = bool(path) and not Path(path).exists()
                border_color = "var(--er)" if invalid else "var(--border-s)"
                market_input.style(f"border-color:{'var(--er)' if invalid else 'var(--border)'}")
                market_hint.set_text("percorso non trovato" if invalid else "")
                market_chip.set_content(
                    f'<span class="path-chip" style="border-color:{border_color}">MKT rilevato: {content}</span>'
                )

            def _refresh_trader_select(db_path: str, *, notify_reset: bool = False) -> None:
                traders = discover_traders_from_db(db_path.strip())
                options = {"all": "Tutti i trader"}
                options.update({trader: trader for trader in traders})
                trader_select.options = options
                reset_to_all = False
                if trader_select.value not in options:
                    trader_select.value = "all"
                    state.backtest_trader_filter = "all"
                    reset_to_all = True
                trader_select.update()
                trader_hint.set_text(f"{len(traders)} trader rilevati" if traders else "nessun trader rilevato")

                min_date, max_date = discover_date_range_from_db(db_path.strip())
                if min_date and not date_from_input.value:
                    date_from_input.value = min_date
                    date_from_input.update()
                if max_date and not date_to_input.value:
                    date_to_input.value = max_date
                    date_to_input.update()

                if notify_reset and reset_to_all:
                    ui.notify("Trader filter non valido per il nuovo DB: impostato su Tutti i trader", color="warning")

            def _sync_filters_to_state() -> None:
                changed = (
                    state.backtest_trader_filter != (trader_select.value or "all")
                    or state.backtest_date_from != (date_from_input.value or "")
                    or state.backtest_date_to != (date_to_input.value or "")
                    or state.backtest_max_trades != int(max_trades_input.value or 0)
                )
                state.backtest_trader_filter = trader_select.value or "all"
                state.backtest_date_from = date_from_input.value or ""
                state.backtest_date_to = date_to_input.value or ""
                state.backtest_max_trades = int(max_trades_input.value or 0)
                if changed:
                    _invalidate_market_context_if_needed()
                _refresh_summary()
                _persist()

            def _on_db_change_value(value: str) -> None:
                clean = value.strip()
                if state.parsed_db_path != clean:
                    state.parsed_db_path = clean
                    _invalidate_market_context_if_needed()
                else:
                    state.parsed_db_path = clean
                _refresh_db_validity()
                _refresh_trader_select(state.parsed_db_path, notify_reset=True)
                _sync_filters_to_state()

            def _on_market_change_value(value: str) -> None:
                clean = value.strip()
                if state.market.market_data_dir != clean:
                    state.market.market_data_dir = clean
                    _invalidate_market_context_if_needed()
                else:
                    state.market.market_data_dir = clean
                _refresh_market_chip()
                _refresh_summary()
                _persist()

            db_input.on("update:model-value", lambda e: _on_db_change_value(e.value))
            trader_select.on("update:model-value", lambda *_: _sync_filters_to_state())
            date_from_input.on("update:model-value", lambda *_: _sync_filters_to_state())
            date_to_input.on("update:model-value", lambda *_: _sync_filters_to_state())
            max_trades_input.on("update:model-value", lambda *_: _sync_filters_to_state())
            market_input.on("update:model-value", lambda e: _on_market_change_value(e.value))

            _refresh_db_validity()
            _refresh_market_chip()
            _refresh_trader_select(state.parsed_db_path or state.downloaded_db_path)

        summary_html.set_visibility(False)
