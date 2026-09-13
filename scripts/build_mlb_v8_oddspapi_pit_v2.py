#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, tempfile
from collections import Counter
from datetime import timedelta
from pathlib import Path
try:
    import scripts.build_mlb_v8_oddspapi_pit as v1
except ModuleNotFoundError:
    import build_mlb_v8_oddspapi_pit as v1

ROOT=Path('artifacts/mlb_v8_replay_sources/ODDSPAPI_HISTORICAL')
OUT=Path('artifacts/mlb_v8_replay_archive/oddspapi_pit_v2')
ATT_SCHEMA='MLB_V8_ACTUAL_FIRST_PLAY_ATTESTATION_V1'

def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()

def _raw_bound(root:Path, relpath, expected_sha)->bool:
    if not relpath or not expected_sha:return False
    p=root/str(relpath)
    if not p.is_file():return False
    return sha(p.read_bytes())==str(expected_sha)

def attestation(root, fixture_path, fixture):
    p=root/'actual_starts'/f"{fixture.get('fixtureId')}.json"
    if not p.is_file(): return None
    a=json.loads(p.read_text())
    checks=[
        a.get('schema')==ATT_SCHEMA,
        a.get('source')=='MLB_STATSAPI_GAME_FEED',
        a.get('promotion_authority') is False,
        a.get('retroactive_point_in_time_claim') is False,
        str(a.get('fixture_id'))==str(fixture.get('fixtureId')),
        a.get('fixture_sha256')==sha(fixture_path.read_bytes()),
        _raw_bound(root,a.get('schedule_payload_path'),a.get('schedule_payload_sha256')),
        _raw_bound(root,a.get('game_feed_payload_path'),a.get('game_feed_payload_sha256')),
    ]
    if not all(checks): return None
    try:v1._parse_ts(a['actual_first_play_utc'])
    except Exception:return None
    return a

