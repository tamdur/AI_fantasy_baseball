"""
Weather data fetcher for game-day conditions.
Uses api.weather.gov (free, no auth, no key needed).
Provides: PPD risk, HR-rate wind adjustments, temperature effects.
"""

import logging
from datetime import datetime

import requests

log = logging.getLogger(__name__)

# MLB ballpark coordinates and dome status
BALLPARKS = {
    "ARI": {"name": "Chase Field", "lat": 33.4455, "lon": -112.0667, "dome": True},
    "ATL": {"name": "Truist Park", "lat": 33.8907, "lon": -84.4677, "dome": False},
    "BAL": {"name": "Camden Yards", "lat": 39.2838, "lon": -76.6216, "dome": False},
    "BOS": {"name": "Fenway Park", "lat": 42.3467, "lon": -71.0972, "dome": False},
    "CHC": {"name": "Wrigley Field", "lat": 41.9484, "lon": -87.6553, "dome": False},
    "CWS": {"name": "Guaranteed Rate", "lat": 41.8299, "lon": -87.6338, "dome": False},
    "CIN": {"name": "Great American", "lat": 39.0974, "lon": -84.5069, "dome": False},
    "CLE": {"name": "Progressive Field", "lat": 41.4959, "lon": -81.6852, "dome": False},
    "COL": {"name": "Coors Field", "lat": 39.7559, "lon": -104.9942, "dome": False},
    "DET": {"name": "Comerica Park", "lat": 42.3390, "lon": -83.0485, "dome": False},
    "HOU": {"name": "Minute Maid", "lat": 29.7572, "lon": -95.3555, "dome": True},
    "KC":  {"name": "Kauffman Stadium", "lat": 39.0517, "lon": -94.4803, "dome": False},
    "LAA": {"name": "Angel Stadium", "lat": 33.8003, "lon": -117.8827, "dome": False},
    "LAD": {"name": "Dodger Stadium", "lat": 34.0739, "lon": -118.2400, "dome": False},
    "MIA": {"name": "LoanDepot Park", "lat": 25.7781, "lon": -80.2196, "dome": True},
    "MIL": {"name": "American Family", "lat": 43.0280, "lon": -87.9712, "dome": True},
    "MIN": {"name": "Target Field", "lat": 44.9817, "lon": -93.2776, "dome": False},
    "NYM": {"name": "Citi Field", "lat": 40.7571, "lon": -73.8458, "dome": False},
    "NYY": {"name": "Yankee Stadium", "lat": 40.8296, "lon": -73.9262, "dome": False},
    "OAK": {"name": "Coliseum", "lat": 37.7516, "lon": -122.2005, "dome": False},
    "PHI": {"name": "Citizens Bank", "lat": 39.9061, "lon": -75.1665, "dome": False},
    "PIT": {"name": "PNC Park", "lat": 40.4469, "lon": -80.0058, "dome": False},
    "SD":  {"name": "Petco Park", "lat": 32.7073, "lon": -117.1566, "dome": False},
    "SF":  {"name": "Oracle Park", "lat": 37.7786, "lon": -122.3893, "dome": False},
    "SEA": {"name": "T-Mobile Park", "lat": 47.5914, "lon": -122.3325, "dome": True},
    "STL": {"name": "Busch Stadium", "lat": 38.6226, "lon": -90.1928, "dome": False},
    "TB":  {"name": "Tropicana Field", "lat": 27.7682, "lon": -82.6534, "dome": True},
    "TEX": {"name": "Globe Life Field", "lat": 32.7473, "lon": -97.0835, "dome": True},
    "TOR": {"name": "Rogers Centre", "lat": 43.6414, "lon": -79.3894, "dome": True},
    "WSH": {"name": "Nationals Park", "lat": 38.8731, "lon": -77.0074, "dome": False},
}


