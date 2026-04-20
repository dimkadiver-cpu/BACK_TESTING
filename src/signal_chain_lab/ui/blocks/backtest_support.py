"""Helper utilities for Blocco 3 — Backtest.

Fase 0: policy discovery, DB introspection, report resolution.
These helpers are pure (no UI imports) so they can be tested independently.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.signal_chain_lab.ui.state import UiState

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_POLICIES_DIR = _PROJECT_ROOT / "configs" / "policies"
_FALLBACK_POLICIES: list[str] = ["original_chain", "signal_only"]


@dataclass(frozen=True, slots=True)
class MarketCoverageSnapshot:
    """Latest market coverage snapshot used to gate backtest execution."""

    symbols: int
    symbols_complete: int
    required_intervals: int
    gaps: int

    @property
    def coverage_pct(self) -> float:
        if self.symbols <= 0:
            return 0.0
        return round((self.symbols_complete / self.symbols) * 100, 1)


def discover_policy_names(policies_dir: Path | None = None) -> list[str]:
    """Scan configs/policies/*.yaml and return sorted names.

    Falls back to ['original_chain', 'signal_only'] when the directory is
    missing or contains no valid policy files.
    """
    d = policies_dir or _POLICIES_DIR
    if not d.exists():
        return list(_FALLBACK_POLICIES)
    names = sorted({p.stem for p in d.glob("*.yaml")} | {p.stem for p in d.glob("*.yml")})
    return names if names else list(_FALLBACK_POLICIES)


def policies_dir_path(policies_dir: Path | None = None) -> Path:
    """Return the absolute policy directory used by the GUI."""
    return (policies_dir or _POLICIES_DIR).resolve()


def load_policy_yaml(policy_name: str, policies_dir: Path | None = None) -> str:
    """Return raw YAML text for *policy_name*; empty string when not found."""
    d = policies_dir or _POLICIES_DIR
    path = d / f"{policy_name}.yaml"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def save_policy_yaml(
    policy_name: str, content: str, policies_dir: Path | None = None
) -> Path:
    """Write *content* to configs/policies/{policy_name}.yaml; creates dir if needed."""
    d = policies_dir or _POLICIES_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{policy_name}.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def discover_traders_from_db(db_path: str) -> list[str]:
    """Return distinct trader_ids from operational_signals; empty list on any error."""
    path = Path(db_path)
    if not path.exists():
        return []
    try:
        with sqlite3.connect(str(path)) as conn:
            cur = conn.execute(
                "SELECT DISTINCT trader_id FROM operational_signals"
                " WHERE trader_id IS NOT NULL ORDER BY trader_id"
            )
            return [row[0] for row in cur.fetchall() if row[0]]
    except Exception:
        return []


def discover_date_range_from_db(db_path: str) -> tuple[str, str]:
    """Return (min_date, max_date) as YYYY-MM-DD from NEW_SIGNAL records.

    Uses the join operational_signals → parse_results → raw_messages, the same
    path chain_builder uses for open_ts. Returns ('', '') on any error.
    """
    path = Path(db_path)
    if not path.exists():
        return "", ""
    try:
        with sqlite3.connect(str(path)) as conn:
            row = conn.execute(
                """
                SELECT DATE(MIN(rm.message_ts)), DATE(MAX(rm.message_ts))
                FROM operational_signals os
                JOIN parse_results pr ON pr.parse_result_id = os.parse_result_id
                JOIN raw_messages rm ON rm.raw_message_id = pr.raw_message_id
                WHERE os.message_type = 'NEW_SIGNAL'
                """
            ).fetchone()
        if row and row[0] and row[1]:
            return str(row[0]), str(row[1])
        return "", ""
    except Exception:
        return "", ""


def find_html_report(report_dir: str | Path) -> Path | None:
    """Return the most recently modified HTML file in *report_dir*, or None."""
    d = Path(report_dir)
    if not d.exists():
        return None
    html_files = sorted(d.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return html_files[0] if html_files else None


def load_market_coverage_snapshot(state: "UiState") -> MarketCoverageSnapshot | None:
    """Read the most recent market coverage snapshot from the latest plan artifact."""
    plan_path = Path(state.market.latest_market_plan_path or "")
    if not plan_path.exists():
        return None
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        return None

    symbols = int(summary.get("symbols", 0) or 0)
    symbols_with_gaps = int(summary.get("symbols_with_gaps", 0) or 0)
    symbols_complete = int(summary.get("symbols_complete", max(symbols - symbols_with_gaps, 0)) or 0)
    required_intervals = int(summary.get("required_intervals", 0) or 0)
    gaps = int(summary.get("gaps", state.market.market_data_gap_count) or 0)
    return MarketCoverageSnapshot(
        symbols=symbols,
        symbols_complete=symbols_complete,
        required_intervals=required_intervals,
        gaps=gaps,
    )


def market_backtest_gate(
    state: "UiState",
    *,
    coverage_threshold: float = 0.0,
) -> tuple[bool, str, str]:
    """Gate backtests using the latest coverage snapshot instead of market_ready."""
    snapshot = load_market_coverage_snapshot(state)
    if snapshot is None or snapshot.symbols <= 0:
        return False, "Copertura dataset: 0% · analisi mancante · esegui Analizza", "error"

    coverage_pct = snapshot.coverage_pct
    if coverage_pct <= coverage_threshold:
        return False, f"Copertura dataset: {coverage_pct:.1f}% · {snapshot.gaps} gap · run bloccato", "error"

    status = state.market.market_validation_status
    if snapshot.gaps > 0 or status not in {"validated", "gap_validated", "gap_validated_partial"}:
        return True, f"Copertura dataset: {coverage_pct:.1f}% · {snapshot.gaps} gap · run consentito con warning", "warning"

    return True, f"Copertura dataset: {coverage_pct:.1f}% · {snapshot.gaps} gap · run consentito", "positive"
