#!/usr/bin/env python3
"""Conservative, date-aware stadium matching for the 2004–2023 NFL HFA study.

Workflow:
  1. python code/nfl_venue/prepare_stadium_metadata.py
  2. Audit the staged CSVs and mark verified=True only after checking each
     stadium's roof/surface/history, altitude units and stadium match.
  3. python code/nfl_venue/prepare_stadium_metadata.py --finalize
  4. Rscript code/nfl_venue/run_all_models.R

The script never invents missing matches and never silently 'corrects' source
roof types. Home-team coordinates may be nominal, not actual game locations;
use the game/stadium audits to check temporary and neutral sites explicitly.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import math
import sys
import pandas as pd
import numpy as np

KNOWN_REVIEW_FLAGS = {
    'ATL97': 'Source marks Mercedes-Benz Stadium outdoors; confirm retractable roof and historical game configuration.',
    'DAL00': 'Source marks AT&T Stadium outdoors; confirm retractable roof.',
    'HOU00': 'Source marks NRG/Reliant Stadium outdoors; confirm retractable roof.',
    'IND00': 'Source marks Lucas Oil Stadium outdoors; confirm retractable roof.',
    'PHO00': 'Source marks State Farm Stadium outdoors; confirm retractable roof.',
    'LAX01': 'Source calls SoFi a dome; check canopy/enclosed taxonomy for research definition.',
    'NYC00': 'Giants Stadium overlaps MetLife coordinates; match by GAME DATE, not latitude/longitude alone.',
    'NYC01': 'MetLife overlaps Giants Stadium coordinates; match by GAME DATE, not latitude/longitude alone.',
}

REQUIRED_STADIUM = ['stadium_id', 'stadium_name', 'lat', 'lon',
                    'first_game_date', 'last_game_date', 'roof_type',
                    'surface_type', 'altitude', 'wikipedia_url']
REQUIRED_GAME = ['season', 'date', 'location', 'home_team', 'away_team',
                 'home_score', 'away_score', 'satisfies_cutoff',
                 'lat_home', 'lng_home']


def normalize_dates(series):
    # The game CSV has dates formatted like 9/12/2004; the metadata is ISO.
    out = pd.to_datetime(series, errors='coerce', format='%m/%d/%Y')
    alternate = pd.to_datetime(series, errors='coerce', format='%Y-%m-%d')
    return out.fillna(alternate).dt.normalize()


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(float(lat1)), np.radians(np.asarray(lat2, dtype=float))
    dlat = p2 - p1
    dlon = np.radians(np.asarray(lon2, dtype=float) - float(lon1))
    a = np.sin(dlat/2)**2 + math.cos(p1)*np.cos(p2)*np.sin(dlon/2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.maximum(0, np.minimum(a, 1))))


def load_games(path):
    if not path.exists():
        raise FileNotFoundError(f'NFL game data missing: {path}. Add original NFL_games.csv first.')
    d = pd.read_csv(path, low_memory=False)
    missing = sorted(set(REQUIRED_GAME) - set(d.columns))
    if missing:
        raise ValueError('NFL_games.csv missing required columns: ' + ', '.join(missing))
    cutoff = d.satisfies_cutoff.astype('string').str.strip().str.lower().isin(['true','t','1','yes'])
    d = d.loc[cutoff & d.season.between(2004, 2023)].copy()
    d['game_date'] = normalize_dates(d.date)
    d['home_team'] = d.home_team.astype('string').str.strip()
    d['away_team'] = d.away_team.astype('string').str.strip()
    d['home_flag'] = d.location.astype('string').str.strip().str.lower().eq('home').astype('int64')
    d = d.dropna(subset=['game_date', 'home_team', 'away_team','home_score','away_score'])
    d = d.drop_duplicates()
    d['game_key'] = (d.season.astype(str) + '|' + d.game_date.dt.strftime('%Y-%m-%d') + '|'
                     + d.home_team + '|' + d.away_team)
    if d.game_key.duplicated().any():
        raise ValueError('Game IDs are not unique. Inspect dataset duplicates before stadium matching.')
    return d


def load_stadiums(path):
    d = pd.read_csv(path, low_memory=False)
    missing = sorted(set(REQUIRED_STADIUM)-set(d.columns))
    if missing:
        raise ValueError('stadiums.csv missing required columns: '+', '.join(missing))
    if d.stadium_id.duplicated().any():
        raise ValueError('stadiums.csv has duplicate stadium_id; must be unique')
    d['first_dt'] = normalize_dates(d.first_game_date)
    d['last_dt'] = normalize_dates(d.last_game_date)
    if d[['lat','lon','first_dt','last_dt']].isna().any().any():
        raise ValueError('stadiums.csv has missing coordinates or dates; manual audit needed')
    if (d.first_dt > d.last_dt).any():
        raise ValueError('stadiums.csv has reversed date ranges')
    return d


def make_matches(games, stadiums, max_km=5, ambiguity_km=0.25):
    rows=[]
    for g in games.itertuples(index=False):
        base = {'game_key':g.game_key, 'season':int(g.season),
                'game_date':g.game_date.strftime('%Y-%m-%d'),
                'home_team':g.home_team, 'away_team':g.away_team,
                'home_flag':int(g.home_flag), 'lat_home':g.lat_home,
                'lng_home':g.lng_home}
        candidate = dict(stadium_id='', stadium_name='', match_km=np.nan,
                         match_status='not_required_neutral', second_candidate='',
                         reviewer_note='')
        if g.home_flag:
            candidate['match_status']='unmatched'
            if pd.notna(g.lat_home) and pd.notna(g.lng_home):
                # On this date, the physical stadium must already exist.
                # Date-aware disambiguation separates venues sharing coordinates.
                eligible = stadiums.loc[(stadiums.first_dt <= g.game_date) &
                                        (stadiums.last_dt >= g.game_date)].copy()
                if len(eligible):
                    game_lon = float(g.lng_home)
                    coord_note = ''
                    # The source NFL file miscoded ordinary Saints home longitude.
                    # Keep the unusual 2005 Hurricane Katrina schedule untouched.
                    if (g.home_team == 'New Orleans Saints'
                            and int(g.season) != 2005
                            and abs(float(g.lat_home) - 29.950833) < 0.01
                            and abs(game_lon + 90.811111) < 0.01):
                        game_lon = -90.081111
                        coord_note = 'Source Saints longitude corrected for matching; verify venue history'
                    eligible['match_km'] = haversine_km(g.lat_home, game_lon,
                                                       eligible.lat.values, eligible.lon.values)
                    eligible = eligible.loc[eligible.match_km <= max_km].sort_values('match_km')
                    if len(eligible):
                        best = eligible.iloc[0]
                        close = eligible[eligible.match_km <= best.match_km + ambiguity_km]
                        candidate.update(stadium_id=str(best.stadium_id),
                                         stadium_name=str(best.stadium_name),
                                         match_km=round(float(best.match_km),3),
                                         second_candidate=';'.join(close.stadium_id.iloc[1:].astype(str)))
                        candidate['match_status'] = 'ambiguous' if len(close) > 1 else 'matched'
                        candidate['reviewer_note'] = '; '.join(filter(None, [KNOWN_REVIEW_FLAGS.get(str(best.stadium_id), ''), coord_note]))
        rows.append({**base,**candidate})
    return pd.DataFrame(rows)


def preliminary_features(matches, stadiums):
    counts = matches.loc[matches.match_status.isin(['matched','ambiguous'])]
    counts = counts.groupby('stadium_id').size().rename('matched_games')
    wanted = stadiums[stadiums.stadium_id.isin(counts.index)].copy()
    roof_map = {'outdoors':'open', 'dome':'dome', 'retractable':'retractable'}
    surf_map = {'grass':'grass', 'turf':'turf'}
    wanted['roof_type'] = wanted.roof_type.astype('string').str.lower().map(roof_map)
    # Documented roof architecture corrections; original stadiums.csv is unchanged.
    # "canopy" means a permanent canopy with open sides, NOT a sealed dome.
    roof_overrides = {
        'ATL97': 'retractable', 'DAL00': 'retractable',
        'HOU00': 'retractable', 'IND00': 'retractable',
        'PHO00': 'retractable', 'LAX01': 'canopy',
    }
    wanted['roof_type'] = wanted['stadium_id'].map(roof_overrides).fillna(wanted['roof_type'])
    wanted['surface_type'] = wanted.surface_type.astype('string').str.lower().map(surf_map)
    out = pd.DataFrame({
        'venue_id': wanted.stadium_id,
        'stadium_name': wanted.stadium_name,
        'roof_type': wanted.roof_type,
        'surface_type': wanted.surface_type,
        'altitude_m': wanted.altitude,
        'source_url': wanted.wikipedia_url,
        'first_game_date': wanted.first_game_date,
        'last_game_date': wanted.last_game_date,
        'matched_games': wanted.stadium_id.map(counts).fillna(0).astype(int),
        'verified': False,
        'review_note': wanted.stadium_id.map(KNOWN_REVIEW_FLAGS).fillna(
            'Verify historical roof, surface and elevation; these may change by season.')
    })
    return out.sort_values('venue_id').reset_index(drop=True)


def save_preview(args):
    games=load_games(args.games)
    stadiums=load_stadiums(args.stadiums)
    matches=make_matches(games,stadiums,args.max_km)
    features=preliminary_features(matches,stadiums)
    args.review_dir.mkdir(parents=True,exist_ok=True)
    matches.to_csv(args.review_dir/'stadium_game_matches_REVIEW.csv',index=False)
    features.to_csv(args.review_dir/'stadium_features_REVIEW.csv',index=False)
    home=matches.query('home_flag == 1')
    audit=(home.groupby(['home_team','season'],dropna=False)
           .agg(games=('game_key','count'),distinct_stadiums=('stadium_id','nunique'),
                unmatched=('match_status',lambda x:(x=='unmatched').sum()),
                ambiguous=('match_status',lambda x:(x=='ambiguous').sum()),
                stadiums=('stadium_id',lambda x:';'.join(sorted(set(x)-{''}))))
           .reset_index())
    audit.to_csv(args.review_dir/'franchise_season_stadium_audit.csv',index=False)
    # These are informational source data warnings, not fabricated fixes.
    pd.DataFrame([{'stadium_id':s,'review_note':v} for s,v in KNOWN_REVIEW_FLAGS.items()]).to_csv(
        args.review_dir/'known_stadium_metadata_flags.csv',index=False)
    print('Prepared',len(matches),'games; home-game matches:',
          home.match_status.value_counts().to_dict())
    print('Unique stadium candidates:',len(features))
    print('Review the files in', args.review_dir)
    print('NO final file has been approved or created.')


def finalize(args):
    mpath=args.review_dir/'stadium_game_matches_REVIEW.csv'
    fpath=args.review_dir/'stadium_features_REVIEW.csv'
    if not mpath.exists() or not fpath.exists():
        raise ValueError('Run the initial matching step first to produce REVIEW files.')
    matches=pd.read_csv(mpath,low_memory=False)
    features=pd.read_csv(fpath,low_memory=False)
    home=matches.loc[matches.home_flag.eq(1)]
    bad=home.loc[(home.match_status!='matched') | home.stadium_id.isna()]
    if len(bad):
        raise ValueError(f'{len(bad)} unresolved/ambiguous home games; audit and manually resolve the REVIEW file.')
    if features.venue_id.duplicated().any():
        raise ValueError('Duplicated venue_id in metadata review')
    if not set(home.stadium_id).issubset(set(features.venue_id)):
        raise ValueError('Some matched game venue IDs missing in features')
    true_values={'true','t','1','yes'}
    verified=features.verified.astype(str).str.lower().str.strip().isin(true_values)
    if not verified.all():
        raise ValueError(f'{(~verified).sum()} stadiums not marked verified=True; DO NOT fit attribute model yet.')
    required=['venue_id','roof_type','surface_type','altitude_m','source_url']
    if features[required].isna().any().any():
        raise ValueError('Verified metadata has missing required values')
    if not features.roof_type.isin(['open','dome','retractable','canopy']).all():
        raise ValueError('roof_type must be open/dome/retractable/canopy')
    if not features.surface_type.isin(['grass','turf']).all():
        raise ValueError('surface_type must be grass/turf')
    if not pd.to_numeric(features.altitude_m,errors='coerce').notna().all():
        raise ValueError('Non-numeric altitude_m')
    if not features.source_url.astype(str).str.startswith(('https://','http://')).all():
        raise ValueError('Source URL missing or invalid')
    args.final_dir.mkdir(parents=True,exist_ok=True)
    matches[['game_key','stadium_id','stadium_name','match_km','match_status']].to_csv(
        args.final_dir/'stadium_game_matches.csv',index=False)
    features.to_csv(args.final_dir/'stadium_features.csv',index=False)
    print('Created REVIEWED final data:',args.final_dir/'stadium_game_matches.csv',
          'and',args.final_dir/'stadium_features.csv')


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--games',type=Path,default=Path('data/final/NFL_games.csv'))
    a.add_argument('--stadiums',type=Path,default=Path('data/stadiums.csv'))
    a.add_argument('--review-dir',type=Path,default=Path('results/venue_models/stadium_integration'))
    a.add_argument('--final-dir',type=Path,default=Path('data'))
    a.add_argument('--max-km',type=float,default=5.)
    a.add_argument('--finalize',action='store_true')
    args=a.parse_args()
    if args.finalize: finalize(args)
    else: save_preview(args)

if __name__=='__main__':
    try: main()
    except (ValueError, FileNotFoundError) as e:
        print('Stadium metadata ERROR:', e, file=sys.stderr)
        sys.exit(2)
