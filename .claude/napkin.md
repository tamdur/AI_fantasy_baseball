# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each item includes date + "Do instead".

## Execution & Validation (Highest Priority)
1. **[2026-03-22] Rate stats (OBP, ERA, WHIP, K/BB) need counting-equivalent conversion before z-scoring**
   Do instead: Use Mr. Cheatsheet's marginal-team-impact formulas — convert rate stats to counting equivalents (e.g., OBPc, ERAc) that account for playing time before computing z-scores. Never z-score raw rate stats.

2. **[2026-03-22] All 12 league categories must be used in every valuation: R/HR/TB/RBI/SBN/OBP + K/QS/ERA/WHIP/K÷BB/SVHD**
   Do instead: Derive TB (1B+2×2B+3×3B+4×HR), SBN (SB-CS), and SVHD (SV+HLD) from component stats in projection data. These are not direct columns in FanGraphs CSVs.

3. **[2026-03-22] Replacement level must be calculated for 8 teams, not 12**
   Do instead: Use `roster_slots × 8` to define the starter pool per position. The (N+1)th best player at each position is replacement level. Fewer teams = higher replacement level = compressed value gaps.

4. **[2026-03-22] Z-scores (WERTH), not SGP, for H2H categories valuation**
   Do instead: Port Mr. Cheatsheet's z-score chain to Python. SGP requires roto standings history and doesn't fit H2H. Z-scores self-calibrate from projections alone.

## Data & Infrastructure
1. **[2026-03-22] FanGraphs has undocumented REST API at `/api/projections`**
   Do instead: Use `https://www.fangraphs.com/api/projections?type={TYPE}&stats={bat|pit}&pos=all&team=0&players=0&lg=all`. Returns JSON. See `fangraphs_guide.md` for full type parameter table. Key types: `steamer`, `atc`, `thebatx`, `zipsp1` (3yr 2027), `zipsp2` (3yr 2028), `steamer_vl_0` (batter splits vs LHP), `steamer_vr_0` (batter splits vs RHP).

2. **[2026-03-22] FanGraphs split type params are batter-only; `&hand=` and `&season=` params don't work**
   Do instead: Use `steamer_vl_0`/`steamer_vr_0` for batter platoon splits. These ALWAYS return batter data even with `stats=pit`. Pitcher splits are not available via API. For multi-year ZiPS, use `zipsp1`/`zipsp2` — NOT `&season=2027`.

3. **[2026-03-22] THE BAT X uses `Name` column (with BOM), not `PlayerName`**
   Do instead: When reading THE BAT X CSVs, handle `\ufeffName` or `Name` instead of `PlayerName`. All other systems use `PlayerName`.

5. **[2026-03-26] ESPN has TWO different ID numbering systems — `eligibleSlots` uses SLOT_MAP, `defaultPositionId` uses POS_MAP**
   Do instead: `eligibleSlots` array uses lineup slot IDs (SLOT_MAP: 0=C, 1=1B, 2=2B, 3=3B, 4=SS, 5=OF, 14=SP, 15=RP). `defaultPositionId` uses position IDs (POS_MAP: 1=SP, 2=C, 3=1B, 4=2B, 5=3B, 6=SS, 7=LF). Never mix them. Filter `eligibleSlots` through SLOT_MAP with real-position-only filter ({0,1,2,3,4,5,14,15}).

6. **[2026-03-26] ESPN `mBoxscore` returns ALL season schedule entries, not just current matchup**
   Do instead: Always filter schedule by `status.currentMatchupPeriod` (from `mSettings`). Without this filter, iterating the schedule returns 22 entries and the last one overwrites `our_matchup` → wrong opponent. The `scoringPeriodId` (daily) ≠ `matchupPeriodId` (weekly).

7. **[2026-03-26] Use `data/league_schedule_2026.json` for matchup dates, not ESPN API inference**
   Do instead: The ESPN `matchupPeriods` mapping is unreliable early in season. Instead, load `data/league_schedule_2026.json` (parsed from league schedule PDF). It has exact start/end dates, matchup lengths, and our opponent per week. Key non-standard matchups: MP 1 = 12 days (Opening Week), MP 15 = 14 days (All-Star break). Source PDF stored at `data/league_schedule_2026.pdf`.

8. **[2026-03-22] ESPN stat IDs differ from common documentation — verified mapping exists**
   Do instead: Use the verified stat ID map: OBP=17 (not 16, which is PA), WHIP=41, ERA=47, K=48, QS=63, K/BB=82, SVHD=83, SBN=25. See `espn_api/baseball/constant.py` STATS_MAP.

9. **[2026-03-22] Join FanGraphs projections to ESPN players via MLBAM ID, not name matching**
   Do instead: FanGraphs CSVs have `xMLBAMID` → join to SFBB ID Map `MLBID` → get `ESPNID`. Name matching is fragile (Jr., accents, etc.).

