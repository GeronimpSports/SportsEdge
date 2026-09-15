from pathlib import Path

import pytest

from autonomous_video.models import JobState
from autonomous_video.pipeline import PostgamePipeline
from autonomous_video.providers import FixtureProvider
from autonomous_video.state_machine import InvalidTransition, transition
from autonomous_video.store import JsonJobStore

FIXTURE = Path(__file__).parents[1] / "autonomous_video" / "fixtures" / "ou_michigan_2026.json"


def test_final_game_creates_exactly_one_job(tmp_path):
    provider = FixtureProvider(FIXTURE)
    pipeline = PostgamePipeline(JsonJobStore(tmp_path), provider)
    first = pipeline.scan_for_final_games()
    second = pipeline.scan_for_final_games()
    assert len(first) == 1
    assert second == []
    assert first[0].game.home_score == 17
    assert first[0].game.away_score == 10


def test_pipeline_reaches_one_click_gate(tmp_path):
    provider = FixtureProvider(FIXTURE)
    pipeline = PostgamePipeline(JsonJobStore(tmp_path), provider)
    job = pipeline.scan_for_final_games()[0]
    pipeline.run_until_blocked(job)
    assert job.state == JobState.READY_FOR_APPROVAL
    assert job.artifacts["qa_report"]["pass"] is True
    assert job.artifacts["media_manifest"]["rights_gate_required"] is True
    assert job.stage_attempts == {
        "ingest": 1,
        "analysis": 1,
        "script": 1,
        "media_match": 1,
        "render": 1,
        "qa": 1,
    }


def test_approval_is_explicit(tmp_path):
    provider = FixtureProvider(FIXTURE)
    pipeline = PostgamePipeline(JsonJobStore(tmp_path), provider)
    job = pipeline.scan_for_final_games()[0]
    pipeline.run_until_blocked(job)
    pipeline.approve(job)
    assert job.state == JobState.PUBLISHED


def test_illegal_state_jump_is_rejected(tmp_path):
    provider = FixtureProvider(FIXTURE)
    pipeline = PostgamePipeline(JsonJobStore(tmp_path), provider)
    job = pipeline.scan_for_final_games()[0]
    with pytest.raises(InvalidTransition):
        transition(job, JobState.PUBLISHED)
