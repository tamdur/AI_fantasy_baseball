# State of the Repo — AI Fantasy Baseball Draft Tool

**As of:** 2026-03-26
**Draft:** Tuesday March 24, 2026 at 8:00 PM CDT (draft has passed — tool still usable for reference/re-drafts)
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

### 2. Correlated Uncertainty Model (`model/correlated_uncertainty.py`) — COMPLETE

Replaced the earlier scalar-sigma approach with a multivariate Monte Carlo model:

- **Cross-system disagreement** across 8 projection systems (ATC, Steamer, ZiPS, THE BAT X, Depth Charts, OOPSY, OOPSYPeak, Steamer600) as the variance proxy
- **Cholesky decomposition** for correlated category draws — HR/TB/RBI at r≈0.96; OBP largely independent (r≈0.3); pitcher SVHD independent of everything
- **2000 MC simulations per player**, recentered on ATC-based pos_adj_werth
- **Truncated expectation** E[max(X, waiver_floor)] for option value — high-variance players near the waiver floor gain value
- **Differentiated waiver floors** by position — position players use 4th-best FA, pitchers use 16th-best FA
- **Outputs per player:** risk_adj_werth, draft_value, werth_sigma, q10, q90, skewness

### 3. Injury Model (`model/injury_model.py`, `model/current_injuries.py`) — COMPLETE

Two-layer injury system:

**Projection-based (structural risk):**
- PA/IP gap between Steamer600 (full-season baseline) and realistic projections encodes availability risk
- Cross-system PA/IP disagreement as additional uncertainty signal
- Irreducible floor: 8+ games for position players, 10+ for pitchers
- Outputs: `model/output/injury_risk_batters.csv`, `injury_risk_pitchers.csv`

**Current injury overlay (hand-curated):**
- 26 currently-injured players with games-missed estimates from March 24 sources
- `games_missed_total = max(projection_based, current)` — no double-counting

**Injury discount on WERTH:**
- `risk_adj_werth *= (1 - games_missed_current / 162)` — only current injuries discount WERTH, since projection-based risk is already baked into lower PA/IP → lower counting stats → lower z-scores
- `draft_value` recomputed consistently after discount
- MV formula uses `risk_adj_werth` (injury-discounted) for its base component

### 4. Draft-Day HTML Tool (`draft_tool/index.html`) — COMPLETE

Single-file, ~955KB, fully offline browser tool. Open and use — no server needed.

**Columns (left to right):**
`# | Action | Player | Team | Pos | ADP | WERTH | iW | DV | σ | MV | GM | zR | zHR | zTB | zRBI | zSBN | zOBP | zK | zQS | zERA | zWHIP | zKBB | zSVHD`

| Column | Description |
|--------|-------------|
| WERTH | Raw position-adjusted z-score valuation |
| **iW** | Injury-adjusted WERTH — discounted by current injury games missed (red when < WERTH) |
| **DV** | Draft Value — risk_adj_werth minus waiver floor (marginal value of drafting vs. waiver wire) |
| σ | Projection uncertainty from MC simulation |
| **MV** | Marginal Value — how much this player helps your weakest 4 categories |
| **GM** | Projected games missed (total) — color-coded red (30+), yellow (15+), gray |

**UI Features:**
- 1,470 ranked players with all 12 category z-scores
- Sort/filter by position, name, team, any column (including GM, iW)
- **Injury badges**: Red "IL (Xg)" chip on injured player names
- **ADP badges**: STEAL (WERTH ≥3 rounds better than ADP) / REACH (≥3 rounds worse)
- Click-to-draft marks players as taken, auto-advances pick counter
- **Category dashboard** (right sidebar): bar chart with swing category highlighting (QS★/SVHD★/HR★)
- **Marginal value**: re-ranks available players by impact on your weakest 4 categories
- **Keeper modal**: fuzzy-matching typeahead with player chips
- **Keeper persistence**: auto-saves to localStorage, survives page reloads and HTML rebuilds. Export/Import buttons for JSON file backup.
- **Opponent tracking panel**: collapsible view of each team's category profile, H/P count, strong/weak cats
- **Manager tendency notes**: historical draft patterns per team from 5-year league analysis
- **Draft log**: tracks all picks with team attribution
- Snake draft pick tracking with "YOUR PICK!" indicator
- Keyboard shortcuts: `/` or `Ctrl+F` to search, `Escape` to close modals

