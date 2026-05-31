"""Monte-Carlo rest-of-matchup win-probability simulator (keystone, plan §3.3).

Method (Teddy-corrected, research.md §8 D5): week-ahead variance is *sampling*
randomness over a handful of games, NOT the RoS talent-uncertainty matrix. So the
primary generator **bootstraps a player's recent real game/start component lines**
— resampling whole-game vectors preserves within-game cross-category correlation
and playing-time for free, and lets ratio categories aggregate correctly (sum the
components, then divide — never average ratios). A light talent overlay shrinks the
bootstrap mean toward the RoS projection (anchor) and widens thin samples.

Design split for testability:
  * ``player_week_draws`` turns one player's recent lines (or a projection fallback)
    into ``n`` weekly COMPONENT draws (summed over ``games_remaining``).
  * ``simulate_matchup`` aggregates pre-computed per-player draws into team totals,
    adds banked components, derives the 12 categories, and compares — it is pure
    given the draws, so the statistics are golden-testable.

Inter-player correlation is ignored in v1 (Teddy); ~200 sims by default.
"""

import numpy as np

from advisor import config as cfg

# Per-game component schemas. Counting cats map to themselves; rate cats are built
# from these components at the TEAM level.
HITTER_COMPONENTS = ["R", "HR", "TB", "RBI", "SBN", "onbase", "pa"]
PITCHER_COMPONENTS = ["K", "QS", "ER", "outs", "H", "BB", "SVHD"]
ALL_COMPONENTS = HITTER_COMPONENTS + PITCHER_COMPONENTS

# Categories that are pure counting sums of a single component.
_COUNTING_CAT_COMPONENT = {
    "R": "R", "HR": "HR", "TB": "TB", "RBI": "RBI", "SBN": "SBN",
    "K": "K", "QS": "QS", "SVHD": "SVHD",
}

MIN_BOOTSTRAP_GAMES = 5   # below this, fall back to the projection generator
_EPS = 1e-9
_NO_IP_ERA = 99.0         # sentinel when a team throws zero innings (loses ratio cats)
_NO_IP_WHIP = 99.0


# --------------------------------------------------------------------------- #
# Per-player weekly draws
# --------------------------------------------------------------------------- #

def _rows_to_matrix(rows, components):
    """List[dict] recent game lines -> (G, C) float matrix in ``components`` order."""
    if not rows:
        return np.zeros((0, len(components)), dtype=float)
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in components] for r in rows],
                    dtype=float)


def bootstrap_draws(rows, games_remaining, n, rng, components):
    """Resample whole game lines with replacement and sum over games_remaining.

    Returns {component -> ndarray[n]}. Preserves within-game correlation + PT.
    """
    out_shape = np.zeros(n, dtype=float)
    if games_remaining <= 0 or len(rows) == 0:
        return {c: out_shape.copy() for c in components}
    mat = _rows_to_matrix(rows, components)          # (G, C)
    idx = rng.integers(0, mat.shape[0], size=(n, games_remaining))
    totals = mat[idx].sum(axis=1)                    # (n, C)
    return {c: totals[:, i] for i, c in enumerate(components)}


def _projection_fallback(proj_per_game, games_remaining, n, rng, components, sigma=None):
    """Generator for players with too few recent games (call-ups, returnees).

    Draws each component as a Normal around ``proj_per_game[c] * games_remaining``
    with a coefficient-of-variation widened by role/talent ``sigma`` (or a default).
    Non-negative; counting components rounded to integers.
    """
    out = {}
    g = max(games_remaining, 0)
    for c in components:
        mean = float(proj_per_game.get(c, 0.0) or 0.0) * g
        if mean <= 0:
            out[c] = np.zeros(n, dtype=float)
            continue
        cv = 0.0
        if sigma and c in sigma and mean > 0:
            cv = min(float(sigma[c]) / max(mean, _EPS), 1.0)
        sd = max(cv * mean, 0.35 * np.sqrt(max(mean, 1.0)))  # floor: Poisson-ish spread
        draws = rng.normal(mean, sd, size=n)
        draws = np.clip(draws, 0.0, None)
        if c not in ("onbase", "pa", "outs", "ER"):
            draws = np.round(draws)
        out[c] = draws
    return out


