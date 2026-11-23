# NFL 2004–2023 stadium metadata: researched audit (NOT finalized)

Generated 2026-11-22 from the user's uploaded seven-file ZIP. Original ZIP files were not modified.

## Results
- **43/43 unique venue IDs** have valid roof categories and numeric USGS terrain elevations; all 43 elevation API checks reported OK in the uploaded source.
- **5,395** game records; **5,309** matched home records and **86** `not_required_neutral` records.
- **43/43** matched venue groups pass the *internal* stadium date-window check; counts equal `matched_games`. This is not independent verification of game locations.
- **30 stadiums** have named roof-class evidence in a contemporaneous 2003 Minnesota Stadium Screening Committee study (PDF pp. 31–32); the other **13** have later direct roof references in the crosswalk. Several classifications require explicit architectural taxonomy qualifications.
- `verified` remains **False for all 43** because historical game attribution and roof taxonomy have not received manual final sign-off.

## CRITICAL — resolve before model fitting
**2010-12-20 Minnesota Vikings vs Chicago Bears:** The uploaded `stadium_game_matches_REVIEW.csv` marks `home_flag=0`, `not_required_neutral`, stadium blank. Vikings reporting documents the game hosted at open-air TCF Bank Stadium after the Metrodome collapse. Its **2010-12-13** Giants game was instead moved to Ford Field in Detroit and is a useful neutral control. The Dec 20 Bears game should be evaluated as an actual **Minnesota home game at MIN98**, not a neutral game, under a local physical home-venue definition. Reconcile the **upstream source and preparation script** before refitting: editing only an exported CSV risks mismatching R input, game surfaces, home flags, and model data. The 5,309 count may change after correction, and any previous model metrics may need recomputation.

Source: https://www.vikings.com/news/top-vikings-moments-at-tcf-bank-stadium-16668318

## High-priority exceptions
1. **DAL99 Texas Stadium**: historical government source calls it **Partial dome**; its playing field is exposed through the roof opening. Mapping to `open` is consistent with *field exposure*, not with *absence of roof structure*.
2. **MIA00 Hard Rock Stadium**: a **2016 spectator-canopy renovation** altered architecture but left playing field exposed. An era-constant `open` field-exposure category may be retained, with explicit limitation.
3. **NYC00 Giants Stadium**: uploaded `source_url` incorrectly points to MetLife Stadium. In the proposed CSV this is repaired to `https://en.wikipedia.org/wiki/Giants_Stadium`; roof and date corroboration are separately referenced. Giants Stadium and MetLife are separate physical stadiums; close source coordinates alone do not differentiate them.

## Elevation definition
USGS EPQS interpolated **terrain** elevation (meters) at submitted rounded venue coordinates; not necessarily surveyed playing-field elevation. Largest uploaded old-vs-USGS discrepancies: Dallas -69.79m; Kansas City +13.27m; LA Coliseum +12.17m; Charlotte -5.27m; Oakland -5.17m. No source elevations were silently overwritten in the user's repository. Proposed file keeps both `altitude_m` (USGS) and `original_altitude_m`.

## Files
- `stadium_attribute_evidence_RESEARCHED.csv`: all 43 rows, roof and historical sources, internal date checks, open sign-offs. Review `priority`, `approval_notes`, and `historical_review_notes`.
- `stadium_roof_evidence_CROSSWALK.csv`: per-venue roof provenance and source strength.
- `stadium_features_USGS_PROPOSED_NOT_FINAL.csv`: compatible-style proposed review file, corrected NYC00 source, all `verified=False`; **do not** put this at `data/stadium_features.csv` yet.
- `game_classification_exceptions_REVIEW.csv`: the Vikings two-game contrast, including critical 2010 Dec 20 issue.
- `audit_issue_register.csv`: prioritized remaining methodological and metadata exceptions.
- `audit_counts.json`: machine-readable verification counts.

## Approve, reconcile, and fit
1. Correct and re-run upstream source matching for 2010-12-20 Vikings–Bears *after checking the game-location policy*; regenerate `data/stadium_game_matches.csv` and `data/stadium_surface_by_game.csv`; validate joins.
2. Review roof taxonomy exceptions, historical sources and stadium-level home-game attribution. Add reviewer evidence, then approve only fully supported stadiums; keep audits and sources.
3. Transfer approved venue metadata into `results/venue_models/stadium_integration/stadium_features_REVIEW.csv`, **only then** mark `verified=True` based on documented evidence and run `python code/nfl_venue/prepare_stadium_metadata.py --finalize`.
4. Run `Rscript code/nfl_venue/run_all_models.R` with the project's model settings and re-check Rhat/ESS/divergences and held-out error/coverage. Changing the 2010 game treatment can change existing preliminary results.

## Sources (representative)
- Historical roof source: https://www.lrl.mn.gov/docs/2004/other/040634/Stadium/www.stadium.state.mn.us/meetings/031209/031209_agenda.pdf (PDF page labels 31–32)
- Retractable roof five: https://static.clubs.nfl.com/image/upload/cardinals/icnmdjagghoc1akbntor.pdf (2018 Cardinals official media guide)
- SoFi canopy: https://www.hksinc.com/what-we-do/projects/sofi-stadium/
- U.S. Bank fixed roof: https://www.usbankstadium.com/plan-your-visit/a-z-guide
- Allegiant fixed roof: https://www.allegiantstadium.com/stadium/a-z-guide
- Hard Rock 2016 canopy: https://aecom.com/projects/hard-rock-stadium-renovations-roof-addition/
- USGS terrain measurement limitations: https://www.usgs.gov/faqs/how-accurate-are-elevations-generated-elevation-point-query-service-national-map

**Important:** The 43 per-venue roof evidence URLs are research pointers and documented classifications, not independent proof that every venue-year and game-location decision is correct. The final approval step remains intentionally gated.
