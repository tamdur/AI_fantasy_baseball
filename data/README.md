# Data Directory

ESPN Fantasy Baseball data extracted for Magic Conch 2025 (League ID: 84209353).

## Files

| File | Description |
|------|-------------|
| `league_config.json` | Scoring categories (12), roster slots, draft settings, team list with owners |
| `rosters_2026.json` | Current rosters for all 8 teams (pre-draft) |
| `projections_2026.json` | ESPN projections for 1,200 players (615 with projections) |
| `free_agents_2026.json` | Top 250 free agents |
| `drafts/draft_YYYY.json` | Draft picks 2021-2025 with player names, keeper flags, team assignments |
| `matchups/matchups_YYYY.json` | Weekly matchup results 2021-2025 with per-category scores and WIN/LOSS results |
| `standings/standings_YYYY.json` | Season standings 2021-2025 with W/L/T records |
| `transactions/transaction_summary.json` | Transaction data (empty — ESPN API limitation) |

## Extraction

Run `extraction_scripts/extract_all.py` to re-extract. Requires `espn-api` package and valid ESPN cookies (SWID + espn_s2).

**API view used for matchups**: `mBoxscore` (not `mMatchupScore`) — this is the only view that returns per-category `scoreByStat` data.

## Key Notes

- **2021-2023 had 10 teams**, league reduced to **8 teams in 2024**
- **Keeper data**: 2022 had 20 keepers, 2023 had 17. 2021/2024/2025 show 0 keepers (may be a flag issue or different keeper rules those years)
- **Draft pick counts**: 250 picks in 2021-2023 (10 teams × 25 rounds), 200 picks in 2024-2025 (8 teams × 25 rounds)
- **Your 2026 draft position**: 4th pick (team ID 10 is 4th in snake order [6, 9, 5, 10, 1, 7, 4, 3])
- **Transactions**: ESPN API returns 0 for all years — known limitation for baseball
