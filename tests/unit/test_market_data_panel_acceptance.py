from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

import pytest

from src.signal_chain_lab.ui.blocks.backtest_support import market_backtest_gate
from src.signal_chain_lab.ui.blocks import market_data_panel as panel
from src.signal_chain_lab.ui.state import UiState


class DummyLabel:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def set_text(self, text: str) -> None:
        self.text = text

    def classes(self, *args, **kwargs):  # noqa: ANN001, ANN002
        return self


class DummyLogPanel:
    def __init__(self) -> None:
        self._lines: list[str] = []

    def clear(self) -> None:
        self._lines.clear()

    def push(self, line: str) -> None:
        self._lines.append(line)

    def lines(self) -> list[str]:
        return list(self._lines)


def _make_state(tmp_path: Path, *, validate_mode: str) -> UiState:
    state = UiState()
    state.market.market_data_mode = "new_dir"
    state.market.market_data_dir = str(tmp_path / "market")
    state.market.validate_mode = validate_mode
    state.market.download_tfs = ["1m", "15m"]
    state.market.download_tf = "1m"
    state.market.simulation_tf = "15m"
    state.market.detail_tf = "1m"
    state.market.market_data_source = "bybit"
    state.market.data_types.ohlcv_last = True
    state.market.data_types.ohlcv_mark = False
    state.market.data_types.funding_rate = False
    state.parsed_db_path = str(tmp_path / "parsed.sqlite3")
    Path(state.parsed_db_path).write_text("db", encoding="utf-8")
    return state


def _plan_payload(*, unsupported: list[str] | None = None) -> dict[str, object]:
    return {
        "summary": {
            "symbols": 2,
            "symbols_with_gaps": 1,
            "symbols_complete": 1,
            "required_intervals": 3,
            "gaps": 1,
            "gaps_by_timeframe": {"1m": 1, "15m": 0},
        },
        "download_tfs": ["1m", "15m"],
        "simulation_tf": "15m",
        "detail_tf": "1m",
        "requested_data_types": {
            "ohlcv_last": True,
            "ohlcv_mark": False,
            "funding_rate": False,
        },
        "potentially_unsupported_symbols": unsupported or [],
        "window_preview": "Finestre: BTCUSDT: exec=1 chart=1 download=1",
        "symbols": {
            "BTCUSDT": {
                "last": {
                    "execution_window": [{"start": "2026-04-18T10:00:00+00:00", "end": "2026-04-18T10:01:00+00:00"}],
                    "chart_window": [{"start": "2026-04-18T09:00:00+00:00", "end": "2026-04-18T10:01:00+00:00"}],
                    "download_window": [{"start": "2026-04-18T09:00:00+00:00", "end": "2026-04-18T10:01:00+00:00"}],
                }
            }
        },
    }


