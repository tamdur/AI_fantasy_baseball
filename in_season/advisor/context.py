"""Decision context: the compact substrate the analyst reads each run.

``build_decision_context(date)`` mirrors the ``run_newsletter`` fetch spine but emits
a *compact* JSON (≪ the old briefing book) of pre-computed facts: matchup meta,
strategic posture, banked category state, both rosters joined to RoS WERTH + IL
eligibility + platoon magnitude + projection-disagreement (σ) bands, and the
candidate transactions. The simulator win-probabilities (Phase 2) and the
deterministic optimal lineup (Phase 1) are attached to this context by their
respective phases; here they are ``None`` placeholders.

The context is written to **Tier-2 scratch** (ephemeral, gitignored — plan §1.1):
it is read by the analyst in the same run, then discarded. Only the rendered page
and the decision log are committed.

Network/credential-dependent work lives in ``build_decision_context``; the pure
``assemble_context`` and the per-player compaction helpers are import-safe and unit
tested with synthetic inputs.
"""

import json
import logging
from datetime import date as _date

from advisor import config as cfg

log = logging.getLogger("advisor.context")

# Per-player WERTH fields surfaced into the compact context (subset of the full
# ros_werth columns — the analyst reasons on these, not the raw projection rows).
_HITTER_Z = ["z_R", "z_HR", "z_TB", "z_RBI", "z_SBN", "z_OBP"]
_PITCHER_Z = ["z_K", "z_QS", "z_ERA", "z_WHIP", "z_KBB", "z_SVHD"]


def _round(x, n=3):
    """Round floats for compactness; pass through non-numerics and None."""
    try:
        if x is None:
            return None
        return round(float(x), n)
    except (TypeError, ValueError):
        return x


def compact_player(player, *, werth_by_espn, mlbam_by_espn=None,
                   platoon_by_mlbam=None, sigma_by_mlbam=None, light=False):
    """Compact one roster player for the decision context.

    Pure: takes the parsed ESPN player dict plus pre-built lookup dicts and returns
    a compact record. ``light=True`` (opponent players) drops the WERTH z-vector and
    keeps just the headline value, to stay within the repo/token budget.

    Lookups:
      werth_by_espn   : {espn_id -> ros_werth row dict (with z_*, total_werth, ...)}
      mlbam_by_espn   : {espn_id -> mlbam_id}  (ID bridge; for platoon/σ joins)
      platoon_by_mlbam: {mlbam_id -> platoon dict with 'platoon_obp_gap', ...}
      sigma_by_mlbam  : {mlbam_id -> {stat -> std}}  (§4.4 #2 disagreement band)
    """
    espn_id = player.get("espn_id")
    rec = {
        "espn_id": espn_id,
        "name": player.get("name"),
        "team": player.get("pro_team_abbrev", ""),
        "positions": player.get("positions", []),
        "il_eligible": bool(player.get("il_eligible", False)),
        "injury_status": player.get("injury_status", "ACTIVE"),
        "lineup_slot": player.get("lineup_slot", ""),
        "games_remaining": player.get("games_remaining_this_week"),
    }
    # Raw eligible slot IDs are needed by the feasibility optimizer (slot 17 etc.);
    # keep them on the full (non-light) records only.
    if not light:
        rec["raw_eligible_slots"] = player.get("raw_eligible_slots", [])

    werth = werth_by_espn.get(espn_id) if werth_by_espn else None
    if werth is not None:
        rec["werth"] = _round(werth.get("pos_adj_werth"))
        rec["total_werth"] = _round(werth.get("total_werth"))
        rec["repl_level"] = _round(werth.get("repl_level"))
        rec["is_starter"] = bool(werth.get("is_starter", False))
        if not light:
            zcols = _HITTER_Z if "z_R" in werth else _PITCHER_Z
            rec["z"] = {c[2:]: _round(werth.get(c)) for c in zcols if werth.get(c) is not None}
    else:
        # No WERTH row → likely an ID-bridge miss (stale map ⇒ silent WERTH=0). The
        # context build records the miss rate as a data_warning; here we flag the player.
        rec["werth"] = None
        rec["werth_missing"] = True

    if not light and mlbam_by_espn is not None:
        mlbam = mlbam_by_espn.get(espn_id)
        if mlbam is not None:
            if platoon_by_mlbam and mlbam in platoon_by_mlbam:
                p = platoon_by_mlbam[mlbam]
                rec["platoon_obp_gap"] = _round(p.get("platoon_obp_gap"))  # §4.4 #6 magnitude
            if sigma_by_mlbam and mlbam in sigma_by_mlbam:
                rec["sigma"] = {k: _round(v) for k, v in sigma_by_mlbam[mlbam].items()}  # §4.4 #2
    return rec


