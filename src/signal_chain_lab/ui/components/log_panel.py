"""Reusable log panel component for long-running GUI tasks."""
from __future__ import annotations

from nicegui import ui


class LogPanel:
    """Collapsible terminal-style log panel with semantic colour helpers."""

    def __init__(self, *, title: str = "Log", max_lines: int = 300) -> None:
        self._lines: list[str] = []
        self._max_lines = max_lines
        self._expanded = False

        with ui.card().style(
            "background:var(--log-bg);border:1px solid var(--border);"
            "border-radius:var(--r);padding:0"
        ).classes("w-full"):
            with ui.row().style(
                "padding:6px 12px;border-bottom:1px solid var(--border-s);"
                "align-items:center;gap:8px;cursor:pointer"
            ).on("click", self._toggle):
                ui.label("$").style(
                    "color:#238636;font-family:var(--mono);font-weight:600"
                )
                ui.label(title).style(
                    "color:var(--text2);font-family:var(--mono);font-size:12px"
                )
                ui.element("div").style("flex:1")
                self._chevron = ui.label(">").style(
                    "color:var(--muted);font-family:var(--mono);font-size:11px;user-select:none"
                )

            self._log = (
                ui.log(max_lines=max_lines)
                .style(
                    "background:var(--log-bg);color:var(--log-g);"
                    "font-family:var(--mono);font-size:12px;"
                    "height:176px;overflow-y:auto;padding:8px 12px"
                )
                .classes("w-full")
            )
            self._log.set_visibility(False)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._log.set_visibility(self._expanded)
        self._chevron.set_text("v" if self._expanded else ">")

    def clear(self) -> None:
        self._lines.clear()
        self._log.clear()

    def push(self, line: str) -> None:
        self._lines.append(line)
        if len(self._lines) > self._max_lines:
            self._lines = self._lines[-self._max_lines :]
        self._log.push(line)

    def warn(self, line: str) -> None:
        self.push(f"WARN  {line}")

    def err(self, line: str) -> None:
        self.push(f"ERR   {line}")

    def dim(self, line: str) -> None:
        self.push(f"- {line}")

    def lines(self) -> list[str]:
        return list(self._lines)
