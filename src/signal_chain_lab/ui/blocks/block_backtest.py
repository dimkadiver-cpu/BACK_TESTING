"""Blocco 3 - Backtest."""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from nicegui import ui
from src.signal_chain_lab.market.preparation_cache import (
    build_market_request,
    find_pass_validation_record,
    load_validation_index,
    market_request_fingerprint,
    upsert_validation_record,
    validation_index_path,
    save_validation_index,
)

from src.signal_chain_lab.ui.blocks.backtest_support import (
    discover_date_range_from_db,
    discover_policy_names,
    discover_traders_from_db,
    load_policy_yaml,
    save_policy_yaml,
)
from src.signal_chain_lab.ui.blocks.backtest_observability import (
    append_benchmark_entry,
    compute_benchmark_snapshot,
)
from src.signal_chain_lab.ui.components.log_panel import LogPanel
from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SUMMARY_RE = re.compile(
    r"^- (?P<policy>[^:]+): pnl=(?P<pnl>[-+]?\d+(?:\.\d+)?), "
    r"win_rate=(?P<win_rate>[-+]?\d+(?:\.\d+)?%), "
    r"expectancy=(?P<expectancy>[-+]?\d+(?:\.\d+)?), "
    r"trades=(?P<trades>\d+), excluded=(?P<excluded>\d+)"
)
_BENCHMARK_PATH = Path("artifacts/market_data/backtest_benchmark.json")


def _can_enable_backtest(*, db_path: str) -> bool:
    return bool(db_path.strip()) and Path(db_path.strip()).exists()


def _market_plan_summary(plan_path: Path) -> dict[str, int]:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    return {
        "symbols": int(summary.get("symbols", 0)),
        "required_intervals": int(summary.get("required_intervals", 0)),
        "gaps": int(summary.get("gaps", 0)),
    }


def _set_market_status(label, *, text: str, positive: bool | None = None) -> None:
    label.set_text(text)
    label.classes(remove="text-positive text-negative text-grey-6")
    if positive is True:
        label.classes(add="text-positive")
    elif positive is False:
        label.classes(add="text-negative")
    else:
        label.classes(add="text-grey-6")


def _set_market_validation_status(*, state: UiState, status_label, status_key: str) -> None:
    state.market_validation_status = status_key
    if status_key == "validated":
        _set_market_status(status_label, text="Market data validati", positive=True)
    elif status_key == "gap_validated":
        _set_market_status(status_label, text="Market data pronti, gap validati", positive=True)
    elif status_key == "ready_unvalidated":
        _set_market_status(status_label, text="Market data pronti ma non validati in questa run", positive=None)
    else:
        _set_market_status(status_label, text="Market data da verificare", positive=None)


def _invalidate_market_readiness(*, state: UiState, status_label, summary_label) -> None:
    state.market_data_ready = False
    state.market_data_checked = False
    state.market_validation_fingerprint = ""
    state.market_data_gap_count = 0
    state.latest_market_plan_path = ""
    state.latest_market_sync_report_path = ""
    state.latest_market_validation_report_path = ""
    _set_market_validation_status(state=state, status_label=status_label, status_key="needs_check")
    summary_label.set_text(
        "La cartella verra' analizzata prima del backtest. Se mancano intervalli, la GUI eseguira' plan/sync/validate."
    )


