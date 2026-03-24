# State of the Repo — AI Fantasy Baseball Draft Tool

**As of:** 2026-03-22 (post-build)
**Draft:** Tuesday March 24, 2026 at 8:00 PM CDT
**Repo:** https://github.com/tamdur/AI_fantasy_baseball

---

## What This Project Is

A custom draft tool for an 8-team ESPN H2H Most Categories keeper league. The tool generates player valuations using a z-score (WERTH) methodology ported from Mr. Cheatsheet, tracks the draft in real-time with category balance analysis, and advises on marginal value picks.

## League Specifics

- **Format:** 8-team, H2H Most Categories, snake draft, 3 keepers per team
- **User's team:** Brohei Brotanis (team ID 10), **picks 4th overall**
- **Snake pick sequence:** 4, 13, 20, 29, 36, 45, 52, 61, 68, 77...
- **Hitting categories (6):** R, HR, TB, RBI, SBN (net steals), OBP
- **Pitching categories (6):** K, QS, ERA↓, WHIP↓, K/BB, SVHD (saves+holds)
- **Roster:** C, 1B, 2B, 3B, SS, 5×OF, MI, CI, UTIL, 9×P, 3×BE, 3×IL
- **60-second pick timer**

## What's Built

### 1. Valuation Engine (`model/valuation_engine.py`) — COMPLETE

Full WERTH pipeline ported from Mr. Cheatsheet:

```
ATC projections (627 hitters, 844 pitchers)
→ Derived stats: TB = 1B+2×2B+3×3B+4×HR, SBN = SB-CS, SVHD = SV+HLD
→ ID join: FanGraphs xMLBAMID → SFBB MLBID → ESPN ID (495 hitters, 473 pitchers matched)
→ Starter pool: 104 hitters (by position × 8 teams) + 72 pitchers (48 SP + 24 RP)
→ Rate stat → counting equivalent conversion (OBPc, ERAc, WHIPc, KBBc)
→ Per-category z-scores (ERA/WHIP stdev negated for direction)
→ Total WERTH = sum of z-scores across 12 categories
→ Replacement level per position; UTIL = MAX(position_repls) + STDEV
→ Position-adjusted WERTH = |repl_level| + total_WERTH + 0.5 × multi-pos
→ Ohtani: hitter row gets combined hit+pitch z-scores (WERTH 16.21)
```

**Top 10 overall:** Judge (18.7), Ohtani (17.7), Soto (17.1), Skubal (15.2), Acuña (11.8), Skenes (11.7), Tucker (11.2), J-Rod (11.0), Crochet (9.9), Carroll (9.5)

Key design decisions:
- **SP/RP split in starter pool** (6 SP + 3 RP per team) to avoid SVHD z-score inflation. Without this, closers dominate all rankings because the top-72-by-WAR are all SPs with zero SVHD.
- **ATC as primary projections** (curated consensus blend, not raw Steamer)
- **Two-way player handling**: Ohtani's pitcher z-scores are added to his hitter row; pitcher row excluded from combined rankings

### 2. Draft-Day HTML Tool (`draft_tool/index.html`) — COMPLETE

Single-file, 745KB, fully offline browser tool. Open and use — no server needed.

**Features:**
- 1,470 ranked players with all 12 category z-scores
- Sort/filter by position, name, team, any category z-score
- **Sort by Draft Value** — risk-adjusted ranking accounting for projection variance and waiver floor
- **Draft Value (DV) column** — marginal value of drafting vs. relying on waiver wire at that position
- **Projection uncertainty (σ) column** — shows which players are high-variance lottery tickets
- Click-to-draft marks players as taken, auto-advances pick counter
- **Category dashboard** (right sidebar): bar chart with swing category highlighting (QS★/SVHD★/HR★)
- **Marginal value column**: re-ranks available players by how much they help your weakest 4 categories
- **Keeper autocomplete**: fuzzy-matching typeahead with player chips showing name/team/position/WERTH
- **Opponent tracking panel**: collapsible view of each team's category profile, H/P count, strong/weak cats
- **Manager tendency notes**: historical draft patterns per team from 5-year league analysis
- **Draft log**: tracks all picks with team attribution
- Snake draft pick tracking with "YOUR PICK!" indicator
- Keyboard shortcuts: `/` or `Ctrl+F` to search, `Escape` to close modals

