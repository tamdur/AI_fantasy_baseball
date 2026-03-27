"""
Waiver Floor Analysis — Empirical model using 2022-2025 historical data.

Uses end-of-season FanGraphs stats + this league's draft history to determine
what caliber of player was actually available on waivers at each position,
measured in the WERTH framework.

Replaces the arbitrary HITTER_FA_RANK=4 / PITCHER_FA_RANK=16 heuristic in
correlated_uncertainty.py with empirically derived values.
"""

import pandas as pd
import numpy as np
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HIST = DATA / "historical_stats"
DRAFTS = DATA / "drafts"
TOOLS = ROOT / "existing-tools"

# ============================================================
# League constants (must match data_pipeline.py / valuation_engine.py)
# ============================================================
NUM_TEAMS = 8
ROSTER_SLOTS = {
    "C": 1, "1B": 1, "2B": 1, "SS": 1, "3B": 1,
    "OF": 5, "MI": 1, "CI": 1, "UTIL": 1, "P": 9,
    "BE": 3, "IL": 3,
}
HITTING_ROSTER = {k: v for k, v in ROSTER_SLOTS.items()
                  if k not in ("P", "BE", "IL")}
HITTING_CATS = ["R", "HR", "TB", "RBI", "SBN", "OBP"]
PITCHING_CATS = ["K", "QS", "ERA", "WHIP", "KBB", "SVHD"]
LOWER_IS_BETTER = {"ERA", "WHIP"}
SP_PER_TEAM = 6
RP_PER_TEAM = 3

POSITION_MAP = {
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
    "OF": "OF", "LF": "OF", "CF": "OF", "RF": "OF", "DH": "UTIL",
}

YEARS = [2022, 2023, 2024, 2025]
FA_RANKS_TO_TEST = [1, 2, 4, 8, 16]


# ============================================================
# Step 1: Load historical stats
# ============================================================

def strip_html(s):
    """Remove HTML tags from FanGraphs player name strings."""
    if pd.isna(s):
        return s
    return re.sub(r'<[^>]+>', '', str(s))


def load_historical_batters(year):
    """Load FanGraphs end-of-season batting leaderboard."""
    df = pd.read_csv(HIST / f"fg_bat_{year}.csv")
    df["Name"] = df["Name"].apply(strip_html)
    # Derive league categories
    df["TB"] = df["1B"] + 2 * df["2B"] + 3 * df["3B"] + 4 * df["HR"]
    df["SBN"] = df["SB"] - df["CS"]
    df["season"] = year
    return df


def load_historical_pitchers(year):
    """Load FanGraphs end-of-season pitching leaderboard."""
    df = pd.read_csv(HIST / f"fg_pit_{year}.csv")
    df["Name"] = df["Name"].apply(strip_html)
    # Derive league categories
    df["K"] = df["SO"]
    df["KBB"] = df["K/BB"].fillna(0)
    if "HLD" in df.columns:
        df["SVHD"] = df["SV"].fillna(0) + df["HLD"].fillna(0)
    else:
        df["SVHD"] = df["SV"].fillna(0)
    df["season"] = year
    # Classify SP vs RP
    gs_ratio = df["GS"] / df["G"].replace(0, np.nan)
    df["pitcher_type"] = np.where(gs_ratio.fillna(0) >= 0.5, "SP", "RP")
    return df


# ============================================================
# Step 2: Assign positions (batters)
# ============================================================

def load_id_map():
    """Load SFBB Player ID Map for ESPN ID -> MLBAM ID bridging."""
    idmap = pd.read_csv(TOOLS / "SFBB Player ID Map - PLAYERIDMAP.csv")
    # Create ESPN -> MLBAM lookup
    valid = idmap[idmap["ESPNID"].notna() & idmap["MLBID"].notna()]
    return dict(zip(valid["ESPNID"].astype(int), valid["MLBID"].astype(int)))


