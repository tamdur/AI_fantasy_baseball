# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each item includes date + "Do instead".

## Execution & Validation (Highest Priority)
1. **[2026-03-26] ESPN has TWO different ID numbering systems — never mix them**
   Do instead: `eligibleSlots` uses lineup slot IDs (SLOT_MAP: 0=C, 1=1B, 2=2B, 3=3B, 4=SS, 5=OF, 14=SP, 15=RP). `defaultPositionId` uses position IDs (POS_MAP: 1=SP, 2=C, 3=1B, 4=2B, 5=3B, 6=SS, 7=LF). Filter `eligibleSlots` through SLOT_MAP with `REAL_POSITION_SLOTS` filter ({0,1,2,3,4,5,14,15}).

2. **[2026-03-26] ESPN `mBoxscore` returns ALL season schedule entries, not just current matchup**
   Do instead: Always filter schedule by `status.currentMatchupPeriod` (from `mSettings`). Without this filter, iterating the schedule returns 22 entries and the last one overwrites `our_matchup` → wrong opponent.

3. **[2026-03-26] Use `data/league_schedule_2026.json` for matchup dates, not ESPN API inference**
   Do instead: The ESPN `matchupPeriods` mapping is unreliable early in season. Load `data/league_schedule_2026.json` (parsed from league schedule PDF). It has exact start/end dates, matchup lengths, and our opponent per week. Key: MP 1 = 12 days, MP 15 = 14 days, rest = 7 days.

4. **[2026-03-22] Rate stats (OBP, ERA, WHIP, K/BB) need counting-equivalent conversion before z-scoring**
   Do instead: Use Mr. Cheatsheet's marginal-team-impact formulas — convert rate stats to counting equivalents (e.g., OBPc, ERAc) that account for playing time before computing z-scores. Never z-score raw rate stats.

5. **[2026-03-22] All 12 league categories must be used in every valuation: R/HR/TB/RBI/SBN/OBP + K/QS/ERA/WHIP/K÷BB/SVHD**
   Do instead: Derive TB (1B+2×2B+3×3B+4×HR), SBN (SB-CS), and SVHD (SV+HLD) from component stats in projection data.

## Data & Infrastructure
1. **[2026-03-22] FanGraphs has undocumented REST API at `/api/projections`**
   Do instead: Use `https://www.fangraphs.com/api/projections?type={TYPE}&stats={bat|pit}&pos=all&team=0&players=0&lg=all`. Returns JSON. See `fangraphs_guide.md` for full type parameter table.

2. **[2026-03-22] FanGraphs split type params are batter-only; `&hand=` and `&season=` params don't work**
   Do instead: Use `steamer_vl_0`/`steamer_vr_0` for batter platoon splits. Pitcher splits are not available via API. For multi-year ZiPS, use `zipsp1`/`zipsp2` — NOT `&season=2027`.

3. **[2026-03-22] ESPN stat IDs differ from common documentation — verified mapping exists**
   Do instead: Use the verified stat ID map: OBP=17 (not 16, which is PA), WHIP=41, ERA=47, K=48, QS=63, K/BB=82, SVHD=83, SBN=25.

4. **[2026-03-22] Join FanGraphs projections to ESPN players via MLBAM ID, not name matching**
   Do instead: FanGraphs CSVs have `xMLBAMID` → join to SFBB ID Map `MLBID` → get `ESPNID`. Name matching is fragile (Jr., accents, etc.).

5. **[2026-03-26] FanGraphs RoS API uses `K/BB` column name, not `KBB`**
   Do instead: Check for both `K/BB` and `KBB` columns. Rename `K/BB` → `KBB` during normalization. Also, `HLD` may be missing — handle with `.get()` + fillna.

6. **[2026-03-24] FanGraphs leaderboard API returns player names with HTML anchor tags**
   Do instead: Strip HTML from the `Name` column with `re.sub(r'<[^>]+>', '', name)` when loading leaderboard data.

7. **[2026-03-26] ESPN `mRoster`/`mStandings` views don't always include full team names**
   Do instead: Fetch team names from `mTeam` view separately. In this league, `location`+`nickname` are empty but `name` field has the team name. Cache globally.

8. **[2026-03-22] Flaim MCP lacks stats, projections, draft history, and category-level data**
   Do instead: Use Flaim only for roster lookups and basic standings. Use direct ESPN API for analytical data.

## Domain Behavior Guardrails
1. **[2026-03-26] Savant regression signals need sample size gates**
   Do instead: Require ≥50 BBE for xBA/xSLG, ≥50 BF for xERA, ≥100 PA for BABIP, ≥40 IP for LOB%. In the first 2-3 weeks, most signals fail these gates — rely on projection systems instead.

2. **[2026-03-22] QS, SVHD, and HR are the top swing categories in this league**
   Do instead: Prioritize these in streaming and lineup decisions. QS has 18% tie rate and 42% thin-margin rate.

3. **[2026-03-22] Pitcher starter pool must split SP/RP to avoid SVHD z-score inflation**
   Do instead: Use 6 SP + 3 RP per team (48 SP + 24 RP total) when building the pitcher starter pool.

4. **[2026-03-24] Waiver floor uses empirical actuals-based floors from 2022-2025**
   Do instead: Use `EMPIRICAL_FLOORS_TW` dict in waiver floor analysis. The old projection-based approach inflated all DV by 6-10 points.

5. **[2026-03-23] Use correlated_uncertainty.py NOT risk_adjusted_werth.py for uncertainty modeling**
   Do instead: The correlated model uses 8 projection systems' disagreement + Cholesky decomposition. HR/TB/RBI are 0.96 correlated; OBP is largely independent (r≈0.3); pitcher SVHD is independent.

6. **[2026-03-22] 8-team league compresses positional scarcity**
   Do instead: Dampen positional adjustment relative to 12-team defaults.

## User Directives
1. **[2026-03-26] User is on MAX plan — never use Anthropic API directly**
   Do instead: Use `claude --print --model sonnet -p -` (pipe via stdin) for programmatic Claude calls. No per-token API fees.

2. **[2026-03-26] Never use `or` with pandas Series/DataFrame objects**
   Do instead: Use `if x is None: x = fallback` pattern. Python `or` calls `__bool__()` on pandas objects, raising ValueError.

3. **[2026-03-22] Files referenced in prompts may have wrong paths**
   Do instead: Check the project working directory first. Don't search the full filesystem without asking.
