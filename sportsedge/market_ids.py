from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MARKET_ID_CONFIG = "config/market_id_canonicalization_v1.json"
EXPECTED_SCHEMA = "SPORTSEDGE_MARKET_ID_CANONICALIZATION_V1"
EXPECTED_STATUS = "FROZEN_PRE_EVIDENCE"
EXPECTED_EVIDENCE_FORMAT = "sport:canonical_market_id"


class MarketIdError(ValueError):
    pass


def load_market_id_config(path: str = DEFAULT_MARKET_ID_CONFIG) -> Mapping[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise MarketIdError(f"unable to load market-id config: {path}") from exc
    if not isinstance(raw, Mapping):
        raise MarketIdError("market-id config root must be an object")
    if raw.get("schema") != EXPECTED_SCHEMA or raw.get("status") != EXPECTED_STATUS:
        raise MarketIdError("MARKET_ID_REGISTRY_NOT_FROZEN_V1")
    rules = raw.get("rules")
    if not isinstance(rules, Mapping):
        raise MarketIdError("MARKET_ID_RULES_REQUIRED")
    required_true = (
        "evidence_rows_must_store_canonical_id",
        "evidence_identity_is_sport_scoped",
        "aliases_may_resolve_input_only",
        "aliases_do_not_inherit_certification",
        "unknown_market_ids_fail_closed",
    )
    if any(rules.get(key) is not True for key in required_true):
        raise MarketIdError("MARKET_ID_RULES_MUST_FAIL_CLOSED")
    evidence_identity = raw.get("evidence_identity")
    if not isinstance(evidence_identity, Mapping):
        raise MarketIdError("MARKET_ID_EVIDENCE_IDENTITY_REQUIRED")
    if evidence_identity.get("format") != EXPECTED_EVIDENCE_FORMAT:
        raise MarketIdError("MARKET_ID_EVIDENCE_FORMAT_INVALID")
    if evidence_identity.get("aliases_permitted_in_persisted_identity") is not False:
        raise MarketIdError("MARKET_ID_ALIAS_PERSISTENCE_MUST_BE_DISABLED")
    return raw


def _normalized_sport(sport: str) -> str:
    if not isinstance(sport, str) or not sport.strip():
        raise MarketIdError("sport must be a non-empty string")
    return sport.strip().lower()


def _sport_registry(sport: str, config: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized_sport = _normalized_sport(sport)
    sports = config.get("sports")
    if not isinstance(sports, Mapping):
        raise MarketIdError("MARKET_ID_SPORTS_REQUIRED")
    registry = sports.get(normalized_sport)
    if not isinstance(registry, Mapping):
        raise MarketIdError(f"UNKNOWN_MARKET_ID_SPORT:{sport}")
    return registry


def canonical_market_id(
    sport: str,
    market: str,
    *,
    config: Mapping[str, Any] | None = None,
    path: str = DEFAULT_MARKET_ID_CONFIG,
) -> str:
    if not isinstance(market, str) or not market.strip():
        raise MarketIdError("market must be a non-empty string")
    cfg = config if config is not None else load_market_id_config(path)
    registry = _sport_registry(sport, cfg)
    needle = market.strip()
    matches: list[str] = []
    for canonical, aliases in registry.items():
        if not isinstance(canonical, str) or not canonical.strip():
            raise MarketIdError("INVALID_CANONICAL_MARKET_ID")
        if not isinstance(aliases, list) or not aliases:
            raise MarketIdError(f"MARKET_ID_ALIASES_REQUIRED:{canonical}")
        normalized = [str(alias).strip() for alias in aliases]
        if any(not alias for alias in normalized):
            raise MarketIdError(f"EMPTY_MARKET_ID_ALIAS:{canonical}")
        if len(normalized) != len(set(normalized)):
            raise MarketIdError(f"DUPLICATE_MARKET_ID_ALIAS:{canonical}")
        if canonical not in normalized:
            raise MarketIdError(f"CANONICAL_ID_MUST_ALIAS_SELF:{canonical}")
        if needle in normalized:
            matches.append(canonical)
    if not matches:
        raise MarketIdError(f"UNKNOWN_MARKET_ID:{sport}:{market}")
    if len(matches) != 1:
        raise MarketIdError(f"AMBIGUOUS_MARKET_ID:{sport}:{market}")
    return matches[0]


def canonical_evidence_market_id(
    sport: str,
    market: str,
    *,
    config: Mapping[str, Any] | None = None,
    path: str = DEFAULT_MARKET_ID_CONFIG,
) -> str:
    cfg = config if config is not None else load_market_id_config(path)
    normalized_sport = _normalized_sport(sport)
    canonical = canonical_market_id(normalized_sport, market, config=cfg)
    return f"{normalized_sport}:{canonical}"


def aliases_for_canonical(
    sport: str,
    canonical: str,
    *,
    config: Mapping[str, Any] | None = None,
    path: str = DEFAULT_MARKET_ID_CONFIG,
) -> tuple[str, ...]:
    cfg = config if config is not None else load_market_id_config(path)
    registry = _sport_registry(sport, cfg)
    resolved = canonical_market_id(sport, canonical, config=cfg)
    aliases = registry.get(resolved)
    if not isinstance(aliases, list) or not aliases:
        raise MarketIdError(f"MARKET_ID_ALIASES_REQUIRED:{resolved}")
    return tuple(str(alias).strip() for alias in aliases)
