"""Optimizer package for policy search above scenario runner."""
from __future__ import annotations

from src.signal_chain_lab.optimizer.objective import (
    OptimizerScoringWeights,
    OptimizerSearchSpace,
    build_policy_from_trial,
    compute_score,
)
from src.signal_chain_lab.optimizer.runner import (
    OptimizerConfig,
    OptimizerRunResult,
    run_optimizer,
)

__all__ = [
    "OptimizerConfig",
    "OptimizerRunResult",
    "OptimizerScoringWeights",
    "OptimizerSearchSpace",
    "build_policy_from_trial",
    "compute_score",
    "run_optimizer",
]
