#!/usr/bin/env python3
"""
ESPN Fantasy Baseball Data Extraction Script
League: Magic Conch 2025 (ID: 84209353)
Extracts league config, rosters, drafts, matchups, standings, transactions, and free agents.
"""

import json
import os
import sys
import time
from datetime import datetime

import requests
from espn_api.baseball import League

# =============================================================================
# Configuration
# =============================================================================
LEAGUE_ID = 84209353
SWID = "{5E014CD6-05E5-439D-A8F6-7FDBF6F6EC9A}"
ESPN_S2 = "AEBGZT0m%2FuU36nTWi8dRJkIAQ4X9z8f8cok%2F%2Ft2gHx4453nM%2Fd9ZP8X%2Fbh4uwcHTAJQ35%2FqZXHswr8JcqftTGjjxVEJqJXm%2Fgi0Nel%2BUM%2BiqFRNZxyIP%2BUwvOMKeSF%2FOq7J84nFccRfJjpLcc7KNKBtOitaxDCGVoGxumXYMSWHtW72zhzg1p94Fxmgkd3JXRJPN1ImWsoPEmQgeJgQVv6WuJnInlGAfs6HFVv8XeGanpXxD11Wu5cT%2BNhIL%2FswpsOnJrbkjLaJPFT32Rmz4MCDFWRmEkYeRe7lJ5uzIbvJjcQ%3D%3D"

COOKIES = {"swid": SWID, "espn_s2": ESPN_S2}
HEADERS = {"x-fantasy-filter": ""}

HISTORICAL_YEARS = [2021, 2022, 2023, 2024, 2025]
CURRENT_YEAR = 2026

# ESPN Baseball Stat ID Map (from espn_api/baseball/constant.py)
STATS_MAP = {
    0: "AB", 1: "H", 2: "AVG", 3: "2B", 4: "3B", 5: "HR", 6: "XBH",
    7: "1B", 8: "TB", 9: "SLG", 10: "BB", 11: "IBB", 12: "HBP",
    13: "SF", 14: "SH", 15: "SAC", 16: "PA", 17: "OBP", 18: "OPS",
    19: "RC", 20: "R", 21: "RBI", 23: "SB", 24: "CS", 25: "SBN",
    26: "GDP", 27: "SO", 28: "PS", 29: "PPA", 31: "CYC",
    32: "GP_P", 33: "GS", 34: "OUTS", 35: "TBF", 36: "P",
    37: "HA", 38: "OBA", 39: "BBA", 40: "IBBA", 41: "WHIP",
    42: "HBP_P", 43: "OOBP", 44: "RA", 45: "ER", 46: "HRA",
    47: "ERA", 48: "K", 49: "K9", 50: "WP", 51: "BLK", 52: "PK",
    53: "W", 54: "L", 55: "WPCT", 56: "SVO", 57: "SV", 58: "BLSV",
    59: "SVPCT", 60: "HLD", 62: "CG", 63: "QS", 65: "NH", 66: "PG",
    67: "TC", 68: "PO", 69: "A", 70: "OFA", 71: "FPCT", 72: "E",
    73: "DP", 74: "BGW", 75: "BGL", 76: "PGW", 77: "PGL",
    81: "G", 82: "KBB", 83: "SVHD", 99: "STARTER",
}

# Our league's 12 scoring categories
SCORING_CAT_IDS = [20, 5, 8, 21, 25, 17, 48, 63, 47, 41, 82, 83]

# ESPN position ID map
POS_MAP = {
    1: "SP", 2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS",
    7: "LF", 8: "CF", 9: "RF", 10: "DH", 11: "RP",
}

SLOT_MAP = {
    0: "C", 1: "1B", 2: "2B", 3: "SS", 4: "3B", 5: "OF", 6: "MI",
    7: "CI", 11: "DH", 12: "UTIL", 13: "P", 14: "SP", 15: "RP",
    16: "BE", 17: "IL", 19: "IF",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)))


