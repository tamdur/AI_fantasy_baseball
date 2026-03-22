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
1. **[2026-03-22] Use `mBoxscore` API view for ESPN matchup category data — other views don't return `scoreByStat`**
   Do instead: Always use `mBoxscore` view (not `mMatchupScore` or `mMatchup`) when fetching per-category matchup results. The espn-api `box_scores()` method is broken in v0.45.1 — use direct API calls.

2. **[2026-03-22] ESPN stat IDs differ from common documentation — verified mapping exists**
   Do instead: Use the verified stat ID map: OBP=17 (not 16, which is PA), WHIP=41, ERA=47, K=48, QS=63, K/BB=82, SVHD=83, SBN=25. See `espn_api/baseball/constant.py` STATS_MAP.

3. **[2026-03-22] Join FanGraphs projections to ESPN players via MLBAM ID, not name matching**
   Do instead: FanGraphs CSVs have `xMLBAMID` → join to SFBB ID Map `MLBID` → get `ESPNID`. Name matching is fragile (Jr., accents, etc.).

4. **[2026-03-22] ATC projections are curated (627 batters, 844 pitchers); Steamer is exhaustive (4,187 / 5,162)**
   Do instead: Use ATC as primary projection source (consensus blend, MLB-relevant pool). Use Steamer's quantile data (q10-q90) for uncertainty/consistency modeling.

5. **[2026-03-22] ESPN transactions API returns 0 for all baseball years**
   Do instead: Don't waste time on transaction extraction. Infer activity from roster changes if needed.

6. **[2026-03-22] Flaim MCP lacks stats, projections, draft history, and category-level data**
   Do instead: Use Flaim only for roster lookups and basic standings. Use direct ESPN API for analytical data. Use FanGraphs CSVs for projections.

## Domain Behavior Guardrails
1. **[2026-03-22] H2H categories values consistency differently than roto**
   Do instead: Layer a consistency bonus on top of WERTH for H2H. A player producing 2 HR/week reliably is worth more than a boom-bust player with the same season total. Use Steamer quantile spreads (q90-q10) as a variance proxy.

2. **[2026-03-22] 8-team league compresses positional scarcity**
   Do instead: Dampen positional adjustment relative to 12-team defaults. With only 8 of each position drafted, even C and SS have strong replacement options. Don't overvalue scarcity.

3. **[2026-03-22] In-draft category balance matters for H2H — Mr. Cheatsheet doesn't model this**
   Do instead: Build a category gap tracker that shows "you're weak in SBN and K/BB — prioritize these" as the draft progresses. This is the biggest gap to fill.

## User Directives
1. **[2026-03-22] Files referenced in prompts may have wrong paths**
   Do instead: Check the project working directory first. Don't search the full filesystem without asking.

2. **[2026-03-22] Draft is Tuesday March 24, 2026 at 8 PM CDT**
   Do instead: Prioritize build items by draft-day utility. Data pipeline → valuation engine → rankings → draft tracker → category advisor.
