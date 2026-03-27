"""
Preprocessing: ID bridging, data merging, and briefing book generation.
Transforms raw API data into the compact JSON structure for agent prompts.
"""

import logging
from datetime import datetime

import pandas as pd
import numpy as np

from config import (
    MY_TEAM_ID, HITTING_CATS, PITCHING_CATS, ALL_CATS, LOWER_IS_BETTER,
    ANALYSIS_DIR, load_id_map, join_ids, PRO_TEAM_ABBREV,
)

log = logging.getLogger(__name__)


# ---- ID Resolution ----

def build_id_map():
    """Load SFBB Player ID Map and build lookup dicts."""
    id_map = load_id_map()
    mlbam_to_espn = dict(zip(id_map["MLBID"].dropna(), id_map["ESPNID"].dropna()))
    espn_to_mlbam = dict(zip(id_map["ESPNID"].dropna(), id_map["MLBID"].dropna()))
    fg_to_mlbam = dict(zip(id_map["IDFANGRAPHS"].dropna(), id_map["MLBID"].dropna()))
    return id_map, mlbam_to_espn, espn_to_mlbam, fg_to_mlbam


def resolve_player(id_map_df, espn_id=None, mlbam_id=None, fg_id=None):
    """Given any one ID, return all three plus player name."""
    result = {"espn_id": espn_id, "mlbam_id": mlbam_id, "fg_id": fg_id, "name": None}

    if mlbam_id is not None:
        match = id_map_df[id_map_df["MLBID"] == mlbam_id]
    elif espn_id is not None:
        match = id_map_df[id_map_df["ESPNID"] == espn_id]
    elif fg_id is not None:
        match = id_map_df[id_map_df["IDFANGRAPHS"] == fg_id]
    else:
        return result

    if len(match) > 0:
        row = match.iloc[0]
        result["espn_id"] = row.get("ESPNID")
        result["mlbam_id"] = row.get("MLBID")
        result["fg_id"] = row.get("IDFANGRAPHS")
        result["name"] = row.get("PLAYERNAME")

    return result


def merge_projections_to_roster(roster_players, ros_hitters, ros_pitchers, id_map_df):
    """
    Join RoS projection data to ESPN roster players via MLBAM ID bridge.
    Returns enriched roster with projection stats and WERTH.
    """
    # Build lookup: espn_id -> projection row
    # First, make sure projections have espn_id via ID map
    if "espn_id" not in ros_hitters.columns and "mlbam_id" in ros_hitters.columns:
        ros_hitters = join_ids(ros_hitters, id_map_df)
    if "espn_id" not in ros_pitchers.columns and "mlbam_id" in ros_pitchers.columns:
        ros_pitchers = join_ids(ros_pitchers, id_map_df)

    hit_lookup = {}
    if "espn_id" in ros_hitters.columns:
        for _, row in ros_hitters.dropna(subset=["espn_id"]).iterrows():
            hit_lookup[int(row["espn_id"])] = row

    pit_lookup = {}
    if "espn_id" in ros_pitchers.columns:
        for _, row in ros_pitchers.dropna(subset=["espn_id"]).iterrows():
            pit_lookup[int(row["espn_id"])] = row

    enriched = []
    unmatched = 0
    for p in roster_players:
        eid = p.get("espn_id")
        if eid is None:
            unmatched += 1
            enriched.append(p)
            continue

        proj = hit_lookup.get(int(eid))
        if proj is None:
            proj = pit_lookup.get(int(eid))
        if proj is not None:
            p["mlbam_id"] = proj.get("mlbam_id")
            p["ros_werth"] = _safe_float(proj.get("pos_adj_werth", proj.get("total_werth")))
            p["total_werth"] = _safe_float(proj.get("total_werth"))

            # Per-category z-scores
            z_scores = {}
            cats = HITTING_CATS if int(eid) in hit_lookup else PITCHING_CATS
            for cat in cats:
                z = proj.get(f"z_{cat}")
                if pd.notna(z):
                    z_scores[cat] = round(float(z), 2)
            p["z_scores"] = z_scores
        else:
            unmatched += 1

        enriched.append(p)

    if unmatched > 0:
        log.warning(f"{unmatched} roster players had no projection match")

    return enriched