def api_url(year):
    return f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/flb/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"


def api_get(year, views, params=None):
    """Make an ESPN API request with given views."""
    p = {"view": views}
    if params:
        p.update(params)
    r = requests.get(api_url(year), params=p, cookies=COOKIES)
    r.raise_for_status()
    return r.json()


def save_json(data, *path_parts):
    """Save data as JSON to the data directory."""
    fpath = os.path.join(DATA_DIR, *path_parts)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    with open(fpath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  ✅ Saved {os.path.join(*path_parts)}")


# =============================================================================
# 1. League Configuration
# =============================================================================
def extract_league_config():
    print("\n=== EXTRACTING LEAGUE CONFIG (2026) ===")
    data = api_get(2026, "mSettings")
    settings = data["settings"]
    scoring = settings["scoringSettings"]
    roster = settings["rosterSettings"]
    draft = settings["draftSettings"]

    categories = []
    for item in scoring["scoringItems"]:
        sid = item["statId"]
        categories.append({
            "stat_id": sid,
            "name": STATS_MAP.get(sid, f"UNKNOWN_{sid}"),
            "is_reverse": item.get("isReverseItem", False),
            "is_batting": sid < 32,
        })

    roster_slots = {}
    for slot_id_str, count in roster["lineupSlotCounts"].items():
        if count > 0:
            slot_name = SLOT_MAP.get(int(slot_id_str), f"SLOT_{slot_id_str}")
            roster_slots[slot_name] = count

    draft_date = datetime.fromtimestamp(draft["date"] / 1000)

    config = {
        "league_id": LEAGUE_ID,
        "league_name": settings["name"],
        "year": 2026,
        "scoring_type": "H2H_MOST_CATEGORIES",
        "team_count": 8,
        "reg_season_matchups": settings.get("scheduleSettings", {}).get("matchupPeriodCount", 22),
        "playoff_teams": settings.get("scheduleSettings", {}).get("playoffTeamCount", 4),
        "scoring_categories": categories,
        "roster_slots": roster_slots,
        "draft": {
            "type": draft.get("type", "SNAKE"),
            "date": draft_date.isoformat(),
            "date_display": draft_date.strftime("%A %B %d, %Y at %I:%M %p"),
            "pick_order": draft.get("pickOrder", []),
            "time_per_pick_seconds": draft.get("timePerSelection", 60),
            "keeper_count": draft.get("keeperCount", 3),
            "keeper_order_penalty": draft.get("keeperOrderPenalty"),
        },
        "divisions": settings.get("scheduleSettings", {}).get("divisions", []),
    }

    # Teams
    league = League(league_id=LEAGUE_ID, year=2026, espn_s2=ESPN_S2, swid=SWID)
    teams = []
    for t in league.teams:
        owner = t.owners[0] if t.owners else {}
        teams.append({
            "team_id": t.team_id,
            "team_name": t.team_name,
            "owner_first": owner.get("firstName", ""),
            "owner_last": owner.get("lastName", ""),
            "owner_display": owner.get("displayName", ""),
            "division": t.division_name if hasattr(t, "division_name") else "",
        })
    config["teams"] = teams

    save_json(config, "league_config.json")
    return config


# =============================================================================
# 2. Current Rosters (2026)
# =============================================================================
def extract_rosters_2026():
    print("\n=== EXTRACTING 2026 ROSTERS ===")
    league = League(league_id=LEAGUE_ID, year=2026, espn_s2=ESPN_S2, swid=SWID)

    all_rosters = {}
    for team in league.teams:
        players = []
        for p in team.roster:
            eligible = [POS_MAP.get(pid, f"POS_{pid}") for pid in p.eligibleSlots
                        if pid in POS_MAP]
            player_data = {
                "name": p.name,
                "espn_id": p.playerId,
                "position": p.position,
                "eligible_positions": eligible,
                "pro_team": p.proTeam,
                "acquisition_type": p.acquisitionType if hasattr(p, "acquisitionType") else "",
                "injury_status": p.injuryStatus if hasattr(p, "injuryStatus") else "ACTIVE",
            }

            # Try to get projected stats
            if hasattr(p, "stats") and p.stats:
                player_data["stats"] = {}
                for stat_key, stat_val in p.stats.items():
                    if isinstance(stat_val, dict) and "breakdown" in stat_val:
                        player_data["stats"][str(stat_key)] = stat_val["breakdown"]

            players.append(player_data)

        all_rosters[str(team.team_id)] = {
            "team_id": team.team_id,
            "team_name": team.team_name,
            "players": players,
        }

    save_json(all_rosters, "rosters_2026.json")


# =============================================================================
# 3. Historical Draft Results
# =============================================================================
def extract_draft(year):
    print(f"\n=== EXTRACTING {year} DRAFT ===")
    try:
        data = api_get(year, "mDraftDetail")
    except Exception as e:
        print(f"  ❌ Failed for {year}: {e}")
        return

    draft_detail = data.get("draftDetail", {})
    picks_raw = draft_detail.get("picks", [])

    if not picks_raw:
        print(f"  ⚠️  No draft picks found for {year}")
        save_json({"year": year, "picks": [], "note": "No picks found"}, "drafts", f"draft_{year}.json")
        return

    # Get team names for this year
    try:
        league = League(league_id=LEAGUE_ID, year=year, espn_s2=ESPN_S2, swid=SWID)
        team_map = {t.team_id: t.team_name for t in league.teams}
    except Exception:
        team_map = {}

    # Get player names — need to resolve IDs
    player_ids = [p.get("playerId") for p in picks_raw if p.get("playerId")]

    # Use raw API to get player names
    try:
        player_data = api_get(year, ["mDraftDetail", "mRoster"])
        player_map = {}
        for team in player_data.get("teams", []):
            for entry in team.get("roster", {}).get("entries", []):
                player = entry.get("playerPoolEntry", {}).get("player", {})
                pid = player.get("id")
                if pid:
                    player_map[pid] = {
                        "name": player.get("fullName", f"Unknown ({pid})"),
                        "position": POS_MAP.get(player.get("defaultPositionId", 0), "?"),
                    }
    except Exception:
        player_map = {}

    # If player_map is incomplete, try fetching players directly
    missing_ids = [pid for pid in player_ids if pid not in player_map]
    if missing_ids:
        try:
            # Use players endpoint with filters
            filter_json = json.dumps({
                "players": {
                    "filterIds": {"value": missing_ids[:50]},
                    "limit": 50,
                }
            })
            r = requests.get(
                api_url(year),
                params={"view": "kona_player_info"},
                cookies=COOKIES,
                headers={"x-fantasy-filter": filter_json},
            )
            if r.status_code == 200:
                pdata = r.json()
                for p in pdata.get("players", []):
                    pid = p.get("id")
                    player = p.get("player", p)
                    if pid:
                        player_map[pid] = {
                            "name": player.get("fullName", f"Unknown ({pid})"),
                            "position": POS_MAP.get(player.get("defaultPositionId", 0), "?"),
                        }
        except Exception:
            pass

    picks = []
    for pick in picks_raw:
        pid = pick.get("playerId")
        pinfo = player_map.get(pid, {})
        picks.append({
            "pick_number": pick.get("overallPickNumber"),
            "round": pick.get("roundId"),
            "round_pick": pick.get("roundPickNumber"),
            "team_id": pick.get("teamId"),
            "team_name": team_map.get(pick.get("teamId"), f"Team {pick.get('teamId')}"),
            "player_id": pid,
            "player_name": pinfo.get("name", f"Unknown ({pid})"),
            "player_position": pinfo.get("position", "?"),
            "is_keeper": pick.get("keeper", False),
            "bid_amount": pick.get("bidAmount", 0),
        })

    result = {
        "year": year,
        "total_picks": len(picks),
        "keeper_picks": sum(1 for p in picks if p["is_keeper"]),
        "regular_picks": sum(1 for p in picks if not p["is_keeper"]),
        "picks": sorted(picks, key=lambda x: x.get("pick_number", 0)),
    }

    save_json(result, "drafts", f"draft_{year}.json")


# =============================================================================
# 4. Historical Matchup Data
# =============================================================================
def extract_matchups(year):
    print(f"\n=== EXTRACTING {year} MATCHUPS ===")
    try:
        league = League(league_id=LEAGUE_ID, year=year, espn_s2=ESPN_S2, swid=SWID)
        team_map = {t.team_id: t.team_name for t in league.teams}
    except Exception as e:
        print(f"  ❌ Failed to connect for {year}: {e}")
        return

    # Get scoring categories for this year
    try:
        settings_data = api_get(year, "mSettings")
        scoring_items = settings_data["settings"]["scoringSettings"]["scoringItems"]
        year_cats = [{"stat_id": item["statId"],
                      "name": STATS_MAP.get(item["statId"], f"ID_{item['statId']}"),
                      "is_reverse": item.get("isReverseItem", False)}
                     for item in scoring_items]
    except Exception:
        year_cats = []

    all_matchups = {"year": year, "scoring_categories": year_cats, "matchup_periods": {}}

    # IMPORTANT: Use mBoxscore view — it's the only one that returns scoreByStat.
    # mMatchupScore and mMatchup do NOT return per-category data.
    for period in range(1, 25):
        r = requests.get(api_url(year),
                         params={"view": "mBoxscore", "scoringPeriodId": period},
                         cookies=COOKIES)
        if r.status_code != 200:
            break

        data = r.json()
        period_matchups = []

        for item in data.get("schedule", []):
            if item.get("matchupPeriodId") != period:
                continue

            home = item.get("home", {})
            away = item.get("away", {})

            matchup = {
                "home_team": team_map.get(home.get("teamId"), f"Team {home.get('teamId')}"),
                "home_team_id": home.get("teamId"),
                "away_team": team_map.get(away.get("teamId"), f"Team {away.get('teamId')}"),
                "away_team_id": away.get("teamId"),
                "winner": item.get("winner"),
            }

            for side, side_data in [("home", home), ("away", away)]:
                cum = side_data.get("cumulativeScore", {})
                matchup[f"{side}_category_wins"] = cum.get("wins", 0)
                matchup[f"{side}_category_losses"] = cum.get("losses", 0)
                matchup[f"{side}_category_ties"] = cum.get("ties", 0)

                sbs = cum.get("scoreByStat", {})
                if sbs:
                    stats = {}
                    for sid_str, stat_data in sbs.items():
                        sid = int(sid_str)
                        name = STATS_MAP.get(sid, f"id_{sid}")
                        stats[name] = {
                            "value": stat_data.get("score"),
                            "result": stat_data.get("result"),
                        }
                    matchup[f"{side}_stats"] = stats

            period_matchups.append(matchup)

        if not period_matchups:
            break

        all_matchups["matchup_periods"][str(period)] = period_matchups
        time.sleep(0.2)

    all_matchups["total_periods_extracted"] = len(all_matchups["matchup_periods"])
    save_json(all_matchups, "matchups", f"matchups_{year}.json")


# =============================================================================
# 5. Historical Standings
# =============================================================================
def extract_standings(year):
    print(f"\n=== EXTRACTING {year} STANDINGS ===")
    try:
        league = League(league_id=LEAGUE_ID, year=year, espn_s2=ESPN_S2, swid=SWID)
    except Exception as e:
        print(f"  ❌ Failed for {year}: {e}")
        return

    standings = []
    for team in sorted(league.teams, key=lambda t: t.standing if hasattr(t, "standing") else 99):
        entry = {
            "team_id": team.team_id,
            "team_name": team.team_name,
            "wins": team.wins,
            "losses": team.losses,
            "ties": team.ties,
            "standing": team.standing if hasattr(team, "standing") else None,
            "final_standing": team.final_standing if hasattr(team, "final_standing") else None,
            "points_for": team.points_for if hasattr(team, "points_for") else None,
            "points_against": team.points_against if hasattr(team, "points_against") else None,
            "streak_type": team.streak_type if hasattr(team, "streak_type") else None,
            "streak_length": team.streak_length if hasattr(team, "streak_length") else None,
        }
        # Owner info
        if team.owners:
            owner = team.owners[0]
            entry["owner"] = f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip()

        standings.append(entry)

    result = {
        "year": year,
        "standings": standings,
    }
    save_json(result, "standings", f"standings_{year}.json")


# =============================================================================
# 6. Transactions Summary
# =============================================================================
def extract_transactions(year):
    print(f"\n=== EXTRACTING {year} TRANSACTIONS ===")
    try:
        data = api_get(year, "mTransactions2")
    except Exception as e:
        print(f"  ❌ Failed for {year}: {e}")
        return {"year": year, "error": str(e)}

    transactions = data.get("transactions", [])
    if not transactions:
        print(f"  ⚠️  No transactions for {year}")
        return {"year": year, "total": 0, "by_team": {}, "by_type": {}}

    # Get team names
    try:
        league = League(league_id=LEAGUE_ID, year=year, espn_s2=ESPN_S2, swid=SWID)
        team_map = {t.team_id: t.team_name for t in league.teams}
    except Exception:
        team_map = {}

    # Aggregate by team and type
    by_team = {}
    by_type = {}
    for txn in transactions:
        txn_type = txn.get("type", "UNKNOWN")
        by_type[txn_type] = by_type.get(txn_type, 0) + 1

        team_id = txn.get("teamId")
        if team_id:
            team_name = team_map.get(team_id, f"Team {team_id}")
            if team_name not in by_team:
                by_team[team_name] = {"total": 0, "by_type": {}}
            by_team[team_name]["total"] += 1
            by_team[team_name]["by_type"][txn_type] = by_team[team_name]["by_type"].get(txn_type, 0) + 1

    return {
        "year": year,
        "total": len(transactions),
        "by_team": by_team,
        "by_type": by_type,
    }


# =============================================================================
# 7. Free Agents (2026)
# =============================================================================
def extract_free_agents():
    print("\n=== EXTRACTING 2026 FREE AGENTS ===")
    try:
        league = League(league_id=LEAGUE_ID, year=2026, espn_s2=ESPN_S2, swid=SWID)
        fa_list = league.free_agents(size=250)
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return

    agents = []
    for p in fa_list:
        eligible = [POS_MAP.get(pid, f"POS_{pid}") for pid in p.eligibleSlots
                    if pid in POS_MAP] if hasattr(p, "eligibleSlots") else []
        entry = {
            "name": p.name,
            "espn_id": p.playerId,
            "position": p.position,
            "eligible_positions": eligible,
            "pro_team": p.proTeam,
            "injury_status": p.injuryStatus if hasattr(p, "injuryStatus") else "ACTIVE",
        }

        # Try to get projected stats
        if hasattr(p, "stats") and p.stats:
            entry["stats"] = {}
            for stat_key, stat_val in p.stats.items():
                if isinstance(stat_val, dict) and "breakdown" in stat_val:
                    entry["stats"][str(stat_key)] = stat_val["breakdown"]

        agents.append(entry)

    save_json({"year": 2026, "count": len(agents), "players": agents}, "free_agents_2026.json")


# =============================================================================
# 8. Player Projections via Raw API
# =============================================================================
def extract_projections():
    print("\n=== EXTRACTING 2026 PLAYER PROJECTIONS ===")
    all_players = []

    # Fetch batters and pitchers separately using kona_player_info
    for slot_ids, label in [([0, 1, 2, 3, 4, 5, 6, 7, 11, 12], "hitters"),
                            ([13, 14, 15], "pitchers")]:
        for offset in range(0, 600, 50):
            filter_obj = {
                "players": {
                    "filterStatus": {"value": ["FREEAGENT", "ONTEAM", "WAIVERS"]},
                    "filterSlotIds": {"value": slot_ids},
                    "limit": 50,
                    "offset": offset,
                }
            }

            try:
                r = requests.get(
                    api_url(CURRENT_YEAR),
                    params={"view": "kona_player_info"},
                    cookies=COOKIES,
                    headers={"x-fantasy-filter": json.dumps(filter_obj)},
                )
                if r.status_code != 200:
                    if offset == 0:
                        print(f"  ⚠️  {label}: HTTP {r.status_code}")
                    break

                data = r.json()
                players = data.get("players", [])
                if not players:
                    break

                for p_entry in players:
                    player = p_entry.get("player", {})
                    pid = p_entry.get("id") or player.get("id")

                    eligible = [POS_MAP.get(sid, "") for sid in player.get("eligibleSlots", [])
                                if sid in POS_MAP]

                    player_data = {
                        "espn_id": pid,
                        "name": player.get("fullName", "?"),
                        "position": POS_MAP.get(player.get("defaultPositionId", 0), "?"),
                        "eligible_positions": eligible,
                        "pro_team": player.get("proTeamId"),
                        "ownership_pct": player.get("ownership", {}).get("percentOwned", 0),
                    }

                    for stat_set in player.get("stats", []):
                        source_id = stat_set.get("statSourceId", -1)
                        season = stat_set.get("seasonId", 0)
                        split = stat_set.get("statSplitTypeId", -1)
                        stats = stat_set.get("stats", {})
                        if not stats:
                            continue

                        source_label = "actual" if source_id == 0 else "projected" if source_id == 1 else f"src_{source_id}"
                        key = f"{source_label}_{season}_split{split}"

                        named_stats = {}
                        for sid_str, val in stats.items():
                            stat_name = STATS_MAP.get(int(sid_str), f"id_{sid_str}")
                            named_stats[stat_name] = val
                        player_data[key] = named_stats

                    all_players.append(player_data)

                if offset == 0:
                    print(f"  {label}: fetching (first batch: {len(players)} players)")

            except Exception as e:
                print(f"  ❌ {label}: {e}")
                break

    print(f"  Total: {len(all_players)} players, {sum(1 for p in all_players if any('projected_' in k for k in p.keys()))} with projections")
    save_json({"year": CURRENT_YEAR, "count": len(all_players), "players": all_players}, f"projections_{CURRENT_YEAR}.json")


# =============================================================================
# Main
# =============================================================================
def main():
    print("=" * 60)
    print("ESPN Fantasy Baseball Data Extraction")
    print(f"League: Magic Conch 2025 (ID: {LEAGUE_ID})")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. League config
    config = extract_league_config()

    # 2. Current rosters
    extract_rosters_2026()

    # 3. Historical drafts
    for year in HISTORICAL_YEARS:
        extract_draft(year)
        time.sleep(1)  # Rate limiting

    # 4. Historical matchups
    for year in HISTORICAL_YEARS:
        extract_matchups(year)
        time.sleep(1)

    # 5. Historical standings
    for year in HISTORICAL_YEARS:
        extract_standings(year)
        time.sleep(0.5)

    # 6. Transactions
    txn_summary = {"years": {}}
    for year in HISTORICAL_YEARS:
        result = extract_transactions(year)
        txn_summary["years"][str(year)] = result
        time.sleep(0.5)
    save_json(txn_summary, "transactions", "transaction_summary.json")

    # 7. Free agents
    extract_free_agents()

    # 8. Projections
    extract_projections()

    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print(f"Finished: {datetime.now().isoformat()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
