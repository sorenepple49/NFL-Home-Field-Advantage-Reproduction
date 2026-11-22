#!/usr/bin/env python3
"""Audit per-game NFL stadium surface history without guessing missing years.

Run from the repository root, after prepare_stadium_metadata.py:
  python code/nfl_venue/build_surface_review.py
The preview is NOT approved for modeling. To publish a final, verified per-game
surface file (only after manual review and final stadium data):
  python code/nfl_venue/build_surface_review.py --finalize
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

ROOT = Path.cwd()
REVIEW = ROOT / 'results/venue_models/stadium_integration'
HISTORY = ROOT / 'data/stadium_surface_history_AUDIT.csv'
PREVIEW = REVIEW / 'stadium_surface_by_game_REVIEW.csv'
DEST = ROOT / 'data/stadium_surface_by_game.csv'


def parse_dates(values, name):
    dt = pd.to_datetime(values, format='%Y-%m-%d', errors='coerce')
    if dt.isna().any():
        raise ValueError(f'{name} contains invalid ISO YYYY-MM-DD dates')
    return dt


def load_history():
    if not HISTORY.exists():
        raise FileNotFoundError(f'Missing {HISTORY.relative_to(ROOT)}')
    hist = pd.read_csv(HISTORY, dtype='string').fillna('')
    cols = {'venue_id','start_date','end_date','surface_type','evidence_url','review_status'}
    if not cols.issubset(hist.columns):
        raise ValueError('History CSV missing columns: ' + ', '.join(sorted(cols-set(hist.columns))))
    hist['start'] = parse_dates(hist.start_date,'start_date')
    hist['end'] = parse_dates(hist.end_date,'end_date')
    if (hist.start > hist.end).any():
        raise ValueError('Reversed start/end dates in history CSV')
    if not hist.surface_type.isin(['grass','turf']).all():
        raise ValueError('History surface_type must be grass or turf')
    for vid, rows in hist.groupby('venue_id'):
        rows = rows.sort_values('start')
        if (rows.start.iloc[1:].reset_index(drop=True) <= rows.end.iloc[:-1].reset_index(drop=True)).any():
            raise ValueError(f'Overlapping surface intervals for {vid}')
    return hist


def make_preview():
    matches_path = REVIEW / 'stadium_game_matches_REVIEW.csv'
    features_path = REVIEW / 'stadium_features_REVIEW.csv'
    for p in (matches_path,features_path):
        if not p.exists(): raise FileNotFoundError(f'Missing {p.relative_to(ROOT)}; run prepare_stadium_metadata.py first')
    match = pd.read_csv(matches_path, dtype='string').fillna('')
    feats = pd.read_csv(features_path, dtype='string').fillna('')
    hist = load_history()
    needed_m={'game_key','stadium_id','game_date','home_flag','match_status'}
    needed_f={'venue_id','surface_type','verified'}
    if not needed_m.issubset(match.columns) or not needed_f.issubset(feats.columns):
        raise ValueError('Preview match/feature CSV has missing required columns')
    if match.game_key.duplicated().any() or feats.venue_id.duplicated().any():
        raise ValueError('Duplicate game keys or stadium IDs in preview files')
    feat_lookup=feats.set_index('venue_id').to_dict('index')
    hist_lookup={vid:group for vid,group in hist.groupby('venue_id')}
    dates=parse_dates(match.game_date,'game_date')
    result=[]
    for m, date in zip(match.to_dict('records'), dates):
        home = str(m['home_flag']).strip() in ('1','True','true')
        vid=m['stadium_id']
        rec={'game_key':m['game_key'], 'stadium_id':vid, 'game_date':m['game_date'],
             'home_flag':int(home), 'match_status':m['match_status'],
             'surface_type':'', 'surface_basis':'', 'surface_verified':False,
             'evidence_url':'', 'review_note':''}
        if not home:
            rec.update(surface_basis='not_required_neutral',surface_verified=True)
        elif m['match_status']!='matched' or not vid:
            rec.update(surface_basis='unmatched_stadium',review_note='Resolve stadium match before validating surface')
        elif vid in hist_lookup:
            periods=hist_lookup[vid]
            active=periods.loc[(periods.start<=date)&(periods.end>=date)]
            if len(active)==1:
                item=active.iloc[0]
                rec.update(surface_type=item.surface_type,surface_basis='historical_period',
                           surface_verified=(item.review_status=='source_verified'),
                           evidence_url=item.evidence_url,
                           review_note='Date-specific surface period: check evidence and historical boundaries')
            else:
                rec.update(surface_basis='uncovered_history_period',
                           review_note='Stadium has historical changes but no period covers this game')
        elif vid in feat_lookup:
            static=feat_lookup[vid]
            surf=str(static['surface_type']).lower().strip()
            rec.update(surface_type=surf if surf in ('grass','turf') else '',
                       surface_basis='static_stadium_value',
                       surface_verified=False,
                       review_note='Provisional static value: verify surface history across 2004–2023')
        else:
            rec.update(surface_basis='missing_venue_metadata', review_note='Stadium ID not in metadata')
        result.append(rec)
    out=pd.DataFrame(result)
    REVIEW.mkdir(parents=True,exist_ok=True)
    out.to_csv(PREVIEW,index=False)
    print('Wrote:',PREVIEW.relative_to(ROOT))
    print('Total games:',len(out))
    print('Home stadium surface review by basis:')
    print(out[out.home_flag==1].surface_basis.value_counts(dropna=False).to_string())
    print('Unverified home games:',int(((out.home_flag==1)&~out.surface_verified).sum()))
    print('FINAL model surface file NOT written. Review static records and historical periods.')


def finalize():
    if not PREVIEW.exists():
        raise FileNotFoundError('Generate and inspect the surface preview first')
    for name in ('stadium_game_matches.csv','stadium_features.csv'):
        if not (ROOT/'data'/name).exists():
            raise ValueError(f'Final stadium data/{name} missing. Finish venue verification first.')
    s=pd.read_csv(PREVIEW,dtype='string').fillna('')
    match=pd.read_csv(ROOT/'data/stadium_game_matches.csv',dtype='string').fillna('')
    if s.game_key.duplicated().any() or match.game_key.duplicated().any():
        raise ValueError('Duplicate keys in reviewed files')
    if set(s.game_key) != set(match.game_key):
        raise ValueError('Surface review and final stadium matches refer to different games')
    pairs=s.merge(match[['game_key','stadium_id','match_status']],on='game_key',suffixes=('','_final'),how='left',validate='one_to_one')
    home = pairs.home_flag=='1'
    mismatch=home & ((pairs.stadium_id!=pairs.stadium_id_final) | (pairs.match_status!='matched') | (pairs.match_status_final!='matched'))
    if mismatch.any():
        raise ValueError(f'{mismatch.sum()} game match discrepancies; refuse to write final surfaces')
    approved=pairs.surface_verified.str.strip().str.lower().isin(('true','t','yes','1'))
    bad = home & ((~approved) | (~pairs.surface_type.isin(('grass','turf'))))
    if bad.any():
        print(pairs.loc[bad,['stadium_id','surface_basis']].value_counts().head(20).to_string())
        raise ValueError(f'{bad.sum()} home-game surface records not independently verified')
    s[['game_key','stadium_id','game_date','surface_type','surface_verified','surface_basis','evidence_url']].to_csv(DEST,index=False)
    print('Written verified FINAL game-level surface file:', DEST.relative_to(ROOT))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalize',action='store_true')
    args=parser.parse_args()
    try:
        finalize() if args.finalize else make_preview()
    except (ValueError,FileNotFoundError) as e:
        parser.exit(2, 'SURFACE AUDIT ERROR: '+str(e)+'\n')
