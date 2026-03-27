# Correlated Uncertainty Model for WERTH Valuations

## 1. Motivation and Problem Statement

The original WERTH model uses point-estimate projections (from ATC) to compute z-scores across 12 fantasy categories. The risk-adjusted layer (in `risk_adjusted_werth.py`) added a scalar standard deviation per player derived from Steamer wOBA/ERA quantiles, then applied a truncated normal expectation against a waiver floor.

That approach has three key shortcomings:

**A. Independence assumption across categories.** The old model treats each player's outcome as a single normally-distributed WERTH value. But a "bad season" isn't independently bad in each category — if a hitter's HR disappoints, his TB and RBI almost certainly do too, because they share the same underlying power/contact skill. Conversely, SBN (net steals) is driven by a separate speed skill and may be fine even in a poor power season. By modeling categories independently, the old model underestimates the probability of correlated busts and booms.

**B. Playing time and performance treated as separate.** The old plan proposed separate sigma_PT and sigma_perf combined via `sqrt(sigma_PT^2 + sigma_perf^2)`. This assumes independence between playing time and performance uncertainty, but they're correlated: a player who gets hurt (low PA) also loses counting-stat accumulation (R, HR, TB, RBI all drop together). The cross-category correlations capture this naturally.

**C. Scalar variance ignores distributional shape.** A single sigma + normal assumption can't capture skew. In reality, projections for injury-prone players have heavy left tails (lots of scenarios where they miss significant time) and bounded right tails (they can't play more than 162 games). The Monte Carlo approach captures the full distributional shape.

## 2. Data Foundation: Multi-System Projection Disagreement

Rather than historical actuals (which require pybaseball and are unavailable in the current sandbox), the model exploits the fact that we have **8 independent projection systems** for each player:

| System | Batters | Pitchers | Notes |
|--------|---------|----------|-------|
| ATC | 627 | 844 | Consensus blend, primary projection |
| Steamer | 4,187 | 5,162 | Exhaustive pool, has quantile data |
| THE BAT X | 693 | 708 | Independent methodology |
| ZiPS | 1,903 | 1,838 | Bill James aging curves |
| Depth Charts | 637 | 810 | Playing time consensus |
| OOPSY | 2,803 | 4,248 | FanGraphs optimistic/pessimistic |
| OOPSYPeak | 2,865 | 4,256 | Peak projection variant |
| Steamer600 | 4,187 | 5,162 | Full-season rate stats (600 PA baseline) |

Each system uses different methodologies, weights different historical data, and makes different assumptions about aging, playing time, and performance. Their disagreements are informative about genuine uncertainty.

For each player appearing in ≥3 systems, we compute:

**Consensus projection:** The mean across all available systems for each stat.

**Residual:** `r_cat_i_s = projection_i_s - consensus_i` for player i, system s, category cat.

This gives us 14,449 batter residual observations and 20,390 pitcher observations — a rich dataset for estimating the correlation structure.

## 3. Correlation Structure

### 3.1 Batter Category Correlations

The correlation matrix of cross-system residuals reveals the joint uncertainty structure:

```
        PA     R    HR    TB   RBI   SBN   OBP
PA   1.000 0.982 0.912 0.981 0.977 0.696 0.207
R    0.982 1.000 0.944 0.993 0.990 0.710 0.304
HR   0.912 0.944 1.000 0.960 0.964 0.621 0.359
TB   0.981 0.993 0.960 1.000 0.996 0.694 0.309
RBI  0.977 0.990 0.964 0.996 1.000 0.681 0.309
SBN  0.696 0.710 0.621 0.694 0.681 1.000 0.195
OBP  0.207 0.304 0.359 0.309 0.309 0.195 1.000
```

**Key findings:**

The "power/counting cluster" (PA, R, HR, TB, RBI) is extremely tightly correlated (r = 0.91-0.99). This makes physical sense: these stats share underlying contact quality, power, and playing time. When one system projects a hitter more optimistically, ALL of these stats move together.

SBN is *moderately* correlated with counting stats (r ≈ 0.62-0.71). This reflects the speed/baserunning skill being partially independent of power, but sharing the playing-time component (more PA = more opportunities to steal).

