from __future__ import annotations

from .models import JobRecord, JobState

_ALLOWED: dict[JobState, set[JobState]] = {
    JobState.DETECTED: {JobState.INGESTING, JobState.FAILED},
    JobState.INGESTING: {JobState.DATA_READY, JobState.FAILED},
    JobState.DATA_READY: {JobState.ANALYZING, JobState.FAILED},
    JobState.ANALYZING: {JobState.ANALYSIS_READY, JobState.FAILED},
    JobState.ANALYSIS_READY: {JobState.SCRIPTING, JobState.FAILED},
    JobState.SCRIPTING: {JobState.SCRIPT_READY, JobState.FAILED},
    JobState.SCRIPT_READY: {JobState.MEDIA_MATCHING, JobState.FAILED},
    JobState.MEDIA_MATCHING: {JobState.MEDIA_READY, JobState.FAILED},
    JobState.MEDIA_READY: {JobState.RENDERING, JobState.FAILED},
    JobState.RENDERING: {JobState.QA, JobState.FAILED},
    JobState.QA: {JobState.READY_FOR_APPROVAL, JobState.FAILED},
    JobState.READY_FOR_APPROVAL: {JobState.PUBLISHED, JobState.FAILED},
    JobState.PUBLISHED: set(),
    JobState.FAILED: set(),
}


class InvalidTransition(ValueError):
    pass


def transition(job: JobRecord, target: JobState) -> None:
    if target not in _ALLOWED[job.state]:
        raise InvalidTransition(f"{job.state.value} -> {target.value} is not allowed")
    job.state = target
    job.touch()