# ---- Category State ----

def compute_category_state(our_matchup):
    """
    Parse matchup data into category-by-category state.
    Returns category_state dict and category_triage classification.
    """
    if not our_matchup or not our_matchup.get("categories"):
        return {}, {}

    # Determine which side we are
    if our_matchup["home_team_id"] == MY_TEAM_ID:
        our_key, opp_key = "home_value", "away_value"
    else:
        our_key, opp_key = "away_value", "home_value"

    category_state = {}
    for cat_name, cat_data in our_matchup["categories"].items():
        our_val = cat_data.get(our_key, 0) or 0
        opp_val = cat_data.get(opp_key, 0) or 0

        # For lower-is-better stats (ERA, WHIP), lower = winning
        if cat_name in LOWER_IS_BETTER:
            margin = opp_val - our_val  # positive = we're better
            if our_val < opp_val:
                status = "winning"
            elif our_val > opp_val:
                status = "losing"
            else:
                status = "tied"
        else:
            margin = our_val - opp_val
            if our_val > opp_val:
                status = "winning"
            elif our_val < opp_val:
                status = "losing"
            else:
                status = "tied"

        category_state[cat_name] = {
            "you": round(our_val, 3) if isinstance(our_val, float) else our_val,
            "opp": round(opp_val, 3) if isinstance(opp_val, float) else opp_val,
            "status": status,
            "margin": round(margin, 3) if isinstance(margin, float) else margin,
        }

    # Triage categories
    triage = classify_categories(category_state)
    return category_state, triage


def classify_categories(category_state):
    """
    Classify each category into triage buckets.
    Thresholds are rough heuristics — refine over first 2 weeks.
    """
    triage = {
        "winning_comfortably": [],
        "winning_narrow": [],
        "too_close_to_call": [],
        "losing_flippable": [],
        "losing_unrecoverable": [],
    }

    # Per-category thresholds (absolute margin for "comfortable")
    comfort_thresholds = {
        "R": 8, "HR": 4, "TB": 20, "RBI": 8, "SBN": 4,
        "OBP": 0.015, "K": 15, "QS": 3, "ERA": 0.50,
        "WHIP": 0.10, "KBB": 0.5, "SVHD": 3,
    }
    narrow_thresholds = {
        "R": 4, "HR": 2, "TB": 10, "RBI": 4, "SBN": 2,
        "OBP": 0.008, "K": 8, "QS": 1, "ERA": 0.20,
        "WHIP": 0.05, "KBB": 0.2, "SVHD": 1,
    }

    for cat, state in category_state.items():
        margin = abs(state["margin"])
        status = state["status"]
        comfort = comfort_thresholds.get(cat, 5)
        narrow = narrow_thresholds.get(cat, 2)

        if status == "winning" or status == "tied":
            if margin >= comfort:
                triage["winning_comfortably"].append(cat)
            elif margin >= narrow:
                triage["winning_narrow"].append(cat)
            else:
                triage["too_close_to_call"].append(cat)
        else:  # losing
            if margin <= narrow:
                triage["too_close_to_call"].append(cat)
            elif margin <= comfort:
                triage["losing_flippable"].append(cat)
            else:
                triage["losing_unrecoverable"].append(cat)

    return triage


# ---- Drop Candidates ----

def identify_drop_candidates(my_roster, n=3):
    """Bottom N rostered players by RoS WERTH, excluding IL players."""
    candidates = [
        p for p in my_roster
        if p.get("injury_status") != "INJURY_RESERVE"
        and p.get("lineup_slot") not in ("IL",)
        and p.get("ros_werth") is not None
    ]
    candidates.sort(key=lambda p: p.get("ros_werth", 0))
    return candidates[:n]


# ---- Regression Flags ----

