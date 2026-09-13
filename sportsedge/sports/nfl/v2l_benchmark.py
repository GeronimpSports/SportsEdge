"""Deterministic, provenance-bound M1 benchmark construction for NFL V2L.

Research comparator only. Sportsbook data here is never a V2L model input.
"""
from __future__ import annotations
import hashlib
import json
from typing import Mapping, Sequence

SCHEMA = "SPORTSEDGE_NFL_V2L_BENCHMARK_EVIDENCE_V1"


def _sha64(value: object, label: str) -> str:
    out = str(value or "")
    if len(out) != 64 or any(c not in "0123456789abcdefABCDEF" for c in out):
        raise ValueError(f"{label} must be a 64-character SHA256")
    return out.lower()


def _devig_two_way(home_american: float, away_american: float) -> tuple[float, float]:
    def implied(x: float) -> float:
        if x == 0: raise ValueError("zero American odds invalid")
        return 100.0 / (x + 100.0) if x > 0 else (-x) / ((-x) + 100.0)
    h, a = implied(float(home_american)), implied(float(away_american))
    z = h + a
    if z <= 0: raise ValueError("invalid paired market")
    return h / z, a / z


def build_m1_benchmark(*, captures: Sequence[Mapping[str, object]], benchmark_policy_sha256: str,
                       benchmark_source_manifest_sha256: str) -> dict:
    """Build immutable pregame M1 rows. Missing/unverifiable captures block."""
    policy_sha = _sha64(benchmark_policy_sha256, "benchmark_policy_sha256")
    manifest_sha = _sha64(benchmark_source_manifest_sha256, "benchmark_source_manifest_sha256")
    if not captures: raise ValueError("benchmark captures required")
    rows = []
    seen = set()
    for c in captures:
        required = ("game_id", "captured_at_utc", "kickoff_utc", "home_ml", "away_ml", "home_spread", "game_total", "capture_sha256")
        if any(c.get(k) in (None, "") for k in required): raise ValueError("complete benchmark capture required")
        gid = str(c["game_id"])
        if gid in seen: raise ValueError("one frozen benchmark capture per game required")
        seen.add(gid)
        if str(c["captured_at_utc"]) >= str(c["kickoff_utc"]): raise ValueError("benchmark capture must be pregame")
        capture_sha = _sha64(c["capture_sha256"], "capture_sha256")
        home_p, away_p = _devig_two_way(float(c["home_ml"]), float(c["away_ml"]))
        margin = -float(c["home_spread"])
        total = float(c["game_total"])
        if total <= 0: raise ValueError("positive game total required")
        rows.append({
            "game_id": gid,
            "captured_at_utc": str(c["captured_at_utc"]),
            "kickoff_utc": str(c["kickoff_utc"]),
            "capture_sha256": capture_sha,
            "home_win_probability": home_p,
            "away_win_probability": away_p,
            "market_margin": margin,
            "market_total": total,
            "home_score_mean": (total + margin) / 2.0,
            "away_score_mean": (total - margin) / 2.0,
        })
    rows.sort(key=lambda r: r["game_id"])
    out = {"schema": SCHEMA, "benchmark_id": "M1_CALIBRATED_MARKET_V1", "benchmark_policy_sha256": policy_sha,
           "benchmark_source_manifest_sha256": manifest_sha, "rows": rows,
           "model_p_authority": False, "promotion_authority": False, "official_authority": False}
    raw = json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    out["benchmark_evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    return out


def fold_joint_score_rmse(*, evidence: Mapping[str, object], game_ids: Sequence[str],
                          actual_scores: Mapping[str, Sequence[float]]) -> float:
    if evidence.get("schema") != SCHEMA: raise ValueError("benchmark evidence schema mismatch")
    by_game = {str(r["game_id"]): r for r in evidence.get("rows", [])}
    if not game_ids: raise ValueError("fold game ids required")
    squared = []
    for gid in game_ids:
        if gid not in by_game or gid not in actual_scores: raise ValueError("complete fold benchmark lineage required")
        actual = actual_scores[gid]
        if len(actual) != 2: raise ValueError("home/away actual score pair required")
        r = by_game[gid]
        squared.extend([(float(r["home_score_mean"])-float(actual[0]))**2,
                        (float(r["away_score_mean"])-float(actual[1]))**2])
    return (sum(squared) / len(squared)) ** 0.5
