# Claude Code Prompt: Distribution-Aware WERTH Model

## Context

This builds on the existing WERTH valuation engine in `model/valuation_engine.py`. Read `STATE_OF_REPO.md`, `research.md`, and `plan.md` for current status.

The existing model uses point-estimate projections. We're adding a distribution-aware layer that accounts for two sources of uncertainty:
1. **Performance variance** — will the player hit .240 or .280? (from Steamer percentiles, if available)
2. **Playing time variance** — will the player get 350 PA or 600 PA? (from a regression model we'll build here)

These combine to produce a **risk-adjusted WERTH** that reflects the option value of the waiver wire: busted players get replaced, so the left tail is truncated.

**Update `plan.md` with these tasks and check them off as you go.**

---

## Part A: Playing Time Variance Regression Model

### A1: Acquire Historical Data

Use the `pybaseball` Python package to pull actual player-season stats for 2018-2025 (8 seasons). This package pulls from FanGraphs and Baseball Reference — no subscription needed.

```bash
pip install pybaseball
```

For each season, pull:
- **Hitters**: name, playerid, age, team, position, G (games), PA, AB, and all standard batting stats
- **Pitchers**: name, playerid, age, team, G, GS, IP, and all standard pitching stats

Use `pybaseball.batting_stats(year)` and `pybaseball.pitching_stats(year)` for each year 2018-2025. Filter to players with PA ≥ 50 (hitters) or IP ≥ 10 (pitchers) to exclude cup-of-coffee appearances.

Also pull IL stint data if accessible via pybaseball or Baseball Reference. If IL data isn't readily available programmatically, skip it — we'll use games played as a proxy.

### A2: Build Prior-Year Features

For each player-season, construct features from their PRIOR year(s):

| Feature | Definition | Rationale |
|---------|-----------|-----------|
| `age` | Player age at season start | Older → more injury risk → more PA variance |
| `age_sq` | age² | Nonlinear aging effects (variance accelerates after ~32) |
| `prior_PA` (or `prior_IP`) | PA/IP in the immediately prior season | Low prior PA suggests injury/role issues likely to recur |
| `prior_games` | Games played in prior season | Direct measure of durability |
| `prior_games_pct` | prior_games / 162 | Normalized availability rate |
| `games_trend` | (prior_year_games - two_years_ago_games) / 162 | Declining trend = increasing fragility |
| `is_catcher` | 1 if primary position is C, else 0 | Catchers have inherently more PA variance |
| `is_rookie` | 1 if ≤ 100 career PA entering the season | Rookies have high role uncertainty |
| `career_PA_per_season` | Total career PA / seasons played | Long track record of durability vs. not |

For players in their first MLB season (no prior year data), use their minor league games or flag as `is_rookie` and let that feature carry the signal.

Handle the join carefully — you need to match player IDs across seasons. pybaseball uses FanGraphs playerid which is consistent across years.

### A3: Define the Target Variable

For each player-season:
```
projected_PA = f(prior-year features)  # simple projection, see below
actual_PA = actual PA in that season
residual = actual_PA - projected_PA
abs_residual = |residual|
```

For the "simple projection," don't overthink it. Use:
```
projected_PA = 0.6 × prior_year_PA + 0.3 × two_years_ago_PA + 0.1 × 500
```
(Weighted average of recent PA with regression toward ~500 PA. For players missing a prior year, use 500 × prior_games/162 or similar.)

The point is NOT to build the world's best PA projection — it's to get a reasonable baseline so the residuals capture genuine playing time surprise. The variance structure of the residuals (which is what we're modeling) is robust to moderate errors in the baseline projection.

### A4: Fit the Variance Regression

We're modeling `E[|residual|]` as a function of player features. Use a simple linear regression or a random forest (whichever CC judges appropriate given the sample size and feature count).

```python
from sklearn.linear_model import LinearRegression
# or
from sklearn.ensemble import RandomForestRegressor

# X = feature matrix (age, age_sq, prior_PA, prior_games_pct, games_trend, 
#                     is_catcher, is_rookie, career_PA_per_season)
# y = abs_residual for each player-season

model = LinearRegression()
model.fit(X_train, y_train)
```

**Validation:** Hold out 2024-2025 as a test set. Check that the model makes directional sense:
- Age coefficient should be positive (older → more variance)
- prior_games_pct coefficient should be negative (durable → less variance)
- is_catcher should be positive
- is_rookie should be positive

**Sanity checks on 2026 predictions:**
- Mike Trout (age 34, extensive IL history, declining games): σ_PA should be HIGH
- Bobby Witt Jr. (age 25, 160+ games last 3 years): σ_PA should be LOW
- Agustín Ramírez (rookie catcher): σ_PA should be HIGH
- Shohei Ohtani (unique case — DH only in 2026, historically durable when not pitching): should be MODERATE

If these don't order correctly, investigate and fix.

### A5: Convert E[|residual|] to σ_PA

For a normal distribution, E[|X|] = σ × √(2/π), so:
```
σ_PA = predicted_abs_residual × √(π/2) ≈ predicted_abs_residual × 1.253
```

### A6: Propagate σ_PA Through WERTH (Numerical Perturbation)

For each 2026 player:
```python
# Compute WERTH at PA + σ_PA and PA - σ_PA, holding rate stats fixed
werth_high = compute_werth(player, PA=projected_PA + sigma_PA)
werth_low  = compute_werth(player, PA=projected_PA - sigma_PA)
sigma_PT_WERTH = (werth_high - werth_low) / 2
```

This automatically captures how PA uncertainty flows through both counting stats AND rate-stat counting equivalents (OBPc, ERAc, etc.) because it uses the actual WERTH formula for both evaluations.

Do the same for pitchers with IP instead of PA.

### A7: Save the Model and Predictions

Save:
- `model/playing_time_model.pkl` — the fitted regression model
- `model/output/playing_time_sigmas.csv` — for each 2026 player: name, espn_id, projected_PA, sigma_PA, sigma_PT_WERTH
- `model/playing_time_model.py` — the code that trains the model and generates predictions
- `analysis/playing_time_model_report.md` — brief report on model fit, coefficients, validation results, and sanity checks

---

## Part B: Performance Variance (Steamer Percentiles)

**If Steamer percentile CSVs are available** in `existing-tools/` (files with q10/q90 columns — these require a FanGraphs membership):

### B1: Compute WERTH at q10 and q90

For each player, compute WERTH using the q10 stat projections and separately using the q90 stat projections, holding PA/IP at the median projection:

```python
werth_q10 = compute_werth(player, stats=q10_stats, PA=median_PA)
werth_q90 = compute_werth(player, stats=q90_stats, PA=median_PA)
sigma_perf = (werth_q90 - werth_q10) / 2.56
```

(2.56 = distance between 10th and 90th percentile in standard deviations for a normal: z₉₀ - z₁₀ = 1.28 - (-1.28))

### B2: Save
- `model/output/performance_sigmas.csv` — for each player: name, espn_id, werth_q10, werth_q90, sigma_perf

**If Steamer percentile CSVs are NOT available** (no FanGraphs membership):

### B_fallback: Estimate performance σ from multi-system spread

Compute WERTH for each player using each available projection system (ATC, Steamer median, ESPN). Then:

```python
sigma_perf = stdev(werth_ATC, werth_Steamer, werth_ESPN)
```

This is a rougher estimate (only 3 data points, correlated systems). For players appearing in only 1-2 systems, assign a default σ_perf based on position tier (use the median σ_perf from players who appear in all 3 systems, bucketed by WERTH tier: top-25 / 25-75 / 75-150 / 150+).

Also consider using the ATC `InterSD` column if available — it measures inter-system disagreement and can supplement or replace the 3-system stdev.

Note in the output which method was used so we have a clear audit trail.

---

## Part C: Combine and Compute Risk-Adjusted WERTH

### C1: Total σ

Performance and playing time variance are approximately independent (different causal mechanisms), so variances add:

```python
sigma_total = sqrt(sigma_perf**2 + sigma_PT_WERTH**2)
```

### C2: Position-Specific Waiver Floor

For each position group (C, 1B, 2B, 3B, SS, OF, SP, RP), compute the waiver floor as the WERTH of the **4th-best** projected free agent at that position. Use the free agent data in `data/free_agents_2026.json` combined with WERTH calculations, or use the lower end of the starter pool from the valuation engine.

The 4th-best (not the best): this represents the median realistic outcome of a waiver pickup — not the luckiest possible add, but what I'd reasonably expect to end up with after dropping a bust. Store these as a lookup table.

### C3: Truncated Expectation

For each player with μ = point-estimate WERTH, σ = σ_total, w = position-specific waiver floor:

```python
from scipy.stats import norm

def truncated_expectation(mu, sigma, w):
    """E[max(X, w)] where X ~ N(mu, sigma)"""
    if sigma <= 0:
        return max(mu, w)
    z = (mu - w) / sigma
    return mu * norm.cdf(z) + sigma * norm.pdf(z) + w * norm.cdf(-z)

risk_adj_werth = truncated_expectation(mu, sigma_total, waiver_floor)
draft_value = risk_adj_werth - waiver_floor
```

### C4: Export and Integrate

Add to the rankings output (`model/output/rankings.csv`):
- `sigma_perf` — performance uncertainty
- `sigma_pt` — playing time uncertainty (in WERTH space)
- `sigma_total` — combined
- `risk_adj_werth` — the truncated expectation
- `draft_value` — risk_adj_werth minus waiver floor

Update `model/export_rankings.py` and `model/build_draft_tool.py` to include these new columns in the draft tool.

In the draft tool HTML:
- Add `draft_value` as a sortable column
- Let the user toggle between sorting by `pos_adj_werth` (the standard ranking) and `draft_value` (the risk-adjusted ranking)
- Color-code: green for players where draft_value >> waiver floor (strong draft picks), yellow for marginal, red for players where draft_value ≈ 0 (waiver-wire replacement would be nearly as good — don't waste a pick)
- Add a `σ` column showing sigma_total so I can see who's high-variance at a glance

---

## Part D: Validation and Reporting

### D1: Rankings Comparison

Generate a comparison showing the 20 biggest movers between standard WERTH ranking and risk-adjusted draft_value ranking. These are the players where the distribution model most disagrees with the point-estimate model. For each mover, explain *why* they moved (high σ_perf, high σ_PT, near the waiver floor, etc.).

### D2: Strategy Implications

Write `analysis/distribution_model_report.md` with:
1. Summary of the methodology
2. Playing time model coefficients and interpretation
3. Waiver floor values by position
4. The 20 biggest ranking movers (up and down) with explanations
5. Round-by-round strategy guidance: in early rounds, draft_value ≈ pos_adj_werth (elite players are safe). In late rounds, draft_value diverges — which players are "reach for upside" targets and which are "don't waste a pick"?
6. Any caveats or known weaknesses of the model

### D3: Rebuild the Draft Tool

After all new data is computed:
```bash
python3 model/export_rankings.py
python3 model/build_draft_tool.py
```

Verify the draft tool loads, the new columns appear, sorting by draft_value works, and color-coding is visible.

---

## Priority and Fallbacks

**If time is tight, build in this order:**
1. Part A (playing time regression) — this is the novel contribution and doesn't depend on any subscription
2. Part C (truncated expectation with waiver floor) — this is the payoff
3. Part B (performance σ) — use the multi-system fallback if Steamer percentiles aren't available yet
4. Part D (validation and reporting)

**If pybaseball has issues** (rate limiting, data format changes, etc.): CC can fall back to manually downloading FanGraphs batting/pitching leaderboard CSVs for 2018-2025 from the free FanGraphs website (you don't need a membership for historical actual stats, only for projections/percentiles). The CSV export button on leaderboard pages is free.

**If the regression model is weak** (low R², coefficients don't make sense): fall back to the binning approach — bucket players by (age_bucket × prior_games_bucket) and use the empirical mean |residual| for each bucket. This is cruder but will still correctly assign high σ_PA to old/fragile players and low σ_PA to young/durable ones.
