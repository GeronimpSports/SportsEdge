from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PlayRecord:
    play_id: str
    game_id: str
    period: int | None
    clock: str | None
    offense: str | None
    defense: str | None
    down: int | None
    distance: int | None
    yards_gained: int | None
    play_type: str | None
    play_text: str | None
    epa: float | None
    success: bool | None
    explosive: bool | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    game_id: str
    play_id: str
    evidence_type: str
    summary: str
    confidence: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _clock_to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        minutes = value.get("minutes")
        seconds = value.get("seconds")
        if minutes is not None and seconds is not None:
            return f"{int(minutes):02d}:{int(seconds):02d}"
    return str(value)


def _infer_success(down: int | None, distance: int | None, yards: int | None) -> bool | None:
    if down is None or distance is None or yards is None or distance <= 0:
        return None
    if down == 1:
        return yards >= 0.50 * distance
    if down == 2:
        return yards >= 0.70 * distance
    return yards >= distance


def _infer_explosive(play_type: str | None, yards: int | None) -> bool | None:
    if yards is None:
        return None
    label = (play_type or "").lower()
    if "pass" in label:
        return yards >= 20
    if "rush" in label or "run" in label:
        return yards >= 10
    return yards >= 15


def normalize_play(raw: dict[str, Any], *, fallback_game_id: str, source: str) -> PlayRecord:
    game_id = str(_first(raw, "gameId", "game_id") or fallback_game_id)
    period = _first(raw, "period", "quarter")
    down = _first(raw, "down")
    distance = _first(raw, "distance")
    yards = _first(raw, "yardsGained", "yards_gained")
    play_type = _first(raw, "playType", "play_type")
    play_text = _first(raw, "playText", "play_text")
    epa = _first(raw, "epa", "ppa")
    success = _first(raw, "success")
    explosive = _first(raw, "explosive")

    period = int(period) if period is not None else None
    down = int(down) if down is not None else None
    distance = int(distance) if distance is not None else None
    yards = int(yards) if yards is not None else None
    epa = float(epa) if epa is not None else None
    if success is None:
        success = _infer_success(down, distance, yards)
    else:
        success = bool(success)
    if explosive is None:
        explosive = _infer_explosive(play_type, yards)
    else:
        explosive = bool(explosive)

    raw_id = _first(raw, "id", "playId", "play_id")
    if raw_id is None:
        identity = "|".join(
            [
                game_id,
                str(period),
                str(_clock_to_text(_first(raw, "clock"))),
                str(_first(raw, "offense", "team")),
                str(play_text),
            ]
        )
        raw_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]

    return PlayRecord(
        play_id=str(raw_id),
        game_id=game_id,
        period=period,
        clock=_clock_to_text(_first(raw, "clock")),
        offense=_first(raw, "offense", "team"),
        defense=_first(raw, "defense"),
        down=down,
        distance=distance,
        yards_gained=yards,
        play_type=str(play_type) if play_type is not None else None,
        play_text=str(play_text) if play_text is not None else None,
        epa=epa,
        success=success,
        explosive=explosive,
        source=source,
    )


def build_evidence(play: PlayRecord) -> EvidenceRecord:
    identity = f"{play.game_id}:{play.play_id}:play"
    evidence_id = "ev_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    pieces = []
    if play.period is not None:
        pieces.append(f"Q{play.period}")
    if play.clock:
        pieces.append(play.clock)
    if play.offense:
        pieces.append(play.offense)
    if play.play_text:
        pieces.append(play.play_text)
    summary = " | ".join(pieces)
    return EvidenceRecord(
        evidence_id=evidence_id,
        game_id=play.game_id,
        play_id=play.play_id,
        evidence_type="play",
        summary=summary,
        confidence=1.0,
        source=play.source,
    )
