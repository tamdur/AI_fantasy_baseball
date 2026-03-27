# State of the Repo — AI Fantasy Baseball

**As of:** 2026-03-27
**Season:** 2026 MLB season in progress (Opening Week, Matchup 1: Mar 25–Apr 5)
**Repo:** https://github.com/tamdur/AI_fantasy_baseball
**Newsletter:** https://tamdur.github.io/AI_fantasy_baseball/

---

## What This Project Is

A full-stack fantasy baseball system for an 8-team ESPN H2H Most Categories keeper league. Two major subsystems:

1. **Pre-draft model** (complete) — WERTH valuations, correlated uncertainty, injury model, interactive draft tool
2. **In-season daily newsletter** (active) — multi-agent pipeline that fetches live data, generates a daily matchup briefing, publishes to GitHub Pages

## League Specifics

- **Format:** 8-team, H2H Most Categories, snake draft, 3 keepers per team
- **User's team:** Brohei Brotanis (team ID 10)
- **Hitting categories (6):** R, HR, TB, RBI, SBN (net steals), OBP
- **Pitching categories (6):** K, QS, ERA↓, WHIP↓, K/BB, SVHD (saves+holds)
- **Roster:** C, 1B, 2B, 3B, SS, 5×OF, MI, CI, UTIL, 9×P, 3×BE, 3×IL
- **Schedule:** 22 regular matchups (Mar 25–Sep 6) + 2 playoff rounds (Sep 7–20). MP1=12 days, MP15=14 days, rest=7 days.

---

## What's Built

### 1. Daily Newsletter Pipeline (`in_season/daily_digest/`) — ACTIVE

Multi-agent pipeline that runs daily via `/generate` command:

```
ESPN API (rosters, matchups, standings, FAs)
+ FanGraphs RoS projections + leaderboards
+ Baseball Savant xStats (50 BBE sample size gate)
+ MLB Stats API (probable pitchers, schedule, transactions)
+ Park factors, team quality, Vegas lines, closer roles
→ RoS WERTH computation
→ Briefing book assembly (category state, triage, player data with team abbrevs)
→ Tactician + Actuary agents (parallel) → Synthesizer agent
→ Post-processing validation (header line correction)
→ Publish to docs/index.html (GitHub Pages)
→ Calibration logging (predictions.csv)
```

**Key design decisions:**
- **Schedule-driven matchup metadata** — `data/league_schedule_2026.json` (from ESPN PDF) provides exact matchup dates/lengths/opponents, not the unreliable ESPN API `matchupPeriods` mapping
- **ESPN dual ID systems** — `eligibleSlots` uses SLOT_MAP (0=C,1=1B,2=2B,3=3B,4=SS); `defaultPositionId` uses POS_MAP (different numbering). Code filters eligibleSlots through `REAL_POSITION_SLOTS` set.
- **Sample size gates** — Savant regression signals require ≥50 BBE (batters) / ≥50 BF (pitchers). Agent prompts enforce additional gates: BABIP ≥100 PA, LOB% ≥40 IP, velocity ≥3 starts.
- **Anti-churn guardrails** — Drop urgency classification (URGENT vs NON-URGENT), option value computation, early-season patience rules in all agent prompts
- **Name collision detection** — `add_name_collision_warnings()` flags FAs sharing last names with rostered players; all player references include MLB team abbreviation
- **Dynamic move limits** — `moves_max` from schedule JSON (not hardcoded 7). Prompts use percentage-based thresholds that scale with matchup length.
- **Calibration loop** — `calibration.py` logs predicted P(win) per category daily. `log_actuals_from_espn()` records post-matchup results. `calibration_report()` generates accuracy analysis after 5+ matchups.

**Agent prompts** (`in_season/daily_digest/prompts/`):
- **Tactician** — Category count optimizer, triage protocol, rate-stat dilution math, drop urgency classification
- **Actuary** — Delta-EV framework, risk cards, irreversibility premium, option value, 9 negative-EV trap detectors, sample size gates
- **Synthesizer** — Agreement resolver (Tier 1/2/3/Veto), anti-churn guardrail, self-consistency rules, player disambiguation
- **MVP Analyst** — Single-call fallback if multi-agent pipeline fails

### 2. GitHub Pages Publishing — ACTIVE

- `docs/index.html` — Latest newsletter (dark theme, monospace, mobile-friendly)
- `docs/archive/` — Past newsletters with prev/next navigation chain
- `publish.py` — Archives previous page, wires nav links, builds footer archive index
- Published at: https://tamdur.github.io/AI_fantasy_baseball/

### 3. Pre-Draft Model (`model/`) — COMPLETE

| Component | File | Description |
|-----------|------|-------------|
| Valuation engine | `valuation_engine.py` | WERTH z-scores, replacement level, position adjustment |
| Correlated uncertainty | `correlated_uncertainty.py` | 8-system disagreement, Cholesky MC, truncated expectation |
| Injury model | `injury_model.py` + `current_injuries.py` | Projection-based + hand-curated overlay |
| Export pipeline | `export_rankings.py` | Full pipeline: valuation → MC → injury → CSV/JSON |
| Draft tool builder | `build_draft_tool.py` | Generates single-file HTML with inlined data |
| Historical analysis | `historical_analysis.py` | 5-year matchup/draft/keeper patterns |
| Keeper analysis | `keeper_analysis.py` | Keeper value-over-cost recommendations |
| Waiver floor | `waiver_floor_analysis.py` | Empirical floors from 2022-2025 actuals |