async def _browse_backtest_db(output_input) -> None:
    def _pick_file() -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            return ""

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected_file = filedialog.askopenfilename(
                initialdir=str(_PROJECT_ROOT),
                title="Seleziona il DB parsato",
                filetypes=[("SQLite DB", "*.sqlite3 *.db"), ("All files", "*.*")],
            )
        finally:
            root.destroy()
        return selected_file or ""

    selected = await asyncio.to_thread(_pick_file)
    if not selected:
        ui.notify("Selezione file annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()
    if hasattr(output_input, "_after_set"):
        output_input._after_set()


async def _browse_report_dir(output_input) -> None:
    def _pick_directory() -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            return ""

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected_dir = filedialog.askdirectory(
                initialdir=str(_PROJECT_ROOT / "artifacts"),
                title="Seleziona la cartella report output",
                mustexist=False,
            )
        finally:
            root.destroy()
        return selected_dir or ""

    selected = await asyncio.to_thread(_pick_directory)
    if not selected:
        ui.notify("Selezione cartella annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()


async def _browse_market_dir(output_input) -> None:
    def _pick_directory() -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            return ""

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected_dir = filedialog.askdirectory(
                initialdir=str(_PROJECT_ROOT),
                title="Seleziona la cartella market data",
                mustexist=False,
            )
        finally:
            root.destroy()
        return selected_dir or ""

    selected = await asyncio.to_thread(_pick_directory)
    if not selected:
        ui.notify("Selezione cartella annullata.", color="warning")
        return
    output_input.value = selected
    output_input.update()


def _extract_summary_lines(
    log_panel: LogPanel,
) -> tuple[str | None, list[dict[str, str]], str | None]:
    lines = log_panel.lines()
    chains_selected: str | None = None
    summaries: list[dict[str, str]] = []
    html_path: str | None = None
    for line in lines:
        if line.startswith("chains_selected="):
            chains_selected = line.split("=", 1)[1].strip()
            continue
        if line.startswith("scenario_html="):
            html_path = line.split("=", 1)[1].strip()
            continue
        if line.startswith("policy_report_html="):
            html_path = line.split("=", 1)[1].strip()
            continue
        match = _SUMMARY_RE.match(line.strip())
        if match:
            summaries.append(match.groupdict())
    return chains_selected, summaries, html_path


def _build_single_policy_command(*, db_path: str, state: UiState, output_dir: str) -> list[str]:
    import sys

    command = [
        sys.executable,
        "scripts/run_policy_report.py",
        "--policy",
        state.backtest_policies[0],
        "--db-path",
        db_path,
        "--market-dir",
        state.market_data_dir,
        "--price-basis",
        state.price_basis,
        "--timeframe",
        state.timeframe,
    ]
    if state.backtest_trader_filter and state.backtest_trader_filter != "all":
        command += ["--trader-id", state.backtest_trader_filter]
    if state.backtest_date_from:
        command += ["--date-from", state.backtest_date_from]
    if state.backtest_date_to:
        command += ["--date-to", state.backtest_date_to]
    command += ["--output-dir", output_dir]
    return command


def _build_multi_policy_command(*, db_path: str, state: UiState, output_dir: str) -> list[str]:
    import sys

    command = [
        sys.executable,
        "scripts/run_scenario.py",
        "--policies",
        *state.backtest_policies,
        "--db-path",
        db_path,
        "--market-dir",
        state.market_data_dir,
        "--price-basis",
        state.price_basis,
        "--timeframe",
        state.timeframe,
    ]
    if state.backtest_trader_filter and state.backtest_trader_filter != "all":
        command += ["--trader-id", state.backtest_trader_filter]
    if state.backtest_date_from:
        command += ["--date-from", state.backtest_date_from]
    if state.backtest_date_to:
        command += ["--date-to", state.backtest_date_to]
    if state.backtest_max_trades > 0:
        command += ["--max-trades", str(state.backtest_max_trades)]
    command += ["--output-dir", output_dir]
    return command


def _render_backtest_summary(
    *,
    container,
    chains_selected: str | None,
    summaries: list[dict[str, str]],
    artifact_path: str,
    html_path: str | None = None,
) -> None:
    from pathlib import Path as _Path

    with container:
        container.clear()
        with ui.card().classes("w-full"):
            ui.label("Report Backtest").classes("text-subtitle2")
            if chains_selected is not None:
                ui.label(f"Chain selezionate: {chains_selected}")
            if html_path and _Path(html_path).exists():
                ui.link(
                    "Apri report HTML",
                    target=_Path(html_path).resolve().as_uri(),
                    new_tab=True,
                ).classes("text-primary text-caption")
            elif artifact_path:
                ui.label(f"Artifact: {artifact_path}").classes("text-caption text-grey-7")

            if not summaries:
                ui.label("Nessun riepilogo policy trovato nel log.").classes("text-grey-6")
                return

            for item in summaries:
                with ui.card().classes("w-full bg-slate-50"):
                    ui.label(item["policy"]).classes("text-body1")
                    with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-1"):
                        ui.label(f"Trades: {item['trades']}")
                        ui.label(f"Escluse: {item['excluded']}")
                        ui.label(f"PnL: {item['pnl']}")
                        ui.label(f"Win rate: {item['win_rate']}")
                        ui.label(f"Expectancy: {item['expectancy']}")


async def _handle_backtest(
    *,
    state: UiState,
    db_path: str,
    policies: list[str],
    trader_filter: str,
    date_from_str: str,
    date_to_str: str,
    max_trades: int,
    report_dir: str,
    market_data_dir: str,
    timeframe: str,
    price_basis: str,
    timeout_seconds: int,
    prepare_mode: str,
    market_source: str,
    log_panel: LogPanel,
    market_status_label,
    market_summary_label,
    artifact_label,
    summary_container,
    run_streaming_command,
) -> None:
    from datetime import datetime as _dt

    run_t0 = time.perf_counter()
    policies_clean = [p.strip() for p in policies if p.strip()]
    if not policies_clean:
        ui.notify("Seleziona almeno una policy prima del backtest", color="negative")
        return

    # Validate date filters
    date_from_clean = date_from_str.strip()
    date_to_clean = date_to_str.strip()
    if date_from_clean:
        try:
            _dt.fromisoformat(date_from_clean)
        except ValueError:
            ui.notify("Formato 'Dal' non valido: usa YYYY-MM-DD", color="negative")
            return
    if date_to_clean:
        try:
            _dt.fromisoformat(date_to_clean)
        except ValueError:
            ui.notify("Formato 'Al' non valido: usa YYYY-MM-DD", color="negative")
            return
    if date_from_clean and date_to_clean:
        if _dt.fromisoformat(date_from_clean) > _dt.fromisoformat(date_to_clean):
            ui.notify("'Dal' deve essere <= 'Al'", color="negative")
            return

    state.backtest_policies = policies_clean
    state.backtest_trader_filter = trader_filter or "all"
    state.backtest_date_from = date_from_clean
    state.backtest_date_to = date_to_clean
    state.backtest_max_trades = max(0, int(max_trades))
    state.backtest_report_dir = report_dir.strip()
    state.market_data_dir = market_data_dir.strip()
    state.timeframe = timeframe.strip() or "1m"
    state.price_basis = price_basis.strip() or "last"
    state.timeout_seconds = int(timeout_seconds)
    state.market_data_prepare_mode = prepare_mode.strip().upper() or "SAFE"
    state.market_data_source = market_source.strip() or "bybit"
    log_panel.clear()
    summary_container.clear()

    if not db_path.strip():
        ui.notify("Seleziona un DB parsato prima del backtest", color="negative")
        return
    if not state.market_data_dir:
        ui.notify("Seleziona la cartella market data", color="negative")
        return

    if not state.market_data_ready:
        ui.notify("Preparo/verifico prima la cache market data", color="warning")
        market_ready = await _prepare_market_data(
            state=state,
            db_path=db_path,
            market_data_dir=state.market_data_dir,
            timeframe=state.timeframe,
            price_basis=state.price_basis,
            log_panel=log_panel,
            status_label=market_status_label,
            summary_label=market_summary_label,
            run_streaming_command=run_streaming_command,
            silent=False,
            trader_filter=state.backtest_trader_filter,
            date_from=state.backtest_date_from,
            date_to=state.backtest_date_to,
            prepare_mode=state.market_data_prepare_mode,
            market_source=state.market_data_source,
        )
        if not market_ready:
            return

    is_single_policy = len(state.backtest_policies) == 1
    effective_report_dir = state.backtest_report_dir or (
        "artifacts/policy_reports" if is_single_policy else "artifacts/scenarios"
    )
    command = (
        _build_single_policy_command(db_path=db_path, state=state, output_dir=effective_report_dir)
        if is_single_policy
        else _build_multi_policy_command(db_path=db_path, state=state, output_dir=effective_report_dir)
    )
    if is_single_policy:
        log_panel.push(f"--- Backtest single-policy / policy report: {state.backtest_policies[0]} ---")
        log_panel.push("Fase backtest - esecuzione policy report in corso...")
    else:
        log_panel.push(f"--- Backtest multi-policy / comparison report: {', '.join(state.backtest_policies)} ---")
        log_panel.push("Fase backtest - esecuzione scenario in corso...")
    backtest_t0 = time.perf_counter()
    try:
        rc = await asyncio.wait_for(
            run_streaming_command(command, log_panel),
            timeout=state.timeout_seconds,
        )
    except TimeoutError:
        ui.notify("Timeout backtest", color="negative")
        return
    if rc != 0:
        ui.notify("Backtest fallito: controlla log", color="negative")
        return
    backtest_elapsed = time.perf_counter() - backtest_t0

    state.latest_artifact_path = effective_report_dir
    artifact_label.set_text(f"Artifact: {state.latest_artifact_path}")
    chains_selected, summaries, html_path = _extract_summary_lines(log_panel)
    state.latest_html_report_path = html_path or ""
    _render_backtest_summary(
        container=summary_container,
        chains_selected=chains_selected,
        summaries=summaries,
        artifact_path=state.latest_artifact_path,
        html_path=html_path,
    )
    total_elapsed = time.perf_counter() - run_t0
    log_panel.push(f"Timing fase Backtest: {backtest_elapsed:.2f}s")
    log_panel.push(f"Timing run totale: {total_elapsed:.2f}s")
    benchmark_entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "prepare_mode": state.market_data_prepare_mode,
        "policy_count": len(state.backtest_policies),
        "policies": state.backtest_policies,
        "market_validation_status": state.market_validation_status,
        "market_timing_seconds": getattr(state, "market_prepare_total_seconds", 0.0),
        "backtest_seconds": round(backtest_elapsed, 3),
        "total_seconds": round(total_elapsed, 3),
    }
    benchmark_payload = append_benchmark_entry(_BENCHMARK_PATH, benchmark_entry)
    snapshot = compute_benchmark_snapshot(benchmark_payload)
    if snapshot:
        pairs = [f"{k}={v:.2f}s" for k, v in snapshot.items()]
        log_panel.push("Benchmark snapshot: " + ", ".join(pairs))
        log_panel.push(f"Benchmark artifact: {_BENCHMARK_PATH}")
    ui.notify("Backtest completato", color="positive")


async def _prepare_market_data(
    *,
    state: UiState,
    db_path: str,
    market_data_dir: str,
    timeframe: str,
    price_basis: str,
    log_panel: LogPanel,
    status_label,
    summary_label,
    run_streaming_command,
    silent: bool,
    trader_filter: str = "all",
    date_from: str = "",
    date_to: str = "",
    prepare_mode: str = "SAFE",
    market_source: str = "bybit",
) -> bool:
    import sys

    phase_timings: dict[str, float] = {}

    def _mark_phase(name: str, start_time: float) -> None:
        phase_timings[name] = time.perf_counter() - start_time
        log_panel.push(f"Timing fase {name}: {phase_timings[name]:.2f}s")

    prepare_t0 = time.perf_counter()
    db_path = db_path.strip()
    market_root = Path(market_data_dir.strip())
    timeframe = timeframe.strip() or "1m"
    price_basis = price_basis.strip() or "last"
    prepare_mode = (prepare_mode or "SAFE").strip().upper()
    if prepare_mode not in {"SAFE", "FAST"}:
        prepare_mode = "SAFE"
    market_source = (market_source or "bybit").strip() or "bybit"

    if not db_path:
        ui.notify("Seleziona un DB parsato prima di preparare i market data", color="negative")
        return False
    if not market_data_dir.strip():
        ui.notify("Seleziona la cartella market data", color="negative")
        return False
    if not Path(db_path).exists():
        ui.notify("DB parsato non trovato", color="negative")
        return False

    state.market_data_dir = str(market_root)
    state.timeframe = timeframe
    state.price_basis = price_basis
    state.market_data_prepare_mode = prepare_mode
    state.market_data_source = market_source

    if state.market_data_mode == "existing_dir" and not market_root.exists():
        ui.notify("La cartella market data selezionata non esiste", color="negative")
        _set_market_status(status_label, text="Market data non pronti: cartella inesistente", positive=False)
        return False

    market_root.mkdir(parents=True, exist_ok=True)
    mode_label = (
        "usa cartella esistente e integra i gap mancanti"
        if state.market_data_mode == "existing_dir"
        else "prepara da capo in una cartella dedicata"
    )
    active_trader = trader_filter if trader_filter and trader_filter != "all" else None
    active_date_from = date_from.strip() or None
    active_date_to = date_to.strip() or None
    request = build_market_request(
        db_path=db_path,
        market_data_dir=str(market_root),
        trader_filter=active_trader or "all",
        date_from=active_date_from or "",
        date_to=active_date_to or "",
        timeframe=timeframe,
        price_basis=price_basis,
        source=market_source,
    )
    fingerprint = market_request_fingerprint(request)
    index_path = validation_index_path(str(market_root))
    index_payload = load_validation_index(index_path)
    cached_record = find_pass_validation_record(index_payload, fingerprint)
    state.market_validation_fingerprint = fingerprint

    if cached_record:
        log_panel.push("Validation cache hit: riuso validazione PASS già esistente.")
        log_panel.push(f"Validation cache fingerprint={fingerprint}")
        state.market_data_ready = True
        state.market_data_checked = True
        state.latest_market_plan_path = str(cached_record.get("plan_path") or "")
        state.latest_market_sync_report_path = str(cached_record.get("sync_report_path") or "")
        state.latest_market_validation_report_path = str(cached_record.get("validate_report_path") or "")
        state.market_data_gap_count = int((cached_record.get("summary") or {}).get("gaps", 0))
        _set_market_validation_status(state=state, status_label=status_label, status_key="validated")
        state.market_prepare_total_seconds = 0.0
        summary_label.set_text(
            "Validation cache hit: market data già validati e compatibili con la richiesta corrente."
        )
        if not silent:
            ui.notify("Validation cache hit: market data già validati", color="positive")
        return True

    log_panel.push("Fase market 1/4 - Planner: analisi copertura richiesta dal DB.")
    log_panel.push(f"Market data: modalita' selezionata -> {mode_label}.")
    log_panel.push(f"Market data: root locale -> {market_root}")
    log_panel.push(f"Market data: timeframe={timeframe}, basis primaria={price_basis}")
    log_panel.push(f"Market data: source={market_source}")
    log_panel.push(f"Market data: prepare_mode={prepare_mode}, fingerprint={fingerprint}")
    filter_desc = ", ".join(filter(None, [
        f"trader={active_trader}" if active_trader else None,
        f"dal={active_date_from}" if active_date_from else None,
        f"al={active_date_to}" if active_date_to else None,
    ])) or "nessun filtro (tutti i segnali)"
    log_panel.push(f"Market data: filtro applicato al planner -> {filter_desc}")
    _set_market_status(status_label, text="Market data: planner in esecuzione...", positive=None)

    plan_path = Path("artifacts/market_data/plan_market_data.json")
    sync_path = Path("artifacts/market_data/sync_market_data.json")
    gap_validate_path = Path("artifacts/market_data/gap_validate_market_data.json")
    validate_path = Path("artifacts/market_data/validate_market_data.json")

    plan_command = [
        sys.executable,
        "scripts/plan_market_data.py",
        "--db-path",
        db_path,
        "--market-dir",
        str(market_root),
        "--timeframe",
        timeframe,
        "--bases",
        "last,mark",
        "--source",
        market_source,
        "--output",
        str(plan_path),
    ]
    if active_trader:
        plan_command += ["--trader-id", active_trader]
    if active_date_from:
        plan_command += ["--date-from", active_date_from]
    if active_date_to:
        plan_command += ["--date-to", active_date_to]
    planner_t0 = time.perf_counter()
    rc = await run_streaming_command(plan_command, log_panel)
    if rc != 0 or not plan_path.exists():
        ui.notify("Planner market data fallito", color="negative")
        _set_market_status(status_label, text="Market data: planner fallito", positive=False)
        return False

    _mark_phase("Planner", planner_t0)
    plan_summary = _market_plan_summary(plan_path)
    state.latest_market_plan_path = str(plan_path)
    state.market_data_gap_count = plan_summary["gaps"]
    log_panel.push(
        "Fase market 1/4 - Planner: completata. "
        f"simboli={plan_summary['symbols']}, intervalli={plan_summary['required_intervals']}, gap={plan_summary['gaps']}."
    )
    log_panel.push(f"Artifact planner: {plan_path}")
    summary_label.set_text(
        f"Planner: simboli={plan_summary['symbols']}, intervalli={plan_summary['required_intervals']}, gap={plan_summary['gaps']}."
    )

    if plan_summary["gaps"] > 0:
        log_panel.push("Fase market 2/4 - Sync: avvio integrazione gap mancanti.")
        log_panel.push(
            f"Market data: trovati {plan_summary['gaps']} gap. Avvio sync incrementale sulla cache locale."
        )
        _set_market_status(status_label, text="Market data: sync gap mancanti...", positive=None)
        sync_command = [
            sys.executable,
            "scripts/sync_market_data.py",
            "--plan-file",
            str(plan_path),
            "--db-path",
            db_path,
            "--market-dir",
            str(market_root),
            "--output",
            str(sync_path),
            "--source",
            market_source,
        ]
        sync_t0 = time.perf_counter()
        rc = await run_streaming_command(sync_command, log_panel)
        if rc != 0 or not sync_path.exists():
            ui.notify("Sync market data fallito", color="negative")
            _set_market_status(status_label, text="Market data: sync fallito", positive=False)
            return False
        _mark_phase("Sync", sync_t0)
        state.latest_market_sync_report_path = str(sync_path)
        log_panel.push(f"Fase market 2/4 - Sync: completata. Artifact sync: {sync_path}")

        log_panel.push("Fase market 3/4 - Gap Validation: verifica mirata dei gap sincronizzati.")
        _set_market_status(status_label, text="Market data: gap validation in corso...", positive=None)
        gap_validate_command = [
            sys.executable,
            "scripts/gap_validate_market_data.py",
            "--plan-file",
            str(plan_path),
            "--sync-file",
            str(sync_path),
            "--market-dir",
            str(market_root),
            "--output",
            str(gap_validate_path),
        ]
        gap_validate_t0 = time.perf_counter()
        rc = await run_streaming_command(gap_validate_command, log_panel)
        if rc != 0 or not gap_validate_path.exists():
            ui.notify("Gap validation market data fallita", color="negative")
            _set_market_status(status_label, text="Market data: gap validation fallita", positive=False)
            return False
        _mark_phase("Gap Validation", gap_validate_t0)
        log_panel.push(f"Fase market 3/4 - Gap Validation: completata. Artifact gap validation: {gap_validate_path}")
    else:
        log_panel.push("Fase market 2/4 - Sync: nessun gap trovato, step saltato.")
        log_panel.push("Market data: nessun gap trovato, sync non necessario.")
        log_panel.push("Fase market 3/4 - Gap Validation: nessun gap sincronizzato, step saltato.")

    if prepare_mode == "FAST":
        log_panel.push("FAST mode: validate full saltata (gap validation già eseguita se necessaria).")
        state.latest_market_validation_report_path = ""
        state.market_data_ready = True
        state.market_data_checked = False
        _set_market_validation_status(state=state, status_label=status_label, status_key="ready_unvalidated")
        state.market_prepare_total_seconds = round(time.perf_counter() - prepare_t0, 3)
        log_panel.push(f"Timing prepare market totale: {state.market_prepare_total_seconds:.2f}s")
        summary_label.set_text(
            "FAST mode: planner/sync/gap validation eseguiti, validate full saltata in questa run."
        )
        log_panel.push("Market data: cache pronta per il backtest (senza validazione in questa run).")
        if not silent:
            ui.notify("FAST mode: market data pronti senza validazione", color="warning")
        return True

    log_panel.push("Fase market 4/4 - Validate: verifica consistenza cache locale.")
    _set_market_status(status_label, text="Market data: validazione in corso...", positive=None)
    validate_command = [
        sys.executable,
        "scripts/validate_market_data.py",
        "--plan-file",
        str(plan_path),
        "--market-dir",
        str(market_root),
        "--output",
        str(validate_path),
    ]
    validate_t0 = time.perf_counter()
    rc = await run_streaming_command(validate_command, log_panel)
    if rc != 0 or not validate_path.exists():
        ui.notify("Validazione market data fallita", color="negative")
        _set_market_status(status_label, text="Market data: validazione fallita", positive=False)
        upsert_validation_record(
            index_payload=index_payload,
            request=request,
            fingerprint=fingerprint,
            status="FAIL",
            plan_path=str(plan_path),
            sync_report_path=str(sync_path) if sync_path.exists() else "",
            validate_report_path=str(validate_path) if validate_path.exists() else "",
            summary=plan_summary,
        )
        save_validation_index(index_path, index_payload)
        return False

    state.latest_market_validation_report_path = str(validate_path)
    log_panel.push(f"Fase market 4/4 - Validate: completata. Artifact validate: {validate_path}")
    state.market_data_ready = True
    state.market_data_checked = True
    if plan_summary["gaps"] > 0:
        _set_market_validation_status(state=state, status_label=status_label, status_key="gap_validated")
    else:
        _set_market_validation_status(state=state, status_label=status_label, status_key="validated")

    upsert_validation_record(
        index_payload=index_payload,
        request=request,
        fingerprint=fingerprint,
        status="PASS",
        plan_path=str(plan_path),
        sync_report_path=str(sync_path) if sync_path.exists() else "",
        validate_report_path=str(validate_path),
        summary=plan_summary,
    )
    save_validation_index(index_path, index_payload)
    log_panel.push(f"Validation index aggiornato: {index_path}")
    state.market_prepare_total_seconds = round(time.perf_counter() - prepare_t0, 3)
    log_panel.push(f"Timing prepare market totale: {state.market_prepare_total_seconds:.2f}s")

    summary_label.set_text(
        "Artifacts market data: "
        f"plan={state.latest_market_plan_path}, "
        f"sync={state.latest_market_sync_report_path or '-'}, "
        f"validate={state.latest_market_validation_report_path}"
    )
    log_panel.push("Market data: cache pronta per il backtest.")
    if not silent:
        ui.notify("Market data pronti per il backtest", color="positive")
    return True


def render_block_backtest(
    state: UiState,
    *,
    backtest_button_holder: list,
    run_streaming_command,
) -> None:
    """Renderizza il Blocco 3 - Backtest."""
    with ui.card().classes("w-full"):
        ui.label("Blocco 3 - Backtest").classes("text-h6")

        with ui.row().classes("w-full items-end gap-2"):
            backtest_db = ui.input("DB parsato", value=state.effective_db_path()).classes("flex-1")
            db_status = ui.label("").classes("text-caption")

            async def _on_browse_backtest_db() -> None:
                await _browse_backtest_db(backtest_db)

            ui.button("Sfoglia", on_click=_on_browse_backtest_db, icon="folder_open")

        # --- Policy selector (Fase 1: dinamico da configs/policies/) ---
        def _build_policy_options() -> dict[str, str]:
            names = discover_policy_names()
            return {n: n for n in names}

        with ui.row().classes("w-full items-center gap-2"):
            ui.label("Policy da eseguire").classes("text-caption text-grey-8")
            ui.button(
                "Ricarica", icon="refresh", color="secondary",
                on_click=lambda: _on_reload_policies(),
            ).props("dense flat")
            ui.button(
                "Modifica", icon="edit", color="secondary",
                on_click=lambda: _on_edit_policy(),
            ).props("dense flat")
            ui.button(
                "Nuova", icon="add", color="secondary",
                on_click=lambda: _on_new_policy(),
            ).props("dense flat")

        policy_select = ui.select(
            options=_build_policy_options(),
            value=[p for p in state.backtest_policies if p in _build_policy_options()],
            label="Policy",
            multiple=True,
        ).classes("w-full")
        ui.label(
            "Seleziona una o piu' policy. Se ne scegli più di una, il confronto viene eseguito in un unico run."
        ).classes("text-caption text-grey-6")

        def _on_reload_policies() -> None:
            opts = _build_policy_options()
            policy_select.options = opts
            current = policy_select.value if isinstance(policy_select.value, list) else []
            policy_select.value = [v for v in current if v in opts] or list(opts.keys())[:2]
            policy_select.update()
            ui.notify(f"Policy ricaricate: {len(opts)} trovate", color="info")

        def _on_edit_policy() -> None:
            selected = policy_select.value if isinstance(policy_select.value, list) else []
            if not selected:
                ui.notify("Seleziona almeno una policy da modificare", color="warning")
                return
            policy_to_edit = selected[0]
            content = load_policy_yaml(policy_to_edit)
            if not content:
                ui.notify(f"File YAML per '{policy_to_edit}' non trovato", color="warning")
                return

            with ui.dialog() as dlg, ui.card().classes("min-w-[640px] w-full"):
                ui.label(f"Editor policy: {policy_to_edit}").classes("text-subtitle2")
                editor = ui.textarea(value=content).classes("w-full font-mono").style(
                    "height:420px; font-size:12px; white-space:pre"
                )

                def _save_overwrite() -> None:
                    try:
                        import yaml as _yaml
                        _yaml.safe_load(editor.value)
                    except Exception as exc:
                        ui.notify(f"YAML non valido: {exc}", color="negative")
                        return
                    save_policy_yaml(policy_to_edit, editor.value)
                    ui.notify(f"Policy '{policy_to_edit}' salvata", color="positive")
                    dlg.close()

                def _open_save_as_dialog() -> None:
                    with ui.dialog() as dlg2, ui.card():
                        ui.label("Salva come nuova policy").classes("text-subtitle2")
                        name_input = ui.input(
                            "Nome policy (es. be_after_tp2)",
                            placeholder="solo lettere, cifre, _ e -",
                        ).classes("w-full")

                        def _confirm_save_as() -> None:
                            import re as _re
                            new_name = name_input.value.strip()
                            if not new_name:
                                ui.notify("Inserisci un nome", color="warning")
                                return
                            if not _re.match(r'^[a-z][a-z0-9_-]*$', new_name):
                                ui.notify(
                                    "Nome non valido: usa solo lettere minuscole, cifre, _ e -",
                                    color="warning",
                                )
                                return
                            try:
                                import yaml as _yaml
                                _yaml.safe_load(editor.value)
                            except Exception as exc:
                                ui.notify(f"YAML non valido: {exc}", color="negative")
                                return
                            path = save_policy_yaml(new_name, editor.value)
                            ui.notify(f"Policy '{new_name}' salvata in {path}", color="positive")
                            dlg2.close()
                            dlg.close()
                            _on_reload_policies()

                        with ui.row():
                            ui.button("Salva", on_click=_confirm_save_as)
                            ui.button("Annulla", on_click=dlg2.close)
                    dlg2.open()

                with ui.row().classes("gap-2 mt-2"):
                    ui.button("Salva", on_click=_save_overwrite)
                    ui.button("Salva come nuova...", on_click=_open_save_as_dialog)
                    ui.button("Chiudi", on_click=dlg.close)
            dlg.open()

        def _on_new_policy() -> None:
            template_names = discover_policy_names()
            template_content = load_policy_yaml(template_names[0]) if template_names else ""

            with ui.dialog() as dlg, ui.card().classes("min-w-[640px] w-full"):
                ui.label("Nuova policy").classes("text-subtitle2")
                name_input = ui.input(
                    "Nome policy (es. my_custom)",
                    placeholder="solo lettere, cifre, _ e -",
                ).classes("w-full")
                editor = ui.textarea(value=template_content).classes("w-full font-mono").style(
                    "height:400px; font-size:12px; white-space:pre"
                )

                def _save_new() -> None:
                    import re as _re
                    new_name = name_input.value.strip()
                    if not new_name:
                        ui.notify("Inserisci un nome", color="warning")
                        return
                    if not _re.match(r'^[a-z][a-z0-9_-]*$', new_name):
                        ui.notify(
                            "Nome non valido: usa solo lettere minuscole, cifre, _ e -",
                            color="warning",
                        )
                        return
                    try:
                        import yaml as _yaml
                        _yaml.safe_load(editor.value)
                    except Exception as exc:
                        ui.notify(f"YAML non valido: {exc}", color="negative")
                        return
                    path = save_policy_yaml(new_name, editor.value)
                    ui.notify(f"Policy '{new_name}' salvata in {path}", color="positive")
                    dlg.close()
                    _on_reload_policies()

                with ui.row().classes("gap-2 mt-2"):
                    ui.button("Salva nuova policy", on_click=_save_new)
                    ui.button("Annulla", on_click=dlg.close)
            dlg.open()
        # --- fine sezione policy ---

        # ---- Filtri dataset (Fase 2+3) ----
        def _refresh_trader_select(db_path: str) -> None:
            db_path = db_path.strip()
            traders = discover_traders_from_db(db_path)
            opts: dict[str, str] = {"all": "Tutti i trader"}
            opts.update({t: t for t in traders})
            trader_select.options = opts
            if trader_select.value not in opts:
                trader_select.value = "all"
            trader_hint.set_text(
                f"{len(traders)} trader trovati" if traders else "Nessun trader rilevato"
            )
            trader_select.update()

            # Popola date estreme rilevate nel DB
            min_date, max_date = discover_date_range_from_db(db_path)
            if min_date and not date_from_input.value:
                date_from_input.value = min_date
                date_from_input.update()
            if max_date and not date_to_input.value:
                date_to_input.value = max_date
                date_to_input.update()

        with ui.expansion("Filtri dataset", icon="filter_list").classes("w-full"):
            with ui.row().classes("w-full gap-4 items-end"):
                trader_select = ui.select(
                    options={"all": "Tutti i trader"},
                    value=state.backtest_trader_filter or "all",
                    label="Trader",
                ).classes("flex-1")
                trader_hint = ui.label("").classes("text-caption text-grey-6 self-center")
                ui.button(
                    "Rileva",
                    icon="search",
                    color="secondary",
                    on_click=lambda: _refresh_trader_select(backtest_db.value),
                ).props("dense flat")

            with ui.row().classes("w-full gap-4 mt-2"):
                date_from_input = ui.input(
                    "Dal (YYYY-MM-DD)", value=state.backtest_date_from,
                    placeholder="es. 2024-01-01",
                ).classes("flex-1")
                date_to_input = ui.input(
                    "Al (YYYY-MM-DD)", value=state.backtest_date_to,
                    placeholder="es. 2024-12-31",
                ).classes("flex-1")
                max_trades_input = ui.number(
                    "Max trade (0 = tutti)", value=state.backtest_max_trades, min=0, step=10,
                ).classes("flex-1")

            ui.label(
                "Campi vuoti = nessun filtro (usa tutti i trade). "
                "Max trade = 0 significa nessun limite."
            ).classes("text-caption text-grey-6 mt-1")
        # ---- fine filtri dataset ----

        with ui.row().classes("w-full items-end gap-2"):
            market_data_dir = ui.input("Cartella market data", value=state.market_data_dir).classes("flex-1")

            async def _on_browse_market_dir() -> None:
                await _browse_market_dir(market_data_dir)

            ui.button("Sfoglia", on_click=_on_browse_market_dir, icon="folder_open")

        market_data_mode = ui.radio(
            {
                "existing_dir": "Usa cartella esistente e integra i gap mancanti",
                "new_dir": "Prepara da capo in una nuova cartella",
            },
            value=state.market_data_mode,
        ).props("inline")
        market_mode_hint = ui.label("").classes("text-caption text-grey-7")
        market_status = ui.label("").classes("text-caption text-grey-6")
        market_summary = ui.label("").classes("text-caption text-grey-7")

        with ui.row().classes("w-full gap-4"):
            timeframe = ui.input("Timeframe (es. 1m)", value=state.timeframe).classes("flex-1")
            price_basis = ui.select(
                options={"last": "last (standard)", "mark": "mark (mark price)"},
                value=state.price_basis,
                label="Price basis",
            ).classes("flex-1")
            market_source = ui.select(
                options={"bybit": "bybit", "fixture": "fixture"},
                value=state.market_data_source,
                label="Market source",
            ).classes("flex-1")
            timeout_seconds = ui.number("Timeout (s)", value=state.timeout_seconds, min=5, step=5).classes("flex-1")
        market_prepare_mode = ui.radio(
            {"SAFE": "SAFE (planner+sync+validate con cache)", "FAST": "FAST (planner+sync, validate opzionale)"},
            value=state.market_data_prepare_mode,
        ).props("inline")

        # --- Report output dir (Fase 4) ---
        with ui.row().classes("w-full items-end gap-2"):
            report_dir_input = ui.input(
                "Cartella report output",
                value=state.backtest_report_dir,
                placeholder="default: artifacts/scenarios",
            ).classes("flex-1")
            ui.label("Lascia vuoto per usare la cartella di default (artifacts/scenarios).").classes(
                "text-caption text-grey-6 self-center"
            )

            async def _on_browse_report_dir() -> None:
                await _browse_report_dir(report_dir_input)

            ui.button("Sfoglia", on_click=_on_browse_report_dir, icon="folder_open")
        # --- fine report output dir ---

        block3_log = LogPanel(title="Log Backtest")
        artifact_label = ui.label(f"Artifact: {state.latest_artifact_path or '-'}")
        summary_container = ui.column().classes("w-full")

        async def _on_backtest_click() -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            if resolved_db_path != backtest_db.value:
                backtest_db.value = resolved_db_path
                backtest_db.update()
                _refresh_backtest_button()
            selected_policies = (
                policy_select.value
                if isinstance(policy_select.value, list)
                else ([policy_select.value] if policy_select.value else [])
            )
            await _handle_backtest(
                state=state,
                db_path=resolved_db_path,
                policies=selected_policies,
                trader_filter=trader_select.value or "all",
                date_from_str=date_from_input.value,
                date_to_str=date_to_input.value,
                max_trades=int(max_trades_input.value or 0),
                report_dir=report_dir_input.value,
                market_data_dir=market_data_dir.value,
                timeframe=timeframe.value,
                price_basis=price_basis.value,
                timeout_seconds=int(timeout_seconds.value),
                prepare_mode=market_prepare_mode.value,
                market_source=market_source.value,
                log_panel=block3_log,
                market_status_label=market_status,
                market_summary_label=market_summary,
                artifact_label=artifact_label,
                summary_container=summary_container,
                run_streaming_command=run_streaming_command,
            )

        async def _on_prepare_market_data() -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            if resolved_db_path != backtest_db.value:
                backtest_db.value = resolved_db_path
                backtest_db.update()
            block3_log.clear()
            summary_container.clear()
            ready = await _prepare_market_data(
                state=state,
                db_path=resolved_db_path,
                market_data_dir=market_data_dir.value,
                timeframe=timeframe.value,
                price_basis=price_basis.value,
                log_panel=block3_log,
                status_label=market_status,
                summary_label=market_summary,
                run_streaming_command=run_streaming_command,
                silent=False,
                trader_filter=trader_select.value or "all",
                date_from=date_from_input.value,
                date_to=date_to_input.value,
                prepare_mode=market_prepare_mode.value,
                market_source=market_source.value,
            )
            if ready:
                _refresh_backtest_button()

        def _refresh_market_mode_hint(*_) -> None:
            state.market_data_mode = market_data_mode.value
            if market_data_mode.value == "existing_dir":
                market_mode_hint.set_text(
                    "La cartella indicata viene controllata contro il DB; se mancano periodi, la GUI li aggiunge prima del run."
                )
            else:
                market_mode_hint.set_text(
                    "La cartella puo' essere nuova o vuota: il planner costruisce la cache richiesta dal DB e poi la valida."
                )
            _invalidate_market_readiness(state=state, status_label=market_status, summary_label=market_summary)
            _refresh_backtest_button()

        def _on_market_inputs_change(*_) -> None:
            _invalidate_market_readiness(state=state, status_label=market_status, summary_label=market_summary)
            _refresh_backtest_button()

        def _refresh_backtest_button(*_) -> None:
            resolved_db_path = backtest_db.value.strip() or state.effective_db_path()
            has_market_dir = bool(market_data_dir.value.strip())
            if _can_enable_backtest(db_path=resolved_db_path) and has_market_dir:
                db_status.set_text("DB valido")
                db_status.classes(remove="text-negative text-grey-6")
                db_status.classes(add="text-positive")
                run_backtest_button.enable()
            elif _can_enable_backtest(db_path=resolved_db_path) and not has_market_dir:
                db_status.set_text("DB valido ma cartella market data non selezionata")
                db_status.classes(remove="text-positive")
                db_status.classes(add="text-negative")
                run_backtest_button.disable()
            else:
                db_status.set_text("DB non trovato o non selezionato")
                db_status.classes(remove="text-positive")
                db_status.classes(add="text-negative")
                run_backtest_button.disable()

        run_backtest_button = ui.button("Esegui Backtest", on_click=_on_backtest_click)
        ui.button("Prepara / verifica market data", on_click=_on_prepare_market_data, color="secondary")

        def _on_db_path_change(*_) -> None:
            _invalidate_market_readiness(state=state, status_label=market_status, summary_label=market_summary)
            _refresh_backtest_button()
            _refresh_trader_select(backtest_db.value.strip() or state.effective_db_path())

        backtest_db._after_set = _on_db_path_change
        backtest_db.on("update:model-value", _on_db_path_change)
        market_data_dir.on("update:model-value", _on_market_inputs_change)
        timeframe.on("update:model-value", _on_market_inputs_change)
        price_basis.on("update:model-value", _on_market_inputs_change)
        market_source.on("update:model-value", _on_market_inputs_change)
        market_prepare_mode.on("update:model-value", _on_market_inputs_change)
        market_data_mode.on("update:model-value", _refresh_market_mode_hint)
        _refresh_market_mode_hint()
        _refresh_backtest_button()
        # Pre-populate trader selector if state already has a valid DB path
        if state.db_exists():
            _refresh_trader_select(state.effective_db_path())

    backtest_button_holder.append(run_backtest_button)
    _mark_phase("Validate full", validate_t0)
