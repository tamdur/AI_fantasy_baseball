"""Phase-2 gamelogs: IP→outs, component parsing, QS/TB derivation, DNP exclusion,
prior-season backfill (fetch injected, no network)."""

from advisor import gamelogs as G


def test_ip_to_outs_thirds_notation():
    assert G.ip_to_outs("6.0") == 18
    assert G.ip_to_outs("5.2") == 17
    assert G.ip_to_outs("0.1") == 1
    assert G.ip_to_outs(None) == 0
    assert G.ip_to_outs("7") == 21


def test_parse_hitting_row_components_and_dnp():
    stat = {"plateAppearances": 5, "atBats": 4, "runs": 2, "homeRuns": 1, "rbi": 3,
            "hits": 2, "doubles": 1, "triples": 0, "baseOnBalls": 1, "hitByPitch": 0,
            "stolenBases": 1, "caughtStealing": 0}
    row = G.parse_hitting_row(stat)
    # TB from components: singles(2-1-0-1=0) + 2*doubles(2) + 3*triples(0) + 4*HR(4) = 6
    assert row["TB"] == 6
    assert row["onbase"] == 2 + 1 + 0       # H + BB + HBP
    assert row["SBN"] == 1                   # SB - CS
    assert row["pa"] == 5
    # DNP (0 PA) excluded.
    assert G.parse_hitting_row({"plateAppearances": 0}) is None


def test_parse_hitting_row_prefers_explicit_total_bases():
    stat = {"plateAppearances": 4, "hits": 3, "totalBases": 7, "homeRuns": 1}
    assert G.parse_hitting_row(stat)["TB"] == 7


def test_parse_pitching_row_qs_and_outs():
    qs_start = {"battersFaced": 25, "inningsPitched": "7.0", "earnedRuns": 2,
                "strikeOuts": 8, "hits": 5, "baseOnBalls": 1}
    row = G.parse_pitching_row(qs_start)
    assert row["outs"] == 21 and row["QS"] == 1.0 and row["K"] == 8

    blowup = {"battersFaced": 20, "inningsPitched": "5.0", "earnedRuns": 5}
    assert G.parse_pitching_row(blowup)["QS"] == 0.0   # <6 IP and >3 ER

    save = {"battersFaced": 4, "inningsPitched": "1.0", "earnedRuns": 0, "saves": 1, "holds": 0}
    assert G.parse_pitching_row(save)["SVHD"] == 1.0

    assert G.parse_pitching_row({"battersFaced": 0, "inningsPitched": "0.0"}) is None


def test_fetch_recent_gamelogs_prior_season_backfill():
    """Thin current-season sample -> top up from prior season, current games stay newest."""
    cur = [{"stat": {"plateAppearances": 4, "hits": 2}} for _ in range(3)]
    prior = [{"stat": {"plateAppearances": 4, "hits": 1}} for _ in range(40)]

    def fake_fetch(mlbam_id, group, season):
        return cur if season == 2026 else prior

    rows = G.fetch_recent_gamelogs(123, "hitter", n_games=30, season=2026,
                                   backfill_season=2025, fetch_fn=fake_fetch)
    assert len(rows) == 30                 # filled to target from prior season
    # Current-season rows (onbase == 2) come first (most recent).
    assert rows[0]["onbase"] == 2

    # Rich current season -> no backfill needed.
    rich = [{"stat": {"plateAppearances": 4, "hits": 2}} for _ in range(35)]
    rows2 = G.fetch_recent_gamelogs(123, "hitter", n_games=30, season=2026,
                                    fetch_fn=lambda i, g, s: rich if s == 2026 else prior)
    assert len(rows2) == 30
    assert all(r["onbase"] == 2 for r in rows2)
