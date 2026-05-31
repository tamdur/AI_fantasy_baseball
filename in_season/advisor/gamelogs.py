"""Recent per-player game/start logs for the bootstrap simulator (plan §3.4).

Source: MLB Stats API ``people/{id}/stats?stats=gameLog`` (free, returns MLBAM IDs
— our join key). Parses each game into the simulator's component schema. Prior-season
(2025) backfill fills thin current-season samples (returnees, call-ups, early season).

Wall-time discipline (annotation #1): fetch only relevant players; cache within the
run in Tier-2 scratch (cold across runs is accepted — the cache is gitignored, never
committed). No HTTP timeout caps beyond a courtesy connect timeout.

Pure parsing (``parse_gamelog_splits``, ``ip_to_outs``) is unit-tested without network.
"""

import json
import logging

import requests

from advisor import config as cfg
from http_utils import RateLimiter

log = logging.getLogger("advisor.gamelogs")

_STATSAPI = "https://statsapi.mlb.com/api/v1"
_rate = RateLimiter(0.34)  # ~3 req/s, courteous to a free public API

_HIT_TARGET = 30
_PITCH_TARGET = 10


def ip_to_outs(ip):
    """MLB innings-pitched notation -> outs. '6.0'->18, '5.2'->17, '0.1'->1."""
    if ip is None:
        return 0
    try:
        whole, _, frac = str(ip).partition(".")
        outs = int(whole or 0) * 3
        if frac:
            outs += int(frac[0])  # the fractional digit is thirds (0/1/2), not decimal
        return outs
    except (TypeError, ValueError):
        return 0


def _num(stat, key, default=0):
    v = stat.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_hitting_row(stat):
    """One hitting gameLog split -> component dict, or None if the player didn't bat."""
    pa = _num(stat, "plateAppearances")
    if pa <= 0:
        return None  # DNP / pinch-run-only -> exclude (healthy filter)
    h = _num(stat, "hits")
    hr = _num(stat, "homeRuns")
    tb = stat.get("totalBases")
    tb = _num(stat, "totalBases") if tb is not None else (
        (h - _num(stat, "doubles") - _num(stat, "triples") - hr)  # singles
        + 2 * _num(stat, "doubles") + 3 * _num(stat, "triples") + 4 * hr)
    onbase = h + _num(stat, "baseOnBalls") + _num(stat, "hitByPitch")
    return {
        "R": _num(stat, "runs"), "HR": hr, "TB": tb, "RBI": _num(stat, "rbi"),
        "SBN": _num(stat, "stolenBases") - _num(stat, "caughtStealing"),
        "onbase": onbase, "pa": pa,
    }


def parse_pitching_row(stat):
    """One pitching gameLog split -> component dict, or None if no batters faced."""
    bf = _num(stat, "battersFaced")
    outs = ip_to_outs(stat.get("inningsPitched"))
    if bf <= 0 and outs <= 0:
        return None
    er = _num(stat, "earnedRuns")
    qs = 1.0 if (outs >= 18 and er <= 3) else 0.0
    return {
        "K": _num(stat, "strikeOuts"), "QS": qs, "ER": er, "outs": outs,
        "H": _num(stat, "hits"), "BB": _num(stat, "baseOnBalls"),
        "SVHD": _num(stat, "saves") + _num(stat, "holds"),
    }


def parse_gamelog_splits(splits, kind):
    """List of gameLog splits (newest last from the API) -> component rows, newest
    FIRST, excluding DNP rows."""
    parse = parse_hitting_row if kind == "hitter" else parse_pitching_row
    rows = []
    for sp in splits or []:
        stat = sp.get("stat", sp)
        row = parse(stat)
        if row is not None:
            rows.append(row)
    rows.reverse()  # API returns chronological; we want most-recent first
    return rows


def _fetch_raw(mlbam_id, group, season):
    """Raw gameLog splits for one player-season. Cached in Tier-2 scratch (within-run)."""
    cache_file = cfg.GAMELOG_CACHE_DIR / f"{mlbam_id}_{group}_{season}.json"
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                return json.load(f)
        except Exception:
            pass
    cfg.ensure_scratch()
    _rate.throttle()
    url = f"{_STATSAPI}/people/{mlbam_id}/stats"
    params = {"stats": "gameLog", "group": group, "season": str(season)}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        splits = []
        for s in data.get("stats", []):
            splits.extend(s.get("splits", []))
        with open(cache_file, "w") as f:
            json.dump(splits, f)
        return splits
    except Exception as e:
        log.warning("gameLog fetch failed for %s (%s/%s): %s", mlbam_id, group, season, e)
        return []


def fetch_recent_gamelogs(mlbam_id, kind, n_games=None, season=2026, backfill_season=2025,
                          fetch_fn=None):
    """Most-recent ``n_games`` healthy component rows for one player.

    Falls back to ``backfill_season`` when the current season is thin. ``fetch_fn`` is
    injectable for tests (default hits the MLB Stats API). Returns list of component
    dicts, newest first.
    """
    group = "hitting" if kind == "hitter" else "pitching"
    target = n_games or (_HIT_TARGET if kind == "hitter" else _PITCH_TARGET)
    fetch_fn = fetch_fn or _fetch_raw

    rows = parse_gamelog_splits(fetch_fn(mlbam_id, group, season), kind)
    if len(rows) < target and backfill_season:
        prior = parse_gamelog_splits(fetch_fn(mlbam_id, group, backfill_season), kind)
        rows = rows + prior  # current-season games stay most-recent
    return rows[:target]
