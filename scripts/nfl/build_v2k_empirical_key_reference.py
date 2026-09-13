#!/usr/bin/env python3
"""Build the frozen NFL V2K signed key-number reference from raw game results.

This builder is intentionally market-blind.  It consumes only schedule/result fields
from a pinned nflverse games.csv snapshot and emits the four preregistered signed
margin masses together with provenance hashes.  It does not inspect V2K output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

SOURCE_REPOSITORY = "nflverse/nfldata"
SOURCE_COMMIT = "dffc0c00a5a2e6b87f4354a23cd213a617149971"
SOURCE_PATH = "data/games.csv"
SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    f"{SOURCE_REPOSITORY}/{SOURCE_COMMIT}/{SOURCE_PATH}"
)
SEASON_START = 2002
SEASON_END = 2025
INCLUDED_GAME_TYPES = ("REG", "WC", "DIV", "CON", "SB")
SIGNED_KEYS = (-7, -3, 3, 7)
ABSOLUTE_MASS_TOLERANCE = 0.005
REQUIRED_COLUMNS = {
    "game_id",
    "season",
    "game_type",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "location",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def _parse_score(value: str) -> int | None:
    value = value.strip()
    if value == "" or value.upper() == "NA":
        return None
    parsed = float(value)
    if not parsed.is_integer():
        raise ValueError(f"non-integer final score: {value!r}")
    return int(parsed)


def build_reference(raw: bytes, generated_at_utc: str, builder_sha256: str) -> dict:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ValueError("games.csv has no header")
    missing = REQUIRED_COLUMNS.difference(reader.fieldnames)
    if missing:
        raise ValueError(f"games.csv missing required columns: {sorted(missing)}")

    margins: Counter[int] = Counter()
    seen_game_ids: set[str] = set()
    game_count = 0
    neutral_site_count = 0
    excluded_unplayed_rows = 0
    included_type_counts: Counter[str] = Counter()

    for row in reader:
        season_raw = row["season"].strip()
        if not season_raw:
            continue
        season = int(float(season_raw))
        if not (SEASON_START <= season <= SEASON_END):
            continue

        game_type = row["game_type"].strip().upper()
        if game_type not in INCLUDED_GAME_TYPES:
            continue

        home_score = _parse_score(row["home_score"])
        away_score = _parse_score(row["away_score"])
        if home_score is None or away_score is None:
            excluded_unplayed_rows += 1
            continue

        game_id = row["game_id"].strip()
        if not game_id:
            raise ValueError("completed row missing game_id")
        if game_id in seen_game_ids:
            raise ValueError(f"duplicate completed game_id: {game_id}")
        seen_game_ids.add(game_id)

        margin = home_score - away_score
        margins[margin] += 1
        game_count += 1
        included_type_counts[game_type] += 1
        if row["location"].strip().lower() == "neutral":
            neutral_site_count += 1

    if game_count < 6000:
        raise ValueError(f"unexpectedly small completed-game sample: {game_count}")

    abs_three = (margins[3] + margins[-3]) / game_count
    abs_seven = (margins[7] + margins[-7]) / game_count
    if not 0.12 <= abs_three <= 0.18:
        raise ValueError(f"3-point mass failed corruption sanity bound: {abs_three:.6f}")
    if not 0.06 <= abs_seven <= 0.12:
        raise ValueError(f"7-point mass failed corruption sanity bound: {abs_seven:.6f}")

    distribution = [
        {"signed_margin": margin, "count": count}
        for margin, count in sorted(margins.items())
    ]
    source_manifest = {
        "dataset_id": "nflverse/nfldata games.csv",
        "dataset_version": SOURCE_COMMIT,
        "repository": SOURCE_REPOSITORY,
        "path": SOURCE_PATH,
        "url": SOURCE_URL,
        "season_scope": {
            "start": SEASON_START,
            "end": SEASON_END,
            "inclusive": True,
            "game_types": list(INCLUDED_GAME_TYPES),
            "completed_finals_only": True,
        },
        "sample_size": game_count,
        "signed_margin_convention": (
            "home_score - away_score; positive means the schedule-designated home "
            "team finished ahead"
        ),
        "neutral_site_assignment": (
            "neutral-site games are included; sign follows nflverse home_team/away_team "
            "designation rather than inferred venue ownership"
        ),
        "overtime_rule": (
            "official final score is used, including all overtime scoring; regulation-only "
            "margins are not reconstructed"
        ),
        "sportsbook_fields_used": [],
        "v2k_outputs_used": [],
        "excluded_unplayed_rows": excluded_unplayed_rows,
        "neutral_site_game_count": neutral_site_count,
        "included_game_type_counts": dict(sorted(included_type_counts.items())),
        "raw_source_sha256": sha256_bytes(raw),
        "builder_code_sha256": builder_sha256,
        "generated_at_utc": generated_at_utc,
    }

    signed_counts = {str(key): margins[key] for key in SIGNED_KEYS}
    signed_mass = {
        str(key): round(margins[key] / game_count, 12) for key in SIGNED_KEYS
    }

    return {
        "schema": "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V1",
        "status": "FROZEN_READY",
        "authority": "REFERENCE_ONLY_NO_MODEL_P_NO_PROMOTION_NO_STAKING",
        "purpose": (
            "Independent signed historical final-margin reference for V2K key-number "
            "validation. Built before any untouched V2K readout."
        ),
        "required_signed_keys": list(SIGNED_KEYS),
        "absolute_mass_tolerance": ABSOLUTE_MASS_TOLERANCE,
        "source_requirements": {
            "real_historical_games_only": True,
            "sportsbook_prices_forbidden": True,
            "v2k_simulations_forbidden": True,
            "hand_entered_reference_values_forbidden": True,
            "source_manifest_required": True,
            "raw_source_sha256_required": True,
            "builder_code_sha256_required": True,
            "season_scope_required": True,
            "game_count_required": True,
        },
        "freeze_requirements": {
            "signed_probabilities_required": True,
            "sum_of_full_margin_distribution_not_required_but_recommended": True,
            "built_before_any_untouched_v2k_readout": True,
            "immutable_after_untouched_readout": True,
        },
        "source_manifest": source_manifest,
        "reference": {
            "season_scope": source_manifest["season_scope"],
            "game_count": game_count,
            "raw_source_sha256": source_manifest["raw_source_sha256"],
            "builder_code_sha256": builder_sha256,
            "source_manifest_sha256": canonical_sha256(source_manifest),
            "full_signed_margin_distribution_sha256": canonical_sha256(distribution),
            "signed_margin_counts": signed_counts,
            "signed_margin_mass": signed_mass,
            "absolute_margin_3_mass": round(abs_three, 12),
            "absolute_margin_7_mass": round(abs_seven, 12),
        },
        "block_reason": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--generated-at-utc", required=True)
    args = parser.parse_args()

    raw = args.input.read_bytes()
    builder_sha256 = sha256_bytes(Path(__file__).read_bytes())
    reference = build_reference(raw, args.generated_at_utc, builder_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(reference, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    print(f"source_url={SOURCE_URL}")
    print(f"raw_source_sha256={reference['reference']['raw_source_sha256']}")
    print(f"builder_code_sha256={builder_sha256}")
    print(f"game_count={reference['reference']['game_count']}")
    print(f"signed_counts={reference['reference']['signed_margin_counts']}")
    print(f"signed_mass={reference['reference']['signed_margin_mass']}")
    print(f"absolute_margin_3_mass={reference['reference']['absolute_margin_3_mass']}")
    print(f"absolute_margin_7_mass={reference['reference']['absolute_margin_7_mass']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
