from __future__ import annotations

from src.signal_chain_lab.optimizer.objective import OptimizerSearchSpace, build_policy_from_trial


class FakeTrial:
    def __init__(self) -> None:
        self.number = 7

    def suggest_categorical(self, name: str, choices: list[str | int | None]) -> str | int | None:
        picks: dict[str, str | int | None] = {
            "entry_allocation": "equal",
            "use_tp_count": 3,
            "tp_distribution": "tp_50_30_20",
            "be_trigger": "tp1",
        }
        return picks[name]

    def suggest_float(self, name: str, low: float, high: float, *, step: float | None = None) -> float:
        assert name == "pending_timeout_hours"
        assert low == 4.0
        assert high == 48.0
        assert step == 1.0
        return 12.0


def test_build_policy_from_trial_generates_valid_policy_config() -> None:
    trial = FakeTrial()
    policy = build_policy_from_trial(trial, search_space=OptimizerSearchSpace())

    assert policy.name == "optuna_trial_7"
    assert policy.entry.entry_allocation == "equal"
    assert policy.tp.use_tp_count == 3
    assert policy.tp.tp_distribution == "tp_50_30_20"
    assert policy.sl.be_trigger == "tp1"
    assert policy.pending.pending_timeout_hours == 12.0
