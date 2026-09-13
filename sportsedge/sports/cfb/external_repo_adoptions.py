"""SportsEdge-native adaptations of useful public-repository engineering patterns.

Nothing in this module grants model, Truth Gate, promotion, eligibility, edge-floor,
or OFFICIAL authority.  It deliberately separates useful source/engineering ideas from
actual SportsEdge evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable, Mapping


class CFBExternalAdoptionError(ValueError):
    pass


def _dt(value: Any, field: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise CFBExternalAdoptionError(f"{field}:REQUIRED")
    try:
        out = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CFBExternalAdoptionError(f"{field}:INVALID") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise CFBExternalAdoptionError(f"{field}:TIMEZONE_REQUIRED")
    return out.astimezone(timezone.utc)


def validate_odds_event_timing(
    event: Mapping[str, Any], *, scheduled_start_utc: str, max_start_skew_seconds: int = 900
) -> dict[str, Any]:
    """Reject rescheduled/mismatched and post-kickoff sportsbook observations.

    Inspired by public CFB verification harnesses, independently implemented here.
    The provider event commence time must remain close to the canonical schedule and
    every bookmaker/market timestamp must precede the canonical game start.
    """
    if max_start_skew_seconds < 0:
        raise CFBExternalAdoptionError("MAX_START_SKEW_NEGATIVE")
    scheduled = _dt(scheduled_start_utc, "scheduled_start_utc")
    commence = _dt(event.get("commence_time"), "event.commence_time")
    skew = abs((commence - scheduled).total_seconds())
    if skew > max_start_skew_seconds:
        raise CFBExternalAdoptionError(
            f"ODDS_EVENT_START_MISMATCH:{int(skew)}>{int(max_start_skew_seconds)}"
        )

    checked = 0
    for book in event.get("bookmakers") or []:
        if not isinstance(book, Mapping):
            continue
        book_ts_raw = book.get("last_update")
        if book_ts_raw is not None:
            book_ts = _dt(book_ts_raw, "book.last_update")
            if book_ts >= scheduled:
                raise CFBExternalAdoptionError("POST_START_BOOK_QUOTE_FORBIDDEN")
            checked += 1
        for market in book.get("markets") or []:
            if not isinstance(market, Mapping) or market.get("last_update") is None:
                continue
            market_ts = _dt(market.get("last_update"), "market.last_update")
            if market_ts >= scheduled:
                raise CFBExternalAdoptionError("POST_START_MARKET_QUOTE_FORBIDDEN")
            checked += 1
    if checked == 0:
        raise CFBExternalAdoptionError("ODDS_QUOTE_TIMESTAMP_MISSING")
    return {
        "status": "TIMING_VALIDATED",
        "event_start_skew_seconds": skew,
        "timestamps_checked": checked,
        "promotion_authority": False,
        "model_p_authority": False,
    }


def build_cfbd_lines_research_benchmark(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Normalize CFBD/cfbfastR open/close fields as research-only benchmarks.

    These values are *not* paired PIT evidence because the endpoint fields alone do
    not prove independently observed decision/close timestamps.
    """
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        provider = str(row.get("provider") or row.get("provider_name") or "").strip()
        game_id = str(row.get("game_id") or row.get("id") or "").strip()
        if not game_id:
            continue
        normalized.append(
            {
                "game_id": game_id,
                "provider": provider or None,
                "spread": row.get("spread"),
                "spread_open": row.get("spread_open"),
                "over_under": row.get("over_under"),
                "over_under_open": row.get("over_under_open"),
                "home_moneyline": row.get("home_moneyline"),
                "away_moneyline": row.get("away_moneyline"),
            }
        )
    return {
        "schema_version": "CFB_CFBD_LINES_RESEARCH_BENCHMARK_V1",
        "status": "RESEARCH_BENCHMARK_NOT_PAIRED_PIT",
        "rows": normalized,
        "decision_and_close_prices_pit_proven": False,
        "promotion_authority": False,
        "truth_gate_input": False,
        "model_p_authority": False,
        "may_change_market_eligibility": False,
    }


def build_event_timestamped_replay_entry(
    *,
    source_contract: str,
    endpoint: str,
    target_season: int,
    target_week: int,
    as_of_week: int,
    source_event_time_utc: str,
    target_game_start_utc: str,
    snapshot_path: str,
    raw_bytes: bytes,
) -> dict[str, Any]:
    """Build one candidate EVENT_TIMESTAMPED_REPLAY manifest entry.

    This is only structural materialization.  It does not prove endpoint revision
    history or promotion fitness; the existing CFB PIT validator remains authority.
    """
    contract = str(source_contract or "").strip()
    endpoint_value = str(endpoint or "").strip()
    path = str(snapshot_path or "").strip()
    if not contract or not endpoint_value or not path:
        raise CFBExternalAdoptionError("REPLAY_ENTRY_REQUIRED_FIELD_MISSING")
    source_event = _dt(source_event_time_utc, "source_event_time_utc")
    target_start = _dt(target_game_start_utc, "target_game_start_utc")
    if source_event >= target_start:
        raise CFBExternalAdoptionError("REPLAY_SOURCE_EVENT_NOT_STRICTLY_PREGAME")
    if int(as_of_week) >= int(target_week):
        raise CFBExternalAdoptionError("REPLAY_ASOF_WEEK_MUST_PRECEDE_TARGET_WEEK")
    return {
        "source_contract": contract,
        "endpoint": endpoint_value,
        "target_season": int(target_season),
        "target_week": int(target_week),
        "as_of_week": int(as_of_week),
        "snapshot_path": path,
        "snapshot_sha256": sha256(raw_bytes).hexdigest(),
        "source_mode": "EVENT_TIMESTAMPED_REPLAY",
        "source_event_time_utc": source_event.isoformat(),
        "promotion_authority": False,
        "model_p_authority": False,
        "structural_candidate_only": True,
    }
