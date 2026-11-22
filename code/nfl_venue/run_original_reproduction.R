# Standalone reproduction of the ORIGINAL Benz/Bliss/Lopez NFL Stan models.
# These are retrospective full-sample fits, not chronological holdout scores.
# Run from repository root after obtaining original model_1.stan / model_2.stan.

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(rstan)
  library(ggplot2)
})
rstan_options(auto_write = TRUE)
options(mc.cores = min(4L, parallel::detectCores()))

source_csv <- "data/final/NFL_games.csv"
model_dir <- "code/model/stan"
out <- "results/reproduction"
dir.create(out, recursive = TRUE, showWarnings = FALSE)
for (f in c(source_csv, file.path(model_dir, "model_1.stan"),
            file.path(model_dir, "model_2.stan"))) {
  if (!file.exists(f)) stop("Required file not found: ", f)
}

nfl <- read_csv(source_csv, show_col_types = FALSE) %>%
  filter(satisfies_cutoff %in% TRUE, between(season, 2004, 2023)) %>%
  mutate(h_point_diff = as.numeric(home_score) - as.numeric(away_score),
         h_adv = as.integer(location == "Home")) %>%
  filter(!is.na(h_point_diff), !is.na(home_team), !is.na(away_team))

teams <- sort(unique(c(paste(nfl$season, nfl$home_team, sep = "_"),
                       paste(nfl$season, nfl$away_team, sep = "_"))))
home_code <- as.integer(match(paste(nfl$season, nfl$home_team, sep = "_"), teams))
away_code <- as.integer(match(paste(nfl$season, nfl$away_team, sep = "_"), teams))
season_code <- as.integer(nfl$season - min(nfl$season) + 1)
common <- list(num_clubs = length(teams), num_games = nrow(nfl),
               home_team_code = home_code, away_team_code = away_code,
               h_point_diff = nfl$h_point_diff, h_adv = nfl$h_adv)

message("Full-sample games: ", nrow(nfl), "; source range: ",
        min(nfl$season), "-", max(nfl$season))
fit1 <- stan(file = file.path(model_dir, "model_1.stan"),
             data = common, seed = 73097L, chains = 4, iter = 2000,
             warmup = 500, control = list(adapt_delta = 0.95,
                                           max_treedepth = 12),
             pars = "mu", include = FALSE)
write_csv(as.data.frame(summary(fit1, pars = c("alpha", "sigma_m"))$summary) %>%
            tibble::rownames_to_column("parameter"),
          file.path(out, "original_model1_summary.csv"))
saveRDS(fit1, file.path(out, "original_model1_fit.rds"))

fit2 <- stan(file = file.path(model_dir, "model_2.stan"),
             data = c(common, list(num_seasons = max(season_code),
                                   season = season_code)),
             seed = 73097L, chains = 4, iter = 2000, warmup = 500,
             control = list(adapt_delta = 0.999, max_treedepth = 12),
             pars = "mu", include = FALSE)
write_csv(as.data.frame(summary(fit2, pars = c("alpha_intercept", "alpha_trend"))$summary) %>%
            tibble::rownames_to_column("parameter"),
          file.path(out, "original_model2_summary.csv"))
saveRDS(fit2, file.path(out, "original_model2_fit.rds"))

post <- rstan::extract(fit2, pars = c("alpha_intercept", "alpha_trend"))
# Original paper uses season code 1 for 2004; intercept is season index 0,
# so the first season's fitted HFA is intercept + 1 * trend.
trend <- do.call(rbind, lapply(sort(unique(nfl$season)), function(year) {
  period <- year - min(nfl$season) + 1
  draw <- post$alpha_intercept + period * post$alpha_trend
  data.frame(season = year, mean = mean(draw),
             lower = unname(quantile(draw, .025)),
             upper = unname(quantile(draw, .975)))
}))
write_csv(trend, file.path(out, "original_model2_trend.csv"))
p <- ggplot(trend, aes(season, mean)) +
  geom_ribbon(aes(ymin = lower, ymax = upper), alpha = .2) +
  geom_line(linewidth = .8) + geom_hline(yintercept = 0, linetype = 2) +
  theme_minimal() + labs(title = "Parent model: NFL home advantage by season",
                         y = "Estimated points", x = "NFL season")
ggsave(file.path(out, "original_model2_trend.png"), p, width = 8, height = 5)
message("Finished full-sample reproduction: ", out)
