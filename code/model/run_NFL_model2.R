
library(tidyverse)
library(rstan)

# Set working directory
setwd("C:/Users/Soren/comprehensive_survey_american_football_home_adv")

rstan_options(auto_write = TRUE)
options(mc.cores = 4)

# Load NFL dataset
df_NFL <- read_csv(
  "data/final/NFL_games.csv",
  show_col_types = FALSE
) |>
  filter(satisfies_cutoff, season >= 2004) |>
  mutate(
    home_point_diff = home_score - away_score,
    home_game = as.integer(location == "Home")
  ) |>
  filter(!is.na(home_point_diff))

# Assign unique codes to teams within seasons
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

# Encode seasons beginning at 1
season_code <- df_NFL$season - min(df_NFL$season) + 1

# Prepare data for original Model 2
stan_data <- list(
  num_clubs = length(teams),
  num_games = nrow(df_NFL),
  num_seasons = max(season_code),
  season = season_code,
  home_team_code = home_code,
  away_team_code = away_code,
  h_point_diff = df_NFL$home_point_diff,
  h_adv = df_NFL$home_game
)

# Fit original Bayesian Model 2
fit2 <- stan(
  file = "code/model/stan/model_2.stan",
  data = stan_data,
  seed = 73097,
  chains = 4,
  iter = 2000,
  warmup = 500,
  control = list(adapt_delta = 0.999),,
  pars = "mu",
  include = FALSE
)

# Display home-field advantage parameters
print(fit2, pars = c("alpha_intercept", "alpha_trend"))

# Save model
dir.create(
  "stan_results/model_2",
  recursive = TRUE,
  showWarnings = FALSE
)

saveRDS(fit2, "stan_results/model_2/NFL.rds")

# Save numerical results
dir.create(
  "results/reproduction",
  recursive = TRUE,
  showWarnings = FALSE
)

model2_summary <- summary(
  fit2,
  pars = c("alpha_intercept", "alpha_trend")
)$summary

write.csv(
  model2_summary,
  "results/reproduction/NFL_model2_summary.csv"
)

# Plot estimated home advantage over time
posterior2 <- rstan::extract(
  fit2,
  pars = c("alpha_intercept", "alpha_trend")
)

seasons <- sort(unique(df_NFL$season))

trend_results <- map_dfr(seasons, function(y) {
  t <- y - min(seasons) + 1
  
  estimates <- posterior2$alpha_intercept +
    posterior2$alpha_trend * t
  
  tibble(
    season = y,
    mean = mean(estimates),
    lower = quantile(estimates, 0.025),
    upper = quantile(estimates, 0.975)
  )
})

p2 <- ggplot(trend_results, aes(x = season, y = mean)) +
  geom_ribbon(
    aes(ymin = lower, ymax = upper),
    fill = "steelblue",
    alpha = 0.2
  ) +
  geom_line(color = "steelblue", linewidth = 1) +
  geom_hline(yintercept = 0, linetype = "dashed") +
  labs(
    title = "NFL Home-Field Advantage Over Time",
    subtitle = "Benz, Bliss & Lopez — Model 2 reproduction",
    x = "Season",
    y = "Estimated home-field advantage (points)"
  ) +
  theme_minimal()

print(p2)

ggsave(
  "results/reproduction/NFL_model2_trend.png",
  p2,
  width = 8,
  height = 5
)