def _build_lookups(ros_hitters, ros_pitchers, id_map=None,
                   platoon_splits=None, sigma_bat=None, sigma_pit=None):
    """Build the lookup dicts compact_player needs from the fetched frames.

    Returns (werth_by_espn, mlbam_by_espn, platoon_by_mlbam, sigma_by_mlbam).
    """
    werth_by_espn = {}
    for df in (ros_hitters, ros_pitchers):
        if df is None:
            continue
        for row in df.to_dict("records"):
            eid = row.get("espn_id")
            if eid is not None and not (isinstance(eid, float) and eid != eid):  # not NaN
                werth_by_espn[int(eid)] = row

    mlbam_by_espn = {}
    if id_map is not None:
        for _, r in id_map.dropna(subset=["ESPNID", "MLBID"]).iterrows():
            mlbam_by_espn[int(r["ESPNID"])] = int(r["MLBID"])

    platoon_by_mlbam = dict(platoon_splits) if platoon_splits else {}

    sigma_by_mlbam = {}
    for df in (sigma_bat, sigma_pit):
        if df is None:
            continue
        for row in df.to_dict("records"):
            mlbam = row.get("mlbam_id")
            if mlbam is None or (isinstance(mlbam, float) and mlbam != mlbam):
                continue
            stds = {k[:-4]: v for k, v in row.items()
                    if k.endswith("_std") and v is not None}
            if stds:
                sigma_by_mlbam[int(mlbam)] = stds
    return werth_by_espn, mlbam_by_espn, platoon_by_mlbam, sigma_by_mlbam


def assemble_context(*, date_str, matchup_meta, posture, category_state,
                     category_triage, my_roster, opponent_roster, candidates,
                     swing_categories, lookups, vegas=None, data_warnings=None):
    """Pure assembler: fetched+computed inputs -> the compact context dict.

    Phase-0 sections only. ``lineup_today`` (Phase 1 feasibility) and ``winprob``
    (Phase 2 simulator) are attached later and start as None.
    """
    werth_by_espn, mlbam_by_espn, platoon_by_mlbam, sigma_by_mlbam = lookups

    def _compact(roster, light):
        return [
            compact_player(p, werth_by_espn=werth_by_espn, mlbam_by_espn=mlbam_by_espn,
                           platoon_by_mlbam=platoon_by_mlbam, sigma_by_mlbam=sigma_by_mlbam,
                           light=light)
            for p in roster
        ]

    my_compact = _compact(my_roster, light=False)
    miss = sum(1 for p in my_compact if p.get("werth_missing"))
    warnings = list(data_warnings or [])
    if miss:
        warnings.append(f"{miss} of {len(my_compact)} rostered players missing WERTH "
                        f"(ID-bridge miss — check SFBB map freshness)")

    return {
        "date": date_str,
        "matchup_week": matchup_meta.get("matchup_period_id"),
        "matchup_day": matchup_meta.get("day_of_matchup"),
        "matchup_length_days": matchup_meta.get("matchup_length_days"),
        "days_remaining": matchup_meta.get("days_remaining"),
        "moves_used": matchup_meta.get("moves_used"),       # filled in Phase 3
        "moves_max": matchup_meta.get("moves_max"),
        "opponent": matchup_meta.get("opponent_name"),
        "opponent_team_id": matchup_meta.get("opponent_team_id"),
        "strategic_posture": posture,
        "category_state": category_state,
        "category_triage": category_triage,
        "swing_categories": swing_categories,
        "my_roster": my_compact,
        "opponent_roster": _compact(opponent_roster, light=True),
        "candidates": candidates,
        "vegas": vegas,
        "lineup_today": None,   # Phase 1 (feasibility) attaches the optimal lineup
        "winprob": None,        # Phase 2 (simulator) attaches per-cat + overall P(win)
        "data_warnings": warnings,
        "props": None,          # deferred entirely for v1 (annotation #4)
    }


def write_context(context, date_str=None):
    """Write the context to Tier-2 scratch (ephemeral). Returns the path."""
    date_str = date_str or context.get("date")
    path = cfg.context_path(date_str)
    with open(path, "w") as f:
        json.dump(context, f, indent=2, default=str)
    log.info("Wrote decision context -> %s", path)
    return path


