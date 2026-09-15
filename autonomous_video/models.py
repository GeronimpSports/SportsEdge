from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobState(StrEnum):
    DETECTED = "DETECTED"
    INGESTING = "INGESTING"
    DATA_READY = "DATA_READY"
    ANALYZING = "ANALYZING"
    ANALYSIS_READY = "ANALYSIS_READY"
    SCRIPTING = "SCRIPTING"
    SCRIPT_READY = "SCRIPT_READY"
    MEDIA_MATCHING = "MEDIA_MATCHING"
    MEDIA_READY = "MEDIA_READY"
    RENDERING = "RENDERING"
    QA = "QA"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class GameRecord:
    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    status: str
    home_score: int | None = None
    away_score: int | None = None
    start_time: str | None = None
    source: str = "unknown"

    @property
    def is_final(self) -> bool:
        return self.status.strip().upper() in {"FINAL", "COMPLETED"}


@dataclass
class JobRecord:
    job_id: str
    game: GameRecord
    state: JobState = JobState.DETECTED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    artifacts: dict[str, Any] = field(default_factory=dict)
    stage_attempts: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        game = GameRecord(**data["game"])
        return cls(
            job_id=data["job_id"],
            game=game,
            state=JobState(data["state"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            artifacts=data.get("artifacts", {}),
            stage_attempts=data.get("stage_attempts", {}),
            errors=data.get("errors", []),
        )
