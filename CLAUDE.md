# Project: AI Fantasy Baseball Draft Tool

## Napkin Workflow (Always Active)
Every session, before doing any other work:
1. Read `.claude/napkin.md` and apply its guidance silently.
2. Curate: re-prioritize, merge duplicates, remove stale items, enforce max 10 per category.
3. During work, update the napkin whenever you learn something reusable (frequent gotchas, user directives, non-obvious tactics). Each entry must have a date and "Do instead:" line.

See `SKILL.md` for full napkin specification.

## League Context
- 8-team ESPN H2H Most Categories keeper league (League ID: 84209353)
- Team: Brohei Brotanis (team ID 10)
- Hitting: R / HR / TB / RBI / SBN / OBP
- Pitching: K / QS / ERA / WHIP / K÷BB / SVHD
- Draft: March 24, 2026 at 8 PM CDT

## Key Files
- `research.md` — Deep analysis of Mr. Cheatsheet WERTH methodology, SGP vs z-scores, projection data assessment
- `flaim_assessment.md` — Flaim MCP capabilities and limitations
- `existing-tools/` — Mr. Cheatsheet spreadsheet, FanGraphs CSVs (Steamer + ATC), SFBB Player ID Map
- `SKILL.md` — Napkin runbook skill definition

## Data Architecture
- **Projections**: FanGraphs Steamer + ATC CSVs in `existing-tools/`
- **Player ID bridge**: SFBB ID Map (join via MLBAM ID: FanGraphs `xMLBAMID` → SFBB `MLBID` → `ESPNID`)
- **Live league data**: Flaim MCP for rosters/standings; `espn-api` for stats/draft history
- **Valuation**: Z-score (WERTH) methodology ported from Mr. Cheatsheet, not SGP

## Conventions
- Python for all tooling (not Excel)
- Rate stats must be converted to counting equivalents before z-scoring
- Replacement level = (N+1)th best at position for 8-team rosters
