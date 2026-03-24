"""
Export rankings CSV and JSON data blob for the draft tool.
"""

import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path

# Add model dir to path
sys.path.insert(0, str(Path(__file__).parent))

from valuation_engine import run_valuation, HITTING_CATS, PITCHING_CATS, ALL_CATS
from risk_adjusted_werth import run_risk_adjustment
from data_pipeline import ROOT, DATA

OUTPUT = ROOT / "model" / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)


def build_combined_rankings(hitters, pitchers):
    """Build combined rankings DataFrame."""
    # Hitter columns
    h_cols = {
        "name": "name", "Team": "team", "primary_position": "position",
        "fg_id": "fg_id", "mlbam_id": "mlbam_id", "espn_id": "espn_id",
        "PA": "PA", "pos_adj_werth": "pos_adj_werth",
        "total_werth": "total_werth", "is_two_way": "is_two_way",
        "risk_adj_werth": "risk_adj_werth", "draft_value": "draft_value",
        "werth_sigma": "werth_sigma", "adp": "adp",
    }
    for cat in HITTING_CATS:
        h_cols[f"z_{cat}"] = f"z_{cat}"
    # Add pitching z-scores for two-way players
    for cat in PITCHING_CATS:
        if f"z_{cat}" in hitters.columns:
            h_cols[f"z_{cat}"] = f"z_{cat}"
    # Raw stats for display
    for stat in ["R", "HR", "TB", "RBI", "SBN", "OBP"]:
        if stat in hitters.columns:
            h_cols[stat] = stat

    h_rank = hitters[[c for c in h_cols.keys() if c in hitters.columns]].copy()
    h_rank = h_rank.rename(columns={k: v for k, v in h_cols.items() if k in h_rank.columns})
    h_rank["type"] = "H"
    h_rank["IP"] = np.nan

    # Pitcher columns
    pit_for_rank = pitchers[~pitchers["exclude_from_combined"].fillna(False).astype(bool)]
    p_cols = {
        "name": "name", "Team": "team", "pitcher_type": "position",
        "fg_id": "fg_id", "mlbam_id": "mlbam_id", "espn_id": "espn_id",
        "IP": "IP", "pos_adj_werth": "pos_adj_werth",
        "total_werth": "total_werth",
        "risk_adj_werth": "risk_adj_werth", "draft_value": "draft_value",
        "werth_sigma": "werth_sigma", "adp": "adp",
    }
    for cat in PITCHING_CATS:
        p_cols[f"z_{cat}"] = f"z_{cat}"
    for stat in ["K", "QS", "ERA", "WHIP", "KBB", "SVHD"]:
        if stat in pit_for_rank.columns:
            p_cols[stat] = stat

    p_rank = pit_for_rank[[c for c in p_cols.keys() if c in pit_for_rank.columns]].copy()
    p_rank = p_rank.rename(columns={k: v for k, v in p_cols.items() if k in p_rank.columns})
    p_rank["type"] = "P"
    p_rank["PA"] = np.nan
    p_rank["is_two_way"] = False

    combined = pd.concat([h_rank, p_rank], ignore_index=True)
    combined = combined.sort_values("pos_adj_werth", ascending=False).reset_index(drop=True)
    combined.index += 1
    combined.index.name = "rank"

    return combined


def load_roster_data():
    """Load roster and team data for the draft tool."""
    with open(DATA / "rosters_2026.json") as f:
        rosters = json.load(f)
    with open(DATA / "league_config.json") as f:
        config = json.load(f)
    return rosters, config


def export_csv(combined):
    """Export rankings as CSV."""
    csv_cols = ["name", "team", "position", "type", "pos_adj_werth", "total_werth",
                "risk_adj_werth", "draft_value", "werth_sigma", "adp",
                "espn_id", "PA", "IP"]
    for cat in ALL_CATS:
        csv_cols.append(f"z_{cat}")
    # Add raw stats
    for stat in ["R", "HR", "TB", "RBI", "SBN", "OBP", "K", "QS", "ERA", "WHIP", "KBB", "SVHD"]:
        if stat in combined.columns:
            csv_cols.append(stat)

    csv_cols = [c for c in csv_cols if c in combined.columns]
    combined[csv_cols].to_csv(OUTPUT / "rankings.csv", float_format="%.3f")
    print(f"Exported {len(combined)} players to {OUTPUT / 'rankings.csv'}")


