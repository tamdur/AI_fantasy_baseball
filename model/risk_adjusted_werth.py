"""
Distribution-Aware WERTH: Risk-adjusted valuations accounting for projection
variance and the waiver wire floor.

Key insight: In H2H with 7 weekly pickups, the waiver wire acts as a free put
option. If a drafted player busts below replacement, you drop and pick up a FA.
This truncates the left tail, making higher-variance players more valuable
(especially in late rounds near the waiver floor).

Formula: E[max(X, w)] = mu*Phi((mu-w)/sigma) + sigma*phi((mu-w)/sigma) + w*Phi((w-mu)/sigma)
where Phi = normal CDF, phi = normal PDF, mu = WERTH, sigma = WERTH SD, w = waiver floor
"""

import pandas as pd
import numpy as np
from scipy.stats import norm


def estimate_werth_sigma(hitters, pitchers, steamer_hit, steamer_pit):
    """
    Estimate per-player WERTH standard deviation using Steamer quantile data.

    Approach: Use linear regression of total_werth on the performance metric
    (wOBA for batters, ERA for pitchers) to get a conversion factor, then
    multiply by each player's performance SD from Steamer quantiles.
    """
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    # --- Batters: wOBA quantiles -> WERTH sigma ---
    # Join Steamer wOBA data to hitters
    stm_cols = ["xMLBAMID", "q10", "q50", "q90", "woba_sd", "total_se"]
    stm_h = steamer_hit[stm_cols].rename(columns={"xMLBAMID": "mlbam_id"}).copy()
    stm_h = stm_h.drop_duplicates(subset=["mlbam_id"])

    hitters = hitters.merge(stm_h, on="mlbam_id", how="left", suffixes=("", "_stm"))

    # Performance SD from quantiles: sigma_wOBA = (q90 - q10) / 2.56
    hitters["perf_sd"] = (hitters["q90"] - hitters["q10"]) / 2.56

    # Regression: total_werth ~ wOBA for starters to get slope
    starters_h = hitters[hitters["is_starter"] & hitters["OBP"].notna() & hitters["perf_sd"].notna()]
    if len(starters_h) > 10:
        # Use wOBA (q50) as the performance metric
        x = starters_h["q50"].values
        y = starters_h["total_werth"].values
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) > 5:
            # Simple linear regression
            slope = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 0
            # Also account for playing time: scale by sqrt(PA/avg_PA) since
            # variance of counting stats scales with sqrt(PA)
            avg_pa = starters_h["PA"].mean()
            pa_factor = np.sqrt(hitters["PA"].fillna(avg_pa) / avg_pa)
            hitters["werth_sigma"] = abs(slope) * hitters["perf_sd"].fillna(0) * pa_factor
        else:
            hitters["werth_sigma"] = 0
    else:
        hitters["werth_sigma"] = 0

    # --- Pitchers: ERA quantiles -> WERTH sigma ---
    stm_p_cols = ["xMLBAMID", "q10", "q50", "q90", "ra_talent_sd", "total_ra_se"]
    stm_p = steamer_pit[stm_p_cols].rename(columns={"xMLBAMID": "mlbam_id"}).copy()
    stm_p = stm_p.drop_duplicates(subset=["mlbam_id"])

    pitchers = pitchers.merge(stm_p, on="mlbam_id", how="left", suffixes=("", "_stm"))

    # For pitchers: q10 = bad (high ERA), q90 = good (low ERA)
    # sigma_ERA = (q10 - q90) / 2.56
    pitchers["perf_sd"] = (pitchers["q10"] - pitchers["q90"]) / 2.56

    # Regression: total_werth ~ -ERA for starters
    starters_p = pitchers[pitchers["is_starter"] & pitchers["ERA"].notna() & pitchers["perf_sd"].notna()]
    if len(starters_p) > 10:
        x = starters_p["q50"].values  # ERA at median
        y = starters_p["total_werth"].values
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) > 5:
            slope = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 0
            avg_ip = starters_p["IP"].mean()
            ip_factor = np.sqrt(pitchers["IP"].fillna(avg_ip) / avg_ip)
            # slope is negative (lower ERA -> higher WERTH), take abs
            pitchers["werth_sigma"] = abs(slope) * pitchers["perf_sd"].fillna(0) * ip_factor
        else:
            pitchers["werth_sigma"] = 0
    else:
        pitchers["werth_sigma"] = 0

    # Fill missing sigmas with position-group median
    for pos in hitters["primary_position"].unique():
        mask = (hitters["primary_position"] == pos) & (hitters["werth_sigma"] <= 0)
        pos_median = hitters.loc[
            (hitters["primary_position"] == pos) & (hitters["werth_sigma"] > 0),
            "werth_sigma"
        ].median()
        if pd.notna(pos_median) and pos_median > 0:
            hitters.loc[mask, "werth_sigma"] = pos_median

    for pt in ["SP", "RP"]:
        mask = (pitchers.get("pitcher_type") == pt) & (pitchers["werth_sigma"] <= 0)
        pt_median = pitchers.loc[
            (pitchers.get("pitcher_type") == pt) & (pitchers["werth_sigma"] > 0),
            "werth_sigma"
        ].median()
        if pd.notna(pt_median) and pt_median > 0:
            pitchers.loc[mask, "werth_sigma"] = pt_median

    # Ensure minimum sigma (even reliable players have some variance)
    min_sigma = 0.5
    hitters["werth_sigma"] = hitters["werth_sigma"].clip(lower=min_sigma)
    pitchers["werth_sigma"] = pitchers["werth_sigma"].clip(lower=min_sigma)

    # Drop temporary columns
    for col in ["q10", "q50", "q90", "woba_sd", "total_se", "perf_sd",
                "ra_talent_sd", "total_ra_se"]:
        for df in [hitters, pitchers]:
            if col in df.columns:
                df.drop(columns=[col], inplace=True, errors="ignore")

    return hitters, pitchers


