# Flaim MCP Assessment — Magic Conch 2025 (ESPN League 84209353)

**Date:** 2026-03-22
**MCP Endpoint:** `https://api.flaim.app/mcp`

---

## 1. Connection Status

- **`flaim` MCP server:** FAILED — OAuth token expired, needs re-authorization
- **`claude_ai_Flaim_Fantasy` MCP server:** WORKING — all tools functional
- The working server found 3 connected leagues: Magic Conch 2025 (baseball), Magic Conch League (football), IF 2025 Fantasy Football
- Your team: **Brohei Brotanis** (team ID 10)

---

## 2. Tool-by-Tool Results

### Test 1: User Session ✅
Returns all connected leagues with platform, sport, league ID, team ID, season year, league name, and team name. Correctly identifies Magic Conch 2025 as the default baseball league.

### Test 2: League Info ⚠️ Partial
**What it returns:**
- League name, size (8 teams), season ID, scoring type (`H2H_MOST_CATEGORIES`)
- All 8 team names and abbreviations (but NO owner/manager names — just team names)
- Roster slot counts (as numeric slot codes, not human-readable positions)
- Previous seasons list: 2021, 2022, 2023, 2024, 2025
- Schedule info (playoff seeding rule, matchup period length)

**What's MISSING:**
- **Scoring categories NOT listed** — only tells us it's H2H categories, not which 12 categories (R, HR, TB, RBI, SBN, OBP, K, QS, ERA, WHIP, K/BB, SVHD)
- **Roster positions use numeric codes** (0, 1, 2, 3... 19) not human-readable names (C, 1B, 2B, etc.)
- **No manager/owner names** — only team names and abbreviations

### Test 3: My Roster ✅ (with gaps)
**What it returns per player:**
- Player name, position, eligible positions, lineup slot
- Pro team, injury status
- Percent owned / percent started (league-wide ESPN %)
- Acquisition type (DRAFT or ADD) and acquisition date

**Your current roster (26 players):** Ohtani, Yordan Alvarez, Crochet, Lindor, Logan Gilbert, Blake Snell, Acuna Jr., Mike Trout, Freddy Peralta, Luis Castillo, Gausman, Hunter Brown, Riley Greene, Brice Turang, Vinnie Pasquantino, Luis Arraez, Randy Arozarena, Kodai Senga, Nick Castellanos, Maikel Garcia, Clay Holmes, Aroldis Chapman, Agustin Ramirez, Ryan McMahon, Brendon Little, Brad Keller

**What's MISSING:**
- **No player stats** — `stats` field is empty `{}` for every player
- **No projections**
- **No keeper designations** — cannot tell which players are kept vs. drafted fresh

### Test 4: All Rosters ✅
Successfully pulled rosters for all 8 teams. Same data quality as Test 3 — player names, positions, acquisition info, but no stats and no keeper info. All 8 teams returned full rosters.

### Test 5: Standings ⚠️ Partial
**2026 (current):** All zeros — season hasn't started (expected)

**2025 (historical):** Returns W/L/T record, win percentage, playoff seed, and rank for all 8 teams:
| Rank | Team | Record | Win% |
|------|------|--------|------|
| 1 | TBD's H0E$ | 15-5-2 | .682 |
| 2 | Big Pfaadt Tatis | 15-7-0 | .682 |
| 3 | Latte Nate | 12-8-2 | .545 |
| 4 | Team Q | 12-7-3 | .545 |
| 5 | Brohei Brotanis | 10-11-1 | .455 |
| 6 | Shohei's Translator | 8-11-3 | .364 |
| 7 | Ya Like Jazz? | 7-14-1 | .318 |
| 8 | Special K | 3-19-0 | .136 |

