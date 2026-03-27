#!/usr/bin/env python3
"""
Daily Newsletter Pipeline Orchestrator.
Run: python3 in_season/daily_digest/run_newsletter.py

Fetches live data, builds briefing book, generates newsletter via Claude,
and saves to output file.
"""

import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Ensure we can import from this directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from config import validate_config, OUTPUT_DIR, MY_TEAM_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(OUTPUT_DIR / "pipeline.log"),
    ],
)
log = logging.getLogger("newsletter")


def main():
    """Run the full daily newsletter pipeline."""
    log.info("=" * 60)
    log.info("DAILY NEWSLETTER PIPELINE — Starting")
    log.info(f"Date: {datetime.now().isoformat()}")
    log.info("=" * 60)

    # Validate config
    issues = validate_config()
    data_warnings = []
    if issues:
        log.warning(f"Config issues: {issues}")
        for issue in issues:
            if "Claude Code" in issue:
                data_warnings.append(f"⚠ {issue} — will use fallback newsletter")
            else:
                data_warnings.append(f"⚠ {issue}")

    # ---- Step 1: Fetch ESPN data ----
    log.info("Step 1: Fetching ESPN data...")
    all_rosters = {}
    my_roster = []
    opponent_roster = []
    our_matchup = None
    standings = []
    free_agents = []
    scoring_period_id = 1

    matchup_meta = {}
    try:
        from fetch_espn import (
            fetch_all_rosters, fetch_matchup_scores,
            fetch_standings, fetch_free_agents,
            fetch_current_scoring_period, fetch_current_matchup_period,
        )

        # Get matchup metadata (period, day count, move limits)
        matchup_meta = fetch_current_matchup_period()
        scoring_period_id = matchup_meta["scoring_period_id"]
        matchup_period_id = matchup_meta["matchup_period_id"]
        log.info(f"  Scoring period: {scoring_period_id}, Matchup period: {matchup_period_id}")
        log.info(f"  Day {matchup_meta['day_of_matchup']}/{matchup_meta['matchup_length_days']}, Moves max: {matchup_meta['moves_max']}")

        all_rosters = fetch_all_rosters()
        my_roster_data = all_rosters.get(MY_TEAM_ID, {})
        my_roster = my_roster_data.get("players", [])
        log.info(f"  My roster: {len(my_roster)} players")

        our_matchup, all_matchups = fetch_matchup_scores(scoring_period_id, matchup_period_id)
        if our_matchup:
            opp_id = (our_matchup["away_team_id"]
                      if our_matchup["home_team_id"] == MY_TEAM_ID
                      else our_matchup["home_team_id"])
            opp_data = all_rosters.get(opp_id, {})
            opponent_roster = opp_data.get("players", [])
            opp_name = our_matchup.get("away_team_name") if our_matchup["home_team_id"] == MY_TEAM_ID else our_matchup.get("home_team_name")
            log.info(f"  Matchup found: vs {opp_name} (team {opp_id})")
        else:
            log.warning("  No current matchup found")
            data_warnings.append("⚠ No current matchup data available")

        standings = fetch_standings()
        log.info(f"  Standings: {len(standings)} teams")

        free_agents = fetch_free_agents(count=250)
        log.info(f"  Free agents: {len(free_agents)}")

    except PermissionError as e:
        log.error(f"ESPN auth error: {e}")
        data_warnings.append(f"🔴 ESPN API auth failed: {e}")
    except Exception as e:
        log.error(f"ESPN fetch error: {e}", exc_info=True)
        data_warnings.append(f"🔴 ESPN API error: {e}")

    # ---- Step 2: Fetch FanGraphs data ----
    log.info("Step 2: Fetching FanGraphs projections...")
    ros_bat_raw = None
    ros_pit_raw = None
    leaderboard_bat = None
    leaderboard_pit = None

    try:
        from fetch_fangraphs import fetch_ros_projections, fetch_leaderboard

        ros_bat_raw = fetch_ros_projections("bat")
        log.info(f"  RoS batters: {len(ros_bat_raw)} players")

        ros_pit_raw = fetch_ros_projections("pit")
        log.info(f"  RoS pitchers: {len(ros_pit_raw)} players")

        leaderboard_bat = fetch_leaderboard("bat")
        log.info(f"  Leaderboard batters: {len(leaderboard_bat)} players")

        leaderboard_pit = fetch_leaderboard("pit")
        log.info(f"  Leaderboard pitchers: {len(leaderboard_pit)} players")

    except Exception as e:
        log.error(f"FanGraphs fetch error: {e}", exc_info=True)
        data_warnings.append(f"⚠ FanGraphs data unavailable: {e}")

    # ---- Step 3: Fetch MLB Stats API data ----
    log.info("Step 3: Fetching MLB Stats API data...")
    probable_pitchers = []
    two_starters = []
    games_per_team = {}
    transactions = []

    try:
        from fetch_mlb import fetch_probable_pitchers, fetch_weekly_schedule, fetch_transactions

        probable_pitchers = fetch_probable_pitchers()
        log.info(f"  Probable pitchers today: {len(probable_pitchers)}")

        two_starters, games_per_team = fetch_weekly_schedule()
        log.info(f"  Two-start pitchers this week: {len(two_starters)}")
        log.info(f"  Teams with games: {len(games_per_team)}")

        transactions = fetch_transactions()
        log.info(f"  Transactions today: {len(transactions)}")

    except Exception as e:
        log.error(f"MLB API error: {e}", exc_info=True)
        data_warnings.append(f"⚠ MLB Stats API error: {e}")

    # ---- Step 3b: Fetch Savant xStats ----
    log.info("Step 3b: Fetching Baseball Savant data...")
    savant_bat = pd.DataFrame()
    savant_pit = pd.DataFrame()
    savant_signals = {}

    try:
        from fetch_savant import fetch_savant_expected_stats, compute_regression_signals

        savant_bat = fetch_savant_expected_stats("batter")
        log.info(f"  Savant batters: {len(savant_bat)} players")

        savant_pit = fetch_savant_expected_stats("pitcher")
        log.info(f"  Savant pitchers: {len(savant_pit)} players")

        savant_signals = compute_regression_signals(savant_bat, savant_pit)
        log.info(f"  Savant regression signals: {len(savant_signals)} players flagged")

    except Exception as e:
        log.warning(f"Savant fetch error: {e}")
        data_warnings.append(f"⚠ Savant data unavailable: {e}")

    # ---- Step 3c: Fetch weather data ----
    log.info("Step 3c: Fetching weather data...")
    game_weather = {}

    try:
        from fetch_weather import fetch_game_weather

        # Build game list from probable pitchers
        games_for_weather = []
        seen_games = set()
        for pp in probable_pitchers:
            game_key = pp.get("game_pk")
            if game_key and game_key not in seen_games:
                seen_games.add(game_key)
                home_team = pp["team"] if pp.get("home_away") == "home" else pp.get("opponent", "")
                away_team = pp["team"] if pp.get("home_away") == "away" else pp.get("opponent", "")
                games_for_weather.append({
                    "home_team": home_team,
                    "away_team": away_team,
                    "game_time": pp.get("game_time"),
                })

        if games_for_weather:
            game_weather = fetch_game_weather(games_for_weather)
            log.info(f"  Weather fetched for {len(game_weather)} games")

    except Exception as e:
        log.warning(f"Weather fetch error: {e}")

    # ---- Step 3d: Fetch park factors, opponent quality, Vegas, closer info ----
    log.info("Step 3d: Fetching park factors, team quality, Vegas lines, closer roles...")
    team_quality = {}
    vegas_lines = {}
    closer_roles = {}
    platoon_splits = {}

    try:
        from fetch_extras import (
            enrich_with_park_factors, fetch_team_offense_quality,
            enrich_streamers_with_opponent_quality, fetch_vegas_lines,
            fetch_closer_info, load_platoon_splits,
        )

        team_quality = fetch_team_offense_quality()
        log.info(f"  Team wRC+: {len(team_quality)} teams")

        vegas_lines = fetch_vegas_lines()
        log.info(f"  Vegas lines: {len(vegas_lines)} games")

        closer_roles = fetch_closer_info()
        log.info(f"  Closer roles: {len(closer_roles)} teams")

        platoon_splits = load_platoon_splits()
        log.info(f"  Platoon splits: {len(platoon_splits)} batters")

    except Exception as e:
        log.warning(f"Extra data fetch error: {e}")

    # ---- Step 4: Compute RoS WERTH ----
    log.info("Step 4: Computing RoS WERTH...")
    ros_hitters = pd.DataFrame()
    ros_pitchers = pd.DataFrame()

    try:
        from ros_werth import compute_ros_werth
        from config import load_id_map, join_ids

        if ros_bat_raw is not None and len(ros_bat_raw) > 0:
            id_map_df = load_id_map()

            # Join ESPN IDs to projections
            if "espn_id" not in ros_bat_raw.columns and "mlbam_id" in ros_bat_raw.columns:
                ros_bat_raw = join_ids(ros_bat_raw, id_map_df)
            if ros_pit_raw is not None and "espn_id" not in ros_pit_raw.columns and "mlbam_id" in ros_pit_raw.columns:
                ros_pit_raw = join_ids(ros_pit_raw, id_map_df)

            # Build rostered/FA ID sets
            rostered_ids = set()
            for team_data in all_rosters.values():
                for p in team_data.get("players", []):
                    eid = p.get("espn_id")
                    if eid is not None:
                        rostered_ids.add(int(eid))

            fa_ids = {int(p["espn_id"]) for p in free_agents if p.get("espn_id")}

            pit_df = ros_pit_raw if ros_pit_raw is not None and len(ros_pit_raw) > 0 else pd.DataFrame()
            ros_hitters, ros_pitchers = compute_ros_werth(
                ros_bat_raw, pit_df,
                rostered_espn_ids=rostered_ids,
                fa_espn_ids=fa_ids,
            )
            log.info(f"  WERTH computed: {len(ros_hitters)} hitters, {len(ros_pitchers)} pitchers")
        else:
            log.warning("  No RoS projections available — WERTH not computed")
            data_warnings.append("⚠ No RoS projections — player valuations unavailable")

    except Exception as e:
        log.error(f"WERTH computation error: {e}", exc_info=True)
        data_warnings.append(f"⚠ WERTH computation failed: {e}")

    # ---- Step 5: Build briefing book ----
    log.info("Step 5: Building briefing book...")
    try:
        from preprocess import build_briefing_book

        briefing_book = build_briefing_book(
            my_roster=my_roster,
            opponent_roster=opponent_roster,
            our_matchup=our_matchup,
            standings=standings,
            free_agents=free_agents,
            probable_pitchers_today=probable_pitchers,
            two_start_pitchers=two_starters,
            games_per_team=games_per_team,
            transactions_today=transactions,
            ros_hitters=ros_hitters,
            ros_pitchers=ros_pitchers,
            leaderboard_bat=leaderboard_bat if leaderboard_bat is not None else pd.DataFrame(),
            leaderboard_pit=leaderboard_pit if leaderboard_pit is not None else pd.DataFrame(),
            scoring_period_id=scoring_period_id,
            matchup_meta=matchup_meta,
        )

        # Enrich streamable pitchers with park factors and opponent quality
        try:
            from fetch_extras import enrich_with_park_factors, enrich_streamers_with_opponent_quality
            if briefing_book.get("streamable_pitchers_today"):
                enrich_with_park_factors(briefing_book["streamable_pitchers_today"])
                if team_quality:
                    enrich_streamers_with_opponent_quality(
                        briefing_book["streamable_pitchers_today"], team_quality
                    )
        except Exception:
            pass

        # Add Savant regression signals to briefing book
        if savant_signals:
            briefing_book["savant_regression_signals"] = {
                str(k): v for k, v in savant_signals.items()
            }

        # Add weather data to briefing book
        if game_weather:
            briefing_book["game_weather"] = game_weather

        # Add team offensive quality
        if team_quality:
            briefing_book["team_offensive_quality"] = team_quality

        # Add Vegas lines
        if vegas_lines:
            briefing_book["vegas_lines"] = vegas_lines

        # Add closer/RP role info
        if closer_roles:
            briefing_book["closer_roles"] = closer_roles

        # Add platoon split flags for rostered players
        if platoon_splits:
            extreme_platoon = {
                str(k): v for k, v in platoon_splits.items()
                if v.get("extreme_platoon")
            }
            if extreme_platoon:
                briefing_book["extreme_platoon_players"] = extreme_platoon

        # Add data warnings to briefing book
        if data_warnings:
            briefing_book["data_warnings"] = data_warnings

        log.info(f"  Briefing book built: {len(json.dumps(briefing_book, default=str))} chars")

    except Exception as e:
        log.error(f"Briefing book error: {e}", exc_info=True)
        briefing_book = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "error": str(e),
            "data_warnings": data_warnings + [f"🔴 Briefing book assembly failed: {e}"],
        }

    # ---- Step 6: Generate newsletter ----
    log.info("Step 6: Generating newsletter via Claude...")
    try:
        from agents import generate_newsletter
        newsletter = generate_newsletter(briefing_book)
    except Exception as e:
        log.error(f"Newsletter generation error: {e}", exc_info=True)
        newsletter = f"Newsletter generation failed: {e}\n\nRaw briefing book saved to output directory."

    # ---- Step 6b: Log calibration predictions ----
    try:
        from calibration import log_predictions
        log_predictions(briefing_book, newsletter)
    except Exception as e:
        log.warning(f"Calibration logging failed (non-fatal): {e}")

    # ---- Step 7: Save output ----
    log.info("Step 7: Saving output...")
    try:
        from save_output import save_newsletter
        output_path = save_newsletter(newsletter, briefing_book)
        log.info(f"  Newsletter saved to: {output_path}")
    except Exception as e:
        log.error(f"Save error: {e}", exc_info=True)
        # Emergency fallback: write directly
        emergency_path = OUTPUT_DIR / f"newsletter_{datetime.now().strftime('%Y-%m-%d')}_emergency.txt"
        emergency_path.write_text(newsletter, encoding="utf-8")
        output_path = emergency_path

    log.info("=" * 60)
    log.info(f"PIPELINE COMPLETE — Newsletter: {output_path}")
    if data_warnings:
        log.info(f"Data warnings ({len(data_warnings)}):")
        for w in data_warnings:
            log.info(f"  {w}")
    log.info("=" * 60)

    return output_path


if __name__ == "__main__":
    path = main()
    print(f"\n✅ Newsletter saved to: {path}")
