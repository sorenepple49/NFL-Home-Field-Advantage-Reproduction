#!/usr/bin/env python3
"""Record an explicit owner's decision to accept all 43 reconciled stadium records.

This is OWNER ACCEPTANCE of an audited, internally reconciled dataset. It is
NOT a claim that each external citation and all 5,310 historical game placements
were independently verified. This limitation is recorded in the output CSVs.

From the repository root:
    python code/nfl_venue/approve_all_stadiums_owner_signoff.py --check
    python code/nfl_venue/approve_all_stadiums_owner_signoff.py --apply

Do not run prepare_stadium_metadata.py without --finalize afterward: its
preview mode reconstructs REVIEW files and resets approval flags.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from datetime import datetime
import math
from pathlib import Path
import shutil
import sys

PATHS = {
    'checklist': Path('results/venue_models/final_stadium_audit/stadium_approval_checklist.csv'),
    'evidence': Path('results/venue_models/final_stadium_audit/stadium_attribute_evidence_RESEARCHED.csv'),
    'features': Path('results/venue_models/stadium_integration/stadium_features_REVIEW.csv'),
    'matches': Path('results/venue_models/stadium_integration/stadium_game_matches_REVIEW.csv'),
    'final_matches': Path('data/stadium_game_matches.csv'),
}
ALLOWED_ROOF = {'open','dome','retractable','canopy'}
APPROVAL_NOTE = ('OWNER ACCEPTANCE for exploratory M3: all 43 records have complete research links; '
                 '43/43 internal date and USGS checks passed; matching/counts and attributes reconciled. '
                 'The owner elected blanket approval; independent verification of every external '
                 'source and every historical game placement has NOT been completed. '
                 'USGS elevations are interpolated terrain estimates, not surveyed field altitudes.')

def require(ok, description):
    if not ok:
        raise ValueError(description)

def read(path):
    require(path.exists(), f'Missing file: {path}')
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        d = csv.DictReader(f)
        require(d.fieldnames is not None, f'Missing CSV header: {path}')
        return list(d.fieldnames), list(d)

def unique(rows, field, label):
    require(all((x.get(field) or '').strip() for x in rows), f'{label}: blank {field}')
    ids = [x[field].strip() for x in rows]
    require(len(set(ids)) == len(ids), f'{label}: duplicated {field}')
    return {x[field].strip(): x for x in rows}

def assert_columns(header, names, label):
    require(set(names).issubset(set(header)), f'{label}: missing columns {sorted(set(names) - set(header))}')

def valid_http(url):
    return (url or '').strip().lower().startswith(('https://','http://'))

def validated_tables():
    tables = {name: read(path) for name,path in PATHS.items()}
    hdr = {name: value[0] for name,value in tables.items()}
    rows = {name: value[1] for name,value in tables.items()}
    assert_columns(hdr['checklist'], ['venue_id','roof_type','manual_roof_signoff','manual_venue_history_signoff','matched_home_games'], 'checklist')
    assert_columns(hdr['evidence'], ['venue_id','roof_type','surface_type','altitude_m','matched_home_games','manual_roof_signoff',
        'manual_venue_history_signoff','historical_review_notes','approval_notes','verified','roof_evidence_url',
        'historical_identity_evidence_url','altitude_evidence_url','usgs_api_status','internal_venue_date_check'], 'evidence')
    assert_columns(hdr['features'], ['venue_id','roof_type','surface_type','altitude_m','matched_games','verified','review_note'], 'features')
    assert_columns(hdr['matches'], ['game_key','home_flag','stadium_id','match_status'], 'matches')
    assert_columns(hdr['final_matches'], ['game_key','stadium_id','match_status'], 'final matches')
    c = unique(rows['checklist'], 'venue_id', 'checklist')
    e = unique(rows['evidence'], 'venue_id', 'evidence')
    f = unique(rows['features'], 'venue_id', 'features')
    mr = unique(rows['matches'], 'game_key', 'matches')
    fm = unique(rows['final_matches'], 'game_key', 'final matches')
    require(len(c) == len(e) == len(f) == 43 and c.keys() == e.keys() == f.keys(),
            'The checklist, evidence and feature records do not have identical 43 venue IDs')
    require(len(mr) == len(fm) == 5395 and mr.keys() == fm.keys(), 'Game match crosswalks are not identical 5,395-key sets')
    counts = Counter()
    neutral = 0
    for key,m in mr.items():
        final = fm[key]
        require(m['match_status'] == final['match_status'] and (m['stadium_id'] or '') == (final['stadium_id'] or ''),
                f'Match crosswalk inconsistency for {key}')
        if m['home_flag'].strip() == '1':
            require(m['match_status'] == 'matched', f'Unresolved home-game match: {key}')
            counts[m['stadium_id']] += 1
        else:
            require(m['home_flag'].strip() == '0' and m['match_status'] != 'matched', f'Invalid neutral game {key}')
            neutral += 1
    require(sum(counts.values()) == 5310 and neutral == 85, f'Unexpected study counts: {sum(counts.values())} home, {neutral} neutral')
    for vid in sorted(f):
        row_e, row_f, row_c = e[vid], f[vid], c[vid]
        require(row_f['roof_type'].strip().lower() == row_e['roof_type'].strip().lower() == row_c['roof_type'].strip().lower(), f'{vid}: roof mismatch')
        require(row_f['roof_type'].strip().lower() in ALLOWED_ROOF, f'{vid}: unknown roof type')
        require(row_f['surface_type'].strip().lower() == row_e['surface_type'].strip().lower() and row_f['surface_type'].strip().lower() in {'grass','turf'}, f'{vid}: surface mismatch')
        require(math.isfinite(float(row_f['altitude_m'])) and
                abs(float(row_f['altitude_m']) - float(row_e['altitude_m'])) <= 0.01 and
                abs(float(row_c['altitude_m']) - float(row_e['altitude_m'])) <= 0.01,
                f'{vid}: elevation mismatch or not numeric')
        require(int(row_c['matched_home_games']) == int(row_e['matched_home_games']) == int(row_f['matched_games']) == counts[vid],
                f'{vid}: historical game count mismatch')
        require(row_e['usgs_api_status'].strip() == 'OK' and row_e['internal_venue_date_check'].strip() == 'PASS',
                f'{vid}: internal historical/USGS validation incomplete')
        require(all(valid_http(row_e.get(k)) for k in ['roof_evidence_url','altitude_evidence_url','historical_identity_evidence_url']),
                f'{vid}: incomplete evidence links')
        require(valid_http(row_f.get('source_url')), f'{vid}: missing feature source URL')
        for section, r in [('checklist',row_c), ('evidence',row_e)]:
            for k in ['manual_roof_signoff','manual_venue_history_signoff']:
                require(r[k].strip().upper() in {'PENDING','APPROVED'}, f'{vid}: unexpected {section} {k}: {r[k]!r}')
        require(row_e['verified'].strip().lower() in {'false','true','0','1'}, f'{vid}: unexpected evidence verified')
        require(row_f['verified'].strip().lower() in {'false','true','0','1'}, f'{vid}: unexpected feature verified')
    return tables

def annotate(old):
    old = old.strip()
    return old if APPROVAL_NOTE in old else ((old + ' | ') if old else '') + APPROVAL_NOTE

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    tables = validated_tables()
    print('PRECHECK PASS: 43 stadiums, 5,395 games, 5,310 matched homes, 85 neutral.')
    print('All 43 roof/surface/elevation/count fields agree and evidence URLs are present.')
    print('NOTE: Owner acceptance is NOT independent validation of every cited source/game.')
    if args.check:
        print('CHECK ONLY: no files modified.')
        return
    changed = ['checklist','evidence','features']
    for name in changed:
        header, rows = tables[name]
        for r in rows:
            if name in {'checklist','evidence'}:
                r['manual_roof_signoff'] = 'APPROVED'
                r['manual_venue_history_signoff'] = 'APPROVED'
            if name == 'evidence':
                r['verified'] = 'True'
                r['approval_notes'] = annotate(r.get('approval_notes',''))
                r['historical_review_notes'] = annotate(r.get('historical_review_notes',''))
            elif name == 'features':
                r['verified'] = 'True'
                r['review_note'] = annotate(r.get('review_note',''))
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backups = {name: PATHS[name].with_name(PATHS[name].name+f'.before_owner_approval_{stamp}.bak') for name in changed}
    for name,bp in backups.items():
        require(not bp.exists(), f'Backup path already exists: {bp}')
    for name,bp in backups.items():
        shutil.copy2(PATHS[name],bp)
    try:
        for name in changed:
            h,rows = tables[name]
            tmp = PATHS[name].with_name(PATHS[name].name+'.owner_approval_tmp')
            with tmp.open('w',encoding='utf-8-sig',newline='') as fh:
                writer = csv.DictWriter(fh,fieldnames=h,lineterminator='\n')
                writer.writeheader(); writer.writerows(rows)
            tmp.replace(PATHS[name])
        post = validated_tables()
        for name in changed:
            for r in post[name][1]:
                if name in {'checklist','evidence'}:
                    require(r['manual_roof_signoff']=='APPROVED' and r['manual_venue_history_signoff']=='APPROVED',f'Unapproved {name} row')
                if name in {'features','evidence'}:
                    require(r['verified']=='True',f'Unverified {name} row')
    except Exception as exc:
        for name,bp in backups.items():
            shutil.copy2(bp, PATHS[name])
        raise ValueError(f'Approval failed and backups restored: {exc}') from exc
    print('APPLY PASS: all 43 checklist/evidence/feature records now owner-approved.')
    print('Three files backed up; original game data, matching and surfaces unchanged.')
    print('Limitation documented in approval_notes, historical_review_notes, and review_note.')
    print('NEXT: python code/nfl_venue/prepare_stadium_metadata.py --finalize')
    print('DO NOT run prepare_stadium_metadata.py in preview mode (without --finalize).')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, csv.Error) as exc:
        print('OWNER APPROVAL ERROR:', exc, file=sys.stderr)
        sys.exit(2)
