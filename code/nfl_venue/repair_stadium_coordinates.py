from pathlib import Path
import csv

stadium_path = Path('data/stadiums.csv')
script_path = Path('code/nfl_venue/prepare_stadium_metadata.py')
if not stadium_path.is_file() or not script_path.is_file():
    raise SystemExit('Run this from the repository root. Missing expected project files.')

with stadium_path.open(newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    rows = list(reader)
qualcomm = [r for r in rows if r['stadium_id'] == 'SDG00']
if len(qualcomm) != 1 or abs(abs(float(qualcomm[0]['lon'])) - 117.119592) > 0.01:
    raise SystemExit('Qualcomm Stadium record differs from expected; inspect manually before editing.')
qualcomm[0]['lon'] = '-117.119592'

source = script_path.read_text(encoding='utf-8')
needle1 = 'eligible[\'match_km\'] = haversine_km(g.lat_home, g.lng_home,'
replace1 = '''game_lon = float(g.lng_home)
                    coord_note = ''
                    # The source NFL file miscoded ordinary Saints home longitude.
                    # Keep the unusual 2005 Hurricane Katrina schedule untouched.
                    if (g.home_team == 'New Orleans Saints'
                            and int(g.season) != 2005
                            and abs(float(g.lat_home) - 29.950833) < 0.01
                            and abs(game_lon + 90.811111) < 0.01):
                        game_lon = -90.081111
                        coord_note = 'Source Saints longitude corrected for matching; verify venue history'
                    eligible['match_km'] = haversine_km(g.lat_home, game_lon,'''
needle2 = "candidate['reviewer_note'] = KNOWN_REVIEW_FLAGS.get(str(best.stadium_id),'')"
replace2 = "candidate['reviewer_note'] = '; '.join(filter(None, [KNOWN_REVIEW_FLAGS.get(str(best.stadium_id), ''), coord_note]))"
if needle1 in source and needle2 in source:
    source = source.replace(needle1, replace1, 1).replace(needle2, replace2, 1)
elif replace1 not in source or replace2 not in source:
    raise SystemExit('Matching code differs from expected; no files changed.')

with stadium_path.open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
script_path.write_text(source, encoding='utf-8')

log_path = Path('data/stadium_coordinate_corrections.csv')
log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open('w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['source_file','scope','field','original','matching_value','verification_reference'])
    writer.writerow(['data/stadiums.csv','stadium_id SDG00 Qualcomm Stadium','lon','117.119592','-117.119592','https://mapcarta.com/23116406'])
    writer.writerow(['data/final/NFL_games.csv','Saints usual-home games excluding season 2005 with suspect longitude','lng_home','-90.811111','-90.081111','https://www.findlatitudeandlongitude.com/l/Caesars%2BSuperdome%2C%2B1500%2C%2BSugar%2BBowl%2BDrive%2C%2BCentral%2BBusiness%2BDistrict%2C%2BNew%2BOrleans%2C%2BOrleans%2BParish%2C%2BLouisiana%2C%2B70112%2C%2BUSA/9729804/'])
print('Patched Qualcomm longitude, added selective Saints match correction, and wrote correction audit.')
print('Original NFL_games.csv was NOT modified.')
