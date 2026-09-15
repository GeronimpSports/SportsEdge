from __future__ import annotations

import json
from pathlib import Path

from .models import JobRecord


class JsonJobStore:
    """Small durable V0 store, swappable for a cloud database later."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def save(self, job: JobRecord) -> None:
        destination = self._path(job.job_id)
        tmp = destination.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(job.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(destination)

    def load(self, job_id: str) -> JobRecord:
        return JobRecord.from_dict(json.loads(self._path(job_id).read_text(encoding="utf-8")))

    def all(self) -> list[JobRecord]:
        jobs = []
        for path in sorted(self.root.glob("*.json")):
            jobs.append(JobRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return jobs

    def for_game(self, game_id: str) -> JobRecord | None:
        for job in self.all():
            if job.game.game_id == str(game_id):
                return job
        return None
