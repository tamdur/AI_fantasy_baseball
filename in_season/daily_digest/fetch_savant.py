"""
Baseball Savant (Statcast) data fetchers.
Free public API, no auth required.
Provides expected stats (xBA, xSLG, xERA, xwOBA), barrel rates, sprint speed.
"""

import logging
from datetime import datetime, timedelta

import requests
import pandas as pd

from config import OUTPUT_DIR

log = logging.getLogger(__name__)

SAVANT_LEADERS_URL = "https://baseballsavant.mlb.com/leaderboard/expected_statistics"
SAVANT_SPRINT_URL = "https://baseballsavant.mlb.com/leaderboard/sprint_speed"


def _cache_path(name):
    return OUTPUT_DIR / f"cache_{name}.json"


def _cache_valid(name, max_hours):
    p = _cache_path(name)
    if not p.exists():
        return False
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    return (datetime.now() - mtime) < timedelta(hours=max_hours)


def fetch_savant_expected_stats(player_type="batter"):
    """
    Fetch Statcast expected stats (xBA, xSLG, xwOBA, xERA, barrel%).
    Returns DataFrame with MLBAM IDs.
    """
    cache_name = f"savant_xstats_{player_type}"
    if _cache_valid(cache_name, 12):
        log.info(f"Using cached Savant xStats ({player_type})")
        return pd.read_json(_cache_path(cache_name))

    try:
        params = {
            "type": player_type,  # "batter" or "pitcher"
            "year": "2026",
            "position": "",
            "team": "",
            "min": "1",  # minimum PAs/batters faced
            "csv": "true",
        }

        r = requests.get(SAVANT_LEADERS_URL, params=params, timeout=30)
        r.raise_for_status()

        # Savant returns CSV when csv=true
        if r.headers.get("content-type", "").startswith("text/csv") or "," in r.text[:200]:
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
        else:
            # Sometimes returns JSON
            import json
            data = json.loads(r.text)
            df = pd.DataFrame(data)

        if len(df) > 0:
            # Normalize column names
            col_map = {
                "player_id": "mlbam_id",
                "last_name, first_name": "name",
                "player_name": "name",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

            df.to_json(_cache_path(cache_name), orient="records")
            log.info(f"Fetched Savant xStats: {len(df)} {player_type}s")
            return df

    except Exception as e:
        log.warning(f"Savant xStats fetch failed ({player_type}): {e}")

    return pd.DataFrame()


def fetch_sprint_speed():
    """Fetch Statcast sprint speed leaderboard."""
    cache_name = "savant_sprint"
    if _cache_valid(cache_name, 24):
        log.info("Using cached Savant sprint speed")
        return pd.read_json(_cache_path(cache_name))

    try:
        params = {
            "year": "2026",
            "position": "",
            "team": "",
            "min": "1",
            "csv": "true",
        }
        r = requests.get(SAVANT_SPRINT_URL, params=params, timeout=30)
        r.raise_for_status()

        from io import StringIO
        df = pd.read_csv(StringIO(r.text))
        if len(df) > 0:
            col_map = {"player_id": "mlbam_id", "last_name, first_name": "name"}
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            df.to_json(_cache_path(cache_name), orient="records")
            log.info(f"Fetched sprint speed: {len(df)} players")
            return df

    except Exception as e:
        log.warning(f"Sprint speed fetch failed: {e}")

    return pd.DataFrame()


MIN_BBE_FOR_XSTATS = 50   # minimum batted ball events for xBA/xSLG
MIN_BF_FOR_XERA = 50      # minimum batters faced for xERA
MIN_PA_FOR_BARREL = 50     # minimum PA for barrel rate


def compute_regression_signals(savant_batters, savant_pitchers):
    """
    Compute regression risk scores from Savant expected stats.
    Returns dict of mlbam_id -> regression signals.

    Sample size gates: flags are suppressed below minimum thresholds
    to avoid treating Opening Week noise as actionable intelligence.
    """
    signals = {}

    if savant_batters is not None and len(savant_batters) > 0:
        for _, row in savant_batters.iterrows():
            mid = row.get("mlbam_id")
            if pd.isna(mid):
                continue
            mid = int(mid)
            flags = []

            # Get sample size — Savant uses "pa" or "ab" columns
            bbe = _get_numeric(row, "bip", "bbe", "batted_balls")
            pa = _get_numeric(row, "pa", "plate_appearances")

            # xBA vs actual BA — requires sufficient batted ball events
            if bbe is not None and bbe >= MIN_BBE_FOR_XSTATS:
                xba = row.get("est_ba") or row.get("xba")
                ba = row.get("ba") or row.get("avg")
                if xba is not None and ba is not None:
                    delta = float(ba) - float(xba)
                    if delta > 0.030:
                        flags.append(f"xBA .{int(float(xba)*1000):03d} vs actual .{int(float(ba)*1000):03d} — overperforming, regression risk (n={int(bbe)} BBE)")
                    elif delta < -0.030:
                        flags.append(f"xBA .{int(float(xba)*1000):03d} vs actual .{int(float(ba)*1000):03d} — underperforming, buy-low (n={int(bbe)} BBE)")

            # xSLG vs actual SLG — same threshold
            if bbe is not None and bbe >= MIN_BBE_FOR_XSTATS:
                xslg = row.get("est_slg") or row.get("xslg")
                slg = row.get("slg")
                if xslg is not None and slg is not None:
                    delta = float(slg) - float(xslg)
                    if delta > 0.050:
                        flags.append(f"xSLG .{int(float(xslg)*1000):03d} vs actual .{int(float(slg)*1000):03d} — TB/HR overperforming")
                    elif delta < -0.050:
                        flags.append(f"xSLG .{int(float(xslg)*1000):03d} vs actual .{int(float(slg)*1000):03d} — TB/HR underperforming, buy-low")

            # Barrel rate — needs enough PA to be meaningful
            effective_pa = pa if pa is not None else bbe
            if effective_pa is not None and effective_pa >= MIN_PA_FOR_BARREL:
                barrel = row.get("barrel_batted_rate") or row.get("brl_percent")
                if barrel is not None and float(barrel) > 15:
                    flags.append(f"Barrel% {float(barrel):.1f}% — elite contact quality")

            if flags:
                signals[mid] = flags

    if savant_pitchers is not None and len(savant_pitchers) > 0:
        for _, row in savant_pitchers.iterrows():
            mid = row.get("mlbam_id")
            if pd.isna(mid):
                continue
            mid = int(mid)
            flags = signals.get(mid, [])

            # Get sample size for pitchers
            bf = _get_numeric(row, "pa", "bf", "batters_faced")

            # xERA vs ERA — requires sufficient batters faced
            if bf is not None and bf >= MIN_BF_FOR_XERA:
                xera = row.get("est_era") or row.get("xera")
                era = row.get("era")
                if xera is not None and era is not None:
                    delta = float(era) - float(xera)
                    if delta < -0.50:
                        flags.append(f"xERA {float(xera):.2f} vs actual {float(era):.2f} — ERA likely to RISE (n={int(bf)} BF)")
                    elif delta > 0.50:
                        flags.append(f"xERA {float(xera):.2f} vs actual {float(era):.2f} — ERA likely to IMPROVE (n={int(bf)} BF)")

            if flags:
                signals[mid] = flags

    return signals


def _get_numeric(row, *col_names):
    """Get the first non-null numeric value from a row for the given column names."""
    for col in col_names:
        val = row.get(col)
        if val is not None and not pd.isna(val):
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None
