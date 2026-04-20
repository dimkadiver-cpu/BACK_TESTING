"""Load/save UI state to disk. Atomic write + debounced save."""
from __future__ import annotations

import json
import os
import platform
import threading
from pathlib import Path
from typing import Any

_save_timer: threading.Timer | None = None
_timer_lock = threading.Lock()

_APP_NAME = "SignalChainLab"


def get_state_path() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / _APP_NAME / "ui_state.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "signal_chain_lab" / "ui_state.json"


def load_ui_state() -> dict[str, Any]:
    path = get_state_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return {}


def save_ui_state(data: dict[str, Any]) -> None:
    path = get_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def debounced_save(data: dict[str, Any], delay_ms: int = 500) -> None:
    """Schedule a save; cancels any pending save to avoid write storms."""
    global _save_timer
    snapshot = dict(data)
    with _timer_lock:
        if _save_timer is not None:
            _save_timer.cancel()
        _save_timer = threading.Timer(delay_ms / 1000.0, save_ui_state, args=(snapshot,))
        _save_timer.daemon = True
        _save_timer.start()
