"""Domain warning types for simulation anomalies."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SimulationWarning(BaseModel):
    signal_id: str
    timestamp: datetime
    code: str
    message: str
    event_type: str
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
