"""Deterministic daily-lineup feasibility + optimizer.

This is the pre-pass the analyst never re-reasons (plan §8 D4, §4.4 #8): given who
plays today, assign rostered players to the active lineup slots, honoring ESPN's
own eligibility encoding, the two-way (Ohtani) either/or rule, and IL slotting.

Eligibility uses the *raw* ESPN ``eligibleSlots`` (slot-ID numbering, captured by
the additive ``_parse_player`` change), which authoritatively encodes flex slots
(MI=2B/SS, CI=1B/3B, UTIL=any hitter, P=any pitcher) — more robust than re-deriving
flex rules from positions.

Player value: each player dict carries a ``value`` (the analyst sets it to RoS
``pos_adj_werth``). Two-way players additionally carry ``value_hit`` / ``value_pit``
so the optimizer can pick the higher-EV role for the single daily slot.

The matching is Kuhn's bipartite algorithm with players processed in descending
value, so the *best* eligible players are always started (a stud is never benched
to start a scrub) while flex slots absorb the best remaining fits.
"""

import logging

from advisor import config as cfg

log = logging.getLogger("advisor.feasibility")

IL_SLOT_ID = 17  # SLOT_MAP: IL

# Active-lineup slot name -> ESPN lineup slot ID (SLOT_MAP). These are the slot IDs
# that appear in a player's raw eligibleSlots when they can fill that lineup spot.
SLOT_NAME_TO_ID = {
    "C": 0, "1B": 1, "2B": 2, "3B": 3, "SS": 4, "OF": 5,
    "MI": 6, "CI": 7, "UTIL": 12, "P": 13,
}
# Specificity rank: fill specific position slots before flex, so flex slots stay
# open for players who *need* them. (Pitchers: P is rank 0, their only slot.)
_SLOT_SPECIFICITY = {
    "C": 0, "1B": 0, "2B": 0, "3B": 0, "SS": 0, "OF": 0, "P": 0,
    "MI": 1, "CI": 1, "UTIL": 2,
}
_PITCHER_SLOTS = {"P"}


def il_eligible(raw_eligible_slots):
    """True if ESPN marks this player IL-eligible (slot 17 in eligibleSlots).

    Robust IL test (plan §3.2): preferred over parsing ``injuryStatus`` strings,
    which can't distinguish "OUT today" from "on the IL".
    """
    return IL_SLOT_ID in (raw_eligible_slots or [])


def active_slot_instances():
    """Expand ACTIVE_SLOTS (counts) into a flat list of slot instances.

    Returns list of (instance_idx, slot_name), e.g. ("OF" appears 5x, "P" 9x).
    """
    instances = []
    for slot_name, count in cfg.ACTIVE_SLOTS.items():
        for _ in range(count):
            instances.append((len(instances), slot_name))
    return instances


def _player_value(player, slot_name):
    """Value of placing ``player`` in ``slot_name`` today.

    Two-way players value differently by role (value_pit in P, value_hit elsewhere).
    Everyone else uses a single ``value`` (default: ``werth``, then 0.0).
    """
    is_pitcher_slot = slot_name in _PITCHER_SLOTS
    if "value_hit" in player or "value_pit" in player:
        v = player.get("value_pit") if is_pitcher_slot else player.get("value_hit")
        if v is not None:
            return float(v)
    v = player.get("value")
    if v is None:
        v = player.get("werth")
    return float(v) if v is not None else 0.0


def _eligible_slot_idxs(player, instances, *, restrict_slots=None):
    """Ordered list of slot-instance indices this player can fill (by specificity).

    ``restrict_slots`` (a set of slot names) narrows eligibility — used to pin a
    two-way player to the single role chosen for today.
    """
    raw = set(player.get("raw_eligible_slots", []))
    elig = []
    for idx, slot_name in instances:
        if restrict_slots is not None and slot_name not in restrict_slots:
            continue
        if SLOT_NAME_TO_ID.get(slot_name) in raw:
            elig.append((idx, slot_name))
    elig.sort(key=lambda t: (_SLOT_SPECIFICITY.get(t[1], 9), t[0]))
    return [idx for idx, _ in elig]


