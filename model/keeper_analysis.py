"""
Phase 3: Keeper value-over-cost analysis.

For each player on my roster, compute:
  keeper_value = player_WERTH - expected_WERTH_of_draft_pick_forfeited

Keepers cost early-round picks (Beginning of Draft designation).
"""

import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from valuation_engine import run_valuation, HITTING_CATS, PITCHING_CATS, ALL_CATS
from data_pipeline import ROOT, DATA

OUTPUT = ROOT / "model" / "output"
ANALYSIS = ROOT / "analysis"
ANALYSIS.mkdir(parents=True, exist_ok=True)


def estimate_draft_pick_values(combined_rankings):
    """
    Estimate the expected WERTH of each draft pick based on rankings.
    In a snake draft with 8 teams, pick N gets roughly the Nth best available player.
    Keepers remove top players from the pool, so actual pick values shift.

    For keeper cost analysis, we estimate what the Nth overall pick is worth
    if no keepers existed (pure BPA baseline).
    """
    # Sort by pos_adj_werth descending
    ranked = combined_rankings.sort_values("pos_adj_werth", ascending=False).reset_index(drop=True)

    # Expected value of pick N = WERTH of the Nth best player
    pick_values = {}
    for i in range(min(200, len(ranked))):
        pick_num = i + 1
        pick_values[pick_num] = ranked.iloc[i]["pos_adj_werth"]

    return pick_values


def get_my_pick_sequence():
    """Get my picks in a snake draft from position 4."""
    pick_order = [6, 9, 5, 10, 1, 7, 4, 3]  # team IDs
    my_team_id = 10
    num_teams = 8

    picks = []
    for pick_num in range(1, 201):  # 25 rounds × 8 teams
        round_num = (pick_num - 1) // num_teams + 1
        pos_in_round = (pick_num - 1) % num_teams
        # Snake: odd rounds forward, even rounds backward
        idx = pos_in_round if round_num % 2 == 1 else (num_teams - 1 - pos_in_round)
        if pick_order[idx] == my_team_id:
            picks.append({"pick": pick_num, "round": round_num})

    return picks


