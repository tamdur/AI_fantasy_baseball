# Daily Newsletter Build Plan

**Created:** 2026-03-26
**Status:** NOT STARTED
**Owner:** Claude Code (CC) with user oversight
**Reference:** `daily_newsletter_infrastructure.md` for data source details, `STATE_OF_REPO.md` for codebase inventory

---

## How to Use This Document

This is a living build plan. CC should:

1. **Read this document at the start of every work session.**
2. **Update step statuses** as work completes: `NOT STARTED` → `IN PROGRESS` → `DONE` or `BLOCKED`.
3. **Flag open questions** inline using `> **QUESTION FOR USER:** ...` blockquote format. The user will answer directly in this file.
4. **Log issues** inline using `> **ISSUE:** ...` blockquote format with date.
5. **Never delete completed sections** — mark them DONE so we maintain a build log.
6. After completing Phase 1 (MVP), STOP and run the Phase 2 persona deep-dive before continuing to Phase 3.

---

## Architecture Overview

### What We're Building

A daily automated pipeline that:
1. Fetches live data from ESPN API, FanGraphs RoS API, and MLB Stats API
2. Preprocesses it into a compact analytical briefing book
3. Passes it to two expert analyst agents (Category Tactician + Actuary) powered by Claude Opus
4. Synthesizes their analyses into a tiered decision set via a third Opus call
5. Emails the result as a morning briefing

### The Three Agents

**Agent 1 — The Category Tactician**
Optimizes for winning this week's matchup by maximizing category count. Thinks in terms of: which categories are flippable, which are lost causes, rate-stat risk thresholds, two-start pitcher leverage, games-remaining asymmetry, streaming targets. Format-specific (H2H Most Categories) expertise.

**Agent 2 — The Actuary**
Treats every move as an expected-value calculation across a probability distribution. Uses cross-system projection disagreement as a risk signal. Asks: "What's the probability-weighted upside and downside of this specific add/drop across all 12 categories?" Catches negative-EV moves that look good superficially. Incorporates regression indicators (BABIP, K%, HR/FB%, Hard%) from FanGraphs leaderboard data as additional risk signals.

**Agent 3 — The Synthesizer**
Not a persona — a structured prompt that resolves disagreements between the Tactician and Actuary. Embeds Process Optimizer logic: move budget awareness (7/matchup), opponent behavioral tendencies (from 5-year historical analysis), league meta-game context (standings position, playoff implications). Outputs the final tiered decision set.

### Output Format

Email with three tiers:
- **TIER 1: DO THIS** — Both analysts agree, clear positive EV, no significant risk. One-line summary + brief reasoning.
- **TIER 2: JUDGMENT CALLS** — Analysts mostly agree but with a noted risk or dissent. Summary + the dissenting logic.
- **TIER 3: WORTH CONSIDERING** — One analyst recommends, the other is neutral/against. Lower confidence, longer time horizon, or speculative (e.g., prospect stash).

Plus a compact **MATCHUP DASHBOARD** showing category-by-category state (winning/losing/tight) and a **ROSTER HEALTH** section flagging IL-eligible players, cold streaks, or regression signals.

---

## Phase 1: Data Pipeline MVP

**Goal:** Fetch all required data, preprocess it into the briefing book JSON structure, and produce a first newsletter using a single (non-multi-agent) Claude call. Get the plumbing working before optimizing the intelligence layer.

All new code goes in `in_season/daily_digest/`. Do not modify existing `model/` or `data/` code — import and reuse from it.

### Step 1.1: Project Scaffolding — `DONE`

Create the directory structure and config:

```
in_season/daily_digest/
├── config.py              # API credentials, league constants, file paths
├── fetch_espn.py          # ESPN API data fetchers
├── fetch_fangraphs.py     # FanGraphs RoS projection + leaderboard fetchers
├── fetch_mlb.py           # MLB Stats API (probable pitchers, transactions)
├── preprocess.py          # Transform raw API data → briefing book JSON
├── agents.py              # Claude API calls (Tactician, Actuary, Synthesizer)
├── email_sender.py        # Format and send the newsletter email
├── run_newsletter.py      # Main pipeline orchestrator
├── prompts/
│   ├── tactician.md       # System prompt for Category Tactician
│   ├── actuary.md         # System prompt for Actuary
│   └── synthesizer.md     # System prompt for Synthesizer
└── output/
    └── (daily output files land here)
```

