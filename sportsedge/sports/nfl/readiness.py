"""Evidence-derived OFFICIAL resolution for the canonical NFL M2 run machine."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Mapping

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


def _validate_bettor_facing_odds_snapshot(
    payload: Mapping[str, Any],
    *,
    book_key: str,
) -> Mapping[str, Any]:
    """Reject ambiguous two-way sportsbook payloads before Model_P economics.

    This guard lives outside the byte-frozen M2 compatibility surface. It is
    applied to both operator-supplied snapshots and fetched snapshots by the
    OFFICIAL-capable readiness path. The frozen run machine retains its exact
    bytes/provenance while bettor-facing binding fails closed on duplicates.
    """
    if not isinstance(payload, Mapping):
        raise NFLReadinessError("NFL_BINDING_ODDS_SNAPSHOT_INVALID")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise NFLReadinessError("NFL_BINDING_ODDS_EVENTS_INVALID")
    clean_book = str(book_key or "").strip().lower()
    if not clean_book:
        raise NFLReadinessError("NFL_BINDING_BOOK_KEY_REQUIRED")

    for event in events:
        if not isinstance(event, Mapping):
            raise NFLReadinessError("NFL_BINDING_EVENT_INVALID")
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
        if len(matching_books) != 1:
            raise NFLReadinessError(f"NFL_BINDING_BOOKMAKER_COUNT_INVALID:{clean_book}")
        markets = matching_books[0].get("markets")
        if not isinstance(markets, list):
            raise NFLReadinessError("NFL_BINDING_MARKETS_INVALID")

        for market_key, expected_names in (
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
            if market_key == "totals":
                names = [str(row.get("name") or "").strip().lower() for row in outcomes]
                expected = expected_names
            else:
                names = [str(row.get("name") or "").strip() for row in outcomes]
                expected = expected_names
            if any(not name for name in names):
                raise NFLReadinessError(f"NFL_BINDING_OUTCOME_NAME_MISSING:{market_key}")
            if len(set(names)) != 2:
                raise NFLReadinessError(f"NFL_BINDING_OUTCOME_DUPLICATE:{market_key}")
            if set(names) != expected:
                raise NFLReadinessError(f"NFL_BINDING_OUTCOME_PAIR_MISMATCH:{market_key}")
    return payload


def run_nfl_ready(
    *,
    promotion_registry: Mapping[str, Any],
    floor_path: str | Path = "config/truth_gate_floors.json",
    **kwargs: Any,
) -> NFLMachineReport:
    """Run canonical M2 and resolve real promotion/floor/price gates.

    Promotion is not a manual runtime flag.  The exact-head registry is rebuilt
    from historical validation, CI attestation and forward CLV evidence.  A
    market whose derived stage is DEPLOYED must resolve its NFL-namespaced frozen
    floor before M2 inference is permitted.  The existing Truth Gate owns the
    final OFFICIAL_BET decision.
    """
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
    supplied_odds = run_kwargs.get("odds_snapshot")
    if supplied_odds is not None:
        _validate_bettor_facing_odds_snapshot(supplied_odds, book_key=book_key)
    original_fetcher = run_kwargs.get("odds_fetcher")
    if original_fetcher is not None:
        if not callable(original_fetcher):
            raise NFLReadinessError("NFL_BINDING_ODDS_FETCHER_INVALID")

        def validated_fetcher() -> Mapping[str, Any]:
            fetched = original_fetcher()
            if not isinstance(fetched, Mapping):
                raise NFLReadinessError("NFL_BINDING_ODDS_FETCHER_OUTPUT_INVALID")
            _validate_bettor_facing_odds_snapshot(fetched, book_key=book_key)
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
    if truth_gate_rows:
        run_status = "SUCCESS"
    elif deployed_rows:
        run_status = "BLOCKED"
    else:
        run_status = "BLOCKED"
    return replace(report, results=ordered, summary=summary, run_status=run_status)
