"""
Phase 3: Valuation Engine — Port Mr. Cheatsheet's WERTH formula chain to Python.

Implements:
1. Rate stat → counting equivalent conversion (OBPc, ERAc, WHIPc, K/BBc)
2. Starter pool identification
3. Z-scores per category
4. Replacement level
5. Position-adjusted WERTH

References: research.md §2.2-2.3 and §7 (Appendix A-G)
"""

import pandas as pd
import numpy as np
from data_pipeline import (
    build_unified_table, NUM_TEAMS, ROSTER_SLOTS,
    HITTING_CATS, PITCHING_CATS, ALL_CATS, LOWER_IS_BETTER
)

# ----- Position mapping -----
# Map FanGraphs minpos strings to roster slot categories.
# Players with slash-separated positions are multi-eligible.
POSITION_MAP = {
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
    "OF": "OF", "LF": "OF", "CF": "OF", "RF": "OF",
    "DH": "UTIL",
}
# Flex positions and their eligible slots
FLEX_ELIGIBLE = {
    "MI": {"2B", "SS"},
    "CI": {"1B", "3B"},
    "UTIL": {"C", "1B", "2B", "3B", "SS", "OF", "DH"},
}

# Active hitting roster slots (excluding bench/IL)
HITTING_ROSTER = {k: v for k, v in ROSTER_SLOTS.items()
                  if k not in ("P", "BE", "IL")}
TOTAL_HITTING_STARTERS = sum(HITTING_ROSTER.values()) * NUM_TEAMS  # 13 slots × 8 = 104
TOTAL_PITCHING_STARTERS = ROSTER_SLOTS["P"] * NUM_TEAMS  # 9 × 8 = 72


def classify_pitcher_type(df):
    """Classify pitchers as SP or RP based on GS ratio."""
    df = df.copy()
    if "GS" in df.columns and "G" in df.columns:
        gs_ratio = df["GS"] / df["G"].replace(0, np.nan)
        df["pitcher_type"] = np.where(gs_ratio >= 0.5, "SP", "RP")
    else:
        df["pitcher_type"] = "SP"  # default
    return df


def assign_primary_position(hitters):
    """Assign each hitter a primary roster position from fg_position."""
    hitters = hitters.copy()

    def _parse_primary(pos_str):
        if pd.isna(pos_str) or pos_str == "":
            return "UTIL"
        # Take first position listed (primary)
        primary = str(pos_str).split("/")[0].strip()
        return POSITION_MAP.get(primary, "UTIL")

    def _parse_all_positions(pos_str):
        if pd.isna(pos_str) or pos_str == "":
            return []
        parts = str(pos_str).split("/")
        positions = []
        for p in parts:
            p = p.strip()
            mapped = POSITION_MAP.get(p, None)
            if mapped:
                positions.append(mapped)
        return positions

    hitters["primary_position"] = hitters["fg_position"].apply(_parse_primary)
    hitters["all_positions"] = hitters["fg_position"].apply(_parse_all_positions)
    hitters["is_multi_position"] = hitters["all_positions"].apply(lambda x: len(x) > 1)
    return hitters


