from __future__ import annotations

import json
from pathlib import Path

from src.signal_chain_lab.ui import persistence
from src.signal_chain_lab.ui.state import UiState


def test_save_and_load_ui_state_roundtrip(tmp_path: Path, monkeypatch) -> None:
    state_file = tmp_path / "ui_state.json"
    monkeypatch.setattr(persistence, "get_state_path", lambda: state_file)

    payload = {
        "active_tab": "backtest",
        "parsed_db_path": "parser_test/db/session.sqlite3",
        "market": {
            "market_data_dir": "data/market_NEW",
            "download_tf": "15m",
            "simulation_tf": "1h",
            "detail_tf": "15m",
            "validate_mode": "off",
            "new_dir_enabled": True,
            "new_dir_path": "data/market_NEW",
            "buffer_mode": "manual",
            "pre_buffer_days": 4,
            "post_buffer_days": 2,
            "download_tfs": ["15m", "1h"],
            "data_types": {
                "ohlcv_last": False,
                "ohlcv_mark": True,
                "funding_rate": True,
                "perp": True,
                "spot": False,
                "funding": True,
            },
        },
    }

    persistence.save_ui_state(payload)

    assert state_file.exists()
    assert persistence.load_ui_state() == payload


def test_load_ui_state_returns_empty_dict_for_malformed_json(tmp_path: Path, monkeypatch) -> None:
    state_file = tmp_path / "ui_state.json"
    state_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(persistence, "get_state_path", lambda: state_file)

    assert persistence.load_ui_state() == {}


def test_ui_state_apply_saved_and_validate_paths(tmp_path: Path) -> None:
    existing_db = tmp_path / "signals.sqlite3"
    existing_db.write_text("db", encoding="utf-8")
    existing_market_dir = tmp_path / "market"
    existing_market_dir.mkdir()
    missing_report_dir = tmp_path / "missing_reports"

    state = UiState()
    state.apply_saved(
        {
            "active_tab": "backtest",
            "parsed_db_path": str(existing_db),
            "backtest_report_dir": str(missing_report_dir),
            "timeout_seconds": 300,
            "market": {
                "market_data_dir": str(existing_market_dir),
                "download_tf": "15m",
                "simulation_tf": "1h",
                "detail_tf": "15m",
                "validate_mode": "off",
                "new_dir_enabled": True,
                "new_dir_path": str(tmp_path / "missing_market_new"),
                "buffer_mode": "manual",
                "pre_buffer_days": 3,
                "post_buffer_days": 2,
                "download_tfs": ["15m", "1h"],
                "data_types": {
                    "ohlcv_last": False,
                    "ohlcv_mark": True,
                    "funding_rate": True,
                    "perp": True,
                    "spot": False,
                    "funding": True,
                },
            },
        }
    )

    assert state.active_tab == "backtest"
    assert state.timeout_seconds == 300
    assert state.market.download_tf == "15m"
    assert state.market.simulation_tf == "1h"
    assert state.market.detail_tf == "15m"
    assert state.market.validate_mode == "off"
    assert state.market.new_dir_enabled is True
    assert state.market.data_types.ohlcv_mark is True
    assert state.market.data_types.funding_rate is True

    serialized = state.to_dict()
    assert serialized["timeout_seconds"] == 300
    assert serialized["market"]["download_tfs"] == ["15m", "1h"]
    assert serialized["market"]["data_types"]["ohlcv_mark"] is True

    invalid_paths = state.validate_paths()
    assert str(missing_report_dir) in invalid_paths
    assert str(tmp_path / "missing_market_new") in invalid_paths
    assert str(existing_db) not in invalid_paths
    assert str(existing_market_dir) not in invalid_paths
