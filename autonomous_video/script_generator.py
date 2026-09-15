from __future__ import annotations

import hashlib
from typing import Any


def build_evidence_bound_script(reconciliation: dict[str, Any]) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for index, claim in enumerate(reconciliation.get("approved", []), start=1):
        evidence_ids = list(claim["evidence_ids"])
        raw = f"{claim['claim_id']}|{index}"
        segment_id = "seg_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        segments.append(
            {
                "segment_id": segment_id,
                "claim_id": claim["claim_id"],
                "narration": claim["text"],
                "evidence_ids": evidence_ids,
                "visual_instructions": {
                    "mode": "show_supporting_play_or_analytics_graphic",
                    "preferred_evidence_ids": evidence_ids,
                },
            }
        )

    return {
        "status": "EVIDENCE_BOUND_DRAFT",
        "segments": segments,
        "segment_count": len(segments),
        "rule": "No factual narration segment may exist without approved evidence IDs.",
    }
