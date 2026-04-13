from pathlib import Path

from src.signal_chain_lab.ui.blocks.backtest_support import discover_policy_names


def test_discover_policy_names_returns_all_yaml_files(tmp_path: Path) -> None:
    (tmp_path / "signal_only.yaml").write_text("name: signal_only\n", encoding="utf-8")
    (tmp_path / "policy_template_mvp.yaml").write_text("name: template\n", encoding="utf-8")
    (tmp_path / "custom_policy.yml").write_text("name: custom\n", encoding="utf-8")

    names = discover_policy_names(tmp_path)

    assert names == ["custom_policy", "policy_template_mvp", "signal_only"]
