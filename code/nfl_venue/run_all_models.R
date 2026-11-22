# NFL stadium-level home-field advantage: chronological model comparison
# Team 13 | DS 340W | November 2026
# Run from the repository root: Rscript code/nfl_venue/run_all_models.R
# Do not use setwd() or mix this up with the high-school hierarchical model.

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(ggplot2)
  library(rstan)
})

rstan_options(auto_write = TRUE)
options(mc.cores = min(4L, parallel::detectCores()))
set.seed(73097)

DATA_PATH <- "data/final/NFL_games.csv"
FEATURES_PATH <- "data/stadium_features.csv"
STADIUM_MATCH_PATH <- "data/stadium_game_matches.csv"
STAN_PATH <- "code/nfl_venue/stan/venue_model.stan"
OUTPUT <- "results/venue_models"
SEED <- 73097L
CHAINS <- 4L
ITER <- 2000L
WARMUP <- 500L
DRAWS_FOR_PREDICTION <- 250L
RUN_LOO <- identical(tolower(Sys.getenv("RUN_LOO", "false")), "true")
RUN_ALL <- identical(tolower(Sys.getenv("RUN_ALL", "true")), "true")
dir.create(OUTPUT, recursive = TRUE, showWarnings = FALSE)
writeLines(capture.output(sessionInfo()), file.path(OUTPUT, "R_sessionInfo.txt"))
stopifnot(file.exists(DATA_PATH), file.exists(STAN_PATH))

# Physical-venue ID: source coordinates represent the *designated home
# franchise's usual stadium*, not the actual venue of neutral-site games.
# IDs based on rounded coordinates are PROVISIONAL and require manual audit.
venue_key <- function(lat, lng) sprintf("%.3f:%.3f", lat, lng)

parse_game_date <- function(x) {
  as_date <- as.Date(as.character(x), format = "%m/%d/%Y")
  missing <- is.na(as_date)
  if (any(missing)) as_date[missing] <- as.Date(as.character(x[missing]))
  as_date
}