def assign_positions_from_fangraphs(batters):
    """
    FanGraphs leaderboard doesn't have minpos. We need a position proxy.
    Use the player's primary position from their FanGraphs data.
    The leaderboard API doesn't return position directly, so we'll use
    a heuristic based on fetching with position filters, or fall back to
    position from our draft data.

    Since we don't have minpos in the leaderboard API, we'll use a
    roster-depth approach that doesn't require position assignment for
    the waiver floor computation — just filter by total WERTH.

    However, for position-specific floors we DO need positions. Let's
    try using the FanGraphs position-filtered API data we already have,
    or assign positions based on the player's defensive stats.

    APPROACH: We'll fetch position data from FanGraphs by making
    position-specific API calls. But since we already have the data,
    let's use a simpler approach: assign positions based on where
    players accumulated the most games.

    For the historical analysis, we'll use a SIMPLIFIED position assignment:
    - We have draft data with positions (player_position field)
    - For undrafted players, we'll need the FanGraphs fielding data

    SIMPLIFICATION: Since we're computing waiver floors, the key question
    is "what WERTH was available at each position on waivers?" We can
    fetch position-specific leaderboards from FanGraphs. But for now,
    let's use the draft position data + a broader position assignment.
    """
    # We'll handle this in the main pipeline using position-specific fetches
    pass


# ============================================================
# Step 2b: Get position data from FanGraphs position-filtered leaderboards
# ============================================================

def load_position_map_from_drafts():
    """
    Build a player_name -> position map from all draft data.
    This covers drafted players. For undrafted players, we'll need
    another source.
    """
    pos_map = {}  # espn_player_id -> position
    name_pos_map = {}  # player_name -> position
    for year in YEARS:
        path = DRAFTS / f"draft_{year}.json"
        if path.exists():
            d = json.load(open(path))
            for pick in d.get("picks", []):
                pid = pick.get("player_id")
                name = pick.get("player_name", "")
                pos = pick.get("player_position", "")
                if pid:
                    pos_map[pid] = pos
                if name:
                    name_pos_map[name.strip()] = pos
    return pos_map, name_pos_map


# ============================================================
# Step 3: WERTH computation (mirrors valuation_engine.py)
# ============================================================

