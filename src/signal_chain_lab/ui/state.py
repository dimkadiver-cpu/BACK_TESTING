"""Shared state used by the NiceGUI Sprint 9 workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class QualityReport:
    """Synthetic parse/chain readiness report displayed in block 2."""

    total_signals: int = 0
    simulable_signals: int = 0
    top_warnings: list[tuple[str, int]] = field(default_factory=list)


@dataclass(slots=True)
class UiState:
    """Mutable state shared across the three sequential GUI blocks."""

    source_kind: str = "existing_db"
    chat_id: str = ""
    date_from: str = ""
    date_to: str = ""

    downloaded_db_path: str = ""
    parsed_db_path: str = ""

    parser_profile: str = "trader_a"
    trader_mapping_path: str = "configs/telegram_source_map.json"
    proceed_to_backtest: bool = False

    policy_name: str = "original_chain"
    market_data_dir: str = "data/market"
    timeframe: str = "M1"
    timeout_seconds: int = 60

    latest_artifact_path: str = ""

    def effective_db_path(self) -> str:
        return self.parsed_db_path or self.downloaded_db_path

    def db_exists(self) -> bool:
        path = self.effective_db_path()
        return bool(path) and Path(path).exists()
