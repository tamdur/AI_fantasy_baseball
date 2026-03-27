#!/usr/bin/env python3
"""
Correlated Uncertainty Model for WERTH Valuations.

Replaces the old scalar-sigma approach (risk_adjusted_werth.py) with a
multivariate model that captures cross-category correlations.

Key insight: A "10th percentile season" doesn't mean 10th percentile in every
category independently. HR, TB, and RBI are highly correlated (they share an
underlying power/contact skill). SBN is largely independent. OBP partially
correlates. For pitchers, ERA/WHIP/K-BB share a talent axis, QS depends on
both skill and IP, and SVHD is role-dependent.

Approach:
1. Load 8 projection systems to compute cross-system residuals per player
2. Extract the correlation structure of disagreement across categories
3. Use Steamer/ATC uncertainty metrics for variance scaling
4. Fit age/position/usage modifiers for playing time variance
5. Monte Carlo simulate correlated outcomes via Cholesky decomposition
6. Compute WERTH distribution and risk-adjusted (truncated) expectation

Author: AI Draft Tool
Date: 2026-03-23
"""

import pandas as pd
import numpy as np
from pathlib import Path
import math


# ============================================================
# Pure-numpy replacements for scipy functions
# ============================================================

def _norm_cdf(x):
    """Standard normal CDF using the error function."""
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def _norm_pdf(x):
    """Standard normal PDF."""
    return np.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)


def _cholesky_lower(A):
    """Lower Cholesky decomposition using numpy."""
    return np.linalg.cholesky(A)


def _skewness(x):
    """Sample skewness."""
    n = len(x)
    if n < 3:
        return 0.0
    m = np.mean(x)
    s = np.std(x, ddof=1)
    if s == 0:
        return 0.0
    return (n / ((n - 1) * (n - 2))) * np.sum(((x - m) / s) ** 3)

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "existing-tools"

# ============================================================
# League categories
# ============================================================
HITTING_CATS = ["R", "HR", "TB", "RBI", "SBN", "OBP"]
PITCHING_CATS = ["K", "QS", "ERA", "WHIP", "KBB", "SVHD"]
# Extended categories including playing time (used for correlation estimation)
HITTING_CATS_EXT = ["PA"] + HITTING_CATS
PITCHING_CATS_EXT = ["IP"] + PITCHING_CATS

N_SIMS = 2000  # Monte Carlo simulations per player


# ============================================================
# PHASE 1: Load all projection systems
# ============================================================

def _derive_batter_cats(df):
    """Derive TB, SBN from components if not present."""
    if "TB" not in df.columns and "1B" in df.columns:
        df["TB"] = df["1B"] + 2 * df["2B"] + 3 * df["3B"] + 4 * df["HR"]
    if "SBN" not in df.columns and "SB" in df.columns:
        df["SBN"] = df["SB"] - df["CS"].fillna(0)
    return df


def _derive_pitcher_cats(df):
    """Derive SVHD, KBB from components if not present."""
    if "SVHD" not in df.columns:
        df["SVHD"] = df.get("SV", 0) + df.get("HLD", pd.Series(0, index=df.index))
    if "K" not in df.columns and "SO" in df.columns:
        df["K"] = df["SO"]
    if "KBB" not in df.columns and "BB" in df.columns:
        df["KBB"] = np.where(df["BB"] > 0, df["K"] / df["BB"], 0)
    return df


def load_batter_systems():
    """Load all batter projection systems, return dict of {system_name: DataFrame}."""
    systems = {}
    configs = [
        ("ATC", "FanGraphs_ATC_Batters_2026.csv", "xMLBAMID"),
        ("Steamer", "FanGraphs_Steamer_Batters_2026.csv", "xMLBAMID"),
        ("TheBatX", "FanGraphs_TheBatX_Batters_2026.csv", "MLBAMID"),
        ("ZiPS", "FanGraphs_ZiPS_Batters_2026.csv", "xMLBAMID"),
        ("DepthCharts", "FanGraphs_DepthCharts_Batters_2026.csv", "xMLBAMID"),
        ("OOPSY", "FanGraphs_OOPSY_Batters_2026.csv", "xMLBAMID"),
        ("OOPSYPeak", "FanGraphs_OOPSYPeak_Batters_2026.csv", "xMLBAMID"),
        ("Steamer600", "FanGraphs_Steamer600_Batters_2026.csv", "xMLBAMID"),
    ]
    for name, fname, id_col in configs:
        path = TOOLS / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df = df.rename(columns={id_col: "mlbam_id"})
        # Handle BOM in Name column
        if "\ufeffName" in df.columns:
            df = df.rename(columns={"\ufeffName": "name"})
        elif "Name" in df.columns:
            df = df.rename(columns={"Name": "name"})
        elif "PlayerName" in df.columns:
            df = df.rename(columns={"PlayerName": "name"})
        df = _derive_batter_cats(df)
        # Keep only the columns we need
        keep_cols = ["mlbam_id", "name"] + [c for c in HITTING_CATS_EXT if c in df.columns]
        # Also keep age if present
        if "Age" in df.columns:
            keep_cols.append("Age")
        # Keep position info
        for pc in ["minpos", "Pos"]:
            if pc in df.columns:
                keep_cols.append(pc)
        # Keep uncertainty columns from specific systems
        for uc in ["InterSD", "IntraSD", "woba_sd", "truetalent_sd",
                    "woba_se", "total_se", "q10", "q50", "q90"]:
            if uc in df.columns:
                keep_cols.append(uc)
        keep_cols = [c for c in keep_cols if c in df.columns]
        systems[name] = df[keep_cols].copy()
    return systems


def load_pitcher_systems():
    """Load all pitcher projection systems."""
    systems = {}
    configs = [
        ("ATC", "FanGraphs_ATC_Pitchers_2026.csv", "xMLBAMID"),
        ("Steamer", "FanGraphs_Steamer_Pitchers_2026.csv", "xMLBAMID"),
        ("TheBat", "FanGraphs_TheBat_Pitchers_2026.csv", "xMLBAMID"),
        ("ZiPS", "FanGraphs_ZiPS_Pitchers_2026.csv", "xMLBAMID"),
        ("DepthCharts", "FanGraphs_DepthCharts_Pitchers_2026.csv", "xMLBAMID"),
        ("OOPSY", "FanGraphs_OOPSY_Pitchers_2026.csv", "xMLBAMID"),
        ("OOPSYPeak", "FanGraphs_OOPSYPeak_Pitchers_2026.csv", "xMLBAMID"),
        ("Steamer600", "FanGraphs_Steamer600_Pitchers_2026.csv", "xMLBAMID"),
    ]
    for name, fname, id_col in configs:
        path = TOOLS / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df = df.rename(columns={id_col: "mlbam_id"})
        if "PlayerName" in df.columns:
            df = df.rename(columns={"PlayerName": "name"})
        elif "\ufeffPlayerName" in df.columns:
            df = df.rename(columns={"\ufeffPlayerName": "name"})
        df = _derive_pitcher_cats(df)
        keep_cols = ["mlbam_id", "name"] + [c for c in PITCHING_CATS_EXT if c in df.columns]
        # Keep GS/G for SP/RP classification
        for gc in ["GS", "G"]:
            if gc in df.columns:
                keep_cols.append(gc)
        # Keep uncertainty columns
        for uc in ["InterSD", "IntraSD", "ra_talent_sd", "total_ra_se",
                    "q10", "q50", "q90"]:
            if uc in df.columns:
                keep_cols.append(uc)
        keep_cols = [c for c in keep_cols if c in df.columns]
        systems[name] = df[keep_cols].copy()
    return systems


