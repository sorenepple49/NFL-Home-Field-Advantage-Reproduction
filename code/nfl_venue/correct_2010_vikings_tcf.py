#!/usr/bin/env python3
"""Correct one 2010 Vikings–Bears home-game venue and its linked audit tables.

Run at the NFL-Home-Field-Advantage-Reproduction repository root:
    python code/nfl_venue/correct_2010_vikings_tcf.py --check
    python code/nfl_venue/correct_2010_vikings_tcf.py --apply

DOES NOT mark stadium metadata verified or run the Bayesian model.
Only the 2010-12-20 Minnesota Vikings vs Chicago Bears game is reclassified.
The 2010-12-13 Vikings vs New York Giants game stays Neutral.

Reproducibility: original files are backed up next to their originals with
'.before_2010_tcf.bak' suffix, and the script refuses to overwrite pre-existing
backups. Data provenance URLs are embedded in the new surface-history row.
"""
import argparse
import csv
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path

GAME_KEY = '2010|2010-12-20|Minnesota Vikings|Chicago Bears'
GIANTS_KEY = '2010|2010-12-13|Minnesota Vikings|New York Giants'
EVIDENCE_GAME = 'https://www.vikings.com/news/top-vikings-moments-at-tcf-bank-stadium-16668318'
EVIDENCE_TURF = 'https://www.cbsnews.com/minnesota/news/no-shovelers-needed-for-tcf-bank-stadium/'
VENUE_ID = 'MIN98'
BACKUP_SUFFIX = '.before_2010_tcf.bak'

PATHS = {
    'games': 'data/final/NFL_games.csv',
    'stadiums': 'data/stadiums.csv',
    'matches_review': 'results/venue_models/stadium_integration/stadium_game_matches_REVIEW.csv',
    'matches_final': 'data/stadium_game_matches.csv',
    'surface_review': 'results/venue_models/stadium_integration/stadium_surface_by_game_REVIEW.csv',
    'surface_final': 'data/stadium_surface_by_game.csv',
    'history': 'data/stadium_surface_history_AUDIT.csv',
    'features_review': 'results/venue_models/stadium_integration/stadium_features_REVIEW.csv',
    'franchise_audit': 'results/venue_models/stadium_integration/franchise_season_stadium_audit.csv',
}
MUTABLE = ('games','matches_review','matches_final','surface_review','surface_final','history','features_review','franchise_audit')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_csv(path):
    with path.open('r',encoding='utf-8-sig',newline='') as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None, f'{path} has no CSV header')
        return list(reader.fieldnames), list(reader)


