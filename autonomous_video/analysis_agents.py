from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from .schema import PlayRecord


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    agent: str
    category: str
    text: str
    evidence_ids: tuple[str, ...]
    confidence: float
    scope: str = "indexed_plays"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_ids"] = list(self.evidence_ids)
        return data


def _claim_id(agent: str, text: str, evidence_ids: list[str]) -> str:
    raw = f"{agent}|{text}|{'|'.join(sorted(evidence_ids))}"
    return "cl_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_baseline_claims(
    *,
    plays: list[PlayRecord],
    evidence_index: list[dict[str, Any]],
    analytics: dict[str, Any],
) -> list[ClaimRecord]:
    evidence_by_play = {str(item["play_id"]): str(item["evidence_id"]) for item in evidence_index}
    claims: list[ClaimRecord] = []

    by_team: dict[str, list[PlayRecord]] = {}
    for play in plays:
        if play.offense:
            by_team.setdefault(play.offense, []).append(play)

    for team, team_plays in sorted(by_team.items()):
        team_metrics = analytics.get("teams", {}).get(team, {})
        explosive = [p for p in team_plays if p.explosive is True]
        if explosive:
            evidence_ids = [evidence_by_play[p.play_id] for p in explosive if p.play_id in evidence_by_play]
            text = f"{team} produced {len(explosive)} explosive play(s) among the indexed plays."
            claims.append(
                ClaimRecord(
                    claim_id=_claim_id("advanced_analytics", text, evidence_ids),
                    agent="advanced_analytics",
                    category="explosiveness",
                    text=text,
                    evidence_ids=tuple(evidence_ids),
                    confidence=0.99,
                )
            )

        known_success = [p for p in team_plays if p.success is not None]
        success_rate = team_metrics.get("success_rate")
        if known_success and success_rate is not None:
            evidence_ids = [evidence_by_play[p.play_id] for p in known_success if p.play_id in evidence_by_play]
            text = (
                f"{team} had a {success_rate:.1%} success rate on indexed plays "
                f"where down, distance, and yards gained were available."
            )
            claims.append(
                ClaimRecord(
                    claim_id=_claim_id("advanced_analytics", text, evidence_ids),
                    agent="advanced_analytics",
                    category="efficiency",
                    text=text,
                    evidence_ids=tuple(evidence_ids),
                    confidence=0.95,
                )
            )

        epa_per_play = team_metrics.get("epa_per_play")
        epa_plays = [p for p in team_plays if p.epa is not None]
        if epa_plays and epa_per_play is not None:
            evidence_ids = [evidence_by_play[p.play_id] for p in epa_plays if p.play_id in evidence_by_play]
            text = f"{team} averaged {epa_per_play:+.3f} EPA per indexed play with EPA available."
            claims.append(
                ClaimRecord(
                    claim_id=_claim_id("advanced_analytics", text, evidence_ids),
                    agent="advanced_analytics",
                    category="epa",
                    text=text,
                    evidence_ids=tuple(evidence_ids),
                    confidence=0.99,
                )
            )

    return claims


def reconcile_claims(
    claims: list[ClaimRecord],
    *,
    valid_evidence_ids: set[str],
    minimum_confidence: float = 0.75,
) -> dict[str, Any]:
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_text: set[str] = set()

    for claim in claims:
        reasons: list[str] = []
        if not claim.evidence_ids:
            reasons.append("no_evidence")
        missing = [eid for eid in claim.evidence_ids if eid not in valid_evidence_ids]
        if missing:
            reasons.append("missing_evidence")
        if claim.confidence < minimum_confidence:
            reasons.append("low_confidence")
        if claim.text in seen_text:
            reasons.append("duplicate_claim")

        row = claim.to_dict()
        row["reconciliation_reasons"] = reasons
        if reasons:
            row["status"] = "REJECTED"
            rejected.append(row)
        else:
            row["status"] = "APPROVED"
            approved.append(row)
            seen_text.add(claim.text)

    return {
        "minimum_confidence": minimum_confidence,
        "approved": approved,
        "rejected": rejected,
        "approved_count": len(approved),
        "rejected_count": len(rejected),
    }
