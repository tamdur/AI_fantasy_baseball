"""Phase-4 decision page: stakes-tiered layout, <details> drill-down, hold/closest-call,
and publish file writes + nav."""

from advisor import render as R


def _ctx(date="2026-05-31"):
    return {
        "date": date, "matchup_week": 10, "matchup_day": 3, "matchup_length_days": 7,
        "days_remaining": 4, "opponent": "Rival", "moves_used": 1, "moves_max": 7,
        "winprob": {"overall": {"p_win_matchup": 0.61, "expected_cats_won": 6.8},
                    "by_cat": {"HR": {"p_win": 0.34, "status": "live-swing"},
                               "ERA": {"p_win": 0.99, "status": "clinched"}}},
        "data_warnings": [],
    }


def test_hold_day_shows_no_moves_and_closest_call():
    html = R.render_decision_page(_ctx(), [{"type": "hold", "tier": "hold"}],
                                  closest_call="stream Lugo vs SD, +0.006 — below the bar")
    assert "No moves." in html
    assert "Closest call:" in html
    assert "61%" in html                      # P(win) headline
    assert "ERA 99%" in html and "HR 34%" in html


def test_significant_move_renders_details_drilldown():
    decisions = [{"type": "add", "tier": "significant",
                  "headline": "Add Skenes (PIT), drop Bench Arm",
                  "one_liner": "+0.031 P(win), QS +0.6, ratios safe",
                  "drilldown_md": "EV table:\n  HR +0.0\n  QS +0.6\nSelf-critique: small sample but...",
                  "confidence": "med"}]
    html = R.render_decision_page(_ctx(), decisions)
    assert "<details" in html
    assert "Add Skenes" in html
    assert "Self-critique" in html            # drill-down body present
    assert "No moves." not in html


def test_stakes_ordering_significant_before_tweak():
    decisions = [
        {"type": "sit", "tier": "tweak", "headline": "Sit Rooker vs LHP"},
        {"type": "add", "tier": "significant", "headline": "Drop X for Y"},
    ]
    html = R.render_decision_page(_ctx(), decisions)
    assert html.index("Drop X for Y") < html.index("Sit Rooker")


def test_publish_writes_index_archive_and_nav(tmp_path):
    docs = tmp_path / "docs"
    archive = docs / "archive"
    archive.mkdir(parents=True)
    (archive / "2026-05-30.html").write_text("old", encoding="utf-8")  # prior day for nav

    html = R.render_decision_page(_ctx("2026-05-31"), [{"type": "hold", "tier": "hold"}])
    out = R.publish_page(html, "2026-05-31", docs_dir=docs, archive_dir=archive)
    assert out.exists()
    assert (archive / "2026-05-31.html").exists()
    published = (docs / "index.html").read_text()
    assert "2026-05-30.html" in published      # prev nav link
    assert "&larr;" in published
