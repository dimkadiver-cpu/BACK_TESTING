"""Optuna objective helpers: policy generation and explicit scoring."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from src.signal_chain_lab.domain.results import ScenarioResult
from src.signal_chain_lab.policies.base import PolicyConfig


class TrialLike(Protocol):
    """Minimal trial protocol to support unit tests without Optuna runtime."""

    number: int

    def suggest_categorical(self, name: str, choices: list[str | int | None]) -> str | int | None:
        ...

    def suggest_float(self, name: str, low: float, high: float, *, step: float | None = None) -> float:
        ...


class OptimizerSearchSpace(BaseModel):
    entry_allocation_choices: list[str] = Field(default_factory=lambda: ["equal", "front_loaded", "back_loaded"])
    use_tp_count_choices: list[int] = Field(default_factory=lambda: [1, 2, 3])
    tp_distribution_choices: list[str] = Field(default_factory=lambda: ["original", "tp_50_30_20", "equal"])
    be_trigger_choices: list[str | None] = Field(default_factory=lambda: [None, "tp1"])
    pending_timeout_hours_min: float = 4.0
    pending_timeout_hours_max: float = 48.0
    pending_timeout_hours_step: float = 1.0


class OptimizerScoringWeights(BaseModel):
    return_pct_weight: float = 1.0
    expectancy_weight: float = 1.0
    win_rate_weight: float = 0.25
    drawdown_penalty: float = 1.0
    warning_rate_penalty: float = 0.25
    excluded_rate_penalty: float = 0.5


def build_policy_from_trial(
    trial: TrialLike,
    *,
    search_space: OptimizerSearchSpace | None = None,
    policy_name_prefix: str = "optuna_trial",
) -> PolicyConfig:
    """Build a PolicyConfig from trial suggestions (PRD §19.2 initial search space)."""
    space = search_space or OptimizerSearchSpace()

    entry_allocation = trial.suggest_categorical("entry_allocation", space.entry_allocation_choices)
    use_tp_count = trial.suggest_categorical("use_tp_count", space.use_tp_count_choices)
    tp_distribution = trial.suggest_categorical("tp_distribution", space.tp_distribution_choices)
    be_trigger = trial.suggest_categorical("be_trigger", space.be_trigger_choices)
    pending_timeout_hours = trial.suggest_float(
        "pending_timeout_hours",
        space.pending_timeout_hours_min,
        space.pending_timeout_hours_max,
        step=space.pending_timeout_hours_step,
    )

    break_even_mode = "none" if be_trigger is None else "after_trigger"

    return PolicyConfig.model_validate(
        {
            "name": f"{policy_name_prefix}_{trial.number}",
            "entry": {"entry_allocation": entry_allocation},
            "tp": {
                "use_tp_count": use_tp_count,
                "tp_distribution": tp_distribution,
            },
            "sl": {
                "break_even_mode": break_even_mode,
                "be_trigger": be_trigger,
            },
            "pending": {
                "pending_timeout_hours": pending_timeout_hours,
            },
        }
    )


def compute_score(
    scenario_result: ScenarioResult,
    *,
    weights: OptimizerScoringWeights | None = None,
) -> float:
    """Compute an explicit, explainable score from scenario metrics.

    Formula (higher is better):
    score =
        + return_pct * return_pct_weight
        + expectancy * expectancy_weight
        + win_rate * win_rate_weight
        - max_drawdown * drawdown_penalty
        - warning_rate * warning_rate_penalty
        - excluded_rate * excluded_rate_penalty
    """
    cfg = weights or OptimizerScoringWeights()

    total_chains = scenario_result.simulated_chains_count + scenario_result.excluded_chains_count
    excluded_rate = (scenario_result.excluded_chains_count / total_chains) if total_chains > 0 else 0.0
    warning_rate = scenario_result.avg_warnings_per_trade

    score = (
        (scenario_result.return_pct * cfg.return_pct_weight)
        + (scenario_result.expectancy * cfg.expectancy_weight)
        + (scenario_result.win_rate * cfg.win_rate_weight)
        - (scenario_result.max_drawdown * cfg.drawdown_penalty)
        - (warning_rate * cfg.warning_rate_penalty)
        - (excluded_rate * cfg.excluded_rate_penalty)
    )
    return float(score)
