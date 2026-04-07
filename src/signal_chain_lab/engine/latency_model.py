"""Latency model: simulates message-to-execution delay."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.signal_chain_lab.policies.base import PolicyConfig


def apply_latency(timestamp: datetime, latency_ms: int) -> datetime:
    """Return timestamp shifted by the configured latency in milliseconds."""
    return timestamp + timedelta(milliseconds=max(0, latency_ms))


def policy_latency_ms(policy: PolicyConfig) -> int:
    """Extract execution latency from policy with safe fallback to 0."""
    return max(0, policy.execution.latency_ms)
