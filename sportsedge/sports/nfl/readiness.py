"""Evidence-derived OFFICIAL resolution for the canonical NFL M2 run machine."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from sportsedge.edge_floors import FrozenEdgeFloor, require_production_edge_floor
from sportsedge.truth_gate import decide_bet

from .m2 import NFL_M2_FEATURE_CONTRACT, PRODUCTION_NFL_M2_MODEL_ID
from .run_machine import (
    NFLMachineReport,
    NFLMachineResult,
    SUPPORTED_GAME_MARKETS,
    run_nfl_machine,
)

PROMOTION_SCHEMA_VERSION = 9


class NFLReadinessError(ValueError):
    pass


def load_nfl_promotion_registry(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_UNREADABLE") from exc
    if not isinstance(payload, dict):
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_INVALID")
    return payload


def _sha256(value: Any, error: str) -> str:
    raw = str(value or "").strip().lower()
    if len(raw) != 64 or any(ch not in "0123456789abcdef" for ch in raw):
        raise NFLReadinessError(error)
    return raw


def _git_sha(value: Any, error: str) -> str:
    raw = str(value or "").strip().lower()
    if len(raw) != 40 or any(ch not in "0123456789abcdef" for ch in raw):
        raise NFLReadinessError(error)
    return raw


def _validate_registry(
    registry: Mapping[str, Any],
    *,
    artifact_payload: Mapping[str, Any],
    runtime_code_git_sha: str,
) -> dict[str, Mapping[str, Any]]:
    if registry.get("schema_version") != PROMOTION_SCHEMA_VERSION:
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_SCHEMA_INVALID")
    if str(registry.get("sport") or "").lower() != "nfl":
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_SPORT_INVALID")
    if registry.get("model_id") != PRODUCTION_NFL_M2_MODEL_ID:
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_MODEL_ID_MISMATCH")
    if registry.get("feature_contract") != NFL_M2_FEATURE_CONTRACT:
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_FEATURE_CONTRACT_MISMATCH")

    registry_code = _git_sha(
        registry.get("code_git_sha"), "NFL_PROMOTION_REGISTRY_CODE_GIT_SHA_INVALID"
    )
    runtime_code = _git_sha(runtime_code_git_sha, "NFL_RUNTIME_CODE_GIT_SHA_INVALID")
    artifact_code = _git_sha(
        artifact_payload.get("code_git_sha"), "NFL_MODEL_ARTIFACT_CODE_GIT_SHA_INVALID"
    )
    if {registry_code, runtime_code, artifact_code} != {runtime_code}:
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_CODE_BINDING_MISMATCH")

    registry_source = _sha256(
        registry.get("source_manifest_sha256"),
        "NFL_PROMOTION_REGISTRY_SOURCE_MANIFEST_SHA256_INVALID",
    )
    artifact_source = _sha256(
        artifact_payload.get("source_manifest_sha256"),
        "NFL_MODEL_ARTIFACT_SOURCE_SHA256_INVALID",
    )
    if registry_source != artifact_source:
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_SOURCE_BINDING_MISMATCH")

    markets = registry.get("markets")
    if not isinstance(markets, Mapping):
        raise NFLReadinessError("NFL_PROMOTION_REGISTRY_MARKETS_INVALID")
    out: dict[str, Mapping[str, Any]] = {}
    for market in SUPPORTED_GAME_MARKETS:
        key = market.lower()
        row = markets.get(key)
        if not isinstance(row, Mapping):
            raise NFLReadinessError(f"NFL_PROMOTION_MARKET_MISSING:{key}")
        stage = str(row.get("stage") or "").strip().upper()
        eligible = row.get("eligible")
        if not isinstance(eligible, bool):
            raise NFLReadinessError(f"NFL_PROMOTION_ELIGIBLE_INVALID:{key}")
        if eligible is not (stage == "DEPLOYED"):
            raise NFLReadinessError(f"NFL_PROMOTION_STAGE_CONTRADICTION:{key}")
        out[market] = row
    return out


def _floor_key(market: str) -> str:
    resolved = str(market or "").strip().upper()
    if resolved not in SUPPORTED_GAME_MARKETS:
        raise NFLReadinessError(f"NFL_PROMOTION_MARKET_UNSUPPORTED:{resolved}")
    return f"NFL_{resolved}"


def _binding_instant(value: Any, error: str) -> datetime:
    raw = str(value or "").strip().replace("Z", "+00:00")
    if not raw:
        raise NFLReadinessError(error)
    try:
        out = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise NFLReadinessError(error) from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise NFLReadinessError(error)
    return out.astimezone(timezone.utc)


def _modeled_game_rows(live_features: Mapping[str, Any]) -> list[dict[str, Any]]:
    games = live_features.get("games")
    if not isinstance(games, list) or not games:
        raise NFLReadinessError("NFL_BINDING_LIVE_FEATURE_GAMES_INVALID")
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, datetime]] = set()
    for raw in games:
        if not isinstance(raw, Mapping):
            raise NFLReadinessError("NFL_BINDING_LIVE_FEATURE_GAME_INVALID")
        game_id = str(raw.get("game_id") or "").strip()
        home = str(raw.get("provider_home_team") or "").strip()
        away = str(raw.get("provider_away_team") or "").strip()
        if not game_id or not home or not away or home == away:
            raise NFLReadinessError("NFL_BINDING_LIVE_FEATURE_IDENTITY_INVALID")
        start = _binding_instant(
            raw.get("game_start_ts"), f"NFL_BINDING_LIVE_FEATURE_START_INVALID:{game_id}"
        )
        identity = (home, away, start)
        if identity in seen:
            raise NFLReadinessError(f"NFL_BINDING_LIVE_FEATURE_GAME_DUPLICATE:{game_id}")
        seen.add(identity)
        out.append({"game_id": game_id, "home": home, "away": away, "start": start})
    return out


def _normalized_outcome_names(outcomes: list[Mapping[str, Any]], market_key: str) -> list[str]:
    if market_key == "totals":
        return [str(row.get("name") or "").strip().lower() for row in outcomes]
    return [str(row.get("name") or "").strip() for row in outcomes]


def _structural_event_guard(
    event: Mapping[str, Any],
    *,
    clean_book: str,
    check_outcome_duplicates: bool = True,
) -> Mapping[str, Any] | None:
    event_home = str(event.get("home_team") or "").strip()
    event_away = str(event.get("away_team") or "").strip()
    if not event_home or not event_away or event_home == event_away:
        raise NFLReadinessError("NFL_BINDING_EVENT_TEAMS_INVALID")
    books = event.get("bookmakers")
    if not isinstance(books, list):
        raise NFLReadinessError("NFL_BINDING_BOOKMAKERS_INVALID")
    matching_books = [
        row for row in books
        if isinstance(row, Mapping)
        and str(row.get("key") or "").strip().lower() == clean_book
    ]
    if len(matching_books) > 1:
        raise NFLReadinessError(f"NFL_BINDING_BOOKMAKER_COUNT_INVALID:{clean_book}")
    if not matching_books:
        return None
    book = matching_books[0]
    markets = book.get("markets")
    if not isinstance(markets, list):
        raise NFLReadinessError("NFL_BINDING_MARKETS_INVALID")
    for market_key in ("h2h", "spreads", "totals"):
        matching_markets = [
            row for row in markets
            if isinstance(row, Mapping)
            and str(row.get("key") or "").strip().lower() == market_key
        ]
        if len(matching_markets) > 1:
            raise NFLReadinessError(f"NFL_BINDING_MARKET_COUNT_INVALID:{market_key}")
        if not matching_markets:
            continue
        outcomes = matching_markets[0].get("outcomes")
        if not isinstance(outcomes, list):
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_INVALID:{market_key}")
        if not all(isinstance(row, Mapping) for row in outcomes):
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_INVALID:{market_key}")
        names = _normalized_outcome_names(outcomes, market_key)
        if any(not name for name in names):
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_NAME_MISSING:{market_key}")
        if check_outcome_duplicates and len(set(names)) != len(names):
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_DUPLICATE:{market_key}")
    return book


def _strict_event_guard(event: Mapping[str, Any], *, clean_book: str) -> None:
    event_home = str(event.get("home_team") or "").strip()
    event_away = str(event.get("away_team") or "").strip()
    book = _structural_event_guard(
        event,
        clean_book=clean_book,
        check_outcome_duplicates=False,
    )
    if book is None:
        raise NFLReadinessError(f"NFL_BINDING_BOOKMAKER_COUNT_INVALID:{clean_book}")
    markets = book.get("markets")
    assert isinstance(markets, list)
    for market_key, expected in (
        ("h2h", {event_home, event_away}),
        ("spreads", {event_home, event_away}),
        ("totals", {"over", "under"}),
    ):
        matching_markets = [
            row for row in markets
            if isinstance(row, Mapping)
            and str(row.get("key") or "").strip().lower() == market_key
        ]
        if len(matching_markets) != 1:
            raise NFLReadinessError(f"NFL_BINDING_MARKET_COUNT_INVALID:{market_key}")
        outcomes = matching_markets[0].get("outcomes")
        if not isinstance(outcomes, list) or len(outcomes) != 2:
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_COUNT_INVALID:{market_key}")
        if not all(isinstance(row, Mapping) for row in outcomes):
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_INVALID:{market_key}")
        names = _normalized_outcome_names(outcomes, market_key)
        if any(not name for name in names):
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_NAME_MISSING:{market_key}")
        if len(set(names)) != 2:
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_DUPLICATE:{market_key}")
        if set(names) != expected:
            raise NFLReadinessError(f"NFL_BINDING_OUTCOME_PAIR_MISMATCH:{market_key}")


def _validate_bettor_facing_odds_snapshot(
    payload: Mapping[str, Any],
    *,
    book_key: str,
    required_games: Sequence[Mapping[str, Any]] | None = None,
) -> Mapping[str, Any]:
    """Reject ambiguous sportsbook bindings before Model_P economics.

    With no feature context, preserve the original conservative contract and
    require a complete selected-book H2H/spread/total pair for every event.
    With feature context, structural duplicate/corruption checks remain global,
    while full market completeness is required only for exact modeled games.
    """
    if not isinstance(payload, Mapping):
        raise NFLReadinessError("NFL_BINDING_ODDS_SNAPSHOT_INVALID")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise NFLReadinessError("NFL_BINDING_ODDS_EVENTS_INVALID")
    clean_book = str(book_key or "").strip().lower()
    if not clean_book:
        raise NFLReadinessError("NFL_BINDING_BOOK_KEY_REQUIRED")

    event_rows: list[Mapping[str, Any]] = []
    seen_event_ids: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping):
            raise NFLReadinessError("NFL_BINDING_EVENT_INVALID")
        event_id = str(event.get("id") or "").strip()
        if event_id:
            if event_id in seen_event_ids:
                raise NFLReadinessError(f"NFL_BINDING_EVENT_ID_DUPLICATE:{event_id}")
            seen_event_ids.add(event_id)
        event_rows.append(event)

    if required_games is None:
        for event in event_rows:
            _strict_event_guard(event, clean_book=clean_book)
        return payload

    required_matches: list[tuple[str, Mapping[str, Any]]] = []
    matched_event_indexes: set[int] = set()
    for game in required_games:
        game_id = str(game.get("game_id") or "").strip()
        home = str(game.get("home") or "").strip()
        away = str(game.get("away") or "").strip()
        start = game.get("start")
        if not game_id or not home or not away or not isinstance(start, datetime):
            raise NFLReadinessError("NFL_BINDING_REQUIRED_GAME_INVALID")
        matches: list[tuple[int, Mapping[str, Any]]] = []
        for index, event in enumerate(event_rows):
            if str(event.get("home_team") or "").strip() != home:
                continue
            if str(event.get("away_team") or "").strip() != away:
                continue
            event_start = _binding_instant(
                event.get("commence_time"), f"NFL_BINDING_EVENT_START_INVALID:{game_id}"
            )
            if event_start == start:
                matches.append((index, event))
        if not matches:
            raise NFLReadinessError(f"NFL_BINDING_MODELED_EVENT_NOT_FOUND:{game_id}")
        if len(matches) != 1:
            raise NFLReadinessError(f"NFL_BINDING_MODELED_EVENT_AMBIGUOUS:{game_id}")
        event_index, event = matches[0]
        if not str(event.get("id") or "").strip():
            raise NFLReadinessError(f"NFL_BINDING_MODELED_EVENT_ID_MISSING:{game_id}")
        if event_index in matched_event_indexes:
            raise NFLReadinessError(f"NFL_BINDING_MODELED_EVENT_AMBIGUOUS:{game_id}")
        matched_event_indexes.add(event_index)
        required_matches.append((game_id, event))

    for index, event in enumerate(event_rows):
        if index not in matched_event_indexes:
            _structural_event_guard(event, clean_book=clean_book)

    for _game_id, event in required_matches:
        _strict_event_guard(event, clean_book=clean_book)
    return payload


def run_nfl_ready(
    *,
    promotion_registry: Mapping[str, Any],
    floor_path: str | Path = "config/truth_gate_floors.json",
    **kwargs: Any,
) -> NFLMachineReport:
    """Run canonical M2 and resolve real promotion/floor/price gates."""
    artifact_payload = kwargs.get("model_artifact")
    if not isinstance(artifact_payload, Mapping):
        raise NFLReadinessError("NFL_MODEL_ARTIFACT_REQUIRED")
    runtime_code = str(kwargs.get("runtime_code_git_sha") or "")
    market_registry = _validate_registry(
        promotion_registry,
        artifact_payload=artifact_payload,
        runtime_code_git_sha=runtime_code,
    )

    floors: dict[str, FrozenEdgeFloor] = {}
    for market, state in market_registry.items():
        if state.get("eligible") is True:
            floors[market] = require_production_edge_floor(
                market=_floor_key(market), path=floor_path
            )

    run_kwargs = dict(kwargs)
    book_key = str(run_kwargs.get("book_key") or "draftkings")
    supplied_features = run_kwargs.get("live_features")
    supplied_odds = run_kwargs.get("odds_snapshot")
    original_builder = run_kwargs.get("feature_builder")
    original_fetcher = run_kwargs.get("odds_fetcher")
    feature_state: dict[str, list[dict[str, Any]] | None] = {"required_games": None}

    if supplied_features is not None and isinstance(supplied_features, Mapping):
        feature_state["required_games"] = _modeled_game_rows(supplied_features)

    if supplied_odds is not None:
        if feature_state["required_games"] is not None:
            _validate_bettor_facing_odds_snapshot(
                supplied_odds,
                book_key=book_key,
                required_games=feature_state["required_games"],
            )
        elif original_builder is not None:
            # Structural corruption fails immediately, but modeled-event
            # completeness waits for the feature builder to reveal the slate.
            _validate_bettor_facing_odds_snapshot(
                supplied_odds,
                book_key=book_key,
                required_games=[],
            )
        else:
            _validate_bettor_facing_odds_snapshot(supplied_odds, book_key=book_key)

    if original_builder is not None:
        if not callable(original_builder):
            raise NFLReadinessError("NFL_BINDING_FEATURE_BUILDER_INVALID")

        def validated_builder() -> Mapping[str, Any]:
            built = original_builder()
            if not isinstance(built, Mapping):
                raise NFLReadinessError("NFL_BINDING_FEATURE_BUILDER_OUTPUT_INVALID")
            required = _modeled_game_rows(built)
            feature_state["required_games"] = required
            if supplied_odds is not None:
                _validate_bettor_facing_odds_snapshot(
                    supplied_odds,
                    book_key=book_key,
                    required_games=required,
                )
            return built

        run_kwargs["feature_builder"] = validated_builder

    if original_fetcher is not None:
        if not callable(original_fetcher):
            raise NFLReadinessError("NFL_BINDING_ODDS_FETCHER_INVALID")

        def validated_fetcher() -> Mapping[str, Any]:
            fetched = original_fetcher()
            if not isinstance(fetched, Mapping):
                raise NFLReadinessError("NFL_BINDING_ODDS_FETCHER_OUTPUT_INVALID")
            required = feature_state["required_games"]
            if required is None and original_builder is not None:
                raise NFLReadinessError("NFL_BINDING_REQUIRED_GAMES_UNAVAILABLE_BEFORE_ODDS")
            _validate_bettor_facing_odds_snapshot(
                fetched,
                book_key=book_key,
                required_games=required,
            )
            return fetched

        run_kwargs["odds_fetcher"] = validated_fetcher

    report = run_nfl_machine(**run_kwargs)
    resolved_results: list[NFLMachineResult] = []
    truth_gate_rows = 0
    official_bets = 0
    deployed_rows = 0

    for row in report.results:
        state = market_registry[row.market]
        deployed = state.get("eligible") is True
        if not deployed:
            resolved_results.append(replace(
                row,
                bet_status="BLOCKED",
                reason=f"NFL_PROMOTION_EVIDENCE_REQUIRED:{row.market}",
            ))
            continue
        deployed_rows += 1
        floor = floors.get(row.market)
        if floor is None:
            raise NFLReadinessError(
                f"NFL_FROZEN_FLOOR_PREFLIGHT_MISSING:{_floor_key(row.market)}"
            )
        if row.reason == "NFL_QUOTE_STALE" or row.fair_market_p is None:
            resolved_results.append(replace(row, bet_status="BLOCKED"))
            continue

        decision = decide_bet(
            float(row.model_p),
            float(row.american_odds),
            fair_market_probability=float(row.fair_market_p),
            bound=True,
            fresh=True,
            deployed=True,
            edge_floor=float(floor.value_probability_points),
            push_probability=float(row.push_p or 0.0),
        )
        truth_gate_rows += 1
        if decision.bet_status == "OFFICIAL_BET":
            official_bets += 1
        resolved_results.append(replace(
            row,
            bet_status=decision.bet_status,
            reason="TRUTH_GATE_RESOLVED",
            edge=decision.edge,
            ev_per_dollar=decision.ev_per_dollar,
        ))

    ordered = tuple(resolved_results)
    summary = dict(report.summary)
    summary.update({
        "blocked": sum(row.bet_status == "BLOCKED" for row in ordered),
        "official_bets": official_bets,
        "deployed_rows": deployed_rows,
        "truth_gate_rows": truth_gate_rows,
        "deployed_markets": sorted(
            market for market, state in market_registry.items()
            if state.get("eligible") is True
        ),
        "manual_eligible_toggle_required": False,
        "floor_keys": sorted(_floor_key(market) for market in floors),
    })
    run_status = "SUCCESS" if truth_gate_rows else "BLOCKED"
    return replace(report, results=ordered, summary=summary, run_status=run_status)