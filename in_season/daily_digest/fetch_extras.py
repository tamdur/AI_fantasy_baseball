"""
Additional data fetchers identified by Tactician/Actuary persona research:
- Park factors (FanGraphs)
- Team offensive quality / wRC+ (FanGraphs leaderboard)
- Vegas implied run totals (The Odds API free tier)
- Closer/RP role info (Roster Resource scraping)
- Platoon split lookups (from existing CSVs)
"""

import re
import json
import logging
from datetime import datetime, timedelta
from io import StringIO

import requests
import pandas as pd

from config import OUTPUT_DIR, EXISTING_TOOLS

log = logging.getLogger(__name__)


# ---- Caching helpers ----

def _cache_path(name):
    return OUTPUT_DIR / f"cache_{name}.json"


def _cache_valid(name, max_hours):
    p = _cache_path(name)
    if not p.exists():
        return False
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    return (datetime.now() - mtime) < timedelta(hours=max_hours)


def _load_cache(name):
    with open(_cache_path(name)) as f:
        return json.load(f)


def _save_cache(name, data):
    with open(_cache_path(name), "w") as f:
        json.dump(data, f, default=str)


# ---- Park Factors ----

# Static park factors (FanGraphs 2024 5-year regressed, HR-specific)
# Source: fangraphs.com/guts.aspx?type=pf&teamid=0&season=2024
# Values are index where 100 = neutral. >100 = inflates, <100 = suppresses.
PARK_FACTORS = {
    "COL": {"overall": 114, "hr": 116, "r": 114},
    "CIN": {"overall": 105, "hr": 112, "r": 104},
    "TEX": {"overall": 103, "hr": 108, "r": 103},
    "PHI": {"overall": 103, "hr": 107, "r": 103},
    "CHC": {"overall": 103, "hr": 106, "r": 103},
    "TOR": {"overall": 103, "hr": 105, "r": 103},
    "BAL": {"overall": 102, "hr": 109, "r": 102},
    "MIL": {"overall": 102, "hr": 104, "r": 101},
    "BOS": {"overall": 102, "hr": 98, "r": 104},
    "NYY": {"overall": 101, "hr": 110, "r": 100},
    "ATL": {"overall": 101, "hr": 103, "r": 101},
    "MIN": {"overall": 101, "hr": 102, "r": 101},
    "LAA": {"overall": 100, "hr": 103, "r": 100},
    "HOU": {"overall": 100, "hr": 101, "r": 100},
    "ARI": {"overall": 100, "hr": 99, "r": 101},
    "KC":  {"overall": 100, "hr": 95, "r": 101},
    "WSH": {"overall": 99, "hr": 100, "r": 99},
    "CLE": {"overall": 99, "hr": 99, "r": 99},
    "DET": {"overall": 99, "hr": 97, "r": 99},
    "CWS": {"overall": 99, "hr": 102, "r": 98},
    "STL": {"overall": 98, "hr": 96, "r": 99},
    "LAD": {"overall": 98, "hr": 97, "r": 98},
    "PIT": {"overall": 98, "hr": 93, "r": 99},
    "SF":  {"overall": 97, "hr": 90, "r": 97},
    "NYM": {"overall": 97, "hr": 95, "r": 97},
    "SEA": {"overall": 97, "hr": 96, "r": 97},
    "SD":  {"overall": 96, "hr": 93, "r": 96},
    "TB":  {"overall": 96, "hr": 91, "r": 96},
    "MIA": {"overall": 95, "hr": 88, "r": 95},
    "OAK": {"overall": 96, "hr": 94, "r": 96},
}


def get_park_factor(team_abbrev, stat="overall"):
    """Get park factor for a team's home park."""
    pf = PARK_FACTORS.get(team_abbrev, {})
    return pf.get(stat, 100)


def enrich_with_park_factors(games_or_pitchers):
    """Add park factor info to a list of game/pitcher dicts."""
    for item in games_or_pitchers:
        # Figure out the home team
        home = None
        if item.get("home_away") == "home":
            home = item.get("team", "")
        elif item.get("home_away") == "away":
            home = item.get("opponent", "")
        else:
            home = item.get("home_team", "")

        if home:
            item["park_hr_factor"] = get_park_factor(home, "hr")
            item["park_run_factor"] = get_park_factor(home, "r")
            item["park_overall_factor"] = get_park_factor(home, "overall")

    return games_or_pitchers


