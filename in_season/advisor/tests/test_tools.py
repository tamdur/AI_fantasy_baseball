"""Phase-3 tools: form summary + EV recomputation over a synthetic sim-state."""

import numpy as np

from advisor import tools as T


def test_summarize_form_pitcher_rates():
    rows = [{"K": 8, "QS": 1, "ER": 2, "outs": 18, "H": 5, "BB": 1, "SVHD": 0},
            {"K": 6, "QS": 1, "ER": 1, "outs": 18, "H": 4, "BB": 2, "SVHD": 0}]
    s = T.summarize_form(rows, "pitcher")
    assert s["games"] == 2
    assert s["ERA"] == round(9 * 3 / 12, 2)          # 3 ER over 12 IP
    assert s["WHIP"] == round((9 + 3) / 12, 2)
    assert s["QS"] == 2


def test_summarize_form_hitter_obp():
    rows = [{"R": 1, "HR": 0, "TB": 2, "RBI": 1, "SBN": 0, "onbase": 2, "pa": 4}] * 5
    s = T.summarize_form(rows, "hitter")
    assert s["OBP"] == 0.5 and s["games"] == 5


def _sim_state(n=200, seed=3):
    rng = np.random.default_rng(0)

    def hgl():
        return [{"R": 1, "HR": int(rng.random() < 0.08), "TB": 2, "RBI": 1, "SBN": 0,
                 "onbase": 2, "pa": 4} for _ in range(20)]

    def pgl(strong=False):
        return [{"K": 8 if strong else 5, "QS": 1 if strong else 0,
                 "ER": 1 if strong else 3, "outs": 18, "H": 4 if strong else 7,
                 "BB": 1 if strong else 3, "SVHD": 0} for _ in range(12)]

    my = [{"espn_id": i, "gamelog": hgl(), "proj": {}, "kind": "hitter",
           "games_remaining": 5, "shrink": 0.0} for i in range(7)]
    my += [{"espn_id": 200 + i, "gamelog": pgl(), "proj": {}, "kind": "pitcher",
            "games_remaining": 2, "shrink": 0.0} for i in range(5)]
    opp = [{"espn_id": 100 + i, "gamelog": hgl(), "proj": {}, "kind": "hitter",
            "games_remaining": 5, "shrink": 0.0} for i in range(7)]
    opp += [{"espn_id": 300 + i, "gamelog": pgl(), "proj": {}, "kind": "pitcher",
             "games_remaining": 2, "shrink": 0.0} for i in range(5)]
    return {"n": n, "seed": seed, "my_inputs": my, "opp_inputs": opp,
            "banked_my": None, "banked_opp": None}, pgl(strong=True)


def test_stream_impact_strong_pitcher_helps_or_neutral():
    state, strong_pgl = _sim_state()
    streamer = {"gamelog": strong_pgl, "proj": {}, "kind": "pitcher", "games_remaining": 1}
    ev = T.compute_stream_impact(state, streamer)
    assert np.isfinite(ev["d_p_overall"])
    assert set(ev["d_by_cat"])  # has per-cat deltas
    # A strong QS/ratio pitcher should not hurt the ratio categories.
    assert ev["ratio_safe"] is True


def test_drop_check_contribution_sign():
    state, _ = _sim_state()
    ev = T.compute_drop_impact(state, drop_espn_id=200)   # drop a pitcher, no replacement
    # Dropping a contributing pitcher should not INCREASE win prob (contribution >= ~0).
    assert ev["d_p_overall"] <= 0.05