def player_week_draws(gamelog, proj, games_remaining, n, rng, *, kind="hitter",
                      sigma=None, shrink=0.25):
    """``n`` weekly component draws for one player, summed over ``games_remaining``.

    gamelog: list of per-game component dicts (recent healthy games/starts).
    proj:    per-game projected component rates (the anchor; also the fallback mean).
    sigma:   {component -> std} talent/role band (§4.4 #2); widens the fallback and
             the overlay for thin samples.
    shrink:  overlay weight pulling the bootstrap MEAN toward the projection mean
             (0 = pure bootstrap). Spread is preserved.
    """
    components = HITTER_COMPONENTS if kind == "hitter" else PITCHER_COMPONENTS
    rows = gamelog or []
    if len(rows) >= MIN_BOOTSTRAP_GAMES and games_remaining > 0:
        draws = bootstrap_draws(rows, games_remaining, n, rng, components)
        if shrink > 0 and proj:
            for c in components:
                proj_total = float(proj.get(c, 0.0) or 0.0) * games_remaining
                cur_mean = float(draws[c].mean())
                draws[c] = draws[c] + shrink * (proj_total - cur_mean)  # recenter only
                draws[c] = np.clip(draws[c], 0.0, None)
        return draws
    # Thin sample -> projection generator.
    return _projection_fallback(proj or {}, games_remaining, n, rng, components, sigma=sigma)


# --------------------------------------------------------------------------- #
# Team aggregation + category derivation
# --------------------------------------------------------------------------- #

def team_totals(player_draws, n):
    """Sum per-player component draws into team component totals {comp -> ndarray[n]}."""
    totals = {c: np.zeros(n, dtype=float) for c in ALL_COMPONENTS}
    for draws in player_draws:
        for c, arr in draws.items():
            if c in totals:
                totals[c] = totals[c] + np.asarray(arr, dtype=float)
    return totals


def add_banked(totals, banked_components):
    """Add banked component totals (already-accrued) to simulated remaining totals.

    ``banked_components`` is a {component -> scalar} dict. Counting cats come straight
    from category_state; rate-cat components (onbase/pa/ER/outs/H/BB) are estimated by
    the caller (context) from elapsed days — see plan §3.3 / kb. Adding COMPONENTS
    (not rates) keeps ratio aggregation correct.
    """
    if not banked_components:
        return totals
    out = {}
    for c, arr in totals.items():
        out[c] = arr + float(banked_components.get(c, 0.0) or 0.0)
    return out


def derive_cats(totals):
    """Team component totals -> the 12 category values (each an ndarray[n]).

    Ratio cats sum components THEN divide (never average). LOWER_IS_BETTER cats
    (ERA/WHIP) get a large sentinel when no innings were thrown, so they lose.
    """
    cats = {}
    for cat, comp in _COUNTING_CAT_COMPONENT.items():
        cats[cat] = totals[comp]

    pa = totals["pa"]
    cats["OBP"] = np.where(pa > 0, totals["onbase"] / np.maximum(pa, _EPS), 0.0)

    outs = totals["outs"]
    ip = outs / 3.0
    has_ip = outs > 0
    cats["ERA"] = np.where(has_ip, 9.0 * totals["ER"] / np.maximum(ip, _EPS), _NO_IP_ERA)
    cats["WHIP"] = np.where(has_ip, (totals["H"] + totals["BB"]) / np.maximum(ip, _EPS), _NO_IP_WHIP)
    bb = totals["BB"]
    cats["KBB"] = np.where(bb > 0, totals["K"] / np.maximum(bb, _EPS), totals["K"])  # BB=0 -> K/1
    return cats


# --------------------------------------------------------------------------- #
# Matchup simulation
# --------------------------------------------------------------------------- #

def _cat_win_mask(my_vals, opp_vals, cat):
    """Boolean[n]: did MY team win this category per sim? (ties -> False)."""
    if cat in cfg.LOWER_IS_BETTER:
        return my_vals < opp_vals
    return my_vals > opp_vals


def simulate_matchup(my_player_draws, opp_player_draws, banked_my=None, banked_opp=None,
                     n=200, seed=None):
    """Aggregate pre-computed per-player draws -> per-cat P(win) + overall.

    my_player_draws / opp_player_draws: list of {component -> ndarray[n]} (from
    ``player_week_draws``). banked_my / banked_opp: {component -> scalar} accrued
    totals. Returns the WinProb dict (per_cat + overall).
    """
    my_tot = add_banked(team_totals(my_player_draws, n), banked_my)
    opp_tot = add_banked(team_totals(opp_player_draws, n), banked_opp)
    my_cats = derive_cats(my_tot)
    opp_cats = derive_cats(opp_tot)

    cats_won = np.zeros(n, dtype=int)
    opp_cats_won = np.zeros(n, dtype=int)
    per_cat = {}
    for cat in cfg.ALL_CATS:
        win = _cat_win_mask(my_cats[cat], opp_cats[cat], cat)
        loss = _cat_win_mask(opp_cats[cat], my_cats[cat], cat)
        cats_won += win
        opp_cats_won += loss
        p_win = float(win.mean())
        per_cat[cat] = {
            "p_win": round(p_win, 4),
            "you_proj": round(float(np.mean(my_cats[cat])), 3),
            "opp_proj": round(float(np.mean(opp_cats[cat])), 3),
            "status": _cat_status(p_win),
        }

    p_win_matchup = float(np.mean(cats_won > opp_cats_won))
    p_tie = float(np.mean(cats_won == opp_cats_won))
    # Distribution of categories won (0..12).
    counts = np.bincount(cats_won, minlength=len(cfg.ALL_CATS) + 1)
    record_dist = {str(i): round(float(counts[i] / n), 4) for i in range(len(counts)) if counts[i]}

    return {
        "overall": {
            "p_win_matchup": round(p_win_matchup, 4),
            "p_tie": round(p_tie, 4),
            "expected_cats_won": round(float(np.mean(cats_won)), 2),
            "record_dist": record_dist,
        },
        "by_cat": per_cat,
        "n_sims": n,
    }