def identify_starter_pool(hitters, pitchers):
    """
    Identify the starter pool for z-score calculation.
    Starters = roster_slots × num_teams best players at each position.

    For pitchers: 9 P slots per team, typically ~6 SP + ~3 RP.
    We use a realistic SP/RP split to avoid SVHD z-score inflation.
    """
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    # --- Hitters ---
    hitters["_rank_proxy"] = hitters["PA"].fillna(0)

    position_starters = {}
    for pos, slots in HITTING_ROSTER.items():
        position_starters[pos] = slots * NUM_TEAMS

    hitters["is_starter"] = False
    filled = {pos: 0 for pos in position_starters}
    assigned_players = set()
    sorted_idx = hitters["_rank_proxy"].sort_values(ascending=False).index

    # First pass: assign players to their primary position
    for idx in sorted_idx:
        pos = hitters.loc[idx, "primary_position"]
        if pos in filled and filled[pos] < position_starters.get(pos, 0):
            hitters.loc[idx, "is_starter"] = True
            hitters.loc[idx, "starter_position"] = pos
            filled[pos] += 1
            assigned_players.add(idx)

    # Second pass: fill flex positions (MI, CI, UTIL) with best remaining
    for flex_pos, eligible_positions in FLEX_ELIGIBLE.items():
        if flex_pos not in position_starters:
            continue
        needed = position_starters[flex_pos] - filled.get(flex_pos, 0)
        if needed <= 0:
            continue
        for idx in sorted_idx:
            if idx in assigned_players:
                continue
            player_pos = hitters.loc[idx, "primary_position"]
            if player_pos in eligible_positions:
                hitters.loc[idx, "is_starter"] = True
                hitters.loc[idx, "starter_position"] = flex_pos
                filled[flex_pos] = filled.get(flex_pos, 0) + 1
                assigned_players.add(idx)
                needed -= 1
                if needed <= 0:
                    break

    # --- Pitchers: realistic SP/RP split ---
    # 9 P slots per team. Typical roster: 6 SP + 3 RP = 48 SP + 24 RP = 72 total
    SP_PER_TEAM = 6
    RP_PER_TEAM = 3
    n_sp_starters = SP_PER_TEAM * NUM_TEAMS  # 48
    n_rp_starters = RP_PER_TEAM * NUM_TEAMS  # 24

    pitchers["_rank_proxy"] = pitchers.get("WAR", pitchers["IP"]).fillna(0)
    pitchers["is_starter"] = False

    sp_mask = pitchers["pitcher_type"] == "SP"
    rp_mask = pitchers["pitcher_type"] == "RP"

    # Top SPs by WAR
    sp_sorted = pitchers[sp_mask].sort_values("_rank_proxy", ascending=False)
    sp_starter_idx = sp_sorted.index[:n_sp_starters]
    pitchers.loc[sp_starter_idx, "is_starter"] = True

    # Top RPs by a RP-appropriate proxy: SVHD + K (closers/setup men)
    pitchers.loc[rp_mask, "_rp_rank"] = (
        pitchers.loc[rp_mask, "SVHD"].fillna(0) +
        pitchers.loc[rp_mask, "K"].fillna(0) * 0.5
    )
    rp_sorted = pitchers[rp_mask].sort_values("_rp_rank", ascending=False)
    rp_starter_idx = rp_sorted.index[:n_rp_starters]
    pitchers.loc[rp_starter_idx, "is_starter"] = True

    starter_count = hitters["is_starter"].sum()
    pit_starter_count = pitchers["is_starter"].sum()
    sp_count = pitchers[pitchers["is_starter"] & sp_mask].shape[0]
    rp_count = pitchers[pitchers["is_starter"] & rp_mask].shape[0]
    print(f"Hitting starters: {starter_count} (target: {sum(position_starters.values())})")
    print(f"Pitching starters: {pit_starter_count} ({sp_count} SP + {rp_count} RP)")

    return hitters, pitchers


