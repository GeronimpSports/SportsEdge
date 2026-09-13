"""Research-only pre-odds joint-score handoff for NFL team-total derivatives.

The canonical frozen NFL run machine intentionally does not expose its joint
score rows.  This module reproduces the *same* market-blind distribution boundary
without modifying that frozen surface: it uses the canonical bound-model loader,
PIT live-feature validator, score-distribution function, and distribution hash.

Nothing here consumes sportsbook data, prices a market, promotes a derivative,
changes Model_P authority, sizes a stake, or creates OFFICIAL eligibility.
A handoff becomes usable by downstream research only after its distribution hash
and provenance are proven identical to the canonical run-machine report.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .m2 import derive_nfl_m2_score_distribution
from .run_machine import (
    DEFAULT_FEATURE_TTL_SECONDS,
    NFLMachineReport,
    NFLRunMachineError,
    _distribution_hash,
    _load_bound_model,
    _validate_live_features,
)

HANDOFF_SCHEMA = "SPORTSEDGE_NFL_TEAM_TOTAL_DISTRIBUTION_HANDOFF_V1"
HANDOFF_STATUS = "RESEARCH_ONLY_PRE_ODDS_DISTRIBUTION_HANDOFF"
VERIFICATION_STATUS = "RESEARCH_ONLY_CANONICAL_DISTRIBUTION_MATCH"


class NFLTeamTotalHandoffError(ValueError):
    pass


def _fail(message: str) -> NFLTeamTotalHandoffError:
    return NFLTeamTotalHandoffError(message)


def build_team_total_distribution_handoff(
    *,
    model_artifact: Mapping[str, Any],
    expected_model_artifact_sha256: str,
    runtime_code_git_sha: str,
    live_features: Mapping[str, Any],
    now: datetime,
    feature_ttl_seconds: int = DEFAULT_FEATURE_TTL_SECONDS,
) -> dict[str, Any]:
    """Create market-blind score rows before sportsbook acquisition/binding."""
    try:
        model, artifact_sha, code_sha, training_sha = _load_bound_model(
            model_artifact,
            expected_model_artifact_sha256=expected_model_artifact_sha256,
            runtime_code_git_sha=runtime_code_git_sha,
        )
        live_sha, live_asof, games = _validate_live_features(
            live_features,
            current=now,
            feature_ttl_seconds=feature_ttl_seconds,
        )
    except (NFLRunMachineError, ValueError) as exc:
        raise _fail(str(exc)) from exc

    handoff_games: list[dict[str, Any]] = []
    for game in games:
        game_id = str(game.get("game_id") or "").strip()
        try:
            distribution = tuple(derive_nfl_m2_score_distribution(model, dict(game)))
        except ValueError as exc:
            raise _fail(str(exc)) from exc
        if not distribution:
            raise _fail(f"NFL_TEAM_TOTAL_HANDOFF_DISTRIBUTION_EMPTY:{game_id}")
        score_rows = [dict(row) for row in distribution]
        try:
            distribution_sha = _distribution_hash(score_rows)
        except NFLRunMachineError as exc:
            raise _fail(str(exc)) from exc
        handoff_games.append({
            "game_id": game_id,
            "game_start_ts": str(game.get("game_start_ts") or ""),
            "home_team": str(game.get("home_team") or ""),
            "away_team": str(game.get("away_team") or ""),
            "provider_home_team": str(game.get("provider_home_team") or ""),
            "provider_away_team": str(game.get("provider_away_team") or ""),
            "distribution_sha256": distribution_sha,
            "score_rows": score_rows,
        })

    if not handoff_games:
        raise _fail("NFL_TEAM_TOTAL_HANDOFF_GAMES_EMPTY")
    return {
        "schema_version": HANDOFF_SCHEMA,
        "status": HANDOFF_STATUS,
        "sport": "nfl",
        "model_artifact_sha256": artifact_sha,
        "model_code_git_sha": code_sha,
        "training_source_manifest_sha256": training_sha,
        "live_feature_source_manifest_sha256": live_sha,
        "live_feature_asof_ts": live_asof.isoformat(),
        "games": handoff_games,
        "sportsbook_data_consumed": False,
        "market_line_consumed": False,
        "market_price_consumed": False,
        "model_fit_performed": False,
        "promotion_authority": False,
        "model_p_authority": False,
        "staking_authority": False,
        "official_authority": False,
    }


def verify_handoff_against_canonical_report(
    handoff: Mapping[str, Any],
    report: NFLMachineReport,
) -> dict[str, Any]:
    """Prove score rows are the exact canonical distribution used by the game run."""
    if not isinstance(handoff, Mapping):
        raise _fail("NFL_TEAM_TOTAL_HANDOFF_INVALID")
    if handoff.get("schema_version") != HANDOFF_SCHEMA:
        raise _fail("NFL_TEAM_TOTAL_HANDOFF_SCHEMA_INVALID")
    if handoff.get("status") != HANDOFF_STATUS:
        raise _fail("NFL_TEAM_TOTAL_HANDOFF_STATUS_INVALID")
    for field in (
        "sportsbook_data_consumed",
        "market_line_consumed",
        "market_price_consumed",
        "model_fit_performed",
        "promotion_authority",
        "model_p_authority",
        "staking_authority",
        "official_authority",
    ):
        if handoff.get(field) is not False:
            raise _fail(f"NFL_TEAM_TOTAL_HANDOFF_ZERO_AUTHORITY_REQUIRED:{field}")

    identity_pairs = (
        ("model_artifact_sha256", report.model_artifact_sha256),
        ("model_code_git_sha", report.model_code_git_sha),
        ("training_source_manifest_sha256", report.training_source_manifest_sha256),
        ("live_feature_source_manifest_sha256", report.live_feature_source_manifest_sha256),
        ("live_feature_asof_ts", report.live_feature_asof_ts),
    )
    for field, expected in identity_pairs:
        if str(handoff.get(field) or "") != str(expected or ""):
            raise _fail(f"NFL_TEAM_TOTAL_HANDOFF_IDENTITY_MISMATCH:{field}")

    games = handoff.get("games")
    if not isinstance(games, list) or not games:
        raise _fail("NFL_TEAM_TOTAL_HANDOFF_GAMES_INVALID")
    handoff_by_game: dict[str, Mapping[str, Any]] = {}
    for raw in games:
        if not isinstance(raw, Mapping):
            raise _fail("NFL_TEAM_TOTAL_HANDOFF_GAME_INVALID")
        game_id = str(raw.get("game_id") or "").strip()
        if not game_id or game_id in handoff_by_game:
            raise _fail(f"NFL_TEAM_TOTAL_HANDOFF_GAME_ID_INVALID:{game_id or 'EMPTY'}")
        score_rows = raw.get("score_rows")
        if not isinstance(score_rows, list) or not score_rows:
            raise _fail(f"NFL_TEAM_TOTAL_HANDOFF_SCORE_ROWS_INVALID:{game_id}")
        try:
            actual_sha = _distribution_hash(score_rows)
        except NFLRunMachineError as exc:
            raise _fail(str(exc)) from exc
        declared_sha = str(raw.get("distribution_sha256") or "").strip().lower()
        if actual_sha != declared_sha:
            raise _fail(f"NFL_TEAM_TOTAL_HANDOFF_SELF_HASH_MISMATCH:{game_id}")
        handoff_by_game[game_id] = raw

    report_by_game: dict[str, list[Any]] = {}
    for row in report.results:
        report_by_game.setdefault(str(row.game_id), []).append(row)
    if set(handoff_by_game) != set(report_by_game):
        raise _fail("NFL_TEAM_TOTAL_HANDOFF_GAME_SET_MISMATCH")

    verified_games: list[dict[str, Any]] = []
    for game_id, rows in sorted(report_by_game.items()):
        report_hashes = {str(row.distribution_sha256 or "") for row in rows}
        if len(report_hashes) != 1 or "" in report_hashes:
            raise _fail(f"NFL_TEAM_TOTAL_CANONICAL_DISTRIBUTION_IDENTITY_INVALID:{game_id}")
        canonical_sha = next(iter(report_hashes))
        handoff_game = handoff_by_game[game_id]
        if canonical_sha != str(handoff_game.get("distribution_sha256") or ""):
            raise _fail(f"NFL_TEAM_TOTAL_HANDOFF_CANONICAL_HASH_MISMATCH:{game_id}")
        for row in rows:
            if row.model_artifact_sha256 != report.model_artifact_sha256:
                raise _fail(f"NFL_TEAM_TOTAL_CANONICAL_MODEL_IDENTITY_MISMATCH:{game_id}")
            if row.model_code_git_sha != report.model_code_git_sha:
                raise _fail(f"NFL_TEAM_TOTAL_CANONICAL_CODE_IDENTITY_MISMATCH:{game_id}")
            if row.training_source_manifest_sha256 != report.training_source_manifest_sha256:
                raise _fail(f"NFL_TEAM_TOTAL_CANONICAL_TRAINING_IDENTITY_MISMATCH:{game_id}")
            if row.live_feature_source_manifest_sha256 != report.live_feature_source_manifest_sha256:
                raise _fail(f"NFL_TEAM_TOTAL_CANONICAL_LIVE_IDENTITY_MISMATCH:{game_id}")
        verified_games.append({
            "game_id": game_id,
            "distribution_sha256": canonical_sha,
            "score_rows": [dict(row) for row in handoff_game["score_rows"]],
        })

    return {
        "schema_version": HANDOFF_SCHEMA,
        "status": VERIFICATION_STATUS,
        "sport": "nfl",
        "games": verified_games,
        "model_artifact_sha256": report.model_artifact_sha256,
        "model_code_git_sha": report.model_code_git_sha,
        "training_source_manifest_sha256": report.training_source_manifest_sha256,
        "live_feature_source_manifest_sha256": report.live_feature_source_manifest_sha256,
        "live_feature_asof_ts": report.live_feature_asof_ts,
        "canonical_distribution_match": True,
        "sportsbook_data_was_excluded_from_handoff_build": True,
        "promotion_authority": False,
        "model_p_authority": False,
        "staking_authority": False,
        "official_authority": False,
    }