### 3. Historical League Analysis (`analysis/league_history_report.md`) — COMPLETE

5-year analysis of matchup data, draft patterns, and keeper history. Key findings:

| Finding | Detail | Draft Implication |
|---------|--------|-------------------|
| **Swing categories** | QS (0.60), SVHD (0.52), HR (0.47) | Marginal improvements in these flip the most matchups |
| **Typical win split** | 7-5 most common (16.7%) | Must be competitive across all 12 cats |
| **Champions specialize** | Nate (2x champ) dominates K/QS/WHIP/KBB | Counter by targeting his weak cats: R, SBN, SVHD |
| **Draft value cliff** | Round 13 — retention drops below 50% | Keepers only valuable if they'd be drafted rounds 1-12 |
| **Keeper caliber** | Average keeper round 1.9 | Overwhelmingly early-round talent |
| **OBP is least swingy** | 17.7% thin-margin rate | OBP advantages are durable; don't overpay for marginal OBP |

### 4. Keeper Analysis (`analysis/keeper_analysis.md`) — COMPLETE

**Recommendation: Keep all 3 — Ohtani + Acuña + Crochet**

| Scenario | Expected Value |
|----------|---------------|
| Keep 3: Ohtani, Acuña, Crochet | **39.44** |
| Keep 2: Ohtani, Acuña | 36.63 |
| Keep 1: Ohtani | 33.55 |
| Keep 0 | 31.04 |