Implementation notes:
- `config.py` should load ESPN cookies (SWID, ESPN_S2) from environment variables or a `.env` file, NOT hardcoded. Reference `data/extraction_scripts/extract_all.py` for the existing auth pattern.
- Import league constants from `model/data_pipeline.py` (HITTING_CATS, PITCHING_CATS, NUM_TEAMS, ROSTER_SLOTS) rather than redefining them.
- Import `load_id_map()` and `join_ids()` from `model/data_pipeline.py` for player ID bridging.

### Step 1.2: ESPN API Fetchers — `DONE`

Build `fetch_espn.py` with the following functions. All use the same base URL and auth pattern from `data/extraction_scripts/extract_all.py`.

**Base URL:** `https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/2026/segments/0/leagues/84209353`

**Functions to implement:**

| Function | ESPN View | Returns | Notes |
|----------|-----------|---------|-------|
| `fetch_my_roster()` | `mRoster` | My team's roster (team ID 10) with player IDs, positions, injury status | Filter from all-teams response |
| `fetch_opponent_roster(team_id)` | `mRoster` | Specific opponent's roster | Same call, different filter |
| `fetch_all_rosters()` | `mRoster` | All 8 teams' rosters | Single API call returns all |
| `fetch_matchup_scores(scoring_period_id)` | `mBoxscore` | Per-category scores for current matchup | Need to determine current scoring period programmatically |
| `fetch_free_agents(count=250)` | `mFreeAgents` | Top free agents with player detail | Already implemented in extraction scripts |
| `fetch_standings()` | `mStandings` | Current W/L/T standings | Simple |
| `fetch_current_scoring_period()` | `mSettings` | Current scoring period ID | Extract from league settings response |

**Critical implementation detail for `fetch_matchup_scores`:** The `mBoxscore` view with `scoringPeriodId` is the ONLY ESPN view that returns per-category breakdowns. This has been proven to work for completed weeks. Verify it also works for in-progress weeks (it should — the historical extraction used the same endpoint). If not, flag as ISSUE.

**Auth:** Cookies `SWID` and `ESPN_S2` sent as request cookies. Load from env vars. Include error handling that detects auth expiration (typically returns 401 or empty data) and logs a clear message telling the user to refresh cookies.

**Rate limiting:** Add a 1-second delay between ESPN API calls. The API is undocumented and we don't want to get blocked.

> **QUESTION FOR USER:** Where do you want ESPN cookies stored? Options: (a) `.env` file in project root, (b) environment variables set in shell profile, (c) a `secrets.json` file in `.gitignore`. Current extraction scripts appear to hardcode them — we should fix that.

### Step 1.3: FanGraphs RoS Projection Fetcher — `DONE`

Build `fetch_fangraphs.py`. Two main functions:

**`fetch_ros_projections(stats='bat'|'pit')`**

```
GET https://www.fangraphs.com/api/projections?type=ratcdc&stats={bat|pit}&pos=all&team=0&players=0&lg=all
```

- Primary system: `ratcdc` (ATC RoS — same consensus approach used in pre-season WERTH)
- Fallback if `ratcdc` unavailable: `rsteamer`
- Returns JSON array of player projections with FanGraphs player IDs
- Save raw response to `output/ros_projections_{bat|pit}_{date}.json` for debugging
- **RoS projections only become available once the MLB regular season starts.** Before then, fall back to pre-season ATC CSVs already in `existing-tools/`.

**`fetch_leaderboard(stats='bat'|'pit')`**

```
GET https://www.fangraphs.com/api/leaders/major-league/data?pos=all&stats={bat|pit}&lg=all&qual=0&season=2026&month=0&ind=0
```

- Returns current-season actual stats for all players
- Key columns for regression detection: K%, BB%, BABIP, HR/FB%, Hard%, GB/FB
- `qual=0` gets everyone (no PA minimum)

**`fetch_multi_system_ros(stats='bat'|'pit')`**

