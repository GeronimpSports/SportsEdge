"""NFL V2K research-only football-native drive simulator.

No Model_P, promotion, staking, or OFFICIAL authority. This module implements
only the preregistered generative mechanics. Fitted parameters must come from
PIT-safe training data and an exact source manifest before untouched readout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping
import hashlib
import json
import numpy as np


V2K_SCHEMA = "SPORTSEDGE_NFL_V2K_DRIVE_SIM_V1"
DEFAULT_SEED = 20260913


class DriveOutcome(str, Enum):
    TD = "TD"
    FG = "FG"
    SAFETY = "SAFETY"
    DEF_ST_TD = "DEF_ST_TD"
    TURNOVER = "TURNOVER"
    PUNT_OTHER = "PUNT_OTHER"


@dataclass(frozen=True)
class V2KParams:
    drives_mean: float
    drives_sd: float
    start_yard_mean: float
    start_yard_sd: float
    shared_efficiency_sd: float
    outcome_probs: Mapping[str, float]
    pat_good: float = 0.94
    two_pt_attempt: float = 0.03
    two_pt_good: float = 0.48

    def validate(self) -> None:
        if self.drives_mean <= 0 or self.drives_sd < 0:
            raise ValueError("invalid drive-count parameters")
        if self.start_yard_sd < 0 or self.shared_efficiency_sd < 0:
            raise ValueError("invalid distribution parameters")
        keys = {x.value for x in DriveOutcome}
        if set(self.outcome_probs) != keys:
            raise ValueError("outcome taxonomy mismatch")
        probs = np.array([self.outcome_probs[k] for k in sorted(keys)], dtype=float)
        if np.any(probs < 0) or not np.isclose(float(probs.sum()), 1.0, atol=1e-12):
            raise ValueError("drive probabilities must sum to one")
        for p in (self.pat_good, self.two_pt_attempt, self.two_pt_good):
            if not 0.0 <= p <= 1.0:
                raise ValueError("conversion probability outside [0,1]")


def _normalized_probs(params: V2KParams, shared_efficiency: float) -> tuple[list[str], np.ndarray]:
    labels = [x.value for x in DriveOutcome]
    p = np.array([params.outcome_probs[k] for k in labels], dtype=float)
    # Shared game environment changes scoring efficiency for both teams and is
    # renormalized; it creates correlation without independent-Poisson scores.
    score_mask = np.array([1, 1, 0, 0, 0, 0], dtype=bool)
    p[score_mask] *= np.exp(shared_efficiency)
    p = p / p.sum()
    return labels, p


def _td_points(rng: np.random.Generator, params: V2KParams) -> int:
    if rng.random() < params.two_pt_attempt:
        return 8 if rng.random() < params.two_pt_good else 6
    return 7 if rng.random() < params.pat_good else 6


def _drive_points(rng: np.random.Generator, outcome: str, params: V2KParams) -> tuple[int, int]:
    if outcome == DriveOutcome.TD.value:
        return _td_points(rng, params), 0
    if outcome == DriveOutcome.FG.value:
        return 3, 0
    if outcome == DriveOutcome.SAFETY.value:
        return 0, 2
    if outcome == DriveOutcome.DEF_ST_TD.value:
        return 0, _td_points(rng, params)
    return 0, 0


def simulate_game(params_home: V2KParams, params_away: V2KParams, *, seed: int = DEFAULT_SEED) -> tuple[int, int]:
    params_home.validate(); params_away.validate()
    rng = np.random.Generator(np.random.PCG64(seed))
    shared = float(rng.normal(0.0, (params_home.shared_efficiency_sd + params_away.shared_efficiency_sd) / 2.0))
    # Shared pace component couples possession counts; minimum one possession.
    pace = float(rng.normal(0.0, 1.0))
    h_drives = max(1, int(round(params_home.drives_mean + params_home.drives_sd * pace)))
    a_drives = max(1, int(round(params_away.drives_mean + params_away.drives_sd * pace)))
    h_labels, h_probs = _normalized_probs(params_home, shared)
    a_labels, a_probs = _normalized_probs(params_away, shared)
    home = away = 0
    for _ in range(h_drives):
        # Starting field position is explicitly generated and retained as part
        # of the generative contract; fitted V2K outcome conditioning consumes
        # it once PIT training parameters are bound.
        _start = float(np.clip(rng.normal(params_home.start_yard_mean, params_home.start_yard_sd), 1.0, 99.0))
        hp, ap = _drive_points(rng, str(rng.choice(h_labels, p=h_probs)), params_home)
        home += hp; away += ap
    for _ in range(a_drives):
        _start = float(np.clip(rng.normal(params_away.start_yard_mean, params_away.start_yard_sd), 1.0, 99.0))
        ap, hp = _drive_points(rng, str(rng.choice(a_labels, p=a_probs)), params_away)
        away += ap; home += hp
    return home, away


def simulate_distribution(params_home: V2KParams, params_away: V2KParams, *, n: int = 50_000, seed: int = DEFAULT_SEED) -> dict:
    if n <= 0:
        raise ValueError("n must be positive")
    scores = np.empty((n, 2), dtype=np.int16)
    root = np.random.SeedSequence(seed)
    for i, child in enumerate(root.spawn(n)):
        child_seed = int(child.generate_state(1, dtype=np.uint64)[0])
        scores[i] = simulate_game(params_home, params_away, seed=child_seed)
    home = scores[:, 0].astype(int); away = scores[:, 1].astype(int)
    margin = home - away; total = home + away
    payload = {
        "schema": V2K_SCHEMA,
        "n": n,
        "seed": seed,
        "home_win_p": float(np.mean(margin > 0)),
        "tie_p": float(np.mean(margin == 0)),
        "mean_home": float(np.mean(home)),
        "mean_away": float(np.mean(away)),
        "mean_margin": float(np.mean(margin)),
        "mean_total": float(np.mean(total)),
        "signed_key_mass": {str(k): float(np.mean(margin == k)) for k in (-7, -3, 3, 7)},
        "model_p_authority": False,
        "promotion_authority": False,
        "official_authority": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["distribution_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload
