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
    format_data_types_summary,
    format_window_preview,
    roadmap_data_type_labels,
    supported_data_type_labels,
)
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.file_dialogs import ask_directory
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
    elif "unvalidated" in status:
        badge_label.classes(add="text-grey-6")
    else:
        badge_label.classes(add="text-negative")


def _apply_validation_status(*, state: UiState, status_label, badge_label, status_key: str) -> None:
    state.market.market_validation_status = status_key
    if status_key == "validated":
        _set_status(status_label, text="Market data validati", positive=True)
        _update_badge(badge_label, status="READY")
    elif status_key == "gap_validated":
        _set_status(status_label, text="Market data pronti, gap validati", positive=True)
        _update_badge(badge_label, status="READY")
    elif status_key == "ready_unvalidated":
        _set_status(status_label, text="Market data pronti ma non validati", positive=None)
        _update_badge(badge_label, status="READY (unvalidated)")
    else:
        _set_status(status_label, text="Market data da verificare", positive=None)
        _update_badge(badge_label, status="NOT READY")


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
    return {
        "symbols": int(s.get("symbols", 0)),
        "required_intervals": int(s.get("required_intervals", 0)),
        "gaps": int(s.get("gaps", 0)),
        "window_preview": format_window_preview(payload),
    }


def _selected_data_types_text(state: UiState) -> str:
    return format_data_types_summary(state.market.data_types)


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
    run_streaming_command,
) -> None:
    """Planner only — discovery, no download."""
    db_path = db_path.strip()
    if not _validate_inputs(state, db_path):
        return

    log_panel.clear()
    log_panel.push("Analisi copertura richiesta dal DB...")
    _set_status(status_label, text="Analisi in corso...", positive=None)

    plan_path = Path("artifacts/market_data/plan_market_data.json")
    rc = await run_streaming_command(_build_plan_command(state=state, db_path=db_path, plan_path=plan_path), log_panel)
    if rc != 0 or not plan_path.exists():
        ui.notify("Analisi fallita: controlla log", color="negative")
        _set_status(status_label, text="Analisi fallita", positive=False)
        return

    ps = _market_plan_summary(plan_path)
    state.market.latest_market_plan_path = str(plan_path)
    state.market.market_data_gap_count = ps["gaps"]
    summary_label.set_text(
        f"Simboli: {ps['symbols']} | Intervalli: {ps['required_intervals']} | Gap: {ps['gaps']}"
    )
    window_summary_label.set_text(str(ps["window_preview"]))
    _set_status(status_label, text="Analisi completata", positive=True)
    log_panel.push(
        f"Analisi completata: simboli={ps['symbols']}, intervalli={ps['required_intervals']}, gap={ps['gaps']}."
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
    run_streaming_command,
) -> bool:
    """Planner + sync + gap_validate (no validate_full)."""
    db_path = db_path.strip()
    if not _validate_inputs(state, db_path):
        return False

    log_panel.clear()
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
            _set_status(status_label, text="Sync fallito", positive=False)
            return False
        state.market.latest_market_sync_report_path = str(sync_path)
        log_panel.push(f"Sync completato. ({time.perf_counter()-t0:.2f}s)")

        # 3/3 Gap validate
        log_panel.push("Fase 3/3 - Gap Validation: verifica gap sincronizzati...")
        _set_status(status_label, text="Gap validation in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_gap_validate_command(plan_path=plan_path, sync_path=sync_path, market_root=market_root, out_path=gap_path),
            log_panel,
        )
        if rc != 0 or not gap_path.exists():
            ui.notify("Gap validation fallita", color="negative")
            _set_status(status_label, text="Gap validation fallita", positive=False)
            return False
        log_panel.push(f"Gap validation completata. ({time.perf_counter()-t0:.2f}s)")
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
            _set_status(status_label, text="Funding sync fallito", positive=False)
            return False
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="synced")
        log_panel.push(f"Funding sync completato. ({time.perf_counter()-t0:.2f}s)")
    else:
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="not_requested")

    state.market.market_ready = True
    state.market.market_prepare_total_seconds = round(time.perf_counter() - t_total, 3)
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="ready_unvalidated")
    summary_label.set_text(
        f"Preparazione: {state.market.market_prepare_total_seconds:.2f}s | "
        f"Simboli: {ps['symbols']} | Gap: {ps['gaps']}"
    )
    window_summary_label.set_text(str(ps["window_preview"]))
    log_panel.push(f"Timing totale: {state.market.market_prepare_total_seconds:.2f}s")
    ui.notify("Market data pronti (non validati)", color="positive")
    return True