For the Actuary's inter-projection disagreement signal. Fetch from multiple RoS systems:
- `rsteamer`, `rzips`, `ratcdc`, `rthebatx`, `rfangraphsdc`, `roopsy`
- Compute per-player standard deviation of projected counting stats across systems
- This reuses the same disagreement methodology from `model/correlated_uncertainty.py`
- **Frequency:** Weekly, not daily. Cache results and only re-fetch if >7 days stale.

**Rate limiting:** Max 1 request per 3 seconds to FanGraphs. Cache aggressively — RoS projections don't change daily.

> **QUESTION FOR USER:** Do you have a FanGraphs subscription login, or have the API endpoints been working without auth? The pre-season fetches in `fangraphs_guide.md` suggest no auth was needed for projection endpoints. Confirm this holds for RoS endpoints too (testable once season starts).

USER: Claude cowork can just directly access my chrome browser and navigate my logged-in experience. Not sure what can be done for CC

### Step 1.4: MLB Stats API Fetcher — `DONE`

Build `fetch_mlb.py`. Free, public, no auth required.

**`fetch_probable_pitchers(date)`**

```
GET https://statsapi.mlb.com/api/v1/schedule?date={YYYY-MM-DD}&sportId=1&hydrate=probablePitcher
```

- Returns today's games with probable starters including MLBAM IDs
- MLBAM ID is our universal join key (maps directly via SFBB ID Map)
- Parse out: pitcher name, MLBAM ID, team, opponent, game time, home/away

**`fetch_weekly_schedule(start_date, end_date)`**

```
GET https://statsapi.mlb.com/api/v1/schedule?startDate={}&endDate={}&sportId=1&hydrate=probablePitcher
```

- Fetch full week's schedule to identify two-start pitchers
- Cross-reference pitcher MLBAM IDs appearing 2+ times in the week
- Also compute games-per-team for counting stat projections

**`fetch_transactions(date)`**

```
GET https://statsapi.mlb.com/api/v1/transactions?date={YYYY-MM-DD}
```

- Filter for: call-ups (option recalls), DFA, trades
- Cross-reference with a prospect watchlist (initially hand-curated, later automated)
- Flag any transaction involving a player ranked in top-100 prospect lists

### Step 1.5: Player ID Bridging — `DONE`

Build the ID resolution layer in `preprocess.py`.

The join path is already proven: **FanGraphs `xMLBAMID` → SFBB `MLBID` → ESPN `ESPNID`**

Functions needed:
- `build_id_map()` — Load SFBB Player ID Map, build lookup dicts (MLBAM→ESPN, ESPN→MLBAM, FG→MLBAM). Reuse `load_id_map()` from `model/data_pipeline.py`.
- `resolve_player(espn_id=None, mlbam_id=None, fg_id=None)` — Given any one ID, return all three plus player name. Handle missing mappings gracefully (log warning, skip player).
- `merge_data_sources(espn_roster, ros_projections, leaderboard_stats)` — Join all data sources on MLBAM ID to produce a unified player record.

**Coverage expectation:** ~95% for fantasy-relevant players (per existing analysis). New mid-season call-ups may not be in the SFBB map immediately — SFBB updates monthly during the season. For unmapped players, use name-matching as fallback with a warning flag.

### Step 1.6: Briefing Book Generator — `DONE`

Build the core of `preprocess.py`: transform raw data into the compact, decision-ready JSON structure that gets injected into agent prompts.

**Target output structure:**

