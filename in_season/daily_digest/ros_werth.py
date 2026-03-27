"""
In-season RoS WERTH calculator.
Reuses core valuation logic from model/valuation_engine.py but operates on:
- RoS projections (not pre-season full-year)
- Actual rostered players (not theoretical starter pool)
- Dynamic replacement level (best available FA, not (N+1)th best)
"""

import sys
import logging
from pathlib import Path

import pandas as pd
import numpy as np

from config import (
    HITTING_CATS, PITCHING_CATS, ALL_CATS, LOWER_IS_BETTER,
    NUM_TEAMS, ROSTER_SLOTS,
)

# Import core functions from the pre-season valuation engine
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "model"))
from valuation_engine import (
    classify_pitcher_type,
    assign_primary_position,
    HITTING_ROSTER,
    POSITION_MAP,
    FLEX_ELIGIBLE,
)

log = logging.getLogger(__name__)

# Roster config for starter pool sizing
SP_PER_TEAM = 6
RP_PER_TEAM = 3


def compute_ros_werth(ros_batters, ros_pitchers, rostered_espn_ids=None, fa_espn_ids=None):
    """
    Compute RoS WERTH using actual league rosters.

    Args:
        ros_batters: DataFrame of RoS batter projections (from FanGraphs)
        ros_pitchers: DataFrame of RoS pitcher projections
        rostered_espn_ids: set of ESPN IDs currently on any roster (defines starter pool)
        fa_espn_ids: set of ESPN IDs that are free agents (for replacement level)

    Returns:
        hitters_df, pitchers_df with z-scores and WERTH columns
    """
    hitters = ros_batters.copy()
    pitchers = ros_pitchers.copy()

    # Classify pitchers
    pitchers = classify_pitcher_type(pitchers)

    # Assign positions to hitters
    if "fg_position" not in hitters.columns:
        if "minpos" in hitters.columns:
            hitters["fg_position"] = hitters["minpos"]
        else:
            hitters["fg_position"] = ""
    hitters = assign_primary_position(hitters)

    # --- Identify starter pool from actual rosters ---
    if rostered_espn_ids is not None and "espn_id" in hitters.columns:
        hitters["is_starter"] = hitters["espn_id"].isin(rostered_espn_ids)
        pitchers["is_starter"] = pitchers["espn_id"].isin(rostered_espn_ids)
    else:
        # Fallback: use top-N by PA/IP as proxy
        _fallback_starter_pool(hitters, pitchers)

    starter_h = hitters["is_starter"].sum()
    starter_p = pitchers["is_starter"].sum()
    log.info(f"Starter pool: {starter_h} hitters, {starter_p} pitchers (from rosters)")

    # --- Convert rate stats ---
    hitters, pitchers = _convert_rate_stats(hitters, pitchers)

    # --- Compute z-scores ---
    hitters, pitchers = _compute_zscores(hitters, pitchers)

    # --- Replacement level from best available FAs ---
    pos_repl, pit_repl = _compute_replacement_level(hitters, pitchers, fa_espn_ids)

    # --- Position-adjusted WERTH ---
    hitters["repl_level"] = hitters["primary_position"].map(pos_repl).fillna(0)
    multi_bonus = hitters.get("is_multi_position", pd.Series(False, index=hitters.index)).astype(float) * 0.5
    hitters["pos_adj_werth"] = hitters["repl_level"].abs() + hitters["total_werth"] + multi_bonus

    pitchers["repl_level"] = pit_repl
    pitchers["pos_adj_werth"] = abs(pit_repl) + pitchers["total_werth"]

    return hitters, pitchers


def _fallback_starter_pool(hitters, pitchers):
    """Use top-N by PA/IP when we don't have roster data."""
    total_h = sum(v for k, v in HITTING_ROSTER.items()) * NUM_TEAMS
    total_p = ROSTER_SLOTS["P"] * NUM_TEAMS

    hitters["is_starter"] = False
    h_sorted = hitters.sort_values("PA", ascending=False) if "PA" in hitters.columns else hitters
    hitters.loc[h_sorted.index[:total_h], "is_starter"] = True

    pitchers["is_starter"] = False
    p_sorted = pitchers.sort_values("IP", ascending=False) if "IP" in pitchers.columns else pitchers
    pitchers.loc[p_sorted.index[:total_p], "is_starter"] = True