def convert_rate_stats(hitters, pitchers):
    """
    Convert rate stats to counting equivalents per research.md §7 Appendix A-B.

    Hitting rate stats (OBP → OBPc):
        OBPc = ((player_OBP × PA) - (league_OBP × PA)) / (avg_starter_PA × total_starter_slots)

    Pitching rate stats:
        ERAc = ((player_IP / total_IP) × player_ERA + (1 - player_IP/total_IP) × league_ERA) - league_ERA
        WHIPc = same pattern as ERA
        KBBc = ((player_IP / total_IP) × player_KBB + (1 - player_IP/total_IP) × league_KBB) - league_KBB
    """
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    # --- Hitting: OBPc ---
    starters_h = hitters[hitters["is_starter"]]
    league_obp = (starters_h["OBP"] * starters_h["PA"]).sum() / starters_h["PA"].sum()
    avg_starter_pa = starters_h["PA"].mean()
    total_hitting_slots = sum(v for k, v in HITTING_ROSTER.items()) * NUM_TEAMS

    hitters["OBPc"] = (
        (hitters["OBP"].fillna(league_obp) * hitters["PA"].fillna(0)) -
        (league_obp * hitters["PA"].fillna(0))
    ) / (avg_starter_pa * total_hitting_slots)

    # --- Pitching: ERAc, WHIPc, KBBc ---
    starters_p = pitchers[pitchers["is_starter"]]
    total_league_ip = starters_p["IP"].sum()
    league_era = (starters_p["ERA"] * starters_p["IP"]).sum() / total_league_ip
    league_whip = (starters_p["WHIP"] * starters_p["IP"]).sum() / total_league_ip
    league_kbb = (starters_p["KBB"] * starters_p["IP"]).sum() / total_league_ip

    ip = pitchers["IP"].fillna(0)
    ip_share = ip / total_league_ip

    # ERAc: marginal team ERA impact (lower = better, so negative ERAc = good)
    pitchers["ERAc"] = (
        ip_share * pitchers["ERA"].fillna(league_era) +
        (1 - ip_share) * league_era
    ) - league_era

    # WHIPc: same pattern
    pitchers["WHIPc"] = (
        ip_share * pitchers["WHIP"].fillna(league_whip) +
        (1 - ip_share) * league_whip
    ) - league_whip

    # KBBc: K/BB is "higher is better" but still a rate stat needing conversion
    pitchers["KBBc"] = (
        ip_share * pitchers["KBB"].fillna(league_kbb) +
        (1 - ip_share) * league_kbb
    ) - league_kbb

    print(f"\nRate stat conversion (hitting):")
    print(f"  League OBP: {league_obp:.4f}, Avg starter PA: {avg_starter_pa:.1f}")
    print(f"Rate stat conversion (pitching):")
    print(f"  League ERA: {league_era:.3f}, WHIP: {league_whip:.4f}, K/BB: {league_kbb:.3f}")
    print(f"  Total league IP: {total_league_ip:.1f}")

    return hitters, pitchers


def compute_zscores(hitters, pitchers):
    """
    Compute per-category z-scores.

    For counting stats: z = (player_stat - mean) / stdev
    For rate stats: use the converted counting equivalent
    For lower-is-better stats: negate the stdev so z-score direction is consistent
    """
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    # --- Hitting z-scores ---
    starters_h = hitters[hitters["is_starter"]]

    for cat in HITTING_CATS:
        # Use converted stat for rate categories
        if cat == "OBP":
            stat_col = "OBPc"
        else:
            stat_col = cat

        values = starters_h[stat_col]
        mean = values.mean()
        std = values.std()

        if cat in LOWER_IS_BETTER:
            std = -std  # negate for lower-is-better

        if abs(std) < 1e-10:
            hitters[f"z_{cat}"] = 0.0
        else:
            hitters[f"z_{cat}"] = (hitters[stat_col].fillna(mean) - mean) / std

    # --- Pitching z-scores ---
    starters_p = pitchers[pitchers["is_starter"]]

    for cat in PITCHING_CATS:
        # Use converted stat for rate categories
        if cat == "ERA":
            stat_col = "ERAc"
        elif cat == "WHIP":
            stat_col = "WHIPc"
        elif cat == "KBB":
            stat_col = "KBBc"
        else:
            stat_col = cat

        values = starters_p[stat_col]
        mean = values.mean()
        std = values.std()

        if cat in LOWER_IS_BETTER:
            std = -std  # ERA, WHIP: lower is better

        if abs(std) < 1e-10:
            pitchers[f"z_{cat}"] = 0.0
        else:
            pitchers[f"z_{cat}"] = (pitchers[stat_col].fillna(mean) - mean) / std

    # Total WERTH
    hit_z_cols = [f"z_{cat}" for cat in HITTING_CATS]
    pit_z_cols = [f"z_{cat}" for cat in PITCHING_CATS]

    hitters["total_werth"] = hitters[hit_z_cols].sum(axis=1)
    pitchers["total_werth"] = pitchers[pit_z_cols].sum(axis=1)

    return hitters, pitchers


