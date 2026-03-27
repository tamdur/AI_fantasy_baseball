"""
Current injury overrides as of 2026-03-24 (draft day).

These are late-breaking injuries from web sources that override or supplement
the projection-based injury model. The projection systems were built weeks ago
and don't reflect injuries that happened during spring training's final days.

Source: ESPN, CBS Sports, MLB.com injury reports (March 24, 2026)
"""

# Map player names → estimated games missed this season
# Only includes currently-injured players; healthy players default to 0.
CURRENT_INJURIES = {
    # PITCHERS — Major
    "Spencer Strider": 40,       # Braves — left oblique strain, 4-6 weeks
    "Josh Hader": 30,            # Astros — biceps tendinitis
    "Joe Musgrove": 45,          # Padres — TJ complication
    "Blake Snell": 20,           # Dodgers — left shoulder discomfort
    "Gavin Stone": 20,           # Dodgers — right shoulder discomfort
    "Shane Bieber": 15,          # Blue Jays — forearm fatigue (TJ recovery)
    "José Berríos": 30,          # Blue Jays — stress fracture right elbow
    "Nick Lodolo": 5,            # Reds — left index finger blister
    "Zack Wheeler": 10,          # Phillies — thoracic outlet recovery (sim game 3/23)
    "Hunter Greene": 60,         # Reds — elbow surgery (60-day IL)
    "Josiah Gray": 60,           # Nationals — flexor strain (60-day IL)
    "Beau Brieske": 60,          # Tigers — adductor strain (60-day IL)
    "Orion Kerkering": 15,       # Phillies — hamstring strain
    "Ryan Pepiot": 15,           # Rays — hip injury

    # PITCHERS — Season-ending
    "Mike Vasil": 162,           # White Sox — TJ surgery

    # POSITION PLAYERS — Major
    "Seiya Suzuki": 20,          # Cubs — right knee PCL sprain
    "Jackson Holliday": 35,      # Orioles — UCL tear, out through April
    "Jordan Westburg": 60,       # Orioles — partially torn UCL throwing elbow
    "Corbin Carroll": 30,        # Diamondbacks — hamate surgery
    "Francisco Lindor": 30,      # Mets — hamate surgery
    "Gavin Lux": 30,             # Dodgers — shoulder injury
    "Esteury Ruiz": 45,          # Marlins — oblique strain, 6-8 weeks
    "Lars Nootbaar": 15,         # Cardinals — heel recovery
    "Ketel Marte": 10,           # Diamondbacks — status unclear
    "Akil Baddoo": 60,           # Brewers — 60-day IL

    # POSITION PLAYERS — Season-ending
    "Mike Tauchman": 162,        # Mets — torn meniscus left knee
}


def get_current_games_missed(player_name: str) -> int:
    """Return current injury games-missed estimate, or 0 if healthy."""
    # Try exact match first
    if player_name in CURRENT_INJURIES:
        return CURRENT_INJURIES[player_name]
    # Try partial match (handles accent differences, Jr./Sr., etc.)
    name_lower = player_name.lower()
    for inj_name, games in CURRENT_INJURIES.items():
        if inj_name.lower() in name_lower or name_lower in inj_name.lower():
            return games
    return 0


def merge_injury_data(rankings_df):
    """
    Add injury columns to a rankings DataFrame.
    Combines projection-based injury risk with current injury overrides.

    Args:
        rankings_df: DataFrame with 'name' column

    Returns:
        DataFrame with added columns:
        - games_missed_proj: from projection-based model
        - games_missed_current: from current injury reports
        - games_missed_total: max of the two (don't double-count)
        - injury_note: text description if currently injured
    """
    import pandas as pd
    from pathlib import Path

    out_dir = Path(__file__).parent / "output"
    df = rankings_df.copy()

    # Load projection-based injury estimates
    try:
        bat_inj = pd.read_csv(out_dir / "injury_risk_batters.csv")
        pit_inj = pd.read_csv(out_dir / "injury_risk_pitchers.csv")
        inj = pd.concat([bat_inj, pit_inj], ignore_index=True)
        inj = inj.drop_duplicates(subset=["mlbam_id"], keep="first")
        # Merge on mlbam_id if available, else on name
        if "mlbam_id" in df.columns:
            inj_map = inj.set_index("mlbam_id")["games_missed_estimate"].to_dict()
            df["games_missed_proj"] = df["mlbam_id"].map(inj_map).fillna(0)
        else:
            inj_map = inj.set_index("name")["games_missed_estimate"].to_dict()
            df["games_missed_proj"] = df["name"].map(inj_map).fillna(0)
    except Exception:
        df["games_missed_proj"] = 0

    # Add current injuries
    df["games_missed_current"] = df["name"].apply(get_current_games_missed)

    # Total: use the MAXIMUM of projection-based and current
    # (don't add them — current injuries are already reflected in
    # the "missed games" concept; projection-based captures historical risk)
    df["games_missed_total"] = df[["games_missed_proj", "games_missed_current"]].max(axis=1)

    # Injury note for display
    df["injury_note"] = df["name"].apply(
        lambda n: f"IL ({CURRENT_INJURIES[n]}g)" if n in CURRENT_INJURIES
        else next((f"IL ({v}g)" for k, v in CURRENT_INJURIES.items()
                    if k.lower() in n.lower() or n.lower() in k.lower()), "")
    )

    return df


if __name__ == "__main__":
    print(f"Current injuries database: {len(CURRENT_INJURIES)} players")
    print()
    for name, games in sorted(CURRENT_INJURIES.items(), key=lambda x: -x[1]):
        print(f"  {name:25s}  {games:3d} games")