def fetch_game_weather(games):
    """
    Fetch weather for today's games.

    Args:
        games: list of dicts with at least 'home_team' (abbreviation) and 'game_time'

    Returns:
        dict of game_key -> weather info with PPD risk and HR modifier
    """
    results = {}

    for game in games:
        home = game.get("home_team") or game.get("team", "")
        # Normalize team abbreviation
        park = BALLPARKS.get(home)
        if not park:
            continue

        game_key = f"{game.get('away_team', '?')}@{home}"

        # Domed stadiums: no weather impact
        if park["dome"]:
            results[game_key] = {
                "park": park["name"],
                "dome": True,
                "ppd_risk": "NONE",
                "hr_modifier": 0,
                "temp_f": None,
                "wind_mph": None,
                "conditions": "Dome — no weather impact",
            }
            continue

        # Fetch weather from api.weather.gov
        try:
            weather = _fetch_nws_forecast(park["lat"], park["lon"])
            if weather:
                ppd_risk = _assess_ppd_risk(weather)
                hr_mod = _compute_hr_modifier(weather)
                results[game_key] = {
                    "park": park["name"],
                    "dome": False,
                    "ppd_risk": ppd_risk,
                    "hr_modifier": hr_mod,
                    "temp_f": weather.get("temperature"),
                    "wind_mph": weather.get("wind_speed"),
                    "wind_direction": weather.get("wind_direction"),
                    "precip_chance": weather.get("precip_chance"),
                    "conditions": weather.get("short_forecast", ""),
                }
        except Exception as e:
            log.warning(f"Weather fetch failed for {game_key}: {e}")

    return results


def _fetch_nws_forecast(lat, lon):
    """Fetch hourly forecast from NWS api.weather.gov."""
    try:
        # Step 1: Get the forecast grid point
        point_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
        r = requests.get(point_url, headers={"User-Agent": "FantasyBaseball/1.0"}, timeout=10)
        r.raise_for_status()
        point_data = r.json()

        # Step 2: Get the hourly forecast
        hourly_url = point_data["properties"]["forecastHourly"]
        r = requests.get(hourly_url, headers={"User-Agent": "FantasyBaseball/1.0"}, timeout=10)
        r.raise_for_status()
        forecast_data = r.json()

        # Find the forecast period closest to typical game time (7 PM local)
        # For simplicity, grab the next few hours
        periods = forecast_data["properties"]["periods"]
        if not periods:
            return None

        # Use the period closest to evening (game time)
        now = datetime.now()
        target_hour = 19  # 7 PM
        best_period = periods[0]
        for p in periods[:24]:
            period_time = datetime.fromisoformat(p["startTime"].replace("Z", "+00:00"))
            if period_time.hour >= target_hour - 2 and period_time.hour <= target_hour + 2:
                best_period = p
                break

        wind_str = best_period.get("windSpeed", "0 mph")
        wind_mph = int("".join(c for c in wind_str.split()[0] if c.isdigit()) or "0")

        precip = best_period.get("probabilityOfPrecipitation", {}).get("value", 0) or 0

        return {
            "temperature": best_period.get("temperature"),
            "wind_speed": wind_mph,
            "wind_direction": best_period.get("windDirection", ""),
            "precip_chance": precip,
            "short_forecast": best_period.get("shortForecast", ""),
        }

    except Exception as e:
        log.debug(f"NWS forecast error: {e}")
        return None


def _assess_ppd_risk(weather):
    """Assess postponement risk."""
    precip = weather.get("precip_chance", 0) or 0
    if precip >= 80:
        return "HIGH"
    elif precip >= 50:
        return "MODERATE"
    elif precip >= 30:
        return "LOW"
    return "NONE"


def _compute_hr_modifier(weather):
    """
    Compute HR rate modifier based on weather.
    Returns a float: -0.15 to +0.25
    Positive = more HR likely, Negative = fewer HR likely
    """
    modifier = 0.0

    # Temperature effect
    temp = weather.get("temperature")
    if temp is not None:
        if temp < 50:
            modifier -= 0.10  # cold suppresses HR
        elif temp > 85:
            modifier += 0.05  # heat helps slightly

    # Wind effect (simplified — would need park orientation for full accuracy)
    wind = weather.get("wind_speed", 0) or 0
    if wind >= 15:
        # Strong wind has big effect but direction matters
        # Without park orientation, use a moderate estimate
        modifier += 0.08  # assume mixed effect for strong wind
    elif wind >= 10:
        modifier += 0.03

    return round(modifier, 3)
