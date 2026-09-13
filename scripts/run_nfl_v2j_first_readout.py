#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from sportsedge.sports.nfl.history import normalize_nfl_rows, parse_schedule_csv
from sportsedge.sports.nfl.m2_history_features import fit_nfl_prior_decay_curves
from sportsedge.sports.nfl.m2_history_policy import build_nfl_m2_history_rows
from sportsedge.sports.nfl.m2_v2h_candidate import build_nfl_v2h_game_event_rows
from sportsedge.sports.nfl.m2_v2j_validation import build_nfl_m2_v2j_candidate_evidence
from scripts.run_nfl_production_validation import (
    _PBP_FIELDS, _PARTICIPATION_FIELDS, _DEPTH_FIELDS, _STADIUM_FIELDS,
    _files, _extend, _read_projected, bridge_preopening_away_origins,
    audit_starting_qb_coverage, apply_pinned_starting_qb_overrides,
)

_SCORING_PBP_FIELDS = {"game_id","posteam","drive","touchdown","td_team","play_type","field_goal_result","extra_point_result","two_point_conv_result","safety"}

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--schedule-file', type=Path, required=True); p.add_argument('--pbp-dir', type=Path, required=True)
    p.add_argument('--participation-dir', type=Path, required=True); p.add_argument('--depth-dir', type=Path, required=True)
    p.add_argument('--stadium-file', type=Path, required=True); p.add_argument('--source-manifest', type=Path, required=True)
    p.add_argument('--starter-override-file', type=Path, default=Path('config/nfl_historical_starter_overrides.json'))
    p.add_argument('--start-season', type=int, default=2016); p.add_argument('--end-season', type=int, default=2025)
    p.add_argument('--out', type=Path, required=True); args = p.parse_args()
    if (args.start_season,args.end_season)!=(2016,2025): raise SystemExit('NFL_V2J_FIRST_READOUT_FROZEN_WINDOW_REQUIRED')
    manifest = json.loads(args.source_manifest.read_text(encoding='utf-8'))
    manifest_hash = str(manifest.get('manifest_sha256') or '').lower()
    if len(manifest_hash)!=64: raise SystemExit('NFL_V2J_SOURCE_MANIFEST_REQUIRED')

    schedule = normalize_nfl_rows(parse_schedule_csv(args.schedule_file.read_text(encoding='utf-8-sig')), range(2016,2026))
    pbp_files = _files(args.pbp_dir,'play_by_play_{season}.{ext}',2016,2025)
    participation_files = _files(args.participation_dir,'pbp_participation_{season}.{ext}',2016,2025)
    depth_files = _files(args.depth_dir,'depth_charts_{season}.{ext}',2016,2025)
    pbp=[]; participation=[]; depth=[]; scoring_pbp=[]
    _extend(pbp,pbp_files,_PBP_FIELDS); _extend(participation,participation_files,_PARTICIPATION_FIELDS); _extend(depth,depth_files,_DEPTH_FIELDS)
    _extend(scoring_pbp,pbp_files,_SCORING_PBP_FIELDS)
    stadiums, bridges = bridge_preopening_away_origins(schedule, _read_projected(args.stadium_file,_STADIUM_FIELDS))
    prior_curves = fit_nfl_prior_decay_curves(schedule,pbp,min_train_seasons=2,weeks=range(1,7))
    before = audit_starting_qb_coverage(schedule,depth,eligible_seasons=prior_curves)
    overrides = json.loads(args.starter_override_file.read_text(encoding='utf-8'))
    depth, applied = apply_pinned_starting_qb_overrides(schedule,depth,overrides)
    after = audit_starting_qb_coverage(schedule,depth,eligible_seasons=prior_curves)
    if after: raise SystemExit(f'NFL_V2J_STARTING_QB_COVERAGE_GAPS:{len(after)}')
    exclusions={}
    history_rows = build_nfl_m2_history_rows(schedule,pbp,participation,depth,stadiums,prior_decay_curves=prior_curves,neutral_site_policy='exclude_from_evaluation',exclusion_report=exclusions)
    if not history_rows: raise SystemExit('NFL_V2J_HISTORY_ROWS_EMPTY')
    event_rows = build_nfl_v2h_game_event_rows(schedule, scoring_pbp)
    eligible_ids = {str(r.get('game_id') or '') for r in history_rows}
    event_rows = [r for r in event_rows if str(r.get('game_id') or '') in eligible_ids]
    evidence = build_nfl_m2_v2j_candidate_evidence(event_rows, history_rows, source_manifest_sha256=manifest_hash)
    evidence.update({
        'code_role':'RESEARCH_FIRST_READOUT_ONLY','historical_data_role':'REUSED_RESEARCH_HISTORY_NOT_FINAL_HOLDOUT',
        'point_in_time_history_row_count':len(history_rows),'event_row_count':len(event_rows),
        'market_prices_consumed_as_model_features':False,'prospective_outcomes_consumed_for_tuning':False,
        'v2h_or_v2i_readout_values_consumed_for_numeric_tuning':False,'starter_override_count':len(applied),
        'stadium_bridge_count':len(bridges),'environment_exclusions_by_season':{str(k):v for k,v in exclusions.items()},'nfl_props':'NO_ENGINE'
    })
    args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'status':evidence['status'],'model_id':evidence['model_id'],'historical':evidence['candidate_historical_evidence'],'signed_key_probability':evidence['candidate_distribution_profile']['signed_key_probability'],'source_manifest_sha256':manifest_hash,'promotion_authority':False},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
