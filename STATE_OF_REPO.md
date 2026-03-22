# State of the Repo — AI Fantasy Baseball Draft Tool

**As of:** 2026-03-22
**Draft:** Tuesday March 24, 2026 at 8:00 PM CDT (~46 hours from now)
**Repo:** https://github.com/tamdur/AI_fantasy_baseball

---

## What This Project Is

Building a custom draft tool for an 8-team ESPN H2H Most Categories keeper league (Magic Conch 2025, league ID 84209353). The tool will generate player valuations, track the draft in real-time, and advise on category balance.

## League Specifics

- **Format:** 8-team, H2H Most Categories, snake draft, 3 keepers per team
- **User's team:** Brohei Brotanis (team ID 10), **picks 4th overall**
- **Snake pick sequence:** 4, 13, 20, 29, 36, 45, 52, 61...
- **Hitting categories (6):** R, HR, TB, RBI, SBN (net steals), OBP
- **Pitching categories (6):** K, QS, ERA↓, WHIP↓, K/BB, SVHD (saves+holds)
- **Roster:** C, 1B, 2B, 3B, SS, 5×OF, MI, CI, UTIL, 9×P, 3×BE, 3×IL
- **60-second pick timer**

## What's Been Done

### 1. Research (`research.md`) — COMPLETE
Deep reverse-engineering of Mr. Cheatsheet's WERTH valuation spreadsheet. The full formula chain is documented:

```
Raw projections → Rate stat conversion (OBPc, ERAc, etc.)
→ Starter pool mean/stdev per category → Per-category z-scores
→ Total WERTH → Position-adjusted WERTH (with replacement level)
```

Key decisions made:
- **Use z-scores (WERTH), not SGP** — SGP is designed for roto; z-scores are better for H2H and self-calibrate from projections
- **Rate stat conversion is critical** — must convert OBP/ERA/WHIP/K-BB to "counting equivalents" that account for playing time before z-scoring
- **Position adjustment** = |replacement_level_at_position| + raw_WERTH + multi-position bonus
- **Replacement level** = (N+1)th best player at position, where N = roster_slots × 8

### 2. Data Extraction (`data/`) — COMPLETE
Full ESPN API extraction via `data/extraction_scripts/extract_all.py`:

| Dataset | File(s) | Status |
|---------|---------|--------|
| League config (categories, roster, teams, draft order) | `data/league_config.json` | ✅ |
| Draft history 2021-2025 (all picks, keeper flags, player names) | `data/drafts/draft_YYYY.json` | ✅ |
| Matchup results 2021-2025 (per-category WIN/LOSS/TIE scores) | `data/matchups/matchups_YYYY.json` | ✅ |
| Standings 2021-2025 | `data/standings/standings_YYYY.json` | ✅ |
| Current rosters 2026 (all 8 teams) | `data/rosters_2026.json` | ✅ |
| ESPN projections 2026 (1,200 players, 615 with projections) | `data/projections_2026.json` | ✅ |
| Free agents 2026 (250 players) | `data/free_agents_2026.json` | ✅ |
| Transactions | ❌ ESPN API returns 0 for baseball | N/A |

**Note:** League was 10 teams in 2021-2023, reduced to 8 in 2024.

### 3. Projection Sources (`existing-tools/`) — AVAILABLE, NOT YET MERGED
- `FanGraphs_Steamer_Batters_2026.csv` — 4,187 players, includes uncertainty quantiles (q10-q90)
- `FanGraphs_Steamer_Pitchers_2026.csv` — 5,162 players
- `FanGraphs_ATC_Batters_2026.csv` — 627 players (curated consensus blend)
- `FanGraphs_ATC_Pitchers_2026.csv` — 844 players
- `SFBB Player ID Map - PLAYERIDMAP.csv` — 3,825 players, 16+ ID systems (join path: FanGraphs `xMLBAMID` → SFBB `MLBID` → `ESPNID`)
- `2026_Roto_Draft_Cheatsheet_v1.20.xlsm` — Mr. Cheatsheet (reference, not directly used)