OBP is the most independent category (r = 0.20-0.36 with others). OBP is a rate stat that depends on plate discipline and contact quality, skills that don't necessarily co-vary with power or speed. This is an important finding for draft strategy: a player's OBP uncertainty is substantially independent of their counting-stat uncertainty.

**Practical implication:** A player simulated at the 10th percentile of HR is also near the 10th percentile of TB and RBI (r ≈ 0.96), but could be at the 35th-40th percentile of OBP and the 25th-30th percentile of SBN. A truly catastrophic season (10th percentile in ALL categories simultaneously) is far rarer than the old model assumed.

### 3.2 Pitcher Category Correlations

```
          IP      K     QS    ERA   WHIP    KBB   SVHD
IP     1.000  0.967 -0.098  0.142  0.011  0.058 -0.040
K      0.967  1.000 -0.124  0.091  0.042  0.106 -0.053
QS    -0.098 -0.124  1.000 -0.013  0.022  0.000  0.020
ERA    0.142  0.091 -0.013  1.000  0.480 -0.399  0.024
WHIP   0.011  0.042  0.022  0.480  1.000 -0.284  0.005
KBB    0.058  0.106  0.000 -0.399 -0.284  1.000  0.033
SVHD  -0.040 -0.053  0.020  0.024  0.005  0.033  1.000
```

**Key findings:**

IP and K are extremely tightly correlated (r = 0.97). More innings means proportionally more strikeouts.

ERA and WHIP share a "run prevention" skill axis (r = 0.48). K/BB anti-correlates with ERA (r = -0.40) and WHIP (r = -0.28), reflecting the dominance-vs-control tradeoff.

**QS is surprisingly independent** of almost everything (|r| < 0.13). Quality starts depend on both rate quality AND making it through 6 innings, making QS partly a binary outcome that doesn't correlate well with continuous stats.

**SVHD is essentially independent** of all other categories (|r| < 0.05). This reflects the "role uncertainty" dimension: whether a pitcher will be used as a closer/setup man is largely orthogonal to their skill level.

## 4. Variance Model

### 4.1 Base Variance

For each player and each category, the base variance is the standard deviation of projections across systems. A player where all 8 systems agree (low cross-system std) has low uncertainty; one where systems wildly disagree has high uncertainty.

### 4.2 Variance Inflation

Cross-system disagreement *underestimates* true outcome uncertainty because projection systems are correlated — they share training data, use similar methodologies, and are calibrated to similar samples. We inflate using two system-specific metrics:

**ATC InterSD**: Inter-system standard deviation of WAR (captures total system-level disagreement).
**ATC IntraSD**: Intra-system standard deviation (captures within-model uncertainty from sample size effects).

The inflation factor: `var_inflation = sqrt(InterSD² + IntraSD²) / InterSD`

When these metrics are unavailable, we use a default inflation of 1.5× (estimated from players where both are available).

### 4.3 Age, Position, and Usage Scaling

After inflation, per-category sigmas are further scaled by:

**Age factor:** Variance increases 3% per year after age 28 (batters) or 27 (pitchers), capped at 2.0×. Older players have more injury risk and performance decline uncertainty.

**Position factor:** Catchers get 30% more PA variance, reflecting the position's inherent physical toll and platoon/rest dynamics.

**Playing time factor:** Players with low consensus PA (<400) or IP (<100) get 30% more variance. Low projected PT indicates the systems already see role uncertainty (platoon, injury, rookie promotion timing).

**Category-specific application:**
- PA/IP: Gets all three scalings (age × position × PT)
- Rate stats (OBP, ERA, WHIP, K/BB): Age scaling only (less affected by PT uncertainty)
- Counting stats: sqrt(age × PT) scaling (intermediate — affected by both performance and PT uncertainty)

### 4.4 Variance Floors

Even when all systems agree, irreducible uncertainty exists. Floors are applied:
- OBP: σ ≥ 0.005
- ERA: σ ≥ 0.15
- WHIP: σ ≥ 0.03
- K/BB: σ ≥ 0.1
- Counting stats: σ ≥ max(1.0, 5% of consensus value)

### Observed Sigma Magnitudes