def write_csv(path, header, rows):
    tmp = path.with_name(path.name + '.2010_tcf_tmp')
    with tmp.open('w',encoding='utf-8',newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=header,lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def one(rows, column, value, label):
    found = [r for r in rows if r.get(column,'')==value]
    require(len(found)==1,f'{label}: expected 1 record for {column}={value}; got {len(found)}')
    return found[0]


def great_circle_km(lat1,lon1,lat2,lon2):
    r=math.pi/180
    p1,p2=lat1*r,lat2*r
    dlat=(lat2-lat1)*r
    dlon=(lon2-lon1)*r
    a=math.sin(dlat/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 6371.0088*2*math.asin(min(1,math.sqrt(max(0,a))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true',help='Read-only preflight')
    mode.add_argument('--apply',action='store_true',help='Backup and apply the exact one-game correction')
    args=parser.parse_args()
    root=Path.cwd()
    paths={k:root/v for k,v in PATHS.items()}
    for label,path in paths.items():
        require(path.exists(),f'Missing required {label} file: {path}')

    tables={k:read_csv(p) for k,p in paths.items()}
    gh, games=tables['games']
    sh,stadiums=tables['stadiums']
    mrh,matches_review=tables['matches_review']
    mfh,matches_final=tables['matches_final']
    srh,surface_review=tables['surface_review']
    sfh,surface_final=tables['surface_final']
    hh,history=tables['history']
    fh,features=tables['features_review']
    fah,franchise_audit=tables['franchise_audit']

    for key,required_cols in {
        'games': ['season','date','location','home_team','away_team','lat_home','lng_home','distance'],
        'stadiums': ['stadium_id','stadium_name','lat','lon','first_game_date','last_game_date'],
        'matches_review': ['game_key','stadium_id','stadium_name','home_flag','match_status','match_km'],
        'matches_final': ['game_key','stadium_id','stadium_name','match_status','match_km'],
        'surface_review':['game_key','stadium_id','home_flag','match_status','surface_type','surface_basis','surface_verified','evidence_url'],
        'surface_final':['game_key','stadium_id','surface_type','surface_verified'],
        'history':['venue_id','start_date','end_date','surface_type','evidence_url','review_status'],
        'features_review':['venue_id','matched_games','verified'],
        'franchise_audit':['home_team','season','games','distinct_stadiums','stadiums'],
    }.items():
        missing=set(required_cols)-set(tables[key][0])
        require(not missing,f'{key} lacks columns {sorted(missing)}')

    def date_value(s):
        return datetime.strptime(s.strip(),'%Y-%m-%d').date()
    target_game=[g for g in games if g['season']=='2010' and
        g['home_team']=='Minnesota Vikings' and g['away_team']=='Chicago Bears' and
        datetime.strptime(g['date'].strip(), '%m/%d/%Y').date().isoformat()=='2010-12-20']
    require(len(target_game)==1,f'Expected one 2010-12-20 Vikings–Bears game; found {len(target_game)}')
    game=target_game[0]
    require(game['location'].strip().lower()=='neutral', 'Source row is not Neutral (perhaps already patched)')
    giants=[g for g in games if g['season']=='2010' and g['home_team']=='Minnesota Vikings'
            and g['away_team']=='New York Giants' and g['date'].strip()=='12/13/2010']
    require(len(giants)==1 and giants[0]['location'].strip().lower()=='neutral',
            'Dec 13 Giants neutral control missing/changed')
    venue=one(stadiums,'stadium_id',VENUE_ID,'stadiums')
    require(date_value(venue['first_game_date'])<=date_value('2010-12-20')<=date_value(venue['last_game_date']),
            'MIN98 date window does not include 2010-12-20')
    lat,lon=float(venue['lat']),float(venue['lon'])
    eligible=[]
    for s in stadiums:
        if date_value(s['first_game_date'])<=date_value('2010-12-20')<=date_value(s['last_game_date']):
            eligible.append((great_circle_km(lat,lon,float(s['lat']),float(s['lon'])),s['stadium_id']))
    eligible.sort()
    require(eligible[0][1]==VENUE_ID and eligible[0][0]<0.1,'Corrected coordinates do not map unambiguously to MIN98')
    require(len(eligible)<2 or eligible[1][0]-eligible[0][0]>0.25,
            f'MIN98 stadium proximity ambiguous: next {eligible[1] if len(eligible)>1 else None}')

    old_mr=one(matches_review,'game_key',GAME_KEY,'match review')
    old_mf=one(matches_final,'game_key',GAME_KEY,'match final')
    old_sr=one(surface_review,'game_key',GAME_KEY,'surface review')
    old_sf=one(surface_final,'game_key',GAME_KEY,'surface final')
    require(old_mr['home_flag'].strip()=='0' and old_mr['match_status']=='not_required_neutral',
            'Match REVIEW is not the expected neutral baseline')
    require(old_sr['home_flag'].strip()=='0' and old_sr['surface_basis']=='not_required_neutral',
            'Surface REVIEW is not the expected neutral baseline')
    require(old_mf['match_status']=='not_required_neutral', 'Final match is not neutral')
    require(not old_sf['stadium_id'].strip(),'Final surface row unexpectedly has an assigned stadium')
    require(one(matches_review,'game_key',GIANTS_KEY,'Giants match')['home_flag'].strip()=='0',
            'Giants match row is not neutral')
    require(one(surface_review,'game_key',GIANTS_KEY,'Giants surface')['home_flag'].strip()=='0',
            'Giants surface row is not neutral')
    feat=one(features,'venue_id',VENUE_ID,'feature review')
    require(feat['verified'].strip().lower() in ('false','0','f'), 'Refusing to change an already approved feature row')
    relevant=[r for r in history if r['venue_id']==VENUE_ID and
              date_value(r['start_date'])<=date_value('2010-12-20')<=date_value(r['end_date'])]
    require(not relevant,'A MIN98 historical period already covers 2010-12-20; inspect before changing')

    # V3: Use exactly the SAME study filter as the stadium matcher.
    # A hand-written check for "nonempty" score strings is not equivalent to
    # pandas dropna: entries such as "NA" can be parsed as missing by pandas.
    # Discrepancies are reported by game key; they are never silently ignored.
    try:
        from prepare_stadium_metadata import load_games
    except ImportError as exc:
        raise ValueError('Cannot import prepare_stadium_metadata.load_games; keep this script beside prepare_stadium_metadata.py') from exc
    study = load_games(paths['games'])
    analysis_keys = study['game_key'].astype(str).tolist()
    require(len(set(analysis_keys)) == len(analysis_keys),
            'Source has duplicate study game keys; inspect before patching')
    expected = set(analysis_keys)
    require(GAME_KEY in expected and GIANTS_KEY in expected,
            '2010 Vikings control games not found in study filtered data')
    for name, table in [('matches_review',matches_review),('matches_final',matches_final),
                        ('surface_review',surface_review),('surface_final',surface_final)]:
        keys = [r['game_key'] for r in table]
        require(len(set(keys)) == len(keys), f'{name} duplicates game_key')
        missing = sorted(expected - set(keys))
        extra = sorted(set(keys) - expected)
        require(not missing and not extra,
                f'{name} differs from prepared study: {len(missing)} missing and '
                f'{len(extra)} extra; missing examples={missing[:5]}, extra examples={extra[:5]}')
    print(f'Raw source: {len(games)} rows; filtered study: {len(expected)} games; '
          f'excluded from study: {len(games)-len(expected)} rows.')

    print('PRECHECK PASS: Vikings–Bears 2010-12-20 is Neutral, MIN98 qualifies; Giants stays Neutral.')
    print('Current matched-home count:',sum(r['home_flag'].strip()=='1' for r in matches_review))
    print('Proposed: set Bears location=Home at TCF Bank Stadium, use turf; set travel distance missing.')
    print('Proposed: add single-day 2010-12-20 MIN98 surface-history period (2014–16 period unchanged).')
    print('New projected matched-home count:',sum(r['home_flag'].strip()=='1' for r in matches_review)+1)
    if args.check:
        print('CHECK ONLY: no files written. Run --apply to back up and apply.')
        return

    for key in MUTABLE:
        back=Path(str(paths[key])+BACKUP_SUFFIX)
        require(not back.exists(),f'Backup already exists; refusing to overwrite it: {back}')

    game['location']='Home'
    game['lat_home']=str(lat)
    game['lng_home']=str(lon)
    # Existing neutral-case distance=0 is not a usable Bears travel estimate.
    # R uses travel_missing=1 when distance is NA: no fabricated travel distance.
    game['distance']=''
    match_dist=f'{eligible[0][0]:.3f}'
    old_mr.update({'home_flag':'1','lat_home':str(lat),'lng_home':str(lon),
                   'stadium_id':VENUE_ID,'stadium_name':venue['stadium_name'],
                   'match_km':match_dist,'match_status':'matched','second_candidate':'',
                   'reviewer_note':'2010-12-20 Vikings home venue moved to TCF Bank Stadium; '+EVIDENCE_GAME})
    old_mf.update({'stadium_id':VENUE_ID,'stadium_name':venue['stadium_name'],
                   'match_km':match_dist,'match_status':'matched'})
    old_sr.update({'stadium_id':VENUE_ID,'home_flag':'1','match_status':'matched',
                   'surface_type':'turf','surface_basis':'historical_period',
                   'surface_verified':'True','evidence_url':EVIDENCE_TURF,
                   'review_note':'Vikings played Bears at TCF Bank Stadium; artificial turf, contemporaneous evidence.'})
    old_sf.update({k:v for k,v in {
        'stadium_id':VENUE_ID,'surface_type':'turf','surface_verified':'True',
        'game_date':'2010-12-20','surface_basis':'historical_period',
        'evidence_url':EVIDENCE_TURF,'match_status':'matched','home_flag':'1'
    }.items() if k in sfh})
    newhist={h:'' for h in hh}
    newhist.update({'venue_id':VENUE_ID,'start_date':'2010-12-20','end_date':'2010-12-20',
                    'surface_type':'turf','evidence_url':EVIDENCE_TURF,
                    'review_status':'source_verified',
                    'notes':'2010-12-20 Vikings-Bears at TCF Bank Stadium (artificial surface). '+EVIDENCE_GAME})
    history.append(newhist)
    history.sort(key=lambda r:(r['venue_id'],r['start_date']))
    feat['matched_games']=str(sum(1 for m in matches_review if m['home_flag'].strip()=='1' and m['stadium_id']==VENUE_ID))
    # Recalculate ONLY Minnesota's 2010 franchise audit group from updated match-review rows.
    grouped=[m for m in matches_review if m['season'].strip()=='2010' and m['home_team']=='Minnesota Vikings'
             and m['home_flag'].strip()=='1']
    fai=[x for x in franchise_audit if x['home_team']=='Minnesota Vikings' and x['season'].strip()=='2010']
    require(len(fai)==1,'Missing 2010 Minnesota Vikings franchise audit group')
    fai[0].update({'games':str(len(grouped)),
                   'distinct_stadiums':str(len({m['stadium_id'] for m in grouped if m['stadium_id']})),
                   'unmatched':str(sum(m['match_status']=='unmatched' for m in grouped)),
                   'ambiguous':str(sum(m['match_status']=='ambiguous' for m in grouped)),
                   'stadiums':';'.join(sorted({m['stadium_id'] for m in grouped if m['stadium_id']}))})

    require(sum(r['home_flag'].strip()=='1' for r in matches_review)==5310,'Review did not reach 5310 home games')
    require(sum(r['home_flag'].strip()=='1' for r in surface_review)==5310,'Surface did not reach 5310 home games')
    require(one(matches_review,'game_key',GIANTS_KEY,'Giants match')['home_flag'].strip()=='0',
            'Giants neutral game changed unexpectedly')
    # Back up all files BEFORE writing anything; restore all backups on failure.
    for key in MUTABLE:
        shutil.copy2(paths[key],str(paths[key])+BACKUP_SUFFIX)
    try:
        for key in MUTABLE:
            write_csv(paths[key],*tables[key])
    except Exception:
        for key in MUTABLE:
            shutil.copy2(str(paths[key])+BACKUP_SUFFIX,paths[key])
        raise
    print('APPLY PASS: backed up and updated source game, match crosswalk, surface history,')
    print('surface-by-game, stadium feature counts, and franchise-season audit.')
    print('2010-12-20 Bears: Home, MIN98, FieldTurf. 2010-12-13 Giants: still Neutral.')
    print('NEW HOME TOTAL: 5310, NEUTRAL TOTAL:',len(matches_review)-5310)
    print('NEXT: validate R joins, review git diff, then rerun preliminary models (2010 training data changed).')

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print('TCF GAME CORRECTION ERROR:',e,file=sys.stderr)
        sys.exit(2)
