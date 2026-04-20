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
from src.signal_chain_lab.ui.blocks.shared_context import render_shared_context
from src.signal_chain_lab.ui.persistence import debounced_save, load_ui_state, save_ui_state
from src.signal_chain_lab.ui.state import UiState

APP_STATE = UiState()


def _apply_theme() -> None:
    ui.colors(
        primary="#58a6ff",
        secondary="#30363d",
        accent="#3fb950",
        positive="#3fb950",
        negative="#f85149",
        warning="#d29922",
        info="#58a6ff",
        dark="#161b22",
    )
    ui.add_head_html(
        r"""
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#0d1117; --surface:#161b22; --surface-2:#1c2128;
    --border:#30363d; --border-s:#21262d;
    --accent:#58a6ff; --accent-d:rgba(88,166,255,.12);
    --ok:#3fb950; --ok-d:rgba(63,185,80,.10);
    --wa:#d29922; --wa-d:rgba(210,153,34,.10);
    --er:#f85149; --er-d:rgba(248,81,73,.10);
    --muted:#8b949e; --text:#e6edf3; --text2:#c9d1d9;
    --log-bg:#010409; --log-g:#39d353;
    --mono:'IBM Plex Mono',monospace;
    --sans:'IBM Plex Sans',system-ui,sans-serif;
    --nav-h:42px; --panel-w:980px; --r:6px; --rs:4px;
  }
  body { font-family:var(--sans) !important; font-size:14px; background:var(--bg) !important; color:var(--text); }
  ::-webkit-scrollbar { width:5px; height:5px; }
  ::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
  *:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .inp-mono input { font-family:var(--mono) !important; font-size:12px !important; }
  .sec-lbl { display:flex; align-items:center; gap:8px; margin-bottom:8px; font-size:9px; font-weight:600; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); }
  .sec-lbl::after { content:''; flex:1; height:1px; background:var(--border-s); }
  .path-chip {
    font-family:var(--mono); font-size:11px;
    background:var(--surface-2); border:1px solid var(--border-s);
    border-radius:var(--rs); padding:4px 9px; color:var(--muted);
    display:inline-flex; align-items:center; gap:5px;
  }
  .app-shell { width:100%; min-height:100vh; }
  .app-topbar {
    position:sticky; top:0; z-index:100;
    background:rgba(22,27,34,.97);
    border-bottom:1px solid var(--border);
    backdrop-filter:blur(10px);
  }
  .app-topbar-inner {
    max-width:var(--panel-w); margin:0 auto; padding:0 20px;
    height:var(--nav-h); display:flex; align-items:flex-end; gap:2px;
  }
  .app-brand {
    font-family:var(--mono); font-size:11px; font-weight:600; color:var(--muted);
    padding:0 12px 10px 0; white-space:nowrap;
    border-right:1px solid var(--border-s); margin-right:8px;
  }
  .app-brand .dot { color:var(--accent); }
  .app-panels { max-width:var(--panel-w); margin:0 auto; padding:20px 20px 60px; }
  .main-tabs, .sub-nav { border-bottom:none; }
  .main-tabs .q-tabs__content, .sub-nav .q-tabs__content { align-items:flex-end; gap:2px; }
  .main-tabs .q-tab, .sub-nav .q-tab {
    font-family:var(--mono); font-size:11px; font-weight:500;
    color:var(--muted); min-height:42px; padding:8px 16px 10px;
    border-bottom:2px solid transparent; margin-bottom:-1px;
  }
  .main-tabs .q-tab:hover, .sub-nav .q-tab:hover { color:var(--text2); }
  .main-tabs .q-tab--active, .sub-nav .q-tab--active {
    color:var(--accent); border-bottom:2px solid var(--accent);
  }
  .sub-nav { border-bottom:1px solid var(--border-s); padding:0 2px; }
  .sub-nav .q-tab { min-height:36px; font-size:12px; padding:0 16px; }
  .block-card {
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:var(--r);
    padding:18px !important;
    box-shadow:none;
  }
  .block-shell { padding:16px 20px; gap:16px; }
  .section-head { display:flex; align-items:baseline; gap:8px; margin-bottom:10px; }
  .section-step { font-family:var(--mono); font-size:10px; color:var(--muted); }
  .section-title { font-family:var(--sans); font-size:12px; font-weight:600; color:var(--text); }
  .nicegui-expansion {
    border:1px solid var(--border-s) !important;
    border-radius:var(--rs) !important;
    overflow:hidden;
  }
  .nicegui-expansion .q-expansion-item__container { background:var(--surface-2); }
  .nicegui-expansion .q-item__label {
    font-family:var(--mono);
    font-size:11px;
    color:var(--muted);
  }
  .nicegui-expansion .q-expansion-item__content {
    background:var(--surface-2);
    border-top:1px solid var(--border-s);
  }
  .q-table, .res-tbl, .w-tbl { width:100%; border-collapse:collapse; }
  .res-tbl th, .w-tbl th {
    text-align:left;
    padding:5px 9px;
    font-size:9px;
    font-weight:600;
    text-transform:uppercase;
    letter-spacing:.08em;
    color:var(--muted);
    border-bottom:1px solid var(--border-s);
  }
  .res-tbl td, .w-tbl td {
    padding:5px 9px;
    border-bottom:1px solid var(--border-s);
    font-family:var(--mono);
    color:var(--text2);
    font-size:11px;
  }
  .res-tbl tr:last-child td, .w-tbl tr:last-child td { border-bottom:none; }
  .sum-grid {
    display:grid !important;
    grid-template-columns:repeat(auto-fit,minmax(130px,1fr)) !important;
    gap:8px !important;
    margin-top:8px !important;
  }
  .sum-card {
    background:var(--surface-2) !important;
    border:1px solid var(--border-s) !important;
    border-radius:var(--r) !important;
    padding:11px 12px !important;
  }
  .sum-card .sum-val {
    font-family:var(--mono);
    font-size:20px !important;
    font-weight:600;
    color:var(--text);
    line-height:1.15;
  }
  .sum-card .sum-lbl {
    font-size:9px !important;
    font-weight:600;
    text-transform:uppercase;
    letter-spacing:.08em;
    color:var(--muted);
    margin-top:5px;
  }
  .notice-info {
    background:var(--accent-d);
    border:1px solid rgba(88,166,255,.2);
    border-radius:var(--rs);
    padding:9px 11px;
    font-size:12px;
    color:var(--text2);
  }
  .ui-btn.q-btn {
    min-height:32px;
    border-radius:var(--rs);
    padding:0 13px;
    box-shadow:none;
    text-transform:none;
    font-size:12px;
    font-weight:500;
    letter-spacing:0;
  }
  .ui-btn .q-btn__content { gap:5px; }
  .q-field--filled .q-field__control,
  .q-field--outlined .q-field__control,
  .q-field__control {
    background:var(--surface-2);
    border:1px solid var(--border);
    color:var(--text2);
    border-radius:var(--rs);
    min-height:34px;
  }
  .q-field--focused .q-field__control,
  .q-field:hover .q-field__control { border-color:var(--accent); }
  .q-field__label, .q-toggle__label, .q-radio__label, .q-checkbox__label {
    color:var(--muted);
    font-size:10px;
    letter-spacing:.03em;
  }
  .q-field__native, .q-field__input, .q-field__marginal {
    color:var(--text2) !important;
    font-size:12px;
  }
  .q-btn.bg-primary {
    background:var(--accent) !important;
    border:1px solid var(--accent) !important;
    color:#0d1117 !important;
    box-shadow:none !important;
    text-transform:none;
    border-radius:var(--rs);
  }
  .q-btn.bg-primary:hover {
    background:#79c0ff !important;
    border-color:#79c0ff !important;
  }
  .q-btn.q-btn--outline {
    background:transparent !important;
    border:1px solid var(--border) !important;
    color:var(--text2) !important;
    box-shadow:none !important;
    text-transform:none;
    border-radius:var(--rs);
  }
  .q-btn.q-btn--outline:hover {
    border-color:var(--muted) !important;
    color:var(--text) !important;
  }
  .q-expansion-item, .q-expansion-item .q-item { background:transparent; color:var(--text2); }
  .q-expansion-item .q-item { min-height:38px; padding:7px 11px; }
  .q-menu, .q-dialog, .q-list { background:var(--surface-2); color:var(--text2); }
  .q-item { min-height:34px; }
  .q-toggle__inner, .q-radio__inner, .q-checkbox__inner { color:var(--accent); }
  .nicegui-tab-panel { padding:0; background:transparent; }
</style>
"""
    )


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
    _apply_theme()
    APP_STATE.apply_saved(load_ui_state())

    backtest_button_holder: list = []

    def _remember_active_tab(value: str | None) -> None:
        if value in {"download", "parse", "backtest"}:
            APP_STATE.active_tab = value
            debounced_save(APP_STATE.to_dict())

    with ui.column().classes("app-shell w-full").style("gap:0"):
        with ui.element("div").classes("app-topbar w-full"):
            with ui.element("div").classes("app-topbar-inner"):
                ui.html('<div class="app-brand">SCL <span class="dot">&middot;</span> Signal Chain Lab</div>')
                with ui.tabs(value=APP_STATE.active_tab).classes("main-tabs") as tabs:
                    ui.tab("download", label="01 Download")
                    ui.tab("parse", label="02 Parse")
                    ui.tab("backtest", label="03 Market Data & Backtest")
        tabs.on("update:model-value", lambda e: _remember_active_tab(e.args))

        with ui.element("div").classes("app-panels"):
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
                    render_shared_context(APP_STATE)
                    with ui.card().classes("w-full block-card").style("padding:0;margin-top:0"):
                        with ui.tabs(value="market").classes("sub-nav") as sub_tabs:
                            ui.tab("market", label="Market Data")
                            ui.tab("backtesting", label="Backtesting")
                        with ui.tab_panels(sub_tabs, value="market").classes("w-full"):
                            with ui.tab_panel("market"):
                                render_market_data_panel(
                                    APP_STATE,
                                    run_streaming_command=_run_streaming_command,
                                    backtest_button_holder=backtest_button_holder,
                                )
                            with ui.tab_panel("backtesting"):
                                render_block_backtest(
                                    APP_STATE,
                                    backtest_button_holder=backtest_button_holder,
                                    run_streaming_command=_run_streaming_command,
                                )
    panels.on("update:model-value", lambda e: _remember_active_tab(e.args))


def run() -> None:
    _patch_nicegui_process_pool_setup()
    from nicegui import app as _nicegui_app

    _nicegui_app.on_shutdown(lambda: save_ui_state(APP_STATE.to_dict()))
    ui.run(title="Signal Chain Lab GUI", reload=False, port=7777)


if __name__ in {"__main__", "__mp_main__"}:
    run()