def compute_waiver_floor(hitters, pitchers, pos_replacement):
    """
    Compute the waiver floor (w) for each position group.

    The waiver floor represents the WERTH of the 4th-best free agent at each
    position — the median realistic outcome of a waiver pickup.

    We define "free agent quality" as players ranked outside the top
    (starters + bench) at each position.
    """
    from data_pipeline import NUM_TEAMS, ROSTER_SLOTS

    # Total drafted players per position = starters + bench allocation
    # Bench is 3 per team, roughly split across positions
    bench_per_team = ROSTER_SLOTS.get("BE", 3)
    total_rostered = (sum(v for k, v in ROSTER_SLOTS.items()
                         if k not in ("IL",)) * NUM_TEAMS)

    waiver_floors = {}

    # Hitter positions
    for pos in ["C", "1B", "2B", "3B", "SS", "OF"]:
        pos_players = hitters[hitters["primary_position"] == pos].sort_values(
            "pos_adj_werth", ascending=False
        )
        # Rostered: starters + ~1 bench per position per team
        roster_depth = ROSTER_SLOTS.get(pos, 1) * NUM_TEAMS + NUM_TEAMS
        if pos == "OF":
            roster_depth = ROSTER_SLOTS["OF"] * NUM_TEAMS + NUM_TEAMS * 2

        fa_pool = pos_players.iloc[roster_depth:] if len(pos_players) > roster_depth else pd.DataFrame()
        if len(fa_pool) >= 4:
            waiver_floors[pos] = fa_pool.iloc[3]["pos_adj_werth"]
        elif len(fa_pool) > 0:
            waiver_floors[pos] = fa_pool.iloc[-1]["pos_adj_werth"]
        else:
            waiver_floors[pos] = 0

    # Use the worst hitter floor for flex positions
    hitter_floor_vals = [v for v in waiver_floors.values()]
    for flex in ["MI", "CI", "UTIL"]:
        waiver_floors[flex] = max(hitter_floor_vals) if hitter_floor_vals else 0

    # Pitcher positions
    for pt in ["SP", "RP"]:
        pt_players = pitchers[pitchers.get("pitcher_type") == pt].sort_values(
            "pos_adj_werth", ascending=False
        )
        if pt == "SP":
            roster_depth = 6 * NUM_TEAMS + NUM_TEAMS  # ~7 SP rostered per team
        else:
            roster_depth = 3 * NUM_TEAMS + NUM_TEAMS  # ~4 RP rostered per team

        fa_pool = pt_players.iloc[roster_depth:] if len(pt_players) > roster_depth else pd.DataFrame()
        if len(fa_pool) >= 4:
            waiver_floors[pt] = fa_pool.iloc[3]["pos_adj_werth"]
        elif len(fa_pool) > 0:
            waiver_floors[pt] = fa_pool.iloc[-1]["pos_adj_werth"]
        else:
            waiver_floors[pt] = 0

    # General pitcher floor
    waiver_floors["P"] = min(waiver_floors.get("SP", 0), waiver_floors.get("RP", 0))

    print("\nWaiver floors by position:")
    for pos, val in sorted(waiver_floors.items()):
        print(f"  {pos}: {val:.2f}")

    return waiver_floors


def truncated_expectation(mu, sigma, w):
    """
    E[max(X, w)] for X ~ N(mu, sigma^2).

    = mu*Phi((mu-w)/sigma) + sigma*phi((mu-w)/sigma) + w*Phi((w-mu)/sigma)
    """
    if sigma <= 0:
        return max(mu, w)

    z = (mu - w) / sigma
    return mu * norm.cdf(z) + sigma * norm.pdf(z) + w * norm.cdf(-z)


