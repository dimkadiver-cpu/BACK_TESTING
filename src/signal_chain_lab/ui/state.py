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
class MarketDataTypeState:
    """User-selectable supported market data types shown in the UI."""

    ohlcv_last: bool = True
    ohlcv_mark: bool = False
    funding_rate: bool = False


@dataclass(slots=True)
class MarketState:
    """All Market DATA state, owned and written by MarketDataPanel."""

    # Setup
    market_data_dir: str = str((_PROJECT_ROOT / "data" / "market").resolve())
    market_data_mode: str = "existing_dir"   # existing_dir | new_dir
    validate_mode: str = "light"             # full | light | off
    market_data_source: str = "bybit"
    # Timeframe
    download_tf: str = "1m"
    download_tfs: list[str] = field(default_factory=lambda: ["1m"])
    simulation_tf: str = "1m"               # parent TF (futuro Fase 5)
    detail_tf: str = "1m"                   # child TF (futuro Fase 5)
    price_basis: str = "last"
    # Buffer
    buffer_mode: str = "auto"               # auto | manual
    pre_buffer_days: int = 0
    post_buffer_days: int = 0
    buffer_preset: str = ""                 # intraday | swing | position | custom
    data_types: MarketDataTypeState = field(default_factory=MarketDataTypeState)
    # Results
    market_ready: bool = False
    market_validation_status: str = "needs_check"
    market_validation_fingerprint: str = ""
    market_data_gap_count: int = 0
    latest_market_plan_path: str = ""
    latest_market_sync_report_path: str = ""
    latest_market_validation_report_path: str = ""
    funding_status: str = "not_requested"  # not_requested | needs_sync | synced | validated | failed
    market_prepare_total_seconds: float = 0.0

    def mark_needs_check(self, *, clear_artifacts: bool = False) -> None:
        """Invalidate market readiness when DB/filters/setup context changes."""
        self.market_ready = False
        self.market_validation_status = "needs_check"
        self.market_validation_fingerprint = ""
        self.funding_status = "needs_sync" if self.data_types.funding_rate else "not_requested"
        if clear_artifacts:
            self.market_data_gap_count = 0
            self.latest_market_plan_path = ""
            self.latest_market_sync_report_path = ""
            self.latest_market_validation_report_path = ""
            self.market_prepare_total_seconds = 0.0


@dataclass(slots=True)
class UiState:
    """Mutable state shared across the three sequential GUI blocks."""

    active_tab: str = "download"

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
    timeout_seconds: int = 60

    latest_artifact_path: str = ""

    market: MarketState = field(default_factory=MarketState)

    def effective_db_path(self) -> str:
        return self.parsed_db_path or self.downloaded_db_path

    def db_exists(self) -> bool:
        path = self.effective_db_path()
        return bool(path) and Path(path).exists()
