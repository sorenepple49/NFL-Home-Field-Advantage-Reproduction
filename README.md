# NFL venue home-field advantage — stadium data integration (November 2026)

This update **includes the uploaded `stadiums.csv` (67 stadiums)** and a cautious
physical-stadium matching workflow for the paper's M2/M3 venue models. It does
not claim that M3 has already been fitted or that all stadium metadata is
historically verified. The RStan model files and earlier evaluation scripts are
retained from the prior code package.

## Required input files

Copy this package over the ROOT of the NFL project repository. Keep existing
`code/model/stan/model_1.stan` and `model_2.stan`. Provide the original game data at
`data/final/NFL_games.csv`, **not bundled with this ZIP**. The attached
`data/stadiums.csv` is bundled unchanged. Its `altitude` is tentatively treated
as metres (m), requiring confirmation against the source's data dictionary.

## Run the stadium-matching workflow BEFORE fitting venue models

From the **repository root**:

```bash
python -m pip install -r requirements_stadium_match.txt
python code/nfl_venue/prepare_stadium_metadata.py
```

This reads `data/final/NFL_games.csv` and `data/stadiums.csv`, producing:

- `results/venue_models/stadium_integration/stadium_game_matches_REVIEW.csv`
- `results/venue_models/stadium_integration/stadium_features_REVIEW.csv`
- `results/venue_models/stadium_integration/franchise_season_stadium_audit.csv`
- `results/venue_models/stadium_integration/known_stadium_metadata_flags.csv`

The matcher uses a haversine distance threshold of **5 km** and requires each
candidate's recorded first/last game dates to cover the NFL game. It flags
near-tied matches instead of guessing. This is a candidate crosswalk, not
independent confirmation that the location supplied in the original game file
was the location of every actual game. Check the candidate mapping against
franchise relocations, temporary home sites and stadium openings.

Review **every** used venue in `stadium_features_REVIEW.csv`, especially its
`roof_type`, `surface_type`, `altitude_m`, and `source_url`. Change a metadata
value if supported by a reliable source, document the change, and set
`verified=True` **only after review**. The supplied source incorrectly or at
least questionably labels some retractable-roof facilities as `Outdoors`:
Mercedes-Benz Stadium, AT&T Stadium, NRG Stadium, Lucas Oil Stadium and State
Farm Stadium. SoFi's roof taxonomy also deserves explicit treatment.
The source contains stadium records beyond the 2004–2023 study period; the
matching algorithm excludes venues whose first game postdates the observed game.

If any home games are unmatched/ambiguous, resolve the individual records in
`stadium_game_matches_REVIEW.csv`. Do not assign the nearest stadium by default
for unresolved cases. Only after all used venue features and all home-game
matches are reviewed, execute:

```bash
python code/nfl_venue/prepare_stadium_metadata.py --finalize
```

This writes the **approved** files expected by the R code:

- `data/stadium_game_matches.csv` (game-key to *physical stadium ID* crosswalk)
- `data/stadium_features.csv` (reviewed roof/surface/altitude, source URL)

If the review is unfinished, `--finalize` stops with an error; the package does
not silently approve the attached values. An additional quick source-level
review list is included as `stadiums_source_audit.csv`.

## Then fit and evaluate the venue models

From repository ROOT in RStudio (R + compatible compiler and RStan required):

```r
install.packages(c("rstan", "dplyr", "tidyr", "readr", "ggplot2", "loo", "tibble"))
source("code/nfl_venue/run_all_models.R")
```

The revised `run_all_models.R` now joins the **approved physical stadium IDs**
by `season|YYYY-MM-DD|home_team|away_team`, so two stadiums at the same
coordinates are not automatically merged. A neutral-site game is not given a
home/franchise/venue effect; the stadium matching step does not force a home
stadium onto neutral games. Stadium model coefficients remain **associations**,
not causal evidence.

**Important limitations:** Actual venue coordinates may differ from the
original data's designated-home-team coordinates. Roof configurations, playing
surfaces and stadium names may change over 2004–2023; the one-row-per-stadium
review file assumes the values apply across a venue's used seasons. If this
assumption is unsupported, build a validated stadium-by-season feature table
and modify the Stan design matrix accordingly before publishing an attribute
coefficient. Do not present static source features as verified time-varying
features. Weather/attendance also require separate historical game-level data.

