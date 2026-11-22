#!/usr/bin/env python3
"""Apply documented NFL stadium roof-architecture corrections to modeling code.

Run in the repository root, then rerun prepare_stadium_metadata.py to refresh
REVIEW files. This script DOES NOT mark any stadium fully verified or finalize
metadata. Physical roof type is not the same as roof-open status on game day.
"""
from __future__ import annotations
import csv
from pathlib import Path
import shutil

ROOT = Path.cwd()
PREP = ROOT / 'code/nfl_venue/prepare_stadium_metadata.py'
RUN = ROOT / 'code/nfl_venue/run_all_models.R'
AUDIT = ROOT / 'data/stadium_roof_corrections.csv'

ROOFS = [
    ('ATL97', 'Mercedes-Benz Stadium', 'open', 'retractable', 'https://www.mercedesbenzstadium.com/news/mercedes-benz-stadium-officials-announce-sundays-falcons-vs-packers-game-will-be-teams-first-open-air-game-since-1991-in-atlanta-weather-permitting'),
    ('DAL00', 'AT&T Stadium', 'open', 'retractable', 'https://static.www.nfl.com/league/apps/league-site/media-guides/2025/DAL.pdf'),
    ('HOU00', 'Reliant / NRG Stadium', 'open', 'retractable', 'https://www.nrgpark.com/reliant-stadium/'),
    ('IND00', 'Lucas Oil Stadium', 'open', 'retractable', 'https://www.lucasoilstadium.com/tours-stadium-info/background-history/'),
    ('PHO00', 'State Farm Stadium', 'open', 'retractable', 'https://www.statefarmstadium.com/stadium-info/about'),
    ('LAX01', 'SoFi Stadium', 'dome', 'canopy', 'https://www.hksinc.com/what-we-do/projects/sofi-stadium/'),
]

if not PREP.is_file() or not RUN.is_file():
    raise SystemExit('Run from the NFL repository root; required scripts not found.')

py = PREP.read_text(encoding='utf-8')
r = RUN.read_text(encoding='utf-8')

# Add documented overrides *after* converting source roof categories.
marker = "    wanted['roof_type'] = wanted.roof_type.astype('string').str.lower().map(roof_map)\n"
overrides = """    # Documented roof architecture corrections; original stadiums.csv is unchanged.
    # "canopy" means a permanent canopy with open sides, NOT a sealed dome.
    roof_overrides = {
        'ATL97': 'retractable', 'DAL00': 'retractable',
        'HOU00': 'retractable', 'IND00': 'retractable',
        'PHO00': 'retractable', 'LAX01': 'canopy',
    }
    wanted['roof_type'] = wanted['stadium_id'].map(roof_overrides).fillna(wanted['roof_type'])
"""
if 'roof_overrides = {' not in py:
    if marker not in py:
        raise SystemExit('Unexpected prepare_stadium_metadata.py content; refusing to guess where to patch.')
    py = py.replace(marker, marker + overrides, 1)

old = "if not features.roof_type.isin(['open','dome','retractable']).all():"
new = "if not features.roof_type.isin(['open','dome','retractable','canopy']).all():"
if old in py:
    py = py.replace(old, new, 1)
elif new not in py:
    raise SystemExit('Unknown Python roof validation logic; no files changed.')
old = "raise ValueError('roof_type must be open/dome/retractable')"
new = "raise ValueError('roof_type must be open/dome/retractable/canopy')"
if old in py:
    py = py.replace(old, new, 1)
elif new not in py:
    raise SystemExit('Unexpected Python roof validation message; no files changed.')

# Add a separate predictor for SoFi's permanent canopy instead of a false dome.
old = '!(roof %in% c("open", "dome", "retractable"))'
new = '!(roof %in% c("open", "dome", "retractable", "canopy"))'
if old in r:
    r = r.replace(old, new, 1)
elif new not in r:
    raise SystemExit('Unexpected R roof categories; no files changed.')
old = 'Fill roof_type=open/dome/retractable, surface_type=grass/turf, '
new = 'Fill roof_type=open/dome/retractable/canopy, surface_type=grass/turf, '
if old in r:
    r = r.replace(old, new, 1)
elif new not in r:
    raise SystemExit('Unexpected R roof validation message; no files changed.')
old = '  f$roof_retractable <- as.integer(roof == "retractable")\n'
new = old + '  f$roof_canopy <- as.integer(roof == "canopy")\n'
if 'f$roof_canopy <- ' not in r:
    if old not in r:
        raise SystemExit('Unexpected R predictor coding; no files changed.')
    r = r.replace(old, new, 1)
old = 'attr_columns <- c("roof_dome", "roof_retractable", "turf", "altitude_m")'
new = 'attr_columns <- c("roof_dome", "roof_retractable", "roof_canopy", "turf", "altitude_m")'
if old in r:
    r = r.replace(old, new, 1)
elif new not in r:
    raise SystemExit('Unexpected R attribute vector; no files changed.')

# A new roof type that never occurs in 2004-2017 cannot be estimated from
# the training set. Drop all invariant attributes from the Stan Z design,
# while preserving their true classifications in the curated CSV.
needle = '  z_means <- vapply(attr_train[attr_columns], mean, numeric(1))\n'
filter_code = """  train_attribute_sds <- vapply(attr_train[attr_columns], sd, numeric(1))
  not_estimable <- !is.finite(train_attribute_sds) | train_attribute_sds == 0
  if (any(not_estimable)) {
    message('Dropping attributes with no variation in 2004-2017: ',
            paste(names(train_attribute_sds)[not_estimable], collapse = ', '))
    attr_columns <- attr_columns[!not_estimable]
  }
  if (!length(attr_columns)) stop('No varying stadium attributes in training data')
"""
if 'train_attribute_sds <-' not in r:
    if needle not in r:
        raise SystemExit('Unexpected R standardization block; no files changed.')
    r = r.replace(needle, filter_code + needle, 1)

for f, data in [(PREP, py), (RUN, r)]:
    previous = f.read_text(encoding='utf-8')
    if data != previous:
        backup = f.with_suffix(f.suffix + '.before_roof_audit.bak')
        if not backup.exists():
            shutil.copy2(f, backup)
        f.write_text(data, encoding='utf-8')
        print('Updated:', f.relative_to(ROOT))
    else:
        print('Already patched:', f.relative_to(ROOT))

AUDIT.parent.mkdir(exist_ok=True, parents=True)
with AUDIT.open('w', newline='', encoding='utf-8') as out:
    writer = csv.writer(out)
    writer.writerow(['stadium_id', 'stadium_name', 'previous_model_roof_type',
                     'corrected_roof_type', 'reference_url', 'interpretation'])
    for id, name, previous, corrected, url in ROOFS:
        interpretation = ('Fixed open-sided canopy; not a sealed dome'
                          if corrected == 'canopy' else
                          'Retractable roof architecture; game-day open/closed status not observed')
        writer.writerow([id, name, previous, corrected, url, interpretation])
print('Created:', AUDIT.relative_to(ROOT))
print('Raw data/stadiums.csv unchanged; no stadiums marked verified.')
print('Next: python code/nfl_venue/prepare_stadium_metadata.py')
