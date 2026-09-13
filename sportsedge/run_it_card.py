"""Fail-closed bettor-facing visibility rules for RUN IT output.

Diagnostic rows may contain blocked, research, PAPER, or rejected candidates.
Those rows are useful evidence, but they are never bettor-card selections.  This
module owns the final presentation boundary so an upstream status inconsistency
cannot turn a rejected candidate into a recommendation.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


_DISQUALIFYING_CANDIDATE_STATES = frozenset({
    "PAPER",
    "REJECTED",
    "BLOCKED",
    "NO_ENGINE",
    "EVIDENCE_BLOCKED",
    "FAIL",
    "FAILED",
    "INCONCLUSIVE",
})
_CANDIDATE_STATE_FIELDS = (
    "candidate_status",
    "candidate_state",
    "research_status",
    "model_state",
)


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def bettor_card_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only rows that are legitimately bettor-facing.

    ``OFFICIAL_BET`` is necessary but not sufficient when a diagnostic payload
    also carries candidate/gate metadata.  Any explicit predictive-gate failure,
    rejected/PAPER research state, explicit presentation veto, or non-positive
    stake suppresses the row.  Missing optional research metadata does not block a
    production OFFICIAL_BET because the production Truth Gate already owns that
    authority.
    """
    visible: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if _upper(row.get("bet_status")) != "OFFICIAL_BET":
            continue

        predictive_gate = row.get("predictive_gate")
        if predictive_gate is not None and _upper(predictive_gate) != "PASS":
            continue

        if any(
            _upper(row.get(field)) in _DISQUALIFYING_CANDIDATE_STATES
            for field in _CANDIDATE_STATE_FIELDS
            if row.get(field) is not None
        ):
            continue

        if row.get("bettor_card_presence") is False:
            continue

        if row.get("stake_units") is not None:
            try:
                stake_units = float(row["stake_units"])
            except (TypeError, ValueError):
                continue
            if stake_units <= 0:
                continue

        row["bettor_card_presence"] = True
        visible.append(row)
    return visible