**Execution status:** The Python matching code was tested against a small
synthetic sample including Giants Stadium/MetLife, two flagged roof stadiums,
and a neutral-site game. The full project data was **not** available to run the
match, the RStan models were **not** executed, and results remain unverified.
The synthetic test input is not included in the deliverable.

---

# NFL Home-Field Advantage — Revised modeling code (Team 13)

**Purpose:** Make the code consistent with the paper *What Makes an NFL Stadium Capable of Being Called True Home-Field Advantage?*, rather than submitting the parent paper's high-school hierarchy as an NFL stadium model.

## What is included

| Model | Purpose | Implemented |
| --- | --- | --- |
| M0 | Training-data average home scoring margin | Yes (no Stan) |
| M1 | Constant league-wide Bayesian home effect, with team strengths | Yes (re-estimated in common comparison model) |
| M1b | League-wide trend in home advantage | Yes (re-estimated) |
| M2a | Stadium fixed deviations with a Gaussian/ridge penalty | Yes; penalty SD tuned on 2018–2019 only |
| M2b | Partially pooled venue deviations | Yes |
| M3a | Time-varying stadium effects + franchise effect, no venue attributes | Yes |
| M3b | Attribute-informed venue effects + franchise effect, no time drift | Requires verified stadium metadata |
| M3c | Attribute-informed venue effects + time drift, no franchise effect | Requires verified stadium metadata |
| M3 | Attribute-informed venue + franchise effect + time drift | Requires verified stadium metadata |

`run_original_reproduction.R` separately fits the published **original** `model_1.stan` and `model_2.stan` on all eligible 2004–2023 games, preserving the parent-paper reproduction. The common comparison model M1/M1b uses regularized evolving team strength for comparability across all extensions and therefore will **not reproduce precisely the same point estimates** as the original models. In the paper, distinguish the full-sample reproduction (2.20, 2.72, −0.05 from prior recorded runs) from new held-out evaluations.

## Repo file layout

Copy **both** `code/nfl_venue/` and `README_NFL_VENUE.md` into the repository root. Do not delete the parent paper's `code/model/stan/model_1.stan` and `model_2.stan` if you are still reproducing them. The project root must contain:

```text
repo-root/
  data/final/NFL_games.csv
  data/stadium_features.csv           # optional until M3 features are collected
  code/model/stan/model_1.stan       # existing original code for reproduction
  code/model/stan/model_2.stan
  code/nfl_venue/run_original_reproduction.R
  code/nfl_venue/run_all_models.R
  code/nfl_venue/stan/venue_model.stan
  results/venue_models/              # created by script
```

## R requirements and commands

Install **R**, a C++ toolchain compatible with **RStan**, and these packages:

```r
install.packages(c("rstan", "dplyr", "tidyr", "readr", "ggplot2", "loo", "tibble"))
```

From the repository ROOT (RStudio project root or terminal), run:

```r
source("code/nfl_venue/run_original_reproduction.R")  # original full-sample results
source("code/nfl_venue/run_all_models.R")              # evaluate stadium extensions
```

For a preliminary run of four models without metadata (M1, M1b, M2b, M3a) from terminal:

```bash
RUN_ALL=false Rscript code/nfl_venue/run_all_models.R
```

On Windows PowerShell use:

```powershell
$env:RUN_ALL="false"
Rscript code/nfl_venue/run_all_models.R
```

To calculate approximate PSIS-LOO **on the training set only**, set `RUN_LOO=true` before running. This optional diagnostic is not a substitute for the chronological test. The Stan models can take substantial compute and RAM; fit models one by one if needed. The scripts will save large fit RDS files to `results/venue_models/<model>/fit.rds` (typically exclude these from GitHub).

## Essential data validation for M3

The original `NFL_games.csv` provides game date, scores, designated teams, home/neutral label, distance, and `lat_home`/`lng_home`. It does **not** include verified roof type, playing surface, altitude, actual stadium name, or attendance. The code does **not fabricate** these fields.