def compute_werth_historical(batters, pitchers):
    """
    Compute WERTH for a single historical season.
    Follows the same methodology as valuation_engine.py:
    1. Identify starter pool
    2. Convert rate stats to counting equivalents
    3. Compute z-scores
    4. Compute replacement levels
    5. Position-adjusted WERTH
    """
    batters = batters.copy()
    pitchers = pitchers.copy()

    # --- Filter to meaningful players ---
    batters = batters[batters["PA"] >= 1].copy()
    pitchers = pitchers[pitchers["IP"] >= 0.1].copy()

    # --- Identify starter pool ---
    # Hitters: top 104 by PA (13 slots × 8 teams)
    total_hitting_starters = sum(HITTING_ROSTER.values()) * NUM_TEAMS  # 104
    batters = batters.sort_values("PA", ascending=False).reset_index(drop=True)
    batters["is_starter"] = False
    batters.loc[batters.index[:total_hitting_starters], "is_starter"] = True

    # Pitchers: 48 SP + 24 RP
    n_sp = SP_PER_TEAM * NUM_TEAMS  # 48
    n_rp = RP_PER_TEAM * NUM_TEAMS  # 24

    pitchers = pitchers.copy()
    pitchers["is_starter"] = False

    sp_mask = pitchers["pitcher_type"] == "SP"
    rp_mask = pitchers["pitcher_type"] == "RP"

    sp_sorted = pitchers[sp_mask].sort_values("IP", ascending=False)
    pitchers.loc[sp_sorted.index[:n_sp], "is_starter"] = True

    # RP: rank by SVHD + 0.5*K (same as valuation_engine.py)
    pitchers.loc[rp_mask, "_rp_rank"] = (
        pitchers.loc[rp_mask, "SVHD"].fillna(0) +
        pitchers.loc[rp_mask, "K"].fillna(0) * 0.5
    )
    rp_sorted = pitchers[rp_mask].sort_values("_rp_rank", ascending=False)
    pitchers.loc[rp_sorted.index[:n_rp], "is_starter"] = True

    # --- Convert rate stats ---
    starters_h = batters[batters["is_starter"]]
    league_obp = (starters_h["OBP"] * starters_h["PA"]).sum() / starters_h["PA"].sum()
    avg_starter_pa = starters_h["PA"].mean()
    total_hitting_slots = total_hitting_starters

    batters["OBPc"] = (
        (batters["OBP"].fillna(league_obp) * batters["PA"].fillna(0)) -
        (league_obp * batters["PA"].fillna(0))
    ) / (avg_starter_pa * total_hitting_slots)

    starters_p = pitchers[pitchers["is_starter"]]
    total_league_ip = starters_p["IP"].sum()
    league_era = (starters_p["ERA"] * starters_p["IP"]).sum() / total_league_ip
    league_whip = (starters_p["WHIP"] * starters_p["IP"]).sum() / total_league_ip
    league_kbb = (starters_p["KBB"] * starters_p["IP"]).sum() / total_league_ip

    ip = pitchers["IP"].fillna(0)
    ip_share = ip / total_league_ip

    pitchers["ERAc"] = (
        ip_share * pitchers["ERA"].fillna(league_era) +
        (1 - ip_share) * league_era
    ) - league_era

    pitchers["WHIPc"] = (
        ip_share * pitchers["WHIP"].fillna(league_whip) +
        (1 - ip_share) * league_whip
    ) - league_whip

    pitchers["KBBc"] = (
        ip_share * pitchers["KBB"].fillna(league_kbb) +
        (1 - ip_share) * league_kbb
    ) - league_kbb

    # --- Z-scores ---
    # Hitting
    for cat in HITTING_CATS:
        stat_col = "OBPc" if cat == "OBP" else cat
        values = starters_h[stat_col] if stat_col in starters_h.columns else batters.loc[starters_h.index, stat_col]
        # Recompute from updated batters df for OBPc
        if stat_col == "OBPc":
            values = batters.loc[batters["is_starter"], "OBPc"]
        mean = values.mean()
        std = values.std()
        if cat in LOWER_IS_BETTER:
            std = -std
        if abs(std) < 1e-10:
            batters[f"z_{cat}"] = 0.0
        else:
            batters[f"z_{cat}"] = (batters[stat_col].fillna(mean) - mean) / std

    # Pitching
    for cat in PITCHING_CATS:
        if cat == "ERA":
            stat_col = "ERAc"
        elif cat == "WHIP":
            stat_col = "WHIPc"
        elif cat == "KBB":
            stat_col = "KBBc"
        else:
            stat_col = cat

        values = pitchers.loc[pitchers["is_starter"], stat_col]
        mean = values.mean()
        std = values.std()
        if cat in LOWER_IS_BETTER:
            std = -std
        if abs(std) < 1e-10:
            pitchers[f"z_{cat}"] = 0.0
        else:
            pitchers[f"z_{cat}"] = (pitchers[stat_col].fillna(mean) - mean) / std

    # Total WERTH
    hit_z_cols = [f"z_{cat}" for cat in HITTING_CATS]
    pit_z_cols = [f"z_{cat}" for cat in PITCHING_CATS]

    batters["total_werth"] = batters[hit_z_cols].sum(axis=1)
    pitchers["total_werth"] = pitchers[pit_z_cols].sum(axis=1)

    # --- Replacement level ---
    # We don't need position-adjusted WERTH for the waiver floor analysis
    # since we're comparing total_werth across positions. But let's compute
    # a simplified version for consistency.

    # For hitters, replacement = (N*8+1)th best by total_werth at that position
    # Since we don't have fine positions from FanGraphs leaderboard,
    # we'll use total_werth directly and compute floors by pitcher_type only.

    # Pitcher replacement by type
    sp_sorted_werth = pitchers[sp_mask].sort_values("total_werth", ascending=False)
    rp_sorted_werth = pitchers[rp_mask].sort_values("total_werth", ascending=False)

    sp_repl = sp_sorted_werth.iloc[n_sp]["total_werth"] if len(sp_sorted_werth) > n_sp else 0
    rp_repl = rp_sorted_werth.iloc[n_rp]["total_werth"] if len(rp_sorted_werth) > n_rp else 0

    return batters, pitchers


# ============================================================
# Step 4: Identify who was on waivers
# ============================================================