def _kuhn(priority_players, eligible_by_player):
    """Max bipartite matching (Kuhn's). ``priority_players`` in desc-value order so
    higher-value players are guaranteed inclusion when feasible. Returns
    {player_id -> slot_idx}.
    """
    match_slot = {}   # slot_idx -> player_id
    match_player = {}  # player_id -> slot_idx

    def augment(pid, visited):
        for s in eligible_by_player.get(pid, ()):
            if s in visited:
                continue
            visited.add(s)
            if s not in match_slot or augment(match_slot[s], visited):
                match_slot[s] = pid
                match_player[pid] = s
                return True
        return False

    for pid in priority_players:
        augment(pid, set())
    return match_player


def _two_way_choice(player, pitch_starts_today):
    """For a two-way entity, choose HIT vs PITCH for today's single slot.

    Pitch only if the player has a probable pitching start today AND pitching value
    exceeds hitting value; else hit. (Hit availability is governed separately by
    plays_today / team-plays — a two-way player can hit on non-pitching days.)
    Returns (chosen_role, restrict_slots, info_dict).
    """
    v_hit = float(player.get("value_hit", player.get("value", 0.0)) or 0.0)
    v_pit = float(player.get("value_pit", 0.0) or 0.0)
    starts = player.get("espn_id") in pitch_starts_today
    if starts and v_pit > v_hit:
        chosen, restrict = "PITCH", {"P"}
    else:
        chosen, restrict = "HIT", {s for s in SLOT_NAME_TO_ID if s not in _PITCHER_SLOTS}
    info = {
        "espn_id": player.get("espn_id"), "name": player.get("name"),
        "chosen": chosen, "alt": "HIT" if chosen == "PITCH" else "PITCH",
        "value_hit": round(v_hit, 3), "value_pit": round(v_pit, 3),
        "reason": (f"pitch start today, value {v_pit:.2f} > hit {v_hit:.2f}"
                   if chosen == "PITCH"
                   else f"hit (value {v_hit:.2f}" + (f" ≥ pitch {v_pit:.2f})" if starts else ", no start today)")),
    }
    return chosen, restrict, info


