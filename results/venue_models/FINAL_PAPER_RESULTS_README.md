# NFL Home-Field Advantage — Final Research Results

## Dataset
- NFL seasons: 2004–2023
- Study games: 5,395
- Matched home games: 5,310
- Neutral games: 85
- Physical stadiums: 43
- Test observations: 854

## Modeling
Eight Bayesian model variants were fitted using RStan:
M1, M1b, M2a, M2b, M3a, M3b, M3c, and M3.

M0 is the non-Bayesian predictive baseline.

## Main Findings
- Best test RMSE: M1, 14.0337
- Full M3 test RMSE: 14.0791
- M3 baseline home advantage: 2.511 points
- M3 baseline home effect 95% credible interval: [1.747, 3.299]
- No stadium roof or elevation coefficient had a 95% credible interval excluding zero.
- Relative rest had a positive posterior association with scoring margin.
- All fitted Bayesian models had maximum R-hat below 1.01 and zero divergences.

## Important Limitations
- Stadium metadata was owner-approved following automated consistency checks.
- Independent verification of every historical game assignment was not completed.
- USGS elevations represent interpolated terrain elevations, not surveyed field heights.
- The SoFi Stadium canopy effect was not estimable from the training period.
- Predictive 90% intervals covered approximately 86% of test observations.
- Associations from this observational analysis should not be interpreted as causal effects.

## Reproduction
Primary pipeline: code/nfl_venue/run_all_models.R
Stan model: code/nfl_venue/stan/venue_model.stan
Final stadium features: data/stadium_features.csv
Historical surface data: data/stadium_surface_by_game.csv
Game-to-stadium matches: data/stadium_game_matches.csv

The source data and analysis code are retained to reproduce the model outputs.
Large fitted-model RDS objects are intentionally excluded from Git.