def load_drafted_mlbam_ids(year):
    """
    Get the set of MLBAM IDs for players drafted in a given year.
    Uses ESPN player IDs from draft data, bridged via SFBB ID Map.
    """
    espn_to_mlbam = load_id_map()

    path = DRAFTS / f"draft_{year}.json"
    if not path.exists():
        return set()

    d = json.load(open(path))
    drafted_mlbam = set()
    unmatched = []
    for pick in d.get("picks", []):
        espn_id = pick.get("player_id")
        if espn_id and espn_id in espn_to_mlbam:
            drafted_mlbam.add(espn_to_mlbam[espn_id])
        elif espn_id:
            unmatched.append(pick.get("player_name", f"ID:{espn_id}"))

    return drafted_mlbam


def identify_waiver_players(df, drafted_mlbam_ids, player_type="hitter"):
    """
    Mark players as 'drafted' or 'waiver available' based on whether their
    MLBAM ID appears in the draft data.

    Players not in the draft = undrafted = available on waivers at some point.
    """
    df = df.copy()
    df["was_drafted"] = df["xMLBAMID"].isin(drafted_mlbam_ids)
    df["is_waiver"] = ~df["was_drafted"]
    return df


# ============================================================
# Step 5: Compute waiver floors
# ============================================================

def compute_waiver_floors_by_position(batters_all, pitchers_all):
    """
    For each season and position, compute the Nth-best waiver player's WERTH
    at various values of N.

    Since FanGraphs leaderboard API doesn't include position data,
    we use two approaches:
    1. For PITCHERS: we have pitcher_type (SP/RP) from GS/G ratio — clean split.
    2. For HITTERS: we use a single "hitter" pool, since the current code's
       waiver floor also falls back to a single hitter floor for flex positions.
       We also attempt position-specific floors using draft position data.

    Returns a dict of results.
    """
    results = []

    for year in YEARS:
        bat = batters_all[batters_all["season"] == year].copy()
        pit = pitchers_all[pitchers_all["season"] == year].copy()

        # --- Hitter waiver floor (aggregate) ---
        # Minimum PA filter: only count players who actually produced something
        bat_meaningful = bat[bat["PA"] >= 50].copy()
        waiver_hitters = bat_meaningful[bat_meaningful["is_waiver"]].sort_values(
            "total_werth", ascending=False
        ).reset_index(drop=True)

        for rank in FA_RANKS_TO_TEST:
            if len(waiver_hitters) >= rank:
                werth = waiver_hitters.iloc[rank - 1]["total_werth"]
                name = waiver_hitters.iloc[rank - 1]["Name"]
                pa = waiver_hitters.iloc[rank - 1]["PA"]
            else:
                werth = np.nan
                name = ""
                pa = 0
            results.append({
                "year": year, "position": "ALL_HIT", "fa_rank": rank,
                "werth": werth, "player_name": name, "pa_ip": pa,
                "pool_size": len(waiver_hitters),
            })

        # --- SP waiver floor ---
        sp_meaningful = pit[(pit["pitcher_type"] == "SP") & (pit["IP"] >= 20)].copy()
        waiver_sp = sp_meaningful[sp_meaningful["is_waiver"]].sort_values(
            "total_werth", ascending=False
        ).reset_index(drop=True)

        for rank in FA_RANKS_TO_TEST:
            if len(waiver_sp) >= rank:
                werth = waiver_sp.iloc[rank - 1]["total_werth"]
                name = waiver_sp.iloc[rank - 1]["Name"]
                ip = waiver_sp.iloc[rank - 1]["IP"]
            else:
                werth = np.nan
                name = ""
                ip = 0
            results.append({
                "year": year, "position": "SP", "fa_rank": rank,
                "werth": werth, "player_name": name, "pa_ip": ip,
                "pool_size": len(waiver_sp),
            })

        # --- RP waiver floor ---
        rp_meaningful = pit[(pit["pitcher_type"] == "RP") & (pit["IP"] >= 10)].copy()
        waiver_rp = rp_meaningful[rp_meaningful["is_waiver"]].sort_values(
            "total_werth", ascending=False
        ).reset_index(drop=True)

        for rank in FA_RANKS_TO_TEST:
            if len(waiver_rp) >= rank:
                werth = waiver_rp.iloc[rank - 1]["total_werth"]
                name = waiver_rp.iloc[rank - 1]["Name"]
                ip = waiver_rp.iloc[rank - 1]["IP"]
            else:
                werth = np.nan
                name = ""
                ip = 0
            results.append({
                "year": year, "position": "RP", "fa_rank": rank,
                "werth": werth, "player_name": name, "pa_ip": ip,
                "pool_size": len(waiver_rp),
            })

    return pd.DataFrame(results)


