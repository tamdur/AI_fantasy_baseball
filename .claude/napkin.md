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

3. **[2026-03-22] Chrome blocks blob downloads after ~15 rapid downloads in a session**
   Do instead: Space blob downloads with 2s delays. If blocked, open a new tab or use native Export Data link. Data URI downloads also get blocked. In sandboxed VMs, HTTP fetching to fangraphs.com is blocked — must use browser JS.

4. **[2026-03-22] THE BAT X uses `Name` column (with BOM), not `PlayerName`**
   Do instead: When reading THE BAT X CSVs, handle `\ufeffName` or `Name` instead of `PlayerName`. All other systems use `PlayerName`.

5. **[2026-03-22] Use `mBoxscore` API view for ESPN matchup category data — other views don't return `scoreByStat`**
   Do instead: Always use `mBoxscore` view (not `mMatchupScore` or `mMatchup`) when fetching per-category matchup results. The espn-api `box_scores()` method is broken in v0.45.1 — use direct API calls.

6. **[2026-03-22] ESPN stat IDs differ from common documentation — verified mapping exists**
   Do instead: Use the verified stat ID map: OBP=17 (not 16, which is PA), WHIP=41, ERA=47, K=48, QS=63, K/BB=82, SVHD=83, SBN=25. See `espn_api/baseball/constant.py` STATS_MAP.

7. **[2026-03-22] Join FanGraphs projections to ESPN players via MLBAM ID, not name matching**
   Do instead: FanGraphs CSVs have `xMLBAMID` → join to SFBB ID Map `MLBID` → get `ESPNID`. Name matching is fragile (Jr., accents, etc.).

8. **[2026-03-22] ATC projections are curated (627 batters, 844 pitchers); Steamer is exhaustive (4,187 / 5,162)**
   Do instead: Use ATC as primary projection source (consensus blend, MLB-relevant pool). THE BAT X for playing time uncertainty (decimal PA/IP). Steamer quantiles (q10-q90) for performance uncertainty. ZiPS 3yr for keeper aging curves.

9. **[2026-03-22] ESPN transactions API returns 0 for all baseball years**
   Do instead: Don't waste time on transaction extraction. Infer activity from roster changes if needed.

10. **[2026-03-22] Flaim MCP lacks stats, projections, draft history, and category-level data**
   Do instead: Use Flaim only for roster lookups and basic standings. Use direct ESPN API for analytical data. Use FanGraphs CSVs for projections.

## Domain Behavior Guardrails
1. **[2026-03-22] Steamer quantiles are wOBA (batters) and ERA (pitchers), NOT per-stat quantiles**
   Do instead: The q10-q90 columns in Steamer CSVs represent wOBA quantiles for batters (q10=low/bad, q90=high/good) and ERA quantiles for pitchers (q10=high/bad, q90=low/good). To convert to WERTH sigma, regress total_werth on the performance metric across starters and multiply by (q90-q10)/2.56 × sqrt(PA_or_IP/avg). This is implemented in `model/risk_adjusted_werth.py`.

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

## User Directives
1. **[2026-03-22] Files referenced in prompts may have wrong paths**
   Do instead: Check the project working directory first. Don't search the full filesystem without asking.

2. **[2026-03-22] Draft is Tuesday March 24, 2026 at 8 PM CDT**
   Do instead: Prioritize build items by draft-day utility. Data pipeline → valuation engine → rankings → draft tracker → category advisor.
