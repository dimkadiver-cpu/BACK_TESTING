from __future__ import annotations

from datetime import datetime, timezone

from src.signal_chain_lab.domain.enums import ChainInputMode, TradeStatus
from src.signal_chain_lab.domain.trade_state import FillRecord, TradeState
from src.signal_chain_lab.reports.trade_report import build_trade_result


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_build_trade_result_uses_state_funding_paid() -> None:
    state = TradeState(
        signal_id="sig-funding-1",
        symbol="BTCUSDT",
        side="BUY",
        status=TradeStatus.CLOSED,
        input_mode=ChainInputMode.CHAIN_COMPLETE,
        policy_name="policy-a",
        fills=[FillRecord(price=100.0, qty=1.0, timestamp=_utc("2026-01-01T00:00:00"))],
        avg_entry_price=100.0,
        realized_pnl=10.0,
        fees_paid=2.0,
        close_fees_paid=1.0,
        funding_paid=3.0,
    )

    result = build_trade_result(state, event_log=[])
    assert result.funding_total_raw_net == 3.0
    assert result.pnl_gross_raw == 11.0
    assert result.pnl_net_raw == 12.0
