"""Synthetic fixtures for advisor tests: players + a small roster that exercises
the two-way (Ohtani), IL-star, DTD-marginal, and streamer cases (plan §5).

ESPN raw eligibleSlot IDs (SLOT_MAP): 0=C 1=1B 2=2B 3=3B 4=SS 5=OF 6=MI 7=CI
12=UTIL 13=P 14=SP 15=RP 16=BE 17=IL.
"""

# Common slot bundles (always include 12/UTIL for hitters, 16/BE for everyone).
C = [0, 12, 16]
FIRST = [1, 7, 12, 16]      # 1B + CI
SECOND = [2, 6, 12, 16]     # 2B + MI
THIRD = [3, 7, 12, 16]      # 3B + CI
SHORT = [4, 6, 12, 16]      # SS + MI
OUTF = [5, 12, 16]          # OF
SP = [13, 14, 16]           # P/SP
RP = [13, 15, 16]           # P/RP


def make_player(espn_id, name, slots, value=1.0, *, il_eligible=False,
                injury="ACTIVE", team="LAD", **extra):
    p = {
        "espn_id": espn_id, "name": name, "raw_eligible_slots": list(slots),
        "il_eligible": il_eligible, "injury_status": injury, "team": team,
        "value": value,
    }
    p.update(extra)
    return p


def ohtani(espn_id=100, value_hit=6.0, value_pit=4.0):
    """Single two-way entity: UTIL + P eligible, distinct hit/pitch values."""
    return make_player(espn_id, "Ohtani (LAD)", [12, 13, 14, 16],
                       team="LAD", value_hit=value_hit, value_pit=value_pit)


def build_roster():
    """A small but structurally complete roster + plays_today + two_way_ids.

    Includes: Ohtani (two-way), an IL-eligible injured SS star, a DTD marginal OF
    (NOT IL-eligible), enough hitters to create UTIL/flex contention, and pitchers.
    """
    roster = [
        make_player(1, "Catcher", C, 3.0, team="ATL"),
        make_player(2, "FirstBase", FIRST, 5.0, team="NYY"),
        make_player(3, "SecondBase", SECOND, 4.0, team="HOU"),
        make_player(4, "ThirdBase", THIRD, 4.5, team="PHI"),
        make_player(5, "Shortstop", SHORT, 5.5, team="BAL"),
        make_player(6, "OF-A", OUTF, 5.2, team="SEA"),
        make_player(7, "OF-B", OUTF, 4.8, team="TEX"),
        make_player(8, "OF-C", OUTF, 4.1, team="SD"),
        make_player(9, "OF-D", OUTF, 3.6, team="CHC"),
        make_player(10, "OF-E", OUTF, 3.2, team="MIN"),
        make_player(11, "OF-F-bench", OUTF, 1.5, team="COL"),  # 6th OF -> benched (5 OF slots)
        ohtani(100, value_hit=6.0, value_pit=4.0),
        make_player(101, "SP-1", SP, 5.0, team="LAD"),
        make_player(102, "SP-2", SP, 4.2, team="ATL"),
        make_player(103, "SP-3", SP, 3.8, team="NYM"),
        make_player(104, "RP-1", RP, 3.0, team="MIL"),
        # Injured IL-eligible SS star: high value, OUT, slot 17 present.
        make_player(50, "Injured Star (SS)", [4, 6, 12, 16, 17], 7.5,
                    il_eligible=True, injury="INJURY_RESERVE", team="LAD"),
        # DTD marginal OF: low value, day-to-day, NOT IL-eligible (no slot 17).
        make_player(51, "DTD Marginal (OF)", OUTF, 0.8,
                    injury="DAY_TO_DAY", team="WSH"),
    ]
    plays_today = {p["espn_id"]: True for p in roster}
    plays_today[51] = False  # DTD marginal sits today
    two_way_ids = {100}
    pitch_starts_today = {100}  # Ohtani has a start available today (hit value still higher)
    return {"roster": roster, "plays_today": plays_today, "two_way_ids": two_way_ids,
            "pitch_starts_today": pitch_starts_today}