def compute_regression_flags(player, leaderboard_row):
    """
    Flag potential regression candidates based on FanGraphs leaderboard stats.
    Returns list of warning strings.
    """
    flags = []
    if leaderboard_row is None:
        return flags

    # Batter regression signals
    babip = leaderboard_row.get("BABIP")
    if babip is not None:
        if babip < 0.250:
            flags.append(f"BABIP .{int(babip*1000):03d} (due for positive regression)")
        elif babip > 0.350:
            flags.append(f"BABIP .{int(babip*1000):03d} (due for negative regression)")

    hr_fb = leaderboard_row.get("HR/FB") or leaderboard_row.get("HR/FB%")
    if hr_fb is not None:
        if isinstance(hr_fb, str):
            hr_fb = float(hr_fb.replace("%", "")) / 100
        if hr_fb > 0.22:
            flags.append(f"HR/FB {hr_fb:.1%} (unsustainable)")
        elif hr_fb < 0.05:
            flags.append(f"HR/FB {hr_fb:.1%} (due for positive regression)")

    # Pitcher regression signals
    lob_pct = leaderboard_row.get("LOB%")
    if lob_pct is not None:
        if isinstance(lob_pct, str):
            lob_pct = float(lob_pct.replace("%", "")) / 100
        if lob_pct > 0.80:
            flags.append(f"LOB% {lob_pct:.1%} (ERA likely to rise)")
        elif lob_pct < 0.65:
            flags.append(f"LOB% {lob_pct:.1%} (ERA likely to improve)")

    k_pct = leaderboard_row.get("K%")
    if k_pct is not None:
        if isinstance(k_pct, str):
            k_pct = float(k_pct.replace("%", "")) / 100
        # Can't compare to career without historical data, but flag extremes
        if k_pct > 0.35:
            flags.append(f"K% {k_pct:.1%} (elite, monitor for regression)")

    return flags


# ---- Opponent Tendencies ----

def load_opponent_tendencies(opponent_team_name):
    """Load historical tendency text for a specific opponent."""
    report_path = ANALYSIS_DIR / "league_history_report.md"
    if not report_path.exists():
        return f"No historical data available for {opponent_team_name}."

    with open(report_path) as f:
        content = f.read()

    # Extract relevant sections mentioning the opponent
    lines = content.split("\n")
    relevant = []
    for i, line in enumerate(lines):
        if opponent_team_name.lower() in line.lower():
            # Grab surrounding context
            start = max(0, i - 2)
            end = min(len(lines), i + 5)
            relevant.extend(lines[start:end])

    if relevant:
        return "\n".join(relevant)
    return f"No specific historical tendencies found for {opponent_team_name}."


# ---- Briefing Book Assembly ----

