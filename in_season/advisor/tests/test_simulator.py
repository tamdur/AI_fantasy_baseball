"""Phase-2 simulator: ratio aggregation (golden), banked-once, lower-is-better,
determinism, monotonicity, and EV-of-move. Property-style checks use deterministic
seeded loops (no hypothesis dependency — kb)."""

import numpy as np

from advisor import config as cfg
from advisor import simulator as S


def _arr(v, n=1):
    return np.full(n, float(v))


def test_derive_cats_golden_ratio_aggregation():
    """Sum components THEN divide — the classic error guard. Hand-computed values."""
    totals = {
        "R": _arr(25), "HR": _arr(8), "TB": _arr(80), "RBI": _arr(24), "SBN": _arr(5),
        "onbase": _arr(20), "pa": _arr(50),
        "K": _arr(30), "QS": _arr(3), "SVHD": _arr(2),
        "ER": _arr(4), "outs": _arr(54), "H": _arr(15), "BB": _arr(5),
    }
    cats = S.derive_cats(totals)
    assert cats["R"][0] == 25 and cats["HR"][0] == 8 and cats["SBN"][0] == 5
    assert abs(cats["OBP"][0] - 0.40) < 1e-9            # 20/50
    assert abs(cats["ERA"][0] - 2.0) < 1e-9             # 9*4/18
    assert abs(cats["WHIP"][0] - (20 / 18)) < 1e-9      # (15+5)/18
    assert abs(cats["KBB"][0] - 6.0) < 1e-9             # 30/5


def test_derive_cats_guards_zero_denominators():
    totals = {c: _arr(0) for c in S.ALL_COMPONENTS}
    totals["K"] = _arr(7)  # K with zero BB -> KBB = K/1
    cats = S.derive_cats(totals)
    assert cats["OBP"][0] == 0.0
    assert cats["ERA"][0] == S._NO_IP_ERA      # no innings -> sentinel (loses)
    assert cats["WHIP"][0] == S._NO_IP_WHIP
    assert cats["KBB"][0] == 7.0


def test_banked_added_exactly_once():
    sim = {"R": _arr(10), "onbase": _arr(10), "pa": _arr(25)}
    totals = S.team_totals([sim], n=1)
    banked = {"R": 5, "onbase": 10, "pa": 25}
    combined = S.add_banked(totals, banked)
    assert combined["R"][0] == 15
    cats = S.derive_cats(combined)
    assert abs(cats["OBP"][0] - (20 / 50)) < 1e-9       # banked components combine correctly


def test_lower_is_better_direction():
    """ERA/WHIP: the LOWER team wins the category."""
    my = [{"ER": _arr(2, 200), "outs": _arr(54, 200), "H": _arr(10, 200), "BB": _arr(3, 200),
           "K": _arr(20, 200)}]
    opp = [{"ER": _arr(6, 200), "outs": _arr(54, 200), "H": _arr(20, 200), "BB": _arr(8, 200),
            "K": _arr(20, 200)}]
    res = S.simulate_matchup(my, opp, n=200, seed=1)
    assert res["by_cat"]["ERA"]["p_win"] == 1.0         # my lower ERA wins every sim
    assert res["by_cat"]["WHIP"]["p_win"] == 1.0


def test_pwin_bounds_and_record_dist_sums_to_one():
    rng = np.random.default_rng(7)
    my = [S.player_week_draws(_synth_gamelog(rng, "hitter"), {}, 5, 200, rng, kind="hitter")
          for _ in range(9)]
    op = [S.player_week_draws(_synth_gamelog(rng, "hitter"), {}, 5, 200, rng, kind="hitter")
          for _ in range(9)]
    res = S.simulate_matchup(my, op, n=200, seed=3)
    for cat, d in res["by_cat"].items():
        assert 0.0 <= d["p_win"] <= 1.0
    assert 0.0 <= res["overall"]["p_win_matchup"] <= 1.0
    assert abs(sum(res["overall"]["record_dist"].values()) - 1.0) < 1e-6


def test_determinism_same_seed_same_draws():
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    gl = _synth_gamelog(np.random.default_rng(0), "hitter")
    d1 = S.player_week_draws(gl, {}, 6, 200, rng1, kind="hitter", shrink=0.0)
    d2 = S.player_week_draws(gl, {}, 6, 200, rng2, kind="hitter", shrink=0.0)
    for c in S.HITTER_COMPONENTS:
        assert np.array_equal(d1[c], d2[c])