```json
{
  "date": "2026-05-15",
  "matchup_week": 7,
  "opponent": "Latte Nate",
  "days_remaining_in_matchup": 3,
  "moves_used": 4,
  "moves_remaining": 3,

  "category_state": {
    "R":    {"you": 28, "opp": 24, "status": "winning", "margin": 4},
    "HR":   {"you": 6,  "opp": 9,  "status": "losing",  "margin": -3},
    "TB":   {"you": 82, "opp": 70, "status": "winning", "margin": 12},
    "RBI":  {"you": 18, "opp": 20, "status": "tight",   "margin": -2},
    "SBN":  {"you": 2,  "opp": 5,  "status": "losing",  "margin": -3},
    "OBP":  {"you": 0.287, "opp": 0.271, "status": "winning", "margin": 0.016},
    "K":    {"you": 48, "opp": 40, "status": "winning", "margin": 8},
    "QS":   {"you": 1,  "opp": 3,  "status": "losing",  "margin": -2},
    "ERA":  {"you": 3.15, "opp": 3.22, "status": "tight", "margin": -0.07},
    "WHIP": {"you": 1.08, "opp": 1.22, "status": "winning", "margin": -0.14},
    "KBB":  {"you": 2.8, "opp": 2.9, "status": "tight",  "margin": -0.1},
    "SVHD": {"you": 2,  "opp": 4,  "status": "losing",  "margin": -2}
  },

  "category_triage": {
    "winning_comfortably": ["R", "TB", "K", "WHIP"],
    "winning_narrow": ["OBP"],
    "too_close_to_call": ["RBI", "ERA", "KBB"],
    "losing_flippable": ["QS", "SVHD"],
    "losing_unrecoverable": ["HR", "SBN"]
  },

  "my_roster": [
    {
      "name": "Player Name",
      "espn_id": 12345,
      "mlbam_id": 67890,
      "positions": ["SS", "2B"],
      "status": "ACTIVE",
      "ros_werth": 5.2,
      "ros_werth_sigma": 1.8,
      "games_remaining_this_week": 4,
      "z_scores": {"R": 0.8, "HR": 1.2, ...},
      "regression_flags": ["BABIP .220 (due for correction up)", "HR/FB 28% (unsustainable)"]
    }
  ],

  "drop_candidates": [],

  "opponent_roster": [],

  "top_free_agents": [
    {
      "name": "FA Name",
      "positions": ["SP"],
      "ros_werth": 2.1,
      "marginal_value_to_weak_cats": 1.8,
      "ownership_pct": 12,
      "note": "Two starts this week (vs COL, vs MIA)"
    }
  ],

  "streamable_pitchers_today": [
    {
      "name": "Pitcher Name",
      "opponent": "COL",
      "park": "Coors Field",
      "proj_k": 6.2,
      "proj_era": 4.10,
      "proj_whip": 1.25,
      "proj_kbb": 2.8,
      "two_start_this_week": true,
      "era_risk_assessment": "Your ERA cushion is 0.07 — this stream risks flipping ERA against you"
    }
  ],

  "two_start_pitchers_available": [],

  "transactions_today": [],

  "standings": {},

  "opponent_tendencies": "Latte Nate historically strongest in K/QS/WHIP/KBB (pitcher-heavy build). Weakest in R, SBN, SVHD. Tends to make 2-3 moves per matchup, mostly mid-week. Rarely streams on weekends.",

  "league_context": "Week 7 of 22. You are 4th place (9-5). Top 4 make playoffs. Nate is 2nd (11-3)."
}
```

**Implementation notes:**

- `category_triage` classification logic:
  - "winning_comfortably": margin > 20% of opponent's total (counting) or > 0.010 (OBP) / similar thresholds for rate stats
  - "winning_narrow": winning but within 10%
  - "too_close_to_call": margin < 10% either direction
  - "losing_flippable": losing but within a reasonable range for the days remaining (e.g., down 2 QS with 3 days left = flippable)
  - "losing_unrecoverable": losing by a margin that would require heroic luck to flip
  - These thresholds need tuning — start with rough heuristics, refine over the first 2 weeks of use.

