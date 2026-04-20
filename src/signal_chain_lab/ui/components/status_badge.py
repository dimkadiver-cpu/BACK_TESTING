"""Semantic status badges for Signal Chain Lab UI."""
from __future__ import annotations

from nicegui import ui

_STYLES: dict[str, str] = {
    "NOT_STARTED": (
        "background:var(--surface-2);color:var(--muted);border:1px solid var(--border-s)"
    ),
    "READY": (
        "background:var(--ok-d);color:var(--ok);border:1px solid var(--ok)"
    ),
    "RUNNING": (
        "background:var(--accent-d);color:var(--accent);border:1px solid var(--accent)"
    ),
    "DONE": (
        "background:rgba(63,185,80,.18);color:var(--ok);border:1px solid var(--ok)"
    ),
    "WARNING": (
        "background:var(--wa-d);color:var(--wa);border:1px solid var(--wa)"
    ),
    "STALE": (
        "background:transparent;color:var(--wa);border:1px dashed var(--wa)"
    ),
    "ERROR": (
        "background:var(--er-d);color:var(--er);border:1px solid var(--er)"
    ),
}

_DEFAULT_LABELS: dict[str, str] = {
    "NOT_STARTED": "not started",
    "READY": "ready",
    "RUNNING": "running …",
    "DONE": "done",
    "WARNING": "warning",
    "STALE": "stale",
    "ERROR": "error",
}

_CSS_INJECTED = False


def _inject_css() -> None:
    global _CSS_INJECTED
    if _CSS_INJECTED:
        return
    _CSS_INJECTED = True
    ui.add_head_html("""
<style>
  @keyframes scl-pulse { 0%,100%{opacity:1} 50%{opacity:.45} }
  .scl-badge {
    display:inline-flex;align-items:center;gap:4px;
    font-family:var(--mono);font-size:10px;font-weight:600;
    padding:2px 8px;border-radius:var(--rs);
    text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;
  }
  .scl-badge-running { animation:scl-pulse 1.4s ease-in-out infinite; }
</style>
""")


def render_status_badge(status: str, label: str | None = None) -> None:
    """Render an inline semantic badge.

    Args:
        status: One of NOT_STARTED | READY | RUNNING | DONE | WARNING | STALE | ERROR
        label: Override display text; defaults to status-specific label.
    """
    _inject_css()
    key = status.upper()
    style = _STYLES.get(key, _STYLES["NOT_STARTED"])
    text = label if label is not None else _DEFAULT_LABELS.get(key, key.lower())
    extra = " scl-badge-running" if key == "RUNNING" else ""
    ui.html(f'<span class="scl-badge{extra}" style="{style}">{text}</span>')
