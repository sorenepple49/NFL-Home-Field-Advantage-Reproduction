// NFL home-field advantage: common, ridge, hierarchical, and informed venue models.
// All home-related terms are multiplied by home_flag; neutral sites have no home edge.
// Team-season strengths evolve through a regularized AR(1) process.
data {
  int<lower=1> N;
  int<lower=1> T;
  int<lower=1> V;
  int<lower=1> F;
  int<lower=1> S;
  int<lower=1> K;
  int<lower=1> Q;
  int<lower=1> D;
  int<lower=1, upper=T> home_t[N];
  int<lower=1, upper=T> away_t[N];
  int<lower=0, upper=T> prev_t[T];
  int<lower=1, upper=S> team_year[T];
  int<lower=1, upper=V> venue[N];
  int<lower=1, upper=F> franchise[N];
  int<lower=1, upper=S> year[N];
  int<lower=1, upper=S> first_venue_year[V];
  int<lower=0, upper=1> home_flag[N];
  vector[N] y;
  matrix[N, K] X;
  matrix[V, Q] Z;
  int<lower=0,upper=1> use_trend;
  int<lower=0,upper=1> use_venue;
  int<lower=0,upper=1> use_franchise;
  int<lower=0,upper=1> use_attributes;
  int<lower=0,upper=1> use_time;
  int<lower=0,upper=1> use_covariates;
  int<lower=0,upper=1> ridge_venue;
  real<lower=0> ridge_sd;
}
parameters {
  vector[T] theta_raw;
  real<lower=0> sigma_initial;
  real<lower=0> sigma_transition;
  real<lower=0, upper=1> rho;
  real alpha0;
  real alpha_trend;
  vector[V] eta_raw;
  real<lower=0> tau_venue;
  vector[F] phi_raw;
  real<lower=0> tau_franchise;
  vector[Q] gamma;
  vector[K] beta;
  matrix[V, D] delta_raw;
  real<lower=0> sigma_drift;
  real<lower=0> sigma_y;
}
transformed parameters {
  vector[T] theta_uncentered;
  vector[T] theta;
  vector[V] venue_base;
  vector[F] franchise_home;
  matrix[V, D] drift_effect;
  vector[N] mu;

  // Earlier team-season indices always precede later ones.
  for (t in 1:T) {
    if (prev_t[t] == 0)
      theta_uncentered[t] = sigma_initial * theta_raw[t];
    else
      theta_uncentered[t] = pow(rho, team_year[t] - team_year[prev_t[t]])
                          * theta_uncentered[prev_t[t]] + sigma_transition * theta_raw[t];
  }
  theta = theta_uncentered;
  // Center strengths within each season for identifiability.
  for (s in 1:S) {
    real avg = 0;
    int n_teams = 0;
    for (t in 1:T) {
      if (team_year[t] == s) {
        avg += theta_uncentered[t];
        n_teams += 1;
      }
    }
    if (n_teams > 0) {
      avg = avg / n_teams;
      for (t in 1:T)
        if (team_year[t] == s) theta[t] = theta_uncentered[t] - avg;
    }
  }

  venue_base = rep_vector(0, V);
  franchise_home = rep_vector(0, F);
  drift_effect = rep_matrix(0, V, D);
  if (use_venue == 1) {
    if (use_attributes == 1) venue_base += Z * gamma;
    if (ridge_venue == 1)
      venue_base += ridge_sd * (eta_raw - mean(eta_raw));
    else
      venue_base += tau_venue * (eta_raw - mean(eta_raw));
  }
  if (use_franchise == 1)
    franchise_home = tau_franchise * (phi_raw - mean(phi_raw));

  // Venue-specific random walks start at zero in the first observed season.
  if (use_time == 1) {
    for (v in 1:V) {
      for (s in 1:D) {
        if (s > first_venue_year[v])
          drift_effect[v,s] = drift_effect[v,s-1] + sigma_drift * delta_raw[v,s];
      }
    }
    // A season-specific centered drift cannot absorb the common home effect.
    for (s in 1:D) {
      real avg = 0;
      int n_active = 0;
      for (v in 1:V) {
        if (s >= first_venue_year[v]) {
          avg += drift_effect[v,s];
          n_active += 1;
        }
      }
      if (n_active > 0) {
        avg /= n_active;
        for (v in 1:V)
          if (s >= first_venue_year[v]) drift_effect[v,s] -= avg;
      }
    }
  }

  for (i in 1:N) {
    real common_hfa = alpha0 + use_trend * alpha_trend * (year[i] - 1);
    real extra_hfa = 0;
    if (use_venue == 1) extra_hfa += venue_base[venue[i]];
    if (use_franchise == 1) extra_hfa += franchise_home[franchise[i]];
    if (use_time == 1) extra_hfa += drift_effect[venue[i],year[i]];
    mu[i] = theta[home_t[i]] - theta[away_t[i]]
            + home_flag[i] * (common_hfa + extra_hfa);
    if (use_covariates == 1) mu[i] += X[i] * beta;
  }
}
model {
  theta_raw ~ std_normal();
  sigma_initial ~ normal(0, 5);
  sigma_transition ~ normal(0, 3);
  rho ~ beta(8, 2);
  alpha0 ~ normal(0, 5);
  alpha_trend ~ normal(0, 0.15);
  eta_raw ~ std_normal();
  tau_venue ~ normal(0, 2.5);
  phi_raw ~ std_normal();
  tau_franchise ~ normal(0, 2.5);
  gamma ~ normal(0, 1.5);
  beta ~ normal(0, 1.5);
  to_vector(delta_raw) ~ std_normal();
  sigma_drift ~ normal(0, 0.75);
  sigma_y ~ normal(0, 15);
  y ~ normal(mu, sigma_y);
}
generated quantities {
  vector[N] log_lik;
  for (i in 1:N) log_lik[i] = normal_lpdf(y[i] | mu[i], sigma_y);
}