def optimal_daily_lineup(roster, plays_today=None, two_way_ids=None,
                         pitch_starts_today=None, context=None):
    """Assign ``roster`` to today's active lineup. Returns a Lineup dict.

    Args:
      roster: list of player dicts. Each needs ``espn_id``, ``name``,
              ``raw_eligible_slots``, ``il_eligible``, and a value
              (``value`` or ``werth``; two-way players: ``value_hit``/``value_pit``).
      plays_today: {espn_id -> bool} hit/play availability (team plays today).
              Missing -> True (assume plays). For a two-way player this is the
              hit-availability gate, NOT the pitching-start signal.
      two_way_ids: set of espn_ids that are single-entity two-way players (Ohtani).
      pitch_starts_today: set of espn_ids with a probable pitching start today
              (used only to let a two-way entity choose PITCH over HIT).
      context: unused here (reserved for future EV-aware two-way choice via simulator).

    Returns dict: assignments / bench / il_slotted / off_today / two_way / open_slots
    / feasible / feasibility_reason.
    """
    plays_today = plays_today or {}
    two_way_ids = set(two_way_ids or [])
    pitch_starts_today = set(pitch_starts_today or [])
    instances = active_slot_instances()
    by_id = {p["espn_id"]: p for p in roster}

    # 1) IL-bound: il_eligible players go to IL slots (off the active roster). Cap at
    #    N_IL_SLOTS; surplus is surfaced as a warning (the analyst resolves it).
    il_players = [p for p in roster if p.get("il_eligible")]
    il_players.sort(key=lambda p: -_player_value(p, "UTIL"))  # keep the most valuable stashes
    il_slotted = il_players[:cfg.N_IL_SLOTS]
    il_overflow = il_players[cfg.N_IL_SLOTS:]
    il_ids = {p["espn_id"] for p in il_slotted}

    # 2) Two-way role choice (restrict each two-way entity to one role's slots).
    two_way_info = None
    restrict_by_id = {}
    for tid in two_way_ids:
        p = by_id.get(tid)
        if p is None or tid in il_ids:
            continue
        _, restrict, info = _two_way_choice(p, pitch_starts_today)
        restrict_by_id[tid] = restrict
        two_way_info = info  # single two-way entity expected; last wins if several

    # 3) Active candidates: not IL-bound, playing today.
    def plays(p):
        return plays_today.get(p["espn_id"], True)

    candidates = [p for p in roster if p["espn_id"] not in il_ids and plays(p)]
    off_today = [p for p in roster
                 if p["espn_id"] not in il_ids and not plays(p)]

    # Priority order: best players first (two-way uses their chosen role's value).
    def priority_value(p):
        if p["espn_id"] in restrict_by_id:
            role = restrict_by_id[p["espn_id"]]
            slot = "P" if "P" in role else "UTIL"
            return _player_value(p, slot)
        return max((_player_value(p, s) for _, s in instances), default=0.0)

    candidates.sort(key=priority_value, reverse=True)

    eligible_by_player = {}
    for p in candidates:
        pid = p["espn_id"]
        eligible_by_player[pid] = _eligible_slot_idxs(
            p, instances, restrict_slots=restrict_by_id.get(pid))

    match_player = _kuhn([p["espn_id"] for p in candidates], eligible_by_player)

    # 4) Build the lineup output.
    slot_name_by_idx = {idx: name for idx, name in instances}
    assignments = []
    for pid, slot_idx in match_player.items():
        p = by_id[pid]
        slot_name = slot_name_by_idx[slot_idx]
        mode = None
        if pid in two_way_ids:
            mode = "PITCH" if slot_name in _PITCHER_SLOTS else "HIT"
        assignments.append({
            "slot": slot_name, "espn_id": pid, "name": p.get("name"),
            "team": p.get("team", p.get("pro_team_abbrev", "")),
            "value": round(_player_value(p, slot_name), 3), "mode": mode,
        })
    assignments.sort(key=lambda a: (a["slot"], -a["value"]))

    matched_ids = set(match_player)
    bench = [p for p in candidates if p["espn_id"] not in matched_ids]
    filled_slot_idxs = set(match_player.values())
    open_slots = [name for idx, name in instances if idx not in filled_slot_idxs]

    lineup = {
        "assignments": assignments,
        "bench": [_brief(p) for p in bench],
        "il_slotted": [_brief(p) for p in il_slotted],
        "off_today": [_brief(p) for p in off_today],
        "two_way": two_way_info,
        "open_slots": open_slots,
    }
    feasible, reason = lineup_feasibility(lineup, by_id)
    lineup["feasible"] = feasible
    lineup["feasibility_reason"] = reason
    if il_overflow:
        lineup["il_overflow"] = [_brief(p) for p in il_overflow]
        lineup["feasibility_reason"] = (
            f"{reason}; {len(il_overflow)} IL-eligible player(s) exceed {cfg.N_IL_SLOTS} "
            f"IL slots — analyst must bench or drop the worst").strip("; ")
    return lineup


def _brief(p):
    return {
        "espn_id": p.get("espn_id"), "name": p.get("name"),
        "team": p.get("team", p.get("pro_team_abbrev", "")),
        "il_eligible": bool(p.get("il_eligible", False)),
        "injury_status": p.get("injury_status", "ACTIVE"),
    }


def lineup_feasibility(lineup, by_id=None):
    """Hard structural checks on a lineup. Returns (feasible, reason).

    Checks: no player in two active slots; assignments respect eligibility; a two-way
    entity is not double-slotted; IL slots hold only il_eligible players; no player is
    both active and IL; no *healthy* player sits in an IL slot (would block adds).
    """
    assignments = lineup.get("assignments", [])
    active_ids = [a["espn_id"] for a in assignments]
    if len(active_ids) != len(set(active_ids)):
        return False, "a player is assigned to two active slots"

    instances = active_slot_instances()
    slot_ids_present = {name: SLOT_NAME_TO_ID[name] for _, name in instances}
    if by_id is not None:
        for a in assignments:
            p = by_id.get(a["espn_id"], {})
            raw = set(p.get("raw_eligible_slots", []))
            sid = slot_ids_present.get(a["slot"])
            if raw and sid is not None and sid not in raw:
                return False, f"{a['name']} not eligible for slot {a['slot']}"

    il_ids = {p["espn_id"] for p in lineup.get("il_slotted", [])}
    if il_ids & set(active_ids):
        return False, "a player occupies both an active slot and an IL slot"
    for p in lineup.get("il_slotted", []):
        if not p.get("il_eligible", False):
            return False, f"{p.get('name')} is in an IL slot but is not IL-eligible (blocks adds)"

    if len(lineup.get("il_slotted", [])) > cfg.N_IL_SLOTS:
        return False, f"more than {cfg.N_IL_SLOTS} players in IL slots"
    return True, "ok"
