from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MARKET_ID_CONFIG = "config/market_id_canonicalization_v1.json"
EXPECTED_SCHEMA = "SPORTSEDGE_MARKET_ID_CANONICALIZATION_V1"
EXPECTED_STATUS = "FROZEN_PRE_EVIDENCE"


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
        "aliases_may_resolve_input_only",
        "aliases_do_not_inherit_certification",
        "unknown_market_ids_fail_closed",
    )
    if any(rules.get(key) is not True for key in required_true):
        raise MarketIdError("MARKET_ID_RULES_MUST_FAIL_CLOSED")
    return raw


def _sport_registry(sport: str, config: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(sport, str) or not sport.strip():
        raise MarketIdError("sport must be a non-empty string")
    sports = config.get("sports")
    if not isinstance(sports, Mapping):
        raise MarketIdError("MARKET_ID_SPORTS_REQUIRED")
    registry = sports.get(sport.strip().lower())
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
        if canonical not in normalized:
            raise MarketIdError(f"CANONICAL_ID_MUST_ALIAS_SELF:{canonical}")
        if needle in normalized:
            matches.append(canonical)
    if not matches:
        raise MarketIdError(f"UNKNOWN_MARKET_ID:{sport}:{market}")
    if len(matches) != 1:
        raise MarketIdError(f"AMBIGUOUS_MARKET_ID:{sport}:{market}")
    return matches[0]


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
