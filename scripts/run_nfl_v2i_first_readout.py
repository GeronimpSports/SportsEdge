#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sportsedge.sports.nfl.history import parse_schedule_csv
from sportsedge.sports.nfl.m2_v2h_candidate import build_nfl_v2h_game_event_rows
from sportsedge.sports.nfl.m2_v2i_validation import build_nfl_m2_v2i_candidate_evidence
from sportsedge.sports.nfl.source_manifest import manifest_sha256
from scripts.build_nfl_v2g_source_bound_artifact import (
    _identity_scoped_pbp, _load_manifest, _normalize_schedule_team_aliases,
    _pbp_path, _read_projected, _verify_source,
)

PBP_FIELDS = {
    "game_id", "posteam", "drive", "touchdown", "td_team", "play_type",
    "field_goal_result", "extra_point_result", "two_point_conv_result", "safety",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule-file", type=Path, required=True)
    parser.add_argument("--pbp-dir", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--start-season", type=int, default=2016)
    parser.add_argument("--end-season", type=int, default=2025)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if (args.start_season, args.end_season) != (2016, 2025):
        raise SystemExit("NFL_V2I_FIRST_READOUT_FROZEN_WINDOW_REQUIRED")

    manifest, expected, manifest_sha = _load_manifest(args.source_manifest)
    if manifest_sha != manifest_sha256(manifest):
        raise SystemExit("NFL_V2I_MANIFEST_HASH_MISMATCH")
    _verify_source(args.schedule_file, expected.get("schedule"), "schedule")

    schedule_rows = []
    for raw in parse_schedule_csv(args.schedule_file.read_text(encoding="utf-8-sig")):
        try:
            season = int(float(raw.get("season") or 0))
        except (TypeError, ValueError):
            continue
        if 2016 <= season <= 2025 and str(raw.get("game_type") or "REG").upper() == "REG":
            schedule_rows.append(dict(raw))
    schedule_rows, alias_applications = _normalize_schedule_team_aliases(schedule_rows)

    pbp_rows = []
    ignored = 0
    for season in range(2016, 2026):
        path = _pbp_path(args.pbp_dir, season)
        label = f"pbp_{season}"
        _verify_source(path, expected.get(label), label)
        scoped, dropped = _identity_scoped_pbp(_read_projected(path, PBP_FIELDS))
        pbp_rows.extend(scoped)
        ignored += dropped

    event_rows = build_nfl_v2h_game_event_rows(schedule_rows, pbp_rows)
    evidence = build_nfl_m2_v2i_candidate_evidence(event_rows, source_manifest_sha256=manifest_sha)
    evidence.update({
        "code_role": "RESEARCH_FIRST_READOUT_ONLY",
        "historical_data_role": "REUSED_RESEARCH_HISTORY_NOT_FINAL_HOLDOUT",
        "event_row_count": len(event_rows),
        "ignored_unscoped_pbp_row_count": ignored,
        "team_alias_application_count": len(alias_applications),
        "market_prices_consumed_as_model_features": False,
        "prospective_outcomes_consumed_for_tuning": False,
        "v2h_readout_values_consumed_for_numeric_tuning": False,
        "nfl_props": "NO_ENGINE",
    })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": evidence["status"],
        "model_id": evidence["model_id"],
        "historical": evidence["candidate_historical_evidence"],
        "signed_key_probability": evidence["candidate_distribution_profile"]["signed_key_probability"],
        "source_manifest_sha256": evidence["source_manifest_sha256"],
        "promotion_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
