"""
Configuration for the daily digest newsletter pipeline.
Loads credentials from environment variables or .env file.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Project root
ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

# ESPN API
LEAGUE_ID = 84209353
MY_TEAM_ID = 10
SWID = os.environ.get("ESPN_SWID", "")
ESPN_S2 = os.environ.get("ESPN_S2", "")
ESPN_COOKIES = {"swid": SWID, "espn_s2": ESPN_S2}
ESPN_BASE_URL = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/2026/segments/0/leagues/{LEAGUE_ID}"

# Anthropic — no API key needed; we use Claude Code CLI (MAX plan)

# Rate limiting (seconds between requests)
ESPN_RATE_LIMIT = 1.0
FANGRAPHS_RATE_LIMIT = 3.0

# FanGraphs RoS projection types (primary + fallbacks)
ROS_PROJECTION_PRIMARY = "ratcdc"  # ATC RoS
ROS_PROJECTION_FALLBACK = "rsteamer"  # Steamer RoS
ROS_MULTI_SYSTEMS = ["rsteamer", "rzips", "ratcdc", "rthebatx", "rfangraphsdc", "roopsy"]

# Cache settings
FANGRAPHS_CACHE_HOURS = 24  # RoS projections cache
MULTI_SYSTEM_CACHE_DAYS = 7  # Multi-system disagreement cache

# ESPN stat ID map (verified)
STATS_MAP = {
    0: "AB", 1: "H", 2: "AVG", 5: "HR", 8: "TB", 10: "BB",
    16: "PA", 17: "OBP", 20: "R", 21: "RBI", 23: "SB", 24: "CS",
    25: "SBN", 27: "SO", 41: "WHIP", 47: "ERA", 48: "K",
    63: "QS", 82: "KBB", 83: "SVHD",
}

# Our league's 12 scoring category stat IDs
SCORING_CAT_IDS = [20, 5, 8, 21, 25, 17, 48, 63, 47, 41, 82, 83]

# ESPN position maps
POS_MAP = {
    1: "SP", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS",
    7: "LF", 8: "CF", 9: "RF", 10: "DH", 11: "RP",
}
SLOT_MAP = {
    0: "C", 1: "1B", 2: "2B", 3: "3B", 4: "SS", 5: "OF", 6: "MI",
    7: "CI", 11: "DH", 12: "UTIL", 13: "P", 14: "SP", 15: "RP",
    16: "BE", 17: "IL", 19: "IF",
}

# ESPN pro team ID -> abbreviation (for player disambiguation)
PRO_TEAM_ABBREV = {
    1: "BAL", 2: "BOS", 3: "LAA", 4: "CHW", 5: "CLE", 6: "DET",
    7: "KC", 8: "MIL", 9: "MIN", 10: "NYY", 11: "ATH", 12: "SEA",
    13: "TEX", 14: "TOR", 15: "ATL", 16: "CHC", 17: "CIN", 18: "HOU",
    19: "LAD", 20: "WSH", 21: "NYM", 22: "PHI", 23: "PIT", 24: "STL",
    25: "SD", 26: "SF", 27: "COL", 28: "MIA", 29: "ARI", 30: "TB",
}

# League constants and ID utilities (shared module in model/)
sys.path.insert(0, str(ROOT / "model"))
from league import (
    HITTING_CATS, PITCHING_CATS, ALL_CATS, LOWER_IS_BETTER,
    NUM_TEAMS, ROSTER_SLOTS, load_id_map, join_ids,
)

# Paths
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
EXISTING_TOOLS = ROOT / "existing-tools"
ANALYSIS_DIR = ROOT / "analysis"
DATA_DIR = ROOT / "data"

OUTPUT_DIR.mkdir(exist_ok=True)


def validate_config():
    """Check that required credentials are present."""
    issues = []
    if not SWID:
        issues.append("ESPN_SWID not set")
    if not ESPN_S2:
        issues.append("ESPN_S2 not set")
    # Check if claude CLI is available
    import shutil
    if not shutil.which("claude"):
        issues.append("Claude Code CLI not found in PATH")
    return issues