def compute_replacement_level(hitters, pitchers):
    """
    Replacement level = WERTH of the (N+1)th best player at each position.
    DH/UTIL = MAX(all_position_replacements) + STDEV(all_position_replacements)
    """
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    # Hitter replacement levels by position
    position_replacement = {}
    for pos, slots in HITTING_ROSTER.items():
        if pos in ("MI", "CI", "UTIL"):
            continue  # handle flex positions separately
        n_starters = slots * NUM_TEAMS
        pos_players = hitters[hitters["primary_position"] == pos].sort_values(
            "total_werth", ascending=False
        )
        if len(pos_players) > n_starters:
            repl_werth = pos_players.iloc[n_starters]["total_werth"]
        elif len(pos_players) > 0:
            repl_werth = pos_players.iloc[-1]["total_werth"]
        else:
            repl_werth = 0
        position_replacement[pos] = repl_werth

    # UTIL replacement: MAX + STDEV of position replacements
    if position_replacement:
        repl_values = list(position_replacement.values())
        position_replacement["UTIL"] = max(repl_values) + np.std(repl_values)
        # MI and CI: use the worse of their eligible positions
        position_replacement["MI"] = max(
            position_replacement.get("2B", 0),
            position_replacement.get("SS", 0)
        )
        position_replacement["CI"] = max(
            position_replacement.get("1B", 0),
            position_replacement.get("3B", 0)
        )

    # Pitcher replacement level
    n_pit_starters = ROSTER_SLOTS["P"] * NUM_TEAMS
    pit_sorted = pitchers.sort_values("total_werth", ascending=False)
    if len(pit_sorted) > n_pit_starters:
        pit_replacement = pit_sorted.iloc[n_pit_starters]["total_werth"]
    else:
        pit_replacement = pit_sorted.iloc[-1]["total_werth"] if len(pit_sorted) > 0 else 0

    print(f"\nReplacement levels:")
    for pos, val in sorted(position_replacement.items()):
        print(f"  {pos}: {val:.3f}")
    print(f"  P: {pit_replacement:.3f}")

    return position_replacement, pit_replacement


def compute_position_adjusted_werth(hitters, pitchers, pos_replacement, pit_replacement):
    """
    Position-Adjusted WERTH = |replacement_level| + total_WERTH + 0.5 × multi_pos
    """
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    # For each hitter: use their primary position's replacement level
    hitters["repl_level"] = hitters["primary_position"].map(pos_replacement).fillna(0)
    multi_pos_bonus = hitters["is_multi_position"].astype(float) * 0.5

    hitters["pos_adj_werth"] = (
        hitters["repl_level"].abs() +
        hitters["total_werth"] +
        multi_pos_bonus
    )

    # Pitchers: single replacement level
    pitchers["repl_level"] = pit_replacement
    pitchers["pos_adj_werth"] = (
        abs(pit_replacement) +
        pitchers["total_werth"]
    )

    return hitters, pitchers


def handle_two_way_players(hitters, pitchers):
    """
    Combine hitting + pitching value for two-way players (Ohtani).
    The hitter row gets the pitcher's z-scores added to its total WERTH.
    The pitcher row is kept but flagged so it's excluded from combined rankings.
    """
    # Find players in both tables by mlbam_id
    two_way_ids = set(hitters["mlbam_id"].dropna()) & set(pitchers["mlbam_id"].dropna())

    for mlbam_id in two_way_ids:
        h_mask = hitters["mlbam_id"] == mlbam_id
        p_mask = pitchers["mlbam_id"] == mlbam_id

        if h_mask.sum() == 0 or p_mask.sum() == 0:
            continue

        h_idx = hitters[h_mask].index[0]
        p_idx = pitchers[p_mask].index[0]

        player_name = hitters.loc[h_idx, "name"]
        pit_werth = pitchers.loc[p_idx, "total_werth"]

        # Add pitching z-scores to the hitter row
        for cat in PITCHING_CATS:
            z_col = f"z_{cat}"
            if z_col in pitchers.columns:
                hitters.loc[h_idx, z_col] = pitchers.loc[p_idx, z_col]

        # Update total WERTH to include both hitting and pitching
        hit_z = sum(hitters.loc[h_idx, f"z_{cat}"] for cat in HITTING_CATS
                    if f"z_{cat}" in hitters.columns)
        pit_z = sum(hitters.loc[h_idx, f"z_{cat}"] for cat in PITCHING_CATS
                    if f"z_{cat}" in hitters.columns)
        hitters.loc[h_idx, "total_werth"] = hit_z + pit_z
        hitters.loc[h_idx, "is_two_way"] = True

        # Flag the pitcher row for exclusion from combined rankings
        pitchers.loc[p_idx, "exclude_from_combined"] = True

        print(f"  Two-way: {player_name} — hit WERTH {hit_z:.2f} + pit WERTH {pit_z:.2f} = {hit_z + pit_z:.2f}")

    hitters["is_two_way"] = hitters["is_two_way"].fillna(False).astype(bool)
    if "exclude_from_combined" not in pitchers.columns:
        pitchers["exclude_from_combined"] = False

    return hitters, pitchers