def compute_risk_adjusted_werth(hitters, pitchers, waiver_floors):
    """
    Compute risk-adjusted WERTH = E[max(WERTH, waiver_floor)] for each player,
    and draft_value = risk_adj_werth - waiver_floor.
    """
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    # Hitters
    def _hitter_risk_adj(row):
        pos = row.get("primary_position", "UTIL")
        w = waiver_floors.get(pos, 0)
        mu = row["pos_adj_werth"]
        sigma = row.get("werth_sigma", 0.5)
        return truncated_expectation(mu, sigma, w)

    hitters["risk_adj_werth"] = hitters.apply(_hitter_risk_adj, axis=1)
    hitters["waiver_floor"] = hitters["primary_position"].map(waiver_floors).fillna(0)
    hitters["draft_value"] = hitters["risk_adj_werth"] - hitters["waiver_floor"]

    # Pitchers
    def _pitcher_risk_adj(row):
        pt = row.get("pitcher_type", "SP")
        w = waiver_floors.get(pt, waiver_floors.get("P", 0))
        mu = row["pos_adj_werth"]
        sigma = row.get("werth_sigma", 0.5)
        return truncated_expectation(mu, sigma, w)

    pitchers["risk_adj_werth"] = pitchers.apply(_pitcher_risk_adj, axis=1)
    pitchers["waiver_floor"] = pitchers["pitcher_type"].map(waiver_floors).fillna(0)
    pitchers["draft_value"] = pitchers["risk_adj_werth"] - pitchers["waiver_floor"]

    # Summary stats
    print("\nRisk-adjusted WERTH summary:")
    print(f"  Hitters: mean adjustment = {(hitters['risk_adj_werth'] - hitters['pos_adj_werth']).mean():.3f}")
    print(f"  Pitchers: mean adjustment = {(pitchers['risk_adj_werth'] - pitchers['pos_adj_werth']).mean():.3f}")

    # Show biggest movers
    hitters["_adj_delta"] = hitters["risk_adj_werth"] - hitters["pos_adj_werth"]
    top_movers_h = hitters.nlargest(5, "_adj_delta")[["name", "pos_adj_werth", "risk_adj_werth", "werth_sigma", "draft_value"]]
    print(f"\n  Top hitter beneficiaries of variance adjustment:")
    print(top_movers_h.to_string(float_format=lambda x: f"{x:.2f}"))
    hitters.drop(columns=["_adj_delta"], inplace=True)

    pitchers["_adj_delta"] = pitchers["risk_adj_werth"] - pitchers["pos_adj_werth"]
    top_movers_p = pitchers.nlargest(5, "_adj_delta")[["name", "pos_adj_werth", "risk_adj_werth", "werth_sigma", "draft_value"]]
    print(f"\n  Top pitcher beneficiaries of variance adjustment:")
    print(top_movers_p.to_string(float_format=lambda x: f"{x:.2f}"))
    pitchers.drop(columns=["_adj_delta"], inplace=True)

    return hitters, pitchers


def run_risk_adjustment(hitters, pitchers, pos_replacement):
    """
    Full risk-adjustment pipeline. Call after run_valuation().

    Args:
        hitters, pitchers: DataFrames from run_valuation()
        pos_replacement: dict of replacement levels from compute_replacement_level()

    Returns:
        hitters, pitchers with risk_adj_werth, draft_value, werth_sigma columns
    """
    from data_pipeline import TOOLS
    import pandas as pd

    print("\n" + "=" * 60)
    print("DISTRIBUTION-AWARE WERTH ADJUSTMENT")
    print("=" * 60)

    # Load Steamer quantile data
    steamer_hit = pd.read_csv(TOOLS / "FanGraphs_Steamer_Batters_2026.csv")
    steamer_pit = pd.read_csv(TOOLS / "FanGraphs_Steamer_Pitchers_2026.csv")

    # Step 1: Estimate WERTH sigma from Steamer quantiles
    print("\nEstimating WERTH variance from Steamer quantiles...")
    hitters, pitchers = estimate_werth_sigma(hitters, pitchers, steamer_hit, steamer_pit)

    # Step 2: Compute waiver floors
    print("\nComputing waiver floors...")
    waiver_floors = compute_waiver_floor(hitters, pitchers, pos_replacement)

    # Step 3: Risk-adjusted WERTH
    print("\nComputing risk-adjusted WERTH...")
    hitters, pitchers = compute_risk_adjusted_werth(hitters, pitchers, waiver_floors)

    return hitters, pitchers, waiver_floors