### 5. Historical League Analysis (`analysis/league_history_report.md`) — COMPLETE

5-year analysis of matchup data, draft patterns, and keeper history. Key findings:

| Finding | Detail | Draft Implication |
|---------|--------|-------------------|
| **Swing categories** | QS (0.60), SVHD (0.52), HR (0.47) | Marginal improvements in these flip the most matchups |
| **Typical win split** | 7-5 most common (16.7%) | Must be competitive across all 12 cats |
| **Champions specialize** | Nate (2x champ) dominates K/QS/WHIP/KBB | Counter by targeting his weak cats: R, SBN, SVHD |
| **Draft value cliff** | Round 13 — retention drops below 50% | Keepers only valuable if they'd be drafted rounds 1-12 |
| **OBP is least swingy** | 17.7% thin-margin rate | OBP advantages are durable; don't overpay for marginal OBP |

### 6. Keeper Analysis (`analysis/keeper_analysis.md`) — COMPLETE

**Recommendation: Keep all 3 — Ohtani + Acuña + Crochet**

| Scenario | Expected Value |
|----------|---------------|
| Keep 3: Ohtani, Acuña, Crochet | **39.44** |
| Keep 2: Ohtani, Acuña | 36.63 |
| Keep 1: Ohtani | 33.55 |
| Keep 0 | 31.04 |

### 7. Supporting Data & Research — COMPLETE

| Asset | Location |
|-------|----------|
| Research (WERTH formulas) | `research.md` |
| FanGraphs API guide | `fangraphs_guide.md` |
| ESPN data assessment | `data_assessment.md` |
| Flaim MCP assessment | `flaim_assessment.md` |
| Correlated uncertainty methodology | `analysis/correlated_uncertainty_methodology.md` |
| League config | `data/league_config.json` |
| Draft history 2021-2025 | `data/drafts/draft_YYYY.json` |
| Matchup results 2021-2025 | `data/matchups/matchups_YYYY.json` |
| Standings 2021-2025 | `data/standings/standings_YYYY.json` |
| Rosters 2026 | `data/rosters_2026.json` |
| ESPN projections 2026 | `data/projections_2026.json` |
| FanGraphs CSVs (23 files, 8 systems) | `existing-tools/` |
| SFBB ID Map | `existing-tools/` |
| Mr. Cheatsheet spreadsheet | `existing-tools/` |

## Known Issues / Open Work

### DV/MV Pitching Bias (Investigated, Not Yet Fixed)

DV and MV are systematically biased toward position players over pitchers. Top-50 hitters average DV=10.58 vs top-50 pitchers DV=4.83. Root causes:

| Source | DV Gap Contribution |
|--------|-------------------|
| **Waiver floor asymmetry** — PITCHER_FA_RANK=16 vs HITTER_FA_RANK=4 | +2.84 (49%) |
| **Raw z-score totals** — rate stat compression + SVHD drag on SPs | +1.86 (32%) |
| **Replacement level boost** — position scarcity inflates hitter pos_adj | +1.10 (19%) |

The waiver floor constants (4 vs 16) are heuristic, not empirical. A cowork task has been created (`plans/cowork_waiver_floor_model.md`) to build an empirical waiver floor model using historical end-of-season FanGraphs data (2022-2025) to determine what caliber of player was actually available on waivers at each position.

### Other Open Items

1. Sanity-check rankings against Mr. Cheatsheet output (top 20 comparison)
2. Waiver floor empirical model (cowork in progress — see `plans/cowork_waiver_floor_model.md`)

## File Structure

