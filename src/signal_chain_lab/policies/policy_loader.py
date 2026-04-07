"""Policy loader: reads and validates YAML policy files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.signal_chain_lab.policies.base import PolicyConfig


class PolicyLoadError(RuntimeError):
    """Raised when a policy cannot be loaded or validated."""


class PolicyLoader:
    """Load policy configurations from YAML files."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self.base_dir = Path(base_dir) if base_dir is not None else root_dir / "configs" / "policies"

    def load(self, policy: str | Path) -> PolicyConfig:
        policy_path = self._resolve_policy_path(policy)
        if not policy_path.exists():
            raise PolicyLoadError(f"Policy file not found: {policy_path}")

        try:
            raw_data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PolicyLoadError(f"Invalid YAML in policy file: {policy_path}") from exc

        if not isinstance(raw_data, dict):
            raise PolicyLoadError("Policy YAML must define a mapping object")

        normalized = self._apply_defaults(raw_data)

        try:
            return PolicyConfig.from_dict(normalized)
        except Exception as exc:  # pragma: no cover - defensive
            raise PolicyLoadError(f"Policy validation failed for {policy_path}") from exc

    def _resolve_policy_path(self, policy: str | Path) -> Path:
        value = Path(policy)
        if value.suffix in {".yaml", ".yml"}:
            return value if value.is_absolute() else self.base_dir / value
        return self.base_dir / f"{policy}.yaml"

    def _apply_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("name"):
            raise PolicyLoadError("Policy field 'name' is required")

        normalized = dict(data)

        for section in ("updates", "execution"):
            section_value = normalized.get(section)
            if section_value is None:
                normalized[section] = {}
            elif not isinstance(section_value, dict):
                raise PolicyLoadError(f"Policy field '{section}' must be a mapping")

        for section in ("entry", "tp", "sl", "pending", "risk"):
            section_value = normalized.get(section)
            if section_value is None:
                normalized[section] = {}
            elif not isinstance(section_value, dict):
                raise PolicyLoadError(f"Policy field '{section}' must be a mapping")

        return normalized
