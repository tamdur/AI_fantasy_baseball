"""Advisor valuation: the §4.4 cheap fixes wrapped around ``ros_werth`` (plan §4a).

Keeps the backend ``compute_ros_werth`` untouched; applies the fixes in a wrapper:

* **#1 regulars-vs-bench pool** — the backend computes z-score means/stds over *all*
  rostered players (bench scrubs included), distorting the reference. We instead pass
  a **regulars** pool (top players by projected PT, ≈ the league's actual starting
  lineups) so the normalization reflects real starters.
* **#3 FA-pool replacement** — already implemented by the backend when ``fa_espn_ids``
  is passed (replacement = observed FA pool, not pre-season floors). We pass live FA ids.
* **#4 small-average replacement** — the backend uses a single best FA (``.max()``) for
  hitter replacement, which a hot/skewed FA distorts. We override with a top-k mean.
* **#2 disagreement σ** — surfaced separately from ``fetch_multi_system_ros`` (wired in
  context, consumed by the simulator's thin-sample fallback). ``proj_per_game`` here
  produces the per-game projection anchor the simulator needs.
"""

import logging

import numpy as np
import pandas as pd

from advisor import config as cfg

log = logging.getLogger("advisor.valuation")

# League starting-lineup sizing for the regulars pool.
_HITTING_STARTER_SLOTS = sum(v for k, v in cfg.ROSTER_SLOTS.items()
                             if k not in ("P", "BE", "IL"))          # 12 per team
_PITCHER_STARTER_SLOTS = cfg.ROSTER_SLOTS["P"]                        # 9 per team
_DIRECT_POSITIONS = ("C", "1B", "2B", "3B", "SS", "OF")
_PA_PER_GAME = 4.3
_IP_PER_START = 5.2


def regular_pool(ros_bat, ros_pit, rostered_ids):
    """ESPN-id set of likely REGULARS among rostered players (§4.4 #1).

    Top ``NUM_TEAMS * starting slots`` rostered hitters by PA + pitchers by IP — i.e.
    roughly the league's actual starting lineups, excluding deep-bench scrubs that
    would otherwise distort the z-score reference pool.
    """
    rostered_ids = set(rostered_ids or [])
    keep = set()
    for df, pt_col, slots in ((ros_bat, "PA", _HITTING_STARTER_SLOTS),
                              (ros_pit, "IP", _PITCHER_STARTER_SLOTS)):
        if df is None or "espn_id" not in df.columns or pt_col not in df.columns:
            continue
        rostered = df[df["espn_id"].isin(rostered_ids)]
        n = cfg.NUM_TEAMS * slots
        top = rostered.sort_values(pt_col, ascending=False).head(n)
        keep.update(int(x) for x in top["espn_id"].dropna())
    return keep


def _small_avg(series, k=2):
    """Mean of the top-k values (robust replacement vs a single skewed best)."""
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    return float(s.nlargest(min(k, len(s))).mean())


def apply_small_avg_replacement(hitters, pitchers, fa_espn_ids, k=2):
    """Override repl_level / pos_adj_werth using a top-k FA mean for hitters (§4.4 #4).

    Pitchers already use nlargest(3).mean() in the backend; we recompute consistently.
    """
    if fa_espn_ids is None or "espn_id" not in hitters.columns:
        return hitters, pitchers
    fa_h = hitters[hitters["espn_id"].isin(fa_espn_ids)]
    fa_p = pitchers[pitchers["espn_id"].isin(fa_espn_ids)]

    pos_repl = {}
    for pos in _DIRECT_POSITIONS:
        pos_fas = fa_h[fa_h["primary_position"] == pos]
        pos_repl[pos] = _small_avg(pos_fas["total_werth"], k=k) if len(pos_fas) else 0.0
    if pos_repl:
        vals = list(pos_repl.values())
        pos_repl["UTIL"] = max(vals) + float(np.std(vals))
        pos_repl["MI"] = max(pos_repl.get("2B", 0.0), pos_repl.get("SS", 0.0))
        pos_repl["CI"] = max(pos_repl.get("1B", 0.0), pos_repl.get("3B", 0.0))

    hitters = hitters.copy()
    hitters["repl_level"] = hitters["primary_position"].map(pos_repl).fillna(0.0)
    multi = hitters.get("is_multi_position", pd.Series(False, index=hitters.index)).astype(float) * 0.5
    hitters["pos_adj_werth"] = hitters["repl_level"].abs() + hitters["total_werth"] + multi

    pit_repl = _small_avg(fa_p["total_werth"], k=3) if len(fa_p) else 0.0
    pitchers = pitchers.copy()
    pitchers["repl_level"] = pit_repl
    pitchers["pos_adj_werth"] = abs(pit_repl) + pitchers["total_werth"]
    return hitters, pitchers


def compute_werth(ros_bat, ros_pit, rostered_ids, fa_ids, *, regulars_only=True, repl_k=2):
    """§4.4-fixed RoS WERTH. Drop-in for ``ros_werth.compute_ros_werth`` from context."""
    import ros_werth
    pool = regular_pool(ros_bat, ros_pit, rostered_ids) if regulars_only else set(rostered_ids or [])
    if not pool:                      # safety: never hand an empty pool to the backend
        pool = set(rostered_ids or [])
    hitters, pitchers = ros_werth.compute_ros_werth(
        ros_bat, ros_pit, rostered_espn_ids=pool, fa_espn_ids=fa_ids)
    hitters, pitchers = apply_small_avg_replacement(hitters, pitchers, fa_ids, k=repl_k)
    return hitters, pitchers


def proj_per_game(row, kind):
    """RoS projection row -> per-game component rates (the simulator's anchor/fallback).

    Estimates games from PA (hitters: PA/4.3) or IP (pitchers: IP/5.2 starts). Rough by
    design — it only anchors the thin-sample fallback and the overlay recentering.
    """
    g = lambda key: float(row.get(key, 0.0) or 0.0)
    if kind == "hitter":
        pa = g("PA")
        games = max(pa / _PA_PER_GAME, 1.0)
        return {
            "R": g("R") / games, "HR": g("HR") / games, "TB": g("TB") / games,
            "RBI": g("RBI") / games, "SBN": g("SBN") / games,
            "onbase": (g("OBP") * pa) / games if pa > 0 else 0.0,
            "pa": pa / games if games else _PA_PER_GAME,
        }
    ip = g("IP")
    games = max(ip / _IP_PER_START, 1.0)
    era, whip, kbb, k = g("ERA"), g("WHIP"), g("KBB"), g("K")
    # Recover components: BB = K / (K/BB); H = WHIP*IP - BB; ER = ERA*IP/9.
    bb_season = (k / kbb) if kbb > 0 else 0.0
    h_season = max(whip * ip - bb_season, 0.0) if ip > 0 else 0.0
    er_season = era * ip / 9.0 if ip > 0 else 0.0
    return {
        "K": k / games, "QS": g("QS") / games, "SVHD": g("SVHD") / games,
        "ER": er_season / games, "outs": (ip / games) * 3.0,
        "H": h_season / games, "BB": bb_season / games,
    }
