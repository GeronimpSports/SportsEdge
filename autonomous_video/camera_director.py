from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraDecision:
    angle: str
    reason: str


WIDE_TERMS = {"coverage", "routes", "route", "spacing", "safety", "shell", "formation", "motion", "concept"}
TIGHT_TERMS = {"blocking", "block", "run fit", "run_fit", "protection", "blitz", "pressure", "gap", "line", "trench", "linebacker"}
BROADCAST_TERMS = {"result", "catch", "touchdown", "context", "emotion", "celebration", "sideline"}


def choose_camera(intent: str, available: set[str]) -> CameraDecision:
    text = intent.casefold()
    scores = {
        "wide": sum(term in text for term in WIDE_TERMS),
        "end_zone": sum(term in text for term in TIGHT_TERMS),
        "broadcast": sum(term in text for term in BROADCAST_TERMS),
    }
    order = ["wide", "end_zone", "broadcast"]
    ranked = sorted(order, key=lambda name: (scores[name], -order.index(name)), reverse=True)
    for angle in ranked:
        if angle in available and scores[angle] > 0:
            return CameraDecision(angle, f"{angle} best matches analysis intent: {intent}")
    for fallback in ("wide", "end_zone", "broadcast"):
        if fallback in available:
            return CameraDecision(fallback, f"fallback because preferred angle is unavailable for: {intent}")
    raise ValueError("no camera angles available")
