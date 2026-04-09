"""Shared state used by the NiceGUI Sprint 9 workflow."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(slots=True)
class QualityReport:
    """Synthetic parse/chain readiness report displayed in block 2."""

    trader_id: str = ""
    total_messages: int = 0
    new_signal_count: int = 0
    new_signal_complete: int = 0
    new_signal_incomplete: int = 0
    update_count: int = 0
    update_orphan_count: int = 0
    info_only_count: int = 0
    unclassified_count: int = 0
    total_signals: int = 0
    simulable_signals: int = 0
    non_simulable_signals: int = 0
    signals_rows: int = 0
    operational_signals_rows: int = 0
    operational_new_signal_rows: int = 0
    backtest_ready: bool = False
    top_warnings: list[tuple[str, int]] = field(default_factory=list)


@dataclass(slots=True)
class UiState:
    """Mutable state shared across the three sequential GUI blocks."""

    source_kind: str = "telegram"
    chat_id: str = ""
    topic_id: str = ""
    date_from: str = ""
    date_to: str = ""
    full_history: bool = True
    download_media: bool = False
    db_output_dir: str = "parser_test/db"

    downloaded_db_path: str = ""
    parsed_db_path: str = ""

    parser_profile: str = ""
    trader_mapping_path: str = "configs/telegram_source_map.json"
    generate_parse_csv: bool = False
    parse_reports_dir: str = "parser_test/reports"
    latest_reports_dir: str = ""
    proceed_to_backtest: bool = False

    backtest_policies: list[str] = field(default_factory=lambda: ["original_chain", "signal_only"])
    latest_html_report_path: str = ""
    backtest_trader_filter: str = "all"
    backtest_date_from: str = ""
    backtest_date_to: str = ""
    backtest_max_trades: int = 0
    backtest_report_dir: str = ""
    market_data_dir: str = str((_PROJECT_ROOT / "data" / "market").resolve())
    market_data_mode: str = "existing_dir"
    market_data_ready: bool = False
    market_data_checked: bool = False
    market_data_gap_count: int = 0
    latest_market_plan_path: str = ""
    latest_market_sync_report_path: str = ""
    latest_market_validation_report_path: str = ""
    timeframe: str = "1m"
    price_basis: str = "last"
    timeout_seconds: int = 60

    latest_artifact_path: str = ""

    def effective_db_path(self) -> str:
        return self.parsed_db_path or self.downloaded_db_path

    def db_exists(self) -> bool:
        path = self.effective_db_path()
        return bool(path) and Path(path).exists()
