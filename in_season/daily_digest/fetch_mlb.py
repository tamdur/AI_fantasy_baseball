"""
MLB Stats API fetchers — probable pitchers, weekly schedule, transactions.
Free, public, no auth required.
"""

import logging
from datetime import datetime, timedelta
from collections import Counter

import requests

log = logging.getLogger(__name__)

MLB_BASE = "https://statsapi.mlb.com/api/v1"


def _mlb_get(endpoint, params=None):
    """GET request to MLB Stats API."""
    r = requests.get(f"{MLB_BASE}/{endpoint}", params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_probable_pitchers(date=None):
    """
    Fetch today's probable pitchers with MLBAM IDs.
    Returns list of dicts with pitcher info + game context.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    data = _mlb_get("schedule", {
        "date": date,
        "sportId": 1,
        "hydrate": "probablePitcher,team",
    })

    pitchers = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_time = game.get("gameDate", "")
            game_pk = game.get("gamePk")
            status = game.get("status", {}).get("detailedState", "")

            for side in ["away", "home"]:
                team_data = game.get("teams", {}).get(side, {})
                pp = team_data.get("probablePitcher", {})
                if not pp:
                    continue

                opp_side = "home" if side == "away" else "away"
                opp_team = game.get("teams", {}).get(opp_side, {})

                pitchers.append({
                    "name": pp.get("fullName", ""),
                    "mlbam_id": pp.get("id"),
                    "team": team_data.get("team", {}).get("abbreviation", ""),
                    "team_name": team_data.get("team", {}).get("name", ""),
                    "opponent": opp_team.get("team", {}).get("abbreviation", ""),
                    "opponent_name": opp_team.get("team", {}).get("name", ""),
                    "home_away": side,
                    "game_time": game_time,
                    "game_pk": game_pk,
                    "game_status": status,
                })

    log.info(f"Found {len(pitchers)} probable pitchers for {date}")
    return pitchers


def fetch_weekly_schedule(start_date=None, end_date=None):
    """
    Fetch a week's schedule to identify two-start pitchers and games per team.
    Returns:
        two_starters: list of pitchers appearing 2+ times
        games_per_team: dict of team_abbrev -> game_count
    """
    if start_date is None:
        # Default to current week (Mon-Sun)
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        start_date = monday.strftime("%Y-%m-%d")
    if end_date is None:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = (start_dt + timedelta(days=6)).strftime("%Y-%m-%d")

    data = _mlb_get("schedule", {
        "startDate": start_date,
        "endDate": end_date,
        "sportId": 1,
        "hydrate": "probablePitcher,team",
    })

    pitcher_appearances = Counter()  # mlbam_id -> count
    pitcher_info = {}  # mlbam_id -> info dict
    team_games = Counter()  # team_abbrev -> game count
    pitcher_matchups = {}  # mlbam_id -> list of (date, opponent)

    for date_entry in data.get("dates", []):
        game_date = date_entry.get("date", "")
        for game in date_entry.get("games", []):
            for side in ["away", "home"]:
                team_data = game.get("teams", {}).get(side, {})
                team_abbr = team_data.get("team", {}).get("abbreviation", "")
                team_games[team_abbr] += 1

                pp = team_data.get("probablePitcher", {})
                if pp and pp.get("id"):
                    pid = pp["id"]
                    pitcher_appearances[pid] += 1

                    opp_side = "home" if side == "away" else "away"
                    opp_abbr = game.get("teams", {}).get(opp_side, {}).get("team", {}).get("abbreviation", "")

                    if pid not in pitcher_info:
                        pitcher_info[pid] = {
                            "name": pp.get("fullName", ""),
                            "mlbam_id": pid,
                            "team": team_abbr,
                        }
                    if pid not in pitcher_matchups:
                        pitcher_matchups[pid] = []
                    pitcher_matchups[pid].append({
                        "date": game_date,
                        "opponent": opp_abbr,
                        "home_away": side,
                    })

    # Identify two-start pitchers
    two_starters = []
    for pid, count in pitcher_appearances.items():
        if count >= 2:
            info = pitcher_info[pid].copy()
            info["start_count"] = count
            info["matchups"] = pitcher_matchups.get(pid, [])
            two_starters.append(info)

    log.info(f"Weekly schedule {start_date} to {end_date}: {len(two_starters)} two-start pitchers")
    return two_starters, dict(team_games)


def fetch_transactions(date=None):
    """
    Fetch MLB transactions for a given date.
    Filters for fantasy-relevant moves: call-ups, DFA, trades.
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    try:
        data = _mlb_get("transactions", {"date": date})
    except requests.HTTPError as e:
        log.warning(f"Transactions fetch failed: {e}")
        return []

    relevant_types = {"Recalled", "Selected", "Designated for Assignment",
                      "Trade", "Claimed off Waivers", "Signed to a Mlb Contract",
                      "Optioned", "Placed on"}

    transactions = []
    for txn in data.get("transactions", []):
        txn_type = txn.get("typeDesc", "")

        # Filter to fantasy-relevant transaction types
        if not any(rt in txn_type for rt in relevant_types):
            continue

        player = txn.get("player", {})
        transactions.append({
            "type": txn_type,
            "description": txn.get("description", ""),
            "player_name": player.get("fullName", ""),
            "mlbam_id": player.get("id"),
            "team": txn.get("team", {}).get("abbreviation", ""),
            "date": txn.get("date", date),
        })

    log.info(f"Found {len(transactions)} relevant transactions for {date}")
    return transactions
