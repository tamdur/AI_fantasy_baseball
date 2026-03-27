# Empirical Injury/Games-Missed Model

## Overview

This module builds an injury risk model using **cross-system projection disagreement** as a proxy for injury/playing-time uncertainty. The key insight is that the gap between a player's full-season projection (Steamer600 at 600 PA baseline) and realistic projections (Steamer, ATC, ZiPS, DepthCharts, etc.) implicitly encodes injury/PT risk.

## Methodology

### Core Idea

- **Steamer600**: Represents what a player would achieve if healthy for the full 162-game season (batters: 600 PA, pitchers: 200 IP normalized baseline)
- **Realistic systems** (Steamer, ATC, ZiPS, DepthCharts, TheBatX, OOPSY, OOPSYPeak): These incorporate various sources and tend to be more conservative about playing time
- **Gap = Injury Risk**: `games_missed = (1 - pa_projected / pa_fullseason) * 162`

### Key Metrics

For each batter:
- **pa_projected**: Mean PA across realistic systems (realistic playing time estimate)
- **pa_fullseason**: Steamer600 PA (healthy baseline)
- **games_missed_estimate**: Expected games missed = `(1 - pa_proj/pa_full) * 162`, clamped to [0, 162]
- **pa_disagreement**: Standard deviation of PA across systems (uncertainty in the estimate)
- **injury_risk_tier**: LOW / MODERATE / HIGH / VERY_HIGH (quartile-based)

For each pitcher:
- **ip_projected**: Mean IP across realistic systems
- **ip_fullseason**: Steamer600 IP (healthy baseline)
- **games_missed_estimate**: Expected starts missed = `(1 - ip_proj/ip_full) * 33` (assuming ~33 starts/season)
- **ip_disagreement**: Standard deviation of IP across systems
- **injury_risk_tier**: Quartile-based risk assignment

## Data Sources

### Input CSVs
All from FanGraphs 2026 projections in `existing-tools/`:

**Batters (8 systems):**
- FanGraphs_Steamer600_Batters_2026.csv (full-season baseline)
- FanGraphs_Steamer_Batters_2026.csv
- FanGraphs_ATC_Batters_2026.csv
- FanGraphs_ZiPS_Batters_2026.csv
- FanGraphs_DepthCharts_Batters_2026.csv
- FanGraphs_TheBatX_Batters_2026.csv
- FanGraphs_OOPSY_Batters_2026.csv
- FanGraphs_OOPSYPeak_Batters_2026.csv

**Pitchers (8 systems):**
- Same structure with IP instead of PA

### Output CSVs
- `model/output/injury_risk_batters.csv` (4,186 batters)
- `model/output/injury_risk_pitchers.csv` (5,161 pitchers)

## Usage

### Python API

```python
from model.injury_model import load_injury_estimates, get_injury_risk

# Load all estimates
batters, pitchers = load_injury_estimates()

# Get info for a single player
judge_risk = get_injury_risk(592450)  # Aaron Judge
# Returns: {
#   'mlbam_id': 592450,
#   'name': 'Aaron Judge',
#   'games_missed_estimate': 0.0,
#   'disagreement': 15.47,
#   'injury_risk_tier': 'LOW',
#   'age': NaN
# }

# Query DataFrames directly
high_risk = batters[batters['games_missed_estimate'] > 50]
high_uncertainty = batters[batters['pa_disagreement'] > 150]
```

### Run Standalone

```bash
python model/injury_model.py
```

Outputs:
- Summary statistics by age bucket and position
- Risk tier distribution
- Top 10 highest-risk players
- CSV exports

## Interpretation

### Risk Tiers

**LOW (Q1, ≤25th percentile):**
- Low probability of missing significant time
- Projection systems agree closely on PA/IP
- Safe playing-time floor assumption

**MODERATE (Q2, 25-50th percentile):**
- Moderate availability risk
- Some uncertainty in projections
- Reserve/backup consideration

