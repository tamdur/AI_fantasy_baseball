# Roadmap — AI Fantasy Baseball Tools

## Completed (Pre-Draft)
- [x] Data pipeline: FanGraphs ATC/Steamer + ESPN projections + SFBB ID merge
- [x] WERTH valuation engine: z-scores, rate stat conversion, replacement level, position adjustment
- [x] Draft-day HTML tool: player rankings, click-to-draft, category dashboard, marginal value
- [x] Keeper analysis: value-over-cost recommendations
- [x] Historical league analysis: category tightness, manager tendencies, pick value curve

## In-Season Tools (Planned)

### Daily Digest (`in_season/daily_digest/`)
- Morning report: today's starters, probable pitchers, injury updates
- Lineup optimization: who to start based on matchup opponent's weaknesses
- Streaming recommendations: pitchers with favorable matchups today

### Matchup Analyzer (`in_season/matchup_analyzer/`)
- Weekly matchup preview: projected category-by-category comparison
- Strategy recommendations: which categories to target, which to concede
- Mid-week adjustment alerts: "you're losing K by 3 — consider streaming a starter"

### Waiver Recommender (`in_season/waiver_wire/`)
- Marginal value analysis: which free agents would most improve your weakest categories
- Hot/cold detection: players outperforming/underperforming projections
- Trade value calculator: fair trade proposals based on category needs

### Standings Tracker (`in_season/standings/`)
- Playoff probability simulation
- Category balance vs league field
- Rest-of-season projection adjustments