def build_briefing_book(
    my_roster,
    opponent_roster,
    our_matchup,
    standings,
    free_agents,
    probable_pitchers_today,
    two_start_pitchers,
    games_per_team,
    transactions_today,
    ros_hitters,
    ros_pitchers,
    leaderboard_bat,
    leaderboard_pit,
    scoring_period_id,
    matchup_meta=None,
):
    """
    Assemble the full briefing book JSON from all data sources.
    This is the single input that feeds the analyst agents.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Category state
    category_state, category_triage = compute_category_state(our_matchup)

    # Identify opponent
    opponent_name = ""
    opponent_team_id = None
    if our_matchup:
        if our_matchup["home_team_id"] == MY_TEAM_ID:
            opponent_name = our_matchup.get("away_team_name", "")
            opponent_team_id = our_matchup.get("away_team_id")
        else:
            opponent_name = our_matchup.get("home_team_name", "")
            opponent_team_id = our_matchup.get("home_team_id")

    # Enrich rosters with projections and WERTH
    id_map_df = load_id_map()
    my_roster_enriched = merge_projections_to_roster(
        my_roster, ros_hitters, ros_pitchers, id_map_df
    )
    opp_roster_enriched = merge_projections_to_roster(
        opponent_roster, ros_hitters, ros_pitchers, id_map_df
    ) if opponent_roster else []

    # Add regression flags from leaderboard
    _add_regression_flags(my_roster_enriched, leaderboard_bat, leaderboard_pit, id_map_df)

    # Add games remaining this week per player
    _add_games_remaining(my_roster_enriched, games_per_team)

    # Drop candidates
    drop_candidates = identify_drop_candidates(my_roster_enriched)

    # Free agents with WERTH
    fa_enriched = merge_projections_to_roster(
        free_agents[:50], ros_hitters, ros_pitchers, id_map_df
    )
    # Sort FAs by WERTH
    fa_enriched.sort(key=lambda p: p.get("ros_werth") or 0, reverse=True)

    # Streamable pitchers today (FAs who are probable starters)
    streamable = _find_streamable_pitchers(
        free_agents, probable_pitchers_today, ros_pitchers,
        id_map_df, two_start_pitchers, category_state
    )

    # Two-start pitchers available on waivers
    two_start_available = _find_two_start_fas(
        free_agents, two_start_pitchers, ros_pitchers, id_map_df
    )

    # Standings context
    standings_context = _format_standings_context(standings)

    # Opponent tendencies
    opponent_tendencies = load_opponent_tendencies(opponent_name)

    # Matchup metadata from schedule JSON + ESPN API
    if matchup_meta is None:
        matchup_meta = {}
    matchup_week = matchup_meta.get("matchup_period_id") or (scoring_period_id // 7 + 1 if scoring_period_id else None)

    # Triage summary counts (so agents don't have to recount)
    triage_counts = {bucket: len(cats) for bucket, cats in category_triage.items()} if category_triage else {}

    # Assemble
    briefing = {
        "date": today,
        "matchup_week": matchup_week,
        "scoring_period_id": scoring_period_id,
        "matchup_day": matchup_meta.get("day_of_matchup"),
        "matchup_length_days": matchup_meta.get("matchup_length_days"),
        "days_remaining": matchup_meta.get("days_remaining"),
        "matchup_start": matchup_meta.get("matchup_start"),
        "matchup_end": matchup_meta.get("matchup_end"),
        "moves_max": matchup_meta.get("moves_max"),
        "opponent": opponent_name,
        "opponent_team_id": opponent_team_id,

        "category_state": category_state,
        "category_triage": category_triage,
        "triage_counts": triage_counts,

        "my_roster": _serialize_roster(my_roster_enriched),
        "drop_candidates": _serialize_roster(drop_candidates),
        "opponent_roster": _serialize_roster(opp_roster_enriched),

        "top_free_agents": _serialize_roster(fa_enriched[:20]),  # name collisions added below
        "streamable_pitchers_today": streamable,
        "two_start_pitchers_available": two_start_available,

        "transactions_today": transactions_today,
        "standings": standings_context,
        "opponent_tendencies": opponent_tendencies,
        "league_context": _build_league_context(standings, matchup_week),

        "data_freshness": {
            "espn_rosters": today,
            "ros_projections": today,
            "probable_pitchers": today,
        },
    }

    # Add name collision warnings to free agents
    add_name_collision_warnings(briefing["my_roster"], briefing["top_free_agents"])

    return briefing


def _add_regression_flags(roster, leaderboard_bat, leaderboard_pit, id_map_df):
    """Add regression flags to roster players from leaderboard data."""
    if leaderboard_bat is None or len(leaderboard_bat) == 0:
        return

    # Build leaderboard lookups by mlbam_id
    bat_lookup = {}
    if "mlbam_id" in leaderboard_bat.columns:
        for _, row in leaderboard_bat.iterrows():
            mid = row.get("mlbam_id")
            if pd.notna(mid):
                bat_lookup[int(mid)] = row

    pit_lookup = {}
    if leaderboard_pit is not None and "mlbam_id" in leaderboard_pit.columns:
        for _, row in leaderboard_pit.iterrows():
            mid = row.get("mlbam_id")
            if pd.notna(mid):
                pit_lookup[int(mid)] = row

    for p in roster:
        mid = p.get("mlbam_id")
        if mid is None:
            # Try to resolve via ESPN ID
            eid = p.get("espn_id")
            if eid is not None:
                resolved = resolve_player(id_map_df, espn_id=eid)
                mid = resolved.get("mlbam_id")
                if mid is not None:
                    p["mlbam_id"] = mid

        if mid is not None:
            lb_row = bat_lookup.get(int(mid))
            if lb_row is None:
                lb_row = pit_lookup.get(int(mid))
            if lb_row is not None:
                p["regression_flags"] = compute_regression_flags(p, lb_row)
            else:
                p["regression_flags"] = []
        else:
            p["regression_flags"] = []


def _add_games_remaining(roster, games_per_team):
    """Add games remaining this week for each roster player."""
    if not games_per_team:
        return
    # ESPN pro_team is an int (team ID), we need to map to abbrev
    # For now, store the count if we can match
    for p in roster:
        team = p.get("pro_team", "")
        if isinstance(team, str) and team in games_per_team:
            p["games_remaining_this_week"] = games_per_team[team]
        else:
            p["games_remaining_this_week"] = None


def _find_streamable_pitchers(free_agents, probable_pitchers, ros_pitchers, id_map_df,
                               two_starters, category_state):
    """Find free agent pitchers who are probable starters today."""
    # Build set of probable pitcher MLBAM IDs
    pp_ids = {pp["mlbam_id"] for pp in probable_pitchers if pp.get("mlbam_id")}
    pp_info = {pp["mlbam_id"]: pp for pp in probable_pitchers if pp.get("mlbam_id")}

    # Build FA ESPN ID set
    fa_ids = {p["espn_id"] for p in free_agents if p.get("espn_id")}

    # Map ESPN IDs to MLBAM IDs
    espn_to_mlbam = {}
    mlbam_to_espn = {}
    for _, row in id_map_df.iterrows():
        eid = row.get("ESPNID")
        mid = row.get("MLBID")
        if pd.notna(eid) and pd.notna(mid):
            espn_to_mlbam[int(eid)] = int(mid)
            mlbam_to_espn[int(mid)] = int(eid)

    # Two-start lookup
    two_start_ids = {ts["mlbam_id"] for ts in two_starters}

    # Projection lookup
    pit_lookup = {}
    if "espn_id" in ros_pitchers.columns:
        for _, row in ros_pitchers.dropna(subset=["espn_id"]).iterrows():
            pit_lookup[int(row["espn_id"])] = row

    streamable = []
    for fa in free_agents:
        eid = fa.get("espn_id")
        if eid is None:
            continue
        mid = espn_to_mlbam.get(int(eid))
        if mid is None or mid not in pp_ids:
            continue

        pp = pp_info[mid]
        proj = pit_lookup.get(int(eid), {})

        entry = {
            "name": fa.get("name", pp.get("name", "")),
            "espn_id": eid,
            "mlbam_id": mid,
            "opponent": pp.get("opponent", ""),
            "home_away": pp.get("home_away", ""),
            "game_time": pp.get("game_time", ""),
            "two_start_this_week": mid in two_start_ids,
            "proj_k": _safe_float(proj.get("K")),
            "proj_era": _safe_float(proj.get("ERA")),
            "proj_whip": _safe_float(proj.get("WHIP")),
            "proj_kbb": _safe_float(proj.get("KBB")),
            "ros_werth": _safe_float(proj.get("pos_adj_werth", proj.get("total_werth"))),
        }

        # ERA risk assessment
        era_state = category_state.get("ERA", {})
        if era_state and entry["proj_era"]:
            cushion = era_state.get("margin", 0)
            if cushion < 0.20 and entry["proj_era"] > 4.00:
                entry["era_risk"] = f"ERA cushion {cushion:.2f} — this stream risks flipping ERA against you"
            elif cushion > 0.50:
                entry["era_risk"] = "Comfortable ERA cushion — low risk"
            else:
                entry["era_risk"] = f"ERA cushion {cushion:.2f} — moderate risk"

        streamable.append(entry)

    streamable.sort(key=lambda x: x.get("ros_werth") or 0, reverse=True)
    return streamable


def _find_two_start_fas(free_agents, two_starters, ros_pitchers, id_map_df):
    """Find free agent pitchers with two starts this week."""
    two_start_ids = {ts["mlbam_id"]: ts for ts in two_starters}

    espn_to_mlbam = {}
    for _, row in id_map_df.iterrows():
        eid = row.get("ESPNID")
        mid = row.get("MLBID")
        if pd.notna(eid) and pd.notna(mid):
            espn_to_mlbam[int(eid)] = int(mid)

    result = []
    for fa in free_agents:
        eid = fa.get("espn_id")
        if eid is None:
            continue
        mid = espn_to_mlbam.get(int(eid))
        if mid is None or mid not in two_start_ids:
            continue

        ts = two_start_ids[mid]
        matchup_strs = [f"vs {m['opponent']}" for m in ts.get("matchups", [])]
        result.append({
            "name": fa.get("name", ts.get("name", "")),
            "espn_id": eid,
            "mlbam_id": mid,
            "start_count": ts.get("start_count", 2),
            "matchups": matchup_strs,
            "positions": fa.get("positions", []),
        })

    return result


def _format_standings_context(standings):
    """Format standings into a compact dict."""
    if not standings:
        return {}
    return {
        "teams": [
            {
                "team_name": s["team_name"],
                "team_id": s["team_id"],
                "wins": s["wins"],
                "losses": s["losses"],
                "ties": s.get("ties", 0),
            }
            for s in standings
        ]
    }


def _build_league_context(standings, matchup_week):
    """Build a text summary of league context."""
    if not standings:
        return ""

    my_team = next((s for s in standings if s["team_id"] == MY_TEAM_ID), None)
    if not my_team:
        return ""

    rank = next((i + 1 for i, s in enumerate(standings) if s["team_id"] == MY_TEAM_ID), "?")
    record = f"{my_team['wins']}-{my_team['losses']}"
    if my_team.get("ties", 0) > 0:
        record += f"-{my_team['ties']}"

    week_str = f"Week {matchup_week} of 22" if matchup_week else "Season in progress"
    return f"{week_str}. You are {_ordinal(rank)} place ({record}). Top 4 make playoffs."


def _serialize_roster(players):
    """Convert roster players to JSON-safe dicts."""
    result = []
    for p in players:
        team_abbrev = p.get("pro_team_abbrev", "")
        entry = {
            "name": p.get("name", ""),
            "team": team_abbrev,
            "espn_id": p.get("espn_id"),
            "positions": p.get("positions", []),
            "status": p.get("injury_status", "ACTIVE"),
            "lineup_slot": p.get("lineup_slot", ""),
        }
        if p.get("ros_werth") is not None:
            entry["ros_werth"] = round(p["ros_werth"], 2)
        if p.get("total_werth") is not None:
            entry["total_werth"] = round(p["total_werth"], 2)
        if p.get("z_scores"):
            entry["z_scores"] = p["z_scores"]
        if p.get("regression_flags"):
            entry["regression_flags"] = p["regression_flags"]
        if p.get("games_remaining_this_week") is not None:
            entry["games_remaining_this_week"] = p["games_remaining_this_week"]
        if p.get("ownership_pct"):
            entry["ownership_pct"] = p["ownership_pct"]
        if p.get("mlbam_id") is not None:
            entry["mlbam_id"] = _safe_int(p["mlbam_id"])
        result.append(entry)

    return result


def add_name_collision_warnings(my_roster_serialized, fa_serialized):
    """
    Flag free agents who share a last name with a rostered player.
    Adds 'name_collision' field to the FA entry for disambiguation.
    """
    rostered_last_names = {}
    for p in my_roster_serialized:
        name = p.get("name", "")
        parts = name.split()
        if parts:
            last = parts[-1]
            rostered_last_names.setdefault(last, []).append(p)

    for fa in fa_serialized:
        name = fa.get("name", "")
        parts = name.split()
        if parts:
            last = parts[-1]
            if last in rostered_last_names:
                rostered_matches = rostered_last_names[last]
                # Only flag if it's a different player
                for rm in rostered_matches:
                    if rm.get("espn_id") != fa.get("espn_id"):
                        fa["name_collision"] = (
                            f"Note: different player from your rostered "
                            f"{rm['name']} ({rm.get('team', '')})"
                        )


def _safe_float(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return round(float(val), 3)
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _ordinal(n):
    if isinstance(n, str):
        return n
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = suffixes.get(n % 10, "th")
    return f"{n}{suffix}"