def build_decision_context(date=None, *, write=True):
    """Live orchestration: fetch backend data, compute WERTH, assemble compact context.

    Mirrors the run_newsletter spine but emits the compact context, not a briefing
    book. Requires ESPN credentials + network (validated in the Phase-5 dry-run, not
    in unit tests). Phase-1/2 engines (feasibility, simulator) are attached to the
    returned context by their own modules.
    """
    import fetch_espn as espn
    import fetch_fangraphs as fg
    import fetch_mlb as mlb
    import preprocess as pp

    date_str = (date or _date.today().isoformat())
    log.info("Building decision context for %s", date_str)

    # --- ESPN live data ---
    matchup_meta = espn.fetch_current_matchup_period()
    all_rosters = espn.fetch_all_rosters()
    scoring_period_id = matchup_meta.get("scoring_period_id")
    our_matchup, _all = espn.fetch_matchup_scores(scoring_period_id,
                                                  matchup_meta.get("matchup_period_id"))
    standings = espn.fetch_standings()
    free_agents = espn.fetch_free_agents(count=250)

    my_roster = all_rosters.get(cfg.MY_TEAM_ID, {}).get("players", [])
    opp_id = matchup_meta.get("opponent_team_id")
    opponent_roster = all_rosters.get(opp_id, {}).get("players", []) if opp_id else []

    # --- FanGraphs RoS projections + multi-system disagreement (§4.4 #2) ---
    id_map = cfg.load_id_map()
    ros_bat = cfg.join_ids(fg.fetch_ros_projections("bat"), id_map)
    ros_pit = cfg.join_ids(fg.fetch_ros_projections("pit"), id_map)
    sigma_bat = fg.fetch_multi_system_ros("bat")
    sigma_pit = fg.fetch_multi_system_ros("pit")

    rostered_ids = {p["espn_id"] for r in all_rosters.values() for p in r.get("players", [])
                    if p.get("espn_id")}
    fa_ids = {p["espn_id"] for p in free_agents if p.get("espn_id")}
    ros_hitters, ros_pitchers = _compute_werth(ros_bat, ros_pit, rostered_ids, fa_ids)

    # --- MLB schedule (games remaining drives feasibility; §4.4 #8) ---
    two_starters, games_per_team = mlb.fetch_weekly_schedule()
    pp._add_games_remaining(my_roster, games_per_team)
    pp._add_games_remaining(opponent_roster, games_per_team)

    # --- Strategic posture + banked category state ---
    posture = pp._compute_strategic_posture(standings, matchup_meta.get("matchup_period_id"))
    category_state, category_triage = pp.compute_category_state(our_matchup)
    swing_categories = _swing_categories(category_triage)

    # --- Platoon magnitude (§4.4 #6) ---
    try:
        import fetch_extras as extras
        platoon_splits = extras.load_platoon_splits()
    except Exception as e:  # non-fatal: platoon detail is an enhancement, not a gate
        log.warning("platoon splits unavailable: %s", e)
        platoon_splits = {}

    lookups = _build_lookups(ros_hitters, ros_pitchers, id_map=id_map,
                             platoon_splits=platoon_splits,
                             sigma_bat=sigma_bat, sigma_pit=sigma_pit)

    candidates = _build_candidates(free_agents, my_roster, lookups[0])

    context = assemble_context(
        date_str=date_str, matchup_meta=matchup_meta, posture=posture,
        category_state=category_state, category_triage=category_triage,
        my_roster=my_roster, opponent_roster=opponent_roster, candidates=candidates,
        swing_categories=swing_categories, lookups=lookups,
    )

    # Phase 1: deterministic optimal lineup (feasibility-guaranteed).
    werth_by_espn = lookups[0]
    il_ids = {p["espn_id"] for p in my_roster if p.get("il_eligible")}
    two_way_ids = _detect_two_way(my_roster)
    for p in my_roster:
        w = werth_by_espn.get(p.get("espn_id"))
        p["value"] = float(w.get("pos_adj_werth")) if w else 0.0
    try:
        from advisor import feasibility
        context["lineup_today"] = feasibility.optimal_daily_lineup(
            my_roster, plays_today=None, two_way_ids=two_way_ids, pitch_starts_today=None)
    except Exception as e:
        log.warning("lineup optimization failed: %s", e)

    # Phase 2: matchup win-probability (the real P(win) — replaces fabricated numbers).
    try:
        attach_winprob(context, my_roster=my_roster, opponent_roster=opponent_roster,
                       lookups=lookups, matchup_meta=matchup_meta,
                       category_state=category_state, il_ids=il_ids, seed=1)
    except Exception as e:
        log.warning("win-probability simulation failed: %s", e)

    if write:
        write_context(context, date_str)
    return context


