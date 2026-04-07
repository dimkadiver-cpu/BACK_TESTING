"""Event log report: exports per-tick simulation events to CSV/JSON."""
from __future__ import annotations

import json
from pathlib import Path

from src.signal_chain_lab.domain.results import EventLogEntry


def write_event_log_jsonl(entries: list[EventLogEntry], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return path
