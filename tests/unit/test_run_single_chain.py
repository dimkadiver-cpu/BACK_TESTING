from __future__ import annotations

from scripts.run_single_chain import _safe_path_component


def test_safe_path_component_replaces_windows_reserved_chars() -> None:
    assert _safe_path_component("trader_3:2103") == "trader_3_2103"
    assert _safe_path_component('bad<>:"/\\\\|?*name') == "bad_name"
