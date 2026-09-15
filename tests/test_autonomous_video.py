from pathlib import Path

import pytest

from autonomous_video.models import JobState
from autonomous_video.pipeline import PostgamePipeline
from autonomous_video.providers import EspnPublicProvider, FixtureProvider
from autonomous_video.state_machine import InvalidTransition, transition
from autonomous_video.store import JsonJobStore
from autonomous_video.schema import build_evidence, normalize_play

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


def test_normalized_play_and_evidence_are_stable():
    raw = {
        "gameId": 123,
        "id": "p1",
        "period": 3,
        "clock": {"minutes": 8, "seconds": 30},
        "offense": "Oklahoma",
        "defense": "Michigan",
        "down": 2,
        "distance": 8,
        "yardsGained": 22,
        "playType": "Pass Reception",
        "playText": "22-yard touchdown",
        "ppa": 0.91,
    }
    play = normalize_play(raw, fallback_game_id="x", source="cfbd")
    assert play.game_id == "123"
    assert play.clock == "08:30"
    assert play.success is True
    assert play.explosive is True
    ev1 = build_evidence(play)
    ev2 = build_evidence(play)
    assert ev1.evidence_id == ev2.evidence_id


def test_pipeline_builds_play_index_and_analytics(tmp_path):
    provider = FixtureProvider(FIXTURE)
    pipeline = PostgamePipeline(JsonJobStore(tmp_path), provider)
    job = pipeline.scan_for_final_games()[0]
    pipeline.run_until_blocked(job)
    game_data = job.artifacts["game_data"]
    assert len(game_data["normalized_plays"]) == 4
    assert len(game_data["evidence_index"]) == 4
    analytics = job.artifacts["analytics"]
    assert analytics["plays_indexed"] == 4
    assert set(analytics["teams"]) == {"Michigan", "Oklahoma"}


def test_espn_provider_detects_final_and_maps_plays_without_key(monkeypatch):
    provider = EspnPublicProvider(date="20260912", team="Oklahoma")
    scoreboard = {
        "week": {"number": 2},
        "events": [{
            "id": "401856679",
            "date": "2026-09-12T16:14Z",
            "season": {"year": 2026},
            "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "score": "17", "team": {"id": "130", "displayName": "Michigan Wolverines"}},
                {"homeAway": "away", "score": "10", "team": {"id": "201", "displayName": "Oklahoma Sooners"}},
            ]}],
        }],
    }
    summary = {
        "header": {"competitions": [{"competitors": [
            {"team": {"id": "130", "displayName": "Michigan Wolverines"}},
            {"team": {"id": "201", "displayName": "Oklahoma Sooners"}},
        ]}]},
        "plays": [{
            "id": "play-1",
            "period": {"number": 1},
            "clock": {"displayValue": "14:57"},
            "team": {"id": "201"},
            "start": {"down": 1, "distance": 10},
            "statYardage": 8,
            "type": {"text": "Rush"},
            "text": "Rush for 8 yards",
        }],
    }

    def fake_get(base, params):
        return scoreboard if "scoreboard" in base else summary

    monkeypatch.setattr(provider, "_get_url", fake_get)
    games = provider.list_games()
    assert len(games) == 1
    assert games[0].is_final
    assert games[0].home_score == 17
    assert games[0].away_score == 10
    data = provider.ingest_game(games[0])
    assert data["play_count"] == 1
    assert data["plays"][0]["offense"] == "Oklahoma Sooners"
    assert data["plays"][0]["defense"] == "Michigan Wolverines"


def test_claim_reconciliation_and_script_are_evidence_bound(tmp_path):
    provider = FixtureProvider(FIXTURE)
    pipeline = PostgamePipeline(JsonJobStore(tmp_path), provider)
    job = pipeline.scan_for_final_games()[0]
    pipeline.run_until_blocked(job)

    reconciliation = job.artifacts["claim_reconciliation"]
    assert reconciliation["approved_count"] >= 1
    valid = {item["evidence_id"] for item in job.artifacts["game_data"]["evidence_index"]}
    for claim in reconciliation["approved"]:
        assert claim["evidence_ids"]
        assert set(claim["evidence_ids"]).issubset(valid)

    script = job.artifacts["script_draft"]
    assert script["segment_count"] == reconciliation["approved_count"]
    for segment in script["segments"]:
        assert segment["evidence_ids"]
        assert set(segment["evidence_ids"]).issubset(valid)
