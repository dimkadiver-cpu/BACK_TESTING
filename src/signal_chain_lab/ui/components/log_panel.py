"""Reusable log panel component for long-running GUI tasks."""
from __future__ import annotations

from nicegui import ui


class LogPanel:
    """Thin wrapper around ``ui.log`` with helpers used across blocks."""

    def __init__(self, *, title: str = "Log", max_lines: int = 300) -> None:
        self._lines: list[str] = []
        self._max_lines = max_lines
        with ui.card().classes("w-full"):
            ui.label(title).classes("text-subtitle2")
            self._log = ui.log(max_lines=max_lines).classes("w-full h-56 bg-slate-950 text-emerald-300")

    def clear(self) -> None:
        self._lines.clear()
        self._log.clear()

    def push(self, line: str) -> None:
        self._lines.append(line)
        if len(self._lines) > self._max_lines:
            self._lines = self._lines[-self._max_lines :]
        self._log.push(line)

    def lines(self) -> list[str]:
        return list(self._lines)
