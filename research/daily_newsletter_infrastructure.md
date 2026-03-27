# Daily Newsletter Research: Infrastructure & Data Source Assessment

**Date:** 2026-03-26
**Purpose:** Understand what existing tools, pipelines, APIs, and data sources can be leveraged to build a daily fantasy baseball newsletter that provides expert-level roster advice.

---

## The Product Vision

A one-page daily briefing that tells you exactly what moves to make today. Think of it as a personal expert analyst who has already done the homework: checked your matchup category gaps, scanned the wire, flagged prospect call-ups, and distilled it all into 3-5 actionable items. The bar is top-professional-fantasy-player-level expertise — not generic "start your studs" advice.

---

## 1. What We Can Reuse Today (Existing Codebase)

### Valuation Engine — Production-Ready

The WERTH pipeline (`model/valuation_engine.py`) can be repurposed almost directly for in-season use. The key functions:

| Function | What It Does | In-Season Use |
|----------|-------------|---------------|
| `convert_rate_stats()` | OBP/ERA/WHIP/KBB → counting equivalents | Same math applies to actual stats or RoS projections |
| `compute_zscores()` | Per-category z-scores within starter pool | Recompute weekly with RoS projections as input |
| `compute_replacement_level()` | (N+1)th best at each position | Recalculate as rosters churn — the wire floor shifts |
| `compute_position_adjusted_werth()` | Final WERTH rankings | The core of "who should I roster?" |
| `identify_starter_pool()` | Top 104 H + 72 P | Needs dynamic version — re-identify as season progresses |

**Key adaptation:** The engine currently runs on pre-season ATC projections. For in-season, swap in RoS projections blended with year-to-date actuals. The z-score math is identical.

### ID Mapping — Complete

The SFBB Player ID Map (`existing-tools/SFBB Player ID Map - PLAYERIDMAP.csv`) bridges every system we need:

```
FanGraphs (xMLBAMID / IDFANGRAPHS)
  ↔ MLBAM ID (MLBID) — the universal join key
    ↔ ESPN (ESPNID)
    ↔ Baseball-Reference (BREFID)
    ↔ Yahoo (YAHOOID)
    ↔ Rotowire (ROTOWIREID)
    ↔ FantasyPros (FANTPROSNAME)
```

3,825 players mapped. Coverage is ~95%+ for fantasy-relevant players. The `ACTIVE` column can filter to current MLB players.

### Injury Model — Adaptable

`model/injury_model.py` provides structural injury risk (PA/IP gap between systems). `model/current_injuries.py` provides the hand-curated overlay. For in-season use:
- The structural model doesn't need retraining — the projections encode risk for the full season
- The current injuries file needs weekly updates (could be automated from ESPN injury feed)
- The discount formula (`risk_adj_werth *= 1 - games_missed_current/162`) scales cleanly to remaining games

### Historical League Data — Contextual Intelligence

Five years of this league's data is already extracted and analyzed:

| Data | Location | Newsletter Use |
|------|----------|---------------|
| Matchup results (per-category) | `data/matchups/matchups_YYYY.json` | Historical matchup tendencies per opponent |
| Standings | `data/standings/standings_YYYY.json` | Context for playoff positioning |
| Draft history | `data/drafts/draft_YYYY.json` | Who valued what — informs trade targets |
| Manager tendencies | `analysis/league_history_report.md` | "Nate always picks up SPs on Monday" type insights |
| Category swing analysis | `analysis/league_history_report.md` | Which categories flip matchups most often (QS, SVHD, HR) |

The key finding from historical analysis: QS has an 18% tie rate and 42% thin-margin rate. **The newsletter should always flag QS-impacting moves first** — a single quality start pickup flips more matchups than any other category improvement.

### ESPN API Extraction Patterns — Working

`data/extraction_scripts/extract_all.py` has proven patterns for:
- Roster fetching (all 8 teams, full player detail)
- Matchup scores via `mBoxscore` view (the ONLY view that returns per-category breakdown)
- Free agent listings (top 250)
- Standings

Auth requires SWID + ESPN_S2 cookies (already configured). These expire periodically but are stable for weeks.

---

## 2. What Needs to Be Built

### A. Current-Week Category Scores (Critical Path)

**The problem:** We need to know "you're losing HR 12-15 against Simon this week" to make useful recommendations.

**ESPN API approach:**
```
GET /apis/v3/games/flb/seasons/2026/segments/0/leagues/84209353
    ?view=mBoxscore&scoringPeriodId={WEEK}
```