def compute_position_specific_hitter_floors(batters_all, position_data):
    """
    Attempt position-specific hitter waiver floors using position data
    from FanGraphs API position-filtered queries.

    Falls back to the draft data position mapping if API data not available.
    """
    # For now, we'll use the name-based position map from draft data
    # This only covers drafted players, but we can also infer positions
    # for undrafted players if we have the data.
    espn_pos_map, name_pos_map = load_position_map_from_drafts()

    batters_all = batters_all.copy()

    # Assign position from name map
    def get_position(row):
        name = row["Name"]
        if name in name_pos_map:
            pos = name_pos_map[name]
            return POSITION_MAP.get(pos, "UTIL")
        return None

    batters_all["mapped_position"] = batters_all.apply(get_position, axis=1)

    return batters_all


# ============================================================
# Step 6: Alternative approach — Roster-depth cutoff
# ============================================================

def compute_roster_depth_floors(batters_all, pitchers_all):
    """
    Alternative to draft-based identification:
    Assume the top (roster_slots × 8) players at each broad position
    (by end-of-season WERTH) were rostered. Everyone below = waiver available.

    This doesn't require draft data and is more conservative (assumes
    perfect roster management).
    """
    results = []

    for year in YEARS:
        bat = batters_all[batters_all["season"] == year].copy()
        pit = pitchers_all[pitchers_all["season"] == year].copy()

        # Hitters: assume top 104 + ~24 bench (3 per team) = 128 rostered
        # In an 8-team league, total roster spots = 16 * 8 = 128 (excluding IL)
        # But some of those are pitchers. Active hitting = 13 * 8 = 104
        # Plus bench hitters ~ 1-2 per team = 8-16
        rostered_hitters = 104 + 16  # 120 rostered hitters

        bat_sorted = bat[bat["PA"] >= 50].sort_values("total_werth", ascending=False)
        waiver_bat = bat_sorted.iloc[rostered_hitters:].reset_index(drop=True)

        for rank in FA_RANKS_TO_TEST:
            if len(waiver_bat) >= rank:
                werth = waiver_bat.iloc[rank - 1]["total_werth"]
                name = waiver_bat.iloc[rank - 1]["Name"]
                pa = waiver_bat.iloc[rank - 1]["PA"]
            else:
                werth = np.nan
                name = ""
                pa = 0
            results.append({
                "year": year, "position": "ALL_HIT_depth", "fa_rank": rank,
                "werth": werth, "player_name": name, "pa_ip": pa,
                "method": "roster_depth",
            })

        # SP: top 48 + ~8 bench SP = 56 rostered
        rostered_sp = 48 + 8
        sp = pit[pit["pitcher_type"] == "SP"]
        sp_sorted = sp[sp["IP"] >= 20].sort_values("total_werth", ascending=False)
        waiver_sp = sp_sorted.iloc[rostered_sp:].reset_index(drop=True)

        for rank in FA_RANKS_TO_TEST:
            if len(waiver_sp) >= rank:
                werth = waiver_sp.iloc[rank - 1]["total_werth"]
                name = waiver_sp.iloc[rank - 1]["Name"]
                ip = waiver_sp.iloc[rank - 1]["IP"]
            else:
                werth = np.nan
                name = ""
                ip = 0
            results.append({
                "year": year, "position": "SP_depth", "fa_rank": rank,
                "werth": werth, "player_name": name, "pa_ip": ip,
                "method": "roster_depth",
            })

        # RP: top 24 + ~8 bench RP = 32 rostered
        rostered_rp = 24 + 8
        rp = pit[pit["pitcher_type"] == "RP"]
        rp_sorted = rp[rp["IP"] >= 10].sort_values("total_werth", ascending=False)
        waiver_rp = rp_sorted.iloc[rostered_rp:].reset_index(drop=True)

        for rank in FA_RANKS_TO_TEST:
            if len(waiver_rp) >= rank:
                werth = waiver_rp.iloc[rank - 1]["total_werth"]
                name = waiver_rp.iloc[rank - 1]["Name"]
                ip = waiver_rp.iloc[rank - 1]["IP"]
            else:
                werth = np.nan
                name = ""
                ip = 0
            results.append({
                "year": year, "position": "RP_depth", "fa_rank": rank,
                "werth": werth, "player_name": name, "pa_ip": ip,
                "method": "roster_depth",
            })

    return pd.DataFrame(results)