def binding(book,market_id,player_id,info,outcome_ids):
    obj={'book':book,'market_id':market_id,'player_id':player_id,'handicap':info.get('handicap'),'period':info.get('period'),'market_type':info.get('marketType'),'outcome_ids':list(outcome_ids)}
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def build(root:Path,out:Path):
    catalog,catalog_sha=v1._load_catalog(root); rows=[]; failures=[]; counts=Counter()
    for fp in sorted(root.glob('????-??-??/*/fixture.normalized.json')):
        try:
            fixture=json.loads(fp.read_text()); att=attestation(root,fp,fixture)
            if att is None: counts['missing_or_invalid_actual_start_attestation']+=1; continue
            actual=v1._parse_ts(att['actual_first_play_utc']); target=actual-timedelta(minutes=v1.DECISION_MINUTES)
        except Exception as e: failures.append({'path':fp.as_posix(),'reason':f'FIXTURE_ATTESTATION_INVALID:{type(e).__name__}:{e}'}); continue
        for hp in sorted(fp.parent.glob('history_*.json')):
            if hp.name.endswith('.meta.json'): continue
            try:
                raw,_=v1._verify_raw(hp); payload=json.loads(raw)
                if str(payload.get('fixtureId'))!=str(fixture.get('fixtureId')): raise RuntimeError('FIXTURE_ID_MISMATCH')
            except Exception as e: failures.append({'path':hp.as_posix(),'reason':f'HISTORY_INVALID:{type(e).__name__}:{e}'}); continue
            for book,br in sorted((payload.get('bookmakers') or {}).items()):
                if not isinstance(br,dict): continue
                for mid,market in sorted((br.get('markets') or {}).items()):
                    info=catalog.get(str(mid)); om=market.get('outcomes') or {}
                    if not info or not isinstance(om,dict) or len(om)!=2: counts['market_or_binary_blocked']+=1; continue
                    ids=tuple(sorted(str(x) for x in om)); ors=[om[ids[0]],om[ids[1]]]
                    for pid in v1._player_ids(ors):
                        left,right=v1._timeline(ors[0],pid),v1._timeline(ors[1],pid)
                        decision=v1._state_pair(left,right,cutoff=target,max_age_seconds=v1.CANONICAL_TOLERANCE_SECONDS)
                        if decision is None: counts['no_actual_t30_pair']+=1; continue
                        close=v1._state_pair(left,right,cutoff=actual-timedelta(microseconds=1),max_age_seconds=None)
                        if close and min(close[0]['_ts'],close[1]['_ts'])<=max(decision[0]['_ts'],decision[1]['_ts']): close=None
                        a,b=decision; names=v1._catalog_outcomes(info)
                        row={'schema':'MLB_V8_ODDSPAPI_PIT_PAIR_V2','source':'ODDSPAPI_HISTORICAL','fixture_id':str(fixture.get('fixtureId')),'provider_scheduled_start_utc':v1._parse_ts(fixture['startTime']).isoformat(),'actual_first_play_utc':actual.isoformat(),'actual_start_feed_sha256':att['game_feed_payload_sha256'],'actual_start_feed_path':att['game_feed_payload_path'],'decision_target_utc':target.isoformat(),'decision_target_minutes_before_actual_first_play':v1.DECISION_MINUTES,'bookmaker':str(book),'market_id':str(mid),'market_name':info.get('marketName'),'market_type':info.get('marketType'),'period':info.get('period'),'handicap':info.get('handicap'),'player_id':pid,'threshold_binding_sha256':binding(str(book),str(mid),pid,info,(ids[0],ids[1])),'same_book_same_threshold_bound':True,'outcome_a_id':ids[0],'outcome_a_name':names.get(ids[0]),'outcome_a_decimal':a['_price'],'outcome_a_quote_utc':a['_ts'].isoformat(),'outcome_b_id':ids[1],'outcome_b_name':names.get(ids[1]),'outcome_b_decimal':b['_price'],'outcome_b_quote_utc':b['_ts'].isoformat(),'history_sha256':sha(raw),'market_catalog_sha256':catalog_sha,'promotion_authority':False,'close_available':bool(close)}
                        if close:
                            ca,cb=close; row.update({'close_outcome_a_decimal':ca['_price'],'close_outcome_a_quote_utc':ca['_ts'].isoformat(),'close_outcome_b_decimal':cb['_price'],'close_outcome_b_quote_utc':cb['_ts'].isoformat(),'close_after_decision':min(ca['_ts'],cb['_ts'])>max(a['_ts'],b['_ts']),'close_before_actual_first_play':max(ca['_ts'],cb['_ts'])<actual,'close_same_book_same_threshold':True})
                            if not row['close_before_actual_first_play']: raise RuntimeError('POST_START_CLOSE_ADMITTED')
                            counts['actual_start_bound_paired_closes']+=1
                        rows.append(row); counts['actual_start_bound_t30_pairs']+=1
    out.mkdir(parents=True,exist_ok=True)
    with (out/'pit_pairs.jsonl').open('w') as f:
        for r in rows:f.write(json.dumps(r,sort_keys=True)+'\n')
    summary={'schema':'MLB_V8_ODDSPAPI_PIT_ARCHIVE_V2','actual_start_required':True,'actual_start_raw_provenance_required':True,'same_book_same_threshold_required':True,'rows':len(rows),'counts':dict(counts),'failures':failures,'promotion_eligible':False,'promotion_reason':'PAIRED_PRICE_EVIDENCE_ALONE_DOES_NOT_SATISFY_MODEL_REPLAY_HOLDOUT_CALIBRATION_OR_TRUTH_GATE'}
    v1._write_json(out/'summary.json',summary); return summary

def self_test():
    x={'handicap':7.5,'period':'FT','marketType':'TOTAL'}
    assert binding('draftkings','12','0',x,('over','under'))==binding('draftkings','12','0',x,('over','under'))
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); rel='actual_starts/raw/fixture-1/game_feed.json'; p=root/rel
        p.parent.mkdir(parents=True); raw=b'{"fixture":"fixture-1"}'; p.write_bytes(raw)
        assert _raw_bound(root,rel,sha(raw))
        assert not _raw_bound(root,rel,'0'*64)
        assert not _raw_bound(root,'actual_starts/raw/fixture-1/missing.json',sha(raw))
        assert not _raw_bound(root,None,sha(raw))
    print(json.dumps({'status':'SELF_TEST_OK','actual_start_required':True,'actual_start_raw_provenance_required':True,'raw_sha_binding_exercised':True,'promotion_authority':False})); return 0

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--out',type=Path,default=OUT);p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:return self_test()
    print(json.dumps(build(a.root,a.out),indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