# ============================================================
# PHASE 2: Cross-system residuals and correlation matrix
# ============================================================

def compute_cross_system_residuals(systems, cats_ext, min_systems=3):
    """
    For each player appearing in >= min_systems, compute per-system residuals
    (deviation from consensus) for each category.

    Returns:
        residuals_df: DataFrame with columns [mlbam_id, system, cat1_resid, cat2_resid, ...]
        consensus_df: DataFrame with columns [mlbam_id, cat1_mean, cat2_mean, ..., n_systems]
        per_player_sigma: DataFrame with per-player std dev for each category
    """
    # Collect all (mlbam_id, system, stats) triples
    records = []
    for sys_name, df in systems.items():
        if "mlbam_id" not in df.columns:
            continue
        for _, row in df.iterrows():
            mid = row["mlbam_id"]
            if pd.isna(mid) or mid == 0:
                continue
            rec = {"mlbam_id": int(mid), "system": sys_name}
            for cat in cats_ext:
                if cat in row.index and pd.notna(row[cat]):
                    rec[cat] = float(row[cat])
            if any(cat in rec for cat in cats_ext):
                records.append(rec)

    all_df = pd.DataFrame(records)

    # Compute consensus (mean across systems) for each player
    consensus_rows = []
    residual_rows = []

    for mid, grp in all_df.groupby("mlbam_id"):
        n_sys = len(grp)
        if n_sys < min_systems:
            continue

        cons = {"mlbam_id": mid, "n_systems": n_sys}
        for cat in cats_ext:
            vals = grp[cat].dropna()
            if len(vals) >= min_systems:
                cons[f"{cat}_mean"] = vals.mean()
                cons[f"{cat}_std"] = vals.std()
            else:
                cons[f"{cat}_mean"] = np.nan
                cons[f"{cat}_std"] = np.nan
        consensus_rows.append(cons)

        # Residuals for each system
        for _, row in grp.iterrows():
            res = {"mlbam_id": mid, "system": row["system"]}
            for cat in cats_ext:
                mean_val = cons.get(f"{cat}_mean", np.nan)
                if cat in row and pd.notna(row[cat]) and pd.notna(mean_val):
                    res[f"{cat}_resid"] = row[cat] - mean_val
                else:
                    res[f"{cat}_resid"] = np.nan
            residual_rows.append(res)

    consensus_df = pd.DataFrame(consensus_rows)
    residuals_df = pd.DataFrame(residual_rows)

    # Per-player sigma
    sigma_cols = [f"{cat}_std" for cat in cats_ext]
    per_player_sigma = consensus_df[["mlbam_id"] + [c for c in sigma_cols if c in consensus_df.columns]].copy()

    return residuals_df, consensus_df, per_player_sigma


def compute_correlation_matrix(residuals_df, cats_ext):
    """
    Compute the correlation matrix of cross-system residuals across categories.
    This captures how projection disagreement in one category correlates with
    disagreement in another.
    """
    resid_cols = [f"{cat}_resid" for cat in cats_ext]
    avail_cols = [c for c in resid_cols if c in residuals_df.columns]

    # Drop rows with too many NAs
    mat = residuals_df[avail_cols].dropna(thresh=len(avail_cols) - 1)

    if len(mat) < 50:
        print(f"  WARNING: Only {len(mat)} residual observations, correlation may be noisy")

    corr = mat.corr()
    # Rename columns/index to category names
    rename = {f"{cat}_resid": cat for cat in cats_ext}
    corr = corr.rename(index=rename, columns=rename)

    # Also compute the covariance matrix
    cov = mat.cov()
    cov = cov.rename(index=rename, columns=rename)

    return corr, cov


# ============================================================
# PHASE 3: Variance scaling model
# ============================================================

