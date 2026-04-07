"""Optimizer runner orchestration and trial artifact persistence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.signal_chain_lab.domain.events import CanonicalChain
from src.signal_chain_lab.market.data_models import MarketDataProvider
from src.signal_chain_lab.optimizer.objective import (
    OptimizerScoringWeights,
    OptimizerSearchSpace,
    build_policy_from_trial,
    compute_score,
)
from src.signal_chain_lab.scenario.runner import run_scenarios


class OptimizerConfig(BaseModel):
    benchmark_dataset_path: str
    n_trials: int = 20
    direction: str = "maximize"
    study_name: str = "signal_chain_optimizer"
    storage_url: str | None = None
    random_seed: int = 42
    artifacts_dir: str = "artifacts/optimizer"
    search_space: OptimizerSearchSpace = Field(default_factory=OptimizerSearchSpace)
    scoring_weights: OptimizerScoringWeights = Field(default_factory=OptimizerScoringWeights)


class TrialRecord(BaseModel):
    trial_id: int
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float | int] = Field(default_factory=dict)
    score: float


class OptimizerRunResult(BaseModel):
    study_name: str
    direction: str
    best_trial_id: int
    best_score: float
    trial_count: int
    trials_path: str
    ranking_path: str


def load_optimizer_config(path: str | Path) -> OptimizerConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return OptimizerConfig.model_validate(payload)


def run_optimizer(
    *,
    chains: list[CanonicalChain],
    config: OptimizerConfig,
    market_provider: MarketDataProvider | None = None,
) -> OptimizerRunResult:
    try:
        import optuna
    except ImportError as exc:  # pragma: no cover - environment dependency
        raise RuntimeError("Optuna is required for optimizer runner. Install with .[optimizer].") from exc

    sampler = optuna.samplers.TPESampler(seed=config.random_seed)
    study = optuna.create_study(
        direction=config.direction,
        study_name=config.study_name,
        storage=config.storage_url,
        load_if_exists=True,
        sampler=sampler,
    )

    def objective(trial: Any) -> float:
        policy = build_policy_from_trial(trial, search_space=config.search_space)
        scenario_results, _ = run_scenarios(chains=chains, policies=[policy], market_provider=market_provider)
        scenario_result = scenario_results[0]
        score = compute_score(scenario_result, weights=config.scoring_weights)
        trial.set_user_attr(
            "scenario_metrics",
            {
                "total_pnl": scenario_result.total_pnl,
                "return_pct": scenario_result.return_pct,
                "max_drawdown": scenario_result.max_drawdown,
                "win_rate": scenario_result.win_rate,
                "profit_factor": scenario_result.profit_factor,
                "expectancy": scenario_result.expectancy,
                "trades_count": scenario_result.trades_count,
                "simulated_chains_count": scenario_result.simulated_chains_count,
                "excluded_chains_count": scenario_result.excluded_chains_count,
                "avg_warnings_per_trade": scenario_result.avg_warnings_per_trade,
            },
        )
        return score

    study.optimize(objective, n_trials=config.n_trials)

    trial_records: list[TrialRecord] = []
    for trial in study.trials:
        if trial.value is None:
            continue
        metrics = trial.user_attrs.get("scenario_metrics", {})
        trial_records.append(
            TrialRecord(
                trial_id=trial.number,
                params=dict(trial.params),
                metrics=metrics,
                score=float(trial.value),
            )
        )

    reverse = config.direction == "maximize"
    ranking = sorted(trial_records, key=lambda item: item.score, reverse=reverse)

    artifacts_dir = Path(config.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    trials_path = artifacts_dir / "trials.json"
    ranking_path = artifacts_dir / "ranking.json"

    trials_path.write_text(
        json.dumps([record.model_dump(mode="json") for record in trial_records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ranking_path.write_text(
        json.dumps([record.model_dump(mode="json") for record in ranking], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not ranking:
        raise RuntimeError("Optimizer did not produce completed trials.")

    best = ranking[0]
    return OptimizerRunResult(
        study_name=config.study_name,
        direction=config.direction,
        best_trial_id=best.trial_id,
        best_score=best.score,
        trial_count=len(trial_records),
        trials_path=str(trials_path),
        ranking_path=str(ranking_path),
    )