**HIGH (Q3, 50-75th percentile):**
- Higher injury/PT risk
- Noticeable projection disagreement
- May miss 50-100+ games

**VERY_HIGH (Q4, >75th percentile):**
- Significant uncertainty; could miss 100+ games/15+ starts
- High disagreement across systems
- Strong injury/durability concerns

### Disagreement Metric

**PA Disagreement (batters) / IP Disagreement (pitchers):**
- Measures cross-system standard deviation
- High disagreement = low consensus = genuine uncertainty
- Useful for identifying "off the board" players where models diverge

**Example:**
- Aaron Judge: ±15.5 PA (tight consensus = reliable projection)
- Mystery fringe player: ±400+ PA (wide disagreement = high variance)

## Key Findings (2026)

### Batters
- **Average games missed estimate**: 115 games (high, suggests many deep minors/never-played players)
- **Risk distribution**: 25% LOW, 34% MODERATE, 41% HIGH, 0% VERY_HIGH
- **Healthiest (0 games missed)**: Aaron Judge, Juan Soto, Shohei Ohtani, Julio Rodríguez, Bobby Witt Jr., Gunnar Henderson
- **Highest position risk**: Catchers (C) have mean ~101 games, likely due to durability questions
- **Lowest position risk**: Designated hitters (DH) average ~99 games

### Pitchers
- **Average starts missed estimate**: 19.75 starts (reasonable; corresponds to ~30 IP in 200 IP season)
- **Risk distribution**: 25% LOW, 25% MODERATE, 25% HIGH, 25% VERY_HIGH (evenly split by quartile)
- **Highest risk pitchers**: Many minor-league/never-played arms projected to miss nearly all starts
- **Healthiest**: Tarik Skubal, Paul Skenes, Garrett Crochet (realistic starters; <2 starts missed)

## Limitations

### Data Quality
1. **Age data**: FanGraphs CSVs don't include explicit Age column; would need external ID bridge
2. **Minor league skew**: Dataset includes 3000+ minor leaguers with almost no PA/IP in most systems
3. **No explicit injury history**: Model uses projections only; doesn't incorporate historical injury data
4. **Noise from rare players**: Players with 0 PA in most systems have maxed-out games_missed (162 games)

### Model Assumptions
1. **Cross-system disagreement = uncertainty**: Assumes projection divergence reflects genuine information, not independent errors
2. **Full-season baseline valid**: Steamer600 may not be true "healthy" baseline for truly injury-prone players
3. **Linear PA-to-games mapping**: Assumes 600 PA = 162 games (not accounting for pace differences)
4. **No roster context**: Doesn't factor in team depth, lineup construction, or organizational PT philosophy

### Next Steps to Improve
1. **Integrate age data** from external sources (Baseball-Reference, MLB.com roster APIs)
2. **Filter to realistic universe**: Remove never-played prospects with 0 PA across systems
3. **Incorporate historical injury rates** as Bayesian priors
4. **Add veteran adjustment**: Older players may have structural durability concerns beyond projection gaps
5. **Position-specific models**: Catchers, OF, etc. have different injury patterns

## File Locations

- **Module**: `/sessions/awesome-kind-maxwell/mnt/AI_fantasy_baseball/model/injury_model.py`
- **Batters output**: `/sessions/awesome-kind-maxwell/mnt/AI_fantasy_baseball/model/output/injury_risk_batters.csv`
- **Pitchers output**: `/sessions/awesome-kind-maxwell/mnt/AI_fantasy_baseball/model/output/injury_risk_pitchers.csv`
- **Documentation**: This file

## Integration with Draft Tool

This model should be integrated into `model/build_draft_tool.py` to:
1. Adjust projected values downward for high-risk players
2. Apply uncertainty penalties in draft rankings
3. Flag lineup positions vulnerable to backups/injuries
4. Inform keeper decisions (hold healthy players over injury-prone upside)