def build_player_variance_profile(consensus_df, systems, cats_ext, player_type="batter"):
    """
    For each player, estimate a per-category standard deviation that accounts for:
    1. Cross-system disagreement (base variance)
    2. System-specific uncertainty metrics (Steamer woba_sd, ATC InterSD)
    3. Playing time uncertainty (amplified for older players, catchers, injury-prone)

    Returns DataFrame with columns: mlbam_id, name, cat_sigma for each cat,
    plus metadata (age, position, etc.)
    """
    profiles = []

    # Get metadata from the ATC system (our primary)
    primary = systems.get("ATC", systems.get("Steamer", None))
    if primary is None:
        return pd.DataFrame()

    # Get Steamer uncertainty data
    steamer = systems.get("Steamer", pd.DataFrame())
    steamer_meta = {}
    if not steamer.empty and "mlbam_id" in steamer.columns:
        for _, row in steamer.iterrows():
            mid = row.get("mlbam_id")
            if pd.notna(mid):
                steamer_meta[int(mid)] = row

    # Get ATC uncertainty data
    atc = systems.get("ATC", pd.DataFrame())
    atc_meta = {}
    if not atc.empty and "mlbam_id" in atc.columns:
        for _, row in atc.iterrows():
            mid = row.get("mlbam_id")
            if pd.notna(mid):
                atc_meta[int(mid)] = row

    # Merge consensus data
    for _, crow in consensus_df.iterrows():
        mid = int(crow["mlbam_id"])
        profile = {"mlbam_id": mid, "n_systems": crow["n_systems"]}

        # Get player metadata
        stm = steamer_meta.get(mid, {})
        atc_row = atc_meta.get(mid, {})

        if isinstance(atc_row, pd.Series):
            profile["name"] = atc_row.get("name", "Unknown")
        elif isinstance(stm, pd.Series):
            profile["name"] = stm.get("name", "Unknown")
        else:
            profile["name"] = "Unknown"

        # --- Base variance from cross-system disagreement ---
        for cat in cats_ext:
            std_col = f"{cat}_std"
            mean_col = f"{cat}_mean"
            if std_col in crow.index and pd.notna(crow[std_col]):
                profile[f"{cat}_base_sigma"] = crow[std_col]
            else:
                profile[f"{cat}_base_sigma"] = np.nan
            if mean_col in crow.index:
                profile[f"{cat}_consensus"] = crow[mean_col]

        # --- System-specific uncertainty scaling ---
        # The cross-system std underestimates true uncertainty because:
        # a) Systems are correlated (share data sources)
        # b) Doesn't capture within-system uncertainty (random variance)
        # We use ATC InterSD and Steamer woba_sd to calibrate

        if player_type == "batter":
            # ATC InterSD is the inter-system SD of WAR-like metric
            inter_sd = atc_row.get("InterSD") if isinstance(atc_row, pd.Series) else np.nan
            intra_sd = atc_row.get("IntraSD") if isinstance(atc_row, pd.Series) else np.nan
            woba_sd = stm.get("woba_sd") if isinstance(stm, pd.Series) else np.nan
            tt_sd = stm.get("truetalent_sd") if isinstance(stm, pd.Series) else np.nan

            profile["atc_inter_sd"] = inter_sd if pd.notna(inter_sd) else np.nan
            profile["atc_intra_sd"] = intra_sd if pd.notna(intra_sd) else np.nan
            profile["steamer_woba_sd"] = woba_sd if pd.notna(woba_sd) else np.nan
            profile["steamer_tt_sd"] = tt_sd if pd.notna(tt_sd) else np.nan

            # Compute variance inflation factor:
            # True SD ≈ sqrt(cross_system_var + within_system_var)
            # ATC IntraSD approximates within-system variance
            if pd.notna(intra_sd) and pd.notna(inter_sd) and inter_sd > 0:
                # Total SD = sqrt(inter^2 + intra^2) for WAR-like metric
                # Inflation = total / inter
                profile["var_inflation"] = np.sqrt(inter_sd**2 + intra_sd**2) / inter_sd
            else:
                profile["var_inflation"] = 1.5  # Default: cross-system underestimates by ~50%

        else:  # pitcher
            ra_sd = stm.get("ra_talent_sd") if isinstance(stm, pd.Series) else np.nan
            inter_sd = atc_row.get("InterSD") if isinstance(atc_row, pd.Series) else np.nan
            intra_sd = atc_row.get("IntraSD") if isinstance(atc_row, pd.Series) else np.nan

            profile["steamer_ra_sd"] = ra_sd if pd.notna(ra_sd) else np.nan
            profile["atc_inter_sd"] = inter_sd if pd.notna(inter_sd) else np.nan
            profile["atc_intra_sd"] = intra_sd if pd.notna(intra_sd) else np.nan

            if pd.notna(intra_sd) and pd.notna(inter_sd) and inter_sd > 0:
                profile["var_inflation"] = np.sqrt(inter_sd**2 + intra_sd**2) / inter_sd
            else:
                profile["var_inflation"] = 1.5

        # --- Playing time uncertainty ---
        pa_col = "PA" if player_type == "batter" else "IP"
        pa_std = profile.get(f"{pa_col}_base_sigma", np.nan)
        pa_consensus = profile.get(f"{pa_col}_consensus", np.nan)

        # Age-based PT risk multiplier
        # Steamer has per-player PA/IP projections that already incorporate age/injury
        # The cross-system disagreement on PA/IP captures this to some extent
        # We add an age-based scaling to further differentiate
        age = None
        if isinstance(atc_row, pd.Series) and "Age" in atc_row.index:
            age = atc_row.get("Age")
        profile["age"] = age if pd.notna(age) else np.nan

        # Position
        pos = None
        if isinstance(atc_row, pd.Series):
            for pcol in ["minpos", "Pos"]:
                if pcol in atc_row.index:
                    pos = atc_row.get(pcol)
                    break
        profile["position"] = pos

        profiles.append(profile)

    return pd.DataFrame(profiles)


def apply_variance_scaling(profiles, cats_ext, player_type="batter"):
    """
    Apply age/position/usage-based variance scaling to produce final per-player
    per-category sigmas.

    Key scalings:
    - Age: variance increases ~3% per year after 28 for batters, 27 for pitchers
    - Catchers: +30% PA variance
    - Low PA/IP consensus: +20% variance (less certain playing time)
    - Apply variance inflation from ATC InterSD/IntraSD
    """
    profiles = profiles.copy()
    pa_col = "PA" if player_type == "batter" else "IP"

    # Age scaling
    ref_age = 28 if player_type == "batter" else 27
    age_factor = np.where(
        profiles["age"].notna(),
        np.clip(1.0 + 0.03 * (profiles["age"].fillna(ref_age) - ref_age), 0.9, 2.0),
        1.0
    )
    profiles["age_factor"] = age_factor

    # Position scaling (catchers have more PT variance)
    pos_factor = np.ones(len(profiles))
    if player_type == "batter":
        is_catcher = profiles["position"].fillna("").str.contains("C", case=False, na=False)
        # Exclude CF
        is_cf = profiles["position"].fillna("").str.contains("CF", case=False, na=False)
        pos_factor = np.where(is_catcher & ~is_cf, 1.3, 1.0)
    profiles["pos_factor"] = pos_factor

    # Low PT consensus scaling
    pa_consensus = profiles[f"{pa_col}_consensus"].fillna(0)
    if player_type == "batter":
        pt_factor = np.where(pa_consensus < 400, 1.3, np.where(pa_consensus < 500, 1.1, 1.0))
    else:
        pt_factor = np.where(pa_consensus < 100, 1.3, np.where(pa_consensus < 150, 1.1, 1.0))
    profiles["pt_factor"] = pt_factor

    # Variance inflation (from system-specific metrics)
    var_inflation = profiles["var_inflation"].fillna(1.5).clip(1.0, 3.0)

    # Compute final sigma for each category
    for cat in cats_ext:
        base_col = f"{cat}_base_sigma"
        if base_col not in profiles.columns:
            profiles[f"{cat}_sigma"] = np.nan
            continue

        base = profiles[base_col].fillna(0)

        # Apply scalings: inflation applies to all categories,
        # age/pos/PT factors apply primarily to PA/IP and counting stats
        if cat in (pa_col,):
            # Playing time sigma gets the full treatment
            profiles[f"{cat}_sigma"] = base * var_inflation * age_factor * pos_factor * pt_factor
        elif cat in ("OBP", "ERA", "WHIP", "KBB"):
            # Rate stats: less affected by PT uncertainty, mainly performance uncertainty
            profiles[f"{cat}_sigma"] = base * var_inflation * age_factor
        else:
            # Counting stats: affected by both performance AND PT uncertainty
            # Counting stats variance ∝ sqrt(PT_var × rate_var + PT × rate_var^2 + rate^2 × PT_var)
            # Simplified: counting variance scales with ~sqrt(PT_factor)
            combined_factor = var_inflation * np.sqrt(age_factor * pt_factor)
            profiles[f"{cat}_sigma"] = base * combined_factor

        # Floor: even with full agreement, there's irreducible variance
        # For counting stats, floor = ~5% of consensus value
        # For rate stats, use small absolute floor
        cons_col = f"{cat}_consensus"
        if cat in ("OBP",):
            profiles[f"{cat}_sigma"] = profiles[f"{cat}_sigma"].clip(lower=0.005)
        elif cat in ("ERA",):
            profiles[f"{cat}_sigma"] = profiles[f"{cat}_sigma"].clip(lower=0.15)
        elif cat in ("WHIP",):
            profiles[f"{cat}_sigma"] = profiles[f"{cat}_sigma"].clip(lower=0.03)
        elif cat in ("KBB",):
            profiles[f"{cat}_sigma"] = profiles[f"{cat}_sigma"].clip(lower=0.1)
        elif cons_col in profiles.columns:
            floor = profiles[cons_col].abs().fillna(0) * 0.05
            floor = floor.clip(lower=1.0)
            profiles[f"{cat}_sigma"] = profiles[f"{cat}_sigma"].clip(lower=floor)

    return profiles