async def _run_validate_full(
    *,
    state: UiState,
    log_panel: LogPanel,
    status_label,
    badge_label,
    summary_label,
    window_summary_label,
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

    log_panel.push("Validazione completa del dataset...")
    _set_status(status_label, text="Validazione in corso...", positive=None)
    t0 = time.perf_counter()
    rc = await run_streaming_command(
        [
            sys.executable,
            "scripts/validate_market_data.py",
            "--plan-file", str(plan_path),
            "--market-dir", str(market_root),
            "--output", str(validate_path),
        ],
        log_panel,
    )
    elapsed = time.perf_counter() - t0

    if rc != 0 or not validate_path.exists():
        ui.notify("Validazione fallita: controlla log", color="negative")
        _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="needs_check")
        return False

    state.market.latest_market_validation_report_path = str(validate_path)
    state.market.market_ready = True
    ps = _market_plan_summary(plan_path)
    key = "gap_validated" if ps["gaps"] > 0 else "validated"
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key=key)
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
    run_streaming_command,
) -> bool:
    """Pipeline completa secondo validate_mode: full / light / off."""
    db_path = db_path.strip()
    if not _validate_inputs(state, db_path):
        return False

    # Off: trust existing dataset, skip all phases
    if state.market.validate_mode == "off":
        log_panel.clear()
        log_panel.push("Modalità Off: nessuna preparazione eseguita.")
        log_panel.push("Dataset marcato come pronto senza validazione.")
        state.market.market_ready = True
        state.market.market_prepare_total_seconds = 0.0
        _set_funding_status(
            state=state,
            funding_status_label=funding_status_label,
            status_key="needs_sync" if state.market.data_types.funding_rate else "not_requested",
        )
        _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="ready_unvalidated")
        summary_label.set_text("Modalità Off: dataset fidato senza esecuzione del pipeline.")
        window_summary_label.set_text("Finestre: non calcolate in modalità Off.")
        ui.notify("Market data marcati come pronti (non validati)", color="warning")
        return True

    # Light: planner + sync + gap_validate only
    if state.market.validate_mode == "light":
        return await _run_prepare(
            state=state,
            db_path=db_path,
            log_panel=log_panel,
            status_label=status_label,
            badge_label=badge_label,
            funding_status_label=funding_status_label,
            summary_label=summary_label,
            window_summary_label=window_summary_label,
            run_streaming_command=run_streaming_command,
        )

    # Full: planner + sync + gap_validate + validate_full (with fingerprint cache)
    log_panel.clear()
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
            _set_status(status_label, text="Sync fallito", positive=False)
            return False
        state.market.latest_market_sync_report_path = str(sync_path)
        log_panel.push(f"Sync completato. ({time.perf_counter()-t0:.2f}s)")

        # 3/4 Gap validate
        log_panel.push("Fase 3/4 - Gap Validation...")
        _set_status(status_label, text="Gap validation in corso...", positive=None)
        t0 = time.perf_counter()
        rc = await run_streaming_command(
            _build_gap_validate_command(plan_path=plan_path, sync_path=sync_path, market_root=market_root, out_path=gap_path),
            log_panel,
        )
        if rc != 0 or not gap_path.exists():
            ui.notify("Gap validation fallita", color="negative")
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
            _set_status(status_label, text="Funding sync fallito", positive=False)
            return False
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="synced")
        log_panel.push(f"Funding sync completato. ({time.perf_counter()-t0:.2f}s)")
    else:
        _set_funding_status(state=state, funding_status_label=funding_status_label, status_key="not_requested")

    # 4/4 Validate full
    log_panel.push("Fase 4/4 - Validate: verifica consistenza cache...")
    _set_status(status_label, text="Validazione completa in corso...", positive=None)
    t0 = time.perf_counter()
    rc = await run_streaming_command(
        [
            sys.executable,
            "scripts/validate_market_data.py",
            "--plan-file", str(plan_path),
            "--market-dir", str(market_root),
            "--output", str(validate_path),
        ],
        log_panel,
    )
    if rc != 0 or not validate_path.exists():
        ui.notify("Validazione fallita", color="negative")
        _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="needs_check")
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
            _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key="needs_check")
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
    key = "gap_validated" if ps["gaps"] > 0 else "validated"
    _apply_validation_status(state=state, status_label=status_label, badge_label=badge_label, status_key=key)

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
# Public render function
# ---------------------------------------------------------------------------

