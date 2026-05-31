"""Thin CLI tools the analyst calls via Bash (plan §1, §3.6).

Each subcommand prints compact JSON to stdout. The EV tools reload the Tier-2 sim
state written by ``context.attach_winprob`` and recompute ``ev_of_move``
deterministically (same seed → same base draws), so the analyst can probe the 2–3
marginal moves that matter without the model doing any arithmetic itself.

  python -m advisor.tools winprob [--date D]
  python -m advisor.tools feasibility [--date D]
  python -m advisor.tools player_form --espn 12345 [--kind pitcher]
  python -m advisor.tools stream_impact --add-mlbam 660271 --kind pitcher [--drop 999] [--games 1]
  python -m advisor.tools drop_check --drop 12345 [--date D]
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import date as _date

import numpy as np

from advisor import config as cfg
from advisor import simulator as sim
from advisor import gamelogs as glmod


def _today():
    return _date.today().isoformat()


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        _emit({"error": f"{Path(path).name} not found — run `python -m advisor.run prepare` first"})
        sys.exit(2)


def _emit(obj):
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


# --- pure helpers (unit-tested) ---

def summarize_form(rows, kind):
    """Recent-form summary from component rows: per-game means + the implied rate cats."""
    if not rows:
        return {"games": 0}
    keys = sim.HITTER_COMPONENTS if kind == "hitter" else sim.PITCHER_COMPONENTS
    per_game = {k: round(float(np.mean([r.get(k, 0.0) for r in rows])), 3) for k in keys}
    out = {"games": len(rows), "per_game": per_game}
    if kind == "hitter":
        pa = sum(r.get("pa", 0) for r in rows)
        ob = sum(r.get("onbase", 0) for r in rows)
        out["OBP"] = round(ob / pa, 3) if pa else None
    else:
        outs = sum(r.get("outs", 0) for r in rows)
        ip = outs / 3.0
        er = sum(r.get("ER", 0) for r in rows)
        h = sum(r.get("H", 0) for r in rows)
        bb = sum(r.get("BB", 0) for r in rows)
        k = sum(r.get("K", 0) for r in rows)
        out["ERA"] = round(9 * er / ip, 2) if ip else None
        out["WHIP"] = round((h + bb) / ip, 2) if ip else None
        out["KBB"] = round(k / bb, 2) if bb else None
        out["QS"] = sum(r.get("QS", 0) for r in rows)
    return out


def compute_stream_impact(sim_state, streamer_input, *, drop_espn_id=None):
    """EV of adding ``streamer_input`` (optionally dropping a player) vs the banked base.

    Pure given sim_state + streamer_input. Returns the ev_of_move dict.
    """
    n = sim_state.get("n", 200)
    seed = sim_state.get("seed", 1)
    rng = np.random.default_rng((seed or 1) + 7)
    my_list, my_by_id = sim._draws_for_inputs(sim_state["my_inputs"], n, rng)
    opp_list, _ = sim._draws_for_inputs(sim_state["opp_inputs"], n, rng)
    add_draws = sim.player_week_draws(
        streamer_input.get("gamelog"), streamer_input.get("proj") or {},
        streamer_input.get("games_remaining", 1), n, rng,
        kind=streamer_input.get("kind", "pitcher"), shrink=streamer_input.get("shrink", 0.25))
    return sim.ev_of_move(my_list, opp_list, banked_my=sim_state.get("banked_my"),
                          banked_opp=sim_state.get("banked_opp"), add_draws=add_draws,
                          remove_espn_id=drop_espn_id, draws_by_id=my_by_id, n=n, seed=seed)


def compute_drop_impact(sim_state, drop_espn_id):
    """EV of dropping a player with no replacement = how much they contribute to P(win)."""
    n = sim_state.get("n", 200)
    seed = sim_state.get("seed", 1)
    rng = np.random.default_rng((seed or 1) + 7)
    my_list, my_by_id = sim._draws_for_inputs(sim_state["my_inputs"], n, rng)
    opp_list, _ = sim._draws_for_inputs(sim_state["opp_inputs"], n, rng)
    return sim.ev_of_move(my_list, opp_list, banked_my=sim_state.get("banked_my"),
                          banked_opp=sim_state.get("banked_opp"),
                          remove_espn_id=drop_espn_id, draws_by_id=my_by_id, n=n, seed=seed)


def _espn_to_mlbam(espn_id):
    id_map = cfg.load_id_map()
    row = id_map[id_map["ESPNID"] == espn_id]
    if len(row):
        v = row.iloc[0]["MLBID"]
        return int(v) if v == v else None  # not NaN
    return None


# --- subcommands ---

def cmd_winprob(args):
    ctx = _load_json(cfg.context_path(args.date))
    _emit(ctx.get("winprob") or {"error": "no winprob in context"})


def cmd_feasibility(args):
    ctx = _load_json(cfg.context_path(args.date))
    _emit(ctx.get("lineup_today") or {"error": "no lineup in context"})


def cmd_player_form(args):
    mlbam = args.mlbam or _espn_to_mlbam(args.espn)
    if mlbam is None:
        _emit({"error": f"no MLBAM id for espn {args.espn}"})
        return
    rows = glmod.fetch_recent_gamelogs(mlbam, args.kind)
    _emit({"espn_id": args.espn, "mlbam_id": mlbam, "kind": args.kind,
           **summarize_form(rows, args.kind)})


def cmd_stream_impact(args):
    state = _load_json(cfg.sim_state_path(args.date))
    rows = glmod.fetch_recent_gamelogs(args.add_mlbam, args.kind)
    streamer = {"gamelog": rows, "proj": {}, "kind": args.kind, "games_remaining": args.games}
    ev = compute_stream_impact(state, streamer, drop_espn_id=args.drop)
    _emit({"add_mlbam": args.add_mlbam, "drop_espn": args.drop, "kind": args.kind,
           "games_remaining": args.games, **ev})


def cmd_drop_check(args):
    state = _load_json(cfg.sim_state_path(args.date))
    ev = compute_drop_impact(state, args.drop)
    _emit({"drop_espn": args.drop, "contribution_to_pwin": -ev["d_p_overall"], **ev})


def build_parser():
    p = argparse.ArgumentParser(prog="advisor.tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("winprob"); w.add_argument("--date", default=_today()); w.set_defaults(fn=cmd_winprob)
    f = sub.add_parser("feasibility"); f.add_argument("--date", default=_today()); f.set_defaults(fn=cmd_feasibility)

    pf = sub.add_parser("player_form")
    pf.add_argument("--espn", type=int); pf.add_argument("--mlbam", type=int)
    pf.add_argument("--kind", choices=["hitter", "pitcher"], default="pitcher")
    pf.set_defaults(fn=cmd_player_form)

    si = sub.add_parser("stream_impact")
    si.add_argument("--add-mlbam", dest="add_mlbam", type=int, required=True)
    si.add_argument("--kind", choices=["hitter", "pitcher"], default="pitcher")
    si.add_argument("--drop", type=int, default=None)
    si.add_argument("--games", type=int, default=1)
    si.add_argument("--date", default=_today())
    si.set_defaults(fn=cmd_stream_impact)

    dc = sub.add_parser("drop_check")
    dc.add_argument("--drop", type=int, required=True)
    dc.add_argument("--date", default=_today())
    dc.set_defaults(fn=cmd_drop_check)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