# ============================================================
# PHASE 4: Multivariate simulation
# ============================================================

def build_cholesky_factor(corr_matrix, cats):
    """
    Build the lower Cholesky factor L from the correlation matrix,
    such that L @ L.T = corr_matrix.

    If the matrix is not positive definite (can happen with noisy estimation),
    apply nearest PD correction.
    """
    # Extract submatrix for the requested categories
    avail = [c for c in cats if c in corr_matrix.index]
    sub = corr_matrix.loc[avail, avail].values.copy()

    # Ensure symmetric
    sub = (sub + sub.T) / 2

    # Fill diagonal to 1
    np.fill_diagonal(sub, 1.0)

    # Replace NaNs with 0 (no correlation assumed for missing pairs)
    sub = np.nan_to_num(sub, nan=0.0)

    # Nearest positive definite correction (eigenvalue floor)
    eigvals, eigvecs = np.linalg.eigh(sub)
    eigvals = np.maximum(eigvals, 1e-6)
    sub = eigvecs @ np.diag(eigvals) @ eigvecs.T
    # Re-normalize to correlation matrix
    d = np.sqrt(np.diag(sub))
    sub = sub / np.outer(d, d)
    np.fill_diagonal(sub, 1.0)

    L = _cholesky_lower(sub)
    return L, avail


def simulate_player_outcomes(consensus, sigmas, L, cats, n_sims=N_SIMS):
    """
    Generate n_sims correlated outcome scenarios for a single player.

    Args:
        consensus: dict of {cat: mean_value}
        sigmas: dict of {cat: std_dev}
        L: Cholesky factor (lower triangular)
        cats: list of category names matching L's dimensions
        n_sims: number of simulations

    Returns:
        sims: dict of {cat: array of simulated values}
    """
    n_cats = len(cats)
    # Draw independent standard normals
    Z = np.random.standard_normal((n_sims, n_cats))
    # Correlate them
    correlated = Z @ L.T  # shape: (n_sims, n_cats)

    sims = {}
    for i, cat in enumerate(cats):
        mu = consensus.get(cat, 0)
        sigma = sigmas.get(cat, 0)
        if sigma <= 0:
            sims[cat] = np.full(n_sims, mu)
        else:
            sims[cat] = mu + sigma * correlated[:, i]

    # Apply physical constraints
    # PA/IP must be non-negative
    for pt_col in ("PA", "IP"):
        if pt_col in sims:
            sims[pt_col] = np.maximum(sims[pt_col], 0)
    # Counting stats floor at 0
    for cat in ("R", "HR", "TB", "RBI", "K", "QS", "SVHD"):
        if cat in sims:
            sims[cat] = np.maximum(sims[cat], 0)
    # SBN can be negative (more CS than SB) but floor at -20
    if "SBN" in sims:
        sims["SBN"] = np.maximum(sims["SBN"], -20)
    # OBP bounded [.100, .600]
    if "OBP" in sims:
        sims["OBP"] = np.clip(sims["OBP"], 0.100, 0.600)
    # ERA bounded [0.5, 12]
    if "ERA" in sims:
        sims["ERA"] = np.clip(sims["ERA"], 0.5, 12.0)
    # WHIP bounded [0.5, 3.0]
    if "WHIP" in sims:
        sims["WHIP"] = np.clip(sims["WHIP"], 0.5, 3.0)
    # KBB bounded [0.1, 10]
    if "KBB" in sims:
        sims["KBB"] = np.clip(sims["KBB"], 0.1, 10.0)

    return sims


# ============================================================
# PHASE 5: WERTH computation for simulated outcomes
# ============================================================

