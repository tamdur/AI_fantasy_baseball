# Cowork Task: Build an Empirical Waiver Floor Model

## Goal

Build a data-driven waiver floor model for the AI Fantasy Baseball Draft Tool. The waiver floor represents the WERTH (z-score valuation) of the best player realistically available on waivers at each position during the season. It's used in the formula `draft_value = risk_adj_werth - waiver_floor` — a higher (less negative) floor means a position is easily replaced from waivers, compressing draft value.

**Current approach (to be replaced):** The code picks the 4th-best (hitters) or 16th-best (pitchers) undrafted player from this year's ATC projections. These ranks (4 and 16) are arbitrary heuristics, not empirically derived. This creates a systematic bias where pitcher DV is compressed ~2.8 points relative to hitter DV, because the 16th-best FA pitcher is much better than the 4th-best FA hitter.

**What we need:** Use historical end-of-season data (ideally 2022-2025) to estimate what caliber of player was actually available on waivers at each position, measured in our WERTH framework.

---

## Approach

### Step 1: Get Historical End-of-Season Stats

We need actual season stats (not projections) for MLB players over 2022-2025. FanGraphs has this data.

**FanGraphs Leaderboard API** (undocumented but functional):
```
https://www.fangraphs.com/api/leaders/major-league/data?pos=all&stats=bat&lg=all&qual=0&season=2024&month=0&ind=0
https://www.fangraphs.com/api/leaders/major-league/data?pos=all&stats=pit&lg=all&qual=0&season=2024&month=0&ind=0
```

- `season=YYYY` for the year
- `stats=bat` or `stats=pit`
- `qual=0` means no minimum qualifier (we want ALL players, not just qualifiers)
- The response is JSON with player stats including: Name, Team, PA/IP, R, HR, 2B, 3B, SB, CS, BB, HBP, OBP, ERA, WHIP, K, QS, SV, HLD, etc.
- You have access to a FanGraphs subscription via the browser if needed

**Alternative**: FanGraphs CSV exports from the leaderboard page at `https://www.fangraphs.com/leaders/major-league` — select the year, "All" for qualifying, and export.

For each season (2022-2025), download batting and pitching leaderboards with ALL players (no minimum PA/IP qualifier).

### Step 2: Compute WERTH for Historical Players

Apply the same valuation methodology used in the draft tool to historical stats. The key files to reference:

- **`model/valuation_engine.py`** — The full WERTH pipeline:
  - Derived stats: `TB = 1B + 2×2B + 3×3B + 4×HR`, `SBN = SB - CS`, `SVHD = SV + HLD`
  - Rate stat counting-equivalent conversion (OBPc, ERAc, WHIPc, KBBc) — see `convert_rate_stats()` at line 172
  - Z-score computation with negated stdev for ERA/WHIP — see `compute_zscores()` at line 235
  - Replacement level and position adjustment — see `compute_replacement_levels()` at line 304
  - League context: 8 teams, 13 hitting slots/team (C/1B/2B/3B/SS/5×OF/MI/CI/UTIL), 9 P slots (6 SP + 3 RP)
  - Starter pool: top 104 hitters, top 72 pitchers (48 SP + 24 RP)
  - **Hitting cats**: R, HR, TB, RBI, SBN, OBP
  - **Pitching cats**: K, QS, ERA, WHIP, K/BB (K÷BB), SVHD

For historical seasons, you'll need to:
1. Compute the 12 league category stats from raw FanGraphs data
2. Identify the starter pool (top N by projected value, or by actual PA/IP)
3. Compute z-scores within that pool
4. Apply replacement levels and position adjustments
5. Result: historical pos_adj_werth for every player-season

### Step 3: Identify Who Was "On Waivers"

For each historical season, determine which players were realistically available as free agents in an 8-team league. Approaches:

**Option A (Preferred — ADP-based):** Players outside the top ~200 ADP (or ~25 picks × 8 teams) were likely undrafted. FanGraphs or NFBC ADP archives can provide this. A player outside preseason ADP 200 who produced a strong season represents the kind of waiver pickup that sets the floor.

**Option B (Roster-depth cutoff):** Assume the top `roster_slots × 8` players at each position (by end-of-season WERTH) were rostered. Everyone below that cutoff was a potential waiver pickup at some point during the season.

**Option C (Hybrid):** Use ADP to determine who was initially undrafted, then look at their end-of-season WERTH. The Nth-best such player at each position is the empirical waiver floor.