10. **[2026-03-22] Flaim MCP lacks stats, projections, draft history, and category-level data**
   Do instead: Use Flaim only for roster lookups and basic standings. Use direct ESPN API for analytical data. Use FanGraphs CSVs for projections.

## Domain Behavior Guardrails
1. **[2026-03-23] Use correlated_uncertainty.py NOT risk_adjusted_werth.py for uncertainty modeling**
   Do instead: The new correlated model in `model/correlated_uncertainty.py` uses 8 projection systems' disagreement + Cholesky decomposition to simulate correlated category outcomes. It replaces the old scalar-sigma approach. Key: HR/TB/RBI are 0.96 correlated; OBP is largely independent (r≈0.3); pitcher SVHD is independent of all other categories. Cross-system disagreement underestimates true variance by ~50% — use ATC InterSD/IntraSD inflation. Steamer quantiles (q10-q90) are still useful as an input but not the primary uncertainty source.

2. **[2026-03-22] 8-team league compresses positional scarcity**
   Do instead: Dampen positional adjustment relative to 12-team defaults. With only 8 of each position drafted, even C and SS have strong replacement options. Don't overvalue scarcity.

3. **[2026-03-22] In-draft category balance matters for H2H — Mr. Cheatsheet doesn't model this**
   Do instead: Build a category gap tracker that shows "you're weak in SBN and K/BB — prioritize these" as the draft progresses. This is the biggest gap to fill.

4. **[2026-03-22] QS, SVHD, and HR are the top swing categories in this league**
   Do instead: Prioritize these in draft strategy and category gap tracker. QS has 18% tie rate and 42% thin-margin rate. Adding one QS or SVHD per week flips more matchups than any other category improvement.

5. **[2026-03-22] Draft value cliff at round 13; keepers averaged round 1.9**
   Do instead: Keeper value is highest for players projected in rounds 1-12. After round 13, year-over-year retention drops below 50% — those players are replacement-level in an 8-team league.

6. **[2026-03-22] Latte Nate (2x champ) wins via pitching dominance, not hitting**
   Do instead: Note that the league's most successful manager drafts 44-48% pitchers and takes SP in round 1-2. Pitching categories (K, QS, WHIP, KBB) are where Nate dominates. Counter by also investing in pitching early or targeting his weak categories (R, SBN, SVHD).

7. **[2026-03-22] Pitcher starter pool must split SP/RP to avoid SVHD z-score inflation**
   Do instead: Use 6 SP + 3 RP per team (48 SP + 24 RP total) when building the pitcher starter pool. If you use top-72-by-WAR, you get all SPs, and SVHD z-scores explode to 150+ because the mean SVHD is near zero.

8. **[2026-03-24] Waiver floor had two bugs: wrong ranks AND wrong methodology (projections vs actuals)**
   Do instead: Use empirical actuals-based floors from 2022-2025 FanGraphs end-of-season stats × league draft history. Rank = 4 pickups × slot_count (C/1B/2B/3B/SS=4, OF=20, SP=20, RP=16). Store as total_werth constants in `EMPIRICAL_FLOORS_TW` dict, convert to pos_adj_werth at runtime via `|repl_level| + floor_tw`. The old projection-based approach inflated all DV by 6-10 points because undrafted players' projections (~-8 tw) are far worse than what actually becomes available on waivers (~-3 tw). See `model/waiver_floor_analysis.py`.

9. **[2026-03-24] FanGraphs leaderboard API returns player names with HTML anchor tags**
   Do instead: Strip HTML from the `Name` column with `re.sub(r'<[^>]+>', '', name)` when loading leaderboard data. The API wraps names in `<a href="statss.aspx?playerid=...">` tags.

## User Directives
1. **[2026-03-22] Files referenced in prompts may have wrong paths**
   Do instead: Check the project working directory first. Don't search the full filesystem without asking.

2. **[2026-03-22] Draft is Tuesday March 24, 2026 at 8 PM CDT**
   Do instead: Prioritize build items by draft-day utility. Data pipeline → valuation engine → rankings → draft tracker → category advisor.

3. **[2026-03-26] User is on MAX plan — never use Anthropic API directly**
   Do instead: Use `claude --print --model sonnet -p -` (pipe via stdin) for programmatic Claude calls. No per-token API fees. The `anthropic` Python SDK is NOT needed.

4. **[2026-03-26] Never use `or` with pandas Series/DataFrame objects**
   Do instead: Use `if x is None: x = fallback` pattern. Python `or` evaluates truthiness which calls `__bool__()` on pandas objects, raising ValueError.

5. **[2026-03-26] FanGraphs RoS API uses `K/BB` column name, not `KBB`**
   Do instead: Check for both `K/BB` and `KBB` columns. Rename `K/BB` → `KBB` during normalization. Also, `HLD` may be missing from pitcher data — handle with `.get()` + fillna.

6. **[2026-03-26] ESPN `mRoster`/`mStandings` views don't always include full team names**
   Do instead: Fetch team names from `mTeam` view separately, cache globally, use as fallback when `location + nickname` is empty.