def precompute_zscore_params(hitters_df, pitchers_df):
    """
    Precompute the z-score conversion parameters (mean, std) for each category
    from the starter pool, so we can rapidly convert simulated stats to z-scores.

    Also precompute the rate-stat conversion parameters.
    """
    from data_pipeline import HITTING_CATS, PITCHING_CATS, LOWER_IS_BETTER, ROSTER_SLOTS, NUM_TEAMS

    params = {}

    # --- Hitting ---
    starters_h = hitters_df[hitters_df["is_starter"]]

    # OBP conversion parameters
    league_obp = (starters_h["OBP"] * starters_h["PA"]).sum() / starters_h["PA"].sum()
    avg_starter_pa = starters_h["PA"].mean()
    total_hitting_slots = sum(v for k, v in ROSTER_SLOTS.items() if k not in ("P", "BE", "IL")) * NUM_TEAMS

    params["hit_league_obp"] = league_obp
    params["hit_avg_starter_pa"] = avg_starter_pa
    params["hit_total_slots"] = total_hitting_slots

    # Z-score means and stds for each hitting category
    for cat in HITTING_CATS:
        if cat == "OBP":
            # Compute OBPc for starters
            obpc = ((starters_h["OBP"] * starters_h["PA"]) -
                    (league_obp * starters_h["PA"])) / (avg_starter_pa * total_hitting_slots)
            mean_val = obpc.mean()
            std_val = obpc.std()
        else:
            mean_val = starters_h[cat].mean()
            std_val = starters_h[cat].std()

        if cat in LOWER_IS_BETTER:
            std_val = -std_val

        params[f"hit_z_{cat}_mean"] = mean_val
        params[f"hit_z_{cat}_std"] = std_val

    # --- Pitching ---
    starters_p = pitchers_df[pitchers_df["is_starter"]]
    total_league_ip = starters_p["IP"].sum()
    league_era = (starters_p["ERA"] * starters_p["IP"]).sum() / total_league_ip
    league_whip = (starters_p["WHIP"] * starters_p["IP"]).sum() / total_league_ip
    league_kbb = (starters_p["KBB"] * starters_p["IP"]).sum() / total_league_ip

    params["pit_total_ip"] = total_league_ip
    params["pit_league_era"] = league_era
    params["pit_league_whip"] = league_whip
    params["pit_league_kbb"] = league_kbb

    for cat in PITCHING_CATS:
        if cat == "ERA":
            ip = starters_p["IP"]
            ip_share = ip / total_league_ip
            erac = (ip_share * starters_p["ERA"] + (1 - ip_share) * league_era) - league_era
            mean_val = erac.mean()
            std_val = erac.std()
        elif cat == "WHIP":
            ip = starters_p["IP"]
            ip_share = ip / total_league_ip
            whipc = (ip_share * starters_p["WHIP"] + (1 - ip_share) * league_whip) - league_whip
            mean_val = whipc.mean()
            std_val = whipc.std()
        elif cat == "KBB":
            ip = starters_p["IP"]
            ip_share = ip / total_league_ip
            kbbc = (ip_share * starters_p["KBB"] + (1 - ip_share) * league_kbb) - league_kbb
            mean_val = kbbc.mean()
            std_val = kbbc.std()
        else:
            mean_val = starters_p[cat].mean()
            std_val = starters_p[cat].std()

        if cat in LOWER_IS_BETTER:
            std_val = -std_val

        params[f"pit_z_{cat}_mean"] = mean_val
        params[f"pit_z_{cat}_std"] = std_val

    return params


def sims_to_werth_hitter(sims, zparams):
    """
    Convert simulated batter stat lines to WERTH (sum of z-scores).

    Args:
        sims: dict of {cat: array of simulated values}
        zparams: precomputed z-score parameters

    Returns:
        werth_array: array of WERTH values, one per simulation
        z_arrays: dict of {cat: array of z-scores}
    """
    from data_pipeline import HITTING_CATS, LOWER_IS_BETTER

    n_sims = len(next(iter(sims.values())))
    z_arrays = {}

    for cat in HITTING_CATS:
        mean = zparams[f"hit_z_{cat}_mean"]
        std = zparams[f"hit_z_{cat}_std"]

        if abs(std) < 1e-10:
            z_arrays[cat] = np.zeros(n_sims)
            continue

        if cat == "OBP":
            # Convert to OBPc first
            obp = sims.get("OBP", np.full(n_sims, zparams["hit_league_obp"]))
            pa = sims.get("PA", np.full(n_sims, zparams["hit_avg_starter_pa"]))
            obpc = ((obp * pa) - (zparams["hit_league_obp"] * pa)) / (
                zparams["hit_avg_starter_pa"] * zparams["hit_total_slots"])
            z_arrays[cat] = (obpc - mean) / std
        else:
            vals = sims.get(cat, np.zeros(n_sims))
            z_arrays[cat] = (vals - mean) / std

    werth = sum(z_arrays[cat] for cat in HITTING_CATS)
    return werth, z_arrays


def sims_to_werth_pitcher(sims, zparams):
    """Convert simulated pitcher stat lines to WERTH."""
    from data_pipeline import PITCHING_CATS, LOWER_IS_BETTER

    n_sims = len(next(iter(sims.values())))
    z_arrays = {}

    for cat in PITCHING_CATS:
        mean = zparams[f"pit_z_{cat}_mean"]
        std = zparams[f"pit_z_{cat}_std"]

        if abs(std) < 1e-10:
            z_arrays[cat] = np.zeros(n_sims)
            continue

        if cat in ("ERA", "WHIP", "KBB"):
            ip = sims.get("IP", np.full(n_sims, 100))
            ip_share = ip / zparams["pit_total_ip"]
            stat_vals = sims.get(cat, np.zeros(n_sims))

            if cat == "ERA":
                league = zparams["pit_league_era"]
            elif cat == "WHIP":
                league = zparams["pit_league_whip"]
            else:  # KBB
                league = zparams["pit_league_kbb"]

            converted = (ip_share * stat_vals + (1 - ip_share) * league) - league
            z_arrays[cat] = (converted - mean) / std
        else:
            vals = sims.get(cat, np.zeros(n_sims))
            z_arrays[cat] = (vals - mean) / std

    werth = sum(z_arrays[cat] for cat in PITCHING_CATS)
    return werth, z_arrays


# ============================================================
# PHASE 6: Full pipeline
# ============================================================

def _compute_waiver_floor(hitters, pitchers, pos_replacement=None, pit_replacement=None):
    """
    Compute the waiver floor (w) for each position group using empirical
    data from 2022-2025 FanGraphs end-of-season actuals.

    Methodology: For each position, the floor is the total_werth of the
    Nth-best undrafted player, where N = 4 pickups × roster_slots.
    This reflects what caliber of player was ACTUALLY available on waivers
    in an 8-team league, not just what projections predict FAs will produce.

    The empirical total_werth values are converted to pos_adj_werth at
    runtime using the current season's replacement levels.

    See analysis/waiver_floor_report.md and model/waiver_floor_analysis.py
    for the full derivation.
    """
    # Empirical waiver floor constants: total_werth scale, 4-year average (2022-2025)
    # Derived from FanGraphs actuals × league draft history
    # Rank = 4 pickups/slot × slot_count (e.g., OF=5 slots → rank 20)
    EMPIRICAL_FLOORS_TW = {
        "C":  -5.29,  # rank 4  (1 slot × 4 pickups)
        "1B": -2.66,  # rank 4
        "2B": -3.62,  # rank 4
        "3B": -3.08,  # rank 4
        "SS": -3.09,  # rank 4
        "OF": -5.23,  # rank 20 (5 slots × 4 pickups)
        "SP": -1.62,  # rank 20 (5 slots × 4 pickups)
        "RP": -0.50,  # rank 16 (4 slots × 4 pickups)
    }

    # Convert total_werth → pos_adj_werth using current replacement levels
    # pos_adj_werth = |repl_level| + total_werth
    waiver_floors = {}

    for pos in ["C", "1B", "2B", "3B", "SS", "OF"]:
        repl = abs(pos_replacement.get(pos, 0)) if pos_replacement else 0
        waiver_floors[pos] = repl + EMPIRICAL_FLOORS_TW[pos]

    # Flex positions: best (highest) floor among eligible positions
    waiver_floors["MI"] = max(waiver_floors.get("2B", 0), waiver_floors.get("SS", 0))
    waiver_floors["CI"] = max(waiver_floors.get("1B", 0), waiver_floors.get("3B", 0))
    hitter_floor_vals = [waiver_floors[p] for p in ["C", "1B", "2B", "3B", "SS", "OF"]]
    waiver_floors["UTIL"] = max(hitter_floor_vals) if hitter_floor_vals else 0

    pit_repl = abs(pit_replacement) if pit_replacement else 0
    for pt in ["SP", "RP"]:
        waiver_floors[pt] = pit_repl + EMPIRICAL_FLOORS_TW[pt]
    waiver_floors["P"] = min(waiver_floors.get("SP", 0), waiver_floors.get("RP", 0))

    print("\nWaiver floors by position (empirical, 2022-2025):")
    for pos, val in sorted(waiver_floors.items()):
        print(f"  {pos}: {val:.2f}")
    return waiver_floors


