"""
ESPN Fantasy Baseball API fetchers.
All functions use cookie-based auth and the mBoxscore/mRoster views.
"""

import json as _json
import logging
from datetime import date, datetime
from pathlib import Path

import requests

from config import (
    ESPN_BASE_URL, ESPN_COOKIES, ESPN_RATE_LIMIT, MY_TEAM_ID,
    SCORING_CAT_IDS, STATS_MAP, POS_MAP, SLOT_MAP, PRO_TEAM_ABBREV,
    ROOT,
)
from http_utils import RateLimiter


# ---- League schedule (parsed from PDF, see data/league_schedule_2026.json) ----

_SCHEDULE_PATH = ROOT / "data" / "league_schedule_2026.json"
_schedule_cache = None


def _load_schedule():
    """Load the league schedule JSON (matchup dates, opponents). Cached after first call."""
    global _schedule_cache
    if _schedule_cache is not None:
        return _schedule_cache
    if _SCHEDULE_PATH.exists():
        with open(_SCHEDULE_PATH) as f:
            _schedule_cache = _json.load(f)
    else:
        _schedule_cache = {}
    return _schedule_cache

log = logging.getLogger(__name__)

_rate = RateLimiter(ESPN_RATE_LIMIT)


def _espn_get(views, params=None):
    """Make a rate-limited ESPN API request."""
    _rate.throttle()

    p = {"view": views}
    if params:
        p.update(params)

    r = requests.get(ESPN_BASE_URL, params=p, cookies=ESPN_COOKIES)

    if r.status_code == 401 or (r.status_code == 200 and not r.text.strip()):
        raise PermissionError(
            "ESPN API auth failed — cookies likely expired. "
            "Refresh ESPN_SWID and ESPN_S2 in .env file."
        )
    r.raise_for_status()
    return r.json()


def _parse_player(player_entry):
    """Parse a player entry from ESPN roster/FA response."""
    pe = player_entry.get("playerPoolEntry", player_entry)
    player = pe.get("player", pe)
    pid = pe.get("id") or player.get("id")

    # eligibleSlots uses lineup slot IDs (SLOT_MAP numbering), NOT position IDs.
    # Real position slots: 0=C, 1=1B, 2=2B, 3=3B, 4=SS, 5=OF, 14=SP, 15=RP
    # Aggregate slots (MI, CI, IF, UTIL, BE, IL, P, DH) are NOT positions.
    REAL_POSITION_SLOTS = {0, 1, 2, 3, 4, 5, 14, 15}
    eligible = [SLOT_MAP.get(s, "") for s in player.get("eligibleSlots", [])
                if s in REAL_POSITION_SLOTS]
    # Deduplicate while preserving order
    seen = set()
    eligible = [p for p in eligible if p and p not in seen and not seen.add(p)]

    slot_id = player_entry.get("lineupSlotId", -1)
    lineup_slot = SLOT_MAP.get(slot_id, "")

    injury = player.get("injuryStatus", "ACTIVE")
    if injury == "NORMAL":
        injury = "ACTIVE"

    pro_team_id = player.get("proTeamId", 0)
    return {
        "espn_id": pid,
        "name": player.get("fullName", f"Unknown ({pid})"),
        "positions": eligible,
        "default_position": POS_MAP.get(player.get("defaultPositionId", 0), "?"),
        "lineup_slot": lineup_slot,
        "pro_team": pro_team_id,
        "pro_team_abbrev": PRO_TEAM_ABBREV.get(pro_team_id, ""),
        "injury_status": injury,
        "ownership_pct": player.get("ownership", {}).get("percentOwned", 0),
    }


# ---- Team name cache ----

_team_names = {}  # team_id -> name


def _ensure_team_names():
    """Fetch team names once and cache them."""
    global _team_names
    if _team_names:
        return
    try:
        data = _espn_get("mTeam")
        for team in data.get("teams", []):
            tid = team["id"]
            loc = team.get("location", "") or ""
            nick = team.get("nickname", "") or ""
            name = f"{loc} {nick}".strip()
            if not name:
                name = team.get("name", "") or team.get("abbrev", f"Team {tid}")
            _team_names[tid] = name
    except Exception:
        pass


def _get_team_name(team_data):
    """Get team name from team data dict, with fallback to cache."""
    tid = team_data.get("id", 0)
    # Try the team data first
    loc = team_data.get("location", "") or ""
    nick = team_data.get("nickname", "") or ""
    name = f"{loc} {nick}".strip()
    if name and name != f"Team {tid}":
        return name
    # Check explicit name field
    name = team_data.get("name", "") or ""
    if name and name != f"Team {tid}":
        return name
    # Fall back to cached names
    _ensure_team_names()
    return _team_names.get(tid, f"Team {tid}")


