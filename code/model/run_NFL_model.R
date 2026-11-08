
library(tidyverse)
library(rstan)

# Set working directory
setwd("C:/Users/Soren/comprehensive_survey_american_football_home_adv")

# Original paper settings
rstan_options(auto_write = TRUE)
options(mc.cores = 4)

# Load NFL dataset
df_NFL <- read_csv("data/final/NFL_games.csv") |>
  filter(satisfies_cutoff, season >= 2004) |>
  mutate(
    home_point_diff = home_score - away_score,
    home_game = as.integer(location == "Home")
  ) |>
  filter(!is.na(home_point_diff))

# Assign unique team codes for each season
teams <- sort(unique(c(
  paste(df_NFL$season, df_NFL$home_team, sep = "_"),
  paste(df_NFL$season, df_NFL$away_team, sep = "_")
)))

home_code <- match(
  paste(df_NFL$season, df_NFL$home_team, sep = "_"),
  teams
)

away_code <- match(
  paste(df_NFL$season, df_NFL$away_team, sep = "_"),
  teams
)

# Prepare NFL data for Stan
stan_data <- list(
  num_clubs = length(teams),
  num_games = nrow(df_NFL),
  home_team_code = home_code,
  away_team_code = away_code,
  h_point_diff = df_NFL$home_point_diff,
  h_adv = df_NFL$home_game
)

# Run original Bayesian Model 1
fit <- stan(
  file = "code/model/stan/model_1.stan",
  data = stan_data,
  seed = 73097,
  chains = 4,
  iter = 2000,
  warmup = 500,
  control = list(adapt_delta = 0.95),
  pars = "mu",
  include = FALSE
)

# Display model results
print(fit)

# Save results
dir.create(
  "stan_results/model_1",
  recursive = TRUE,
  showWarnings = FALSE
)

saveRDS(fit, "stan_results/model_1/NFL.rds")