def run_correlated_uncertainty(hitters_df, pitchers_df, pos_replacement, pit_replacement):
    """
    Full correlated uncertainty pipeline. Replaces run_risk_adjustment().

    Args:
        hitters_df, pitchers_df: DataFrames from run_valuation() (with z-scores, WERTH, etc.)
        pos_replacement: dict of replacement levels
        pit_replacement: float

    Returns:
        hitters_df, pitchers_df with risk-adjusted columns
        metadata dict with correlation matrices, diagnostics, etc.
    """
    print("\n" + "=" * 60)
    print("CORRELATED UNCERTAINTY MODEL")
    print("=" * 60)

    np.random.seed(42)  # Reproducibility

    # Step 1: Load projection systems
    print("\n--- Loading projection systems ---")
    bat_systems = load_batter_systems()
    pit_systems = load_pitcher_systems()
    print(f"  Loaded {len(bat_systems)} batter systems, {len(pit_systems)} pitcher systems")

    # Step 2: Compute cross-system residuals
    print("\n--- Computing cross-system residuals ---")
    bat_resids, bat_consensus, bat_sigmas = compute_cross_system_residuals(
        bat_systems, HITTING_CATS_EXT, min_systems=3)
    pit_resids, pit_consensus, pit_sigmas = compute_cross_system_residuals(
        pit_systems, PITCHING_CATS_EXT, min_systems=3)
    print(f"  Batters: {len(bat_consensus)} players with >=3 systems, "
          f"{len(bat_resids)} total residual observations")
    print(f"  Pitchers: {len(pit_consensus)} players with >=3 systems, "
          f"{len(pit_resids)} total residual observations")

    # Step 3: Correlation matrices
    print("\n--- Computing correlation matrices ---")
    bat_corr, bat_cov = compute_correlation_matrix(bat_resids, HITTING_CATS_EXT)
    pit_corr, pit_cov = compute_correlation_matrix(pit_resids, PITCHING_CATS_EXT)
    print("\nBatter category correlations (includes PA):")
    print(bat_corr.to_string(float_format=lambda x: f"{x:.3f}"))
    print("\nPitcher category correlations (includes IP):")
    print(pit_corr.to_string(float_format=lambda x: f"{x:.3f}"))

    # Step 4: Variance profiles
    print("\n--- Building variance profiles ---")
    bat_profiles = build_player_variance_profile(
        bat_consensus, bat_systems, HITTING_CATS_EXT, "batter")
    pit_profiles = build_player_variance_profile(
        pit_consensus, pit_systems, PITCHING_CATS_EXT, "pitcher")
    bat_profiles = apply_variance_scaling(bat_profiles, HITTING_CATS_EXT, "batter")
    pit_profiles = apply_variance_scaling(pit_profiles, PITCHING_CATS_EXT, "pitcher")
    print(f"  Batter profiles: {len(bat_profiles)}")
    print(f"  Pitcher profiles: {len(pit_profiles)}")

    # Step 5: Cholesky factors
    print("\n--- Building Cholesky factors ---")
    bat_L, bat_sim_cats = build_cholesky_factor(bat_corr, HITTING_CATS_EXT)
    pit_L, pit_sim_cats = build_cholesky_factor(pit_corr, PITCHING_CATS_EXT)
    print(f"  Batter sim dimensions: {bat_sim_cats}")
    print(f"  Pitcher sim dimensions: {pit_sim_cats}")

    # Step 6: Precompute z-score parameters
    print("\n--- Precomputing z-score parameters ---")
    zparams = precompute_zscore_params(hitters_df, pitchers_df)

    # Step 7: Waiver floors (empirical, from 2022-2025 actuals)
    waiver_floors = _compute_waiver_floor(hitters_df, pitchers_df, pos_replacement, pit_replacement)

    # Step 8: Monte Carlo simulation for each player
    print(f"\n--- Running {N_SIMS} Monte Carlo simulations per player ---")

    # --- HITTERS ---
    hitters_out = hitters_df.copy()
    hitters_out["werth_mean_sim"] = np.nan
    hitters_out["werth_std_sim"] = np.nan
    hitters_out["werth_q10_sim"] = np.nan
    hitters_out["werth_q90_sim"] = np.nan
    hitters_out["risk_adj_werth_mc"] = np.nan
    hitters_out["draft_value_mc"] = np.nan
    hitters_out["werth_skew_sim"] = np.nan

    bat_profile_lookup = {}
    for _, p in bat_profiles.iterrows():
        bat_profile_lookup[int(p["mlbam_id"])] = p

    n_simulated_h = 0
    for idx in hitters_out.index:
        mid = hitters_out.loc[idx, "mlbam_id"]
        if pd.isna(mid):
            continue
        mid = int(mid)
        profile = bat_profile_lookup.get(mid)
        if profile is None:
            continue

        # Build consensus and sigma dicts
        consensus = {}
        sigmas = {}
        for cat in bat_sim_cats:
            cons_val = profile.get(f"{cat}_consensus")
            sig_val = profile.get(f"{cat}_sigma")
            if pd.notna(cons_val):
                consensus[cat] = cons_val
            else:
                # Fall back to the player's actual projection data
                if cat in hitters_out.columns:
                    consensus[cat] = hitters_out.loc[idx, cat] if pd.notna(hitters_out.loc[idx, cat]) else 0
                else:
                    consensus[cat] = 0
            sigmas[cat] = sig_val if pd.notna(sig_val) else 0

        # Simulate
        sims = simulate_player_outcomes(consensus, sigmas, bat_L, bat_sim_cats, N_SIMS)

        # Convert to WERTH
        werth_sims, z_sims = sims_to_werth_hitter(sims, zparams)

        # Position adjustment (add replacement level like in valuation_engine)
        pos = hitters_out.loc[idx, "primary_position"]
        repl = pos_replacement.get(pos, 0)
        raw_adj_sims = abs(repl) + werth_sims
        if hitters_out.loc[idx].get("is_multi_position", False):
            raw_adj_sims += 0.5

        # RE-CENTER: anchor perturbations to the original pos_adj_werth
        # The simulation mean may differ from pos_adj_werth because it uses
        # multi-system consensus rather than ATC alone. We preserve the original
        # point estimate and use the simulation only for the distribution SHAPE.
        original_werth = hitters_out.loc[idx, "pos_adj_werth"]
        sim_center = raw_adj_sims.mean()
        adj_werth_sims = raw_adj_sims - sim_center + original_werth

        # Record the sigma (standard deviation of WERTH across simulations)
        werth_sigma = adj_werth_sims.std()

        # Waiver floor truncation
        w = waiver_floors.get(pos, 0)
        truncated_sims = np.maximum(adj_werth_sims, w)

        hitters_out.loc[idx, "werth_mean_sim"] = original_werth
        hitters_out.loc[idx, "werth_std_sim"] = werth_sigma
        hitters_out.loc[idx, "werth_q10_sim"] = np.percentile(adj_werth_sims, 10)
        hitters_out.loc[idx, "werth_q90_sim"] = np.percentile(adj_werth_sims, 90)
        hitters_out.loc[idx, "risk_adj_werth_mc"] = truncated_sims.mean()
        hitters_out.loc[idx, "waiver_floor"] = w
        hitters_out.loc[idx, "draft_value_mc"] = truncated_sims.mean() - w

        # Skewness: positive = more upside than downside (good for late picks)
        hitters_out.loc[idx, "werth_skew_sim"] = _skewness(adj_werth_sims)

        # Per-category z-score volatilities
        for cat in HITTING_CATS:
            if cat in z_sims:
                hitters_out.loc[idx, f"z_{cat}_std"] = z_sims[cat].std()

        n_simulated_h += 1

    print(f"  Simulated {n_simulated_h} hitters")

    # --- PITCHERS ---
    pitchers_out = pitchers_df.copy()
    pitchers_out["werth_mean_sim"] = np.nan
    pitchers_out["werth_std_sim"] = np.nan
    pitchers_out["werth_q10_sim"] = np.nan
    pitchers_out["werth_q90_sim"] = np.nan
    pitchers_out["risk_adj_werth_mc"] = np.nan
    pitchers_out["draft_value_mc"] = np.nan
    pitchers_out["werth_skew_sim"] = np.nan

    pit_profile_lookup = {}
    for _, p in pit_profiles.iterrows():
        pit_profile_lookup[int(p["mlbam_id"])] = p

    n_simulated_p = 0
    for idx in pitchers_out.index:
        mid = pitchers_out.loc[idx, "mlbam_id"]
        if pd.isna(mid):
            continue
        mid = int(mid)
        profile = pit_profile_lookup.get(mid)
        if profile is None:
            continue

        consensus = {}
        sigmas = {}
        for cat in pit_sim_cats:
            cons_val = profile.get(f"{cat}_consensus")
            sig_val = profile.get(f"{cat}_sigma")
            if pd.notna(cons_val):
                consensus[cat] = cons_val
            else:
                if cat in pitchers_out.columns:
                    consensus[cat] = pitchers_out.loc[idx, cat] if pd.notna(pitchers_out.loc[idx, cat]) else 0
                else:
                    consensus[cat] = 0
            sigmas[cat] = sig_val if pd.notna(sig_val) else 0

        sims = simulate_player_outcomes(consensus, sigmas, pit_L, pit_sim_cats, N_SIMS)
        werth_sims, z_sims = sims_to_werth_pitcher(sims, zparams)

        # Position adjustment
        raw_adj_sims = abs(pit_replacement) + werth_sims

        # RE-CENTER on original pos_adj_werth
        original_werth = pitchers_out.loc[idx, "pos_adj_werth"]
        sim_center = raw_adj_sims.mean()
        adj_werth_sims = raw_adj_sims - sim_center + original_werth
        werth_sigma = adj_werth_sims.std()

        pt = pitchers_out.loc[idx].get("pitcher_type", "SP")
        w = waiver_floors.get(pt, waiver_floors.get("P", 0))
        truncated_sims = np.maximum(adj_werth_sims, w)

        pitchers_out.loc[idx, "werth_mean_sim"] = original_werth
        pitchers_out.loc[idx, "werth_std_sim"] = werth_sigma
        pitchers_out.loc[idx, "werth_q10_sim"] = np.percentile(adj_werth_sims, 10)
        pitchers_out.loc[idx, "werth_q90_sim"] = np.percentile(adj_werth_sims, 90)
        pitchers_out.loc[idx, "risk_adj_werth_mc"] = truncated_sims.mean()
        pitchers_out.loc[idx, "waiver_floor"] = w
        pitchers_out.loc[idx, "draft_value_mc"] = truncated_sims.mean() - w

        pitchers_out.loc[idx, "werth_skew_sim"] = _skewness(adj_werth_sims)

        for cat in PITCHING_CATS:
            if cat in z_sims:
                pitchers_out.loc[idx, f"z_{cat}_std"] = z_sims[cat].std()

        n_simulated_p += 1

    print(f"  Simulated {n_simulated_p} pitchers")

    # Fill unsimulated players with old model fallback
    _fallback_unsimulated(hitters_out, pitchers_out, waiver_floors, pos_replacement, pit_replacement)

    # Summary
    _print_summary(hitters_out, pitchers_out)

    metadata = {
        "bat_corr": bat_corr,
        "pit_corr": pit_corr,
        "bat_profiles": bat_profiles,
        "pit_profiles": pit_profiles,
        "waiver_floors": waiver_floors,
        "zparams": zparams,
        "n_sims": N_SIMS,
    }

    return hitters_out, pitchers_out, metadata


