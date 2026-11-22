#!/usr/bin/env python3
"""Patch the existing R modeling script to use date-specific turf predictors.

Run from the repository root. Safeguards: strict anchor checks, idempotence,
backup in results/, no writes to source game data or verified metadata.
"""
from pathlib import Path
import shutil

root=Path.cwd()
path=root/'code/nfl_venue/run_all_models.R'
if not path.is_file():
    raise SystemExit('Run from the Git repository root: code/nfl_venue/run_all_models.R missing')
raw=path.read_text(encoding='utf-8')
if '# SURFACE_HISTORY_PATCH_V1' in raw:
    print('R model already patched for historical playing surfaces; nothing changed.')
    raise SystemExit(0)

def replace_exact(before, after):
    global raw
    n=raw.count(before)
    if n!=1: raise ValueError(f'Expected one matching R anchor, found {n}: {before[:110]!r}. No file modified.')
    raw=raw.replace(before,after,1)

try:
    replace_exact('STADIUM_MATCH_PATH <- "data/stadium_game_matches.csv"\n',
       'STADIUM_MATCH_PATH <- "data/stadium_game_matches.csv"\nSURFACE_GAME_PATH <- "data/stadium_surface_by_game.csv"\n')
    replace_exact('  if (anyDuplicated(df$game_key))\n    stop("Game keys are not unique; resolve duplicated schedule rows")\n', '''  if (anyDuplicated(df$game_key))
    stop("Game keys are not unique; resolve duplicated schedule rows")

  # SURFACE_HISTORY_PATCH_V1: turf depends on the physical venue AND game date.
  # This file is created only after source and game-level review, not by default.
  df$surface_turf <- NA_real_
  if (file.exists(SURFACE_GAME_PATH)) {
    if (!file.exists(STADIUM_MATCH_PATH))
      stop("Cannot use verified surfaces with provisional venue IDs")
    surface <- read_csv(SURFACE_GAME_PATH, show_col_types = FALSE)
    needed_surface <- c("game_key", "stadium_id", "surface_type", "surface_verified")
    if (length(setdiff(needed_surface, names(surface))))
      stop("Final surface table missing required columns")
    if (anyDuplicated(surface$game_key)) stop("Duplicate keys in game surfaces")
    surface <- surface %>% transmute(
      game_key, surface_stadium_id = stadium_id,
      surface_type = tolower(trimws(as.character(surface_type))),
      surface_verified = tolower(trimws(as.character(surface_verified))) %in% c("true", "t", "1", "yes"))
    df <- left_join(df, surface, by = "game_key")
    invalid <- df$home_flag == 1L &
      (is.na(df$surface_verified) | !df$surface_verified |
       is.na(df$surface_type) | !(df$surface_type %in% c("grass", "turf")) |
       is.na(df$surface_stadium_id) | df$surface_stadium_id != df$venue_id)
    if (any(invalid)) stop(sum(invalid), " home games have unverified/mismatched playing surfaces")
    df$surface_turf <- ifelse(df$home_flag == 1L,
                              as.numeric(df$surface_type == "turf"), 0)
  }
''')
    replace_exact('''scaled_X <- function(dat) {
  x <- as.matrix(dat[base_feature_names])
  sweep(sweep(x, 2L, feature_mean, "-"), 2L, feature_sd, "/")
}
''', '''# Surface is added only to attribute-informed M3 variants. It is centered on
# TRAINING home games and multiplied by home_flag; neutral games have no effect.
scaled_X <- function(dat, include_surface = FALSE) {
  x <- as.matrix(dat[base_feature_names])
  x <- sweep(sweep(x, 2L, feature_mean, "-"), 2L, feature_sd, "/")
  if (include_surface) {
    if (!file.exists(SURFACE_GAME_PATH))
      stop("Model with surface effects requires approved game-level surface file")
    if (any(is.na(dat$surface_turf[dat$home_flag == 1L])))
      stop("Surface category unknown for non-neutral game")
    turf_mean <- mean(train$surface_turf[train$home_flag == 1L])
    turf_sd <- sd(train$surface_turf[train$home_flag == 1L])
    if (!is.finite(turf_sd) || turf_sd == 0) stop("No training variation in playing surface")
    turf <- ifelse(dat$home_flag == 1L,
                   (dat$surface_turf - turf_mean) / turf_sd, 0)
    x <- cbind(x, surface_turf = as.numeric(turf))
  }
  x
}
''')
    replace_exact('''  if (!file.exists(STADIUM_MATCH_PATH)) {
    warning("Unreviewed coordinate venue IDs cannot support an attribute-informed model.")
    return(NULL)
  }
''', '''  if (!file.exists(STADIUM_MATCH_PATH)) {
    warning("Unreviewed coordinate venue IDs cannot support an attribute-informed model.")
    return(NULL)
  }
  if (!file.exists(SURFACE_GAME_PATH) ||
      any(is.na(df$surface_turf[df$home_flag == 1L]))) {
    warning("Date-aware verified playing surfaces missing. Skipping attribute M3 models.")
    return(NULL)
  }
''')
    old='attr_columns <- c("roof_dome", "roof_retractable", "roof_canopy", "turf", "altitude_m")'
    new='attr_columns <- c("roof_dome", "roof_retractable", "roof_canopy", "altitude_m")'
    replace_exact(old,new)
    replace_exact('''  X <- if (config[["use_covariates"]] == 1) scaled_X(train) else
    matrix(0, nrow(train), length(base_feature_names))
''', '''  X <- if (config[["use_covariates"]] == 1)
    scaled_X(train, include_surface = needs_attrs) else
    matrix(0, nrow(train), length(base_feature_names))
''')
    replace_exact('''      pred[, i] <- pred[, i] + drop(beta %*% as.numeric(scaled_X(future[i, ])))
''', '''      pred[, i] <- pred[, i] + drop(beta %*%
        as.numeric(scaled_X(future[i, ],
                            include_surface = (stan_input$use_attributes == 1L))))
''')
except ValueError as e:
    raise SystemExit(str(e))

backup=root/'results/venue_models/backups/run_all_models.R.before_surface_history'
backup.parent.mkdir(parents=True, exist_ok=True)
if not backup.exists(): shutil.copy2(path, backup)
path.write_text(raw, encoding='utf-8')
print('Updated code/nfl_venue/run_all_models.R for game-date surfaces.')
print('Backup at', backup.relative_to(root))
print('The final surface CSV must be reviewed/approved before M3 can run.')