# ============================================================
# Main pipeline
# ============================================================

def run_analysis():
    """Full waiver floor analysis pipeline."""
    print("=" * 70)
    print("WAIVER FLOOR ANALYSIS — Empirical Model (2022-2025)")
    print("=" * 70)

    # Load ID map once
    espn_to_mlbam = load_id_map()

    all_batters = []
    all_pitchers = []

    for year in YEARS:
        print(f"\n--- {year} ---")

        # Load stats
        bat = load_historical_batters(year)
        pit = load_historical_pitchers(year)
        print(f"  Loaded {len(bat)} batters, {len(pit)} pitchers")

        # Compute WERTH
        bat, pit = compute_werth_historical(bat, pit)
        print(f"  Computed WERTH (starter pools: {bat['is_starter'].sum()} bat, {pit['is_starter'].sum()} pit)")

        # Identify waiver-available players
        drafted_ids = load_drafted_mlbam_ids(year)
        print(f"  Drafted players matched to MLBAM IDs: {len(drafted_ids)}")

        bat = identify_waiver_players(bat, drafted_ids, "hitter")
        pit = identify_waiver_players(pit, drafted_ids, "pitcher")

        n_drafted_bat = bat["was_drafted"].sum()
        n_drafted_pit = pit["was_drafted"].sum()
        print(f"  Batters: {n_drafted_bat} drafted, {len(bat) - n_drafted_bat} undrafted")
        print(f"  Pitchers: {n_drafted_pit} drafted, {len(pit) - n_drafted_pit} undrafted")

        all_batters.append(bat)
        all_pitchers.append(pit)

    batters_all = pd.concat(all_batters, ignore_index=True)
    pitchers_all = pd.concat(all_pitchers, ignore_index=True)

    # === Method 1: Draft-based waiver identification ===
    print("\n" + "=" * 70)
    print("METHOD 1: Draft-based waiver identification")
    print("=" * 70)

    draft_floors = compute_waiver_floors_by_position(batters_all, pitchers_all)

    # Print summary table
    for pos in ["ALL_HIT", "SP", "RP"]:
        print(f"\n  {pos} Waiver Floors:")
        print(f"  {'Year':<6} {'Rank':<6} {'WERTH':>8} {'Player':<30} {'PA/IP':>6} {'Pool':>5}")
        print(f"  {'-'*65}")
        subset = draft_floors[draft_floors["position"] == pos]
        for _, row in subset.iterrows():
            print(f"  {row['year']:<6} {row['fa_rank']:<6} {row['werth']:>8.2f} "
                  f"{row['player_name']:<30} {row['pa_ip']:>6.0f} {row['pool_size']:>5}")

    # === Method 2: Roster-depth cutoff ===
    print("\n" + "=" * 70)
    print("METHOD 2: Roster-depth cutoff")
    print("=" * 70)

    depth_floors = compute_roster_depth_floors(batters_all, pitchers_all)

    for pos in ["ALL_HIT_depth", "SP_depth", "RP_depth"]:
        print(f"\n  {pos} Waiver Floors:")
        print(f"  {'Year':<6} {'Rank':<6} {'WERTH':>8} {'Player':<30} {'PA/IP':>6}")
        print(f"  {'-'*60}")
        subset = depth_floors[depth_floors["position"] == pos]
        for _, row in subset.iterrows():
            print(f"  {row['year']:<6} {row['fa_rank']:<6} {row['werth']:>8.2f} "
                  f"{row['player_name']:<30} {row['pa_ip']:>6.0f}")

    # === Comparative analysis ===
    print("\n" + "=" * 70)
    print("COMPARATIVE ANALYSIS: Average WERTH by FA Rank (2022-2025)")
    print("=" * 70)

    # Average across years for draft-based method
    avg_draft = draft_floors.groupby(["position", "fa_rank"])["werth"].mean().reset_index()

    print(f"\n  Draft-based method (averaged over {len(YEARS)} seasons):")
    print(f"  {'Position':<10} " + " ".join(f"{'Rank '+str(r):>10}" for r in FA_RANKS_TO_TEST))
    print(f"  {'-'*70}")
    for pos in ["ALL_HIT", "SP", "RP"]:
        vals = avg_draft[avg_draft["position"] == pos].set_index("fa_rank")["werth"]
        line = f"  {pos:<10} "
        for r in FA_RANKS_TO_TEST:
            if r in vals.index:
                line += f"{vals[r]:>10.2f}"
            else:
                line += f"{'N/A':>10}"
        print(line)

    # === Key metric: Hitter-to-Pitcher ratio at each rank ===
    print(f"\n  Hitter vs SP WERTH ratio at each rank:")
    print(f"  {'Rank':<6} {'Hitter':>10} {'SP':>10} {'RP':>10} {'H-SP diff':>10} {'H-RP diff':>10}")
    print(f"  {'-'*60}")
    for rank in FA_RANKS_TO_TEST:
        h = avg_draft[(avg_draft["position"] == "ALL_HIT") & (avg_draft["fa_rank"] == rank)]["werth"].values
        sp = avg_draft[(avg_draft["position"] == "SP") & (avg_draft["fa_rank"] == rank)]["werth"].values
        rp = avg_draft[(avg_draft["position"] == "RP") & (avg_draft["fa_rank"] == rank)]["werth"].values

        h_val = h[0] if len(h) > 0 else np.nan
        sp_val = sp[0] if len(sp) > 0 else np.nan
        rp_val = rp[0] if len(rp) > 0 else np.nan

        h_sp = h_val - sp_val if not (np.isnan(h_val) or np.isnan(sp_val)) else np.nan
        h_rp = h_val - rp_val if not (np.isnan(h_val) or np.isnan(rp_val)) else np.nan

        print(f"  {rank:<6} {h_val:>10.2f} {sp_val:>10.2f} {rp_val:>10.2f} "
              f"{h_sp:>10.2f} {h_rp:>10.2f}")

    # === Recommendation ===
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)

    # Find the rank where hitter and SP floors are approximately equal
    # (i.e., the rank that produces fair DV comparison)
    print("\n  Goal: Find hitter_rank N_h and pitcher_rank N_p such that")
    print("  the waiver floor WERTH is comparable across types.")
    print()

    # For each combination, show the floor difference
    print(f"  {'H_rank':<8} {'P_rank':<8} {'H_floor':>10} {'SP_floor':>10} {'Diff':>10}")
    print(f"  {'-'*50}")
    for h_rank in [2, 4, 8]:
        for p_rank in [2, 4, 8, 16]:
            h = avg_draft[(avg_draft["position"] == "ALL_HIT") & (avg_draft["fa_rank"] == h_rank)]["werth"].values
            sp = avg_draft[(avg_draft["position"] == "SP") & (avg_draft["fa_rank"] == p_rank)]["werth"].values
            if len(h) > 0 and len(sp) > 0:
                diff = h[0] - sp[0]
                marker = " <-- closest" if abs(diff) < 0.5 else ""
                print(f"  {h_rank:<8} {p_rank:<8} {h[0]:>10.2f} {sp[0]:>10.2f} {diff:>10.2f}{marker}")

    return draft_floors, depth_floors, batters_all, pitchers_all


if __name__ == "__main__":
    draft_floors, depth_floors, batters_all, pitchers_all = run_analysis()

    # Save results
    output_dir = ROOT / "analysis"
    output_dir.mkdir(exist_ok=True)

    draft_floors.to_csv(output_dir / "waiver_floors_draft_method.csv", index=False)
    depth_floors.to_csv(output_dir / "waiver_floors_depth_method.csv", index=False)

    print(f"\nResults saved to {output_dir}/")