def _fallback_unsimulated(hitters, pitchers, waiver_floors, pos_replacement, pit_replacement):
    """For players not in enough systems for MC, use simple normal approximation."""
    # Hitters without MC results
    h_missing = hitters["risk_adj_werth_mc"].isna()
    if h_missing.any():
        print(f"\n  Fallback: {h_missing.sum()} hitters without MC simulation")
        for idx in hitters[h_missing].index:
            mu = hitters.loc[idx, "pos_adj_werth"]
            sigma = hitters.loc[idx].get("werth_sigma", 0.5)
            if pd.isna(sigma) or sigma <= 0:
                sigma = 0.5
            pos = hitters.loc[idx, "primary_position"]
            w = waiver_floors.get(pos, 0)

            # Simple truncated normal
            if sigma > 0:
                z = (mu - w) / sigma
                risk_adj = mu * _norm_cdf(z) + sigma * _norm_pdf(z) + w * _norm_cdf(-z)
            else:
                risk_adj = max(mu, w)

            hitters.loc[idx, "risk_adj_werth_mc"] = risk_adj
            hitters.loc[idx, "waiver_floor"] = w
            hitters.loc[idx, "draft_value_mc"] = risk_adj - w
            hitters.loc[idx, "werth_mean_sim"] = mu
            hitters.loc[idx, "werth_std_sim"] = sigma

    # Pitchers without MC results
    p_missing = pitchers["risk_adj_werth_mc"].isna()
    if p_missing.any():
        print(f"  Fallback: {p_missing.sum()} pitchers without MC simulation")
        for idx in pitchers[p_missing].index:
            mu = pitchers.loc[idx, "pos_adj_werth"]
            sigma = pitchers.loc[idx].get("werth_sigma", 0.5)
            if pd.isna(sigma) or sigma <= 0:
                sigma = 0.5
            pt = pitchers.loc[idx].get("pitcher_type", "SP")
            w = waiver_floors.get(pt, waiver_floors.get("P", 0))

            if sigma > 0:
                z = (mu - w) / sigma
                risk_adj = mu * _norm_cdf(z) + sigma * _norm_pdf(z) + w * _norm_cdf(-z)
            else:
                risk_adj = max(mu, w)

            pitchers.loc[idx, "risk_adj_werth_mc"] = risk_adj
            pitchers.loc[idx, "waiver_floor"] = w
            pitchers.loc[idx, "draft_value_mc"] = risk_adj - w
            pitchers.loc[idx, "werth_mean_sim"] = mu
            pitchers.loc[idx, "werth_std_sim"] = sigma


