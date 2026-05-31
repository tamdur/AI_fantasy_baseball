"""Phase-2 integration: banked-component estimation, two-way detection,
games-remaining approximation, and run_matchup over injected gamelogs (no network)."""

import numpy as np

from advisor import context as C
from advisor import simulator as S


def test_estimate_banked_components_reproduces_rates():
    cat_values = {"R": 10, "HR": 4, "TB": 30, "RBI": 12, "SBN": 3,
                  "K": 30, "QS": 5, "SVHD": 2,
                  "OBP": 0.40, "ERA": 3.0, "WHIP": 1.1, "KBB": 6.0}
    proj_match = {"pa": 200, "outs": 180}
    comp = C.estimate_banked_components(cat_values, proj_match, elapsed_fraction=0.5)

    # Counting cats exact; rate-cat components invert back to the actual rates.
    assert comp["R"] == 10 and comp["K"] == 30 and comp["QS"] == 5
    totals = {k: np.array([float(v)]) for k, v in comp.items()}
    cats = S.derive_cats(totals)
    assert abs(cats["OBP"][0] - 0.40) < 1e-9
    assert abs(cats["ERA"][0] - 3.0) < 1e-9
    assert abs(cats["WHIP"][0] - 1.1) < 1e-9
    assert abs(cats["KBB"][0] - 6.0) < 1e-9


def test_estimate_banked_zero_elapsed_is_empty():
    comp = C.estimate_banked_components({"R": 10, "OBP": 0.4}, {"pa": 200, "outs": 180}, 0.0)
    assert comp["onbase"] == 0.0 and comp["outs"] == 0.0


def test_detect_two_way():
    roster = [
        {"espn_id": 1, "raw_eligible_slots": [12, 13, 14, 16]},   # UTIL + P -> two-way
        {"espn_id": 2, "raw_eligible_slots": [5, 12, 16]},        # OF only -> not
        {"espn_id": 3, "raw_eligible_slots": [13, 15, 16]},       # P only -> not
    ]
    assert C._detect_two_way(roster) == {1}


def test_games_remaining_approximation():
    assert C._games_remaining_for("hitter", None, 6) == 6
    assert C._games_remaining_for("pitcher", {"pitcher_type": "SP"}, 6) == 1     # ~every 5th day
    assert C._games_remaining_for("pitcher", {"pitcher_type": "RP"}, 6) == 4     # ~0.6/day
    assert C._games_remaining_for("pitcher", {"pitcher_type": "SP"}, 1) == 0


def test_run_matchup_over_injected_gamelogs():
    """End-to-end: player inputs -> draws -> simulate, deterministic and bounded."""
    rng = np.random.default_rng(0)

    def hl():
        return [{"R": int(rng.integers(0, 3)), "HR": int(rng.random() < 0.1), "TB": 2,
                 "RBI": 1, "SBN": 0, "onbase": 2, "pa": 4} for _ in range(20)]

    my = [{"espn_id": i, "gamelog": hl(), "proj": {}, "kind": "hitter",
           "games_remaining": 5, "shrink": 0.0} for i in range(9)]
    op = [{"espn_id": 100 + i, "gamelog": hl(), "proj": {}, "kind": "hitter",
           "games_remaining": 5, "shrink": 0.0} for i in range(9)]

    wp1, draws = S.run_matchup(my, op, n=200, seed=7)
    wp2, _ = S.run_matchup(my, op, n=200, seed=7)
    assert wp1["overall"]["p_win_matchup"] == wp2["overall"]["p_win_matchup"]   # deterministic
    assert 0.0 <= wp1["overall"]["p_win_matchup"] <= 1.0
    assert set(wp1["by_cat"]) == set(__import_all_cats())
    assert 100 in draws["my_by_id"] or 0 in draws["my_by_id"]   # keyed by espn_id


def __import_all_cats():
    from advisor import config as cfg
    return cfg.ALL_CATS