### Step 4: Compute Waiver Floor by Position

For each position group (C, 1B, 2B, 3B, SS, OF, SP, RP) and each season:
- Rank the "waiver available" players by end-of-season WERTH (descending)
- The waiver floor = the Nth-best player's WERTH, where N represents the realistic pickup depth

Try multiple values of N (e.g., 1st, 2nd, 4th, 8th, 16th) to see how the floor changes. The right N depends on league competitiveness — in an active 8-team league, the top few FAs get claimed quickly, so the 4th-8th best is more realistic than the 1st.

### Step 5: Recommend Position-Specific FA Ranks

The key output: for each position, what rank N should we use in the waiver floor formula? Currently the code uses N=4 for hitters and N=16 for pitchers. Your analysis should determine:

1. Is the 4:1 ratio justified by the data?
2. What N values produce waiver floors that match observed waiver wire quality?
3. Should the ratio differ (e.g., 4:8 instead of 4:16)?

---

## Project Context

### Repository Structure
```
AI_fantasy_baseball/
├── model/
│   ├── valuation_engine.py      # WERTH computation (z-scores, replacement levels)
│   ├── correlated_uncertainty.py # MC simulation, waiver floor usage (line 774-827)
│   ├── export_rankings.py       # Pipeline that runs everything
│   ├── data_pipeline.py         # Data loading, constants (NUM_TEAMS=8, ROSTER_SLOTS)
│   └── output/                  # rankings.csv, draft_data.json
├── existing-tools/              # FanGraphs projection CSVs, SFBB ID Map
├── data/
│   ├── league_config.json       # Roster slots, team info
│   ├── standings_20XX.json      # Historical standings (2021-2025)
│   └── drafts_20XX.json         # Historical draft results (2021-2025)
├── research.md                  # WERTH methodology deep dive
├── fangraphs_guide.md           # FanGraphs API documentation
└── CLAUDE.md                    # Project instructions
```

### Key Constants
- **8 teams**, H2H Most Categories
- **Hitting roster per team**: C(1), 1B(1), 2B(1), 3B(1), SS(1), OF(5), MI(1), CI(1), UTIL(1) = 13
- **Pitching roster per team**: P(9), split as 6 SP + 3 RP in the model
- **Bench**: 3 slots, IL: 3 slots
- **Hitting categories**: R / HR / TB / RBI / SBN / OBP
- **Pitching categories**: K / QS / ERA / WHIP / K÷BB / SVHD
- **ESPN League ID**: 84209353

### Historical Draft Data Available
The `data/drafts_20XX.json` files contain past draft results for this league. These can help identify which players were actually drafted (and thus NOT available on waivers) in each season.

### FanGraphs Access
You have access to a FanGraphs subscription. The leaderboard pages and API endpoints should work. Key patterns:
- Leaderboard page: `https://www.fangraphs.com/leaders/major-league?pos=all&stats=bat&lg=all&qual=0&season=2024`
- API: `https://www.fangraphs.com/api/leaders/major-league/data?pos=all&stats=bat&lg=all&qual=0&season=2024&month=0&ind=0`

### What Stats You Need from FanGraphs
**Batters**: Name, Team, PA, R, HR, 1B (or H and 2B/3B/HR to derive), 2B, 3B, SB, CS, BB, HBP, AB, H, OBP
**Pitchers**: Name, Team, IP, K (or SO), QS, ERA, WHIP, BB (for K/BB), SV, HLD

---

## Deliverables

1. **`model/waiver_floor_analysis.py`** — Script that:
   - Loads historical stats (2022-2025)
   - Computes WERTH for each player-season using the same methodology as `valuation_engine.py`
   - Identifies waiver-available players (via ADP cutoff or roster-depth cutoff)
   - Computes empirical waiver floors at various FA ranks (1st, 2nd, 4th, 8th, 16th)
   - Outputs a summary table by position and season

2. **`analysis/waiver_floor_report.md`** — Report with:
   - Empirical waiver floor by position across 2022-2025
   - Recommended FA rank (N) for hitters and pitchers
   - Whether the current 4:1 hitter:pitcher ratio is justified
   - Key examples (e.g., "in 2024, the 4th-best undrafted SP had WERTH of X")

3. **Recommended constants** to plug into `correlated_uncertainty.py` line 785-786:
   ```python
   HITTER_FA_RANK = ???   # empirically derived
   PITCHER_FA_RANK = ???  # empirically derived
   ```