| Player tier | Mean WERTH σ (hitters) | Mean WERTH σ (pitchers) |
|---|---|---|
| Top 50 | 2.20 | 1.52 |
| All draftable | 5.77 | 1.87 |

Top-50 hitters have a 2.20 WERTH sigma, meaning their 80% confidence interval spans about ±2.8 WERTH points. For pitchers, the interval is tighter (±1.9 points), reflecting less projection disagreement in pitching stats.

## 5. Monte Carlo Simulation Engine

### 5.1 Cholesky Decomposition

Given the 7×7 correlation matrix R (for batters: PA + 6 hitting categories, for pitchers: IP + 6 pitching categories), we compute the lower Cholesky factor L such that L·Lᵀ = R.

If R is not positive definite (possible due to noisy estimation), we apply eigenvalue flooring: decompose R = V·diag(λ)·Vᵀ, set λᵢ ← max(λᵢ, 10⁻⁶), reconstitute, and re-normalize to a correlation matrix before Cholesky.

### 5.2 Simulation Process

For each player (N = 2,000 simulations):

1. Draw independent standard normals: Z ~ N(0, I₇) — shape (2000, 7)
2. Correlate: W = Z · Lᵀ — now W has the target correlation structure
3. Scale: For each category k, simulated value = consensus_k + σ_k · W_k
4. Apply physical constraints:
   - PA, IP ≥ 0
   - Counting stats (R, HR, TB, RBI, K, QS, SVHD) ≥ 0
   - SBN ≥ -20, OBP ∈ [0.100, 0.600], ERA ∈ [0.5, 12], WHIP ∈ [0.5, 3.0], K/BB ∈ [0.1, 10]

### 5.3 Stat-to-WERTH Conversion

Each simulated stat line is converted to z-scores using the same parameters as the base valuation engine (precomputed from the ATC starter pool):

**Counting stats:** z = (simulated_value - starter_mean) / starter_std

**Rate stat counting equivalents:** For OBP, the conversion includes the player's simulated PA:
```
OBPc = (sim_OBP × sim_PA - league_OBP × sim_PA) / (avg_starter_PA × total_slots)
z_OBP = (OBPc - mean_OBPc) / std_OBPc
```
This correctly captures the interaction between playing time and rate-stat contribution — a player with 600 PA and .350 OBP contributes more OBP value than one with 400 PA and .350 OBP. Similarly for ERA, WHIP, and K/BB on the pitching side.

WERTH = Σ(z_cat) across all categories.

### 5.4 Re-centering

The simulation uses multi-system consensus as its center, but the base WERTH model uses ATC projections. To preserve the original point estimate while capturing the simulated distribution shape:

```
adj_werth_sims = raw_werth_sims - mean(raw_werth_sims) + original_pos_adj_werth
```

This anchors the distribution to the established WERTH value and uses the simulation only for the spread, shape, and correlations.

## 6. Risk-Adjusted WERTH (Truncated Expectation)

### 6.1 Waiver Floor

For each position group, the waiver floor w = the 4th-best free agent's pos_adj_werth at that position (representing the median realistic waiver pickup). In an 8-team league:

| Position | Waiver Floor |
|----------|-------------|
| C | -5.98 |
| 1B | -4.02 |
| 2B | -2.73 |
| SS | -4.80 |
| 3B | -7.06 |
| OF | -4.14 |
| SP | -1.12 |
| RP | -0.30 |

### 6.2 Truncation

For each simulation s: `truncated_werth_s = max(adj_werth_s, waiver_floor)`

This represents the fact that if a drafted player busts below the waiver floor, the manager drops them and picks up a free agent instead. The left tail is truncated.

**Risk-adjusted WERTH** = mean of truncated simulations across all 2,000 draws.

**Draft value** = risk_adj_werth - waiver_floor (the marginal value over a free replacement).

### 6.3 Why This Matters More Than the Old Model

The correlated model produces a fundamentally different truncated expectation than the old scalar-normal model because:

1. **Correlated busts are rarer but deeper.** When HR crashes, TB and RBI crash with it — but OBP and SBN might survive. The old model assumed all categories could independently hit their worst case, making the probability of a total bust too high.

2. **Partial busts have different option value.** A player who busts in power but maintains speed still has substantial WERTH. The old model couldn't distinguish "uniform decline" from "category-specific decline."