Each keeper costs an early-round pick. Even Crochet (WERTH 9.94) exceeds the expected value of a Round 3 pick (#20, expected WERTH 7.13).

### 5. Rankings Export (`model/output/rankings.csv`) — COMPLETE

1,470 players with: name, team, position, type, pos_adj_werth, total_werth, espn_id, PA/IP, all 12 z-scores, all 12 raw projected stats.

### 6. Supporting Data & Research — COMPLETE (unchanged)

| Asset | Location |
|-------|----------|
| Research (WERTH formulas) | `research.md` |
| ESPN data assessment | `data_assessment.md` |
| Flaim MCP assessment | `flaim_assessment.md` |
| League config | `data/league_config.json` |
| Draft history 2021-2025 | `data/drafts/draft_YYYY.json` |
| Matchup results 2021-2025 | `data/matchups/matchups_YYYY.json` |
| Standings 2021-2025 | `data/standings/standings_YYYY.json` |
| Rosters 2026 | `data/rosters_2026.json` |
| ESPN projections 2026 | `data/projections_2026.json` |
| FanGraphs CSVs (ATC + Steamer) | `existing-tools/` |
| SFBB ID Map | `existing-tools/` |
| Mr. Cheatsheet spreadsheet | `existing-tools/` |

### 2b. Risk-Adjusted WERTH Model (`model/risk_adjusted_werth.py`) — COMPLETE

Distribution-aware valuations accounting for projection variance and the waiver wire floor:
- **Waiver floor (w)**: position-specific, estimated as 4th-best FA at each position
- **WERTH variance (σ)**: derived from Steamer wOBA/ERA quantiles via regression
- **Risk-adjusted WERTH**: E[max(X, w)] — truncated normal expectation
- **Draft value**: risk_adj_WERTH minus waiver floor (marginal value of drafting vs. waiver wire)

Key insight: variance increases value near the waiver floor (late rounds → prefer high-upside lottery tickets over safe mediocrities), while barely affecting elite players.

## What's NOT Done

### Should-do before draft
1. **ADP integration** — No ADP data source integrated yet. Value alert badges (WERTH rank >> ADP rank) aren't functional. Could pull from ESPN default rankings or NFBC ADP.
2. **Sanity-check against Mr. Cheatsheet** — Rankings haven't been cross-validated against the spreadsheet's output. The math follows the same formulas, but spot-checking the top 20 would increase confidence.
3. **Other teams' keepers** — Unknown until closer to draft. The draft tool has a keeper autocomplete modal ready to accept them.

### Post-draft / in-season (see `ROADMAP.md`)
- Daily digest, matchup analyzer, waiver recommender, standings tracker
- Placeholder directories created under `in_season/`

## File Structure

```
AI_fantasy_baseball/
├── CLAUDE.md                    # Project instructions (loaded every session)
├── STATE_OF_REPO.md             # This file
├── ROADMAP.md                   # In-season tool roadmap
├── plan.md                      # Build checklist with status
├── research.md                  # Mr. Cheatsheet WERTH deep dive
├── data_assessment.md           # ESPN data extraction notes
├── flaim_assessment.md          # Flaim MCP assessment
├── SKILL.md                     # Napkin runbook skill definition
├── .claude/
│   ├── napkin.md                # Live runbook (18 entries)
│   └── projects/.../memory/     # Persistent memory
├── model/
│   ├── data_pipeline.py         # Phase 1: load, derive, join, merge projections
│   ├── valuation_engine.py      # Phase 3: WERTH z-scores, replacement level, position adj
│   ├── risk_adjusted_werth.py   # Phase 3b: distribution-aware WERTH with waiver floor
│   ├── export_rankings.py       # Export CSV + JSON for draft tool
│   ├── build_draft_tool.py      # Generate single-file HTML with inlined data
│   ├── historical_analysis.py   # Phase 2: matchup/draft/keeper pattern analysis
│   ├── keeper_analysis.py       # Keeper value-over-cost recommendations
│   └── output/
│       ├── rankings.csv         # 1,470 players ranked
│       └── draft_data.json      # JSON blob inlined into draft tool
├── draft_tool/
│   ├── index.html               # THE DRAFT TOOL — open in browser
│   └── README.md                # Usage instructions
├── analysis/
│   ├── league_history_report.md # 5-year historical analysis
│   └── keeper_analysis.md       # Keeper recommendations
├── existing-tools/              # FanGraphs CSVs, SFBB ID Map, Mr. Cheatsheet
├── data/
│   ├── league_config.json       # Categories, roster, teams, draft order
│   ├── rosters_2026.json        # All 8 teams' rosters
│   ├── projections_2026.json    # ESPN projections (615 players)
│   ├── free_agents_2026.json    # Top 250 FAs
│   ├── drafts/                  # 2021-2025 draft picks
│   ├── matchups/                # 2021-2025 per-category results
│   ├── standings/               # 2021-2025 W/L/T
│   └── extraction_scripts/      # Re-runnable ESPN extraction
└── in_season/                   # Placeholder dirs for post-draft tools
    ├── daily_digest/
    ├── matchup_analyzer/
    ├── waiver_wire/
    └── standings/
```

## How to Rebuild

If projections or data change:

```bash
cd model
python3 export_rankings.py    # re-runs valuation engine + exports CSV/JSON
python3 build_draft_tool.py   # regenerates draft_tool/index.html with new data
python3 keeper_analysis.py    # re-runs keeper value analysis
python3 historical_analysis.py # re-runs league history (only needed if new matchup data)
```

## Key Technical Notes

- **Python 3.12** with pandas and numpy (standard Anaconda install)
- **No external API calls at runtime** — everything is pre-computed from CSV/JSON files
- **Draft tool is pure client-side JS** — no server, no dependencies, works offline
- **ESPN stat IDs**: R=20, HR=5, TB=8, RBI=21, SBN=25, OBP=17, K=48, QS=63, ERA=47, WHIP=41, K/BB=82, SVHD=83
- **ID join path**: FanGraphs `xMLBAMID` → SFBB `MLBID` → `ESPNID` (74% coverage overall, ~95%+ for fantasy-relevant players)
- **League size change**: 10 teams 2021-2023, 8 teams 2024-2025. Historical analysis weights recent seasons more heavily.
