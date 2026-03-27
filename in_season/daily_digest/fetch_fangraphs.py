"""
FanGraphs API fetchers for RoS projections and leaderboard stats.
"""

import re
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import numpy as np

from config import (
    FANGRAPHS_RATE_LIMIT, ROS_PROJECTION_PRIMARY, ROS_PROJECTION_FALLBACK,
    ROS_MULTI_SYSTEMS, FANGRAPHS_CACHE_HOURS, MULTI_SYSTEM_CACHE_DAYS,
    OUTPUT_DIR, EXISTING_TOOLS,
)

log = logging.getLogger(__name__)

_last_request_time = 0.0

FANGRAPHS_PROJ_URL = "https://www.fangraphs.com/api/projections"
FANGRAPHS_LEADERS_URL = "https://www.fangraphs.com/api/leaders/major-league/data"


def _fg_get(url, params):
    """Rate-limited GET to FanGraphs API."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < FANGRAPHS_RATE_LIMIT:
        time.sleep(FANGRAPHS_RATE_LIMIT - elapsed)

    r = requests.get(url, params=params, timeout=30)
    _last_request_time = time.time()
    r.raise_for_status()
    return r.json()


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
        json.dump(data, f)


# ---- RoS Projections ----

def fetch_ros_projections(stats="bat"):
    """
    Fetch rest-of-season projections from FanGraphs.
    Returns a DataFrame with standard column names.
    Falls back to pre-season ATC CSVs if RoS not available.
    """
    cache_name = f"ros_{stats}"
    if _cache_valid(cache_name, FANGRAPHS_CACHE_HOURS):
        log.info(f"Using cached RoS {stats} projections")
        df = pd.DataFrame(_load_cache(cache_name))
        return _normalize_fg_df(df, stats)

    # Try RoS ATC first, then Steamer RoS
    for proj_type in [ROS_PROJECTION_PRIMARY, ROS_PROJECTION_FALLBACK]:
        try:
            params = {
                "type": proj_type,
                "stats": "bat" if stats == "bat" else "pit",
                "pos": "all",
                "team": "0",
                "players": "0",
                "lg": "all",
            }
            data = _fg_get(FANGRAPHS_PROJ_URL, params)
            if data and len(data) > 10:
                log.info(f"Fetched {len(data)} {stats} RoS projections ({proj_type})")
                df = pd.DataFrame(data)
                _save_cache(cache_name, data)
                return _normalize_fg_df(df, stats)
        except Exception as e:
            log.warning(f"RoS {proj_type} {stats} fetch failed: {e}")

    # Fallback to pre-season ATC CSVs
    log.info(f"RoS projections unavailable, falling back to pre-season ATC")
    return _load_preseason_fallback(stats)


def _normalize_fg_df(df, stats):
    """Normalize FanGraphs DataFrame column names."""
    # Handle BOM in Name column
    for col in df.columns:
        if "Name" in col:
            df = df.rename(columns={col: "name"})
            break

    if "PlayerName" in df.columns:
        df = df.rename(columns={"PlayerName": "name"})
    if "xMLBAMID" in df.columns:
        df = df.rename(columns={"xMLBAMID": "mlbam_id"})
    if "playerid" in df.columns:
        df = df.rename(columns={"playerid": "fg_id"})

    # Strip HTML from names (FanGraphs leaderboard wraps in <a> tags)
    if "name" in df.columns:
        df["name"] = df["name"].apply(
            lambda x: re.sub(r"<[^>]+>", "", str(x)) if isinstance(x, str) else x
        )

    if stats == "bat":
        _derive_batter_stats(df)
    else:
        _derive_pitcher_stats(df)

    return df


def _derive_batter_stats(df):
    """Derive TB, SBN from component stats."""
    if "TB" not in df.columns:
        if "1B" in df.columns and "2B" in df.columns:
            df["TB"] = (df["1B"].fillna(0) + 2 * df["2B"].fillna(0)
                        + 3 * df.get("3B", pd.Series(0, index=df.index)).fillna(0)
                        + 4 * df.get("HR", pd.Series(0, index=df.index)).fillna(0))
        elif "H" in df.columns:
            df["TB"] = (df["H"].fillna(0) + df.get("2B", pd.Series(0, index=df.index)).fillna(0)
                        + 2 * df.get("3B", pd.Series(0, index=df.index)).fillna(0)
                        + 3 * df.get("HR", pd.Series(0, index=df.index)).fillna(0))
    if "SBN" not in df.columns and "SB" in df.columns:
        df["SBN"] = df["SB"].fillna(0) - df.get("CS", pd.Series(0, index=df.index)).fillna(0)


def _derive_pitcher_stats(df):
    """Derive SVHD, K, KBB from pitcher stats."""
    if "HLD" in df.columns:
        df["SVHD"] = df.get("SV", pd.Series(0, index=df.index)).fillna(0) + df["HLD"].fillna(0)
    elif "SV" in df.columns and "SVHD" not in df.columns:
        df["SVHD"] = df["SV"]
    if "SO" in df.columns and "K" not in df.columns:
        df["K"] = df["SO"]
    # FanGraphs uses "K/BB" column name; normalize to "KBB"
    if "K/BB" in df.columns and "KBB" not in df.columns:
        df["KBB"] = df["K/BB"]
    if "KBB" not in df.columns and "BB" in df.columns and "K" in df.columns:
        df["KBB"] = np.where(df["BB"] > 0, df["K"] / df["BB"], 0)


def _load_preseason_fallback(stats):
    """Load pre-season ATC CSV as fallback when RoS isn't available."""
    if stats == "bat":
        path = EXISTING_TOOLS / "FanGraphs_ATC_Batters_2026.csv"
    else:
        path = EXISTING_TOOLS / "FanGraphs_ATC_Pitchers_2026.csv"

    if not path.exists():
        log.error(f"Fallback CSV not found: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    return _normalize_fg_df(df, stats)


# ---- Leaderboard (actual season stats) ----

def fetch_leaderboard(stats="bat"):
    """
    Fetch current-season actual stats for regression detection.
    Returns DataFrame with BABIP, K%, HR/FB%, Hard%, etc.
    """
    cache_name = f"leaders_{stats}"
    if _cache_valid(cache_name, 12):  # 12 hour cache for actuals
        log.info(f"Using cached leaderboard {stats}")
        return pd.DataFrame(_load_cache(cache_name))

    try:
        params = {
            "pos": "all",
            "stats": "bat" if stats == "bat" else "pit",
            "lg": "all",
            "qual": "0",
            "season": "2026",
            "month": "0",
            "ind": "0",
        }
        data = _fg_get(FANGRAPHS_LEADERS_URL, params)

        # FanGraphs leaders endpoint wraps data in a 'data' key
        if isinstance(data, dict) and "data" in data:
            records = data["data"]
        else:
            records = data

        if records and len(records) > 0:
            df = pd.DataFrame(records)
            _save_cache(cache_name, records)
            return _normalize_fg_df(df, stats)
    except Exception as e:
        log.warning(f"Leaderboard fetch failed: {e}")

    return pd.DataFrame()


# ---- Multi-system disagreement ----

def fetch_multi_system_ros(stats="bat"):
    """
    Fetch projections from multiple RoS systems and compute inter-system
    disagreement (std dev) per player per stat. Cached weekly.
    """
    cache_name = f"multi_system_{stats}"
    if _cache_valid(cache_name, MULTI_SYSTEM_CACHE_DAYS * 24):
        log.info(f"Using cached multi-system disagreement {stats}")
        return pd.DataFrame(_load_cache(cache_name))

    all_systems = {}
    for sys_type in ROS_MULTI_SYSTEMS:
        try:
            params = {
                "type": sys_type,
                "stats": "bat" if stats == "bat" else "pit",
                "pos": "all",
                "team": "0",
                "players": "0",
                "lg": "all",
            }
            data = _fg_get(FANGRAPHS_PROJ_URL, params)
            if data and len(data) > 10:
                df = pd.DataFrame(data)
                df = _normalize_fg_df(df, stats)
                all_systems[sys_type] = df
                log.info(f"  Fetched {sys_type}: {len(df)} players")
        except Exception as e:
            log.warning(f"  {sys_type} failed: {e}")

    if len(all_systems) < 2:
        log.warning("Fewer than 2 projection systems available for disagreement calc")
        return pd.DataFrame()

    # Compute per-player disagreement across systems
    if stats == "bat":
        key_stats = ["R", "HR", "TB", "RBI", "SBN", "OBP"]
    else:
        key_stats = ["K", "QS", "ERA", "WHIP", "KBB", "SVHD"]

    # Merge all systems on mlbam_id
    merged_rows = []
    # Get all unique mlbam_ids across systems
    all_ids = set()
    for df in all_systems.values():
        if "mlbam_id" in df.columns:
            all_ids.update(df["mlbam_id"].dropna().astype(int).tolist())

    for mid in all_ids:
        row = {"mlbam_id": mid}
        for stat in key_stats:
            values = []
            for sys_name, df in all_systems.items():
                if "mlbam_id" not in df.columns or stat not in df.columns:
                    continue
                match = df[df["mlbam_id"] == mid]
                if len(match) > 0:
                    val = match.iloc[0].get(stat)
                    if pd.notna(val):
                        values.append(float(val))
            if len(values) >= 2:
                row[f"{stat}_mean"] = np.mean(values)
                row[f"{stat}_std"] = np.std(values)
                row[f"{stat}_n_systems"] = len(values)
            else:
                row[f"{stat}_mean"] = values[0] if values else np.nan
                row[f"{stat}_std"] = np.nan
                row[f"{stat}_n_systems"] = len(values)

        # Get name from any system
        for df in all_systems.values():
            if "mlbam_id" in df.columns and "name" in df.columns:
                match = df[df["mlbam_id"] == mid]
                if len(match) > 0 and pd.notna(match.iloc[0].get("name")):
                    row["name"] = match.iloc[0]["name"]
                    break

        merged_rows.append(row)

    result = pd.DataFrame(merged_rows)
    if len(result) > 0:
        _save_cache(cache_name, result.to_dict(orient="records"))
    return result