**What's MISSING:**
- **No category-level stats** (total R, HR, etc. for each team across the season)
- **No points for/against** (always 0 — likely because it's a categories league, not points)

### Test 6: Free Agents ⚠️ Partial
**What it returns:** Player name, position, eligible positions, pro team, injury status, percent owned/started. Position filter works (tested with `SP`).

**Top free agents returned:** Jesus Luzardo, Sonny Gray, Devin Williams, Spencer Strider, Nathan Eovaldi, Drake Baldwin, Kyle Bradish, Emilio Pagan, Cam Schlittler, Michael King... (25 returned by default, max 100)

**What's MISSING:**
- **No stats** — `stats` field is empty `{}` for every player
- **No projections**
- Without stats, free agent analysis is severely limited

### Test 7: Ancient History ⚠️ Partial
**What it returns:** Confirms seasons 2021, 2022, 2023, 2024, 2025 are accessible for league 84209353. Includes your team name each year (wsb Stonks for 2021-2022, Ted GPT for 2023-2024, Brohei Brotanis for 2025).

**Can access past season data:**
- ✅ `get_standings` for 2025 — returns full standings with W/L/T
- ✅ `get_league_info` for 2025 — returns team names, settings
- ✅ `get_matchups` for 2025 week 1 — returns matchup pairings and winners
- ❌ `get_transactions` for 2025 week 1 — `ESPN_NOT_FOUND` error

**What's CRITICALLY MISSING:**
- **No draft results** — there is no `get_draft` tool at all. Cannot see who picked whom in what round for any season.
- **No historical category-level matchup data** — matchups return winner (HOME/AWAY) and total points (all 0 for categories leagues), but NOT the per-category breakdown
- **Historical transactions are limited/broken** — querying 2025 transactions with a specific week returns ESPN_NOT_FOUND

### Test 8: Matchups ⚠️ Partial
**2026:** Empty matchups (pre-season, expected)

**2025 Week 1:** Returns 4 matchup pairings with home/away team IDs and winner designation. Has `pointsByScoringPeriod` with 13 entries (scoring periods 1-13), but all values are 0.

**What's MISSING:**
- **No category-level scores** — doesn't show R, HR, ERA, etc. per team per matchup
- **Points are always 0** for categories leagues — the points model doesn't apply

### Test 9: Transactions ⚠️ Limited
**2026:** Returns 0 transactions (recent two-week window, pre-season)

**2025:** Default query (recent 2 weeks of completed season) returns 0. Week-specific query returns ESPN_NOT_FOUND error.

**What's available:** The tool supports filtering by type (add, drop, trade, waiver, etc.) and shows FAAB bids, trade lifecycle. But accessing historical transaction data is problematic.

---

## 3. Data Availability Matrix

| Data Need | Flaim Provides? | Quality | Notes |
|-----------|----------------|---------|-------|
| **League settings** | ✅ Yes | Medium | Scoring type but not specific categories; roster slots as numeric codes |
| **Team names** | ✅ Yes | Good | All 8 teams with abbreviations |
| **Manager/owner names** | ❌ No | — | Only team names, not owner identities |
| **Current rosters (all teams)** | ✅ Yes | Good | Player names, positions, eligible positions, acquisition info |
| **Player stats** | ❌ No | — | Stats field always empty `{}` |
| **Player projections** | ❌ No | — | Not included anywhere |
| **Keeper designations** | ❌ No | — | No keeper status field; can only infer from acquisitionType=DRAFT |
| **Draft results (pick order)** | ❌ No | — | No draft tool exists |
| **Standings (W/L/T)** | ✅ Yes | Good | Current + historical seasons |
| **Category-level standings** | ❌ No | — | No per-category totals |
| **Matchup results** | ⚠️ Partial | Low | Winner only, no category scores |
| **Weekly category scores** | ❌ No | — | Critical gap for matchup analysis |
| **Free agents** | ⚠️ Partial | Low | Names/positions only, no stats |
| **Transactions (current)** | ⚠️ Partial | Medium | Recent window only, supports type filters |
| **Transactions (historical)** | ❌ No | — | Past-season queries fail |
| **Injury status** | ✅ Yes | Good | Active, Day-to-Day, Out, SIXTY_DAY_DL, Suspended |
| **Ownership %** | ✅ Yes | Good | League-wide ESPN ownership percentages |
| **Historical seasons (2021-2025)** | ⚠️ Partial | Low | Can see standings and rosters but not draft/stats/categories |

---

## 4. Recommendation

### Verdict: Flaim CANNOT be the primary data source. We need `espn-api` (or direct ESPN API access) for most analytical work.

Flaim is useful as a **convenience layer for roster lookups and basic standings** but lacks the depth needed for serious fantasy analysis.

### For the Draft Tool (Historical Analysis): ❌ Flaim is insufficient

**What we need that Flaim can't provide:**
- Draft results (who picked whom, in what round, at what pick) — **no draft tool exists**
- Historical player stats (to analyze draft pick value over time) — **stats always empty**
- Keeper history (which players were kept, at what cost) — **no keeper data**
- Category-level matchup data (to evaluate how draft picks affected weekly H2H performance) — **only winner, no categories**

### For In-Season Tools (Daily Roster, Matchups, Waivers): ⚠️ Flaim is partially useful

**What Flaim CAN do:**
- Pull current rosters for all teams (good for seeing who owns whom)
- Show free agent pool with position filtering
- Show standings and basic matchup pairings
- Show injury status and ownership %

**What Flaim CAN'T do for in-season:**
- Provide player stats or projections (needed for start/sit, waiver priority)
- Show category-level matchup scores (needed for weekly strategy)
- Provide scoring category details (need to know exactly which categories to optimize)

---

## 5. What's Missing — Build List for `espn-api`

### Critical (Must Build)
1. **Draft results** — Full draft history for 2021-2025 (pick number, round, player, team)
2. **Player stats** — Season stats and weekly stats for rostered + free agent players
3. **Scoring categories** — Programmatic access to the 12 category definitions (R, HR, TB, RBI, SBN, OBP, K, QS, ERA, WHIP, K/BB, SVHD)
4. **Category-level matchup data** — Weekly H2H category scores per team per matchup
5. **Player projections** — Season/ROS projections (may need external source like FanGraphs/Steamer, not just ESPN)

### Important (Should Build)
6. **Keeper designations** — Which players were kept and at what round cost
7. **Historical transactions** — Full transaction log per season (adds, drops, trades, FAAB bids)
8. **Manager/owner mapping** — Team ID to real owner name
9. **Category-level standings** — Season-long category totals per team (for roto-style analysis)

### Nice to Have (Flaim covers adequately)
10. Current rosters — Flaim works fine here
11. Basic standings — Flaim provides W/L/T
12. Free agent pool listing — Flaim covers names/positions (but still need stats from elsewhere)
13. Injury status — Flaim provides this

### Recommended Architecture
- **Flaim:** Use for quick roster lookups, free agent browsing, and basic league structure during conversations
- **`espn-api` Python package:** Primary data source for all analytical work — draft analysis, matchup breakdowns, player stats, projections, keeper strategy
- **External projections (FanGraphs Steamer/ZiPS, ATC):** ESPN projections may be limited; supplement with industry-standard projection systems