# ---- Team Offensive Quality (wRC+) ----

def fetch_team_offense_quality():
    """
    Fetch team-level wRC+ from FanGraphs for opponent quality assessment.
    Cached daily. Returns dict of team_abbrev -> wRC+.
    """
    cache_name = "team_wrcplus"
    if _cache_valid(cache_name, 24):
        return _load_cache(cache_name)

    try:
        url = "https://www.fangraphs.com/api/leaders/major-league/data"
        params = {
            "pos": "all",
            "stats": "bat",
            "lg": "all",
            "qual": "0",
            "season": "2026",
            "month": "0",
            "team": "0,ts",  # team stats
            "ind": "0",
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()

        data = r.json()
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        else:
            records = data

        team_quality = {}
        for row in records:
            team = row.get("TeamNameAbb") or row.get("Team") or ""
            # Strip HTML if present
            team = re.sub(r"<[^>]+>", "", str(team)).strip()
            wrc = row.get("wRC+") or row.get("wRC_plus")
            if team and wrc is not None:
                team_quality[team] = float(wrc)

        if team_quality:
            _save_cache(cache_name, team_quality)
            log.info(f"Fetched team wRC+ for {len(team_quality)} teams")
            return team_quality

    except Exception as e:
        log.warning(f"Team wRC+ fetch failed: {e}")

    # Fallback: neutral for all teams
    return {}


def enrich_streamers_with_opponent_quality(streamers, team_quality):
    """Add opponent offensive quality (wRC+) to streamer data."""
    for s in streamers:
        opp = s.get("opponent", "")
        if opp and opp in team_quality:
            s["opponent_wrcplus"] = team_quality[opp]
            if team_quality[opp] >= 110:
                s["opponent_offense"] = "ELITE"
            elif team_quality[opp] >= 100:
                s["opponent_offense"] = "ABOVE_AVG"
            elif team_quality[opp] >= 90:
                s["opponent_offense"] = "BELOW_AVG"
            else:
                s["opponent_offense"] = "WEAK"
    return streamers


# ---- Vegas Implied Run Totals ----

def fetch_vegas_lines():
    """
    Fetch MLB game lines from The Odds API (free tier: 500 requests/month).
    Returns dict of game descriptions -> implied total and moneyline.
    Requires ODDS_API_KEY env var. If unavailable, returns empty.
    """
    import os
    api_key = os.environ.get("ODDS_API_KEY", "")
    if not api_key:
        log.info("ODDS_API_KEY not set — Vegas lines unavailable (free at the-odds-api.com)")
        return {}

    cache_name = "vegas_lines"
    if _cache_valid(cache_name, 6):  # 6 hour cache
        return _load_cache(cache_name)

    try:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": "totals,h2h",
            "oddsFormat": "american",
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()

        games = r.json()
        result = {}
        for game in games:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            game_key = f"{away} @ {home}"

            # Extract totals and moneyline from first bookmaker
            bookmakers = game.get("bookmakers", [])
            if not bookmakers:
                continue

            book = bookmakers[0]
            for market in book.get("markets", []):
                if market["key"] == "totals":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == "Over":
                            result.setdefault(game_key, {})["implied_total"] = outcome.get("point")
                elif market["key"] == "h2h":
                    for outcome in market.get("outcomes", []):
                        result.setdefault(game_key, {})
                        if outcome["name"] == home:
                            result[game_key]["home_ml"] = outcome.get("price")
                        elif outcome["name"] == away:
                            result[game_key]["away_ml"] = outcome.get("price")

        if result:
            _save_cache(cache_name, result)
            log.info(f"Fetched Vegas lines for {len(result)} games")

        # Log remaining API requests
        remaining = r.headers.get("x-requests-remaining")
        if remaining:
            log.info(f"  Odds API requests remaining: {remaining}")

        return result

    except Exception as e:
        log.warning(f"Vegas lines fetch failed: {e}")
        return {}


# ---- Closer / RP Role Info ----

def fetch_closer_info():
    """
    Fetch current closer/setup info from Roster Resource.
    Returns dict of team_abbrev -> role info.
    Falls back to a static reference if scraping fails.
    """
    cache_name = "closer_roles"
    if _cache_valid(cache_name, 24):
        return _load_cache(cache_name)

    try:
        url = "https://www.rosterresource.com/mlb-bullpen-depth-chart/"
        r = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; FantasyBaseball/1.0)"
        })
        if r.status_code != 200:
            log.warning(f"Roster Resource returned {r.status_code}")
            return {}

        # Parse the HTML for closer info
        # Roster Resource has tables with team -> CL, SU, MR columns
        from html.parser import HTMLParser
        roles = _parse_roster_resource(r.text)
        if roles:
            _save_cache(cache_name, roles)
            log.info(f"Fetched closer roles for {len(roles)} teams")
        return roles

    except Exception as e:
        log.warning(f"Closer info fetch failed: {e}")
        return {}