# ---- Roster fetchers ----

def fetch_all_rosters():
    """Fetch all 8 teams' rosters. Returns dict of team_id -> roster info."""
    data = _espn_get("mRoster")
    rosters = {}

    for team in data.get("teams", []):
        team_id = team["id"]
        team_name = _get_team_name(team)

        players = []
        for entry in team.get("roster", {}).get("entries", []):
            p = _parse_player(entry)
            players.append(p)

        rosters[team_id] = {
            "team_id": team_id,
            "team_name": team_name,
            "players": players,
        }

    return rosters


def fetch_my_roster():
    """Fetch our team's roster (team ID 10)."""
    rosters = fetch_all_rosters()
    return rosters.get(MY_TEAM_ID, {"team_id": MY_TEAM_ID, "players": []})


def fetch_opponent_roster(team_id):
    """Fetch a specific opponent's roster."""
    rosters = fetch_all_rosters()
    return rosters.get(team_id, {"team_id": team_id, "players": []})


# ---- Matchup scores ----

def fetch_current_scoring_period():
    """Get the current scoring period ID from league settings."""
    data = _espn_get("mSettings")
    return data.get("scoringPeriodId", 1)


def fetch_current_matchup_period():
    """
    Get the current matchup period ID and matchup metadata.

    Primary source: data/league_schedule_2026.json (parsed from ESPN schedule PDF).
    This gives exact matchup dates, lengths, and opponent info without relying on
    the ESPN API's matchupPeriods mapping (which is incomplete early in season).

    Falls back to ESPN API if the schedule JSON is missing.
    """
    data = _espn_get("mSettings")
    status = data.get("status", {})
    settings = data.get("settings", {})

    current_mp = status.get("currentMatchupPeriod", 1)
    scoring_period_id = data.get("scoringPeriodId", 1)

    # Acquisition settings (needed regardless of schedule source)
    acq_settings = settings.get("acquisitionSettings", {})
    per_period_limit = acq_settings.get("matchupAcquisitionLimit", 7)
    per_scoring_period = acq_settings.get("matchupLimitPerScoringPeriod", False)

    # Try schedule JSON first (authoritative source)
    schedule = _load_schedule()
    matchup_entry = None
    if schedule.get("matchups"):
        for m in schedule["matchups"]:
            if m["matchup_period"] == current_mp:
                matchup_entry = m
                break

    if matchup_entry:
        matchup_length = matchup_entry["days"]
        start_date = date.fromisoformat(matchup_entry["start"])
        end_date = date.fromisoformat(matchup_entry["end"])
        today = date.today()
        day_of_matchup = (today - start_date).days + 1
        days_remaining = (end_date - today).days + 1  # including today
        log.info(f"Schedule: MP {current_mp}, {matchup_entry['start']} to {matchup_entry['end']} ({matchup_length}d)")
    else:
        # Fallback: estimate from ESPN API
        log.warning("Schedule JSON not found — estimating matchup length from API")
        matchup_length = 7
        day_of_matchup = 1
        days_remaining = 7

    if per_scoring_period:
        moves_max = int(per_period_limit * matchup_length)
    else:
        moves_max = int(per_period_limit) if per_period_limit > 0 else -1

    # Look up our opponent from the schedule
    opponent_info = {}
    our_opponents = schedule.get("our_opponents", {})
    opp_entry = our_opponents.get(str(current_mp))
    if opp_entry:
        # Determine opponent team ID and name
        opp_id = opp_entry.get("away_id") or opp_entry.get("home_id")
        opp_name = opp_entry.get("away_team") or opp_entry.get("home_team")
        opponent_info = {"opponent_team_id": opp_id, "opponent_name": opp_name}

    return {
        "matchup_period_id": current_mp,
        "scoring_period_id": scoring_period_id,
        "matchup_length_days": matchup_length,
        "day_of_matchup": day_of_matchup,
        "days_remaining": days_remaining if matchup_entry else matchup_length,
        "matchup_start": matchup_entry["start"] if matchup_entry else None,
        "matchup_end": matchup_entry["end"] if matchup_entry else None,
        "moves_max": moves_max,
        **opponent_info,
    }


