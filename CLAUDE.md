# Project: AI Fantasy Baseball

## Napkin Workflow (Always Active)
Every session, before doing any other work:
1. Read `.claude/napkin.md` and apply its guidance silently.
2. Curate: re-prioritize, merge duplicates, remove stale items, enforce max 10 per category.
3. During work, update the napkin whenever you learn something reusable (frequent gotchas, user directives, non-obvious tactics). Each entry must have a date and "Do instead:" line.

See `.claude/SKILL.md` for full napkin specification.

## League Context
- 8-team ESPN H2H Most Categories keeper league (League ID: 84209353)
- Team: Brohei Brotanis (team ID 10)
- Hitting: R / HR / TB / RBI / SBN / OBP
- Pitching: K / QS / ERA / WHIP / K÷BB / SVHD
- Draft: March 24, 2026 (completed)
- Season: March 25 – September 20, 2026 (22 regular matchups + 2 playoff rounds)

## Project Phase
**In-season.** The draft tool (`draft_tool/index.html`) is complete and was used for the draft. The active development focus is the **daily newsletter pipeline** (`in_season/daily_digest/`), which generates a daily matchup briefing, publishes it to GitHub Pages, and tracks prediction calibration.

## Key Slash Commands
- **`/generate`** — Run the full daily newsletter pipeline: fetch data → compute WERTH → generate newsletter via Claude agents → publish to GitHub Pages → commit and push.

## Key Files

### In-Season Pipeline (active)
- `in_season/daily_digest/run_newsletter.py` — Pipeline orchestrator (run this or use `/generate`)
- `in_season/daily_digest/config.py` — Credentials, stat maps, SLOT_MAP, POS_MAP, PRO_TEAM_ABBREV
- `in_season/daily_digest/http_utils.py` — Shared rate limiting (`RateLimiter`) and JSON file caching
- `in_season/daily_digest/fetch_espn.py` — ESPN API fetchers (rosters, matchups, standings, FAs)
- `in_season/daily_digest/fetch_fangraphs.py` — FanGraphs RoS projections + leaderboards
- `in_season/daily_digest/fetch_savant.py` — Baseball Savant xStats (sample size gated: 50 BBE min)
- `in_season/daily_digest/fetch_mlb.py` — MLB Stats API (probable pitchers, schedule)
- `in_season/daily_digest/fetch_extras.py` — Park factors, team quality, Vegas lines, closer roles
- `in_season/daily_digest/preprocess.py` — ID bridging, briefing book assembly
- `in_season/daily_digest/agents.py` — Multi-agent newsletter: Tactician + Actuary → Synthesizer
- `in_season/daily_digest/publish.py` — HTML rendering + GitHub Pages publishing with prev/next nav
- `in_season/daily_digest/calibration.py` — Prediction logging and calibration reports
- `in_season/daily_digest/prompts/` — Agent system prompts (tactician, actuary, synthesizer, mvp_analyst)

### Shared Module
- `model/league.py` — League constants (categories, roster slots, team count) and ID bridge utilities (`load_id_map`, `join_ids`). Imported by both pre-draft model and in-season pipeline.

### Schedule & Data
- `data/league_schedule_2026.json` — Authoritative matchup dates/opponents (from PDF). MP1=12d, MP15=14d, rest=7d.
- `data/league_schedule_2026.pdf` — Source ESPN schedule screenshot
- `reference/fangraphs_guide.md` — FanGraphs REST API documentation

### Pre-Draft Model (complete, reference only)
- `model/valuation_engine.py` — WERTH z-score pipeline
- `model/correlated_uncertainty.py` — MC correlated uncertainty + waiver floors
- `model/injury_model.py` + `model/current_injuries.py` — Injury risk model
- `model/export_rankings.py` — Full pipeline: valuation → MC → injury → export
- `draft_tool/index.html` — Draft day HTML tool (~955KB, offline)

### Research & Analysis
- `research/` — Research docs (WERTH methodology, data assessment, Flaim assessment, newsletter infra)
- `analysis/` — League history, keeper analysis, uncertainty methodology, waiver floor reports
- `plans/` — Build plans, roadmap, and cowork prompts
- `reference/` — API documentation (FanGraphs guide)

### Published Output
- `docs/index.html` — Latest newsletter (GitHub Pages: https://tamdur.github.io/AI_fantasy_baseball/)
- `docs/archive/` — Past newsletters with prev/next navigation

## Data Architecture
- **Projections**: 23 FanGraphs CSVs in `existing-tools/` + RoS projections fetched live via API
- **FanGraphs API**: REST at `/api/projections?type={TYPE}&stats={bat|pit}&pos=all`. See `reference/fangraphs_guide.md`.
- **Player ID bridge**: SFBB ID Map (FanGraphs `xMLBAMID` → SFBB `MLBID` → `ESPNID`)
- **Live league data**: Direct ESPN API with cookie auth (`mBoxscore`, `mRoster`, `mSettings` views)
- **Matchup schedule**: `data/league_schedule_2026.json` (not ESPN API — API mapping is unreliable early season)
- **Valuation**: Z-score (WERTH) methodology, both pre-season (full) and RoS (in-season)
- **Newsletter agents**: Claude Code CLI (`claude --print --model sonnet`) via MAX plan (no API fees)

## Conventions
- Python for all tooling (not Excel)
- Rate stats must be converted to counting equivalents before z-scoring
- Replacement level = (N+1)th best at position for 8-team rosters
- ESPN `eligibleSlots` uses SLOT_MAP IDs (0=C,1=1B,2=2B,3=3B,4=SS); `defaultPositionId` uses POS_MAP IDs (different numbering). Never mix them.
- Savant regression signals gated at ≥50 BBE (batters) / ≥50 BF (pitchers) — no early-season noise
- All player references should include MLB team abbreviation for disambiguation