def test_adding_dominant_player_does_not_lower_pwin():
    """Monotonicity: a strictly additive bat can only help (within MC noise)."""
    rng = np.random.default_rng(11)
    my = [S.player_week_draws(_synth_gamelog(rng, "hitter"), {}, 5, 400, rng, kind="hitter")
          for _ in range(6)]
    op = [S.player_week_draws(_synth_gamelog(rng, "hitter"), {}, 5, 400, rng, kind="hitter")
          for _ in range(6)]
    base = S.simulate_matchup(my, op, n=400, seed=5)["overall"]["p_win_matchup"]
    # A monster hitter (huge counting + on-base, no pitching downside).
    monster = {"R": _arr(40, 400), "HR": _arr(20, 400), "TB": _arr(90, 400),
               "RBI": _arr(40, 400), "SBN": _arr(10, 400), "onbase": _arr(40, 400),
               "pa": _arr(60, 400)}
    boosted = S.simulate_matchup(my + [monster], op, n=400, seed=5)["overall"]["p_win_matchup"]
    assert boosted >= base - 0.02       # never meaningfully worse


def test_ev_of_move_returns_finite_delta_and_ratio_flag():
    rng = np.random.default_rng(9)
    my = [S.player_week_draws(_synth_gamelog(rng, "pitcher"), {}, 2, 200, rng, kind="pitcher")
          for _ in range(5)]
    op = [S.player_week_draws(_synth_gamelog(rng, "pitcher"), {}, 2, 200, rng, kind="pitcher")
          for _ in range(5)]
    streamer = S.player_week_draws(_synth_gamelog(rng, "pitcher", strong=True), {}, 1, 200, rng,
                                   kind="pitcher")
    ev = S.ev_of_move(my, op, add_draws=streamer, n=200, seed=2)
    assert np.isfinite(ev["d_p_overall"])
    assert isinstance(ev["ratio_safe"], bool)
    assert set(ev["d_by_cat"]) == set(cfg.ALL_CATS)


def test_regression_golden_locked_pwin():
    """Lock simulate_matchup numerics for a fixed seed + scenario. If this moves, the
    simulator's behavior changed — investigate before re-baselining."""
    def gl(rng, kind, edge=0.0):
        rows = []
        for _ in range(25):
            if kind == "hitter":
                pa = int(rng.integers(3, 6)); h = int(rng.integers(0, 3))
                hr = 1 if rng.random() < 0.08 + edge else 0; bb = int(rng.integers(0, 2))
                rows.append({"R": int(rng.integers(0, 3)), "HR": hr, "TB": h + 3 * hr,
                             "RBI": int(rng.integers(0, 3)), "SBN": int(rng.integers(0, 2)),
                             "onbase": h + bb, "pa": pa})
            else:
                outs = int(rng.integers(15, 21)); er = int(rng.integers(1, 4))
                rows.append({"K": int(rng.integers(3, 9)), "QS": 1 if (outs >= 18 and er <= 3) else 0,
                             "ER": er, "outs": outs, "H": int(rng.integers(3, 8)),
                             "BB": int(rng.integers(0, 4)), "SVHD": 0})
        return rows

    rng = np.random.default_rng(2026)
    my = [S.player_week_draws(gl(rng, "hitter", 0.03), {}, 5, 300, rng, kind="hitter", shrink=0.0)
          for _ in range(7)]
    my += [S.player_week_draws(gl(rng, "pitcher"), {}, 2, 300, rng, kind="pitcher", shrink=0.0)
           for _ in range(5)]
    op = [S.player_week_draws(gl(rng, "hitter"), {}, 5, 300, rng, kind="hitter", shrink=0.0)
          for _ in range(7)]
    op += [S.player_week_draws(gl(rng, "pitcher"), {}, 2, 300, rng, kind="pitcher", shrink=0.0)
           for _ in range(5)]
    res = S.simulate_matchup(my, op, n=300, seed=1)
    assert abs(res["overall"]["p_win_matchup"] - 0.6067) < 0.01      # HR-edge team favored
    assert abs(res["overall"]["expected_cats_won"] - 5.72) < 0.10


# --- helpers: synthetic recent game lines ---

def _synth_gamelog(rng, kind, strong=False, games=20):
    rows = []
    for _ in range(games):
        if kind == "hitter":
            pa = int(rng.integers(3, 6))
            h = int(rng.integers(0, 3))
            hr = 1 if rng.random() < (0.15 if strong else 0.08) else 0
            bb = int(rng.integers(0, 2))
            rows.append({"R": rng.integers(0, 3), "HR": hr, "TB": h + 3 * hr,
                         "RBI": rng.integers(0, 3), "SBN": rng.integers(0, 2),
                         "onbase": h + bb, "pa": pa})
        else:
            outs = int(rng.integers(15, 21))
            er = int(rng.integers(0, 2)) if strong else int(rng.integers(1, 5))
            rows.append({"K": rng.integers(5, 11) if strong else rng.integers(2, 8),
                         "QS": 1 if (outs >= 18 and er <= 3) else 0,
                         "ER": er, "outs": outs, "H": rng.integers(3, 8),
                         "BB": rng.integers(0, 4), "SVHD": 0})
    return rows
