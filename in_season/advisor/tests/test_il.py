"""Phase-1 IL mechanics: slot-17 detection, IL slotting, and the blocks-adds guard."""

from advisor import feasibility as F
from advisor.tests import fixtures as fx


def test_il_eligible_from_injury_status():
    # Verified against live data: slot 17 is on EVERY player, so IL eligibility must come
    # from the injury designation, not the slot.
    assert F.il_eligible("FIFTEEN_DAY_DL") is True
    assert F.il_eligible("TEN_DAY_DL") is True
    assert F.il_eligible("SIXTY_DAY_DL") is True
    assert F.il_eligible("INJURY_RESERVE") is True
    assert F.il_eligible("OUT") is True
    assert F.il_eligible("ACTIVE") is False
    assert F.il_eligible("NORMAL") is False
    assert F.il_eligible("DAY_TO_DAY") is False   # DTD is a bench cost, not IL-able
    assert F.il_eligible(None) is False


def test_il_star_slotted_to_il_marginal_dtd_is_not():
    data = fx.build_roster()
    lineup = F.optimal_daily_lineup(**data)

    il_ids = {p["espn_id"] for p in lineup["il_slotted"]}
    assert 50 in il_ids                 # injured IL-eligible star -> IL slot
    assert 51 not in il_ids             # DTD marginal is NOT IL-eligible -> never IL-slotted

    # IL-slotted players are off the active roster (not double-counted).
    active_ids = {a["espn_id"] for a in lineup["assignments"]}
    assert il_ids.isdisjoint(active_ids)
    assert lineup["feasible"] is True


def test_healthy_player_in_il_slot_fails_feasibility():
    """A healthy player parked in an IL slot would block all FA/waiver adds."""
    lineup = {
        "assignments": [],
        "il_slotted": [{"espn_id": 9, "name": "Healthy Guy", "il_eligible": False,
                        "injury_status": "ACTIVE"}],
    }
    ok, reason = F.lineup_feasibility(lineup)
    assert ok is False
    assert "not IL-eligible" in reason


def test_il_overflow_is_flagged_not_silently_dropped():
    """More IL-eligible injured players than IL slots -> surfaced for the analyst."""
    roster = [
        fx.make_player(i, f"Hurt-{i}", [5, 12, 16, 17], value=float(i),
                       il_eligible=True, injury="INJURY_RESERVE")
        for i in range(1, 6)  # 5 IL-eligible players, only 3 IL slots
    ]
    lineup = F.optimal_daily_lineup(roster, two_way_ids=set())
    assert len(lineup["il_slotted"]) == 3
    assert "il_overflow" in lineup
    assert len(lineup["il_overflow"]) == 2
    # The most valuable stashes are kept on IL (value 5,4,3); 1,2 overflow.
    kept = {p["espn_id"] for p in lineup["il_slotted"]}
    assert kept == {3, 4, 5}
    assert "exceed" in lineup["feasibility_reason"]