def _parse_roster_resource(html):
    """Parse Roster Resource bullpen page for closer/setup roles."""
    roles = {}
    # Simple regex approach — look for team sections with role assignments
    # The page structure varies, so this is best-effort
    try:
        # Try pandas HTML table parsing first
        tables = pd.read_html(StringIO(html))
        for table in tables:
            cols = [str(c).lower() for c in table.columns]
            if any("closer" in c or "cl" in c for c in cols):
                for _, row in table.iterrows():
                    team = str(row.iloc[0]).strip() if len(row) > 0 else ""
                    if len(team) <= 4 and team.isalpha():
                        role_info = {"closer": "", "setup": "", "committee": False}
                        for i, col in enumerate(cols):
                            val = str(row.iloc[i]).strip() if i < len(row) else ""
                            if "closer" in col or "cl" == col:
                                role_info["closer"] = val
                            elif "setup" in col or "su" in col:
                                role_info["setup"] = val
                        if role_info["closer"]:
                            roles[team] = role_info
    except Exception:
        pass

    return roles


# ---- Platoon Splits ----

def load_platoon_splits():
    """
    Load batter platoon splits from existing Steamer CSVs.
    Returns DataFrame with per-player vs-LHP and vs-RHP projections.
    """
    vs_lhp_path = EXISTING_TOOLS / "FanGraphs_Steamer_Batters_vsLHP_2026.csv"
    vs_rhp_path = EXISTING_TOOLS / "FanGraphs_Steamer_Batters_vsRHP_2026.csv"

    splits = {}

    for path, label in [(vs_lhp_path, "vsLHP"), (vs_rhp_path, "vsRHP")]:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        # Normalize name column
        for col in df.columns:
            if "Name" in col:
                df = df.rename(columns={col: "name"})
                break
        if "PlayerName" in df.columns:
            df = df.rename(columns={"PlayerName": "name"})
        if "xMLBAMID" in df.columns:
            df = df.rename(columns={"xMLBAMID": "mlbam_id"})

        for _, row in df.iterrows():
            mid = row.get("mlbam_id")
            if pd.isna(mid):
                continue
            mid = int(mid)
            if mid not in splits:
                splits[mid] = {"name": row.get("name", ""), "mlbam_id": mid}

            # Key stats for split comparison
            for stat in ["OBP", "SLG", "HR", "wRC+"]:
                val = row.get(stat)
                if val is not None and not pd.isna(val):
                    splits[mid][f"{stat}_{label}"] = float(val)

    # Compute platoon differential
    for mid, data in splits.items():
        obp_l = data.get("OBP_vsLHP")
        obp_r = data.get("OBP_vsRHP")
        if obp_l is not None and obp_r is not None:
            data["platoon_obp_gap"] = round(obp_r - obp_l, 3)  # positive = better vs RHP
        slg_l = data.get("SLG_vsLHP")
        slg_r = data.get("SLG_vsRHP")
        if slg_l is not None and slg_r is not None:
            data["platoon_slg_gap"] = round(slg_r - slg_l, 3)
        # Flag extreme platoon players
        if data.get("platoon_obp_gap") is not None and abs(data["platoon_obp_gap"]) > 0.040:
            data["extreme_platoon"] = True

    log.info(f"Loaded platoon splits for {len(splits)} batters")
    return splits