3. **Playing time interacts with counting stats.** The simulation jointly varies PA/IP with counting stats, so a low-PA simulation naturally has low R/HR/TB/RBI. The old model treated PA variance and rate-stat variance as separate.

## 7. Outputs and Interpretation

### 7.1 Key Columns

| Column | Description |
|--------|-------------|
| `werth_std_sim` | Total WERTH standard deviation from MC simulation |
| `werth_q10_sim` | 10th percentile WERTH (downside scenario) |
| `werth_q90_sim` | 90th percentile WERTH (upside scenario) |
| `werth_skew_sim` | Skewness of WERTH distribution (positive = more upside) |
| `risk_adj_werth_mc` | E[max(WERTH, waiver_floor)] — the option-value-adjusted WERTH |
| `draft_value_mc` | risk_adj_werth_mc - waiver_floor |
| `z_{cat}_std` | Per-category z-score volatility |

### 7.2 Biggest Movers (Risk Adjustment vs. Point Estimate)

Among the top 200 hitters, the players with the largest positive adjustment (option value beneficiaries):

| Player | Position | WERTH | Risk-Adj | σ | Δ |
|--------|----------|-------|----------|---|---|
| Giancarlo Stanton | UTIL | -6.46 | -2.17 | 4.66 | +4.29 |
| José Caballero | 2B | -5.47 | -1.67 | 5.37 | +3.80 |
| Tommy Edman | 2B | -5.79 | -2.55 | 2.72 | +3.24 |
| Chandler Simpson | OF | -4.14 | -1.11 | 7.60 | +3.03 |
| Jorge Soler | UTIL | -5.56 | -2.53 | 2.69 | +3.03 |

These are high-variance players near the waiver floor where the truncation effect is strongest. Stanton is the poster child: his WERTH is mediocre (-6.46) but his variance is huge (σ = 4.66), so there's substantial probability of an elite season, while his downside is capped by the waiver floor.

For elite players (top 10), the adjustment is near zero — they're so far above the waiver floor that truncation is irrelevant. Their draft value is driven entirely by the point estimate.

## 8. Caveats and Known Limitations

1. **No historical actuals.** The model uses cross-system disagreement as a proxy for outcome uncertainty rather than fitting to actual projection-vs-outcome residuals. This is a good proxy for *projection uncertainty* but may underestimate true outcome variance (which includes random noise beyond what projections can predict).

2. **System correlation.** Projection systems share data sources and methodologies, so their disagreements underestimate true uncertainty. We partially correct this with the ATC InterSD/IntraSD inflation, but the correction is approximate.

3. **Normal marginals.** The simulation draws from a multivariate normal, which can't capture heavy tails or bimodal outcomes (e.g., a pitcher who might be a closer OR a mop-up man). The physical-constraint clipping provides some tail control, but not full distributional flexibility.

4. **Steamer600 bias.** Including Steamer600 (which projects everyone at 600 PA) inflates PA disagreement for players projected for less playing time. This is partially appropriate (it captures the "what if they got a full-time role" upside) but may overstate variance for confirmed part-timers.

5. **Static correlation structure.** The correlation matrix is estimated from the full player pool and applied uniformly. In reality, the HR-TB correlation may be tighter for power hitters and looser for contact/speed types. Position-specific or archetype-specific correlations could improve accuracy.

6. **No injury-specific modeling.** Injury risk is captured implicitly through cross-system PT disagreement and age scaling, but there's no explicit injury probability model. A player returning from Tommy John surgery has specific PT risk that cross-system disagreement might not fully capture.

## 9. Integration

The model is implemented in `model/correlated_uncertainty.py` and can replace the old `risk_adjusted_werth.py` in the pipeline. It exports:

- `model/output/hitter_uncertainty.csv`
- `model/output/pitcher_uncertainty.csv`
- `model/output/batter_correlation_matrix.csv`
- `model/output/pitcher_correlation_matrix.csv`

The main entry point is `run_correlated_uncertainty(hitters, pitchers, pos_replacement, pit_replacement)` which takes the output of `run_valuation()` and returns enhanced DataFrames with all uncertainty columns.
