"""Reusable log panel component for long-running GUI tasks."""
from __future__ import annotations

from nicegui import ui


class LogPanel:
    """Thin wrapper around ``ui.log`` with helpers used across blocks."""

    def __init__(self, *, title: str = "Log", max_lines: int = 300) -> None:
        with ui.card().classes("w-full"):
            ui.label(title).classes("text-subtitle2")
            self._log = ui.log(max_lines=max_lines).classes("w-full h-56 bg-slate-950 text-emerald-300")

    def clear(self) -> None:
        self._log.clear()

    def push(self, line: str) -> None:
        self._log.push(line)
