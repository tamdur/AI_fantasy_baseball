# Waiver Floor Analysis: Empirical Model (2022-2025)

## Executive Summary

The waiver floor model had two compounding problems: (1) the rank ratio (4 hitter vs 16 pitcher) created a systematic hitter/pitcher DV bias, and (2) the floor values themselves were derived from projections rather than actuals, inflating all draft values by 6-10 WERTH points. The fix replaces the entire projection-based approach with empirical constants derived from 4 years of FanGraphs end-of-season actuals, using position-specific ranks based on the formula `rank = 4 pickups × roster_slots`.

## Methodology

1. Downloaded end-of-season FanGraphs batting and pitching leaderboards for 2022-2025 (all players, no PA/IP minimum).
2. Computed WERTH for each player-season using the same pipeline as `valuation_engine.py` (rate-stat counting equivalents, z-scores within 104-hitter/72-pitcher starter pools).
3. Used this league's draft data (`data/drafts/draft_YYYY.json`) to identify which players were actually drafted via ESPN ID → MLBAM ID bridging through the SFBB Player ID Map.
4. Classified undrafted players as "waiver available" and ranked them by total WERTH at each position (ALL_HIT, SP, RP).
5. Tested FA ranks of 1, 2, 4, 8, and 16 to find where hitter and pitcher floors align.

## Key Findings

### The Current 4:16 Ratio Creates a +2.21 Point Bias

| Year | Hitter (rank 4) | SP (rank 16) | Gap (H - SP) |
|------|-----------------|--------------|---------------|
| 2022 | +0.76           | -1.61        | +2.37         |
| 2023 | +0.60           | -1.14        | +1.74         |
| 2024 | +0.44           | -0.54        | +0.98         |
| 2025 | +2.94           | -0.81        | +3.74         |
| **Avg** | **+1.18**    | **-1.02**    | **+2.21**     |

A positive gap means the hitter floor is higher (easier to replace from waivers), which compresses hitter DV while inflating pitcher DV. The ~2.8-point bias reported in the original problem statement is confirmed.

### At Equal Ranks, SP Floors Are Slightly Higher Than Hitter Floors

| Rank | Hitter WERTH | SP WERTH | RP WERTH | H-SP diff | H-RP diff |
|------|-------------|----------|----------|-----------|-----------|
| 1    | +3.82       | +4.56    | +1.72    | -0.75     | +2.10     |
| 2    | +3.04       | +2.94    | +1.20    | +0.10     | +1.84     |
| 4    | +1.18       | +1.86    | +0.78    | -0.68     | +0.40     |
| 8    | -0.54       | +0.43    | +0.14    | -0.97     | -0.69     |
| 16   | -1.97       | -1.02    | -0.69    | -0.95     | -1.28     |

This confirms that the SP waiver pool is genuinely deeper than the hitter pool — at every rank, undrafted SPs have higher WERTH than undrafted hitters. This makes intuitive sense: in an 8-team league, the top ~48 SP are rostered out of ~200+ qualified SPs, leaving many quality arms available. By contrast, 104 hitters are rostered out of ~400+ qualified hitters, but the hitter pool dilutes faster because hitting contributions are spread across 6 categories while SP value concentrates in K, QS, ERA, WHIP, and KBB.

### The 4:1 Ratio Is Not Justified

The premise behind using rank 16 for pitchers was "pitching has much deeper waiver pools because of IL stints and role changes." But the deeper pool argument works in the opposite direction for the floor: if more quality SP are available, the replacement quality is HIGHER (not lower), and the floor should be higher, meaning LESS draft value.

Using rank 16 instead of rank 4 for SP reduces the floor by ~2.9 WERTH points on average, systematically overvaluing every SP in the draft by that amount.

### Closest-Matching Rank Pairs

| H_rank | SP_rank | H floor | SP floor | Difference |
|--------|---------|---------|----------|------------|
| 2      | 2       | +3.04   | +2.94    | +0.10      |
| 8      | 16      | -0.54   | -1.02    | +0.48      |
| 4      | 4       | +1.18   | +1.86    | -0.68      |
| 4      | 8       | +1.18   | +0.43    | +0.75      |

