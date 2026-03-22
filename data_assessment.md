# ESPN Data Extraction Assessment

## 1. What We Got

### League Configuration
- All 12 scoring categories confirmed with stat IDs and direction: R(20), HR(5), TB(8), RBI(21), SBN(25), OBP(17), K(48), QS(63), ERA(47↓), WHIP(41↓), K/BB(82), SVHD(83)
- Full roster structure: C, 1B, 2B, 3B, SS, 5×OF, MI, CI, UTIL, 9×P, 3×BE, 3×IL
- Draft settings: Snake, 60-second picks, 3 keepers per team
- **Your 2026 draft position: 4th pick** (order: [6, 9, 5, 10, 1, 7, 4, 3])
- All 8 teams with owner names

### Draft History (2021-2025) — Complete
- 5 years of drafts, all player names resolved (0 unknowns)
- Keeper picks flagged for 2022 (20 keepers) and 2023 (17 keepers)
- Pick-by-pick: round, pick number, player, team, keeper status
- Note: League was 10 teams 2021-2023, reduced to 8 in 2024

### Matchup Data (2021-2025) — Complete with Category Detail
- All matchup periods for all 5 seasons (21-24 periods each)
- **Per-category scores with WIN/LOSS/TIE results** — the critical data for understanding category dynamics
- Used `mBoxscore` API view (the only one that returns `scoreByStat`)

### Standings (2021-2025) — Complete
- W/L/T records for all teams, all seasons
- Standing/rank information

### Current Rosters (2026) — Complete
- All 8 teams' full rosters (26-28 players each)
- Player names, ESPN IDs, position eligibility, injury status

### ESPN Projections (2026) — Good
- 1,200 players fetched, 615 have ESPN season projections
- Projections include all standard batting and pitching stats
- Both 2025 actuals and 2026 projections available for many players

### Free Agents (2026)
- Top 250 free agents with position, team, ownership %

## 2. What We Didn't Get

| Data | Status | Impact |
|------|--------|--------|
| **Transactions** | ESPN API returns 0 for all years | Low — can infer activity from roster changes. Not critical for draft tool. |
| **Keeper designations for 2024-2025** | Keeper flag shows 0 | Medium — may need to infer from draft position patterns or ask the commissioner. 2022/2023 keeper data IS available. |
| **Keeper round costs** | Not in API | Medium — need this for keeper value analysis. May need manual input. |
| **Playoff bracket results** | Only regular season | Low — nice for historical context but not needed for draft tool. |

## 3. Data Quality Notes

### Scoring Category Verification
The 12 categories were confirmed by cross-referencing stat IDs against actual player stats:
- OBP is statId 17 (not OPS, not statId 16 which is PA)
- K/BB is statId 82 (verified: Crochet 255K/46BB = 5.543, matches stat 82 = 5.543)
- SVHD is statId 83 (verified: Chapman SV=32 + HLD=4 = 36, matches stat 83 = 36)
- QS is statId 63 (verified against starter counts)
- ERA and WHIP use `isReverseItem=true` (lower is better)

### Matchup Data Quirk
- `mMatchupScore` and `mMatchup` views do NOT return `scoreByStat` — only `mBoxscore` does
- The `box_scores()` method in espn-api v0.45.1 is broken for baseball (`Can't instantiate abstract class BoxScore without an implementation for abstract method '_process_team'`)
- Workaround: direct API calls to `mBoxscore` view

### League Size Change
- 2021-2023: 10 teams (250 draft picks per year)
- 2024-2025: 8 teams (200 draft picks per year)
- Historical analysis should account for this when comparing draft patterns

### ESPN Projection Coverage
- 615 of 1,200 players have projections — good coverage for fantasy-relevant players
- Projections include full stat lines, not just composite scores
- These can supplement FanGraphs projections for cross-validation

## 4. Implications for the Draft Tool

### What This Data Enables

1. **Category margin analysis** — With 5 years of per-category matchup results, we can analyze which categories are decided by the tightest margins and should be prioritized
2. **Draft tendency profiling** — 5 years of draft data shows who each manager tends to draft (position preferences, round tendencies, keeper patterns)
3. **Historical keeper analysis** — 2022-2023 keeper data reveals which players were kept and how that affected draft dynamics
4. **Projection cross-validation** — ESPN projections + FanGraphs Steamer + ATC = three independent projection sources for blending
5. **Category balance tracking** — League category definitions are programmatically confirmed, enabling real-time category gap analysis during the draft

### What We Still Need

1. **2026 keeper selections** — Which 3 players is each team keeping? Need to ask or check closer to draft day.
2. **Keeper round costs** — If keepers cost a draft pick, need to know which round. May need manual input.
3. **FanGraphs projection merge** — Need to join ESPN projections with FanGraphs CSVs via SFBB ID Map (MLBAM ID bridge) for a blended projection set.

### Draft Position Intelligence
You pick **4th overall** in a snake draft. In an 8-team snake:
- Round 1: Pick 4
- Round 2: Pick 13 (8×2 - 4 + 1)
- Round 3: Pick 20
- Round 4: Pick 29
- Pattern: picks 4, 13, 20, 29, 36, 45, 52, 61...

This is a strong position — you get a top-4 player and your round 2 pick (13th overall) is early enough to still get elite talent.