1. Run `run_all_models.R` once; it writes `results/venue_models/stadium_features_TO_FILL.csv`, `venue_coordinate_audit.csv`, and `stadium_audit_by_franchise_year.csv`.
2. Audit coordinate-based `venue_id` against historical venue names, temporary stadiums, moves and shared sites. Coordinates are provisional; an NFL home team can play at a neutral or temporary stadium. Correct any mismatches in a documented preprocessing extension before claiming reliable physical-venue rankings.
3. Complete the generated stadium metadata with `roof_type` (`open`, `dome`, `retractable`), `surface_type` (`grass`, `turf`), numeric `altitude_m`, and `source_url` (verifiable stadium records). Save as `data/stadium_features.csv`.
4. If all venues have verified records, run the full pipeline. If not, the code deliberately skips M3b/M3c/M3 and writes an invalid-record audit; it does **not** fake results.
5. Existing 2004–2023 source has geocoordinates, which do not necessarily prove historic venue or roof status during renovations. If features change over time, the simplified one-row-per-venue file is insufficient: create a venue-by-season validated join before submitting causal/attribute interpretations.

There is **no weather or attendance covariate** in these submitted main models, because they are not in the original dataset. Those require a separate verified game-level join and reported sample counts. Don't report them as included. Rest is calculated only from previous dates; no outcome leakage. Neutral games have zero home/franchise/venue advantage.

## Evaluation (required for paper)

The primary chronological split implements the paper's plan:

- **Training:** 2004–2017; **validation:** 2018–2019; **held-out test:** 2021–2023; **2020:** separate evaluation only.
- Training only determines the parameter fits, scaling, and the ridge penalty. 2021–2023 is never used for tuning.
- Predictions for held-out seasons forecast each franchise's last training posterior team strength with the fitted AR(1) persistence parameter. They do **not** update team strengths after earlier games within the validation/test seasons; the paper's claim of pregame sequential updating would require an additional online Bayesian filtering component. State this accurately rather than claiming a stronger evaluation than this script performs.
- Metrics: mean absolute error, root mean squared error, empirical 50%/90% predictive interval coverage (except deterministic M0), Stan R-hat/effective sample size/divergences, venue posterior intervals, rank stability (M2b vs M3 when available), sensitivity prediction on 2020.
- `results/venue_models/model_comparison.csv` is the source of **actual values** for the Evaluation section. Do **not** report the previous 2.20 and −0.05 estimates as held-out MAE/RMSE.

`venue_credible_intervals.png` and per-model `stadium_posteriors.csv` show adjusted venue deviations from the league mean. For M3 the effect includes attribute estimate, venue residual, and final-training-season drift; **franchise effect is separate**. Avoid assigning causal interpretations to rankings, especially when intervals overlap zero or multiple stadiums have sparse data.

## Important limitations / alignment caveats

- The original paper and these comparative models do not use the same team-strength priors. To present M1/M1b as **exact** replication, use `run_original_reproduction.R` and its separate full-sample table; keep prospective evaluation labels distinct.
- Model M3's franchise home term and venue term can be nearly collinear; identification comes mainly from relocations/shared stadiums and priors, and is not guaranteed by either.
- The original game coordinates correspond to the designated team's home stadium, and neutral-site games are suppressed. Temporary sites and renovated fields must be audited.
- Out-of-period test strengths are conservative forecasts from the training endpoint. If you want to claim **weekly updated pregame Bayesian team-strength forecasts**, implement that filtering and re-evaluate, rather than making that claim from these artifacts.
- M3 with time drift can be computationally demanding. Treat nonzero divergences and poor R-hat as unreliable inference, not as passed diagnostics. Adjust adaptation or parameterization and rerun before claiming robust results.
- `2020_sensitivity` is a special-year **prediction comparison**; it is not a full refit that includes 2020 in training. A separate design would be needed to assess the effect of including the year during training.

## Suggested repository hygiene

Keep data source credited as [Benz/Bliss/Lopez research dataset](https://github.com/ThompsonJamesBliss/comprehensive_survey_american_football_home_adv/blob/main/data/final/NFL_games.csv). Commit the `.R`, `.stan`, `.md`, the cleaned input dataset if redistribution is permitted, audit logs, small result tables, and final plots. Do not commit unvalidated or invented stadium metadata, massive MCMC binary fit files, or drafts misrepresented as final. Include R and package version output (`sessionInfo()`) with the submission.

**Validation status:** Drafted against the user-supplied source-code snippets and publicly documented original data schema. The full RStan pipeline could not be executed in this environment because the R/RStan toolchain and original local data were unavailable. Run the scripts, inspect diagnostics, and reconcile the resulting estimates with the research paper before submission.