def _sync_payload(*, unsupported: list[str] | None = None) -> dict[str, object]:
    return {
        "results": [
            {
                "symbol": "BTCUSDT",
                "basis": "last",
                "timeframe": "1m",
                "status": "ok",
                "reason_code": "ok",
            }
        ],
        "unsupported_symbols": unsupported or [],
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_runner(
    *,
    plan_payload: dict[str, object] | None = None,
    sync_payload: dict[str, object] | None = None,
) -> tuple[list[list[str]], Callable[[list[str], object], asyncio.Future]]:
    calls: list[list[str]] = []

    async def _runner(command, log_panel):  # noqa: ANN001, ANN202
        calls.append(list(command))
        output_path = None
        if "--output" in command:
            output_path = Path(command[command.index("--output") + 1])
        if command[1].endswith("plan_market_data.py"):
            _write_json(output_path, plan_payload or _plan_payload())
        elif command[1].endswith("sync_market_data.py"):
            _write_json(output_path, sync_payload or _sync_payload())
        elif command[1].endswith("gap_validate_market_data.py"):
            _write_json(output_path, {"status": "PASS", "summary": {"passed": 1, "failed": 0}})
        elif command[1].endswith("validate_market_data.py"):
            _write_json(output_path, {"status": "PASS", "summary": {"passed": 1, "failed": 0}})
        return 0

    return calls, _runner


def _script_name(call: list[str]) -> str:
    return Path(call[1]).name


def _dummy_labels() -> dict[str, DummyLabel]:
    return {
        "status": DummyLabel(),
        "badge": DummyLabel(),
        "funding": DummyLabel(),
        "summary": DummyLabel(),
        "window": DummyLabel(),
        "artifact": DummyLabel(),
    }


def _dummy_backtest_holder() -> list:
    class _Button:
        def __init__(self) -> None:
            self.enabled = False

        def enable(self) -> None:
            self.enabled = True

        def disable(self) -> None:
            self.enabled = False

    return [_Button()]


@pytest.mark.asyncio
async def test_prepare_off_skips_validation_and_sets_ready_unvalidated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(panel.ui, "notify", lambda *args, **kwargs: None)
    state = _make_state(tmp_path, validate_mode="off")
    labels = _dummy_labels()
    log_panel = DummyLogPanel()
    calls, runner = _make_runner()
    holder = _dummy_backtest_holder()

    result = await panel._run_prepare(
        state=state,
        db_path=state.effective_db_path(),
        log_panel=log_panel,
        status_label=labels["status"],
        badge_label=labels["badge"],
        funding_status_label=labels["funding"],
        summary_label=labels["summary"],
        window_summary_label=labels["window"],
        backtest_button_holder=holder,
        run_streaming_command=runner,
    )

    assert result is True
    assert state.market.market_validation_status == "ready_unvalidated"
    assert state.market.market_ready is True
    assert state.market.analysis_ready is False
    assert any(_script_name(call) == "plan_market_data.py" for call in calls)
    assert any(_script_name(call) == "sync_market_data.py" for call in calls)
    assert not any(_script_name(call) == "validate_market_data.py" for call in calls)
    assert not any(_script_name(call) == "gap_validate_market_data.py" for call in calls)


@pytest.mark.asyncio
async def test_prepare_and_validate_off_is_identical_to_prepare(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(panel.ui, "notify", lambda *args, **kwargs: None)
    state = _make_state(tmp_path, validate_mode="off")
    labels = _dummy_labels()
    log_panel = DummyLogPanel()
    calls, runner = _make_runner()
    holder = _dummy_backtest_holder()

    result = await panel._run_prepare_and_validate(
        state=state,
        db_path=state.effective_db_path(),
        log_panel=log_panel,
        status_label=labels["status"],
        badge_label=labels["badge"],
        funding_status_label=labels["funding"],
        summary_label=labels["summary"],
        window_summary_label=labels["window"],
        backtest_button_holder=holder,
        run_streaming_command=runner,
    )

    assert result is True
    assert state.market.market_validation_status == "ready_unvalidated"
    assert state.market.market_ready is True
    assert not any(_script_name(call) == "validate_market_data.py" for call in calls)
    assert not any(_script_name(call) == "gap_validate_market_data.py" for call in calls)


@pytest.mark.asyncio
async def test_prepare_light_runs_gap_validation_but_not_full_validate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(panel.ui, "notify", lambda *args, **kwargs: None)
    state = _make_state(tmp_path, validate_mode="light")
    labels = _dummy_labels()
    log_panel = DummyLogPanel()
    calls, runner = _make_runner()
    holder = _dummy_backtest_holder()

    result = await panel._run_prepare(
        state=state,
        db_path=state.effective_db_path(),
        log_panel=log_panel,
        status_label=labels["status"],
        badge_label=labels["badge"],
        funding_status_label=labels["funding"],
        summary_label=labels["summary"],
        window_summary_label=labels["window"],
        backtest_button_holder=holder,
        run_streaming_command=runner,
    )

    assert result is True
    assert state.market.market_validation_status == "ready_unvalidated"
    assert any(_script_name(call) == "gap_validate_market_data.py" for call in calls)
    assert not any(_script_name(call) == "validate_market_data.py" for call in calls)


@pytest.mark.asyncio
async def test_prepare_and_validate_full_runs_full_validation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(panel.ui, "notify", lambda *args, **kwargs: None)
    state = _make_state(tmp_path, validate_mode="full")
    labels = _dummy_labels()
    log_panel = DummyLogPanel()
    calls, runner = _make_runner()
    holder = _dummy_backtest_holder()

    result = await panel._run_prepare_and_validate(
        state=state,
        db_path=state.effective_db_path(),
        log_panel=log_panel,
        status_label=labels["status"],
        badge_label=labels["badge"],
        funding_status_label=labels["funding"],
        summary_label=labels["summary"],
        window_summary_label=labels["window"],
        backtest_button_holder=holder,
        run_streaming_command=runner,
    )

    assert result is True
    assert state.market.market_validation_status == "validated"
    assert state.market.market_ready is True
    assert any(_script_name(call) == "gap_validate_market_data.py" for call in calls)
    assert any(_script_name(call) == "validate_market_data.py" for call in calls)


def test_analyze_warns_on_potentially_unsupported_symbols(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    warnings: list[str] = []
    monkeypatch.setattr(panel.ui, "notify", lambda message, color=None: warnings.append(message))
    state = _make_state(tmp_path, validate_mode="light")
    labels = _dummy_labels()
    log_panel = DummyLogPanel()
    calls, runner = _make_runner(plan_payload=_plan_payload(unsupported=["FAKESYM"]))
    holder = _dummy_backtest_holder()

    asyncio.run(
        panel._run_analyze(
            state=state,
            db_path=state.effective_db_path(),
            log_panel=log_panel,
            status_label=labels["status"],
            badge_label=labels["badge"],
            summary_label=labels["summary"],
            window_summary_label=labels["window"],
            backtest_button_holder=holder,
            run_streaming_command=runner,
        )
    )

    assert state.market.analysis_ready is True
    assert "Potenzialmente non supportati: FAKESYM" in labels["summary"].text
    assert any("Simboli potenzialmente non supportati" in line for line in log_panel.lines())
    assert any("Analisi completata" in message for message in warnings)
    assert any(_script_name(call) == "plan_market_data.py" for call in calls)


def test_market_backtest_gate_acceptance_cases() -> None:
    state = UiState()

    state.market.market_validation_status = "needs_check"
    allowed, message, style = market_backtest_gate(state)
    assert allowed is False
    assert "analisi mancante" in message
    assert style == "error"

    plan_path = Path("artifacts/market_data/plan_market_data.json")
    _write_json(plan_path, _plan_payload())
    state.market.latest_market_plan_path = str(plan_path)
    state.market.market_data_gap_count = 1

    state.market.market_validation_status = "validated"
    allowed, message, style = market_backtest_gate(state)
    assert allowed is True
    assert "Copertura dataset: 50.0%" in message
    assert style == "warning"

    state.market.market_validation_status = "ready_unvalidated"
    state.market.validate_mode = "off"
    allowed, message, style = market_backtest_gate(state)
    assert allowed is True
    assert "run consentito con warning" in message
    assert style == "warning"
