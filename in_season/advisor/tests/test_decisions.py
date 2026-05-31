"""Phase-4 decision log: row schema, CSV roundtrip, daily record, process scoring."""

from advisor import decisions as D


def test_decision_to_row_normalizes_players_and_defaults():
    row = D.decision_to_row({"type": "stream", "tier": "stream",
                             "players": ["Lugo (SD)", "Bench Guy"], "confidence": "med"},
                            date="2026-05-31", matchup_period=10, index=0)
    assert row["players"] == "Lugo (SD);Bench Guy"
    assert row["decision_id"] == "2026-05-31-0"
    assert row["type"] == "stream" and row["realized_outcome"] == ""
    assert set(row) == set(D.FIELDS)


def test_log_decisions_roundtrip(tmp_path):
    path = tmp_path / "decisions.csv"
    D.log_decisions([{"type": "hold", "tier": "hold", "confidence": "high"}],
                    date="2026-05-31", matchup_period=10, path=path)
    D.log_decisions([{"type": "stream", "tier": "stream", "players": ["X"], "ev_estimate": 0.02}],
                    date="2026-06-01", matchup_period=10, path=path)
    rows = D.load_decisions(path)
    assert len(rows) == 2
    assert rows[0]["type"] == "hold" and rows[1]["type"] == "stream"


def test_write_daily_record_excludes_holds(tmp_path):
    ctx = {"winprob": {"overall": {"p_win_matchup": 0.6, "expected_cats_won": 6.8}}}
    decisions = [{"type": "hold", "tier": "hold"},
                 {"type": "stream", "tier": "stream", "players": ["Lugo"], "ev_estimate": 0.02,
                  "confidence": "med"}]
    p = D.write_daily_record(ctx, decisions, date="2026-05-31",
                             closest_call="held Gallen, +0.006", path=tmp_path / "r.json")
    import json
    rec = json.loads(p.read_text())
    assert rec["p_win_matchup"] == 0.6
    assert len(rec["moves"]) == 1 and rec["moves"][0]["type"] == "stream"
    assert rec["closest_call"].startswith("held")


def test_score_process_confidence_hit_rate_and_overturn(tmp_path):
    path = tmp_path / "decisions.csv"
    rows = [
        {"type": "stream", "tier": "stream", "confidence": "high", "overturned": False,
         "winprob_after": 0.7, "realized_outcome": "W"},
        {"type": "stream", "tier": "stream", "confidence": "high", "overturned": False,
         "winprob_after": 0.7, "realized_outcome": "W"},
        {"type": "add", "tier": "significant", "confidence": "low", "overturned": True,
         "winprob_after": 0.55, "realized_outcome": "L"},
    ]
    for i, r in enumerate(rows):
        D.log_decisions([r], date=f"2026-05-3{i}", matchup_period=10, path=path)
    rep = D.score_process(path=path)
    assert rep["n_decisions"] == 3 and rep["n_realized"] == 3
    assert rep["confidence_hit_rate"]["high"]["hit_rate"] == 1.0
    assert rep["confidence_hit_rate"]["low"]["hit_rate"] == 0.0
    assert abs(rep["selfcritique_overturn_rate"] - round(1 / 3, 3)) < 1e-9
    assert rep["reliability"]["n"] == 3
