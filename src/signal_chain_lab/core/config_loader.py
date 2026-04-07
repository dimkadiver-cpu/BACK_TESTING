"""Config loader.

Loads JSON config files and provides a structured object.
See README.md, docs/MASTER_PLAN.md and docs/CONFIG_SCHEMA.md.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict
import json, os
from pathlib import Path

from src.signal_chain_lab.core.trader_tags import normalize_trader_aliases

@dataclass(frozen=True)
class Config:
    trader_aliases: Dict[str, str]
    portfolio_rules: Dict[str, Any]
    traders: Dict[str, Dict[str, Any]]  # trader_id -> {parsing, execution}

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_configs_dir(root_dir: str) -> Path:
    root = Path(root_dir)
    modern = root / "configs"
    if modern.is_dir():
        return modern
    legacy = root / "config"
    if legacy.is_dir():
        return legacy
    raise FileNotFoundError(f"No config directory found under {root}")


def _resolve_traders_dir(root_dir: str) -> Path:
    root = Path(root_dir)
    legacy = root / "traders"
    if legacy.is_dir():
        return legacy
    modern = root / "src" / "signal_chain_lab" / "parser" / "trader_profiles"
    if modern.is_dir():
        return modern
    raise FileNotFoundError(f"No trader profiles directory found under {root}")


def load_config(root_dir: str = ".") -> Config:
    # TODO: implement robust validation per docs/CONFIG_SCHEMA.md
    configs_dir = _resolve_configs_dir(root_dir)
    trader_aliases_path = configs_dir / "trader_aliases.json"
    portfolio_rules_path = configs_dir / "portfolio_rules.json"

    aliases_payload = load_json(str(trader_aliases_path)) if trader_aliases_path.is_file() else {"aliases": {}}
    portfolio = load_json(str(portfolio_rules_path)) if portfolio_rules_path.is_file() else {}
    aliases = normalize_trader_aliases(aliases_payload.get("aliases", {}))
    traders = {}
    traders_dir = _resolve_traders_dir(root_dir)
    for path in sorted(traders_dir.iterdir()):
        if not path.is_dir():
            continue
        parsing_rules = path / "parsing_rules.json"
        if not parsing_rules.is_file():
            continue
        execution_rules = path / "execution_rules.json"
        parsing = load_json(str(parsing_rules))
        execution = load_json(str(execution_rules)) if execution_rules.is_file() else {}
        traders[path.name] = {"parsing": parsing, "execution": execution}
    return Config(trader_aliases=aliases, portfolio_rules=portfolio, traders=traders)
