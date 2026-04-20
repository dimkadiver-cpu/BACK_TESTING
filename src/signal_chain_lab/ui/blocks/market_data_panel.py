"""Market DATA panel — collapsible autonomous panel for Blocco 3."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from nicegui import ui

from src.signal_chain_lab.market.preparation_cache import (
    build_market_request,
    find_pass_validation_record,
    load_validation_index,
    market_request_fingerprint,
    save_validation_index,
    upsert_validation_record,
    validation_index_path,
)
from src.signal_chain_lab.ui.blocks.market_data_support import (
    format_analyze_summary,
    format_data_types_summary,
    format_window_preview,
    roadmap_data_type_labels,
    supported_data_type_labels,
)
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.file_dialogs import ask_directory
from src.signal_chain_lab.ui.persistence import debounced_save
from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_TF_OPTIONS: tuple[tuple[str, str], ...] = (
    ("1m", "1m"),
    ("15m", "15"),
    ("1h", "1h"),
    ("4h", "4h"),
    ("1d", "1D"),
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_status(label, *, text: str, positive: bool | None = None) -> None:
    label.set_text(text)
    label.classes(remove="text-positive text-negative text-grey-6")
    if positive is True:
        label.classes(add="text-positive")
    elif positive is False:
        label.classes(add="text-negative")
    else:
        label.classes(add="text-grey-6")


def _update_badge(badge_label, *, status: str) -> None:
    badge_label.set_text(status)
    badge_label.classes(remove="text-positive text-negative text-grey-6")
    if status == "READY":
        badge_label.classes(add="text-positive")
    elif "gap validated" in status or "unvalidated" in status or status == "ANALYZED":
        badge_label.classes(add="text-grey-6")
    else:
        badge_label.classes(add="text-negative")


def _apply_validation_status(*, state: UiState, status_label, badge_label, status_key: str) -> None:
    state.market.market_validation_status = status_key
    if status_key == "validated":
        _set_status(status_label, text="Market data validati", positive=True)
        _update_badge(badge_label, status="READY")
    elif status_key in ("gap_validated", "gap_validated_partial"):
        _set_status(status_label, text="Market data pronti, gap validati parzialmente", positive=True)
        _update_badge(badge_label, status="READY (gap validated)")
    elif status_key == "ready_unvalidated":
        _set_status(status_label, text="Market data pronti ma non validati", positive=None)
        _update_badge(badge_label, status="READY (unvalidated)")
    elif status_key == "prepared_with_unsupported_symbols":
        _set_status(status_label, text="Market data pronti — simboli non supportati presenti", positive=None)
        _update_badge(badge_label, status="READY (unsupported symbols)")
    elif status_key == "analyzed":
        _set_status(status_label, text="Analisi completata — nessun download eseguito", positive=None)
        _update_badge(badge_label, status="ANALYZED")
    else:
        _set_status(status_label, text="Market data da verificare", positive=None)
        _update_badge(badge_label, status="NOT READY")


def _extract_unsupported_symbols(sync_path: Path) -> list[str]:
    if not sync_path.exists():
        return []
    try:
        report = json.loads(sync_path.read_text(encoding="utf-8"))
        from_top: list[str] = list(report.get("unsupported_symbols") or [])
        if from_top:
            return from_top
        return sorted({
            r["symbol"]
            for r in report.get("results", [])
            if r.get("reason_code") == "unsupported_symbol"
        })
    except Exception:
        return []


def _set_funding_status(*, state: UiState, funding_status_label, status_key: str) -> None:
    state.market.funding_status = status_key
    if status_key == "validated":
        _set_status(funding_status_label, text="Funding: validato", positive=True)
    elif status_key == "synced":
        _set_status(funding_status_label, text="Funding: sincronizzato", positive=True)
    elif status_key == "needs_sync":
        _set_status(funding_status_label, text="Funding: da sincronizzare", positive=None)
    elif status_key == "failed":
        _set_status(funding_status_label, text="Funding: errore", positive=False)
    else:
        _set_status(funding_status_label, text="Funding: non richiesto", positive=None)


def _refresh_backtest_button(backtest_button_holder: list, state: UiState) -> None:
    if not backtest_button_holder:
        return
    try:
        from src.signal_chain_lab.ui.blocks.backtest_support import market_backtest_gate

        allowed, _, _ = market_backtest_gate(state)
    except Exception:
        allowed = False
    button = backtest_button_holder[0]
    if allowed:
        button.enable()
    else:
        button.disable()


def _reset_market_state(
    *,
    state: UiState,
    status_label,
    badge_label,
    summary_label,
    window_summary_label,
    funding_status_label,
) -> None:
    state.market.mark_needs_check(clear_artifacts=True)
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="needs_check")
    _set_funding_status(
        state=state,
        funding_status_label=funding_status_label,
        status_key="needs_sync" if state.market.data_types.funding_rate else "not_requested",
    )
    summary_label.set_text("La cartella verrà analizzata prima del backtest.")
    window_summary_label.set_text("Finestre: in attesa di analisi.")


def _market_plan_summary(plan_path: Path) -> dict[str, object]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    s = payload.get("summary", {})
    total = int(s.get("symbols", 0))
    symbols_with_gaps = int(s.get("symbols_with_gaps", 0))
    return {
        "symbols": total,
        "symbols_with_gaps": symbols_with_gaps,
        "symbols_complete": int(s.get("symbols_complete", total - symbols_with_gaps)),
        "required_intervals": int(s.get("required_intervals", 0)),
        "gaps": int(s.get("gaps", 0)),
        "gaps_by_timeframe": dict(s.get("gaps_by_timeframe", {})),
        "download_tfs": list(payload.get("download_tfs", [])),
        "simulation_tf": str(payload.get("simulation_tf", "")),
        "detail_tf": str(payload.get("detail_tf", "")),
        "requested_data_types": dict(payload.get("requested_data_types", {})),
        "potentially_unsupported_symbols": list(payload.get("potentially_unsupported_symbols", [])),
        "window_preview": format_window_preview(payload),
    }


def _selected_data_types_text(state: UiState) -> str:
    return format_data_types_summary(state.market.data_types)


def _operation_context_text(state: UiState) -> str:
    download_tfs = [tf.strip() for tf in state.market.download_tfs if tf.strip()]
    if not download_tfs:
        download_tfs = [state.market.download_tf or "1m"]
    simulation_tf = state.market.simulation_tf or state.market.download_tf or "1m"
    detail_tf = state.market.detail_tf or state.market.download_tf or "1m"
    return (
        f"TF attivi: download={','.join(download_tfs)} | "
        f"sim={simulation_tf} | detail={detail_tf} | "
        f"{format_data_types_summary(state.market.data_types)}"
    )


def _log_operation_banner(log_panel: LogPanel, *, title: str, state: UiState) -> None:
    log_panel.push(f"=== {title} ===")
    log_panel.push(_operation_context_text(state))


def _mark_prepare_failed(*, state: UiState, status_label, badge_label) -> None:
    state.market.market_ready = False
    state.market.analysis_ready = False
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="prepare_failed")


def _mark_validation_failed(*, state: UiState, status_label, badge_label) -> None:
    state.market.market_ready = False
    state.market.analysis_ready = False
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="validation_failed")


def _validate_inputs(state: UiState, db_path: str) -> bool:
    if not db_path or not Path(db_path).exists():
        ui.notify("Seleziona un DB parsato valido", color="negative")
        return False
    if not state.market.market_data_dir.strip():
        ui.notify("Seleziona la cartella market data", color="negative")
        return False
    return True


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------

def _build_plan_command(*, state: UiState, db_path: str, plan_path: Path) -> list[str]:
    download_tfs = [tf.strip() for tf in state.market.download_tfs if tf.strip()]
    if not download_tfs:
        download_tfs = [state.market.download_tf or "1m"]
    cmd = [
        sys.executable,
        "scripts/plan_market_data.py",
        "--db-path", db_path,
        "--market-dir", state.market.market_data_dir,
        "--timeframe", state.market.download_tf,
        "--download-tfs", ",".join(download_tfs),
        "--simulation-tf", state.market.simulation_tf or state.market.download_tf,
        "--detail-tf", state.market.detail_tf or state.market.download_tf,
        "--bases", "last,mark",
        "--source", state.market.market_data_source,
        "--output", str(plan_path),
        "--buffer-mode", state.market.buffer_mode,
        "--validate-mode", state.market.validate_mode,
    ]
    if state.market.buffer_mode == "manual":
        cmd += ["--pre-buffer-days", str(state.market.pre_buffer_days)]
        cmd += ["--post-buffer-days", str(state.market.post_buffer_days)]
        if state.market.buffer_preset:
            cmd += ["--buffer-preset", state.market.buffer_preset]
    if state.market.data_types.ohlcv_last:
        cmd.append("--ohlcv-last")
    if state.market.data_types.ohlcv_mark:
        cmd.append("--ohlcv-mark")
    if state.market.data_types.funding_rate:
        cmd.append("--funding-rate")
    if state.backtest_trader_filter and state.backtest_trader_filter != "all":
        cmd += ["--trader-id", state.backtest_trader_filter]
    if state.backtest_date_from:
        cmd += ["--date-from", state.backtest_date_from]
    if state.backtest_date_to:
        cmd += ["--date-to", state.backtest_date_to]
    if state.backtest_max_trades > 0:
        cmd += ["--max-trades", str(state.backtest_max_trades)]
    return cmd


def _build_sync_command(*, state: UiState, db_path: str, plan_path: Path, sync_path: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/sync_market_data.py",
        "--plan-file", str(plan_path),
        "--db-path", db_path,
        "--market-dir", state.market.market_data_dir,
        "--output", str(sync_path),
        "--source", state.market.market_data_source,
    ]


def _build_gap_validate_command(
    *, plan_path: Path, sync_path: Path, market_root: Path, out_path: Path
) -> list[str]:
    return [
        sys.executable,
        "scripts/gap_validate_market_data.py",
        "--plan-file", str(plan_path),
        "--sync-file", str(sync_path),
        "--market-dir", str(market_root),
        "--output", str(out_path),
    ]


def _build_funding_sync_command(*, market_root: Path, plan_path: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/sync_funding_rates.py",
        "--market-dir", str(market_root),
        "--plan-file", str(plan_path),
    ]


def _build_funding_validate_command(*, market_root: Path, plan_path: Path, out_path: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/validate_funding_rates.py",
        "--market-dir", str(market_root),
        "--plan-file", str(plan_path),
        "--output", str(out_path),
    ]


# ---------------------------------------------------------------------------
# Orchestration functions
# ---------------------------------------------------------------------------

async def _run_analyze(
    *,
    state: UiState,
    db_path: str,
    log_panel: LogPanel,
    status_label,
    badge_label,
    summary_label,
    window_summary_label,
    backtest_button_holder,
    run_streaming_command,
) -> None:
    """Planner only — discovery, no download."""
    db_path = db_path.strip()
    if not _validate_inputs(state, db_path):
        return

    log_panel.clear()
    _log_operation_banner(log_panel, title="Analizza", state=state)
    log_panel.push("Analisi copertura richiesta dal DB...")
    _set_status(status_label, text="Analisi in corso...", positive=None)

    plan_path = Path("artifacts/market_data/plan_market_data.json")
    rc = await run_streaming_command(_build_plan_command(state=state, db_path=db_path, plan_path=plan_path), log_panel)
    if rc != 0 or not plan_path.exists():
        ui.notify("Analisi fallita: controlla log", color="negative")
        _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
        _set_status(status_label, text="Analisi fallita", positive=False)
        return

    ps = _market_plan_summary(plan_path)
    state.market.latest_market_plan_path = str(plan_path)
    state.market.market_data_gap_count = ps["gaps"]
    state.market.analysis_ready = True
    summary_label.set_text(format_analyze_summary(ps))
    window_summary_label.set_text(str(ps["window_preview"]))
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="analyzed")
    _refresh_backtest_button(backtest_button_holder, state)
    log_panel.push(
        f"Analisi completata: simboli={ps['symbols']} "
        f"({ps.get('symbols_complete', '?')} completi, {ps.get('symbols_with_gaps', '?')} con gap), "
        f"gap totali={ps['gaps']}."
    )
    gaps_by_tf = ps.get("gaps_by_timeframe", {})
    if gaps_by_tf and len(gaps_by_tf) > 1:
        log_panel.push("Gap per TF: " + " | ".join(f"{tf}={cnt}" for tf, cnt in gaps_by_tf.items()))
    unsupported = ps.get("potentially_unsupported_symbols", [])
    if unsupported:
        log_panel.push(
            f"Simboli potenzialmente non supportati ({len(unsupported)}): {', '.join(unsupported)}"
        )
    ui.notify("Analisi completata", color="positive")


async def _run_prepare(
    *,
    state: UiState,
    db_path: str,
    log_panel: LogPanel,
    status_label,
    badge_label,
    funding_status_label,
    summary_label,
    window_summary_label,
    backtest_button_holder,
    run_streaming_command,
) -> bool:
    """Planner + sync + gap_validate (no validate_full)."""
    db_path = db_path.strip()
    if not _validate_inputs(state, db_path):
        return False

    log_panel.clear()
    _log_operation_banner(log_panel, title="Prepara", state=state)
    t_total = time.perf_counter()
    market_root = Path(state.market.market_data_dir)

    if state.market.market_data_mode == "existing_dir" and not market_root.exists():
        ui.notify("Cartella market data non esiste", color="negative")
        _set_status(status_label, text="Cartella non trovata", positive=False)
        return False
    market_root.mkdir(parents=True, exist_ok=True)

    plan_path = Path("artifacts/market_data/plan_market_data.json")
    sync_path = Path("artifacts/market_data/sync_market_data.json")
    gap_path = Path("artifacts/market_data/gap_validate_market_data.json")

    # 1/3 Planner
    log_panel.push("Fase 1/3 - Planner: analisi copertura...")
    _set_status(status_label, text="Planner in esecuzione...", positive=None)
    t0 = time.perf_counter()
    rc = await run_streaming_command(_build_plan_command(state=state, db_path=db_path, plan_path=plan_path), log_panel)
    if rc != 0 or not plan_path.exists():
        ui.notify("Planner fallito", color="negative")
        _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
        _set_status(status_label, text="Planner fallito", positive=False)
        return False
    ps = _market_plan_summary(plan_path)
    state.market.latest_market_plan_path = str(plan_path)
    state.market.market_data_gap_count = ps["gaps"]
    log_panel.push(
        f"Planner: simboli={ps['symbols']}, gap={ps['gaps']}. ({time.perf_counter()-t0:.2f}s)"
    )
    summary_label.set_text(
        f"Simboli: {ps['symbols']} | Intervalli: {ps['required_intervals']} | Gap: {ps['gaps']}"
    )
    window_summary_label.set_text(str(ps["window_preview"]))

    if ps["gaps"] > 0:
        # 2/3 Sync
        log_panel.push(f"Fase 2/3 - Sync: integrazione {ps['gaps']} gap...")
        _set_status(status_label, text="Sync in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_sync_command(state=state, db_path=db_path, plan_path=plan_path, sync_path=sync_path), log_panel
        )
        if rc != 0 or not sync_path.exists():
            ui.notify("Sync fallito", color="negative")
            _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
            _set_status(status_label, text="Sync fallito", positive=False)
            return False
        state.market.latest_market_sync_report_path = str(sync_path)
        log_panel.push(f"Sync completato. ({time.perf_counter()-t0:.2f}s)")

        if state.market.validate_mode == "light":
            # 3/3 Gap validate — solo in modalità light
            _log_operation_banner(log_panel, title="Valida", state=state)
            log_panel.push("Fase 3/3 - Gap Validation: verifica gap sincronizzati...")
            _set_status(status_label, text="Gap validation in corso...", positive=None)
            t0 = time.perf_counter()
            rc = await run_streaming_command(
                _build_gap_validate_command(plan_path=plan_path, sync_path=sync_path, market_root=market_root, out_path=gap_path),
                log_panel,
            )
            if rc != 0 or not gap_path.exists():
                ui.notify("Gap validation fallita", color="negative")
                _mark_validation_failed(state=state, status_label=status_label, badge_label=badge_label)
                _set_status(status_label, text="Gap validation fallita", positive=False)
                return False
            log_panel.push(f"Gap validation completata. ({time.perf_counter()-t0:.2f}s)")
        else:
            log_panel.push(f"Fase 3/3 - Gap Validation: saltata (validate_mode={state.market.validate_mode}).")
    else:
        log_panel.push("Fase 2/3 - Sync: nessun gap, saltato.")
        log_panel.push("Fase 3/3 - Gap Validation: nessun gap, saltato.")

    if state.market.data_types.funding_rate:
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="needs_sync")
        log_panel.push("Fase funding - Sync funding rates...")
        _set_status(status_label, text="Funding sync in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_funding_sync_command(market_root=market_root, plan_path=plan_path),
            log_panel,
        )
        if rc != 0:
            _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="failed")
            ui.notify("Funding sync fallito", color="negative")
            _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
            _set_status(status_label, text="Funding sync fallito", positive=False)
            return False
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="synced")
        log_panel.push(f"Funding sync completato. ({time.perf_counter()-t0:.2f}s)")
    else:
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="not_requested")

    unsupported = _extract_unsupported_symbols(sync_path)
    if unsupported:
        log_panel.push(
            f"Simboli non supportati ({len(unsupported)}): {', '.join(unsupported)}"
        )

    state.market.market_ready = True
    state.market.market_prepare_total_seconds = round(time.perf_counter() - t_total, 3)
    final_status = "prepared_with_unsupported_symbols" if unsupported else "ready_unvalidated"
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key=final_status)
    _refresh_backtest_button(backtest_button_holder, state)
    summary_label.set_text(
        f"Preparazione: {state.market.market_prepare_total_seconds:.2f}s | "
        f"Simboli: {ps['symbols']} | Gap: {ps['gaps']}"
        + (f" | Non supportati: {len(unsupported)}" if unsupported else "")
    )
    window_summary_label.set_text(str(ps["window_preview"]))
    log_panel.push(f"Timing totale: {state.market.market_prepare_total_seconds:.2f}s")
    notify_msg = "Market data pronti — simboli non supportati presenti" if unsupported else "Market data pronti (non validati)"
    ui.notify(notify_msg, color="warning" if unsupported else "positive")
    return True


async def _run_validate_full(
    *,
    state: UiState,
    log_panel: LogPanel,
    status_label,
    badge_label,
    summary_label,
    window_summary_label,
    backtest_button_holder,
    run_streaming_command,
) -> bool:
    """Validate_full only on the existing cache."""
    plan_path = (
        Path(state.market.latest_market_plan_path)
        if state.market.latest_market_plan_path
        else Path("artifacts/market_data/plan_market_data.json")
    )
    if not plan_path.exists():
        ui.notify("Esegui prima Analizza o Prepara per generare il piano", color="negative")
        return False

    market_root = Path(state.market.market_data_dir)
    validate_path = Path("artifacts/market_data/validate_market_data.json")

    log_panel.clear()
    _log_operation_banner(log_panel, title="Valida", state=state)
    log_panel.push("Validazione completa del dataset...")
    _set_status(status_label, text="Validazione in corso...", positive=None)
    t0 = time.perf_counter()
    sync_path_for_validate = Path(state.market.latest_market_sync_report_path) if state.market.latest_market_sync_report_path else Path("artifacts/market_data/sync_market_data.json")
    validate_cmd = [
        sys.executable,
        "scripts/validate_market_data.py",
        "--plan-file", str(plan_path),
        "--market-dir", str(market_root),
        "--output", str(validate_path),
    ]
    if sync_path_for_validate.exists():
        validate_cmd += ["--sync-file", str(sync_path_for_validate)]
    rc = await run_streaming_command(validate_cmd, log_panel)
    elapsed = time.perf_counter() - t0

    if rc != 0 or not validate_path.exists():
        ui.notify("Validazione fallita: controlla log", color="negative")
        state.market.analysis_ready = False
        _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="needs_check")
        return False

    state.market.latest_market_validation_report_path = str(validate_path)
    state.market.market_ready = True
    state.market.analysis_ready = True
    ps = _market_plan_summary(plan_path)
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="validated")
    _refresh_backtest_button(backtest_button_holder, state)
    summary_label.set_text(f"Validazione completata in {elapsed:.2f}s. Artifact: {validate_path}")
    window_summary_label.set_text(str(ps["window_preview"]))
    log_panel.push(f"Validazione completata. ({elapsed:.2f}s)")
    ui.notify("Validazione completata", color="positive")
    return True


async def _run_prepare_and_validate(
    *,
    state: UiState,
    db_path: str,
    log_panel: LogPanel,
    status_label,
    badge_label,
    funding_status_label,
    summary_label,
    window_summary_label,
    backtest_button_holder,
    run_streaming_command,
) -> bool:
    """Pipeline completa secondo validate_mode: full / light / off."""
    db_path = db_path.strip()
    if not _validate_inputs(state, db_path):
        return False

    # Off: planner + sync + (funding sync), skip validate
    if state.market.validate_mode == "off":
        log_panel.clear()
        _log_operation_banner(log_panel, title="Prepara", state=state)
        t_total = time.perf_counter()
        market_root = Path(state.market.market_data_dir)

        if state.market.market_data_mode == "existing_dir" and not market_root.exists():
            ui.notify("Cartella market data non esiste", color="negative")
            _set_status(status_label, text="Cartella non trovata", positive=False)
            return False
        market_root.mkdir(parents=True, exist_ok=True)

        plan_path_off = Path("artifacts/market_data/plan_market_data.json")
        sync_path_off = Path("artifacts/market_data/sync_market_data.json")

        # 1/2 Planner
        log_panel.push("Fase 1/2 - Planner: analisi copertura...")
        _set_status(status_label, text="Planner in esecuzione...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_plan_command(state=state, db_path=db_path, plan_path=plan_path_off), log_panel
        )
        if rc != 0 or not plan_path_off.exists():
            ui.notify("Planner fallito", color="negative")
            _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
            _set_status(status_label, text="Planner fallito", positive=False)
            return False
        ps = _market_plan_summary(plan_path_off)
        state.market.latest_market_plan_path = str(plan_path_off)
        state.market.market_data_gap_count = ps["gaps"]
        log_panel.push(f"Planner: simboli={ps['symbols']}, gap={ps['gaps']}. ({time.perf_counter()-t0:.2f}s)")
        summary_label.set_text(
            f"Simboli: {ps['symbols']} | Intervalli: {ps['required_intervals']} | Gap: {ps['gaps']}"
        )
        window_summary_label.set_text(str(ps["window_preview"]))

        if ps["gaps"] > 0:
            # 2/2 Sync
            log_panel.push(f"Fase 2/2 - Sync: integrazione {ps['gaps']} gap...")
            _set_status(status_label, text="Sync in corso...", positive=None)
            t0 = time.perf_counter()
            rc = await run_streaming_command(
                _build_sync_command(state=state, db_path=db_path, plan_path=plan_path_off, sync_path=sync_path_off),
                log_panel,
            )
            if rc != 0 or not sync_path_off.exists():
                ui.notify("Sync fallito", color="negative")
                _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
                _set_status(status_label, text="Sync fallito", positive=False)
                return False
            state.market.latest_market_sync_report_path = str(sync_path_off)
            log_panel.push(f"Sync completato. ({time.perf_counter()-t0:.2f}s)")
        else:
            log_panel.push("Fase 2/2 - Sync: nessun gap, saltato.")

        log_panel.push("Modalità Off: validate saltato.")

        if state.market.data_types.funding_rate:
            _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="needs_sync")
            log_panel.push("Fase funding - Sync funding rates...")
            _set_status(status_label, text="Funding sync in corso...", positive=None)
            t0 = time.perf_counter()
            rc = await run_streaming_command(
                _build_funding_sync_command(market_root=market_root, plan_path=plan_path_off),
                log_panel,
            )
            if rc != 0:
                _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="failed")
                ui.notify("Funding sync fallito", color="negative")
                _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
                _set_status(status_label, text="Funding sync fallito", positive=False)
                return False
            _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="synced")
            log_panel.push(f"Funding sync completato. ({time.perf_counter()-t0:.2f}s)")
        else:
            _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="not_requested")

        unsupported_off = _extract_unsupported_symbols(sync_path_off)
        if unsupported_off:
            log_panel.push(
                f"Simboli non supportati ({len(unsupported_off)}): {', '.join(unsupported_off)}"
            )

        state.market.market_ready = True
        state.market.analysis_ready = True
        state.market.market_prepare_total_seconds = round(time.perf_counter() - t_total, 3)
        final_status_off = "prepared_with_unsupported_symbols" if unsupported_off else "ready_unvalidated"
        _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key=final_status_off)
        summary_label.set_text(
            f"Preparazione (off): {state.market.market_prepare_total_seconds:.2f}s | "
            f"Simboli: {ps['symbols']} | Gap: {ps['gaps']}"
            + (f" | Non supportati: {len(unsupported_off)}" if unsupported_off else "")
        )
        window_summary_label.set_text(str(ps["window_preview"]))
        log_panel.push(f"Timing totale: {state.market.market_prepare_total_seconds:.2f}s")
        notify_msg_off = "Market data pronti — simboli non supportati (modalità off)" if unsupported_off else "Market data pronti (non validati, modalità off)"
        ui.notify(notify_msg_off, color="warning" if unsupported_off else "positive")
        return True

    # Light: planner + sync + gap_validate only
    if state.market.validate_mode == "light":
        result = await _run_prepare(
            state=state,
            db_path=db_path,
            log_panel=log_panel,
            status_label=status_label,
            badge_label=badge_label,
            funding_status_label=funding_status_label,
            summary_label=summary_label,
            window_summary_label=window_summary_label,
            backtest_button_holder=backtest_button_holder,
            run_streaming_command=run_streaming_command,
        )
        if result:
            _apply_validation_status(
                state=state,
                status_label=status_label,
                badge_label=badge_label,
                status_key="gap_validated_partial",
            )
            _refresh_backtest_button(backtest_button_holder, state)
        return result

    # Full: planner + sync + gap_validate + validate_full (with fingerprint cache)
    log_panel.clear()
    _log_operation_banner(log_panel, title="Prepara", state=state)
    t_total = time.perf_counter()
    market_root = Path(state.market.market_data_dir)

    if state.market.market_data_mode == "existing_dir" and not market_root.exists():
        ui.notify("Cartella market data non esiste", color="negative")
        _set_status(status_label, text="Cartella non trovata", positive=False)
        return False
    market_root.mkdir(parents=True, exist_ok=True)

    plan_path = Path("artifacts/market_data/plan_market_data.json")
    sync_path = Path("artifacts/market_data/sync_market_data.json")
    gap_path = Path("artifacts/market_data/gap_validate_market_data.json")
    validate_path = Path("artifacts/market_data/validate_market_data.json")

    # Fingerprint cache check
    request = build_market_request(
        db_path=db_path,
        market_data_dir=str(market_root),
        trader_filter=state.backtest_trader_filter or "all",
        date_from=state.backtest_date_from or "",
        date_to=state.backtest_date_to or "",
        max_trades=max(0, state.backtest_max_trades),
        timeframe=state.market.download_tf,
        price_basis=state.market.price_basis,
        source=state.market.market_data_source,
        download_tfs=list(state.market.download_tfs),
        simulation_tf=state.market.simulation_tf,
        detail_tf=state.market.detail_tf,
        validate_mode=state.market.validate_mode,
        ohlcv_last=state.market.data_types.ohlcv_last,
        ohlcv_mark=state.market.data_types.ohlcv_mark,
        funding_rate=state.market.data_types.funding_rate,
        buffer_mode=state.market.buffer_mode,
        pre_buffer_days=state.market.pre_buffer_days,
        post_buffer_days=state.market.post_buffer_days,
        buffer_preset=state.market.buffer_preset,
    )
    fingerprint = market_request_fingerprint(request)
    index_path = validation_index_path(str(market_root))
    index_payload = load_validation_index(index_path)
    cached_record = find_pass_validation_record(index_payload, fingerprint)
    state.market.market_validation_fingerprint = fingerprint

    if cached_record and not state.market.data_types.funding_rate:
        log_panel.push("Validation cache hit: riuso validazione PASS già esistente.")
        log_panel.push(f"fingerprint={fingerprint}")
        state.market.market_ready = True
        state.market.latest_market_plan_path = str(cached_record.get("plan_path") or "")
        state.market.latest_market_sync_report_path = str(cached_record.get("sync_report_path") or "")
        state.market.latest_market_validation_report_path = str(cached_record.get("validate_report_path") or "")
        state.market.market_data_gap_count = int((cached_record.get("summary") or {}).get("gaps", 0))
        state.market.market_prepare_total_seconds = 0.0
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="not_requested")
        _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="validated")
        summary_label.set_text("Validation cache hit: market data già validati per questa richiesta.")
        window_summary_label.set_text("Finestre: piano riusato da validation cache.")
        ui.notify("Validation cache hit: market data già validati", color="positive")
        return True

    # 1/4 Planner
    log_panel.push("Fase 1/4 - Planner: analisi copertura...")
    _set_status(status_label, text="Planner in esecuzione...", positive=None)
    t0 = time.perf_counter()
    rc = await run_streaming_command(_build_plan_command(state=state, db_path=db_path, plan_path=plan_path), log_panel)
    if rc != 0 or not plan_path.exists():
        ui.notify("Planner fallito", color="negative")
        _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
        _set_status(status_label, text="Planner fallito", positive=False)
        return False
    ps = _market_plan_summary(plan_path)
    state.market.latest_market_plan_path = str(plan_path)
    state.market.market_data_gap_count = ps["gaps"]
    log_panel.push(f"Planner: simboli={ps['symbols']}, gap={ps['gaps']}. ({time.perf_counter()-t0:.2f}s)")
    summary_label.set_text(
        f"Simboli: {ps['symbols']} | Intervalli: {ps['required_intervals']} | Gap: {ps['gaps']}"
    )
    window_summary_label.set_text(str(ps["window_preview"]))

    if ps["gaps"] > 0:
        # 2/4 Sync
        log_panel.push(f"Fase 2/4 - Sync: integrazione {ps['gaps']} gap...")
        _set_status(status_label, text="Sync in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_sync_command(state=state, db_path=db_path, plan_path=plan_path, sync_path=sync_path), log_panel
        )
        if rc != 0 or not sync_path.exists():
            ui.notify("Sync fallito", color="negative")
            _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
            _set_status(status_label, text="Sync fallito", positive=False)
            return False
        state.market.latest_market_sync_report_path = str(sync_path)
        log_panel.push(f"Sync completato. ({time.perf_counter()-t0:.2f}s)")

        # 3/4 Gap validate
        _log_operation_banner(log_panel, title="Gap Validation", state=state)
        log_panel.push("Fase 3/4 - Gap Validation...")
        _set_status(status_label, text="Gap validation in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_gap_validate_command(plan_path=plan_path, sync_path=sync_path, market_root=market_root, out_path=gap_path),
            log_panel,
        )
        if rc != 0 or not gap_path.exists():
            ui.notify("Gap validation fallita", color="negative")
            _mark_validation_failed(state=state, status_label=status_label, badge_label=badge_label)
            _set_status(status_label, text="Gap validation fallita", positive=False)
            return False
        log_panel.push(f"Gap validation completata. ({time.perf_counter()-t0:.2f}s)")
    else:
        log_panel.push("Fase 2/4 - Sync: nessun gap, saltato.")
        log_panel.push("Fase 3/4 - Gap Validation: nessun gap, saltato.")

    if state.market.data_types.funding_rate:
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="needs_sync")
        log_panel.push("Fase funding - Sync funding rates...")
        _set_status(status_label, text="Funding sync in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_funding_sync_command(market_root=market_root, plan_path=plan_path),
            log_panel,
        )
        if rc != 0:
            _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="failed")
            ui.notify("Funding sync fallito", color="negative")
            _mark_prepare_failed(state=state, status_label=status_label, badge_label=badge_label)
            _set_status(status_label, text="Funding sync fallito", positive=False)
            return False
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="synced")
        log_panel.push(f"Funding sync completato. ({time.perf_counter()-t0:.2f}s)")
    else:
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="not_requested")

    # 4/4 Validate full
    _log_operation_banner(log_panel, title="Valida", state=state)
    log_panel.push("Fase 4/4 - Validate: verifica consistenza cache...")
    _set_status(status_label, text="Validazione completa in corso...", positive=None)
    t0 = time.perf_counter()
    validate_cmd_full = [
        sys.executable,
        "scripts/validate_market_data.py",
        "--plan-file", str(plan_path),
        "--market-dir", str(market_root),
        "--output", str(validate_path),
    ]
    if sync_path.exists():
        validate_cmd_full += ["--sync-file", str(sync_path)]
    rc = await run_streaming_command(validate_cmd_full, log_panel)
    if rc != 0 or not validate_path.exists():
        ui.notify("Validazione fallita", color="negative")
        _mark_validation_failed(state=state, status_label=status_label, badge_label=badge_label)
        upsert_validation_record(
            index_payload=index_payload,
            request=request,
            fingerprint=fingerprint,
            status="FAIL",
            plan_path=str(plan_path),
            sync_report_path=str(sync_path) if sync_path.exists() else "",
            validate_report_path=str(validate_path) if validate_path.exists() else "",
            summary=ps,
        )
        save_validation_index(index_path, index_payload)
        return False

    log_panel.push(f"Validazione completata. ({time.perf_counter()-t0:.2f}s)")

    if state.market.data_types.funding_rate:
        funding_validate_path = Path("artifacts/market_data/validate_funding_rates.json")
        log_panel.push("Fase funding - Validate funding rates...")
        _set_status(status_label, text="Validazione funding in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_funding_validate_command(
                market_root=market_root,
                plan_path=plan_path,
                out_path=funding_validate_path,
            ),
            log_panel,
        )
        if rc != 0 or not funding_validate_path.exists():
            _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="failed")
            ui.notify("Validazione funding fallita", color="negative")
            _mark_validation_failed(state=state, status_label=status_label, badge_label=badge_label)
            upsert_validation_record(
                index_payload=index_payload,
                request=request,
                fingerprint=fingerprint,
                status="FAIL",
                plan_path=str(plan_path),
                sync_report_path=str(sync_path) if sync_path.exists() else "",
                validate_report_path=str(validate_path) if validate_path.exists() else "",
                summary=ps,
            )
            save_validation_index(index_path, index_payload)
            return False
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="validated")
        log_panel.push(f"Validazione funding completata. ({time.perf_counter()-t0:.2f}s)")

    state.market.latest_market_validation_report_path = str(validate_path)
    state.market.market_ready = True
    state.market.analysis_ready = True
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="validated")
    _refresh_backtest_button(backtest_button_holder, state)

    upsert_validation_record(
        index_payload=index_payload,
        request=request,
        fingerprint=fingerprint,
        status="PASS",
        plan_path=str(plan_path),
        sync_report_path=str(sync_path) if sync_path.exists() else "",
        validate_report_path=str(validate_path),
        summary=ps,
    )
    save_validation_index(index_path, index_payload)
    state.market.market_prepare_total_seconds = round(time.perf_counter() - t_total, 3)
    log_panel.push(f"Timing totale: {state.market.market_prepare_total_seconds:.2f}s")
    summary_label.set_text(
        f"Artifacts: plan={state.market.latest_market_plan_path}, "
        f"validate={state.market.latest_market_validation_report_path}"
    )
    window_summary_label.set_text(str(ps["window_preview"]))
    ui.notify("Market data pronti e validati", color="positive")
    return True


# ---------------------------------------------------------------------------
# Market context + stop support
# ---------------------------------------------------------------------------

class _MarketCtx:
    process: object = None  # asyncio.subprocess.Process | None
    stop_requested: bool = False


_market_ctx = _MarketCtx()


def _stop_market(log_panel: LogPanel) -> None:
    if _market_ctx.process is None:
        ui.notify("Nessun processo in corso", color="warning")
        return
    _market_ctx.stop_requested = True
    log_panel.push("Richiesta arresto...")
    try:
        _market_ctx.process.terminate()
    except ProcessLookupError:
        pass
    ui.notify("Arresto richiesto", color="warning")


def _make_tracking_runner(run_streaming_command):
    """Wrap run_streaming_command to auto-track the current process."""
    async def _tracked(cmd, log_panel, process_started=None):
        def _bind(proc):
            _market_ctx.process = proc
            if process_started:
                process_started(proc)
        rc = await run_streaming_command(cmd, log_panel, _bind)
        _market_ctx.process = None
        return rc
    return _tracked


# ---------------------------------------------------------------------------
# Coverage grid helpers
# ---------------------------------------------------------------------------

def _cov_card_html(value: str, label: str, highlight: bool = False) -> str:
    val_color = "var(--ok)" if highlight else "var(--text)"
    return (
        f'<div style="background:var(--surface-2);border:1px solid var(--border-s);'
        f'border-radius:var(--rs);padding:10px 14px;text-align:center">'
        f'<div style="font-family:var(--mono);font-size:20px;font-weight:600;color:{val_color}">{value}</div>'
        f'<div style="font-size:10px;color:var(--muted);margin-top:4px;text-transform:uppercase;'
        f'letter-spacing:.06em">{label}</div>'
        f'</div>'
    )


def _roadmap_chip_html(label: str) -> str:
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;opacity:.5;'
        f'font-family:var(--mono);font-size:11px;padding:2px 8px;'
        f'background:var(--surface-2);border:1px solid var(--border-s);'
        f'border-radius:var(--rs);color:var(--muted)">'
        f'{label} <span style="font-size:9px;color:var(--wa);border:1px solid var(--wa);'
        f'border-radius:var(--rs);padding:0 4px">ROADMAP</span></span>'
    )


# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def render_market_data_panel(state: UiState, *, run_streaming_command, backtest_button_holder: list) -> None:
    """Render the Market Data sub-tab panel."""
    tracking_runner = _make_tracking_runner(run_streaming_command)

    def _persist() -> None:
        debounced_save(state.to_dict())

    with ui.column().style("padding:16px 20px;gap:16px").classes("w-full block-shell"):

        # ── title ────────────────────────────────────────────────────────
        with ui.row().style("align-items:baseline;gap:8px"):
            ui.html('<span style="font-family:var(--mono);font-size:11px;color:var(--muted)">03</span>')
            ui.label("· Market Data").style(
                "font-family:var(--sans);font-size:15px;font-weight:600;color:var(--text)"
            )

        # ── row 1: source + validate mode + price basis ──────────────────
        with ui.row().classes("w-full gap-4"):
            source_select = ui.select(
                options={"bybit": "Bybit", "fixture": "Fixture"},
                value=state.market.market_data_source,
                label="Source",
            ).classes("w-32")
            validate_mode_select = ui.select(
                options={"light": "GAPs — verifica e colma gap", "off": "OFF — dataset esistente"},
                value=state.market.validate_mode if state.market.validate_mode in ("light", "off") else "light",
                label="Validate mode",
            ).classes("flex-1")
            price_basis_select = ui.select(
                options={"last": "last", "mark": "mark"},
                value=state.market.price_basis,
                label="Price basis",
            ).classes("w-32")

        # ── row 2: download TF checkboxes ────────────────────────────────
        ui.html('<div class="sec-lbl">Download TF</div>')
        download_tf_toggles: dict[str, object] = {}
        with ui.row().classes("w-full gap-4 items-center"):
            selected_download_tfs = {
                tf for tf in state.market.download_tfs if tf in {v for v, _ in _TF_OPTIONS}
            }
            if not selected_download_tfs:
                selected_download_tfs = {"1m"}
            for tf_value, tf_label in _TF_OPTIONS:
                download_tf_toggles[tf_value] = ui.checkbox(
                    tf_label, value=tf_value in selected_download_tfs
                )

        # ── buffer ───────────────────────────────────────────────────────
        ui.html('<div class="sec-lbl">Buffer</div>')
        with ui.row().classes("w-full gap-4 items-center"):
            buffer_mode_radio = ui.radio(
                {"auto": "Auto", "manual": "Manuale"},
                value=state.market.buffer_mode,
            ).props("inline")

        with ui.row().classes("w-full gap-4") as manual_buffer_col:
            pre_buffer_input = ui.number(
                "Pre buffer (d)", value=state.market.pre_buffer_days, min=0, max=365, step=1
            ).classes("flex-1")
            post_buffer_input = ui.number(
                "Post buffer (d)", value=state.market.post_buffer_days, min=0, max=365, step=1
            ).classes("flex-1")
        manual_buffer_col.set_visibility(state.market.buffer_mode == "manual")

        # ── new directory toggle ─────────────────────────────────────────
        with ui.row().classes("w-full items-center gap-4"):
            new_dir_toggle = ui.switch("Nuova directory", value=state.market.new_dir_enabled)
            new_dir_path_input = ui.input(
                "Path nuova directory", value=state.market.new_dir_path
            ).classes("flex-1 inp-mono")
            new_dir_hint = ui.label("").style("font-size:11px;color:var(--er)")
        new_dir_path_input.set_visibility(state.market.new_dir_enabled)
        new_dir_toggle.on(
            "update:model-value",
            lambda e: new_dir_path_input.set_visibility(bool(e.value)),
        )

        # ── data types ───────────────────────────────────────────────────
        ui.html('<div class="sec-lbl">Tipo dati</div>')
        with ui.row().classes("w-full gap-4 items-center flex-wrap"):
            perp_toggle = ui.switch("Perp", value=state.market.data_types.perp)
            funding_toggle = ui.switch("Funding rate", value=state.market.data_types.funding)
            ui.html(_roadmap_chip_html("Spot"))
            ui.html(_roadmap_chip_html("Open interest"))
            ui.html(_roadmap_chip_html("Liquidations"))

        # ── status labels (legacy, hidden — kept for orchestration) ──────
        status_label = ui.label("").style("display:none")
        badge_label = ui.label("").style("display:none")
        funding_status_label = ui.label("").style("display:none")
        summary_label = ui.label("").style("display:none")
        window_summary_label = ui.label("").style("display:none")

        _init_status = state.market.market_validation_status
        if _init_status in {"validated", "gap_validated", "gap_validated_partial", "ready_unvalidated"}:
            badge_label.set_text("READY")
        else:
            badge_label.set_text("NOT READY")
        _set_funding_status(
            state=state,
            funding_status_label=funding_status_label,
            status_key=state.market.funding_status,
        )

        # ── coverage grid ────────────────────────────────────────────────
        ui.html('<div class="sec-lbl" style="margin-top:4px">Coverage</div>')
        with ui.grid(columns=4).classes("w-full gap-3"):
            cov_symbols = ui.html(_cov_card_html("—", "Simboli"))
            cov_intervals = ui.html(_cov_card_html("—", "Intervalli req."))
            cov_gaps = ui.html(_cov_card_html("—", "Gap"))
            cov_pct = ui.html(_cov_card_html("—", "Copertura %"))

        def _update_coverage(ps: dict) -> None:
            total = ps.get("symbols", 0)
            complete = ps.get("symbols_complete", 0)
            intervals = ps.get("required_intervals", 0)
            gaps = ps.get("gaps", 0)
            pct = round(100 * complete / total, 1) if total > 0 else 0
            cov_symbols.set_content(_cov_card_html(str(total), "Simboli"))
            cov_intervals.set_content(_cov_card_html(str(intervals), "Intervalli req."))
            cov_gaps.set_content(_cov_card_html(str(gaps), "Gap", highlight=gaps == 0))
            cov_pct.set_content(_cov_card_html(f"{pct}%", "Copertura %", highlight=pct >= 95))

        # ── state sync ───────────────────────────────────────────────────
        def _sync_state_from_ui() -> None:
            state.market.market_data_source = source_select.value
            state.market.validate_mode = validate_mode_select.value
            state.market.price_basis = price_basis_select.value
            selected_tfs = [v for v, _ in _TF_OPTIONS if bool(download_tf_toggles[v].value)]
            if not selected_tfs:
                selected_tfs = ["1m"]
            state.market.download_tfs = selected_tfs
            state.market.download_tf = selected_tfs[0]
            state.market.buffer_mode = buffer_mode_radio.value
            if buffer_mode_radio.value == "manual":
                state.market.pre_buffer_days = int(pre_buffer_input.value or 0)
                state.market.post_buffer_days = int(post_buffer_input.value or 0)
            state.market.new_dir_enabled = bool(new_dir_toggle.value)
            state.market.new_dir_path = new_dir_path_input.value.strip()
            # data types: perp → ohlcv_last/mark depending on price_basis
            perp_on = bool(perp_toggle.value)
            state.market.data_types.perp = perp_on
            state.market.data_types.ohlcv_last = perp_on and state.market.price_basis == "last"
            state.market.data_types.ohlcv_mark = perp_on and state.market.price_basis == "mark"
            funding_on = bool(funding_toggle.value)
            state.market.data_types.funding = funding_on
            state.market.data_types.funding_rate = funding_on

        def _refresh_new_dir_validity() -> None:
            path = new_dir_path_input.value.strip()
            invalid = bool(path) and not Path(path).exists()
            new_dir_path_input.style(f"border-color:{'var(--er)' if invalid else 'var(--border)'}")
            new_dir_hint.set_text("percorso non trovato" if invalid else "")

        def _on_inputs_change(*_) -> None:
            _sync_state_from_ui()
            _refresh_new_dir_validity()
            _reset_market_state(
                state=state,
                status_label=status_label,
                badge_label=badge_label,
                summary_label=summary_label,
                window_summary_label=window_summary_label,
                funding_status_label=funding_status_label,
            )
            _persist()

        def _on_buffer_mode_change(*_) -> None:
            manual_buffer_col.set_visibility(buffer_mode_radio.value == "manual")
            _on_inputs_change()

        # ── action handlers ───────────────────────────────────────────────
        async def _on_analizza() -> None:
            _sync_state_from_ui()
            await _run_analyze(
                state=state,
                db_path=state.effective_db_path(),
                log_panel=market_log,
                status_label=status_label,
                badge_label=badge_label,
                summary_label=summary_label,
                window_summary_label=window_summary_label,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=tracking_runner,
            )
            if state.market.latest_market_plan_path:
                try:
                    from pathlib import Path as _Path
                    import json as _json
                    ps = _market_plan_summary(_Path(state.market.latest_market_plan_path))
                    _update_coverage(ps)
                except Exception:
                    pass

        async def _on_prepara() -> None:
            _sync_state_from_ui()
            await _run_prepare(
                state=state,
                db_path=state.effective_db_path(),
                log_panel=market_log,
                status_label=status_label,
                badge_label=badge_label,
                funding_status_label=funding_status_label,
                summary_label=summary_label,
                window_summary_label=window_summary_label,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=tracking_runner,
            )
            if state.market.latest_market_plan_path:
                try:
                    from pathlib import Path as _Path
                    ps = _market_plan_summary(_Path(state.market.latest_market_plan_path))
                    _update_coverage(ps)
                except Exception:
                    pass

        async def _on_valida() -> None:
            _sync_state_from_ui()
            await _run_validate_full(
                state=state,
                log_panel=market_log,
                status_label=status_label,
                badge_label=badge_label,
                summary_label=summary_label,
                window_summary_label=window_summary_label,
                backtest_button_holder=backtest_button_holder,
                run_streaming_command=tracking_runner,
            )

        # ── log ───────────────────────────────────────────────────────────
        market_log = LogPanel(title="Log Market Data")

        # ── action buttons ────────────────────────────────────────────────
        with ui.row().classes("gap-2"):
            ui.button("▶ Analizza", on_click=_on_analizza).props("color=primary")
            ui.button("⬇ Prepara", on_click=_on_prepara).props("outline")
            ui.button("✓ Valida", on_click=_on_valida).props("outline")
            ui.button(
                "■ Arresta",
                on_click=lambda: _stop_market(market_log),
            ).style("color:var(--er);border-color:var(--er)").props("outline")

        # ── event wiring ─────────────────────────────────────────────────
        source_select.on("update:model-value", _on_inputs_change)
        validate_mode_select.on("update:model-value", _on_inputs_change)
        price_basis_select.on("update:model-value", _on_inputs_change)
        for tf_value, _ in _TF_OPTIONS:
            download_tf_toggles[tf_value].on("update:model-value", _on_inputs_change)
        buffer_mode_radio.on("update:model-value", _on_buffer_mode_change)
        pre_buffer_input.on("update:model-value", _on_inputs_change)
        post_buffer_input.on("update:model-value", _on_inputs_change)
        perp_toggle.on("update:model-value", _on_inputs_change)
        funding_toggle.on("update:model-value", _on_inputs_change)
        new_dir_path_input.on("update:model-value", _on_inputs_change)
        new_dir_toggle.on("update:model-value", _on_inputs_change)
        _refresh_new_dir_validity()
