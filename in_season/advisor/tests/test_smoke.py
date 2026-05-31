"""Phase-0 smoke: the import shim resolves the backend, advisor paths are correct,
the additive _parse_player IL capture works, and the pure compaction helper behaves.

Run from the repo root:  python -m pytest in_season/advisor/tests -q
(pytest prepend-import mode walks up past advisor/ + advisor/tests/ __init__.py to
in_season/, putting `advisor` on sys.path; advisor/__init__ then shims daily_digest.)
"""


def test_advisor_package_imports_and_shims_backend():
    """Importing the advisor package puts daily_digest on the path; backend resolves."""
    from advisor import config as cfg

    # Re-exported league constants are present and sane.
    assert cfg.NUM_TEAMS == 8
    assert cfg.SLOT_MAP[17] == "IL"
    assert "OBP" in cfg.HITTING_CATS and "SVHD" in cfg.PITCHING_CATS
    assert cfg.LOWER_IS_BETTER == {"ERA", "WHIP"}

    # Bare backend imports now resolve (the shim worked).
    import fetch_espn  # noqa: F401
    import preprocess  # noqa: F401


def test_advisor_paths_split_committed_vs_scratch(tmp_path, monkeypatch):
    """Tier-1 (log/docs) vs Tier-2 (scratch) paths resolve; scratch is overridable."""
    from advisor import config as cfg

    assert cfg.LOG_DIR.name == "log"
    assert cfg.DECISIONS_CSV.name == "decisions.csv"
    assert cfg.DOCS_ARCHIVE_DIR.parts[-2:] == ("docs", "archive")
    # archive page path is the idempotency key
    assert cfg.archive_page_path("2026-05-31").name == "2026-05-31.html"

    # ADVISOR_SCRATCH honors the env override (so local dev + Routine agree).
    monkeypatch.setenv("ADVISOR_SCRATCH", str(tmp_path / "scratch"))
    import importlib
    importlib.reload(cfg)
    assert cfg.ADVISOR_SCRATCH == tmp_path / "scratch"
    p = cfg.context_path("2026-05-31")
    assert p.parent == tmp_path / "scratch"
    assert p.name == "decision_context_2026-05-31.json"
    importlib.reload(cfg)  # restore default for other tests


def test_parse_player_captures_il_eligibility():
    """§4.4 #7: _parse_player exposes raw_eligible_slots + il_eligible. IL eligibility is
    driven by injuryStatus (NOT slot 17 — ESPN gives slot 17 to every player), additively,
    without changing the existing `positions` filter."""
    from advisor import config  # noqa: F401  (ensures shim)
    import fetch_espn as espn

    # An injured SS on the DL — IL-eligible. Slot 17 present (as it is for everyone).
    entry_il = {
        "id": 111,
        "player": {
            "id": 111, "fullName": "Injured Star",
            "eligibleSlots": [4, 6, 12, 16, 17],  # SS, MI, UTIL, BE, IL
            "defaultPositionId": 6, "proTeamId": 19, "injuryStatus": "FIFTEEN_DAY_DL",
        },
        "lineupSlotId": 17,
    }
    p = espn._parse_player(entry_il)
    assert p["il_eligible"] is True
    assert 17 in p["raw_eligible_slots"]
    assert p["positions"] == ["SS"]          # filtered view unchanged (no 'IL'/'MI'/'UTIL')
    assert p["lineup_slot"] == "IL"

    # A HEALTHY player who also carries slot 17 (ESPN does this for everyone) -> NOT IL.
    entry_healthy = {
        "id": 222,
        "player": {
            "id": 222, "fullName": "Healthy Bat",
            "eligibleSlots": [3, 5, 7, 12, 16, 17],  # 3B, OF, CI, UTIL, BE, IL
            "defaultPositionId": 5, "proTeamId": 15, "injuryStatus": "ACTIVE",
        },
        "lineupSlotId": 5,
    }
    h = espn._parse_player(entry_healthy)
    assert h["il_eligible"] is False         # healthy despite slot 17 being present
    assert 17 in h["raw_eligible_slots"]
    assert set(h["positions"]) == {"3B", "OF"}

    # DAY_TO_DAY is NOT IL-eligible (a real bench cost).
    entry_dtd = {"id": 333, "player": {"id": 333, "fullName": "DTD Guy",
                 "eligibleSlots": [5, 12, 16, 17], "defaultPositionId": 7,
                 "proTeamId": 1, "injuryStatus": "DAY_TO_DAY"}, "lineupSlotId": 16}
    assert espn._parse_player(entry_dtd)["il_eligible"] is False


def test_compact_player_joins_werth_and_flags_missing():
    """compact_player surfaces WERTH + IL + platoon gap + σ band, and flags ID-bridge misses."""
    from advisor.context import compact_player

    player = {
        "espn_id": 111, "name": "Injured Star", "pro_team_abbrev": "LAD",
        "positions": ["SS"], "raw_eligible_slots": [4, 6, 12, 16, 17],
        "il_eligible": True, "injury_status": "INJURY_RESERVE", "lineup_slot": "IL",
        "games_remaining_this_week": 0,
    }
    werth_by_espn = {111: {
        "z_R": 0.5, "z_HR": 1.2, "z_TB": 0.8, "z_RBI": 0.6, "z_SBN": -0.1, "z_OBP": 0.9,
        "total_werth": 3.9, "pos_adj_werth": 4.7, "repl_level": 0.0, "is_starter": True,
    }}
    rec = compact_player(player, werth_by_espn=werth_by_espn,
                         mlbam_by_espn={111: 660271}, platoon_by_mlbam={660271: {"platoon_obp_gap": 0.045}},
                         sigma_by_mlbam={660271: {"HR": 2.1}})
    assert rec["il_eligible"] is True
    assert rec["werth"] == 4.7
    assert rec["z"]["HR"] == 1.2
    assert rec["platoon_obp_gap"] == 0.045
    assert rec["sigma"]["HR"] == 2.1
    assert "werth_missing" not in rec

    # Missing WERTH row -> flagged (stale ID bridge ⇒ silent WERTH=0 guard).
    rec_missing = compact_player({"espn_id": 999, "name": "Ghost"}, werth_by_espn={})
    assert rec_missing["werth"] is None
    assert rec_missing["werth_missing"] is True