def run_valuation():
    """Run the full valuation pipeline."""
    # Phase 1: Data
    hitters, pitchers = build_unified_table()

    # Classify pitchers
    pitchers = classify_pitcher_type(pitchers)

    # Assign positions
    hitters = assign_primary_position(hitters)

    # Identify starter pool
    hitters, pitchers = identify_starter_pool(hitters, pitchers)

    # Convert rate stats
    hitters, pitchers = convert_rate_stats(hitters, pitchers)

    # Compute z-scores
    hitters, pitchers = compute_zscores(hitters, pitchers)

    # Handle two-way players (Ohtani)
    hitters, pitchers = handle_two_way_players(hitters, pitchers)

    # Compute replacement level
    pos_replacement, pit_replacement = compute_replacement_level(hitters, pitchers)

    # Position-adjusted WERTH
    hitters, pitchers = compute_position_adjusted_werth(
        hitters, pitchers, pos_replacement, pit_replacement
    )

    return hitters, pitchers, pos_replacement, pit_replacement


if __name__ == "__main__":
    hitters, pitchers, pos_repl, pit_repl = run_valuation()

    print("\n" + "=" * 80)
    print("TOP 25 HITTERS BY POSITION-ADJUSTED WERTH")
    print("=" * 80)
    cols = ["name", "Team", "primary_position", "PA",
            "z_R", "z_HR", "z_TB", "z_RBI", "z_SBN", "z_OBP",
            "total_werth", "pos_adj_werth"]
    print(hitters.nlargest(25, "pos_adj_werth")[cols].to_string(
        float_format=lambda x: f"{x:.2f}"
    ))

    print("\n" + "=" * 80)
    print("TOP 25 PITCHERS BY POSITION-ADJUSTED WERTH")
    print("=" * 80)
    cols_p = ["name", "Team", "pitcher_type", "IP",
              "z_K", "z_QS", "z_ERA", "z_WHIP", "z_KBB", "z_SVHD",
              "total_werth", "pos_adj_werth"]
    print(pitchers.nlargest(25, "pos_adj_werth")[cols_p].to_string(
        float_format=lambda x: f"{x:.2f}"
    ))

    # Overall rankings
    print("\n" + "=" * 80)
    print("OVERALL TOP 40 (HITTERS + PITCHERS)")
    print("=" * 80)

    h_rank = hitters[["name", "Team", "primary_position", "pos_adj_werth", "total_werth", "espn_id"]].copy()
    h_rank["type"] = "H"
    h_rank = h_rank.rename(columns={"primary_position": "position"})

    # Exclude pitcher rows for two-way players (their value is in the hitter row)
    pit_for_rank = pitchers[~pitchers["exclude_from_combined"].fillna(False).astype(bool)]
    p_rank = pit_for_rank[["name", "Team", "pitcher_type", "pos_adj_werth", "total_werth", "espn_id"]].copy()
    p_rank["type"] = "P"
    p_rank = p_rank.rename(columns={"pitcher_type": "position"})

    combined = pd.concat([h_rank, p_rank], ignore_index=True)
    combined = combined.sort_values("pos_adj_werth", ascending=False).reset_index(drop=True)
    combined.index += 1
    combined.index.name = "rank"

    print(combined.head(40).to_string(float_format=lambda x: f"{x:.2f}"))