make_data <- function() {
  raw <- read_csv(DATA_PATH, show_col_types = FALSE)
  required <- c("season", "date", "location", "home_team", "away_team",
                "home_score", "away_score", "satisfies_cutoff",
                "lat_home", "lng_home", "distance")
  absent <- setdiff(required, names(raw))
  if (length(absent)) stop("Source dataset lacks: ", paste(absent, collapse = ", "))
  df <- raw %>%
    filter(satisfies_cutoff %in% TRUE, between(season, 2004, 2023)) %>%
    mutate(date_parsed = parse_game_date(date),
           margin = as.numeric(home_score) - as.numeric(away_score),
           home_flag = as.integer(location == "Home"),
           venue_id = venue_key(as.numeric(lat_home), as.numeric(lng_home)),
           franchise = as.character(home_team),
           distance_miles = as.numeric(distance)) %>%
    filter(!is.na(margin), !is.na(date_parsed), !is.na(home_team),
           !is.na(away_team), !is.na(season)) %>%
    distinct() %>%
    arrange(date_parsed, home_team, away_team) %>%
    mutate(game_id = row_number())

  # A physical stadium can share coordinates with a replaced venue. Match
  # physical stadiums by GAME DATE + location, using a reviewed crosswalk.
  # Example: Giants Stadium and MetLife Stadium have the same CSV coordinates.
  df <- df %>% mutate(
    game_key = paste(season, format(date_parsed, "%Y-%m-%d"),
                     trimws(home_team), trimws(away_team), sep = "|"),
    stadium_name = NA_character_)
  if (file.exists(STADIUM_MATCH_PATH)) {
    matches <- read_csv(STADIUM_MATCH_PATH, show_col_types = FALSE)
    required_matches <- c("game_key", "stadium_id", "stadium_name", "match_status")
    if (length(setdiff(required_matches, names(matches))))
      stop("Reviewed stadium crosswalk has missing required columns")
    if (anyDuplicated(matches$game_key)) stop("Duplicate game keys in reviewed crosswalk")
    df <- df %>% select(-stadium_name) %>%
      left_join(matches %>% select(all_of(required_matches)), by = "game_key")
    if (any(is.na(df$stadium_id[df$home_flag == 1L])) ||
        any(is.na(df$match_status[df$home_flag == 1L]) |
            df$match_status[df$home_flag == 1L] != "matched"))
      stop("Reviewed stadium crosswalk does not match EVERY non-neutral game. ",
           "Inspect results/venue_models/stadium_integration/ first.")
    df$venue_id <- ifelse(df$home_flag == 1L, df$stadium_id, "NEUTRAL")
    message("Using reviewed physical stadium IDs from ", STADIUM_MATCH_PATH)
  } else {
    if (any((is.na(df$lat_home) | is.na(df$lng_home)) & df$home_flag == 1L))
      stop("Non-neutral game lacks stadium coordinates and no reviewed crosswalk exists")
    df$venue_id <- ifelse(df$home_flag == 1L, df$venue_id, "NEUTRAL")
    warning("No reviewed stadium crosswalk. Using PROVISIONAL rounded-coordinate IDs. ",
            "Do not interpret stadium-specific results until stadium IDs are audited.")
  }
  if (anyDuplicated(df$game_key))
    stop("Game keys are not unique; resolve duplicated schedule rows")
  if (anyDuplicated(df$game_id)) stop("Duplicate game IDs")

  # Audit potential stadium changes / shared coordinates / team-specific IDs.
  audit <- df %>% filter(home_flag == 1) %>%
    group_by(franchise, season) %>%
    summarise(n_venues = n_distinct(venue_id),
              venues = paste(sort(unique(venue_id)), collapse = "; "),
              .groups = "drop")
  write_csv(audit, file.path(OUTPUT, "stadium_audit_by_franchise_year.csv"))
  if (any(audit$n_venues > 1)) {
    warning("Some franchises have multiple stadium coordinates in one season; ",
            "inspect stadium_audit_by_franchise_year.csv before interpreting ranks")
  }

  # Rest is known BEFORE kickoff. Differences > 35 days are offseason gaps,
  # not ordinary rest; they are marked missing rather than averaged silently.
  previous_date <- new.env(parent = emptyenv())
  rest_h <- rest_a <- rep(NA_real_, nrow(df))
  for (i in seq_len(nrow(df))) {
    h <- df$home_team[i]; a <- df$away_team[i]; d <- df$date_parsed[i]
    if (exists(h, envir = previous_date, inherits = FALSE)) {
      v <- as.numeric(d - get(h, envir = previous_date))
      if (v >= 1 && v <= 35) rest_h[i] <- v
    }
    if (exists(a, envir = previous_date, inherits = FALSE)) {
      v <- as.numeric(d - get(a, envir = previous_date))
      if (v >= 1 && v <= 35) rest_a[i] <- v
    }
    assign(h, d, envir = previous_date)
    assign(a, d, envir = previous_date)
  }
  df$rest_missing <- as.integer(is.na(rest_h) | is.na(rest_a))
  df$rest_diff <- ifelse(df$rest_missing == 1L, 0, rest_h - rest_a)
  # The original distance is from the visitor to a home venue. Neutral-game
  # travel is not necessarily that distance; disable it for neutral games.
  df$log_travel <- ifelse(df$home_flag == 1L & is.finite(df$distance_miles),
                          log1p(pmax(0, df$distance_miles)), 0)
  df$travel_missing <- as.integer(!is.finite(df$distance_miles) |
                                  df$home_flag == 0L)
  df
}

df <- make_data()
write_csv(df %>% count(season, name = "n_games"),
          file.path(OUTPUT, "dataset_counts_by_season.csv"))

train <- df %>% filter(season %in% 2004:2017)
valid <- df %>% filter(season %in% 2018:2019)
test <- df %>% filter(season %in% 2021:2023)
pandemic <- df %>% filter(season == 2020)
stopifnot(nrow(train) > 0, nrow(valid) > 0, nrow(test) > 0,
          max(train$season) < min(valid$season),
          max(valid$season) < min(test$season))
write_csv(data.frame(split = c("train", "validation", "test", "pandemic_only"),
                     games = c(nrow(train), nrow(valid), nrow(test), nrow(pandemic)),
                     from_season = c(2004, 2018, 2021, 2020),
                     to_season = c(2017, 2019, 2023, 2020)),
          file.path(OUTPUT, "split_counts.csv"))

