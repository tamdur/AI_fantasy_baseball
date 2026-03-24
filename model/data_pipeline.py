"""
Phase 1: Data Pipeline — Load, derive, join, and merge all projection data
into a unified player table for the valuation engine.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOOLS = ROOT / "existing-tools"

# League config
NUM_TEAMS = 8
ROSTER_SLOTS = {
    "C": 1, "1B": 1, "2B": 1, "SS": 1, "3B": 1,
    "OF": 5, "MI": 1, "CI": 1, "UTIL": 1, "P": 9,
    "BE": 3, "IL": 3,
}
HITTING_SLOTS = {k: v for k, v in ROSTER_SLOTS.items() if k not in ("P", "BE", "IL")}
PITCHING_SLOTS = {"P": ROSTER_SLOTS["P"]}

# Scoring categories
HITTING_CATS = ["R", "HR", "TB", "RBI", "SBN", "OBP"]
PITCHING_CATS = ["K", "QS", "ERA", "WHIP", "KBB", "SVHD"]
ALL_CATS = HITTING_CATS + PITCHING_CATS
LOWER_IS_BETTER = {"ERA", "WHIP"}  # K/BB is higher=better in this league


def load_atc_batters():
    """Load ATC batter projections, derive TB and SBN."""
    df = pd.read_csv(TOOLS / "FanGraphs_ATC_Batters_2026.csv")
    df = df.rename(columns={"PlayerName": "name", "xMLBAMID": "mlbam_id"})
    # Derive stats
    df["TB"] = df["1B"] + 2 * df["2B"] + 3 * df["3B"] + 4 * df["HR"]
    df["SBN"] = df["SB"] - df["CS"]
    df["player_type"] = "hitter"
    df["fg_id"] = df["playerid"]
    # 'minpos' has position strings like "OF", "SS", "SS/OF"
    if "minpos" in df.columns:
        df["fg_position"] = df["minpos"]
    else:
        df["fg_position"] = ""
    return df


def load_atc_pitchers():
    """Load ATC pitcher projections, derive SVHD."""
    df = pd.read_csv(TOOLS / "FanGraphs_ATC_Pitchers_2026.csv")
    df = df.rename(columns={"PlayerName": "name", "xMLBAMID": "mlbam_id"})
    # Derive SVHD
    if "HLD" in df.columns:
        df["SVHD"] = df["SV"] + df["HLD"]
    elif "SV" in df.columns:
        df["SVHD"] = df["SV"]
    else:
        df["SVHD"] = 0
    # K is SO in FanGraphs
    df["K"] = df["SO"]
    # K/BB
    df["KBB"] = np.where(df["BB"] > 0, df["K"] / df["BB"], 0)
    df["player_type"] = "pitcher"
    df["fg_id"] = df["playerid"]
    return df


def load_steamer_batters():
    """Load Steamer batters for broader pool + quantile data."""
    df = pd.read_csv(TOOLS / "FanGraphs_Steamer_Batters_2026.csv")
    df = df.rename(columns={"PlayerName": "name", "xMLBAMID": "mlbam_id"})
    df["TB"] = df["1B"] + 2 * df["2B"] + 3 * df["3B"] + 4 * df["HR"]
    df["SBN"] = df["SB"] - df["CS"]
    df["player_type"] = "hitter"
    df["fg_id"] = df["playerid"]
    if "minpos" in df.columns:
        df["fg_position"] = df["minpos"]
    else:
        df["fg_position"] = ""
    return df


def load_steamer_pitchers():
    """Load Steamer pitchers for broader pool + quantile data."""
    df = pd.read_csv(TOOLS / "FanGraphs_Steamer_Pitchers_2026.csv")
    df = df.rename(columns={"PlayerName": "name", "xMLBAMID": "mlbam_id"})
    if "HLD" in df.columns:
        df["SVHD"] = df["SV"] + df["HLD"]
    elif "SV" in df.columns:
        df["SVHD"] = df["SV"]
    else:
        df["SVHD"] = 0
    df["K"] = df["SO"]
    df["KBB"] = np.where(df["BB"] > 0, df["K"] / df["BB"], 0)
    df["player_type"] = "pitcher"
    df["fg_id"] = df["playerid"]
    return df


def load_id_map():
    """Load SFBB Player ID Map for cross-referencing."""
    df = pd.read_csv(TOOLS / "SFBB Player ID Map - PLAYERIDMAP.csv",
                     low_memory=False)
    # Key columns: MLBID (= MLBAM ID), ESPNID, IDFANGRAPHS
    # Convert to numeric, coercing errors
    for col in ["MLBID", "ESPNID"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[["MLBID", "ESPNID", "PLAYERNAME", "POS", "TEAM", "IDFANGRAPHS"]].copy()
    # Deduplicate on MLBID (e.g., Ohtani has two rows)
    df = df.drop_duplicates(subset=["MLBID"], keep="first")
    return df


def load_espn_projections():
    """Load ESPN projections as secondary source."""
    with open(DATA / "projections_2026.json") as f:
        data = json.load(f)

    rows = []
    for p in data["players"]:
        proj = p.get("projected_2026_split0", {})
        if not proj:
            continue
        row = {
            "espn_id": p["espn_id"],
            "espn_name": p["name"],
            "espn_position": p.get("position", ""),
            "espn_eligible": p.get("eligible_positions", []),
            "espn_team": p.get("pro_team", ""),
            "ownership_pct": p.get("ownership_pct", 0),
        }
        # Batting stats
        for stat in ["PA", "AB", "R", "HR", "RBI", "SB", "CS", "OBP", "TB",
                      "H", "1B", "2B", "3B", "BB"]:
            row[f"espn_{stat}"] = proj.get(stat)
        # Pitching stats
        for stat in ["K", "QS", "ERA", "WHIP", "KBB", "SVHD", "SV", "HLD",
                      "OUTS", "GS", "W", "L", "ER", "HA", "BBA", "GP_P"]:
            row[f"espn_{stat}"] = proj.get(stat)

        rows.append(row)

    df = pd.DataFrame(rows)
    # Derive ESPN SBN and IP
    if "espn_SB" in df.columns:
        df["espn_SBN"] = df["espn_SB"].fillna(0) - df["espn_CS"].fillna(0)
    if "espn_OUTS" in df.columns:
        df["espn_IP"] = df["espn_OUTS"].fillna(0) / 3.0
    # Deduplicate — ESPN has separate hitter/pitcher rows for two-way players
    df = df.drop_duplicates(subset=["espn_id"], keep="first")
    return df


def load_rosters():
    """Load current 2026 rosters for all teams."""
    with open(DATA / "rosters_2026.json") as f:
        data = json.load(f)
    rows = []
    for team_id, team_data in data.items():
        for p in team_data["players"]:
            rows.append({
                "espn_id": p["espn_id"],
                "roster_team_id": int(team_id),
                "roster_team_name": team_data["team_name"],
                "roster_name": p["name"],
                "roster_position": p.get("position", ""),
                "roster_eligible": p.get("eligible_positions", []),
                "roster_pro_team": p.get("pro_team", ""),
                "acquisition_type": p.get("acquisition_type", ""),
            })
    return pd.DataFrame(rows)


def join_ids(fg_df, id_map):
    """Join FanGraphs data to ESPN IDs via MLBAM ID bridge."""
    # FanGraphs mlbam_id → SFBB MLBID → ESPNID
    merged = fg_df.merge(
        id_map[["MLBID", "ESPNID"]].dropna(subset=["MLBID"]),
        left_on="mlbam_id",
        right_on="MLBID",
        how="left",
    )
    merged = merged.rename(columns={"ESPNID": "espn_id"})
    # Drop the redundant MLBID column
    if "MLBID" in merged.columns:
        merged = merged.drop(columns=["MLBID"])
    return merged


def build_unified_table():
    """
    Build the unified player table combining ATC (primary), Steamer (quantiles),
    ESPN projections (cross-validation), and roster data.
    """
    print("Loading ATC projections...")
    atc_hit = load_atc_batters()
    atc_pit = load_atc_pitchers()

    print("Loading Steamer projections (for quantile data)...")
    stm_hit = load_steamer_batters()
    stm_pit = load_steamer_pitchers()

    print("Loading ID map...")
    id_map = load_id_map()

    print("Loading ESPN projections...")
    espn_proj = load_espn_projections()

    print("Loading rosters...")
    rosters = load_rosters()

    # Join ATC to ESPN IDs
    print("Joining IDs...")
    atc_hit = join_ids(atc_hit, id_map)
    atc_pit = join_ids(atc_pit, id_map)

    # Get Steamer quantile data for uncertainty modeling + ADP
    steamer_extra_cols = [c for c in stm_hit.columns if c.startswith("q") and c[1:].isdigit()]
    if "ADP" in stm_hit.columns:
        steamer_extra_cols.append("ADP")
    if steamer_extra_cols:
        stm_hit_q = stm_hit[["mlbam_id"] + steamer_extra_cols].copy()
        rename_map = {c: f"steamer_{c}" for c in steamer_extra_cols if c != "ADP"}
        rename_map["ADP"] = "adp"
        stm_hit_q = stm_hit_q.rename(columns=rename_map)
        atc_hit = atc_hit.merge(stm_hit_q, on="mlbam_id", how="left")

    steamer_extra_cols_p = [c for c in stm_pit.columns if c.startswith("q") and c[1:].isdigit()]
    if "ADP" in stm_pit.columns:
        steamer_extra_cols_p.append("ADP")
    if steamer_extra_cols_p:
        stm_pit_q = stm_pit[["mlbam_id"] + steamer_extra_cols_p].copy()
        rename_map_p = {c: f"steamer_{c}" for c in steamer_extra_cols_p if c != "ADP"}
        rename_map_p["ADP"] = "adp"
        stm_pit_q = stm_pit_q.rename(columns=rename_map_p)
        atc_pit = atc_pit.merge(stm_pit_q, on="mlbam_id", how="left")

    # Build unified hitter table
    hit_cols = ["name", "fg_id", "mlbam_id", "espn_id", "player_type", "Team",
                "fg_position", "PA", "AB",
                "R", "HR", "TB", "RBI", "SBN", "OBP",
                "H", "1B", "2B", "3B", "SB", "CS", "BB", "HBP", "SF",
                "WAR", "adp"]
    # Add quantile cols if present
    hit_q_cols = [c for c in atc_hit.columns if c.startswith("steamer_q")]
    hit_cols_avail = [c for c in hit_cols + hit_q_cols if c in atc_hit.columns]
    hitters = atc_hit[hit_cols_avail].copy()

    # Build unified pitcher table
    pit_cols = ["name", "fg_id", "mlbam_id", "espn_id", "player_type", "Team",
                "IP", "GS", "G", "K", "QS", "ERA", "WHIP", "KBB", "SVHD",
                "SV", "BB", "ER", "H", "W", "L",
                "WAR", "adp"]
    # Check what's actually in the ATC pitcher data
    if "HLD" in atc_pit.columns:
        pit_cols.append("HLD")
    pit_q_cols = [c for c in atc_pit.columns if c.startswith("steamer_q")]
    pit_cols_avail = [c for c in pit_cols + pit_q_cols if c in atc_pit.columns]
    pitchers = atc_pit[pit_cols_avail].copy()

    # Merge ESPN projections for cross-validation and filling gaps
    if "espn_id" in hitters.columns:
        hitters = hitters.merge(
            espn_proj[["espn_id", "espn_name", "espn_position", "espn_eligible",
                        "ownership_pct", "espn_PA", "espn_R", "espn_HR",
                        "espn_RBI", "espn_OBP", "espn_TB", "espn_SBN"]].dropna(subset=["espn_id"]),
            on="espn_id", how="left"
        )

    if "espn_id" in pitchers.columns:
        espn_pit_cols = ["espn_id", "espn_name", "espn_position", "espn_eligible",
                         "ownership_pct", "espn_K", "espn_QS", "espn_ERA",
                         "espn_WHIP", "espn_KBB", "espn_SVHD", "espn_IP"]
        espn_pit_avail = [c for c in espn_pit_cols if c in espn_proj.columns]
        pitchers = pitchers.merge(
            espn_proj[espn_pit_avail].dropna(subset=["espn_id"]),
            on="espn_id", how="left"
        )

    # Merge roster data (who's on which team in 2026)
    for df in [hitters, pitchers]:
        if "espn_id" in df.columns:
            df_merged = df.merge(
                rosters[["espn_id", "roster_team_id", "roster_team_name"]],
                on="espn_id", how="left"
            )
            # Update in place
            for col in ["roster_team_id", "roster_team_name"]:
                df[col] = df_merged[col]

    # Also merge position eligibility from ESPN/rosters for multi-position detection
    roster_positions = rosters.groupby("espn_id")["roster_eligible"].first().reset_index()
    for df in [hitters, pitchers]:
        if "espn_id" in df.columns:
            df_merged = df.merge(roster_positions, on="espn_id", how="left")
            df["eligible_positions"] = df_merged["roster_eligible"]

    # Fill eligible_positions from ESPN projections where missing
    if "espn_eligible" in hitters.columns:
        mask = hitters["eligible_positions"].isna() | (hitters["eligible_positions"].apply(
            lambda x: len(x) == 0 if isinstance(x, list) else True))
        hitters.loc[mask, "eligible_positions"] = hitters.loc[mask, "espn_eligible"]

    print(f"\nUnified table: {len(hitters)} hitters, {len(pitchers)} pitchers")
    print(f"Hitters with ESPN ID: {hitters['espn_id'].notna().sum()}")
    print(f"Pitchers with ESPN ID: {pitchers['espn_id'].notna().sum()}")

    return hitters, pitchers


if __name__ == "__main__":
    hitters, pitchers = build_unified_table()
    print("\n--- Top 10 Hitters by WAR ---")
    print(hitters.nlargest(10, "WAR")[["name", "Team", "PA", "R", "HR", "TB", "RBI", "SBN", "OBP", "WAR", "espn_id"]].to_string())
    print("\n--- Top 10 Pitchers by WAR ---")
    print(pitchers.nlargest(10, "WAR")[["name", "Team", "IP", "K", "QS", "ERA", "WHIP", "KBB", "SVHD", "WAR", "espn_id"]].to_string())
