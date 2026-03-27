"""
Empirical Injury/Games-Missed Model

This module builds an injury risk model using cross-system projection disagreement.

Key insight: The gap between a player's FULL-SEASON projection (Steamer600 = 600 PA baseline)
and their REALISTIC projection (regular Steamer, ATC, etc.) implicitly encodes injury/PT risk.
Cross-system disagreement on PA/IP tells us how uncertain that risk is.

Model outputs:
  - games_missed_estimate: Estimate of games a player will miss due to injury/availability
  - pa_disagreement (batters) / ip_disagreement (pitchers): Uncertainty in the estimate
  - injury_risk_tier: LOW / MODERATE / HIGH / VERY_HIGH based on quartiles
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings

warnings.filterwarnings('ignore')

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_ROOT = PROJECT_ROOT / 'existing-tools'
OUTPUT_ROOT = Path(__file__).parent / 'output'
OUTPUT_ROOT.mkdir(exist_ok=True)


def load_projection_csvs() -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame]]:
    """Load all projection CSVs for batters and pitchers."""

    batter_files = {
        'Steamer600': 'FanGraphs_Steamer600_Batters_2026.csv',
        'Steamer': 'FanGraphs_Steamer_Batters_2026.csv',
        'ATC': 'FanGraphs_ATC_Batters_2026.csv',
        'ZiPS': 'FanGraphs_ZiPS_Batters_2026.csv',
        'DepthCharts': 'FanGraphs_DepthCharts_Batters_2026.csv',
        'TheBatX': 'FanGraphs_TheBatX_Batters_2026.csv',
        'OOPSY': 'FanGraphs_OOPSY_Batters_2026.csv',
        'OOPSYPeak': 'FanGraphs_OOPSYPeak_Batters_2026.csv',
    }

    pitcher_files = {
        'Steamer600': 'FanGraphs_Steamer600_Pitchers_2026.csv',
        'Steamer': 'FanGraphs_Steamer_Pitchers_2026.csv',
        'ATC': 'FanGraphs_ATC_Pitchers_2026.csv',
        'ZiPS': 'FanGraphs_ZiPS_Pitchers_2026.csv',
        'DepthCharts': 'FanGraphs_DepthCharts_Pitchers_2026.csv',
        'TheBatX': 'FanGraphs_TheBatX_Pitchers_2026.csv',
        'OOPSY': 'FanGraphs_OOPSY_Pitchers_2026.csv',
        'OOPSYPeak': 'FanGraphs_OOPSYPeak_Pitchers_2026.csv',
    }

    batters = {}
    pitchers = {}

    for name, fname in batter_files.items():
        fpath = DATA_ROOT / fname
        if fpath.exists():
            df = pd.read_csv(fpath)
            # Identify join key: use xMLBAMID, except TheBatX uses MLBAMID
            if name == 'TheBatX' and 'MLBAMID' in df.columns:
                df = df.rename(columns={'MLBAMID': 'xMLBAMID'})
            batters[name] = df
            print(f"Loaded {name} batters: {len(df)} rows")
        else:
            print(f"Warning: {fname} not found")

    for name, fname in pitcher_files.items():
        fpath = DATA_ROOT / fname
        if fpath.exists():
            df = pd.read_csv(fpath)
            if name == 'TheBatX' and 'MLBAMID' in df.columns:
                df = df.rename(columns={'MLBAMID': 'xMLBAMID'})
            pitchers[name] = df
            print(f"Loaded {name} pitchers: {len(df)} rows")
        else:
            print(f"Warning: {fname} not found")

    return batters, pitchers


def build_batter_injury_estimates(batters: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build injury estimates for batters.

    For each player:
      - pa_projected: mean PA across realistic systems (Steamer, ATC, ZiPS, DepthCharts, TheBatX, OOPSY, OOPSYPeak)
      - pa_fullseason: Steamer600 PA
      - games_missed_estimate: (1 - pa_projected/pa_fullseason) * 162, clamped to [0, 162]
      - pa_disagreement: std dev of PA across systems
    """

    if 'Steamer600' not in batters:
        print("ERROR: Steamer600 batters not loaded")
        return pd.DataFrame()

    # Start with Steamer600 as baseline
    # Use minpos for position (actual position string), G for games (can infer age trends)
    result = batters['Steamer600'][['xMLBAMID', 'PlayerName', 'minpos', 'PA', 'G']].copy()
    result.columns = ['xMLBAMID', 'PlayerName', 'Pos', 'pa_fullseason', 'G']

    # Gather PA from realistic systems
    realistic_systems = ['Steamer', 'ATC', 'ZiPS', 'DepthCharts', 'TheBatX', 'OOPSY', 'OOPSYPeak']
    pa_data = {}

    for system in realistic_systems:
        if system in batters:
            df = batters[system][['xMLBAMID', 'PA']].copy()
            df.columns = ['xMLBAMID', f'PA_{system}']
            pa_data[system] = df

    # Merge all PA columns
    for system, df in pa_data.items():
        result = result.merge(df, on='xMLBAMID', how='left')

    # Compute pa_projected as mean of realistic systems
    pa_cols = [f'PA_{s}' for s in realistic_systems if s in pa_data]
    result['pa_projected'] = result[pa_cols].mean(axis=1)

    # Compute pa_disagreement as std dev across realistic systems
    result['pa_disagreement'] = result[pa_cols].std(axis=1, ddof=1)

    # Clamp pa_projected to reasonable bounds
    result['pa_projected'] = result['pa_projected'].clip(lower=0, upper=720)

    # Use a realistic full-season PA benchmark rather than Steamer600's 600:
    # A healthy everyday position player gets ~680 PA (162 games × ~4.2 PA/game).
    # Catchers get less (~550). DH/UTIL ~650.
    # Steamer600 uses 600 as a round number, but that UNDERSTATES a full season.
    FULL_SEASON_PA = 680  # non-catcher everyday player benchmark
    FULL_SEASON_PA_C = 550  # catcher benchmark

    is_catcher = result['Pos'].fillna('').str.match(r'^C($|/)', case=False)
    pa_benchmark = np.where(is_catcher, FULL_SEASON_PA_C, FULL_SEASON_PA)

    # Games missed = (1 - pa_projected / pa_benchmark) * 162
    result['games_missed_estimate'] = np.where(
        pa_benchmark > 0,
        (1 - result['pa_projected'] / pa_benchmark) * 162,
        0
    )
    result['games_missed_estimate'] = result['games_missed_estimate'].clip(lower=0, upper=162)

    # Irreducible injury floor: even "healthy" players have baseline injury risk.
    # MLB average: ~15 games missed per season due to minor injuries.
    # This scales up for older players and catchers.
    # Use cross-system PA disagreement as a proxy for injury uncertainty:
    # high disagreement = systems aren't sure about health = higher floor.
    pa_disag_pctile = result['pa_disagreement'].rank(pct=True)
    base_floor = 8  # minimum expected games missed for any MLB regular
    disag_bonus = pa_disag_pctile * 10  # up to 10 extra games for high disagreement
    result['games_missed_estimate'] = result['games_missed_estimate'].clip(
        lower=base_floor + disag_bonus)

    # We don't have explicit age in FanGraphs, so we'll use NaN for now
    # (Could be enhanced with external player ID data)
    result['Age'] = np.nan

    # Clean up intermediate columns
    result = result[['xMLBAMID', 'PlayerName', 'Pos', 'Age', 'pa_projected',
                     'pa_fullseason', 'games_missed_estimate', 'pa_disagreement']]

    return result.dropna(subset=['xMLBAMID', 'PlayerName'])