### 4. Project Infrastructure — COMPLETE
- `CLAUDE.md` — Project context loaded every session
- `.claude/napkin.md` — Runbook with 15 curated entries (execution rules, data gotchas, domain guardrails)
- `.claude/projects/.../memory/` — Persistent memory (league settings, valuation approach, draft position, ESPN API reference)
- `flaim_assessment.md` — Assessment of Flaim MCP (useful for roster lookups only, not analytics)

### 5. Flaim MCP — ASSESSED, LIMITED UTILITY
Connected MCP server for live ESPN data. Useful for quick roster lookups and standings, but lacks stats, projections, draft history, and category-level data. See `flaim_assessment.md`.

## What Has NOT Been Built Yet

### Must-Build for Draft Day (Priority Order)
1. **Data pipeline** — Load FanGraphs CSVs, calculate TB/SBN/SVHD, merge with ESPN projections via SFBB ID Map
2. **WERTH valuation engine** — Port Mr. Cheatsheet's z-score chain to Python (formulas documented in `research.md` §2 and §7)
3. **Pre-draft rankings** — Ranked player list with position-adjusted WERTH, ADP comparison
4. **Keeper analysis** — Value-over-cost for keeper decisions (need to determine who's being kept)
5. **Draft-day tracker** — Mark picks in real-time, update available players, surface recommendations
6. **Category balance advisor** — Track your team's category strengths/weaknesses as you draft

### Nice-to-Have
7. ADP-vs-value steal alerts
8. Opponent draft tracking (what categories they're building toward)
9. Weekly consistency bonus using Steamer quantile data
10. Historical draft tendency profiling per manager

## Key Technical Details

### ESPN API Gotchas
- **`mBoxscore`** is the ONLY view that returns per-category matchup data (`scoreByStat`). `mMatchupScore` and `mMatchup` do not, despite their names.
- `espn-api` v0.45.1 `box_scores()` is broken for baseball — use direct API calls
- Stat ID 17 = OBP (not OPS). Stat ID 16 = PA (not OBP).
- Verified stat IDs: R=20, HR=5, TB=8, RBI=21, SBN=25, OBP=17, K=48, QS=63, ERA=47, WHIP=41, K/BB=82, SVHD=83
- Auth requires SWID + espn_s2 cookies (in extraction script, not committed separately)

### Valuation Approach (from research)
- Z-score per category: `(player_stat - starter_pool_mean) / starter_pool_stdev`
- Rate stats first converted to counting equivalents (e.g., `OBPc = ((player_OBP × PA) - (league_OBP × PA)) / (avg_PA × total_slots)`)
- Position-adjusted: `|replacement_level_WERTH| + total_WERTH + 0.5 × multi_position_eligible`
- Starter pool = `roster_slots_per_position × 8 teams`

### File Structure
```
AI_fantasy_baseball/
├── CLAUDE.md                  # Project context (loaded every session)
├── SKILL.md                   # Napkin runbook skill definition
├── research.md                # Mr. Cheatsheet deep dive + valuation methodology
├── data_assessment.md         # ESPN extraction quality assessment
├── flaim_assessment.md        # Flaim MCP capabilities/limitations
├── .claude/
│   ├── napkin.md              # Live runbook (15 curated entries)
│   ├── settings.local.json    # Permissions
│   └── projects/.../memory/   # Persistent memory files
├── existing-tools/            # FanGraphs CSVs, SFBB ID Map, Mr. Cheatsheet
├── data/
│   ├── league_config.json     # 12 categories, roster, teams, draft order
│   ├── rosters_2026.json      # All 8 teams' current rosters
│   ├── projections_2026.json  # ESPN projections (615 players)
│   ├── free_agents_2026.json  # Top 250 FAs
│   ├── drafts/                # 2021-2025 draft picks with keeper flags
│   ├── matchups/              # 2021-2025 per-category matchup results
│   ├── standings/             # 2021-2025 W/L/T records
│   ├── transactions/          # Empty (API limitation)
│   └── extraction_scripts/
│       └── extract_all.py     # Re-runnable extraction script
└── .gitignore
```