Returns `scoreByStat` per team per matchup with actual category totals. This is the same endpoint used for historical matchup extraction — it's proven to work. The `scoringPeriodId` parameter selects the current week.

**Gap:** No code currently fetches mid-week live scores. The extraction script only pulls completed weeks. Need a new function that:
1. Determines current scoring period
2. Fetches in-progress category scores
3. Computes category gaps (your total vs opponent's total per category)
4. Identifies which categories are winnable, lost, or on the margin

**Complexity:** Low — the API pattern exists, just needs a new wrapper.

### B. Rest-of-Season Projections (Critical Path)

**The problem:** Pre-season projections become stale as the season progresses. By May, a player who's been hurt for 3 weeks or who's dramatically over/underperforming needs updated projections.

**FanGraphs RoS projection API:**
```
GET /api/projections?type=rsteamer&stats=bat&pos=all&team=0&players=0&lg=all
GET /api/projections?type=ratcdc&stats=pit&pos=all&team=0&players=0&lg=all
```

Available RoS systems (active only during MLB season):
- `rsteamer` — Steamer RoS
- `rzips` / `rzipsdc` — ZiPS RoS
- `rthebat` / `rthebatx` — THE BAT RoS
- `ratcdc` — ATC RoS (preferred, same consensus approach as pre-season)
- `rfangraphsdc` — Depth Charts RoS
- `roopsy` — OOPSY RoS

**The play:** Fetch `ratcdc` weekly as the primary RoS source. The existing `load_atc_batters()`/`load_atc_pitchers()` functions need only minor adaptation to handle RoS column names (they're the same schema). Then re-run `run_valuation()` on RoS data to get updated WERTH rankings.

**Complexity:** Medium — API endpoint is documented, but RoS projections only become available once the regular season starts. Can't test until then.

### C. Waiver Wire Intelligence (High Value)

**The problem:** "Who should I pick up?" requires knowing (a) who's available, (b) their expected RoS value, and (c) which of your categories they'd help.

**What we have:**
- `Flaim MCP get_free_agents()` — player names, positions, ownership %, with position filtering
- ESPN API free agent view — same data, more fields
- The marginal value concept from the draft tool (weakest-4-category targeting)

**What we need:**
1. Fetch free agent list (Flaim or ESPN API)
2. Match to RoS projections via MLBAM ID
3. Compute RoS WERTH for each FA
4. Apply the marginal value formula against your current roster's category profile
5. Rank by "how much does this pickup improve my weakest categories this week"

**The marginal value formula from the draft tool translates directly:**
```javascript
// Current draft tool logic (build_draft_tool.py line 350-357)
weakCats = bottom 4 categories by z-score sum
mv = sum(z_weakcat * 1.5 for weak cats) + 0.3 * risk_adj_werth
```

For in-season, replace "my draft roster" with "my current active roster" and "all categories" with "categories I'm losing this week."

**Complexity:** Medium — the logic exists, but needs the RoS projection pipeline (B above) and live category scores (A above) as inputs.

### D. Streaming Pitcher Recommendations (High Value, Unique to H2H)

**The problem:** In H2H, streaming pitchers for QS/K is the highest-leverage daily move. You need to know which available SPs are starting today, against whom, and whether starting them helps your K/QS/ERA/WHIP balance.

**Data sources needed:**
- **Daily probable pitchers:** MLB.com or ESPN starting pitcher feeds
- **Matchup quality:** Team-level stats vs LHP/RHP (available on FanGraphs)
- **Pitcher RoS projection:** FanGraphs RoS (already planned above)

**FanGraphs has probable pitcher data but no documented API endpoint.** Options:
1. ESPN API — player `status` field may indicate "Probable Pitcher" (needs testing)
2. Flaim MCP — roster data includes some status info
3. MLB Stats API (`statsapi.mlb.com`) — has a `/schedule` endpoint that returns probable pitchers:
   ```
   GET https://statsapi.mlb.com/api/v1/schedule?date=2026-04-15&sportId=1&hydrate=probablePitcher
   ```
   This is a free, public, well-documented API. Returns pitcher MLBAM IDs which we can map directly.

**Complexity:** Medium — the MLB Stats API is the cleanest path for daily pitchers. Matchup quality requires a team-level stats table (FanGraphs leaderboards).

### E. Prospect Call-Up Tracking (Differentiator)

**The problem:** The best fantasy managers act on call-ups before they happen. A top prospect getting the call is a waiver wire gold rush — you need to know before your leaguemates.

**Current state:** Zero prospect infrastructure in the codebase. No MiLB data, no prospect rankings, no call-up detection.

**Data sources to investigate:**

| Source | Data | Access | Quality |
|--------|------|--------|---------|
| **MLB Stats API** (`statsapi.mlb.com`) | 40-man roster transactions, option/recall moves | Free, public REST API | Authoritative but reactive (reports after the fact) |
| **FanGraphs prospect rankings** | Top 100/org lists, ETA estimates | Subscription (user has one) | Pre-season only, no daily updates |
| **Baseball Prospectus** | PECOTA forecasts, MiLB stats, ETA | Subscription (unknown) | Best prospect data, but expensive |
| **Roster Resource** (rosterresource.com) | Org depth charts, 40-man status | Free web scraping | Good for "who's next in line" |
| **MLB Pipeline** (mlb.com/prospects) | Top 100, org reports, news | Free | Good for narratives, not structured data |
| **FantasyPros / Rotowire** | Prospect call-up alerts, news feeds | Subscription/free tier | Aggregated, but not always fastest |

**Practical approach for the newsletter:**

1. **40-man roster monitoring** via MLB Stats API — any player added to the 40-man or recalled from options is a potential call-up signal
   ```
   GET https://statsapi.mlb.com/api/v1/transactions?date=2026-04-15
   ```
2. **FanGraphs top prospect list** as a watchlist — cross-reference with 40-man moves
3. **Service time thresholds** — prospects controlled through Super 2 date (typically mid-June) are less likely to be called up before then

**The SFBB ID Map has `MLBID` for many prospects** (even pre-debut players get MLBAM IDs when added to 40-man rosters), so the ID bridge infrastructure already supports this.

**Complexity:** High — this is the most novel component. The MLB Stats API transactions endpoint is the most feasible automated approach.

---

## 3. External APIs Deep Dive

### ESPN Fantasy API

**Base URL:** `https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/{YEAR}/segments/0/leagues/84209353`

| View Parameter | Returns | Useful For |
|---|---|---|
| `mSettings` | League config, categories, teams, roster slots | One-time setup |
| `mRoster` | All teams' rosters with player detail | Daily roster check |
| `mBoxscore` + `scoringPeriodId` | Per-category matchup scores | **Live category tracking** |
| `mDraftDetail` | Full draft pick history | Historical context |
| `mFreeAgents` | Available free agents | Waiver recommendations |
| `mStandings` | W/L/T, playoff seeds | Standings context |

**Auth:** Requires `SWID` and `ESPN_S2` cookies. Already configured in `data/extraction_scripts/extract_all.py`. Cookies expire every few weeks — need a refresh mechanism or prompt.

**Rate limits:** Undocumented. Historical extraction used delays between requests. For daily use (a few calls per day), unlikely to be an issue.

**Known broken:** Transactions endpoint returns 0 for baseball. Player news/alerts not available.

### FanGraphs API

**Base URL:** `https://www.fangraphs.com/api/projections?type={TYPE}&stats={bat|pit}&pos=all&team=0&players=0&lg=all`

| Endpoint | Use Case | Availability |
|---|---|---|
| Pre-season projections (`atc`, `steamer`, etc.) | Baseline WERTH | Year-round |
| **RoS projections** (`ratcdc`, `rsteamer`, etc.) | Updated WERTH during season | **Season only** (typically April-September) |
| Leaderboard API (`/api/leaders/major-league/data`) | Current-season actual stats | Year-round |
| Platoon splits (`steamer_vl_0`, `steamer_vr_0`) | Matchup-specific advice | Pre-season |

**Leaderboard API (for actual stats):**
```
GET /api/leaders/major-league/data?pos=all&stats=bat&lg=all&qual=0&season=2026&month=0&ind=0
```
Returns JSON with all player stats for the season. `qual=0` gets everyone (no PA minimum). This is essential for computing actual-performance z-scores.

**Auth:** FanGraphs subscription required for some data (user has one). Most projection and leaderboard endpoints work without auth.

### MLB Stats API (New — Not Yet Used)

**Base URL:** `https://statsapi.mlb.com/api/v1/`

Free, public, no auth required. Relevant endpoints:

| Endpoint | Returns | Newsletter Use |
|---|---|---|
| `/schedule?date=YYYY-MM-DD&sportId=1&hydrate=probablePitcher` | Today's games + probable starters with MLBAM IDs | Streaming pitcher recommendations |
| `/transactions?date=YYYY-MM-DD` | All MLB transactions (call-ups, DFA, trades) | Prospect call-up detection |
| `/people/{MLBAM_ID}` | Player bio, current team, roster status | Verify call-up status |
| `/teams/{TEAM_ID}/roster?rosterType=40Man` | Full 40-man roster | Monitor for additions/recalls |
| `/standings?leagueId=103,104` | MLB standings | Context for team-level analysis |

**This is the highest-value new data source.** It's free, reliable, returns MLBAM IDs (our universal join key), and provides the two things we can't get elsewhere: probable pitchers and real-time transactions.

### Flaim MCP (Already Integrated)

Useful as a conversational interface for quick lookups, but not for automated daily pipelines:
- `get_roster(team_id)` — quick roster check
- `get_free_agents(position)` — browse available players
- `get_standings()` — current standings
- `get_matchups()` — matchup pairings (but NOT per-category scores)

**Limitation:** Returns no stats, no projections, no per-category matchup data. Use for convenience, not for analysis.

---

## 4. Data Flow Architecture (Proposed)

```
                          ┌──────────────────────────────────┐
                          │     DAILY NEWSLETTER PIPELINE     │
                          └──────────────┬───────────────────┘
                                         │
            ┌────────────────────────────┼────────────────────────────┐
            │                            │                            │
     ┌──────▼──────┐            ┌───────▼───────┐           ┌───────▼────────┐
     │  ESPN API    │            │  FanGraphs    │           │  MLB Stats API │
     │              │            │               │           │                │
     │ • My roster  │            │ • RoS proj    │           │ • Prob pitchers│
     │ • Matchup    │            │ • Leaderboard │           │ • Transactions │
     │   scores     │            │   (actuals)   │           │ • 40-man moves │
     │ • Free agents│            │               │           │                │
     │ • Opponent   │            │               │           │                │
     │   roster     │            │               │           │                │
     └──────┬───────┘            └───────┬───────┘           └───────┬────────┘
            │                            │                            │
            └────────────────────────────┼────────────────────────────┘
                                         │
                               ┌─────────▼─────────┐
                               │  SFBB ID MAP      │
                               │  (MLBAM ↔ ESPN    │
                               │   ↔ FanGraphs)    │
                               └─────────┬─────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
           ┌────────▼────────┐  ┌───────▼───────┐  ┌───────▼────────┐
           │ WERTH Engine    │  │ Category Gap  │  │ Prospect Watch │
           │ (RoS-based)     │  │ Tracker       │  │ (40-man +      │
           │                 │  │               │  │  FG rankings)  │
           │ Reuse:          │  │ Your cats vs  │  │                │
           │ valuation_      │  │ opponent cats │  │ Cross-ref      │
           │ engine.py       │  │ → which are   │  │ transactions   │
           │                 │  │   winnable?   │  │ with prospect  │
           │ Input: RoS proj │  │               │  │ lists          │
           │ Output: WERTH   │  │ Input: ESPN   │  │                │
           │ per FA + roster │  │ mBoxscore     │  │ Input: MLB API │
           └────────┬────────┘  └───────┬───────┘  └───────┬────────┘
                    │                    │                    │
                    └────────────────────┼────────────────────┘
                                         │
                               ┌─────────▼─────────┐
                               │  RECOMMENDATION   │
                               │  ENGINE           │
                               │                   │
                               │ • Drop X, Add Y   │
                               │ • Stream pitcher Z │
                               │ • Stash prospect W │
                               │ • Category outlook │
                               └─────────┬─────────┘
                                         │
                               ┌─────────▼─────────┐
                               │  NEWSLETTER       │
                               │  (HTML or MD)     │
                               └───────────────────┘
```

---

## 5. Reusable Code Inventory

### Can Use As-Is

| Module | Function/Asset | Reuse Notes |
|---|---|---|
| `model/valuation_engine.py` | `run_valuation()` | Swap ATC → RoS projections as input |
| `model/valuation_engine.py` | `convert_rate_stats()` | Identical math for actuals or RoS |
| `model/valuation_engine.py` | `compute_zscores()` | Recompute weekly |
| `model/data_pipeline.py` | `load_id_map()` | Universal join infrastructure |
| `model/data_pipeline.py` | `join_ids()` | FG → MLBAM → ESPN bridge |
| `model/data_pipeline.py` | Constants (`HITTING_CATS`, `PITCHING_CATS`, `NUM_TEAMS`, `ROSTER_SLOTS`) | Unchanged |
| `model/current_injuries.py` | `merge_injury_data()` | Update injury dict weekly |
| `model/injury_model.py` | `load_injury_estimates()` | Structural risk baseline |
| `data/extraction_scripts/extract_all.py` | ESPN API patterns, auth | Copy fetch logic |
| `existing-tools/SFBB Player ID Map` | Full ID crosswalk | Same file, same joins |
| `analysis/league_history_report.md` | Opponent tendencies, swing cat analysis | Context for recommendations |

### Needs Adaptation

| Module | What to Change |
|---|---|
| `model/data_pipeline.py` | New `load_ros_projections()` function fetching from FanGraphs RoS API |
| `model/data_pipeline.py` | New `load_current_stats()` function fetching FanGraphs leaderboard |
| `model/valuation_engine.py` | `identify_starter_pool()` needs to use current rosters, not projections-only |
| `model/correlated_uncertainty.py` | MC simulation may be overkill for daily; simpler RoS WERTH sufficient |
| `model/export_rankings.py` | New export format for newsletter (not draft tool JSON) |

### Needs to Be Built From Scratch

| Component | Description | Primary Data Source |
|---|---|---|
| Live matchup category tracker | Fetch current-week category scores, compute gaps | ESPN API `mBoxscore` |
| Streaming pitcher recommender | Today's probable starters × RoS WERTH × matchup quality | MLB Stats API + FanGraphs RoS |
| Prospect call-up monitor | 40-man roster changes × prospect ranking watchlist | MLB Stats API transactions |
| Waiver wire ranker (in-season) | FA list × RoS WERTH × marginal value vs your weak cats | ESPN/Flaim FA list + FanGraphs RoS |
| Newsletter generator | Template engine that assembles sections into daily output | All of the above |
| Scheduler/runner | Cron job or manual trigger to run pipeline daily | OS-level |

---

## 6. Data Freshness Requirements

| Data Type | How Often | Source | Latency Tolerance |
|---|---|---|---|
| My roster | Daily (before newsletter) | ESPN API or Flaim | Same-day |
| Opponent roster | Daily | ESPN API or Flaim | Same-day |
| Category scores (live matchup) | Daily during matchup weeks | ESPN API `mBoxscore` | Few hours |
| RoS projections | Weekly | FanGraphs RoS API | Days (projections don't change daily) |
| Current-season actuals | Weekly (for trend detection) | FanGraphs leaderboard API | Days |
| Free agent list | Daily | ESPN API or Flaim | Same-day |
| Probable pitchers | Daily (morning) | MLB Stats API `/schedule` | Must be same-day morning |
| Transactions/call-ups | Daily | MLB Stats API `/transactions` | Hours (ideally real-time) |
| Injury updates | Daily | ESPN roster status + manual | Same-day |

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|---|---|---|
| ESPN cookies expire mid-season | Breaks all ESPN data fetching | Build a "cookie refresh" prompt; detect auth failures gracefully |
| FanGraphs RoS projections format differs from pre-season | Loader functions may break | Test on day 1 of season; keep pre-season loader as fallback |
| FanGraphs rate-limits or blocks API calls | Can't fetch leaderboard/RoS data | Cache aggressively; fetch at most once per day; have CSV fallback |
| MLB Stats API changes | Breaks probable pitcher / transaction fetch | This API has been stable for years; low risk |
| Prospect call-up detection has false positives | Recommends stashing a player who doesn't get called up | Frame as "watch" not "must-add"; use prospect ranking as confidence filter |
| SFBB ID Map doesn't include mid-season call-ups | Can't map newly debuted players | SFBB updates the map during the season; re-download monthly |
| Newsletter generation takes too long | Not ready by morning | Pre-compute RoS WERTH weekly; only daily-variable data fetched live |

---

## 8. Open Questions for Design Phase

1. **Delivery format:** HTML email? Markdown file? Browser page like the draft tool? Slack message?
2. **Timing:** Morning (for that day's lineup decisions) or evening (for next-day waiver claims)?
3. **Automation level:** Fully automated cron job, or triggered manually via Claude Code?
4. **Blending actuals + projections:** How much weight should YTD performance get vs RoS projections in the WERTH calculation? (Standard approach: Marcel-style regression — weight actuals more as sample size grows.)
5. **Trade recommendations:** In scope? Requires modeling other teams' rosters and needs.
6. **Playoff-aware recommendations:** Should strategy shift as playoffs approach (e.g., "you're locked in, rest starters" vs "must-win, stream aggressively")?
