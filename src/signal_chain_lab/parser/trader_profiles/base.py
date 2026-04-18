"""Base abstractions for trader-specific parser profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Protocol


@dataclass(slots=True)
class ParserContext:
    trader_code: str
    message_id: int | None
    reply_to_message_id: int | None
    channel_id: str | None
    raw_text: str
    reply_raw_text: str | None = None
    extracted_links: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TraderParseResult:
    message_type: str
    intents: list[str] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    target_refs: list[dict[str, Any]] = field(default_factory=list)
    reported_results: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    # v2 semantic envelope (additive, backward compatible)
    primary_intent: str | None = None
    actions_structured: list[dict[str, Any]] = field(default_factory=list)
    target_scope: dict[str, Any] = field(default_factory=dict)
    linking: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._normalize_symbols()

    def _normalize_symbols(self) -> None:
        if isinstance(self.entities, dict):
            normalized = _normalize_symbol(self.entities.get("symbol"))
            if normalized:
                self.entities["symbol"] = normalized

        for target in self.target_refs:
            if not isinstance(target, dict):
                continue
            if str(target.get("kind") or "").lower() != "symbol":
                continue
            normalized_ref = _normalize_symbol(target.get("ref"))
            if normalized_ref:
                target["ref"] = normalized_ref

        for action in self.actions_structured:
            if not isinstance(action, dict):
                continue
            normalized_action_symbol = _normalize_symbol(action.get("symbol"))
            if normalized_action_symbol:
                action["symbol"] = normalized_action_symbol
            normalized_instrument = _normalize_symbol(action.get("instrument"))
            if normalized_instrument:
                action["instrument"] = normalized_instrument

        for item in self.reported_results:
            if not isinstance(item, dict):
                continue
            normalized_report_symbol = _normalize_symbol(item.get("symbol"))
            if normalized_report_symbol:
                item["symbol"] = normalized_report_symbol


class TraderProfileParser(Protocol):
    def parse_message(self, text: str, context: ParserContext) -> TraderParseResult:
        """Parse a trader message and return normalized profile output."""


_SYMBOL_SUFFIX_RE = re.compile(r"(?:[._-]?P(?:ERP)?)$", re.IGNORECASE)


def _normalize_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.upper().strip()
    if not normalized:
        return None
    normalized = _SYMBOL_SUFFIX_RE.sub("", normalized)
    return normalized or None
