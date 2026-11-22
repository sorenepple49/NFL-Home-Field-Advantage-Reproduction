#!/usr/bin/env python3
"""Review/merge sourced binary NFL playing-surface intervals safely.

Run from the root of NFL-Home-Field-Advantage-Reproduction:
  python code/nfl_venue/merge_surface_history_addendum.py --check
  python code/nfl_venue/merge_surface_history_addendum.py --apply

Inputs: data/stadium_surface_history_AUDIT.csv
        data/stadium_surface_history_ADDENDUM_REVIEW.csv

The second input is a research-backed proposal; read its evidence links before --apply.
No model is fit and no final dataset approval is granted by this script.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter
from datetime import date
from pathlib import Path
from shutil import copy2

ROOT = Path.cwd()
EXISTING = ROOT / 'data/stadium_surface_history_AUDIT.csv'
ADDENDUM = ROOT / 'data/stadium_surface_history_ADDENDUM_REVIEW.csv'
MATCHES = ROOT / 'results/venue_models/stadium_integration/stadium_game_matches_REVIEW.csv'
FIELDS = ['venue_id','start_date','end_date','surface_type','evidence_url','review_status','notes']


def read_csv(path):
    if not path.is_file(): raise ValueError(f'Missing file: {path}')
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f)
        if not set(FIELDS).issubset(rd.fieldnames or []):
            raise ValueError(f'{path}: missing columns {set(FIELDS)-set(rd.fieldnames or [])}')
        return list(rd)


def day(x):
    try: return date.fromisoformat(x)
    except ValueError: raise ValueError(f'Invalid YYYY-MM-DD date: {x}')


def validate(rows):
    records = {}
    for row in rows:
        id = row['venue_id']
        if not id: raise ValueError('Blank venue_id')
        if row['surface_type'] not in ('grass','turf'): raise ValueError(f'Invalid surface for {id}')
        if row['review_status'] != 'source_verified':
            raise ValueError(f'Unapproved source status for {id}: {row["review_status"]}')
        if not row['evidence_url'].startswith('https://'):
            raise ValueError(f'Missing HTTPS source URL for {id}')
        s,e=day(row['start_date']),day(row['end_date'])
        if s>e: raise ValueError(f'Start after end: {id}')
        records.setdefault(id, []).append((s,e,row['surface_type']))
    for id, spans in records.items():
        spans.sort()
        for a,b in zip(spans,spans[1:]):
            if a[1]>=b[0]: raise ValueError(f'Overlapping periods for {id}: {a} vs {b}')
    return records


def compare_to_games(records):
    if not MATCHES.is_file():
        print('WARNING: game-match audit is absent; date coverage cannot be checked')
        return
    with MATCHES.open('r',encoding='utf-8-sig',newline='') as f:
        m=list(csv.DictReader(f))
    games=[r for r in m if r['home_flag'] in ('1','True','true') and r['match_status']=='matched']
    unassigned=[]; ambiguous=[]
    for r in games:
        key=r['stadium_id']; d=day(r['game_date'])
        count=sum(s<=d<=e for s,e,_ in records.get(key,[]))
        if count==0: unassigned.append(r)
        elif count>1: ambiguous.append(r)
    print(f'Game-level coverage check: {len(games)} matched home games; {len(unassigned)} uncovered; {len(ambiguous)} multi-matched')
    if unassigned:
        ids=Counter(r['stadium_id'] for r in unassigned)
        print('First unmatched IDs:', ids.most_common(15))
        raise ValueError('Some home games lack a sourced historical surface period')
    if ambiguous:
        raise ValueError('One or more games fall in overlapping periods')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true',help='Validate without changing files')
    group.add_argument('--apply',action='store_true',help='Back up and merge researched rows into the existing audit')
    args=ap.parse_args()
    old=read_csv(EXISTING)
    new=read_csv(ADDENDUM)
    if len(new)!=38 or len({r['venue_id'] for r in new})!=38:
        raise ValueError('Expected exactly 38 unique stadium additions')
    both=old+new
    spans=validate(both)
    print(f'Validated {len(old)} existing + {len(new)} sourced additional periods; {len(spans)} unique venue IDs')
    compare_to_games(spans)
    if args.check:
        print('CHECK ONLY: no files changed. Read the 38 sources before running --apply.')
        return
    backup_dir=ROOT/'results/venue_models/backups'
    backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/'stadium_surface_history_AUDIT.before_addendum.csv'
    if backup.exists():
        raise ValueError(f'Backup already exists: {backup}; do not overwrite prior backups')
    copy2(EXISTING,backup)
    with EXISTING.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k:r[k] for k in FIELDS} for r in both)
    print(f'APPROVED SOURCE-REVIEW MERGE WRITTEN: {EXISTING.relative_to(ROOT)}')
    print(f'Backup: {backup.relative_to(ROOT)}')
    print('Next: python code/nfl_venue/build_surface_review.py')
    print('This does NOT approve roof/altitude metadata or create a final model dataset.')


if __name__=='__main__':
    try: main()
    except ValueError as exc:
        raise SystemExit(f'SURFACE HISTORY VALIDATION ERROR: {exc}')
