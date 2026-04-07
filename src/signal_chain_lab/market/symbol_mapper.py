"""Symbol mapper: normalizes trader symbol names to exchange symbol format."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SymbolMapper(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)

    def to_market_symbol(self, source_symbol: str) -> str:
        return self.mapping.get(source_symbol, source_symbol)