# Build a blank stadium metadata template; the original NFL_games.csv does
# NOT contain verified roof, playing surface, or altitude information.
all_venue <- df %>% filter(home_flag == 1) %>%
  group_by(venue_id) %>%
  summarise(team_examples = paste(head(unique(franchise), 3), collapse = "; "),
            stadium_name = first(stadium_name),
            first_season = min(season), last_season = max(season),
            latitude = first(lat_home), longitude = first(lng_home),
            .groups = "drop") %>% arrange(first_season, team_examples)
write_csv(all_venue, file.path(OUTPUT, "venue_coordinate_audit.csv"))
if (!file.exists(FEATURES_PATH)) {
  template <- all_venue %>% transmute(venue_id, team_examples, first_season,
                                     last_season, latitude, longitude,
                                     roof_type = NA_character_,
                                     surface_type = NA_character_,
                                     altitude_m = NA_real_,
                                     source_url = NA_character_)
  write_csv(template, file.path(OUTPUT, "stadium_features_TO_FILL.csv"))
  message("No curated data/stadium_features.csv found. Generated a template in ",
          OUTPUT, "; attribute-based models will be skipped.")
}

# Feature standardization uses the TRAINING SET ONLY.
base_feature_names <- c("rest_diff", "rest_missing", "log_travel", "travel_missing")
feature_mean <- vapply(train[base_feature_names], mean, numeric(1))
feature_sd <- vapply(train[base_feature_names], sd, numeric(1))
feature_sd[!is.finite(feature_sd) | feature_sd == 0] <- 1
scaled_X <- function(dat) {
  x <- as.matrix(dat[base_feature_names])
  sweep(sweep(x, 2L, feature_mean, "-"), 2L, feature_sd, "/")
}

# Only use externally checked physical features. Don't invent attributes or
# treat latitude and longitude as equivalent to roof/altitude measurements.
prepare_attributes <- function() {
  if (!file.exists(FEATURES_PATH)) return(NULL)
  f <- read_csv(FEATURES_PATH, show_col_types = FALSE)
  req <- c("venue_id", "roof_type", "surface_type", "altitude_m", "source_url")
  if (length(setdiff(req, names(f))))
    stop("stadium_features.csv lacks: ", paste(setdiff(req, names(f)), collapse = ", "))
  if (anyDuplicated(f$venue_id)) stop("stadium_features.csv needs one row per venue_id")
  if (!"verified" %in% names(f) ||
      any(is.na(f$verified) | tolower(as.character(f$verified)) != "true")) {
    warning("Stadium attributes have not all been verified. Skipping attribute models.")
    return(NULL)
  }
  if (!file.exists(STADIUM_MATCH_PATH)) {
    warning("Unreviewed coordinate venue IDs cannot support an attribute-informed model.")
    return(NULL)
  }
  needed <- all_venue$venue_id
  f <- tibble(venue_id = needed) %>% left_join(f, by = "venue_id")
  roof <- tolower(trimws(f$roof_type))
  surface <- tolower(trimws(f$surface_type))
  invalid <- is.na(roof) | !(roof %in% c("open", "dome", "retractable")) |
    is.na(surface) | !(surface %in% c("grass", "turf")) |
    !is.finite(f$altitude_m) | is.na(f$source_url) | !nzchar(f$source_url)
  if (any(invalid)) {
    write_csv(f[invalid, ], file.path(OUTPUT, "stadium_features_missing_or_invalid.csv"))
    warning("Stadium metadata incomplete/invalid. Skipping M3b, M3c, M3. ",
            "Fill roof_type=open/dome/retractable, surface_type=grass/turf, ",
            "altitude_m and source_url for EVERY venue.")
    return(NULL)
  }
  f$roof_dome <- as.integer(roof == "dome")
  f$roof_retractable <- as.integer(roof == "retractable")
  f$turf <- as.integer(surface == "turf")
  f
}
attr_data <- prepare_attributes()
venue_train_levels <- sort(unique(train$venue_id[train$home_flag == 1]))
franchise_levels <- sort(unique(c(train$home_team, train$away_team)))
S <- length(unique(train$season))