def _convert_rate_stats(hitters, pitchers):
    """Convert rate stats to counting equivalents (same methodology as valuation_engine)."""
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    starters_h = hitters[hitters["is_starter"]]
    if len(starters_h) == 0 or "PA" not in starters_h.columns:
        hitters["OBPc"] = 0
        pitchers["ERAc"] = pitchers["WHIPc"] = pitchers["KBBc"] = 0
        return hitters, pitchers

    # Hitting: OBPc
    pa = starters_h["PA"].fillna(0)
    obp = starters_h["OBP"].fillna(0)
    league_obp = (obp * pa).sum() / pa.sum() if pa.sum() > 0 else 0.320
    avg_pa = pa.mean() if len(pa) > 0 else 500
    total_slots = sum(v for k, v in HITTING_ROSTER.items()) * NUM_TEAMS

    hitters["OBPc"] = (
        (hitters["OBP"].fillna(league_obp) * hitters["PA"].fillna(0)) -
        (league_obp * hitters["PA"].fillna(0))
    ) / (avg_pa * total_slots) if (avg_pa * total_slots) > 0 else 0

    # Pitching: ERAc, WHIPc, KBBc
    starters_p = pitchers[pitchers["is_starter"]]
    if len(starters_p) == 0 or "IP" not in starters_p.columns:
        pitchers["ERAc"] = pitchers["WHIPc"] = pitchers["KBBc"] = 0
        return hitters, pitchers

    total_ip = starters_p["IP"].sum()
    if total_ip == 0:
        pitchers["ERAc"] = pitchers["WHIPc"] = pitchers["KBBc"] = 0
        return hitters, pitchers

    league_era = (starters_p["ERA"] * starters_p["IP"]).sum() / total_ip
    league_whip = (starters_p["WHIP"] * starters_p["IP"]).sum() / total_ip
    league_kbb = (starters_p["KBB"].fillna(0) * starters_p["IP"]).sum() / total_ip

    ip = pitchers["IP"].fillna(0)
    ip_share = ip / total_ip

    pitchers["ERAc"] = (ip_share * pitchers["ERA"].fillna(league_era) + (1 - ip_share) * league_era) - league_era
    pitchers["WHIPc"] = (ip_share * pitchers["WHIP"].fillna(league_whip) + (1 - ip_share) * league_whip) - league_whip
    pitchers["KBBc"] = (ip_share * pitchers["KBB"].fillna(league_kbb) + (1 - ip_share) * league_kbb) - league_kbb

    return hitters, pitchers


def _compute_zscores(hitters, pitchers):
    """Compute per-category z-scores using starter pool as reference."""
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    starters_h = hitters[hitters["is_starter"]]
    for cat in HITTING_CATS:
        stat_col = "OBPc" if cat == "OBP" else cat
        if stat_col not in hitters.columns:
            hitters[f"z_{cat}"] = 0.0
            continue
        values = starters_h[stat_col] if stat_col in starters_h.columns else pd.Series([0])
        mean = values.mean()
        std = values.std()
        if cat in LOWER_IS_BETTER:
            std = -std
        if abs(std) < 1e-10:
            hitters[f"z_{cat}"] = 0.0
        else:
            hitters[f"z_{cat}"] = (hitters[stat_col].fillna(mean) - mean) / std

    starters_p = pitchers[pitchers["is_starter"]]
    for cat in PITCHING_CATS:
        stat_col = {"ERA": "ERAc", "WHIP": "WHIPc", "KBB": "KBBc"}.get(cat, cat)
        if stat_col not in pitchers.columns:
            pitchers[f"z_{cat}"] = 0.0
            continue
        values = starters_p[stat_col] if stat_col in starters_p.columns else pd.Series([0])
        mean = values.mean()
        std = values.std()
        if cat in LOWER_IS_BETTER:
            std = -std
        if abs(std) < 1e-10:
            pitchers[f"z_{cat}"] = 0.0
        else:
            pitchers[f"z_{cat}"] = (pitchers[stat_col].fillna(mean) - mean) / std

    hit_z = [f"z_{cat}" for cat in HITTING_CATS]
    pit_z = [f"z_{cat}" for cat in PITCHING_CATS]
    hitters["total_werth"] = hitters[[c for c in hit_z if c in hitters.columns]].sum(axis=1)
    pitchers["total_werth"] = pitchers[[c for c in pit_z if c in pitchers.columns]].sum(axis=1)

    return hitters, pitchers


def _compute_replacement_level(hitters, pitchers, fa_espn_ids=None):
    """
    Compute replacement level.
    If FA IDs provided, replacement = best FA at each position.
    Otherwise, fall back to (N+1)th best rostered player.
    """
    if fa_espn_ids is not None and "espn_id" in hitters.columns:
        fa_hitters = hitters[hitters["espn_id"].isin(fa_espn_ids)]
        fa_pitchers = pitchers[pitchers["espn_id"].isin(fa_espn_ids)]
    else:
        # Fallback: non-starters
        fa_hitters = hitters[~hitters["is_starter"]]
        fa_pitchers = pitchers[~pitchers["is_starter"]]

    pos_repl = {}
    for pos in HITTING_ROSTER:
        if pos in ("MI", "CI", "UTIL"):
            continue
        pos_fas = fa_hitters[fa_hitters["primary_position"] == pos]
        if len(pos_fas) > 0:
            pos_repl[pos] = pos_fas["total_werth"].max()
        else:
            pos_repl[pos] = 0.0

    if pos_repl:
        repl_vals = list(pos_repl.values())
        pos_repl["UTIL"] = max(repl_vals) + np.std(repl_vals)
        pos_repl["MI"] = max(pos_repl.get("2B", 0), pos_repl.get("SS", 0))
        pos_repl["CI"] = max(pos_repl.get("1B", 0), pos_repl.get("3B", 0))

    if len(fa_pitchers) > 0:
        pit_repl = fa_pitchers["total_werth"].nlargest(3).mean()
    else:
        pit_repl = 0.0

    log.info(f"Replacement levels: {pos_repl}, P={pit_repl:.2f}")
    return pos_repl, pit_repl