def export_draft_tool_json(combined, rosters, config):
    """Export JSON data blob for the draft-day HTML tool."""
    players = []
    for _, row in combined.iterrows():
        player = {
            "rank": int(row.name) if hasattr(row, 'name') and isinstance(row.name, (int, np.integer)) else 0,
            "name": row["name"],
            "team": row.get("team", ""),
            "position": row.get("position", ""),
            "type": row.get("type", ""),
            "werth": round(row.get("pos_adj_werth", 0), 2),
            "total_werth": round(row.get("total_werth", 0), 2),
            "espn_id": int(row["espn_id"]) if pd.notna(row.get("espn_id")) else None,
            "is_two_way": bool(row.get("is_two_way", False)),
            "risk_adj_werth": round(row.get("risk_adj_werth", 0), 2) if pd.notna(row.get("risk_adj_werth")) else 0,
            "draft_value": round(row.get("draft_value", 0), 2) if pd.notna(row.get("draft_value")) else 0,
            "werth_sigma": round(row.get("werth_sigma", 0), 2) if pd.notna(row.get("werth_sigma")) else 0,
            "adp": round(row.get("adp", 0), 1) if pd.notna(row.get("adp")) else None,
        }
        # Z-scores
        for cat in ALL_CATS:
            col = f"z_{cat}"
            player[col] = round(row[col], 3) if col in row and pd.notna(row.get(col)) else 0
        # Raw stats
        for stat in ["PA", "IP", "R", "HR", "TB", "RBI", "SBN", "OBP",
                      "K", "QS", "ERA", "WHIP", "KBB", "SVHD"]:
            if stat in row and pd.notna(row.get(stat)):
                player[stat] = round(row[stat], 2)

        players.append(player)

    # Build team rosters
    teams = {}
    for team_id, team_data in rosters.items():
        teams[team_id] = {
            "team_id": int(team_id),
            "team_name": team_data["team_name"],
            "players": [
                {"name": p["name"], "espn_id": p["espn_id"]}
                for p in team_data["players"]
            ]
        }

    # Draft config
    draft_config = {
        "pick_order": config["draft"]["pick_order"],
        "my_team_id": 10,
        "num_teams": config["team_count"],
        "keeper_count": config["draft"]["keeper_count"],
        "teams": [
            {"team_id": t["team_id"], "team_name": t["team_name"],
             "owner": t["owner_first"]}
            for t in config["teams"]
        ],
        "scoring_categories": {
            "hitting": HITTING_CATS,
            "pitching": PITCHING_CATS,
        },
        "roster_slots": config["roster_slots"],
    }

    data_blob = {
        "players": players,
        "teams": teams,
        "draft_config": draft_config,
    }

    with open(OUTPUT / "draft_data.json", "w") as f:
        json.dump(data_blob, f, indent=None)

    print(f"Exported draft data JSON ({len(players)} players) to {OUTPUT / 'draft_data.json'}")
    return data_blob


if __name__ == "__main__":
    print("Running valuation engine...")
    hitters, pitchers, pos_repl, pit_repl = run_valuation()

    print("\nRunning risk adjustment...")
    hitters, pitchers, waiver_floors = run_risk_adjustment(hitters, pitchers, pos_repl)

    print("\nBuilding combined rankings...")
    combined = build_combined_rankings(hitters, pitchers)

    print(f"\nTotal ranked players: {len(combined)}")
    print(f"  Hitters: {(combined['type'] == 'H').sum()}")
    print(f"  Pitchers: {(combined['type'] == 'P').sum()}")

    export_csv(combined)

    rosters, config = load_roster_data()
    data_blob = export_draft_tool_json(combined, rosters, config)