def build_pitcher_injury_estimates(pitchers: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build injury estimates for pitchers.

    For each pitcher:
      - ip_projected: mean IP across realistic systems
      - ip_fullseason: Steamer600 IP
      - games_missed_estimate: (1 - ip_projected/ip_fullseason) * 33, clamped to [0, 33]
        (assuming ~33 starts per season)
      - ip_disagreement: std dev of IP across systems
    """

    if 'Steamer600' not in pitchers:
        print("ERROR: Steamer600 pitchers not loaded")
        return pd.DataFrame()

    # Start with Steamer600 as baseline
    result = pitchers['Steamer600'][['xMLBAMID', 'PlayerName', 'IP']].copy()
    result.columns = ['xMLBAMID', 'PlayerName', 'ip_fullseason']

    # Gather IP from realistic systems
    realistic_systems = ['Steamer', 'ATC', 'ZiPS', 'DepthCharts', 'TheBatX', 'OOPSY', 'OOPSYPeak']
    ip_data = {}

    for system in realistic_systems:
        if system in pitchers:
            df = pitchers[system][['xMLBAMID', 'IP']].copy()
            df.columns = ['xMLBAMID', f'IP_{system}']
            ip_data[system] = df

    # Merge all IP columns
    for system, df in ip_data.items():
        result = result.merge(df, on='xMLBAMID', how='left')

    # Compute ip_projected as mean of realistic systems
    ip_cols = [f'IP_{s}' for s in realistic_systems if s in ip_data]
    result['ip_projected'] = result[ip_cols].mean(axis=1)

    # Compute ip_disagreement as std dev across realistic systems
    result['ip_disagreement'] = result[ip_cols].std(axis=1, ddof=1)

    # Clamp ip_projected to reasonable bounds
    result['ip_projected'] = result['ip_projected'].clip(lower=0, upper=240)

    # Realistic full-season IP benchmark:
    # An ace SP pitches ~200 IP (33 starts × 6 IP/start).
    # Steamer600 uses 200 IP, which is about right for SP.
    # For RP, a full season is ~65 IP.
    FULL_SEASON_IP_SP = 200
    FULL_SEASON_IP_RP = 65

    # Classify SP vs RP by Steamer600 IP: > 100 IP = SP
    is_sp = result['ip_fullseason'] > 100
    ip_benchmark = np.where(is_sp, FULL_SEASON_IP_SP, FULL_SEASON_IP_RP)

    # Games (starts) missed for SP; appearances missed for RP
    # Normalize to "games missed" on a 162-game scale for consistency with batters
    result['games_missed_estimate'] = np.where(
        ip_benchmark > 0,
        (1 - result['ip_projected'] / ip_benchmark) * 162,
        0
    )
    result['games_missed_estimate'] = result['games_missed_estimate'].clip(lower=0, upper=162)

    # Irreducible floor: even healthy pitchers miss some time
    ip_disag_pctile = result['ip_disagreement'].rank(pct=True)
    base_floor = 10  # pitchers have higher baseline injury risk than position players
    disag_bonus = ip_disag_pctile * 12
    result['games_missed_estimate'] = result['games_missed_estimate'].clip(
        lower=base_floor + disag_bonus)

    # We don't have explicit age in FanGraphs, so we'll use NaN for now
    result['Age'] = np.nan

    # Clean up intermediate columns
    result = result[['xMLBAMID', 'PlayerName', 'Age', 'ip_projected',
                     'ip_fullseason', 'games_missed_estimate', 'ip_disagreement']]

    return result.dropna(subset=['xMLBAMID', 'PlayerName'])


def assign_injury_risk_tiers(df: pd.DataFrame, games_col: str = 'games_missed_estimate') -> pd.DataFrame:
    """Assign injury risk tier (LOW/MODERATE/HIGH/VERY_HIGH) based on quartiles."""

    if games_col not in df.columns or len(df) == 0:
        return df

    # Compute quartiles
    q1, q2, q3 = df[games_col].quantile([0.25, 0.50, 0.75])

    def assign_tier(val):
        if pd.isna(val):
            return 'UNKNOWN'
        elif val <= q1:
            return 'LOW'
        elif val <= q2:
            return 'MODERATE'
        elif val <= q3:
            return 'HIGH'
        else:
            return 'VERY_HIGH'

    df['injury_risk_tier'] = df[games_col].apply(assign_tier)
    return df


def compute_age_risk_factors(batters: pd.DataFrame, pitchers: pd.DataFrame) -> Dict:
    """Compute mean games_missed by age bucket and position."""

    factors = {
        'by_age_batters': {},
        'by_age_pitchers': {},
        'by_position': {},
    }

    # Age buckets for batters
    if not batters.empty and 'Age' in batters.columns:
        age_buckets = [(21, 25), (26, 29), (30, 33), (34, 50)]
        for low, high in age_buckets:
            mask = (batters['Age'] >= low) & (batters['Age'] <= high)
            subset = batters[mask]
            if len(subset) > 0:
                factors['by_age_batters'][f'{low}-{high}'] = {
                    'mean_games_missed': subset['games_missed_estimate'].mean(),
                    'count': len(subset),
                }

    # Age buckets for pitchers
    if not pitchers.empty and 'Age' in pitchers.columns:
        age_buckets = [(21, 25), (26, 29), (30, 33), (34, 50)]
        for low, high in age_buckets:
            mask = (pitchers['Age'] >= low) & (pitchers['Age'] <= high)
            subset = pitchers[mask]
            if len(subset) > 0:
                factors['by_age_pitchers'][f'{low}-{high}'] = {
                    'mean_games_missed': subset['games_missed_estimate'].mean(),
                    'count': len(subset),
                }

    # By position (batters only, since pitchers don't have position info typically)
    if not batters.empty and 'Pos' in batters.columns:
        positions = batters['Pos'].unique()
        for pos in positions:
            if pd.notna(pos):
                subset = batters[batters['Pos'] == pos]
                if len(subset) > 0:
                    factors['by_position'][str(pos)] = {
                        'mean_games_missed': subset['games_missed_estimate'].mean(),
                        'count': len(subset),
                    }

    return factors


def load_injury_estimates() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load the combined injury estimates for batters and pitchers."""

    batter_path = OUTPUT_ROOT / 'injury_risk_batters.csv'
    pitcher_path = OUTPUT_ROOT / 'injury_risk_pitchers.csv'

    batters = pd.read_csv(batter_path) if batter_path.exists() else pd.DataFrame()
    pitchers = pd.read_csv(pitcher_path) if pitcher_path.exists() else pd.DataFrame()

    return batters, pitchers


def get_injury_risk(mlbam_id: int, is_pitcher: bool = False) -> Optional[Dict]:
    """Get injury risk info for a single player."""

    batters, pitchers = load_injury_estimates()

    if is_pitcher:
        match = pitchers[pitchers['mlbam_id'] == mlbam_id]
    else:
        match = batters[batters['mlbam_id'] == mlbam_id]

    if match.empty:
        return None

    row = match.iloc[0]
    return {
        'mlbam_id': int(row['mlbam_id']),
        'name': row['name'],
        'games_missed_estimate': float(row['games_missed_estimate']),
        'disagreement': float(row.get('pa_disagreement', row.get('ip_disagreement', 0))),
        'injury_risk_tier': row['injury_risk_tier'],
        'age': row.get('age', None),
    }


def main():
    """Build and export injury risk model."""

    print("=" * 80)
    print("EMPIRICAL INJURY/GAMES-MISSED MODEL")
    print("=" * 80)
    print()

    # Load projections
    print("Loading projection CSVs...")
    batters_dict, pitchers_dict = load_projection_csvs()
    print()

    # Build estimates
    print("Building batter injury estimates...")
    batters_df = build_batter_injury_estimates(batters_dict)
    print(f"  {len(batters_df)} batters with estimates")
    print()

    print("Building pitcher injury estimates...")
    pitchers_df = build_pitcher_injury_estimates(pitchers_dict)
    print(f"  {len(pitchers_df)} pitchers with estimates")
    print()

    # Assign risk tiers
    print("Assigning injury risk tiers...")
    batters_df = assign_injury_risk_tiers(batters_df, 'games_missed_estimate')
    pitchers_df = assign_injury_risk_tiers(pitchers_df, 'games_missed_estimate')
    print()

    # Compute risk factors
    print("Computing age and position risk factors...")
    risk_factors = compute_age_risk_factors(batters_df, pitchers_df)
    print()

    if risk_factors['by_age_batters']:
        print("AGE-BASED RISK FACTORS (Batters):")
        for age_bucket, stats in risk_factors['by_age_batters'].items():
            print(f"  Age {age_bucket}: mean_games_missed={stats['mean_games_missed']:.2f}, n={stats['count']}")
        print()

    if risk_factors['by_age_pitchers']:
        print("AGE-BASED RISK FACTORS (Pitchers):")
        for age_bucket, stats in risk_factors['by_age_pitchers'].items():
            print(f"  Age {age_bucket}: mean_games_missed={stats['mean_games_missed']:.2f}, n={stats['count']}")
        print()

    print("POSITION-BASED RISK FACTORS (Batters):")
    for pos, stats in sorted(risk_factors['by_position'].items()):
        print(f"  {pos}: mean_games_missed={stats['mean_games_missed']:.2f}, n={stats['count']}")
    print()

    # Summary statistics
    print("SUMMARY STATISTICS (Batters):")
    print(f"  Total: {len(batters_df)}")
    print(f"  Games missed (mean): {batters_df['games_missed_estimate'].mean():.2f}")
    print(f"  Games missed (std): {batters_df['games_missed_estimate'].std():.2f}")
    print(f"  Games missed (min): {batters_df['games_missed_estimate'].min():.2f}")
    print(f"  Games missed (max): {batters_df['games_missed_estimate'].max():.2f}")
    print()

    print("  PA Disagreement (mean): {:.2f}".format(batters_df['pa_disagreement'].mean()))
    print("  PA Disagreement (std): {:.2f}".format(batters_df['pa_disagreement'].std()))
    print()

    print("Risk Tier Distribution (Batters):")
    for tier in ['LOW', 'MODERATE', 'HIGH', 'VERY_HIGH']:
        count = (batters_df['injury_risk_tier'] == tier).sum()
        pct = 100 * count / len(batters_df)
        print(f"  {tier}: {count} ({pct:.1f}%)")
    print()

    print("SUMMARY STATISTICS (Pitchers):")
    print(f"  Total: {len(pitchers_df)}")
    print(f"  Games missed (mean): {pitchers_df['games_missed_estimate'].mean():.2f}")
    print(f"  Games missed (std): {pitchers_df['games_missed_estimate'].std():.2f}")
    print(f"  Games missed (min): {pitchers_df['games_missed_estimate'].min():.2f}")
    print(f"  Games missed (max): {pitchers_df['games_missed_estimate'].max():.2f}")
    print()

    print("  IP Disagreement (mean): {:.2f}".format(pitchers_df['ip_disagreement'].mean()))
    print("  IP Disagreement (std): {:.2f}".format(pitchers_df['ip_disagreement'].std()))
    print()

    print("Risk Tier Distribution (Pitchers):")
    for tier in ['LOW', 'MODERATE', 'HIGH', 'VERY_HIGH']:
        count = (pitchers_df['injury_risk_tier'] == tier).sum()
        pct = 100 * count / len(pitchers_df)
        print(f"  {tier}: {count} ({pct:.1f}%)")
    print()

    # Sample high-risk players
    print("HIGH-RISK BATTERS (top 10 by games missed):")
    top_batters = batters_df.nlargest(10, 'games_missed_estimate')[
        ['PlayerName', 'Age', 'Pos', 'games_missed_estimate', 'pa_disagreement', 'injury_risk_tier']
    ]
    for idx, row in top_batters.iterrows():
        print(f"  {row['PlayerName']:<25} Age {row['Age']:.0f} {row['Pos']:<5} "
              f"miss={row['games_missed_estimate']:.1f} ± {row['pa_disagreement']:.1f} ({row['injury_risk_tier']})")
    print()

    print("HIGH-RISK PITCHERS (top 10 by starts missed):")
    top_pitchers = pitchers_df.nlargest(10, 'games_missed_estimate')[
        ['PlayerName', 'Age', 'games_missed_estimate', 'ip_disagreement', 'injury_risk_tier']
    ]
    for idx, row in top_pitchers.iterrows():
        print(f"  {row['PlayerName']:<25} Age {row['Age']:.0f} "
              f"miss={row['games_missed_estimate']:.1f} ± {row['ip_disagreement']:.1f} ({row['injury_risk_tier']})")
    print()

    # Export to CSV
    print("Exporting to CSV...")
    batter_export = batters_df[['xMLBAMID', 'PlayerName', 'Pos', 'Age', 'pa_projected',
                                  'pa_fullseason', 'games_missed_estimate', 'pa_disagreement',
                                  'injury_risk_tier']].copy()
    batter_export.columns = ['mlbam_id', 'name', 'position', 'age', 'pa_projected',
                              'pa_fullseason', 'games_missed_estimate', 'pa_disagreement',
                              'injury_risk_tier']
    batter_export.to_csv(OUTPUT_ROOT / 'injury_risk_batters.csv', index=False)
    print(f"  Saved: {OUTPUT_ROOT / 'injury_risk_batters.csv'}")

    pitcher_export = pitchers_df[['xMLBAMID', 'PlayerName', 'Age', 'ip_projected',
                                    'ip_fullseason', 'games_missed_estimate', 'ip_disagreement',
                                    'injury_risk_tier']].copy()
    pitcher_export.columns = ['mlbam_id', 'name', 'age', 'ip_projected',
                               'ip_fullseason', 'games_missed_estimate', 'ip_disagreement',
                               'injury_risk_tier']
    pitcher_export.to_csv(OUTPUT_ROOT / 'injury_risk_pitchers.csv', index=False)
    print(f"  Saved: {OUTPUT_ROOT / 'injury_risk_pitchers.csv'}")
    print()

    print("=" * 80)
    print("INJURY MODEL COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
