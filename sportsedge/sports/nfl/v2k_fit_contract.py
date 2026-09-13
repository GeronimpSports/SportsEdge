"""NFL V2K PIT fit/binding contract.

Research only. This module does not grant Model_P, promotion, staking, or
OFFICIAL authority. It validates that fitted V2K parameters are derived only
from rows strictly before the prediction cutoff and binds the fit to immutable
source/code identities before the simulator may consume it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping
import hashlib
import json

from .v2k_drive_simulator import DriveOutcome, V2KParams

FIT_SCHEMA = "SPORTSEDGE_NFL_V2K_PIT_FIT_V1"


@dataclass(frozen=True)
class DriveRow:
    game_id: str
    kickoff_utc: str
    offense: str
    start_yard: float
    outcome: str


def _dt(value: str) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return d.astimezone(timezone.utc)


def fit_pit(rows: Iterable[DriveRow], *, prediction_cutoff_utc: str,
            source_manifest_sha256: str, code_sha: str) -> dict:
    cutoff = _dt(prediction_cutoff_utc)
    accepted = []
    for r in rows:
        if _dt(r.kickoff_utc) >= cutoff:
            raise ValueError("PIT violation: training row at/after prediction cutoff")
        if r.outcome not in {x.value for x in DriveOutcome}:
            raise ValueError("unknown drive outcome")
        if not 1.0 <= float(r.start_yard) <= 99.0:
            raise ValueError("invalid starting field position")
        accepted.append(r)
    if not accepted:
        raise ValueError("no PIT-safe training rows")
    if len(source_manifest_sha256) != 64 or len(code_sha) < 7:
        raise ValueError("missing immutable source/code identity")

    counts = {x.value: 0 for x in DriveOutcome}
    starts = []
    games = {}
    for r in accepted:
        counts[r.outcome] += 1
        starts.append(float(r.start_yard))
        games.setdefault(r.game_id, 0)
        games[r.game_id] += 1
    n = len(accepted)
    mean_start = sum(starts) / n
    var_start = sum((x - mean_start) ** 2 for x in starts) / max(1, n - 1)
    drive_counts = list(games.values())
    mean_drives = sum(drive_counts) / len(drive_counts)
    var_drives = sum((x - mean_drives) ** 2 for x in drive_counts) / max(1, len(drive_counts) - 1)
    probs = {k: counts[k] / n for k in counts}

    fit = {
        "schema": FIT_SCHEMA,
        "prediction_cutoff_utc": cutoff.isoformat(),
        "source_manifest_sha256": source_manifest_sha256,
        "code_sha": code_sha,
        "training_rows": n,
        "training_games": len(games),
        "params": {
            "drives_mean": mean_drives,
            "drives_sd": var_drives ** 0.5,
            "start_yard_mean": mean_start,
            "start_yard_sd": var_start ** 0.5,
            "outcome_probs": probs,
        },
        "model_p_authority": False,
        "promotion_authority": False,
        "official_authority": False,
    }
    canonical = json.dumps(fit, sort_keys=True, separators=(",", ":")).encode()
    fit["fit_sha256"] = hashlib.sha256(canonical).hexdigest()
    return fit


def params_from_fit(fit: Mapping, *, expected_source_manifest_sha256: str,
                    expected_code_sha: str, shared_efficiency_sd: float = 0.0) -> V2KParams:
    if fit.get("schema") != FIT_SCHEMA:
        raise ValueError("fit schema mismatch")
    if fit.get("source_manifest_sha256") != expected_source_manifest_sha256:
        raise ValueError("train/serve source manifest mismatch")
    if fit.get("code_sha") != expected_code_sha:
        raise ValueError("train/serve code SHA mismatch")
    if any(bool(fit.get(k)) for k in ("model_p_authority", "promotion_authority", "official_authority")):
        raise ValueError("research fit cannot carry bettor-facing authority")
    p = fit["params"]
    return V2KParams(
        drives_mean=float(p["drives_mean"]),
        drives_sd=float(p["drives_sd"]),
        start_yard_mean=float(p["start_yard_mean"]),
        start_yard_sd=float(p["start_yard_sd"]),
        shared_efficiency_sd=float(shared_efficiency_sd),
        outcome_probs=dict(p["outcome_probs"]),
    )
