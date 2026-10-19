"""Identity and timing for a single pipeline run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RunContext:
    """One pipeline execution and its row-level metrics."""

    pipeline: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rows_read: int = 0
    rows_written: int = 0
    rows_rejected: int = 0

    def finish(self) -> dict:
        """Return immutable summary metrics for the completed run."""
        finished_at = datetime.now(timezone.utc)
        return {
            "pipeline": self.pipeline,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_s": (finished_at - self.started_at).total_seconds(),
            "rows_read": self.rows_read,
            "rows_written": self.rows_written,
            "rows_rejected": self.rows_rejected,
        }

    def __str__(self) -> str:
        return f"{self.pipeline}[{self.run_id[:8]}]"
