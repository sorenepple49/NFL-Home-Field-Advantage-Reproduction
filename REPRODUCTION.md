\# NFL Home-Field Advantage — Reproduction



\## Parent Paper



\*\*Title:\*\* A Comprehensive Survey of the Home Advantage in American Football  

\*\*Authors:\*\* Luke Benz, Thompson Bliss, and Michael Lopez  

\*\*Original Repository:\*\* https://github.com/ThompsonJamesBliss/comprehensive\_survey\_american\_football\_home\_adv



\## Objective



This project reproduces the NFL portion of the parent paper's Bayesian home-field advantage analysis. The goal is to verify the implementation and establish a reproducible baseline for future research on NFL stadium-specific effects.



\## Dataset



\- League: NFL

\- Seasons: 2004–2023

\- Games analyzed: 5,395

\- Source: `data/final/NFL\_games.csv`



\## Implementation



We reproduced two Bayesian models using R and RStan.



\*\*Model 1 — Constant Home-Field Advantage\*\*



\- Script: `code/model/run\_NFL\_model.R`

\- Original Stan model: `code/model/stan/model\_1.stan`

\- Estimates overall NFL home-field advantage while accounting for team strength.



\*\*Model 2 — Linear Home-Field Advantage Trend\*\*



\- Script: `code/model/run\_NFL\_model2.R`

\- Original Stan model: `code/model/stan/model\_2.stan`

\- Estimates how NFL home-field advantage changes across seasons.



The original Stan model files were preserved. Separate R scripts were created to isolate NFL data and make subsequent modifications easier.



\## Reproduced Results



| Parameter | Reproduced Estimate | 95% Credible Interval |

|---|---:|---|

| Model 1: Home Advantage | 2.20 | \[1.85, 2.55] |

| Model 2: Intercept | 2.72 | \[2.01, 3.44] |

| Model 2: Annual Trend | -0.05 | \[-0.11, 0.01] |



\### Comparison with Original Results



The original Model 2 NFL trend estimate was -0.0492, with a 95% credible interval of \[-0.111, 0.00917].



Our reproduced estimate of approximately -0.05, with a credible interval of \[-0.11, 0.01], closely matches the original results.



Both intervals include zero, indicating uncertainty about whether the underlying linear trend differs from zero.



\## Model Diagnostics



Both models were fitted using four sampling chains, 2,000 iterations per chain, and 500 warmup iterations.



Model 2 was additionally tested with increased `adapt\_delta` settings. At `adapt\_delta = 0.999`, seven divergent transitions remained across 6,000 post-warmup draws. This limitation should be considered when interpreting the posterior estimates.



\## Reproduction Instructions



Install R, RStudio, Rtools (on Windows), and the required R packages, including `tidyverse` and `rstan`.



From the repository root, execute:



```r

source("code/model/run\_NFL\_model.R")

source("code/model/run\_NFL\_model2.R")

```



The scripts generate Bayesian estimates and save the fitted results and summaries.



Reproduced figures, numerical summaries, diagnostics, and the original-versus-reproduced comparison can be found in:



`results/reproduction/`



\## Future Research



The reproduced models provide a baseline for exploring how NFL home-field advantage varies by stadium and whether factors such as attendance, travel, weather, or venue characteristics help explain these differences.



\## Attribution



The original research methodology, Stan model definitions, and underlying dataset belong to Benz, Bliss, and Lopez. This reproduction preserves the original model files while introducing NFL-specific execution scripts and comparison outputs.