def _cat_status(p_win):
    if p_win >= 0.99:
        return "clinched"
    if p_win <= 0.01:
        return "lost"
    return "live-swing"


def _draws_for_inputs(inputs, n, rng):
    """Build per-player weekly draws from a list of player input dicts.

    Each input: {gamelog, proj, kind, games_remaining, sigma?, shrink?}. Returns
    (draws_list, draws_by_id) so EV-of-move can drop a specific player by espn_id.
    """
    draws_list, draws_by_id = [], {}
    for p in inputs:
        d = player_week_draws(
            p.get("gamelog"), p.get("proj") or {}, p.get("games_remaining", 0), n, rng,
            kind=p.get("kind", "hitter"), sigma=p.get("sigma"),
            shrink=p.get("shrink", 0.25))
        draws_list.append(d)
        if p.get("espn_id") is not None:
            draws_by_id[p["espn_id"]] = d
    return draws_list, draws_by_id


def run_matchup(my_inputs, opp_inputs, *, banked_my=None, banked_opp=None, n=200, seed=None):
    """High-level: build draws from player inputs, simulate, return (winprob, draws).

    ``draws`` = {"my_list", "my_by_id", "opp_list"} so a caller can compute ev_of_move
    against the same realized draws.
    """
    rng = np.random.default_rng(seed)
    my_list, my_by_id = _draws_for_inputs(my_inputs, n, rng)
    opp_list, _ = _draws_for_inputs(opp_inputs, n, rng)
    winprob = simulate_matchup(my_list, opp_list, banked_my=banked_my,
                               banked_opp=banked_opp, n=n, seed=seed)
    return winprob, {"my_list": my_list, "my_by_id": my_by_id, "opp_list": opp_list}


def ev_of_move(my_player_draws, opp_player_draws, *, banked_my=None, banked_opp=None,
               add_draws=None, remove_espn_id=None, draws_by_id=None, n=200, seed=None):
    """EV of a roster move = Δ in matchup win-prob (the computed bar streaming must clear).

    Re-simulates with the move applied. The base lineup's per-player draws are keyed
    by espn_id in ``draws_by_id`` (so we can drop a player); ``add_draws`` is the new
    player's weekly draws. Returns {d_p_overall, d_by_cat, ratio_safe, before, after}.
    """
    base = simulate_matchup(my_player_draws, opp_player_draws,
                            banked_my=banked_my, banked_opp=banked_opp, n=n, seed=seed)

    moved = list(my_player_draws)
    if remove_espn_id is not None and draws_by_id is not None:
        drop = draws_by_id.get(remove_espn_id)
        if drop is not None:
            moved = [d for d in moved if d is not drop]
    if add_draws is not None:
        moved = moved + [add_draws]

    after = simulate_matchup(moved, opp_player_draws,
                             banked_my=banked_my, banked_opp=banked_opp, n=n, seed=seed)

    d_by_cat = {cat: round(after["by_cat"][cat]["p_win"] - base["by_cat"][cat]["p_win"], 4)
                for cat in cfg.ALL_CATS}
    # ratio_safe: the move does not meaningfully degrade ERA or WHIP P(win).
    ratio_safe = (d_by_cat.get("ERA", 0.0) >= -0.01) and (d_by_cat.get("WHIP", 0.0) >= -0.01)
    return {
        "d_p_overall": round(after["overall"]["p_win_matchup"] - base["overall"]["p_win_matchup"], 4),
        "d_by_cat": d_by_cat,
        "ratio_safe": bool(ratio_safe),
        "before": base["overall"]["p_win_matchup"],
        "after": after["overall"]["p_win_matchup"],
    }