attr_columns <- c("roof_dome", "roof_retractable", "turf", "altitude_m")
if (!is.null(attr_data)) {
  attr_train <- attr_data[match(venue_train_levels, attr_data$venue_id), ]
  z_means <- vapply(attr_train[attr_columns], mean, numeric(1))
  z_sds <- vapply(attr_train[attr_columns], sd, numeric(1))
  z_sds[!is.finite(z_sds) | z_sds == 0] <- 1
  z_scaled <- function(ids) {
    z <- as.matrix(attr_data[match(ids, attr_data$venue_id), attr_columns])
    if (anyNA(z)) stop("Missing stadium attributes for a requested venue")
    sweep(sweep(z, 2L, z_means, "-"), 2L, z_sds, "/")
  }
} else {
  z_scaled <- function(ids) matrix(0, length(ids), 1L)
}

# Deterministic team-season indexing. Franchise names are used as provided by
# the parent dataset; validate relocation/name aliases in the audit output.
team_table <- bind_rows(
  train %>% transmute(season, team = home_team),
  train %>% transmute(season, team = away_team)
) %>% distinct() %>% arrange(season, team) %>% mutate(team_idx = row_number())
team_table$prev_idx <- vapply(seq_len(nrow(team_table)), function(i) {
  older <- which(team_table$team == team_table$team[i] &
                 team_table$season < team_table$season[i])
  if (length(older)) as.integer(tail(older, 1L)) else 0L
}, integer(1))
stopifnot(all(team_table$prev_idx < team_table$team_idx))
team_id <- function(year, team) match(paste(year, team),
                                       paste(team_table$season, team_table$team))
h <- team_id(train$season, train$home_team)
a <- team_id(train$season, train$away_team)
stopifnot(!anyNA(h), !anyNA(a))

# Even no-venue variants keep a dummy level 1. The switches in Stan ensure
# its value contributes exactly zero rather than leaking a stadium effect.
make_stan_data <- function(name, ridge_sd = 2) {
  config <- switch(name,
    M1 = c(0,0,0,0,0,0,0),
    M1b = c(1,0,0,0,0,0,0),
    M2a = c(1,1,0,0,0,0,1),
    M2b = c(1,1,0,0,0,0,0),
    M3a = c(1,1,1,0,1,1,0),
    M3b = c(1,1,1,1,0,1,0),
    M3c = c(1,1,0,1,1,1,0),
    M3 = c(1,1,1,1,1,1,0),
    stop("Unknown model: ", name)
  )
  names(config) <- c("use_trend", "use_venue", "use_franchise",
                     "use_attributes", "use_time", "use_covariates", "ridge_venue")
  needs_attrs <- config[["use_attributes"]] == 1
  if (needs_attrs && is.null(attr_data)) return(NULL)
  v_levels <- if (config[["use_venue"]] == 1) venue_train_levels else "dummy"
  f_levels <- if (config[["use_franchise"]] == 1) franchise_levels else "dummy"
  n_v <- length(v_levels)
  z <- if (needs_attrs) z_scaled(v_levels) else matrix(0, n_v, 1L)
  X <- if (config[["use_covariates"]] == 1) scaled_X(train) else
    matrix(0, nrow(train), length(base_feature_names))
  first_year <- if (config[["use_time"]] == 1) {
    vapply(v_levels, function(v) as.integer(min(train$season[train$venue_id == v & train$home_flag == 1]) - 2003L), integer(1))
  } else rep(1L, n_v)
  mapping <- if (config[["use_venue"]] == 1)
    match(train$venue_id, v_levels) else rep(1L, nrow(train))
  # Dummy index for neutral games; its venue term is suppressed by home_flag.
  mapping[is.na(mapping)] <- 1L
  list(
    N = nrow(train), T = nrow(team_table), V = n_v, F = length(f_levels),
    S = S, K = ncol(X), Q = ncol(z),
    D = if (config[["use_time"]] == 1) S else 1L,
    home_t = as.integer(h), away_t = as.integer(a),
    prev_t = as.integer(team_table$prev_idx),
    team_year = as.integer(team_table$season - 2003L),
    venue = as.integer(mapping),
    franchise = as.integer(if (config[["use_franchise"]] == 1)
      match(train$home_team, f_levels) else rep(1L, nrow(train))),
    year = as.integer(train$season - 2003L),
    first_venue_year = as.integer(first_year),
    home_flag = as.integer(train$home_flag), y = as.numeric(train$margin),
    X = unname(X), Z = unname(z),
    use_trend = as.integer(config[["use_trend"]]),
    use_venue = as.integer(config[["use_venue"]]),
    use_franchise = as.integer(config[["use_franchise"]]),
    use_attributes = as.integer(config[["use_attributes"]]),
    use_time = as.integer(config[["use_time"]]),
    use_covariates = as.integer(config[["use_covariates"]]),
    ridge_venue = as.integer(config[["ridge_venue"]]), ridge_sd = ridge_sd
  )
}