def _detect_two_way(roster):
    """Single-entity two-way players: eligible for BOTH a pitcher slot and a hitter slot."""
    two_way = set()
    for p in roster:
        slots = set(p.get("raw_eligible_slots", []))
        has_pitch = bool(slots & {13, 14, 15})
        has_hit = bool(slots & {0, 1, 2, 3, 4, 5, 6, 7, 12})
        if has_pitch and has_hit:
            two_way.add(p["espn_id"])
    return two_way


def _compute_werth(ros_bat, ros_pit, rostered_ids, fa_ids):
    """Thin indirection so Phase-2 valuation.py can swap in the §4.4-fixed pool logic."""
    try:
        from advisor import valuation
        return valuation.compute_werth(ros_bat, ros_pit, rostered_ids, fa_ids)
    except Exception:
        import ros_werth
        return ros_werth.compute_ros_werth(ros_bat, ros_pit,
                                           rostered_espn_ids=rostered_ids, fa_espn_ids=fa_ids)


def _swing_categories(category_triage):
    """Categories most worth fighting over: too-close + losing-flippable buckets."""
    swing = []
    for bucket in ("too_close_to_call", "losing_flippable", "winning_narrow"):
        swing.extend(category_triage.get(bucket, []))
    # Preserve order, dedupe.
    seen = set()
    return [c for c in swing if not (c in seen or seen.add(c))]


def _build_candidates(free_agents, my_roster, werth_by_espn):
    """Phase-0 candidate lists (drop candidates + raw FA pool). Streaming EV (the
    computed bar) and ranked adds are attached in Phase 2/3 once the simulator exists.
    """
    drop_candidates = []
    for p in my_roster:
        eid = p.get("espn_id")
        w = werth_by_espn.get(eid)
        drop_candidates.append({
            "espn_id": eid, "name": p.get("name"), "team": p.get("pro_team_abbrev", ""),
            "il_eligible": bool(p.get("il_eligible", False)),
            "injury_status": p.get("injury_status", "ACTIVE"),
            "pos_adj_werth": _round(w.get("pos_adj_werth")) if w else None,
        })
    return {
        "streamers_today": [],   # Phase 3 (needs simulator ev_of_move)
        "adds": [],              # Phase 3
        "drop_candidates": drop_candidates,
        "free_agent_count": len(free_agents),
    }


# --------------------------------------------------------------------------- #
# Simulator wiring (Phase 2): banked components + live win-probability
# --------------------------------------------------------------------------- #

def estimate_banked_components(cat_values, proj_match, elapsed_fraction):
    """Banked component totals for the matchup-so-far (plan §3.3, kb v1 approximation).

    Counting cats are taken EXACTLY from the live category_state. Rate-cat components
    use the ACTUAL banked rate (OBP/ERA/WHIP/KBB from category_state) with a denominator
    estimated as elapsed_fraction × the team's projected full-matchup denominator
    (``proj_match`` = {"pa", "outs"}). Keeps derive_cats component-based (correct ratio
    aggregation); the only approximation is the banked denominator size.
    """
    from advisor.simulator import _COUNTING_CAT_COMPONENT
    f = max(0.0, min(1.0, elapsed_fraction))
    comp = {c: float(cat_values.get(cat, 0.0) or 0.0)
            for cat, c in _COUNTING_CAT_COMPONENT.items()}
    pa = float(proj_match.get("pa", 0.0) or 0.0) * f
    outs = float(proj_match.get("outs", 0.0) or 0.0) * f
    ip = outs / 3.0
    comp["pa"] = pa
    comp["onbase"] = float(cat_values.get("OBP", 0.0) or 0.0) * pa
    comp["outs"] = outs
    comp["ER"] = (float(cat_values.get("ERA", 0.0) or 0.0) * ip / 9.0) if ip > 0 else 0.0
    kbb = float(cat_values.get("KBB", 0.0) or 0.0)
    bb = (comp["K"] / kbb) if kbb > 0 else 0.0
    comp["BB"] = bb
    comp["H"] = max(float(cat_values.get("WHIP", 0.0) or 0.0) * ip - bb, 0.0) if ip > 0 else 0.0
    return comp


