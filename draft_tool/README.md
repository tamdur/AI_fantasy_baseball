# Draft Tool — Brohei Brotanis 2026

## Quick Start

1. Open `index.html` in any browser (Chrome recommended)
2. No server needed — everything runs offline

## Before the Draft

1. Click **Keepers** button to enter each team's keepers (when known)
2. Review the WERTH rankings — sort by different categories to find value
3. Note your pick sequence: R1(#4), R2(#13), R3(#20), R4(#29), R5(#36)...

## During the Draft

### Marking Picks
- Click **Draft** next to a player to mark them as drafted
- The tool auto-advances to the next pick
- Your picks are highlighted in blue

### Finding Value
- **WERTH column**: Overall player value (higher = better)
- **MV column**: Marginal Value — how much this player helps your weakest categories
- Sort by MV when you're on the clock to find the best pick for *your team*

### Category Dashboard (right sidebar)
- Bar chart shows your team's z-score in each of the 12 categories
- Green = strong, Red = weak, Gray = neutral
- "Weakest Categories" section highlights where to focus next

### Filtering
- Search by player name or team
- Filter by position (C, 1B, 2B, SS, 3B, OF, SP, RP)
- Toggle "Hide drafted" to show/hide taken players

### Z-Score Colors
- **Gold**: Elite (z > 2.0) — this player is a difference-maker in this category
- **Green**: Above average (z > 0)
- **Red**: Below average (z < 0)

## Keyboard Shortcuts
- `Ctrl+F` or `/` — Focus search box
- `Escape` — Close modals

## Files

| File | Purpose |
|------|---------|
| `index.html` | The draft tool (open this) |
| `../model/output/rankings.csv` | Full rankings spreadsheet |
| `../analysis/keeper_analysis.md` | Keeper recommendations |
| `../analysis/league_history_report.md` | Historical league analysis |

## Rebuilding

If projections change, re-run from the project root:

```bash
cd model
python3 export_rankings.py    # regenerate rankings
python3 build_draft_tool.py   # rebuild HTML
```
