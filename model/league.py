"""
Shared league constants and ID utilities.

Used by both the pre-draft model (model/) and in-season pipeline
(in_season/daily_digest/). Single source of truth for league config.
"""

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "existing-tools"
DATA = ROOT / "data"

# ---- League Config ----

NUM_TEAMS = 8

ROSTER_SLOTS = {
    "C": 1, "1B": 1, "2B": 1, "SS": 1, "3B": 1,
    "OF": 5, "MI": 1, "CI": 1, "UTIL": 1, "P": 9,
    "BE": 3, "IL": 3,
}
HITTING_SLOTS = {k: v for k, v in ROSTER_SLOTS.items() if k not in ("P", "BE", "IL")}
PITCHING_SLOTS = {"P": ROSTER_SLOTS["P"]}

# ---- Scoring Categories ----

HITTING_CATS = ["R", "HR", "TB", "RBI", "SBN", "OBP"]
PITCHING_CATS = ["K", "QS", "ERA", "WHIP", "KBB", "SVHD"]
ALL_CATS = HITTING_CATS + PITCHING_CATS
LOWER_IS_BETTER = {"ERA", "WHIP"}  # K/BB is higher=better in this league


# ---- ID Bridge Utilities ----

def load_id_map():
    """Load SFBB Player ID Map for cross-referencing."""
    df = pd.read_csv(TOOLS / "SFBB Player ID Map - PLAYERIDMAP.csv",
                     low_memory=False)
    for col in ["MLBID", "ESPNID"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[["MLBID", "ESPNID", "PLAYERNAME", "POS", "TEAM", "IDFANGRAPHS"]].copy()
    df = df.drop_duplicates(subset=["MLBID"], keep="first")
    return df


def join_ids(fg_df, id_map):
    """Join FanGraphs data to ESPN IDs via MLBAM ID bridge."""
    merged = fg_df.merge(
        id_map[["MLBID", "ESPNID"]].dropna(subset=["MLBID"]),
        left_on="mlbam_id",
        right_on="MLBID",
        how="left",
    )
    merged = merged.rename(columns={"ESPNID": "espn_id"})
    if "MLBID" in merged.columns:
        merged = merged.drop(columns=["MLBID"])
    return merged
