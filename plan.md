# Draft Tool Build Plan

## Phase 1: Data Pipeline
- [x] Load ATC + Steamer CSVs into DataFrames, calculate derived stats (TB, SBN, SVHD) — done, 627 hitters / 844 pitchers from ATC
- [x] Load SFBB ID Map and join FanGraphs → MLBAM ID → ESPN ID — done, deduplicated Ohtani
- [x] Load ESPN projections/rosters, merge as secondary source — done, 495 hitters / 473 pitchers matched
- [x] Produce unified player table: name, ESPN ID, FG ID, positions, team, all 12 cat stats + PA/IP — done

## Phase 2: Historical League Analysis
- [x] Category tightness analysis — QS, SVHD, HR are top swing categories
- [x] Winning archetypes — 7-5 most common split; top finishers specialize (4+ cats >60% WR)
- [x] Manager draft tendencies — Nate goes pitching heavy (R1-2), Team Q waits on pitching (R7+)
- [x] Draft pick value curve — quality cliff at round 13 (retention drops below 50%)
- [x] Keeper patterns from 2022-2023 — avg keeper round 1.9, avg rounds saved 1.2
- [x] Written to `analysis/league_history_report.md`

## Phase 3: Valuation Engine
- [x] Rate stat → counting equivalent conversion (OBPc, ERAc, WHIPc, K/BBc) — done
- [x] Starter pool identification (104 hitters, 72 pitchers: 48 SP + 24 RP) — fixed SP/RP split
- [x] Z-score per category (with negated stdev for ERA/WHIP) — done
- [x] Total WERTH = sum of per-category z-scores — done
- [x] Replacement level by position; UTIL = MAX + STDEV — done
- [x] Position-adjusted WERTH = |repl_level| + total_WERTH + 0.5 × multi-pos — done
- [x] Ohtani two-way handling — combined hit + pitch WERTH = 16.21 (rank #2)
- [x] Keeper value-over-cost analysis → `analysis/keeper_analysis.md` — Keep 3 (Ohtani/Acuña/Crochet) optimal
- [ ] Validate against Mr. Cheatsheet rankings (sanity check top 20)

## Phase 4: Draft-Day HTML Tool
- [x] Pre-compute all valuations into JSON data blob — 1470 players, 630KB
- [x] Build single-file HTML: player list, sort/filter, click-to-draft — 640KB
- [x] My team category dashboard (bar chart, live updating) — done
- [x] Marginal value column — re-ranks by weakest 4 categories — done
- [ ] ADP vs WERTH value alert badges — need ADP data source
- [x] Keeper input UI — per-team keeper entry modal — done
- [ ] Surface Phase 2 findings (swing cats, manager tendencies) — TODO

## Phase 5: Outputs & Documentation
- [x] `analysis/league_history_report.md` — complete
- [x] `analysis/keeper_analysis.md` — complete
- [x] `model/output/rankings.csv` — 1470 players exported
- [x] `draft_tool/index.html` — built
- [x] `draft_tool/README.md` — complete
- [x] `ROADMAP.md` with in-season tool placeholders — complete

## Key Design Decisions
- ATC as primary projections (curated, consensus blend)
- SP/RP starter pool split (6 SP + 3 RP per team × 8 = 48 SP + 24 RP) to avoid SVHD z-score inflation
- Ohtani: hitter row gets combined hit+pitch z-scores, pitcher row excluded from combined rankings
- Rankings: Judge #1, Ohtani #2, Soto #3, Skubal #4 (top pitcher)
- Keeper recommendation: Keep 3 (Ohtani + Acuña + Crochet) = 39.44 expected value

## Phase 6: Pre-Draft Polish (March 22-24)
- [x] Fix sort order — default to highest WERTH first (was ascending, now descending)
- [x] Keeper input autocomplete — typeahead with fuzzy matching, player chips showing team/pos/WERTH
- [x] Distribution-aware WERTH — risk-adjusted valuations using Steamer wOBA/ERA quantiles + waiver floor (E[max(X,w)])
- [x] Opponent draft tracking — collapsible panel showing each team's category profile, H/P count, strong/weak cats
- [x] Surface historical findings — swing category stars (QS/SVHD/HR) + manager tendency notes per team
- [x] ADP integration — NFBC ADP from Steamer, STEAL/REACH badges, ADP column + sort

## Remaining Work
1. Sanity-check rankings against Mr. Cheatsheet output