def render_market_data_panel(state: UiState, *, run_streaming_command) -> None:
    """Render the collapsible Market DATA panel inside Blocco 3."""

    with ui.expansion("Market DATA", icon="storage").classes("w-full"):

        # ------------------------------------------------------------------
        # Setup section
        # ------------------------------------------------------------------
        with ui.card().classes("w-full"):
            ui.label("Setup").classes("text-subtitle2")

            with ui.row().classes("w-full items-end gap-2"):
                market_dir_input = ui.input(
                    "Cartella market data",
                    value=state.market.market_data_dir,
                ).classes("flex-1")

                async def _browse() -> None:
                    selected = ask_directory(
                        initialdir=_PROJECT_ROOT,
                        title="Seleziona la cartella market data",
                        mustexist=False,
                    )
                    if selected:
                        market_dir_input.value = selected
                        market_dir_input.update()
                        _on_inputs_change()
                    else:
                        ui.notify("Selezione annullata.", color="warning")

                ui.button("Sfoglia", on_click=_browse, icon="folder_open")

            market_mode = ui.radio(
                {
                    "existing_dir": "Usa cartella esistente e integra i gap mancanti",
                    "new_dir": "Prepara da capo in una nuova cartella",
                },
                value=state.market.market_data_mode,
            ).props("inline")

            with ui.column().classes("w-full mt-2 gap-1"):
                ui.label("Download TF (multi)").classes("text-caption text-grey-7")
                download_tf_toggles: dict[str, object] = {}
                with ui.row().classes("w-full gap-4 items-center"):
                    selected_download_tfs = {
                        tf for tf in state.market.download_tfs if tf in {value for value, _ in _TF_OPTIONS}
                    }
                    if not selected_download_tfs:
                        selected_download_tfs = {"1m"}
                    for tf_value, tf_label in _TF_OPTIONS:
                        download_tf_toggles[tf_value] = ui.checkbox(
                            tf_label,
                            value=tf_value in selected_download_tfs,
                        )

            tf_select_options = {value: label for value, label in _TF_OPTIONS}
            with ui.row().classes("w-full gap-4 mt-2"):
                simulation_tf_select = ui.select(
                    options=tf_select_options,
                    value=state.market.simulation_tf if state.market.simulation_tf in tf_select_options else "1m",
                    label="Simulation TF / Parent",
                ).classes("flex-1")
                detail_tf_select = ui.select(
                    options=tf_select_options,
                    value=state.market.detail_tf if state.market.detail_tf in tf_select_options else "1m",
                    label="Detail TF / Child",
                ).classes("flex-1")

            with ui.row().classes("w-full gap-4 mt-2"):
                price_basis_select = ui.select(
                    options={"last": "last (standard)", "mark": "mark (mark price)"},
                    value=state.market.price_basis,
                    label="Price basis",
                ).classes("flex-1")
                source_select = ui.select(
                    options={"bybit": "bybit", "fixture": "fixture"},
                    value=state.market.market_data_source,
                    label="Market source",
                ).classes("flex-1")

            with ui.row().classes("w-full mt-2"):
                validate_mode_select = ui.select(
                    options={
                        "full": "Full — planner + sync + gap_validate + validate_full",
                        "light": "Light — planner + sync + gap_validate",
                        "off": "Off — fidati del dataset esistente",
                    },
                    value=state.market.validate_mode,
                    label="Modalità validazione",
                ).classes("flex-1")

            ui.separator().classes("mt-2")
            ui.label("Tipo dati").classes("text-caption text-grey-7 mt-1")
            with ui.column().classes("w-full gap-1"):
                with ui.row().classes("w-full gap-4 items-center"):
                    ohlcv_last_toggle = ui.checkbox("OHLCV last", value=state.market.data_types.ohlcv_last)
                    ohlcv_mark_toggle = ui.checkbox("OHLCV mark", value=state.market.data_types.ohlcv_mark)
                    funding_rate_toggle = ui.checkbox("Funding rate", value=state.market.data_types.funding_rate)
                ui.label(
                    "Funding rate richiede `sync_funding_rates.py` prima del backtest."
                ).classes("text-caption text-grey-6")
                ui.label("Dataset roadmap").classes("text-caption text-grey-6")
                for roadmap_label in roadmap_data_type_labels():
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.checkbox(roadmap_label, value=False).disable()
                        ui.badge("roadmap").props("outline color=grey")
                ui.label(
                    "Le voci roadmap sono visibili per orientare l'evoluzione, ma non entrano nella pipeline attuale."
                ).classes("text-caption text-grey-6")
                ui.label(
                    "Fees / Cost Model -> sezione separata"
                ).classes("text-caption text-grey-6")

            ui.separator().classes("mt-2")
            ui.label("Buffer mode").classes("text-caption text-grey-7 mt-1")
            buffer_mode_radio = ui.radio(
                {"auto": "AUTO (adattivo)", "manual": "MANUAL"},
                value=state.market.buffer_mode,
            ).props("inline")

            with ui.column().classes("w-full mt-1") as manual_buffer_col:
                with ui.row().classes("w-full gap-4"):
                    pre_buffer_input = ui.number(
                        "Pre-buffer (giorni)",
                        value=state.market.pre_buffer_days,
                        min=0,
                        max=365,
                        step=1,
                    ).classes("flex-1")
                    post_buffer_input = ui.number(
                        "Post-buffer (giorni)",
                        value=state.market.post_buffer_days,
                        min=0,
                        max=365,
                        step=1,
                    ).classes("flex-1")
                with ui.row().classes("gap-2 items-center mt-1"):
                    ui.label("Preset:").classes("text-caption")

                    def _make_preset_handler(pre: int, post: int, preset_name: str):
                        def _handler():
                            pre_buffer_input.value = pre
                            post_buffer_input.value = post
                            state.market.buffer_preset = preset_name
                        return _handler

                    ui.button("Intraday", on_click=_make_preset_handler(2, 1, "intraday")).props("dense outline")
                    ui.button("Swing", on_click=_make_preset_handler(7, 3, "swing")).props("dense outline")
                    ui.button("Position", on_click=_make_preset_handler(30, 7, "position")).props("dense outline")

            manual_buffer_col.set_visibility(state.market.buffer_mode == "manual")

        # ------------------------------------------------------------------
        # Result badges
        # ------------------------------------------------------------------
        with ui.card().classes("w-full mt-2"):
            ui.label("Stato").classes("text-subtitle2")
            status_label = ui.label("").classes("text-caption text-grey-6")
            summary_label = ui.label("").classes("text-caption text-grey-7")
            data_types_label = ui.label(_selected_data_types_text(state)).classes("text-caption text-grey-7")
            window_summary_label = ui.label("Finestre: in attesa di analisi.").classes("text-caption text-grey-7")
            funding_status_label = ui.label("").classes("text-caption text-grey-6")

            init_status = state.market.market_validation_status
            if init_status in {"validated", "gap_validated"}:
                badge_label = ui.label("READY").classes("text-positive text-body1 font-bold")
            elif init_status == "ready_unvalidated":
                badge_label = ui.label("READY (unvalidated)").classes("text-grey-6 text-body1 font-bold")
            else:
                badge_label = ui.label("NOT READY").classes("text-negative text-body1 font-bold")
            _set_funding_status(
                state=state,
                funding_status_label=funding_status_label,
                status_key=state.market.funding_status,
            )

        # ------------------------------------------------------------------
        # Run section
        # ------------------------------------------------------------------
        with ui.card().classes("w-full mt-2"):
            ui.label("Run").classes("text-subtitle2")
            market_log = LogPanel(title="Log Market DATA")

            def _refresh_data_types_label() -> None:
                active_supported = supported_data_type_labels(state.market.data_types)
                if active_supported:
                    data_types_label.set_text(_selected_data_types_text(state))
                    data_types_label.classes(remove="text-warning")
                    data_types_label.classes(add="text-grey-7")
                else:
                    data_types_label.set_text("Tipi dati attivi: nessuno selezionato")
                    data_types_label.classes(remove="text-grey-7")
                    data_types_label.classes(add="text-warning")

            def _sync_state_from_ui() -> None:
                state.market.market_data_dir = market_dir_input.value.strip()
                selected_download_tfs = [
                    tf_value for tf_value, _ in _TF_OPTIONS if bool(download_tf_toggles[tf_value].value)
                ]
                if not selected_download_tfs:
                    selected_download_tfs = ["1m"]
                state.market.download_tfs = selected_download_tfs
                state.market.download_tf = selected_download_tfs[0]
                state.market.simulation_tf = simulation_tf_select.value or state.market.download_tf
                state.market.detail_tf = detail_tf_select.value or state.market.download_tf
                state.market.price_basis = price_basis_select.value
                state.market.market_data_source = source_select.value
                state.market.market_data_mode = market_mode.value
                state.market.validate_mode = validate_mode_select.value
                state.market.buffer_mode = buffer_mode_radio.value
                state.market.data_types.ohlcv_last = bool(ohlcv_last_toggle.value)
                state.market.data_types.ohlcv_mark = bool(ohlcv_mark_toggle.value)
                state.market.data_types.funding_rate = bool(funding_rate_toggle.value)
                if buffer_mode_radio.value == "manual":
                    state.market.pre_buffer_days = int(pre_buffer_input.value or 0)
                    state.market.post_buffer_days = int(post_buffer_input.value or 0)
                _refresh_data_types_label()

            def _on_inputs_change(*_) -> None:
                _sync_state_from_ui()
                _reset_market_state(
                    state=state,
                    status_label=status_label,
                    badge_label=badge_label,
                    summary_label=summary_label,
                    window_summary_label=window_summary_label,
                    funding_status_label=funding_status_label,
                )
                _refresh_data_types_label()

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
                    run_streaming_command=run_streaming_command,
                )

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
                    run_streaming_command=run_streaming_command,
                )

            async def _on_valida() -> None:
                _sync_state_from_ui()
                await _run_validate_full(
                    state=state,
                    log_panel=market_log,
                    status_label=status_label,
                    badge_label=badge_label,
                    summary_label=summary_label,
                    window_summary_label=window_summary_label,
                    run_streaming_command=run_streaming_command,
                )

            async def _on_prepara_e_valida() -> None:
                _sync_state_from_ui()
                await _run_prepare_and_validate(
                    state=state,
                    db_path=state.effective_db_path(),
                    log_panel=market_log,
                    status_label=status_label,
                    badge_label=badge_label,
                    funding_status_label=funding_status_label,
                    summary_label=summary_label,
                    window_summary_label=window_summary_label,
                    run_streaming_command=run_streaming_command,
                )

            with ui.row().classes("gap-2 mt-2"):
                ui.button("Analizza", on_click=_on_analizza, icon="search", color="secondary").props("dense")
                ui.button("Prepara", on_click=_on_prepara, icon="download", color="primary").props("dense")
                ui.button("Valida", on_click=_on_valida, icon="verified", color="secondary").props("dense")
                ui.button("Prepara + Valida", on_click=_on_prepara_e_valida, icon="done_all").props("dense")

        def _on_buffer_mode_change(*_) -> None:
            manual_buffer_col.set_visibility(buffer_mode_radio.value == "manual")
            _on_inputs_change()

        # Wire up invalidation on input changes
        market_dir_input.on("update:model-value", _on_inputs_change)
        for tf_value, _ in _TF_OPTIONS:
            download_tf_toggles[tf_value].on("update:model-value", _on_inputs_change)
        simulation_tf_select.on("update:model-value", _on_inputs_change)
        detail_tf_select.on("update:model-value", _on_inputs_change)
        price_basis_select.on("update:model-value", _on_inputs_change)
        source_select.on("update:model-value", _on_inputs_change)
        market_mode.on("update:model-value", _on_inputs_change)
        validate_mode_select.on("update:model-value", _on_inputs_change)
        ohlcv_last_toggle.on("update:model-value", _on_inputs_change)
        ohlcv_mark_toggle.on("update:model-value", _on_inputs_change)
        funding_rate_toggle.on("update:model-value", _on_inputs_change)
        buffer_mode_radio.on("update:model-value", _on_buffer_mode_change)
        pre_buffer_input.on("update:model-value", _on_inputs_change)
        post_buffer_input.on("update:model-value", _on_inputs_change)
