from __future__ import annotations

import json
from pathlib import Path

import pytest

from sportsedge.sports.cfb.external_repo_adoptions import (
    CFBExternalAdoptionError,
    build_cfbd_lines_research_benchmark,
    build_event_timestamped_replay_entry,
    validate_odds_event_timing,
)


def test_external_adoption_registry_has_zero_runtime_authority() -> None:
    cfg = json.loads(Path("config/cfb_external_repo_adoptions_v1.json").read_text())
    assert cfg["status"] == "RESEARCH_AND_ENGINEERING_REFERENCE_ONLY"
    assert all(value is False for value in cfg["authority"].values())
    assert all(value is False for value in cfg["governance"].values())
    ids = {row["id"] for row in cfg["sources"]}
    assert {"SPORTSDATAVERSE_CFBFASTR", "CFBD_PYTHON", "SURF_CFB_VERIFY"} <= ids


def _event(*, commence: str, book_update: str, market_update: str) -> dict:
    return {
        "commence_time": commence,
        "bookmakers": [
            {
                "key": "draftkings",
                "last_update": book_update,
                "markets": [{"key": "spreads", "last_update": market_update}],
            }
        ],
    }


def test_odds_timing_accepts_strictly_pregame_aligned_event() -> None:
    report = validate_odds_event_timing(
        _event(
            commence="2026-09-12T17:00:00Z",
            book_update="2026-09-12T16:57:00Z",
            market_update="2026-09-12T16:58:00Z",
        ),
        scheduled_start_utc="2026-09-12T17:00:00Z",
    )
    assert report["status"] == "TIMING_VALIDATED"
    assert report["timestamps_checked"] == 2
    assert report["promotion_authority"] is False


def test_odds_timing_rejects_rescheduled_start_mismatch() -> None:
    with pytest.raises(CFBExternalAdoptionError, match="ODDS_EVENT_START_MISMATCH"):
        validate_odds_event_timing(
            _event(
                commence="2026-09-12T18:00:00Z",
                book_update="2026-09-12T16:57:00Z",
                market_update="2026-09-12T16:58:00Z",
            ),
            scheduled_start_utc="2026-09-12T17:00:00Z",
        )


def test_odds_timing_rejects_post_start_quote() -> None:
    with pytest.raises(CFBExternalAdoptionError, match="POST_START_MARKET_QUOTE_FORBIDDEN"):
        validate_odds_event_timing(
            _event(
                commence="2026-09-12T17:00:00Z",
                book_update="2026-09-12T16:59:00Z",
                market_update="2026-09-12T17:00:01Z",
            ),
            scheduled_start_utc="2026-09-12T17:00:00Z",
        )


def test_cfbd_open_close_fields_are_research_only() -> None:
    out = build_cfbd_lines_research_benchmark(
        [
            {
                "game_id": 123,
                "provider": "consensus",
                "spread_open": -2.5,
                "spread": -3.5,
                "over_under_open": 52.5,
                "over_under": 50.5,
            }
        ]
    )
    assert out["status"] == "RESEARCH_BENCHMARK_NOT_PAIRED_PIT"
    assert out["decision_and_close_prices_pit_proven"] is False
    assert out["promotion_authority"] is False
    assert out["truth_gate_input"] is False


def test_event_timestamped_replay_entry_binds_raw_sha_and_causality() -> None:
    entry = build_event_timestamped_replay_entry(
        source_contract="CFBD_STATS_GAME_ADVANCED_EVENT_REPLAY_V1",
        endpoint="/stats/game/advanced",
        target_season=2025,
        target_week=4,
        as_of_week=3,
        source_event_time_utc="2025-09-13T17:00:00Z",
        target_game_start_utc="2025-09-20T17:00:00Z",
        snapshot_path="history/cfb/pit/raw/2025/week_03.json",
        raw_bytes=b"fixture",
    )
    assert entry["source_mode"] == "EVENT_TIMESTAMPED_REPLAY"
    assert len(entry["snapshot_sha256"]) == 64
    assert entry["structural_candidate_only"] is True
    assert entry["promotion_authority"] is False


def test_event_timestamped_replay_rejects_same_week_or_post_event() -> None:
    with pytest.raises(CFBExternalAdoptionError, match="REPLAY_ASOF_WEEK"):
        build_event_timestamped_replay_entry(
            source_contract="X",
            endpoint="/stats/game/advanced",
            target_season=2025,
            target_week=4,
            as_of_week=4,
            source_event_time_utc="2025-09-13T17:00:00Z",
            target_game_start_utc="2025-09-20T17:00:00Z",
            snapshot_path="history/cfb/pit/raw/x.json",
            raw_bytes=b"x",
        )
    with pytest.raises(CFBExternalAdoptionError, match="REPLAY_SOURCE_EVENT_NOT_STRICTLY_PREGAME"):
        build_event_timestamped_replay_entry(
            source_contract="X",
            endpoint="/stats/game/advanced",
            target_season=2025,
            target_week=4,
            as_of_week=3,
            source_event_time_utc="2025-09-20T17:00:00Z",
            target_game_start_utc="2025-09-20T17:00:00Z",
            snapshot_path="history/cfb/pit/raw/x.json",
            raw_bytes=b"x",
        )
