---
name: ESPN API Access Details
description: How to access ESPN fantasy baseball API — views, endpoints, and known limitations
type: reference
---

**League ID:** 84209353
**Team ID:** 10 (Brohei Brotanis, owner: Teddy Amdur)
**Auth:** SWID + espn_s2 cookies (stored in extraction script, not committed)

**Critical API views:**
- `mBoxscore` — ONLY view that returns per-category matchup data (`scoreByStat`)
- `mMatchupScore` / `mMatchup` — do NOT return per-category data despite their names
- `mDraftDetail` — draft picks (no player names, need separate resolution)
- `mSettings` — scoring categories, roster slots, draft order
- `kona_player_info` — player projections (use `x-fantasy-filter` header, 50 per batch)

**Known issues:**
- `box_scores()` broken in espn-api v0.45.1 (abstract class error)
- Transactions API returns 0 for all baseball years
- Player names not included in draft picks — must resolve from roster data or SFBB ID Map
- Stat ID 17 = OBP (not OPS), stat ID 16 = PA (not OBP)

**Extraction script:** `data/extraction_scripts/extract_all.py`