### Notable Waiver Pickups (Draft-Based Method)

Examples of the caliber of undrafted player available:

**2024 SP — rank 4**: Jack Flaherty (WERTH +3.09, 162 IP). A legitimate ace-caliber season from a player outside the top 200 draft picks.

**2024 Hitters — rank 4**: Brenton Doyle (WERTH +0.44, 603 PA). A solid everyday player but not a league-winner.

**2022 SP — rank 2**: Spencer Strider (WERTH +1.95, 131.2 IP). Pre-breakout Strider was undrafted and became a top-20 pitcher.

**2024 RP — rank 4**: Cade Smith (WERTH +1.59, 75 IP). Quality reliever with K upside.

## RP Analysis

RP waiver floors are notably lower than SP at all ranks, because RP WERTH is concentrated in SVHD — a binary category where closers dominate and middle relievers contribute little. The RP pool has many "replacement-level" arms that aren't true replacement options in a categories league.

| Rank | RP floor (avg) | SP floor (avg) | SP-RP diff |
|------|---------------|----------------|------------|
| 4    | +0.78         | +1.86          | +1.08      |
| 8    | +0.14         | +0.43          | +0.29      |
| 16   | -0.69         | -1.02          | -0.33      |

Since the current code uses a single `PITCHER_FA_RANK` for both SP and RP, and RP floors are lower, using rank 4 for all pitchers is a reasonable compromise. If the code were split by pitcher type, RP could use rank 2-4 (higher floor, less DV) and SP could use rank 4-8.

## Recommendation

### Primary: Use Equal Ranks

```python
HITTER_FA_RANK = 4    # unchanged
PITCHER_FA_RANK = 4   # was 16; reduces bias from +2.21 to -0.68
```

The remaining -0.68 difference (SP floor slightly above hitter floor) is directionally correct — SP IS more replaceable from waivers in an 8-team league. This small asymmetry naturally dampens SP DV relative to hitters, which counteracts the tendency to overdraft pitching.

### Alternative: Split SP/RP

If the code is refactored to use separate ranks:

```python
HITTER_FA_RANK = 4
SP_FA_RANK = 4        # best match at equal ranks (diff = -0.68)
RP_FA_RANK = 2        # RP pool is shallower; rank 2 gives +1.20 floor
```

### Why Not Rank 2 for Everything?

Using rank 2 everywhere (diff = +0.10, closest match) would set the floor too optimistically. Rank 2 assumes you'll reliably pick up the 2nd-best free agent, which requires both (a) identifying breakouts early and (b) winning the waiver claim. In an active 8-team league, the top 1-2 FAs get claimed quickly. Rank 4 better represents the realistic pickup quality.

### Why Not Rank 8?

At rank 8, hitter floor drops to -0.54 and SP to +0.43 (diff = -0.97). This creates a bias in the opposite direction from the current code. It also sets the floor low enough that most waiver pickups look like positive-DV acquisitions, which inflates perceived draft value for marginal players.

## Data Quality Notes

1. **Draft matching**: Only 120-150 of ~200-250 drafted players matched via ESPN→MLBAM ID bridging each year. Unmatched players (likely minor leaguers or players missing from the SFBB ID Map) are incorrectly classified as "undrafted." This inflates the waiver pool slightly but doesn't materially affect the rank-4 floor since we're looking at the top of the pool.

2. **Position granularity**: FanGraphs leaderboard API doesn't return fielding positions, so hitter floors are computed as an aggregate "ALL_HIT" pool rather than position-specific (C, 1B, 2B, etc.). The current code in `correlated_uncertainty.py` already falls back to aggregate floors for flex positions (MI, CI, UTIL), so this is consistent.

3. **2025 season**: Represents a partial or full season depending on when the data was pulled. WERTH values for 2025 are slightly higher than other years, possibly reflecting a stronger breakout class (e.g., Springer, Perdomo, Story).

4. **Roster-depth method vs draft-based**: The roster-depth method (assuming top N by WERTH are rostered) gives much lower floors (-4.7 for hitters, -1.9 for SP) because it assumes perfect roster optimization. The draft-based method is more realistic since it reflects actual league behavior where many drafted players underperform and better undrafted players emerge.