### 4. Draft-Day HTML Tool (`draft_tool/index.html`) — COMPLETE

Single-file, ~955KB, fully offline browser tool. 1,470 ranked players with all 12 category z-scores, click-to-draft, category dashboard, marginal value rankings, keeper persistence, opponent tracking.

### 5. Data Assets

| Asset | Location | Notes |
|-------|----------|-------|
| League schedule | `data/league_schedule_2026.json` | Authoritative matchup dates (from PDF) |
| FanGraphs CSVs (23 files) | `existing-tools/` + `data/FanGraphs/` | 8 projection systems |
| Historical stats | `data/historical_stats/` | FanGraphs bat/pit 2022-2025 |
| League history | `data/drafts/`, `data/matchups/`, `data/standings/` | 2021-2025 |
| SFBB ID Map | `existing-tools/` | Player ID bridge |

---

## Known Issues / Open Work

### DV/MV Pitching Bias (Known, Low Priority)
DV and MV are biased toward hitters (avg DV: 10.58 hitters vs 4.83 pitchers). Root cause: waiver floor asymmetry (49%), raw z-score compression (32%), replacement level boost (19%). Empirical waiver floors partially addressed this but the gap persists.

### Calibration Data Needed
After 5+ completed matchups, run `calibration_report()` to assess whether P(win) estimates are well-calibrated. If not, tune the triage thresholds in `preprocess.py`.

---

## File Structure

```
AI_fantasy_baseball/
├── CLAUDE.md                    # Project instructions (loaded every session)
├── STATE_OF_REPO.md             # This file
├── SKILL.md                     # Napkin runbook skill definition
├── .claude/
│   ├── napkin.md                # Live runbook
│   ├── commands/generate.md     # /generate slash command
│   └── projects/.../memory/     # Persistent memory
├── docs/                        # GitHub Pages (https://tamdur.github.io/AI_fantasy_baseball/)
│   ├── index.html               # Latest newsletter
│   └── archive/                 # Past newsletters with prev/next nav
├── in_season/daily_digest/      # ---- ACTIVE DEVELOPMENT ----
│   ├── run_newsletter.py        # Pipeline orchestrator
│   ├── config.py                # Credentials, stat/slot/position maps
│   ├── fetch_espn.py            # ESPN API + schedule JSON loader
│   ├── fetch_fangraphs.py       # FanGraphs RoS projections
│   ├── fetch_savant.py          # Savant xStats (sample-size gated)
│   ├── fetch_mlb.py             # MLB Stats API
│   ├── fetch_extras.py          # Park factors, team quality, Vegas, closers
│   ├── fetch_weather.py         # Game weather
│   ├── ros_werth.py             # RoS WERTH computation
│   ├── preprocess.py            # Briefing book assembly
│   ├── agents.py                # Multi-agent newsletter generation
│   ├── publish.py               # GitHub Pages HTML publishing
│   ├── calibration.py           # Prediction logging and calibration
│   ├── save_output.py           # Local file output
│   ├── prompts/                 # Agent system prompts
│   │   ├── tactician.md
│   │   ├── actuary.md
│   │   ├── synthesizer.md
│   │   └── mvp_analyst.md
│   └── output/                  # (gitignored) caches, newsletters, logs
├── model/                       # Pre-draft valuation model
│   ├── data_pipeline.py         # Load, derive, join, merge projections
│   ├── valuation_engine.py      # WERTH z-scores
│   ├── correlated_uncertainty.py
│   ├── injury_model.py
│   ├── current_injuries.py
│   ├── export_rankings.py
│   ├── build_draft_tool.py
│   ├── historical_analysis.py
│   ├── keeper_analysis.py
│   ├── waiver_floor_analysis.py
│   └── output/                  # Rankings, uncertainty, injury CSVs
├── draft_tool/
│   └── index.html               # Draft day tool (~955KB, offline)
├── data/
│   ├── league_schedule_2026.json # Matchup dates/opponents (authoritative)
│   ├── league_schedule_2026.pdf  # Source ESPN schedule
│   ├── league_config.json
│   ├── FanGraphs/               # Raw projection CSVs
│   ├── historical_stats/        # FanGraphs end-of-season 2022-2025
│   ├── drafts/                  # 2021-2025 draft picks
│   ├── matchups/                # 2021-2025 per-category results
│   └── standings/               # 2021-2025 W/L/T
├── existing-tools/              # FanGraphs CSVs, SFBB ID Map, Mr. Cheatsheet
├── analysis/                    # League history, keeper, uncertainty, waiver floor
├── research/                    # WERTH methodology, data assessment, newsletter infra
├── plans/                       # Build plans and cowork prompts
└── fangraphs_guide.md           # FanGraphs REST API documentation
```

## How to Run

### Daily Newsletter
```bash
# Via slash command (recommended):
/generate

# Or manually:
python3 in_season/daily_digest/run_newsletter.py
# Then: git add docs/ && git commit -m "Newsletter YYYY-MM-DD" && git push
```

### Rebuild Pre-Draft Model
```bash
cd model
python3 export_rankings.py        # Full pipeline
python3 build_draft_tool.py       # Regenerate HTML tool
```

### Post-Matchup Calibration
```python
from calibration import log_actuals_from_espn, calibration_report
log_actuals_from_espn(matchup_period=1)  # After MP1 ends (Apr 5)
calibration_report()                      # After 5+ matchups
```