def _print_summary(hitters, pitchers):
    """Print summary statistics."""
    print("\n" + "=" * 60)
    print("CORRELATED UNCERTAINTY MODEL — SUMMARY")
    print("=" * 60)

    h_sim = hitters[hitters["werth_std_sim"].notna() & (hitters["werth_std_sim"] > 0)]
    p_sim = pitchers[pitchers["werth_std_sim"].notna() & (pitchers["werth_std_sim"] > 0)]

    print(f"\nHitters with MC simulation: {len(h_sim)}")
    print(f"  Mean WERTH std: {h_sim['werth_std_sim'].mean():.3f}")
    print(f"  Mean risk adjustment: {(h_sim['risk_adj_werth_mc'] - h_sim['pos_adj_werth']).mean():.3f}")

    print(f"\nPitchers with MC simulation: {len(p_sim)}")
    print(f"  Mean WERTH std: {p_sim['werth_std_sim'].mean():.3f}")
    print(f"  Mean risk adjustment: {(p_sim['risk_adj_werth_mc'] - p_sim['pos_adj_werth']).mean():.3f}")

    # Top beneficiaries of variance (option value)
    h_sim["_adj_delta"] = h_sim["risk_adj_werth_mc"] - h_sim["pos_adj_werth"]
    top_h = h_sim.nlargest(10, "_adj_delta")[
        ["name", "primary_position", "pos_adj_werth", "risk_adj_werth_mc",
         "werth_std_sim", "draft_value_mc"]
    ]
    print("\nTop 10 hitter beneficiaries of variance (option value):")
    print(top_h.to_string(float_format=lambda x: f"{x:.2f}"))

    p_sim["_adj_delta"] = p_sim["risk_adj_werth_mc"] - p_sim["pos_adj_werth"]
    top_p = p_sim.nlargest(10, "_adj_delta")[
        ["name", "pos_adj_werth", "risk_adj_werth_mc",
         "werth_std_sim", "draft_value_mc"]
    ]
    print("\nTop 10 pitcher beneficiaries of variance:")
    print(top_p.to_string(float_format=lambda x: f"{x:.2f}"))

    # Biggest losers (high-ranked players penalized by risk)
    h_sim["_adj_delta2"] = h_sim["risk_adj_werth_mc"] - h_sim["pos_adj_werth"]
    worst_h = h_sim.nsmallest(10, "_adj_delta2")[
        ["name", "primary_position", "pos_adj_werth", "risk_adj_werth_mc",
         "werth_std_sim", "draft_value_mc"]
    ]
    print("\nTop 10 hitters penalized by risk (negative adjustment):")
    print(worst_h.to_string(float_format=lambda x: f"{x:.2f}"))


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from valuation_engine import run_valuation

    print("Running valuation engine...")
    hitters, pitchers, pos_repl, pit_repl = run_valuation()

    print("\nRunning correlated uncertainty model...")
    hitters, pitchers, metadata = run_correlated_uncertainty(
        hitters, pitchers, pos_repl, pit_repl)

    # Save outputs
    out_dir = ROOT / "model" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    h_cols = ["name", "mlbam_id", "espn_id", "primary_position", "PA",
              "pos_adj_werth", "werth_mean_sim", "werth_std_sim",
              "werth_q10_sim", "werth_q90_sim", "werth_skew_sim",
              "risk_adj_werth_mc", "waiver_floor", "draft_value_mc"]
    h_cols = [c for c in h_cols if c in hitters.columns]
    hitters[h_cols].sort_values("risk_adj_werth_mc", ascending=False).to_csv(
        out_dir / "hitter_uncertainty.csv", index=False)

    p_cols = ["name", "mlbam_id", "espn_id", "pitcher_type", "IP",
              "pos_adj_werth", "werth_mean_sim", "werth_std_sim",
              "werth_q10_sim", "werth_q90_sim", "werth_skew_sim",
              "risk_adj_werth_mc", "waiver_floor", "draft_value_mc"]
    p_cols = [c for c in p_cols if c in pitchers.columns]
    pitchers[p_cols].sort_values("risk_adj_werth_mc", ascending=False).to_csv(
        out_dir / "pitcher_uncertainty.csv", index=False)

    # Save correlation matrices
    metadata["bat_corr"].to_csv(out_dir / "batter_correlation_matrix.csv")
    metadata["pit_corr"].to_csv(out_dir / "pitcher_correlation_matrix.csv")

    print(f"\nOutputs saved to {out_dir}/")