# For validation/test, team-season strength isn't estimated from future games.
# Instead we forecast each franchise's LAST TRAINING posterior strength by rho^gap.
# This is deliberately conservative; it is NOT a within-test-season Bayesian update.
forecast_mu_draws <- function(fit, stan_input, future, name, n_draws = DRAWS_FOR_PREDICTION) {
  needed <- c("theta", "rho", "alpha0", "alpha_trend", "venue_base",
              "franchise_home", "drift_effect", "beta", "gamma", "sigma_y")
  post <- rstan::extract(fit, pars = needed, permuted = TRUE)
  total <- length(post$alpha0)
  use <- sort(sample.int(total, size = min(n_draws, total), replace = FALSE))
  last_index <- vapply(franchise_levels, function(team) {
    candidates <- which(team_table$team == team)
    if (length(candidates)) tail(candidates, 1L) else NA_integer_
  }, integer(1))
  last_year <- team_table$season[last_index]
  names(last_index) <- names(last_year) <- franchise_levels

  n <- nrow(future); d <- length(use)
  pred <- matrix(0, nrow = d, ncol = n)
  for (i in seq_len(n)) {
    team_projection <- function(team) {
      idx <- last_index[[team]]
      if (is.null(idx) || is.na(idx)) return(rep(0, d))
      yr_gap <- max(0, future$season[i] - last_year[[team]])
      post$theta[use, idx] * post$rho[use]^yr_gap
    }
    v <- match(future$venue_id[i], venue_train_levels)
    f <- match(future$franchise[i], franchise_levels)
    home_effect <- post$alpha0[use] +
      stan_input$use_trend * post$alpha_trend[use] * (future$season[i] - 2004L)
    if (future$home_flag[i] == 1L && stan_input$use_venue == 1L) {
      if (!is.na(v)) {
        home_effect <- home_effect + post$venue_base[use, v]
        if (stan_input$use_time == 1L) {
          home_effect <- home_effect + post$drift_effect[use, v, stan_input$D]
        }
      } else if (stan_input$use_attributes == 1L) {
        # New/never-seen venue: attribute-informed prior mean; eta and drift=0.
        z <- as.numeric(z_scaled(future$venue_id[i]))
        gamma <- matrix(post$gamma[use, ], nrow = d)
        home_effect <- home_effect + drop(gamma %*% z)
      }
    }
    if (future$home_flag[i] == 1L && stan_input$use_franchise == 1L && !is.na(f))
      home_effect <- home_effect + post$franchise_home[use, f]
    pred[, i] <- team_projection(future$home_team[i]) -
      team_projection(future$away_team[i]) + future$home_flag[i] * home_effect
    if (stan_input$use_covariates == 1L) {
      beta <- matrix(post$beta[use, ], nrow = d)
      pred[, i] <- pred[, i] + drop(beta %*% as.numeric(scaled_X(future[i, ])))
    }
  }
  list(mu = pred, sigma = post$sigma_y[use])
}

# Point predictions are posterior means. Predictive intervals also include
# observation noise, not merely parameter uncertainty.
score_draws <- function(pred, actual, model, split, seed = 73097L) {
  set.seed(seed)
  mu <- pred$mu
  obs <- matrix(rnorm(length(mu), mean = as.vector(mu),
                      sd = rep(pred$sigma, ncol(mu))),
                nrow = nrow(mu), ncol = ncol(mu))
  center <- colMeans(mu)
  pi50 <- apply(obs, 2, quantile, probs = c(0.25, 0.75))
  pi90 <- apply(obs, 2, quantile, probs = c(0.05, 0.95))
  tibble(model = model, split = split, n_games = length(actual),
         MAE = mean(abs(actual - center)),
         RMSE = sqrt(mean((actual - center)^2)),
         coverage_50 = mean(actual >= pi50[1, ] & actual <= pi50[2, ]),
         coverage_90 = mean(actual >= pi90[1, ] & actual <= pi90[2, ]))
}

