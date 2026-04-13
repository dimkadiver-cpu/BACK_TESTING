from __future__ import annotations

import pytest

from src.signal_chain_lab.domain.results import ScenarioResult
from src.signal_chain_lab.optimizer.objective import OptimizerScoringWeights, compute_score


def test_compute_score_from_known_metrics_returns_float() -> None:
    scenario_result = ScenarioResult(
        policy_name="candidate",
        avg_trade_return_pct_net=0.20,   # maps to .return_pct property
        expectancy_pct_net=0.04,          # maps to .expectancy property
        win_rate_net=0.60,                # maps to .win_rate property
        max_drawdown=0.10,
        simulated_chains_count=90,
        excluded_chains_count=10,
        avg_warnings_per_trade=0.20,
    )
    weights = OptimizerScoringWeights(
        return_pct_weight=2.0,
        expectancy_weight=1.0,
        win_rate_weight=0.5,
        drawdown_penalty=1.0,
        warning_rate_penalty=0.25,
        excluded_rate_penalty=0.5,
    )

    score = compute_score(scenario_result, weights=weights)

    assert isinstance(score, float)
    assert score == pytest.approx(0.54)
