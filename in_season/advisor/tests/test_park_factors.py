"""Phase-1 §4.4 #5: current-season park-factor refresh with validate-or-fallback.

Network is never hit in tests — we monkeypatch requests + cache so the refresh path
and the graceful-fallback path are both exercised deterministically.
"""

from advisor import config  # noqa: F401  (ensures the daily_digest import shim)
import fetch_extras as extras


def test_static_park_factors_normalize_abbrevs():
    pf = extras._static_park_factors()
    assert len(pf) == 30
    # Legacy abbrevs are normalized to PRO_TEAM_ABBREV convention (fixes the latent bug).
    assert "CHW" in pf and "ATH" in pf
    assert "CWS" not in pf and "OAK" not in pf
    assert pf["COL"]["hr"] == 116  # value preserved through normalization


def test_refresh_falls_back_to_static_on_network_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(extras, "cache_valid", lambda *a, **k: False)
    monkeypatch.setattr(extras.requests, "get", boom)

    pf = extras.fetch_current_park_factors(season=2026)
    assert pf == extras._static_park_factors()        # graceful, full 30-team table
    assert all(50 <= v["overall"] <= 160 for v in pf.values())


def test_refresh_uses_live_data_when_plausible(monkeypatch):
    # 22 plausible teams from the "API"; the rest fill from static.
    fake_rows = [{"Team": abbr, "Basic": 100 + i, "HR": 100 + i, "R": 100 + i}
                 for i, abbr in enumerate(
                     ["NYY", "BOS", "LAD", "SD", "CHC", "ATL", "HOU", "PHI", "TEX",
                      "BAL", "MIL", "MIN", "SEA", "TB", "CLE", "DET", "CWS", "STL",
                      "PIT", "SF", "NYM", "KC"])]

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": fake_rows}

    monkeypatch.setattr(extras, "cache_valid", lambda *a, **k: False)
    monkeypatch.setattr(extras, "save_cache", lambda *a, **k: None)
    monkeypatch.setattr(extras.requests, "get", lambda *a, **k: FakeResp())

    pf = extras.fetch_current_park_factors(season=2026)
    assert pf["NYY"]["overall"] == 100          # live value used
    assert "CHW" in pf and "CWS" not in pf      # CWS row normalized to CHW
    assert len(pf) == 30                         # missing teams filled from static