def _player_kind(player, werth_row):
    if werth_row is not None and "pitcher_type" in werth_row and werth_row.get("pitcher_type"):
        return "pitcher"
    return "pitcher" if any(p in ("SP", "RP") for p in player.get("positions", [])) else "hitter"


def _games_remaining_for(kind, werth_row, days_remaining):
    """v1 approximation (kb): hitters play ~daily; SP ~every 5th day; RP most days.
    Refine later with a today→matchup-end schedule fetch."""
    d = max(int(days_remaining or 0), 0)
    if kind == "hitter":
        return d
    ptype = (werth_row or {}).get("pitcher_type", "SP")
    if ptype == "RP":
        return max(round(d * 0.6), 0)
    return max(round(d / 5.0), 1 if d >= 3 else 0)


def _sim_inputs(roster, *, werth_by_espn, mlbam_by_espn, sigma_by_mlbam, days_remaining,
                il_ids, fetch_fn):
    """Build simulator inputs for week-active players (non-IL). Live: fetches gamelogs."""
    from advisor import gamelogs, valuation
    inputs, proj_pa, proj_outs = [], 0.0, 0.0
    for p in roster:
        eid = p.get("espn_id")
        if eid in il_ids:
            continue
        werth = werth_by_espn.get(eid)
        kind = _player_kind(p, werth)
        gr = _games_remaining_for(kind, werth, days_remaining)
        proj = valuation.proj_per_game(werth, kind) if werth is not None else {}
        mlbam = mlbam_by_espn.get(eid)
        gl = []
        if mlbam is not None and gr > 0:
            try:
                gl = gamelogs.fetch_recent_gamelogs(mlbam, kind, fetch_fn=fetch_fn)
            except Exception as e:  # non-fatal: fall back to projection generator
                log.warning("gamelog fetch failed for %s: %s", eid, e)
        sigma = sigma_by_mlbam.get(mlbam) if mlbam is not None else None
        inputs.append({"espn_id": eid, "gamelog": gl, "proj": proj, "kind": kind,
                       "games_remaining": gr, "sigma": sigma})
        # Accumulate projected full-matchup denominators for banked estimation.
        if proj:
            proj_pa += float(proj.get("pa", 0.0)) * gr
            proj_outs += float(proj.get("outs", 0.0)) * gr
    return inputs, {"pa": proj_pa, "outs": proj_outs}


def attach_winprob(context, *, my_roster, opponent_roster, lookups, matchup_meta,
                   category_state, il_ids, n=200, seed=None, fetch_fn=None):
    """Compute the matchup win-probability and attach it to the context (plan §3.1)."""
    from advisor import simulator as sim
    werth_by_espn, mlbam_by_espn, _platoon, sigma_by_mlbam = lookups
    days_remaining = matchup_meta.get("days_remaining") or 0
    length = matchup_meta.get("matchup_length_days") or max(days_remaining, 1)
    elapsed = max(length - days_remaining, 0)
    elapsed_fraction = elapsed / length if length else 0.0

    my_inputs, my_proj_match = _sim_inputs(
        my_roster, werth_by_espn=werth_by_espn, mlbam_by_espn=mlbam_by_espn,
        sigma_by_mlbam=sigma_by_mlbam, days_remaining=days_remaining, il_ids=il_ids,
        fetch_fn=fetch_fn)
    opp_inputs, opp_proj_match = _sim_inputs(
        opponent_roster, werth_by_espn=werth_by_espn, mlbam_by_espn=mlbam_by_espn,
        sigma_by_mlbam=sigma_by_mlbam, days_remaining=days_remaining, il_ids=set(),
        fetch_fn=fetch_fn)

    my_cat_vals = {cat: st.get("you") for cat, st in (category_state or {}).items()}
    opp_cat_vals = {cat: st.get("opp") for cat, st in (category_state or {}).items()}
    banked_my = estimate_banked_components(my_cat_vals, my_proj_match, elapsed_fraction)
    banked_opp = estimate_banked_components(opp_cat_vals, opp_proj_match, elapsed_fraction)

    winprob, draws = sim.run_matchup(my_inputs, opp_inputs, banked_my=banked_my,
                                     banked_opp=banked_opp, n=n, seed=seed)
    context["winprob"] = winprob
    return winprob, draws, banked_my, banked_opp