def fetch_matchup_scores(scoring_period_id=None, matchup_period_id=None):
    """
    Fetch per-category matchup scores using mBoxscore view.
    Filters to the current matchup period to avoid returning wrong opponent.
    Returns our matchup with category-by-category breakdown.
    """
    if scoring_period_id is None:
        scoring_period_id = fetch_current_scoring_period()

    # Get current matchup period if not provided
    if matchup_period_id is None:
        data_settings = _espn_get("mSettings")
        matchup_period_id = data_settings.get("status", {}).get("currentMatchupPeriod", 1)

    data = _espn_get("mBoxscore", {"scoringPeriodId": scoring_period_id})

    # Find our matchup — filter to current matchup period only
    our_matchup = None
    all_matchups = []

    for item in data.get("schedule", []):
        if item.get("matchupPeriodId") != matchup_period_id:
            continue

        home = item.get("home", {})
        away = item.get("away", {})
        home_id = home.get("teamId")
        away_id = away.get("teamId")

        matchup = _parse_matchup_side(home, away, data)

        all_matchups.append(matchup)

        if home_id == MY_TEAM_ID or away_id == MY_TEAM_ID:
            our_matchup = matchup

    if our_matchup:
        # Validate: opponent should not be us
        if our_matchup["home_team_id"] == MY_TEAM_ID:
            opp_id = our_matchup["away_team_id"]
        else:
            opp_id = our_matchup["home_team_id"]
        log.info(f"Matchup found: MP {matchup_period_id}, opponent team_id={opp_id}")
    else:
        log.warning(f"No matchup found for MP {matchup_period_id}")

    return our_matchup, all_matchups


def _parse_matchup_side(home, away, full_data):
    """Parse a matchup into category scores."""
    matchup = {
        "home_team_id": home.get("teamId"),
        "away_team_id": away.get("teamId"),
        "home_wins": 0, "home_losses": 0, "home_ties": 0,
        "away_wins": 0, "away_losses": 0, "away_ties": 0,
        "categories": {},
    }

    # Get team names
    _ensure_team_names()
    matchup["home_team_name"] = _team_names.get(home.get("teamId"), f"Team {home.get('teamId')}")
    matchup["away_team_name"] = _team_names.get(away.get("teamId"), f"Team {away.get('teamId')}")

    home_cum = home.get("cumulativeScore", {})
    away_cum = away.get("cumulativeScore", {})

    matchup["home_wins"] = home_cum.get("wins", 0)
    matchup["home_losses"] = home_cum.get("losses", 0)
    matchup["home_ties"] = home_cum.get("ties", 0)
    matchup["away_wins"] = away_cum.get("wins", 0)
    matchup["away_losses"] = away_cum.get("losses", 0)
    matchup["away_ties"] = away_cum.get("ties", 0)

    home_sbs = home_cum.get("scoreByStat") or {}
    away_sbs = away_cum.get("scoreByStat") or {}

    for sid in SCORING_CAT_IDS:
        cat_name = STATS_MAP.get(sid, f"id_{sid}")
        h_stat = home_sbs.get(str(sid), {})
        a_stat = away_sbs.get(str(sid), {})
        matchup["categories"][cat_name] = {
            "home_value": h_stat.get("score", 0),
            "away_value": a_stat.get("score", 0),
            "home_result": h_stat.get("result"),
            "away_result": a_stat.get("result"),
        }

    return matchup


# ---- Free agents ----

def fetch_free_agents(count=250):
    """Fetch top free agents with player details."""
    import json
    filter_obj = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
            "limit": count,
            "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
        }
    }
    headers = {"x-fantasy-filter": json.dumps(filter_obj)}

    _rate.throttle()

    r = requests.get(
        ESPN_BASE_URL,
        params={"view": "kona_player_info"},
        cookies=ESPN_COOKIES,
        headers=headers,
    )

    if r.status_code == 401:
        raise PermissionError("ESPN API auth failed — cookies likely expired.")
    r.raise_for_status()

    data = r.json()
    players = []
    for entry in data.get("players", []):
        p = _parse_player(entry)
        players.append(p)

    return players


# ---- Standings ----

def fetch_standings():
    """Fetch current standings."""
    data = _espn_get("mStandings")
    standings = []

    for team in data.get("teams", []):
        tid = team["id"]
        team_name = _get_team_name(team)

        record = team.get("record", {}).get("overall", {})
        standings.append({
            "team_id": tid,
            "team_name": team_name,
            "wins": record.get("wins", 0),
            "losses": record.get("losses", 0),
            "ties": record.get("ties", 0),
            "standing": record.get("playoffSeed", 0),
            "streak_type": record.get("streakType"),
            "streak_length": record.get("streakLength", 0),
        })

    standings.sort(key=lambda x: (-x["wins"], x["losses"]))
    return standings
