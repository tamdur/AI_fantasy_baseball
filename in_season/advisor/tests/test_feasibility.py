"""Phase-1 lineup optimizer: two-way either/or, eligibility, flex resolution,
off-today exclusion, and lexicographic "start your best players"."""

from advisor import feasibility as F
from advisor.tests import fixtures as fx


def _assignment_by_id(lineup):
    return {a["espn_id"]: a for a in lineup["assignments"]}


def test_two_way_occupies_exactly_one_slot_never_both():
    data = fx.build_roster()
    lineup = F.optimal_daily_lineup(**data)
    ohtani_slots = [a for a in lineup["assignments"] if a["espn_id"] == 100]
    assert len(ohtani_slots) == 1                       # never UTIL + P simultaneously
    assert ohtani_slots[0]["mode"] in ("HIT", "PITCH")
    assert lineup["two_way"]["espn_id"] == 100
    assert lineup["feasible"] is True


def test_two_way_picks_higher_value_role():
    base = fx.build_roster()

    # value_hit > value_pit and starting -> HIT
    base["roster"] = [p for p in base["roster"] if p["espn_id"] != 100] + [
        fx.ohtani(100, value_hit=7.0, value_pit=3.0)]
    lineup = F.optimal_daily_lineup(**base)
    assert _assignment_by_id(lineup)[100]["mode"] == "HIT"

    # value_pit > value_hit and starting today -> PITCH
    base["roster"] = [p for p in base["roster"] if p["espn_id"] != 100] + [
        fx.ohtani(100, value_hit=3.0, value_pit=8.0)]
    lineup = F.optimal_daily_lineup(**base)
    assert _assignment_by_id(lineup)[100]["mode"] == "PITCH"

    # high pitch value but NO start today -> HIT (can't pitch; team still plays so he hits)
    base["pitch_starts_today"] = set()
    lineup = F.optimal_daily_lineup(**base)
    assert _assignment_by_id(lineup)[100]["mode"] == "HIT"


def test_assignments_respect_eligibility_and_play_today():
    data = fx.build_roster()
    lineup = F.optimal_daily_lineup(**data)
    by_id = {p["espn_id"]: p for p in data["roster"]}

    for a in lineup["assignments"]:
        sid = F.SLOT_NAME_TO_ID[a["slot"]]
        assert sid in by_id[a["espn_id"]]["raw_eligible_slots"]

    # The DTD marginal sits today -> never in an active slot; lands in off_today.
    active_ids = {a["espn_id"] for a in lineup["assignments"]}
    assert 51 not in active_ids
    assert 51 in {p["espn_id"] for p in lineup["off_today"]}


def test_flex_resolution_mi_ci_util():
    """Two middle infielders (2B-only-ish and SS-only-ish) both start: one takes the
    natural slot, the other the MI flex."""
    roster = [
        fx.make_player(1, "PureSS", [4, 6, 12, 16], 5.0),
        fx.make_player(2, "PureMI2B", [2, 6, 12, 16], 4.0),
        fx.make_player(3, "Pure1B", [1, 7, 12, 16], 4.5),
        fx.make_player(4, "Pure3B-CI", [3, 7, 12, 16], 4.2),
    ]
    lineup = F.optimal_daily_lineup(roster, two_way_ids=set())
    slots = {a["espn_id"]: a["slot"] for a in lineup["assignments"]}
    # All four start (slots available): SS, 2B, 1B, 3B + the MI/CI/UTIL flex absorb extras.
    assert len(slots) == 4
    assert slots[1] in ("SS", "MI", "UTIL")
    assert slots[2] in ("2B", "MI", "UTIL")
    assert lineup["feasible"] is True
    # No double-assignment, all eligible.
    assert F.lineup_feasibility(lineup, {p["espn_id"]: p for p in roster})[0]


def test_lexicographic_starts_best_benches_worst():
    """6 outfielders, 5 OF slots (+ UTIL): the lowest-value OF is benched, not a stud."""
    data = fx.build_roster()
    lineup = F.optimal_daily_lineup(**data)
    bench_ids = {p["espn_id"] for p in lineup["bench"]}
    active_ids = {a["espn_id"] for a in lineup["assignments"]}

    # OF-F-bench (id 11, value 1.5) is the weakest playing hitter -> benched.
    assert 11 in bench_ids
    # The high-value regulars are all started.
    for stud in (2, 5, 6, 100):  # 1B, SS, OF-A, Ohtani
        assert stud in active_ids


def test_full_roster_lineup_is_feasible_and_no_double_slot():
    data = fx.build_roster()
    lineup = F.optimal_daily_lineup(**data)
    active_ids = [a["espn_id"] for a in lineup["assignments"]]
    assert len(active_ids) == len(set(active_ids))     # no double-slotting
    ok, reason = F.lineup_feasibility(lineup, {p["espn_id"]: p for p in data["roster"]})
    assert ok, reason