```
AI_fantasy_baseball/
├── CLAUDE.md                    # Project instructions (loaded every session)
├── STATE_OF_REPO.md             # This file
├── ROADMAP.md                   # In-season tool roadmap
├── plan.md                      # Build checklist with status
├── research.md                  # Mr. Cheatsheet WERTH deep dive
├── fangraphs_guide.md           # FanGraphs REST API documentation
├── data_assessment.md           # ESPN data extraction notes
├── flaim_assessment.md          # Flaim MCP assessment
├── SKILL.md                     # Napkin runbook skill definition
├── .claude/
│   ├── napkin.md                # Live runbook (18 entries)
│   └── projects/.../memory/     # Persistent memory
├── model/
│   ├── data_pipeline.py         # Phase 1: load, derive, join, merge projections
│   ├── valuation_engine.py      # Phase 3: WERTH z-scores, replacement level, position adj
│   ├── correlated_uncertainty.py # Phase 3b: MC correlated uncertainty + waiver floors
│   ├── injury_model.py          # Projection-based injury/games-missed estimates
│   ├── current_injuries.py      # Hand-curated current injury overlay (26 players)
│   ├── export_rankings.py       # Pipeline: valuation → MC → injury → CSV/JSON export
│   ├── build_draft_tool.py      # Generate single-file HTML with inlined data
│   ├── historical_analysis.py   # Phase 2: matchup/draft/keeper pattern analysis
│   ├── keeper_analysis.py       # Keeper value-over-cost recommendations
│   └── output/
│       ├── rankings.csv         # 1,470 players ranked (with injury data)
│       ├── draft_data.json      # JSON blob inlined into draft tool
│       ├── injury_risk_batters.csv
│       ├── injury_risk_pitchers.csv
│       ├── hitter_uncertainty.csv
│       ├── pitcher_uncertainty.csv
│       ├── batter_correlation_matrix.csv
│       └── pitcher_correlation_matrix.csv
├── draft_tool/
│   ├── index.html               # THE DRAFT TOOL — open in browser (~955KB)
│   └── README.md                # Usage instructions
├── analysis/
│   ├── league_history_report.md                # 5-year historical analysis
│   ├── keeper_analysis.md                      # Keeper recommendations
│   └── correlated_uncertainty_methodology.md   # MC model writeup
├── plans/
│   └── cowork_waiver_floor_model.md  # Prompt for empirical waiver floor cowork task
├── existing-tools/              # 23 FanGraphs CSVs, SFBB ID Map, Mr. Cheatsheet
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

If projections, injuries, or data change:

```bash
cd model

# Full pipeline: valuation → MC simulation → injury merge → injury discount → CSV/JSON export
python3 export_rankings.py

# Regenerate draft tool HTML with new data (keepers persist in browser localStorage)
python3 build_draft_tool.py

# Standalone runs (usually not needed — export_rankings.py calls these):
python3 injury_model.py          # rebuild projection-based injury estimates
python3 keeper_analysis.py       # re-run keeper value analysis
python3 historical_analysis.py   # re-run league history (only if new matchup data)
```

## Key Technical Notes

- **Python 3.12** with pandas and numpy (standard Anaconda install)
- **No external API calls at runtime** — everything is pre-computed from CSV/JSON files
- **Draft tool is pure client-side JS** — no server, no dependencies, works offline
- **Keeper persistence**: localStorage (auto) + JSON export/import (manual backup). Survives HTML rebuilds.
- **ESPN stat IDs**: R=20, HR=5, TB=8, RBI=21, SBN=25, OBP=17, K=48, QS=63, ERA=47, WHIP=41, K/BB=82, SVHD=83
- **ID join path**: FanGraphs `xMLBAMID` → SFBB `MLBID` → `ESPNID` (74% coverage overall, ~95%+ for fantasy-relevant players)
- **League size change**: 10 teams 2021-2023, 8 teams 2024-2025. Historical analysis weights recent seasons more heavily.
- **Injury discount**: only applied for `games_missed_current` (hand-curated late-breaking injuries), NOT `games_missed_proj` (already reflected in lower PA/IP projections → lower WERTH). Avoids double-counting.
