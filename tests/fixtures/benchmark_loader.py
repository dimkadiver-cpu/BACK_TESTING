from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from src.signal_chain_lab.domain.enums import ChainInputMode, EventSource, EventType
from src.signal_chain_lab.domain.events import CanonicalChain, CanonicalEvent


_FIXTURE_DIR = Path(__file__).parent


class BenchmarkExpectation(BaseModel):
    signal_id: str
    scenario: str
    expected_status: str
    expected_close_reason: str | None = None
    indicative_pnl: float = 0.0
    expected_warnings: int = 0
    expected_ignored: int = 0


def load_benchmark_chains() -> list[CanonicalChain]:
    payload = json.loads((_FIXTURE_DIR / "benchmark_chains.json").read_text(encoding="utf-8"))
    chains: list[CanonicalChain] = []

    for raw_chain in payload:
        events = [
            CanonicalEvent(
                signal_id=raw_chain["signal_id"],
                trader_id=raw_chain.get("trader_id"),
                symbol=raw_chain["symbol"],
                side=raw_chain["side"],
                timestamp=event["timestamp"],
                event_type=EventType(event["event_type"]),
                source=EventSource(event["source"]),
                payload=event.get("payload", {}),
                sequence=event["sequence"],
            )
            for event in raw_chain["events"]
        ]

        chains.append(
            CanonicalChain(
                signal_id=raw_chain["signal_id"],
                trader_id=raw_chain.get("trader_id"),
                symbol=raw_chain["symbol"],
                side=raw_chain["side"],
                input_mode=ChainInputMode(raw_chain["input_mode"]),
                has_updates_in_dataset=raw_chain["has_updates_in_dataset"],
                created_at=raw_chain["created_at"],
                events=events,
            )
        )

    return chains


def load_expectations() -> dict[str, BenchmarkExpectation]:
    payload = json.loads((_FIXTURE_DIR / "benchmark_expectations.json").read_text(encoding="utf-8"))
    return {item["signal_id"]: BenchmarkExpectation.model_validate(item) for item in payload}