- `drop_candidates`: Bottom 3 rostered players by RoS WERTH, excluding anyone on IL (they're free to hold).

- `regression_flags`: From FanGraphs leaderboard data. Flag when:
  - BABIP < .250 or > .350 (hitters), < .260 or > .320 (pitchers)
  - HR/FB% > 22% (hitters) or < 8% (pitchers sustaining low ERA)
  - K% diverging >5pp from career rate
  - LOB% > 80% or < 65% for pitchers

- `opponent_tendencies`: Pull from `analysis/league_history_report.md` — this is static text, loaded from file and injected per opponent.

- `marginal_value_to_weak_cats`: Reuse the MV formula from the draft tool, but scoped to current `category_triage.losing_flippable` and `too_close_to_call` categories instead of weakest-4.

### Step 1.7: WERTH Engine Adaptation — `DONE`

Create a lightweight in-season WERTH calculator that reuses the existing engine but runs on RoS projections.

**Do NOT modify `model/valuation_engine.py`.** Instead, create `in_season/daily_digest/ros_werth.py` that:

1. Imports core functions from `model/valuation_engine.py` (convert_rate_stats, compute_zscores)
2. Accepts RoS projection DataFrames as input (instead of reading from CSV)
3. Computes z-scores using the same methodology
4. Uses current rosters (from ESPN API) to dynamically determine the starter pool, NOT the static pre-season pool
5. Computes replacement level per position based on who's actually available on waivers (bottom of FA list), not the (N+1)th best

**Key difference from pre-season WERTH:** The starter pool is no longer theoretical — it's the actual rostered players in the league. The replacement level is the best available free agent at each position.

### Step 1.8: MVP Newsletter Generator — `DONE`

For Phase 1, use a single Claude API call (not the multi-agent pipeline) to generate the newsletter from the briefing book. This validates the data pipeline end-to-end before adding agent complexity.

Build `agents.py` with:

```python
def generate_mvp_newsletter(briefing_book: dict) -> str:
    """Single Claude call that produces the full newsletter."""
    # Use claude-sonnet-4-20250514 for MVP (cheaper, faster iteration)
    # System prompt includes: league context, category weights,
    # the tiered decision framework, and instructions to be specific
    # and actionable (no "start your studs" generalities)
    ...
```

System prompt for MVP should encode:
- The 12-category H2H Most Categories format and what it means tactically
- The tiered decision framework (Tier 1/2/3)
- The swing category analysis (QS 0.60 tie rate, SVHD 0.52, HR 0.47)
- The 7-move-per-matchup constraint
- Instructions to always consider rate-stat risk when recommending streams
- Instructions to always note who to drop when recommending adds

### Step 1.9: File Delivery — `DONE`

Build `email_sender.py`.

Options (in order of preference):
1. **Gmail SMTP** — Simplest. Use an app password with `smtplib`. 
2. **SendGrid free tier** — 100 emails/day, more reliable deliverability.
3. **Write to file + manual send** — Fallback if email is too complex for MVP.

Email should be HTML-formatted for readability on mobile. Keep it scannable:
- Subject line: `⚾ Daily Briefing — Week {N} vs {Opponent} — {date}`
- Tier 1 actions at the top in bold
- Matchup dashboard as a compact HTML table
- Full analysis below the fold

> **QUESTION FOR USER:** What email address should this send to? And what email/SMTP credentials should it send from? If you have a Gmail account, an app password is the easiest setup.

### Step 1.10: Pipeline Orchestrator — `DONE`

Build `run_newsletter.py` — the single entry point.

```python
def main():
    """Run the full daily newsletter pipeline."""
    # 1. Fetch data (ESPN, FanGraphs if stale, MLB Stats API)
    # 2. Build ID map and merge data sources
    # 3. Compute RoS WERTH for rostered players + top FAs
    # 4. Generate briefing book JSON
    # 5. Call Claude to generate newsletter
    # 6. Send email
    # 7. Save briefing book + newsletter to output/ for debugging

    # Error handling: if any data source fails, log the failure
    # and proceed with whatever data is available. Never fail silently.
    # The newsletter should note which data sources were unavailable.
```

**CC Scheduler integration:** This script should be runnable as `python3 in_season/daily_digest/run_newsletter.py`. CC scheduler will invoke it daily at a configured time (probably 7 AM CDT).

> **QUESTION FOR USER:** What time do you want the newsletter? First pitch on most days is ~1:10 PM CDT (Chicago time). Morning delivery (7-8 AM) gives you time to act before lineups lock. Earlier?

USER: I'll make a scheduler for this, and it'll be run 2am CT

### Step 1.11: MVP End-to-End Test — `DONE`

Before the regular season starts (Opening Day is March 27, 2026 — TOMORROW):

1. Run the pipeline with pre-season data as a dry run
2. Verify ESPN API calls still work with current cookies
3. Verify FanGraphs leaderboard endpoint works (projections won't have RoS yet)
4. Verify MLB Stats API probable pitcher endpoint returns data for Opening Day
5. Generate a test newsletter using pre-season WERTH data + mock matchup scores
6. Send test email and verify formatting on mobile

> **ISSUE LOG:**
> (CC: add issues here as they arise during build)

---

## Phase 2: Persona Intelligence Deep Dive

**Goal:** AFTER Phase 1 MVP is working, use the Tactician and Actuary personas themselves (via Claude) to research what additional data sources, analytical frameworks, and decision heuristics would make them most effective. Then rebuild the prompts and data pipeline based on what they surface.

**This phase is explicitly a research-then-rebuild loop.** Do not skip it.

### Step 2.1: Tactician Self-Assessment — `DONE`

Give the Category Tactician persona a copy of:
- The briefing book JSON schema
- The 12 categories and swing category analysis
- The league settings (roster, matchup format, move limits)
- Sample output from Phase 1

Ask it: "You are the Category Tactician for an 8-team H2H Most Categories league. Given the data you receive in the briefing book, what additional data, analytical frameworks, or decision rules would make your recommendations significantly better? Be specific about data sources and how you'd use them. Focus on what's achievable with public APIs and a FanGraphs subscription."

Capture its response and evaluate feasibility against our data stack.

### Step 2.2: Actuary Self-Assessment — `DONE`

Same exercise for the Actuary persona. Key question: "What additional risk signals, probability models, or decision frameworks would improve your ability to assess the expected value of roster moves? What data would you need?"

### Step 2.3: Prompt Engineering — `DONE`

Based on 2.1 and 2.2, rebuild `prompts/tactician.md` and `prompts/actuary.md` with:
- Specific analytical frameworks the personas identified
- League-specific context (swing categories, opponent tendencies, historical patterns)
- Decision heuristics encoded as rules (e.g., "Never recommend a stream if ERA cushion < 0.05 and the pitcher's projected ERA > 4.00")
- Format instructions for structured output that the synthesizer can parse

### Step 2.4: Data Pipeline Additions — `DONE`

Implement any new data fetches or preprocessing identified in 2.1/2.2 that are feasible. Update the briefing book schema accordingly.

---

## Phase 3: Multi-Agent Pipeline

**Goal:** Replace the single-call MVP with the Tactician → Actuary → Synthesizer pipeline.

### Step 3.1: Agent Implementation — `DONE`

Rebuild `agents.py` with three separate API calls:

```python
def run_tactician(briefing_book: dict) -> str:
    """Category Tactician analysis. Uses claude-opus-4-6."""
    # System prompt from prompts/tactician.md
    # Returns: structured analysis of category triage, streaming recs,
    #          add/drop recommendations, rate-stat risk assessments

def run_actuary(briefing_book: dict) -> str:
    """Actuary risk analysis. Uses claude-opus-4-6."""
    # System prompt from prompts/actuary.md
    # Returns: EV calculations for proposed moves, risk flags,
    #          projection disagreement signals, regression alerts

def run_synthesizer(briefing_book: dict, tactician_output: str, actuary_output: str) -> str:
    """Synthesizer with Process Optimizer logic. Uses claude-opus-4-6."""
    # System prompt from prompts/synthesizer.md
    # Includes: move budget status, opponent tendencies, standings context
    # Resolves disagreements between Tactician and Actuary
    # Outputs: final tiered decision set (Tier 1/2/3)
```

**Cost consideration:** Three Opus calls per day × ~26 weeks = ~550 calls. At current API pricing this is likely $50-150/season depending on context length. Acceptable for the value delivered, but monitor token usage.

**Fallback:** If Opus is unavailable or too expensive, Sonnet can handle the Tactician and Actuary calls with only modest quality loss. Reserve Opus for the Synthesizer where judgment quality matters most.

### Step 3.2: Synthesizer Prompt with Process Optimizer — `DONE`

The synthesizer prompt must embed:
- Move budget awareness: "The user has {N} moves remaining this matchup. Each move has opportunity cost."
- Opponent behavioral model: loaded from `analysis/league_history_report.md` per opponent
- Standings context: current position, games back, playoff implications
- Temporal awareness: early season (build roster) vs mid-season (optimize matchups) vs late season (playoff positioning) vs playoffs (maximize upside)
- The tiered agreement framework: all agree → Tier 1, mostly agree → Tier 2, split → Tier 3
- The swing category data as a tiebreaker: when in doubt, prioritize QS > SVHD > HR moves

### Step 3.3: Output Formatting — `DONE`

Design the final email template. Must be scannable in 60 seconds on a phone screen.

```
SUBJECT: ⚾ Week 7 vs Latte Nate — Day 5/7 — Winning 5-4-3

━━━ TIER 1: DO THIS ━━━
• Drop [Player] → Add [Player] — flips SVHD from 2-4 to 3-3 [Tactician ✓ Actuary ✓]

━━━ TIER 2: JUDGMENT CALLS ━━━  
• Stream Pfaadt vs COL today — likely flips QS (1-3 → 2-3)
  ⚠ Actuary: ERA cushion is only 0.07. Pfaadt's proj ERA 4.10 = 35% chance of flipping ERA against you.

━━━ TIER 3: CONSIDER ━━━
• [Prospect] recalled to 40-man yesterday. Top-50 prospect, ETA unclear.
  Tactician: stash. Actuary: wait for confirmation of MLB roster spot.

━━━ MATCHUP DASHBOARD ━━━
[compact category table with color coding]

━━━ ROSTER HEALTH ━━━
⚠ [Player] — BABIP .218, due for regression up. Hold.
🔴 [Player] — placed on IL yesterday. Drop candidate.
```

### Step 3.4: Integration Testing — `NOT STARTED`

Run the full multi-agent pipeline for 3 consecutive days and review:
- Are the Tactician and Actuary producing genuinely different analyses?
- Is the Synthesizer correctly resolving disagreements?
- Are the recommendations specific and actionable (not generic)?
- Is the email readable in 60 seconds?
- Are there any data gaps that produce "I don't have enough information" hedging?

**Critical check — Lineup Slot / Position Eligibility Awareness:**
- Verify agents understand ESPN lineup slot constraints when recommending adds/drops.
- **The Ohtani test case:** Ohtani occupies DH/UTIL on most nights. If the system recommends dropping another DH-only player and adding a non-DH (e.g., a pitcher), that's fine. But if it recommends adding ANOTHER DH-only player while Ohtani is already in UTIL, it needs to flag the slot conflict. Similarly, it should never recommend dropping Stanton "to pick up a DH" when Ohtani already fills that role — the real recommendation should be to pick up someone who fills a DIFFERENT positional need or a pitcher.
- The briefing book must include each player's `lineup_slot` and full `positions` eligibility list so agents can reason about slot constraints.
- Test: recommend an add/drop that would leave a required lineup slot empty. The Synthesizer should catch and VETO this.

---

## Phase 4: Automation & Polish

### Step 4.1: CC Scheduler Setup — `NOT STARTED`

Configure CC scheduler to run `python3 in_season/daily_digest/run_newsletter.py` daily at the target time.

Handle: 
- Off-days (no games = no newsletter, or abbreviated version)
- All-Star break
- Failure recovery (if pipeline crashes, send an error email rather than nothing)

### Step 4.2: Cookie Refresh Mechanism — `NOT STARTED`

ESPN cookies expire every few weeks. Build a detection + notification system:
- If ESPN API returns 401 or empty data, log the failure
- Send an alert email: "ESPN cookies expired. Refresh SWID and ESPN_S2 in config."
- Pipeline continues with stale cached data + a note in the newsletter that ESPN data may be outdated

### Step 4.3: Weekly RoS Refresh — `NOT STARTED`

Separate the weekly data refresh (RoS projections, multi-system disagreement, SFBB ID Map update) from the daily pipeline. Run weekly on Sundays via a separate script or CC scheduler job.

### Step 4.4: Prospect Watchlist — `NOT STARTED`

Build a simple hand-curated watchlist of top prospects to monitor via MLB Stats API transactions. Start with top-20 relevant prospects for the 8-team format (only elite prospects matter in shallow leagues).

File: `in_season/daily_digest/prospect_watchlist.json`

```json
[
  {"name": "Player Name", "mlbam_id": 12345, "position": "SS", "org": "BAL", "eta": "May 2026", "note": "Top-5 prospect, 40-man added"}
]
```

Cross-reference against daily transactions. If a watchlist player appears in a recall or 40-man addition, flag prominently in the newsletter.

---

## Appendix A: Data Source Quick Reference

| Source | Endpoint | Auth | Rate Limit | Freshness |
|--------|----------|------|------------|-----------|
| ESPN API | `lm-api-reads.fantasy.espn.com/apis/v3/games/flb/...` | SWID + ESPN_S2 cookies | Undocumented, use 1s delay | Real-time |
| FanGraphs Projections | `fangraphs.com/api/projections?type=...` | None (confirmed for pre-season) | Be gentle, 3s delay | Weekly |
| FanGraphs Leaderboard | `fangraphs.com/api/leaders/major-league/data?...` | None | Same | Daily-capable |
| MLB Stats API | `statsapi.mlb.com/api/v1/...` | None (free, public) | Generous | Real-time |
| SFBB ID Map | CSV file in `existing-tools/` | N/A | N/A | Monthly update |

## Appendix B: Existing Code Reuse Map

| Need | Existing Code | Location | Reuse Strategy |
|------|--------------|----------|----------------|
| Z-score computation | `compute_zscores()` | `model/valuation_engine.py` | Import directly |
| Rate stat conversion | `convert_rate_stats()` | `model/valuation_engine.py` | Import directly |
| Replacement level | `compute_replacement_level()` | `model/valuation_engine.py` | Import, adapt pool |
| ID mapping | `load_id_map()`, `join_ids()` | `model/data_pipeline.py` | Import directly |
| League constants | `HITTING_CATS`, `PITCHING_CATS`, etc. | `model/data_pipeline.py` | Import directly |
| ESPN API auth pattern | Cookie-based fetch | `data/extraction_scripts/extract_all.py` | Copy pattern |
| Opponent tendencies | Historical analysis text | `analysis/league_history_report.md` | Load as string |
| Swing category weights | QS=0.60, SVHD=0.52, HR=0.47 | `analysis/league_history_report.md` | Encode in prompts |
| MC uncertainty model | Correlated simulation | `model/correlated_uncertainty.py` | Weekly batch reuse |

## Appendix C: Key League Rules for Prompt Encoding

- **Format:** 8-team H2H Most Categories, weekly matchups, 22 regular season weeks
- **Categories (6H/6P):** R, HR, TB, RBI, SBN, OBP | K, QS, ERA↓, WHIP↓, K/BB, SVHD
- **Roster:** C, 1B, 2B, 3B, SS, MI, CI, 5×OF, UTIL, 9×P, 3×BE, 3×IL
- **Moves:** 7 per matchup (weekly), daily lineup changes, lock at game time
- **Waivers:** 1-day waiver period, move-to-last-after-claim order
- **Playoffs:** Top 4 teams, starts after week 22
- **Keepers:** 3 per team, locked 1 hour before draft
- **Our team:** Brohei Brotanis (team ID 10)
- **Our draft position was 4th overall (snake)**

## Appendix D: Open Questions Log

> **QUESTION FOR USER:** ESPN cookie storage preference? `.env` file, env vars, or `secrets.json`?
Whatever is easier
> **QUESTION FOR USER:** Email delivery — what address to send to, and what SMTP credentials to send from?
Actually let's just have it save to a simple txt file in the directory that I can open, no need to overcomplicate
> **QUESTION FOR USER:** Preferred newsletter delivery time? (Suggested: 7-8 AM CDT)
I'll set this up in scheduler, but will have it running early, say 2am CT
> **QUESTION FOR USER:** Do you want the newsletter on off-days / All-Star break, or only on game days?
All game days
> **QUESTION FOR USER:** Anthropic API key — should the pipeline use your existing key, or do you want a separate one for cost tracking? The pipeline will need `ANTHROPIC_API_KEY` in the environment.
Existing key under my MAX plan (also why I'm not worried about Opus costs)

USER: Other note. At the end of the txt report that constitutes a 60 second read, if the experts have additional commentary or thoughts that are lying behind the recommendations, I'd be happy to have it available as an appendix that I can read on through if I'd like to understand the thinking better