def analyze_keepers(hitters, pitchers):
    """Analyze keeper options for my team."""
    # Load my roster
    with open(DATA / "rosters_2026.json") as f:
        rosters = json.load(f)

    my_players = rosters["10"]["players"]
    my_espn_ids = {p["espn_id"] for p in my_players}

    # Find my players in the ranked data
    my_hitters = hitters[hitters["espn_id"].isin(my_espn_ids)].copy()
    my_pitchers = pitchers[pitchers["espn_id"].isin(my_espn_ids)].copy()

    # Combine for ranking
    my_h = my_hitters[["name", "Team", "primary_position", "pos_adj_werth", "total_werth", "espn_id"]].copy()
    my_h["type"] = "H"
    my_h = my_h.rename(columns={"primary_position": "position"})

    my_p = my_pitchers[~my_pitchers["exclude_from_combined"].fillna(False).astype(bool)]
    my_p = my_p[["name", "Team", "pitcher_type", "pos_adj_werth", "total_werth", "espn_id"]].copy()
    my_p["type"] = "P"
    my_p = my_p.rename(columns={"pitcher_type": "position"})

    my_combined = pd.concat([my_h, my_p], ignore_index=True)
    my_combined = my_combined.sort_values("pos_adj_werth", ascending=False)

    # Get overall rankings for all players
    all_h = hitters[["name", "pos_adj_werth"]].copy()
    all_p = pitchers[~pitchers["exclude_from_combined"].fillna(False).astype(bool)][["name", "pos_adj_werth"]].copy()
    all_combined = pd.concat([all_h, all_p], ignore_index=True)
    all_combined = all_combined.sort_values("pos_adj_werth", ascending=False).reset_index(drop=True)

    # Add overall rank
    for idx, row in my_combined.iterrows():
        rank = (all_combined["pos_adj_werth"] >= row["pos_adj_werth"]).sum()
        my_combined.loc[idx, "overall_rank"] = rank

    # Pick values
    pick_values = estimate_draft_pick_values(all_combined.rename(columns={"pos_adj_werth": "pos_adj_werth"}))

    # My pick sequence
    my_picks = get_my_pick_sequence()

    # Keeper cost: each keeper costs a pick from the beginning of the draft
    # 3 keepers = lose picks in rounds 1, 2, 3
    # 2 keepers = lose picks in rounds 1, 2 (keep round 3 pick)
    # 1 keeper = lose pick in round 1 (keep rounds 2, 3)

    print("=" * 80)
    print("KEEPER VALUE-OVER-COST ANALYSIS")
    print("=" * 80)

    print(f"\nMy roster ({len(my_combined)} players ranked):")
    print(my_combined[["name", "position", "type", "pos_adj_werth", "overall_rank"]].head(15).to_string(
        float_format=lambda x: f"{x:.2f}"
    ))

    print(f"\nMy draft picks (first 6 rounds):")
    for p in my_picks[:6]:
        val = pick_values.get(p["pick"], 0)
        print(f"  Round {p['round']}, Pick {p['pick']}: Expected WERTH = {val:.2f}")

    # Keeper scenarios
    print("\n" + "-" * 80)
    print("KEEPER SCENARIOS")
    print("-" * 80)

    top_keepers = my_combined.nlargest(5, "pos_adj_werth")

    scenarios = []

    # Scenario: Keep 0
    picks_if_0 = my_picks[:3]  # Get all 3 early picks
    total_0 = sum(pick_values.get(p["pick"], 0) for p in picks_if_0)
    scenarios.append(("Keep 0", [], total_0, picks_if_0))

    # Scenario: Keep 1 (best player)
    for _, keeper in top_keepers.iterrows():
        keeper_val = keeper["pos_adj_werth"]
        # Lose round 1 pick, keep rounds 2-3
        picks_if_1 = my_picks[1:3]
        draft_val = sum(pick_values.get(p["pick"], 0) for p in picks_if_1)
        total_1 = keeper_val + draft_val
        scenarios.append((f"Keep 1: {keeper['name']}", [keeper['name']], total_1, picks_if_1))

    # Scenario: Keep 2 (top 2)
    top2 = top_keepers.head(2)
    keeper_val_2 = top2["pos_adj_werth"].sum()
    picks_if_2 = [my_picks[2]]
    draft_val_2 = sum(pick_values.get(p["pick"], 0) for p in picks_if_2)
    total_2 = keeper_val_2 + draft_val_2
    names_2 = top2["name"].tolist()
    scenarios.append((f"Keep 2: {', '.join(names_2)}", names_2, total_2, picks_if_2))

    # Scenario: Keep 3 (top 3)
    top3 = top_keepers.head(3)
    keeper_val_3 = top3["pos_adj_werth"].sum()
    total_3 = keeper_val_3  # No draft picks in first 3 rounds
    names_3 = top3["name"].tolist()
    scenarios.append((f"Keep 3: {', '.join(names_3)}", names_3, total_3, []))

    # Sort scenarios by total value
    scenarios.sort(key=lambda x: x[2], reverse=True)

    def fmt_picks(picks):
        parts = []
        for p in picks:
            parts.append("R%d(#%d)" % (p["round"], p["pick"]))
        return ", ".join(parts)

    print()
    for name, keepers, total, picks in scenarios:
        keeper_str = "Keepers: " + ", ".join(keepers) if keepers else "No keepers"
        pick_str = "Draft picks: " + fmt_picks(picks) if picks else "No early picks"
        print(f"  {name}")
        print(f"    {keeper_str}")
        print(f"    {pick_str}")
        print(f"    Total expected value: {total:.2f}")
        print()

    # Write analysis
    best = scenarios[0]
    pick_seq = fmt_picks(my_picks[:6])

    report = "# Keeper Analysis — Brohei Brotanis 2026\n\n"
    report += "## My Draft Position\n"
    report += "- **4th overall pick** in snake draft\n"
    report += "- Pick sequence: %s\n\n" % pick_seq
    report += "## My Roster Ranked by WERTH\n\n"
    report += "| Rank | Player | Pos | WERTH | Overall Rank |\n"
    report += "|------|--------|-----|-------|--------------|\n"

    for _, row in my_combined.head(10).iterrows():
        orank = int(row.get("overall_rank", 0))
        report += "| %d | %s | %s | %.2f | #%d |\n" % (
            orank, row["name"], row["position"], row["pos_adj_werth"], orank
        )

    report += "\n## Draft Pick Expected Values\n\n"
    report += "| Round | Pick # | Expected WERTH |\n"
    report += "|-------|--------|----------------|\n"

    for p in my_picks[:6]:
        val = pick_values.get(p["pick"], 0)
        report += "| %d | %d | %.2f |\n" % (p["round"], p["pick"], val)

    report += "\n## Keeper Scenarios (ranked by total expected value)\n\n"

    for name, keepers, total, picks in scenarios:
        keeper_str = ", ".join(keepers) if keepers else "None"
        pick_str = fmt_picks(picks) if picks else "None"
        report += "### %s\n" % name
        report += "- **Keepers:** %s\n" % keeper_str
        report += "- **Available draft picks:** %s\n" % pick_str
        report += "- **Total expected value:** %.2f\n\n" % total

    ohtani_mask = my_combined["name"].str.contains("Ohtani", na=False)
    ohtani_werth = my_combined.loc[ohtani_mask, "pos_adj_werth"].values[0] if ohtani_mask.any() else 0
    r1_pick_val = pick_values.get(my_picks[0]["pick"], 0)

    report += "## Recommendation\n\n"
    report += "**%s** produces the highest total expected value (%.2f).\n\n" % (best[0], best[2])
    report += "Key considerations:\n"
    report += "- Ohtani is a lock keeper — his two-way value (WERTH %.2f) far exceeds any draft pick value\n" % ohtani_werth
    report += "- The keeper cost is a round 1-3 pick. With pick 4 overall, round 1 gives you access to a top-4 player (expected WERTH ~%.2f)\n" % r1_pick_val
    report += "- Keep players whose WERTH exceeds the pick they cost. If your 2nd/3rd best keepers are below the expected pick value, take the pick instead.\n\n"
    report += "## Other Teams' Keepers\n\n"
    report += "Enter other teams' keepers in the draft tool when known. This will:\n"
    report += "1. Remove those players from the draft pool\n"
    report += "2. Shift expected pick values (better players available)\n"
    report += "3. Update your marginal value calculations\n"

    with open(ANALYSIS / "keeper_analysis.md", "w") as f:
        f.write(report)

    print(f"\nKeeper analysis written to {ANALYSIS / 'keeper_analysis.md'}")
    return scenarios


if __name__ == "__main__":
    hitters, pitchers, pos_repl, pit_repl = run_valuation()
    scenarios = analyze_keepers(hitters, pitchers)