baseline <- mean(train$margin[train$home_flag == 1])
score_baseline <- function(future, split) {
  prediction <- baseline * future$home_flag
  tibble(model = "M0", split = split, n_games = nrow(future),
         MAE = mean(abs(future$margin - prediction)),
         RMSE = sqrt(mean((future$margin - prediction)^2)),
         coverage_50 = NA_real_, coverage_90 = NA_real_)
}

summarise_fit_diagnostics <- function(fit, name) {
  summ <- summary(fit)$summary
  pars <- rstan::get_sampler_params(fit, inc_warmup = FALSE)
  divergences <- sum(vapply(pars, function(m) sum(m[, "divergent__"]), numeric(1)))
  tibble(model = name,
         max_Rhat = suppressWarnings(max(summ[, "Rhat"], na.rm = TRUE)),
         min_n_eff = suppressWarnings(min(summ[, "n_eff"], na.rm = TRUE)),
         divergences = divergences)
}

stadium_table <- function(fit, stan_input, model) {
  if (stan_input$use_venue == 0L) return(NULL)
  post <- rstan::extract(fit, pars = c("venue_base", "drift_effect"))
  year_idx <- stan_input$D
  out <- lapply(seq_along(venue_train_levels), function(j) {
    effect <- post$venue_base[, j]
    if (stan_input$use_time == 1L) effect <- effect + post$drift_effect[, j, year_idx]
    tibble(venue_id = venue_train_levels[j], model = model,
           mean = mean(effect), lower = unname(quantile(effect, .025)),
           upper = unname(quantile(effect, .975)),
           prob_positive = mean(effect > 0),
           train_games = sum(train$home_flag == 1 &
                             train$venue_id == venue_train_levels[j]))
  })
  bind_rows(out) %>% left_join(all_venue, by = "venue_id") %>%
    arrange(desc(mean))
}

compare <- list(score_baseline(valid, "validation"),
                score_baseline(test, "test"),
                score_baseline(pandemic, "2020_sensitivity"))
all_diags <- list()
all_rankings <- list()
stan_model_compiled <- rstan::stan_model(STAN_PATH)

fit_variant <- function(name, ridge_sd = 2, save_outputs = TRUE) {
  dat <- make_stan_data(name, ridge_sd)
  if (is.null(dat)) return(NULL)
  message("Fitting ", name, if (name == "M2a") paste0(" (ridge SD=", ridge_sd, ")") else "")
  # Do not store thousands of pointwise mu/log_lik samples unless LOO is requested.
  fit <- rstan::sampling(stan_model_compiled, data = dat,
                        seed = SEED, chains = CHAINS, iter = ITER,
                        warmup = WARMUP, refresh = 100L,
                        pars = if (RUN_LOO) "mu" else c("mu", "log_lik"),
                        include = FALSE,
                        control = list(adapt_delta = 0.99, max_treedepth = 12))
  if (save_outputs) {
    out_dir <- file.path(OUTPUT, name)
    dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
    saveRDS(fit, file.path(out_dir, "fit.rds"))
    write_csv(summarise_fit_diagnostics(fit, name),
              file.path(out_dir, "diagnostics.csv"))
    ranks <- stadium_table(fit, dat, name)
    if (!is.null(ranks)) write_csv(ranks, file.path(out_dir, "stadium_posteriors.csv"))
    if (RUN_LOO) {
      if (!requireNamespace("loo", quietly = TRUE)) stop("Install loo first")
      ll <- loo::extract_log_lik(fit, parameter_name = "log_lik")
      loo_obj <- loo::loo(ll)
      saveRDS(loo_obj, file.path(out_dir, "loo_training_only.rds"))
    }
  }
  list(fit = fit, data = dat)
}

