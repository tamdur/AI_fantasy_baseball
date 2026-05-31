"""Phase-2 valuation §4.4 fixes: regulars pool (#1), small-average replacement (#4),
and the per-game projection anchor used by the simulator."""

import numpy as np
import pandas as pd

from advisor import valuation as V


def test_regular_pool_keeps_top_pt_excludes_bench(monkeypatch):
    # Shrink the per-team slot counts so the cap is small and testable (cap = 8*1 = 8).
    monkeypatch.setattr(V, "_HITTING_STARTER_SLOTS", 1)
    monkeypatch.setattr(V, "_PITCHER_STARTER_SLOTS", 1)

    bat = pd.DataFrame({"espn_id": list(range(1, 11)),
                        "PA": [100 * i for i in range(1, 11)]})   # PA 100..1000
    pit = pd.DataFrame({"espn_id": [100], "IP": [120]})
    rostered = set(range(1, 11)) | {100, 999}                     # 999 is a FA, not in df

    pool = V.regular_pool(bat, pit, rostered)
    # Top 8 hitters by PA = ids 3..10; ids 1,2 (lowest PA) excluded as bench.
    assert {3, 4, 5, 6, 7, 8, 9, 10}.issubset(pool)
    assert 1 not in pool and 2 not in pool
    assert 100 in pool          # the one rostered pitcher
    assert 999 not in pool      # not a rostered df row


def test_small_avg_is_robust_to_a_single_skewed_fa():
    s = pd.Series([10.0, 1.0, 0.5, 0.4])   # one hot FA at 10
    assert V._small_avg(s, k=1) == 10.0    # single-max is skewed
    assert V._small_avg(s, k=2) == 5.5     # top-2 mean dampens it
    assert V._small_avg(pd.Series([], dtype=float)) == 0.0


def test_apply_small_avg_replacement_overrides_repl_level():
    hitters = pd.DataFrame({
        "espn_id": [1, 2, 3, 4],
        "primary_position": ["OF", "OF", "OF", "OF"],
        "total_werth": [8.0, 2.0, 1.5, 1.0],   # ids 2,3,4 are FAs (one is hot at 2.0)
        "is_multi_position": [False, False, False, False],
    })
    pitchers = pd.DataFrame({"espn_id": [10, 11, 12, 13],
                             "total_werth": [5.0, 1.0, 0.8, 0.6]})
    fa_ids = {2, 3, 4, 11, 12, 13}
    h, p = V.apply_small_avg_replacement(hitters, pitchers, fa_ids, k=2)

    # OF replacement = top-2 FA mean = mean(2.0, 1.5) = 1.75 (not the single max 2.0).
    of_repl = h.loc[h["espn_id"] == 1, "repl_level"].iloc[0]
    assert abs(of_repl - 1.75) < 1e-9
    # pos_adj_werth = |repl| + total_werth for the rostered stud (id 1).
    assert abs(h.loc[h["espn_id"] == 1, "pos_adj_werth"].iloc[0] - (1.75 + 8.0)) < 1e-9


def test_proj_per_game_recovers_consistent_pitcher_components():
    row = {"IP": 100, "ERA": 3.6, "WHIP": 1.1, "KBB": 4.0, "K": 120, "QS": 15, "SVHD": 0}
    pg = V.proj_per_game(row, "pitcher")
    games = max(100 / V._IP_PER_START, 1.0)
    # Reconstruct season totals and check the ratio cats invert exactly.
    ip = pg["outs"] * games / 3.0
    assert abs(ip - 100) < 1e-6
    assert abs(9 * pg["ER"] * games / ip - 3.6) < 1e-6           # ERA
    assert abs((pg["H"] + pg["BB"]) * games / ip - 1.1) < 1e-6   # WHIP
    assert abs(pg["K"] / pg["BB"] - 4.0) < 1e-6                  # K/BB


def test_proj_per_game_hitter_obp_consistent():
    row = {"PA": 600, "R": 90, "HR": 25, "TB": 280, "RBI": 85, "SBN": 15, "OBP": 0.350}
    pg = V.proj_per_game(row, "hitter")
    assert abs(pg["onbase"] / pg["pa"] - 0.350) < 1e-9
    assert abs(pg["pa"] - V._PA_PER_GAME) < 1e-6