# Ridge penalty SD is selected ONLY on validation seasons; the test set is
# never used for a tuning decision. This is not a claim about prior-paper LOO.
ridge_choice <- NA_real_
if (RUN_ALL) {
  tune <- list()
  for (sd in c(0.5, 1, 2, 4)) {
    res <- fit_variant("M2a", ridge_sd = sd, save_outputs = FALSE)
    p <- forecast_mu_draws(res$fit, res$data, valid, "M2a")
    sc <- score_draws(p, valid$margin, "M2a", "validation")
    tune[[length(tune) + 1L]] <- sc %>% mutate(ridge_sd = sd)
    rm(res)
    gc(verbose = FALSE)
  }
  ridge_scores <- bind_rows(tune) %>% arrange(MAE)
  write_csv(ridge_scores, file.path(OUTPUT, "ridge_validation_grid.csv"))
  ridge_choice <- ridge_scores$ridge_sd[1]
  message("Selected ridge SD = ", ridge_choice, " on validation MAE")
}

variants <- c("M1", "M1b", "M2a", "M2b", "M3a", "M3b", "M3c", "M3")
if (!RUN_ALL) variants <- c("M1", "M1b", "M2b", "M3a")
for (name in variants) {
  if (name %in% c("M3b", "M3c", "M3") && is.null(attr_data)) {
    message("SKIPPING ", name, ": verified stadium metadata is required")
    next
  }
  res <- fit_variant(name, ridge_sd = if (is.na(ridge_choice)) 2 else ridge_choice)
  if (is.null(res)) next
  all_diags[[name]] <- summarise_fit_diagnostics(res$fit, name)
  all_rankings[[name]] <- stadium_table(res$fit, res$data, name)
  for (split in c("validation", "test", "2020_sensitivity")) {
    holdout <- switch(split, validation = valid, test = test,
                      `2020_sensitivity` = pandemic)
    p <- forecast_mu_draws(res$fit, res$data, holdout, name)
    compare[[length(compare) + 1L]] <- score_draws(p, holdout$margin, name, split)
    write_csv(tibble(game_id = holdout$game_id, season = holdout$season,
                     actual_margin = holdout$margin, predicted = colMeans(p$mu)),
              file.path(OUTPUT, name, paste0(split, "_predictions.csv")))
  }
  rm(res)
  gc(verbose = FALSE)
}

scores <- bind_rows(compare)
write_csv(scores, file.path(OUTPUT, "model_comparison.csv"))
write_csv(bind_rows(all_diags), file.path(OUTPUT, "all_diagnostics.csv"))
write_csv(bind_rows(all_rankings), file.path(OUTPUT, "all_stadium_effects.csv"))

# Report rank correlation only on physically matched stadiums across models.
if (!is.null(all_rankings$M2b) && !is.null(all_rankings$M3)) {
  a <- all_rankings$M2b %>% select(venue_id, effect_M2b = mean)
  b <- all_rankings$M3 %>% select(venue_id, effect_M3 = mean)
  both <- inner_join(a, b, by = "venue_id")
  write_csv(tibble(models = "M2b_vs_M3", matched_stadiums = nrow(both),
                   spearman_rho = cor(both$effect_M2b, both$effect_M3,
                                      method = "spearman")),
            file.path(OUTPUT, "ranking_stability.csv"))
}

# A credible interval crossing 0 warns against a definitive stadium ranking.
ranking <- if (!is.null(all_rankings$M3)) all_rankings$M3 else all_rankings$M2b
if (!is.null(ranking)) {
  p <- ranking %>%
    ggplot(aes(x = reorder(venue_id, mean), y = mean)) +
    geom_pointrange(aes(ymin = lower, ymax = upper), size = 0.2) +
    coord_flip() + geom_hline(yintercept = 0, linetype = 2) +
    labs(title = "Adjusted venue home-field effects (training data)",
         subtitle = "95% credible intervals; associations, not causal effects",
         x = "Reviewed physical venue ID", y = "Points vs league mean") +
    theme_minimal(base_size = 10)
  ggsave(file.path(OUTPUT, "venue_credible_intervals.png"), p,
         width = 10, height = max(6, 0.18 * nrow(ranking)))
}
message("Saved numerical results, diagnostics, and plots under ", OUTPUT)
message("TEST SET NOT used for fitting or for ridge tuning.")
