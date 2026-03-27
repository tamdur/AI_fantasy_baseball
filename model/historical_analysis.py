#!/usr/bin/env python3
"""
Historical league analysis for ESPN H2H Most Categories keeper league (ID 84209353).

Analyzes matchup, draft, and standings data from 2021-2025 to answer:
1. Category tightness / swing categories
2. Winning archetypes (balanced vs. punt)
3. Manager draft tendencies (2024-2025 focus)
4. Draft pick value curve
5. Keeper patterns (2022-2023)

League was 10 teams 2021-2023, 8 teams 2024-2025.
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MATCHUP_DIR = DATA_DIR / "matchups"
DRAFT_DIR = DATA_DIR / "drafts"
STANDINGS_DIR = DATA_DIR / "standings"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"

SCORING_CATS = ["R", "HR", "TB", "RBI", "SBN", "OBP", "K", "QS", "ERA", "WHIP", "KBB", "SVHD"]
HITTING_CATS = ["R", "HR", "TB", "RBI", "SBN", "OBP"]
PITCHING_CATS = ["K", "QS", "ERA", "WHIP", "KBB", "SVHD"]
REVERSE_CATS = {"ERA", "WHIP"}  # lower is better

YEARS = [2021, 2022, 2023, 2024, 2025]
LEAGUE_SIZE = {2021: 10, 2022: 10, 2023: 10, 2024: 8, 2025: 8}

# Weight 2024-2025 more heavily (current league composition)
YEAR_WEIGHT = {2021: 0.5, 2022: 0.5, 2023: 0.5, 2024: 1.0, 2025: 1.0}


def load_json(path):
    with open(path) as f:
        return json.load(f)


# ===================================================================
# 1. CATEGORY TIGHTNESS / SWING CATEGORIES
# ===================================================================

def analyze_category_tightness():
    """For each scoring category, compute margin distributions and swing potential."""
    cat_margins = defaultdict(list)  # cat -> list of (margin, year, weight)
    cat_results = defaultdict(lambda: {"WIN": 0, "LOSS": 0, "TIE": 0})

    for year in YEARS:
        path = MATCHUP_DIR / f"matchups_{year}.json"
        if not path.exists():
            continue
        data = load_json(path)
        weight = YEAR_WEIGHT[year]

        for period_key, matchups in data["matchup_periods"].items():
            for m in matchups:
                home_stats = m.get("home_stats", {})
                away_stats = m.get("away_stats", {})
                for cat in SCORING_CATS:
                    h = home_stats.get(cat, {})
                    a = away_stats.get(cat, {})
                    hv = h.get("value")
                    av = a.get("value")
                    if hv is None or av is None:
                        continue
                    if cat in REVERSE_CATS:
                        margin = av - hv  # positive = home wins (lower is better)
                    else:
                        margin = hv - av  # positive = home wins
                    cat_margins[cat].append((abs(margin), year, weight))
                    result = h.get("result")
                    if result:
                        cat_results[cat][result] += 1

    # Compute tightness metrics
    rows = []
    for cat in SCORING_CATS:
        margins = cat_margins[cat]
        if not margins:
            continue
        abs_margins = [m[0] for m in margins]
        weights = [m[2] for m in margins]
        total = len(abs_margins)

        # Determine "thin margin" threshold per category type
        if cat in ("OBP",):
            thin_threshold = 0.010  # ~10 points of OBP
        elif cat in ("ERA",):
            thin_threshold = 0.50
        elif cat in ("WHIP",):
            thin_threshold = 0.15
        elif cat in ("KBB",):
            thin_threshold = 0.50
        else:
            # counting stats: use percentile-based threshold (bottom 25% of margins)
            thin_threshold = np.percentile(abs_margins, 25)

        thin_count = sum(1 for m in abs_margins if m <= thin_threshold)
        thin_frac = thin_count / total if total > 0 else 0

        # Weighted thin fraction (weight recent years more)
        w_thin = sum(w for m, y, w in margins if m <= thin_threshold)
        w_total = sum(w for m, y, w in margins)
        w_thin_frac = w_thin / w_total if w_total > 0 else 0

        tie_count = cat_results[cat].get("TIE", 0)
        tie_frac = tie_count / total if total > 0 else 0

        rows.append({
            "category": cat,
            "n_matchups": total,
            "median_margin": np.median(abs_margins),
            "mean_margin": np.mean(abs_margins),
            "p25_margin": np.percentile(abs_margins, 25),
            "thin_threshold": thin_threshold,
            "thin_frac": thin_frac,
            "weighted_thin_frac": w_thin_frac,
            "tie_frac": tie_frac,
        })

    df = pd.DataFrame(rows)
    # Swing score: combine thin_frac and tie_frac (categories where small improvements flip outcomes)
    df["swing_score"] = df["weighted_thin_frac"] + df["tie_frac"]
    df = df.sort_values("swing_score", ascending=False)
    return df, cat_margins


# ===================================================================
# 2. WINNING ARCHETYPES
# ===================================================================

def analyze_winning_archetypes():
    """Analyze typical category splits in matchups and whether winners go balanced or punt."""
    matchup_splits = []  # list of (winner_cat_wins, loser_cat_wins, year)
    team_season_records = defaultdict(lambda: defaultdict(lambda: {"cat_wins": 0, "cat_losses": 0, "cat_ties": 0, "match_wins": 0, "match_losses": 0, "match_ties": 0}))

    for year in YEARS:
        path = MATCHUP_DIR / f"matchups_{year}.json"
        if not path.exists():
            continue
        data = load_json(path)

        for period_key, matchups in data["matchup_periods"].items():
            for m in matchups:
                hw = m.get("home_category_wins", 0)
                hl = m.get("home_category_losses", 0)
                ht = m.get("home_category_ties", 0)
                aw = m.get("away_category_wins", 0)
                al = m.get("away_category_losses", 0)

                home_team = m.get("home_team", "")
                away_team = m.get("away_team", "")

                # Determine winner
                if hw > hl:
                    matchup_splits.append((hw, hl, ht, year))
                    team_season_records[year][home_team]["match_wins"] += 1
                    team_season_records[year][away_team]["match_losses"] += 1
                elif hl > hw:
                    matchup_splits.append((aw, al, m.get("away_category_ties", 0), year))
                    team_season_records[year][away_team]["match_wins"] += 1
                    team_season_records[year][home_team]["match_losses"] += 1
                else:
                    team_season_records[year][home_team]["match_ties"] += 1
                    team_season_records[year][away_team]["match_ties"] += 1

                team_season_records[year][home_team]["cat_wins"] += hw
                team_season_records[year][home_team]["cat_losses"] += hl
                team_season_records[year][home_team]["cat_ties"] += ht
                team_season_records[year][away_team]["cat_wins"] += aw
                team_season_records[year][away_team]["cat_losses"] += al

    # Distribution of winning category splits
    split_counts = defaultdict(int)
    for w, l, t, yr in matchup_splits:
        key = f"{w}-{l}" + (f"-{t}" if t > 0 else "")
        split_counts[key] += 1
    total_decided = len(matchup_splits)
    split_df = pd.DataFrame([
        {"split": k, "count": v, "pct": v / total_decided * 100}
        for k, v in split_counts.items()
    ]).sort_values("count", ascending=False)

    # Do winners tend to be balanced or punt?
    # Load standings to identify league winners
    winner_analysis = []
    for year in YEARS:
        spath = STANDINGS_DIR / f"standings_{year}.json"
        if not spath.exists():
            continue
        standings = load_json(spath)

        # Analyze per-category performance for top vs bottom teams
        mpath = MATCHUP_DIR / f"matchups_{year}.json"
        if not mpath.exists():
            continue
        mdata = load_json(mpath)

        # Per-team category win rates
        team_cat_wins = defaultdict(lambda: defaultdict(int))
        team_cat_total = defaultdict(lambda: defaultdict(int))
        for period_key, matchups in mdata["matchup_periods"].items():
            for m in matchups:
                home = m.get("home_team", "")
                away = m.get("away_team", "")
                hs = m.get("home_stats", {})
                as_ = m.get("away_stats", {})
                for cat in SCORING_CATS:
                    hr = hs.get(cat, {}).get("result")
                    ar = as_.get(cat, {}).get("result")
                    if hr:
                        team_cat_total[home][cat] += 1
                        if hr == "WIN":
                            team_cat_wins[home][cat] += 1
                    if ar:
                        team_cat_total[away][cat] += 1
                        if ar == "WIN":
                            team_cat_wins[away][cat] += 1

        for s in standings.get("standings", []):
            team_name = s["team_name"]
            final = s.get("final_standing", s.get("standing"))
            cat_win_rates = {}
            for cat in SCORING_CATS:
                t = team_cat_total[team_name].get(cat, 0)
                w = team_cat_wins[team_name].get(cat, 0)
                cat_win_rates[cat] = w / t if t > 0 else 0.5

            rates = list(cat_win_rates.values())
            winner_analysis.append({
                "year": year,
                "team": team_name,
                "final_standing": final,
                "mean_cat_winrate": np.mean(rates),
                "std_cat_winrate": np.std(rates),
                "min_cat_winrate": np.min(rates),
                "max_cat_winrate": np.max(rates),
                "cats_above_60pct": sum(1 for r in rates if r > 0.6),
                "cats_below_40pct": sum(1 for r in rates if r < 0.4),
                **{f"wr_{cat}": cat_win_rates[cat] for cat in SCORING_CATS},
            })

    winner_df = pd.DataFrame(winner_analysis)
    return split_df, winner_df


# ===================================================================
# 3. MANAGER DRAFT TENDENCIES (2024-2025 focus)
# ===================================================================

def analyze_draft_tendencies():
    """Per manager, what positions/player types do they draft early vs late?"""
    rows = []
    for year in [2024, 2025]:
        path = DRAFT_DIR / f"draft_{year}.json"
        if not path.exists():
            continue
        data = load_json(path)
        n_teams = LEAGUE_SIZE[year]
        n_rounds = data["total_picks"] // n_teams

        for pick in data["picks"]:
            pos = pick["player_position"]
            # Classify position
            if pos in ("SP", "RP"):
                pos_type = "pitcher"
            else:
                pos_type = "hitter"

            # Draft phase: early (1-5), mid (6-15), late (16+)
            rd = pick["round"]
            if rd <= 5:
                phase = "early"
            elif rd <= 15:
                phase = "mid"
            else:
                phase = "late"

            rows.append({
                "year": year,
                "team_name": pick["team_name"],
                "team_id": pick["team_id"],
                "round": rd,
                "pick_number": pick["pick_number"],
                "player_name": pick["player_name"],
                "position": pos,
                "pos_type": pos_type,
                "phase": phase,
                "is_keeper": pick["is_keeper"],
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df, pd.DataFrame()

    # Summarize per manager
    summary_rows = []
    for (team, year), grp in df.groupby(["team_name", "year"]):
        total = len(grp)
        pitchers_early = len(grp[(grp.pos_type == "pitcher") & (grp.phase == "early")])
        hitters_early = len(grp[(grp.pos_type == "hitter") & (grp.phase == "early")])
        pitcher_frac = len(grp[grp.pos_type == "pitcher"]) / total if total > 0 else 0

        pos_counts = grp["position"].value_counts().to_dict()
        early_picks = grp[grp.phase == "early"]
        early_pos = early_picks["position"].value_counts().to_dict()

        summary_rows.append({
            "team_name": team,
            "year": year,
            "total_picks": total,
            "pitcher_frac": pitcher_frac,
            "pitchers_early_rds": pitchers_early,
            "hitters_early_rds": hitters_early,
            "early_positions": early_pos,
            "all_positions": pos_counts,
            "first_pitcher_round": grp[grp.pos_type == "pitcher"]["round"].min() if len(grp[grp.pos_type == "pitcher"]) > 0 else None,
        })

    summary_df = pd.DataFrame(summary_rows)
    return df, summary_df


# ===================================================================
# 4. DRAFT PICK VALUE CURVE
# ===================================================================

def analyze_draft_value_curve():
    """How does player quality drop off by draft round?

    We proxy quality by ADP (average draft position across years).
    Players drafted earlier in multiple years are higher-quality.
    We also look at keeper status as a quality signal.
    """
    rows = []
    for year in YEARS:
        path = DRAFT_DIR / f"draft_{year}.json"
        if not path.exists():
            continue
        data = load_json(path)
        n_teams = LEAGUE_SIZE[year]

        for pick in data["picks"]:
            rows.append({
                "year": year,
                "round": pick["round"],
                "overall_pick": pick["pick_number"],
                "normalized_pick": pick["pick_number"] / n_teams,  # normalize to rounds
                "player_name": pick["player_name"],
                "player_id": pick["player_id"],
                "position": pick["player_position"],
                "team_name": pick["team_name"],
                "is_keeper": pick["is_keeper"],
                "n_teams": n_teams,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df, pd.DataFrame()

    # Players drafted multiple years => higher quality
    player_draft_freq = df.groupby("player_id").agg(
        times_drafted=("year", "count"),
        avg_round=("round", "mean"),
        best_round=("round", "min"),
        years=("year", lambda x: sorted(x.tolist())),
        name=("player_name", "first"),
    ).reset_index()

    # Value curve: for 2024-2025, compute "keeper rate" by round
    recent = df[df.year.isin([2024, 2025])]
    # Since 2024-2025 have 0 keepers, we look at whether players drafted
    # in round N of year Y were drafted in round <= N-2 of year Y+1 (retained value)
    # Instead, let's look at repeat draft rate: was the player drafted again next year?
    # And at what round change?
    value_rows = []
    for year in [2021, 2022, 2023, 2024]:
        next_year = year + 1
        this_year = df[df.year == year][["player_id", "round", "player_name"]].rename(
            columns={"round": "round_y1"})
        next_yr = df[df.year == next_year][["player_id", "round"]].rename(
            columns={"round": "round_y2"})
        merged = this_year.merge(next_yr, on="player_id", how="left")
        merged["retained"] = merged["round_y2"].notna()
        merged["round_improvement"] = merged["round_y1"] - merged["round_y2"]
        merged["year"] = year
        value_rows.append(merged)

    if value_rows:
        retention_df = pd.concat(value_rows, ignore_index=True)
        # Retention rate by round
        round_retention = retention_df.groupby("round_y1").agg(
            n_players=("player_id", "count"),
            n_retained=("retained", "sum"),
            retention_rate=("retained", "mean"),
            avg_round_change=("round_improvement", lambda x: x.dropna().mean()),
        ).reset_index().rename(columns={"round_y1": "round"})
    else:
        retention_df = pd.DataFrame()
        round_retention = pd.DataFrame()

    return df, round_retention


# ===================================================================
# 5. KEEPER PATTERNS (2022-2023)
# ===================================================================

def analyze_keeper_patterns():
    """What caliber of player was typically kept in 2022-2023?"""
    rows = []
    for year in [2022, 2023]:
        path = DRAFT_DIR / f"draft_{year}.json"
        if not path.exists():
            continue
        data = load_json(path)
        keepers = [p for p in data["picks"] if p["is_keeper"]]
        non_keepers = [p for p in data["picks"] if not p["is_keeper"]]

        # Check what round keepers were drafted in the previous year
        prev_year = year - 1
        prev_path = DRAFT_DIR / f"draft_{prev_year}.json"
        prev_lookup = {}
        if prev_path.exists():
            prev_data = load_json(prev_path)
            for p in prev_data["picks"]:
                prev_lookup[p["player_id"]] = {
                    "prev_round": p["round"],
                    "prev_pick": p["pick_number"],
                }

        for k in keepers:
            prev = prev_lookup.get(k["player_id"], {})
            rows.append({
                "year": year,
                "team_name": k["team_name"],
                "player_name": k["player_name"],
                "player_id": k["player_id"],
                "position": k["player_position"],
                "keeper_round": k["round"],
                "keeper_pick": k["pick_number"],
                "prev_year_round": prev.get("prev_round"),
                "prev_year_pick": prev.get("prev_pick"),
                "round_cost_saved": (prev.get("prev_round", k["round"]) - k["round"]) if prev.get("prev_round") else None,
            })

    df = pd.DataFrame(rows)
    return df


# ===================================================================
# REPORT GENERATION
# ===================================================================

def generate_report(cat_df, split_df, winner_df, draft_picks_df, draft_summary_df,
                    value_df, retention_df, keeper_df):
    """Generate markdown report."""
    lines = []
    lines.append("# League Historical Analysis (2021-2025)")
    lines.append("")
    lines.append("League: ESPN H2H Most Categories (ID 84209353)")
    lines.append("Teams: 10 (2021-2023), 8 (2024-2025)")
    lines.append("Categories: R/HR/TB/RBI/SBN/OBP + K/QS/ERA/WHIP/K-BB/SVHD")
    lines.append("")

    # --- Section 1: Category Tightness ---
    lines.append("## 1. Category Tightness & Swing Categories")
    lines.append("")
    lines.append("Categories ranked by **swing score** (how often a small roster improvement flips the outcome):")
    lines.append("")
    lines.append("| Category | Median Margin | Thin Margin % | Tie % | Swing Score |")
    lines.append("|----------|--------------|---------------|-------|-------------|")
    for _, row in cat_df.iterrows():
        cat = row["category"]
        med = row["median_margin"]
        if cat in ("OBP", "ERA", "WHIP", "KBB"):
            med_str = f"{med:.3f}"
        else:
            med_str = f"{med:.1f}"
        lines.append(f"| {cat} | {med_str} | {row['weighted_thin_frac']:.1%} | {row['tie_frac']:.1%} | {row['swing_score']:.3f} |")

    top_swing = cat_df.head(3)["category"].tolist()
    lines.append("")
    lines.append(f"**Top swing categories: {', '.join(top_swing)}** — these are where marginal roster improvements flip the most matchup outcomes.")
    lines.append("")

    # --- Section 2: Winning Archetypes ---
    lines.append("## 2. Winning Archetypes")
    lines.append("")
    lines.append("### Typical Matchup Splits (Winner-Loser)")
    lines.append("")
    lines.append("| Split | Count | % of Decided Matchups |")
    lines.append("|-------|-------|-----------------------|")
    for _, row in split_df.head(10).iterrows():
        lines.append(f"| {row['split']} | {row['count']} | {row['pct']:.1f}% |")
    lines.append("")

    most_common = split_df.iloc[0]["split"] if len(split_df) > 0 else "N/A"
    lines.append(f"**Most common winning split: {most_common}**")
    lines.append("")

    # Balanced vs Punt analysis
    lines.append("### Do Winners Go Balanced or Punt?")
    lines.append("")
    if not winner_df.empty:
        # Top 3 finishers vs bottom 3
        top_teams = winner_df[winner_df.final_standing <= 3]
        bottom_teams = winner_df[winner_df.final_standing > winner_df.groupby("year")["final_standing"].transform("max") - 3]

        lines.append("| Metric | Top-3 Finishers | Bottom-3 Finishers |")
        lines.append("|--------|----------------|--------------------|")
        for metric, label in [
            ("mean_cat_winrate", "Avg cat win rate"),
            ("std_cat_winrate", "Std dev of cat win rates"),
            ("cats_above_60pct", "Cats above 60% WR"),
            ("cats_below_40pct", "Cats below 40% WR"),
        ]:
            top_val = top_teams[metric].mean()
            bot_val = bottom_teams[metric].mean()
            lines.append(f"| {label} | {top_val:.3f} | {bot_val:.3f} |")
        lines.append("")

        # Per-category win rates for top finishers
        lines.append("### Category Win Rates by Finish Position (All Years)")
        lines.append("")
        lines.append("| Category | Top-3 Avg WR | Bottom-3 Avg WR | Gap |")
        lines.append("|----------|-------------|-----------------|-----|")
        for cat in SCORING_CATS:
            col = f"wr_{cat}"
            if col in winner_df.columns:
                top_wr = top_teams[col].mean()
                bot_wr = bottom_teams[col].mean()
                gap = top_wr - bot_wr
                lines.append(f"| {cat} | {top_wr:.3f} | {bot_wr:.3f} | {gap:+.3f} |")
        lines.append("")

        # Check if winners are balanced
        top_std = top_teams["std_cat_winrate"].mean()
        bot_std = bottom_teams["std_cat_winrate"].mean()
        if top_std < bot_std:
            lines.append("**Finding: Top finishers are MORE BALANCED** (lower std dev across categories).")
        else:
            lines.append("**Finding: Top finishers tend to SPECIALIZE** (higher std dev — dominate some, concede others).")
        lines.append("")

        # League champions detail
        champs = winner_df[winner_df.final_standing == 1].sort_values("year")
        if not champs.empty:
            lines.append("### League Champions Detail")
            lines.append("")
            for _, ch in champs.iterrows():
                strong = [cat for cat in SCORING_CATS if ch.get(f"wr_{cat}", 0) > 0.6]
                weak = [cat for cat in SCORING_CATS if ch.get(f"wr_{cat}", 0) < 0.4]
                lines.append(f"- **{int(ch['year'])} {ch['team']}**: {ch['cats_above_60pct']:.0f} cats >60%, {ch['cats_below_40pct']:.0f} cats <40%. Strong: {', '.join(strong) or 'none'}. Weak: {', '.join(weak) or 'none'}.")
            lines.append("")

    # --- Section 3: Manager Draft Tendencies ---
    lines.append("## 3. Manager Draft Tendencies (2024-2025)")
    lines.append("")
    if not draft_summary_df.empty:
        lines.append("| Manager | Year | Pitcher% | 1st Pitcher Rd | Pitchers Early (R1-5) | Hitters Early (R1-5) |")
        lines.append("|---------|------|----------|----------------|----------------------|---------------------|")
        for _, row in draft_summary_df.sort_values(["team_name", "year"]).iterrows():
            fp = int(row["first_pitcher_round"]) if row["first_pitcher_round"] is not None else "N/A"
            lines.append(f"| {row['team_name']} | {row['year']} | {row['pitcher_frac']:.0%} | {fp} | {row['pitchers_early_rds']} | {row['hitters_early_rds']} |")
        lines.append("")

        # Position preferences in early rounds
        lines.append("### Early Round Position Preferences (Rounds 1-5)")
        lines.append("")
        if not draft_picks_df.empty:
            early = draft_picks_df[draft_picks_df.phase == "early"]
            for team in sorted(early.team_name.unique()):
                team_early = early[early.team_name == team]
                pos_str = ", ".join(f"{pos}({ct})" for pos, ct in
                                   team_early.position.value_counts().items())
                players = ", ".join(team_early.sort_values("round")["player_name"].tolist())
                lines.append(f"- **{team}**: {pos_str}")
                lines.append(f"  - Players: {players}")
            lines.append("")

    # --- Section 4: Draft Value Curve ---
    lines.append("## 4. Draft Pick Value Curve")
    lines.append("")
    if not retention_df.empty:
        lines.append("Year-over-year player retention by draft round (proxy for player quality):")
        lines.append("")
        lines.append("| Round | Players | Retained Next Year | Retention Rate |")
        lines.append("|-------|---------|-------------------|----------------|")
        for _, row in retention_df.head(25).iterrows():
            lines.append(f"| {int(row['round'])} | {int(row['n_players'])} | {int(row['n_retained'])} | {row['retention_rate']:.0%} |")
        lines.append("")

        # Find the round where retention drops below 50%
        below_50 = retention_df[retention_df.retention_rate < 0.5]
        if not below_50.empty:
            drop_round = int(below_50.iloc[0]["round"])
            lines.append(f"**Quality cliff: Retention drops below 50% at round {drop_round}.** Players drafted after this point are replacement-level in our league.")
        lines.append("")

    # --- Section 5: Keeper Patterns ---
    lines.append("## 5. Keeper Patterns (2022-2023)")
    lines.append("")
    if not keeper_df.empty:
        lines.append(f"Total keepers: {len(keeper_df)} across 2022-2023")
        lines.append("")
        lines.append("| Year | Player | Position | Kept at Round | Prev Year Round | Cost Saved |")
        lines.append("|------|--------|----------|---------------|-----------------|------------|")
        for _, row in keeper_df.sort_values(["year", "keeper_round"]).iterrows():
            prev = int(row["prev_year_round"]) if pd.notna(row["prev_year_round"]) else "N/A"
            saved = int(row["round_cost_saved"]) if pd.notna(row["round_cost_saved"]) else "N/A"
            lines.append(f"| {row['year']} | {row['player_name']} | {row['position']} | {row['keeper_round']} | {prev} | {saved} |")
        lines.append("")

        # Position breakdown
        pos_counts = keeper_df["position"].value_counts()
        lines.append("### Keeper Position Distribution")
        lines.append("")
        for pos, ct in pos_counts.items():
            lines.append(f"- {pos}: {ct} ({ct/len(keeper_df):.0%})")
        lines.append("")

        avg_round = keeper_df["keeper_round"].mean()
        lines.append(f"**Average keeper round: {avg_round:.1f}** — keepers are overwhelmingly early-round talent.")
        lines.append("")

        if keeper_df["round_cost_saved"].notna().any():
            avg_saved = keeper_df["round_cost_saved"].dropna().mean()
            lines.append(f"**Average rounds saved vs re-draft cost: {avg_saved:.1f}** — keeper value comes from locking in players who would cost more to re-draft.")
        lines.append("")

    # --- Summary ---
    lines.append("## Key Takeaways for 2026 Draft")
    lines.append("")
    if not cat_df.empty:
        lines.append(f"1. **Target swing categories**: {', '.join(top_swing)} — these flip matchup outcomes on thin margins.")
    lines.append("2. **Go balanced**: Top finishers maintain competitive win rates across most categories rather than punting.")
    if not retention_df.empty and not below_50.empty:
        lines.append(f"3. **Draft value cliff at round {drop_round}**: Players after this are replacement-level. Keeper value is highest for players who would be drafted in rounds 1-{drop_round-1}.")
    lines.append("4. **Know your opponents**: Manager tendencies reveal exploitable draft patterns.")
    lines.append("")

    return "\n".join(lines)


# ===================================================================
# MAIN
# ===================================================================

def main():
    print("=" * 70)
    print("LEAGUE HISTORICAL ANALYSIS (2021-2025)")
    print("=" * 70)
    print()

    # 1. Category Tightness
    print("--- 1. Category Tightness & Swing Categories ---")
    cat_df, cat_margins = analyze_category_tightness()
    if not cat_df.empty:
        print(cat_df[["category", "median_margin", "weighted_thin_frac", "tie_frac", "swing_score"]].to_string(index=False))
        top_swing = cat_df.head(3)["category"].tolist()
        print(f"\nTop swing categories: {', '.join(top_swing)}")
    print()

    # 2. Winning Archetypes
    print("--- 2. Winning Archetypes ---")
    split_df, winner_df = analyze_winning_archetypes()
    if not split_df.empty:
        print("Most common matchup splits (winner-loser):")
        print(split_df.head(8).to_string(index=False))
    if not winner_df.empty:
        top3 = winner_df[winner_df.final_standing <= 3]
        bot3 = winner_df[winner_df.final_standing > winner_df.groupby("year")["final_standing"].transform("max") - 3]
        print(f"\nTop-3 finishers avg cat win rate std dev: {top3['std_cat_winrate'].mean():.3f}")
        print(f"Bottom-3 finishers avg cat win rate std dev: {bot3['std_cat_winrate'].mean():.3f}")
        balanced = "BALANCED" if top3['std_cat_winrate'].mean() < bot3['std_cat_winrate'].mean() else "SPECIALIZED"
        print(f"Winners tend to be: {balanced}")
    print()

    # 3. Draft Tendencies
    print("--- 3. Manager Draft Tendencies (2024-2025) ---")
    draft_picks_df, draft_summary_df = analyze_draft_tendencies()
    if not draft_summary_df.empty:
        print(draft_summary_df[["team_name", "year", "pitcher_frac", "first_pitcher_round",
                                 "pitchers_early_rds", "hitters_early_rds"]].to_string(index=False))
    print()

    # 4. Draft Value Curve
    print("--- 4. Draft Pick Value Curve ---")
    value_df, retention_df = analyze_draft_value_curve()
    if not retention_df.empty:
        print("Year-over-year retention by round:")
        print(retention_df.head(20).to_string(index=False))
    print()

    # 5. Keeper Patterns
    print("--- 5. Keeper Patterns (2022-2023) ---")
    keeper_df = analyze_keeper_patterns()
    if not keeper_df.empty:
        print(f"Total keepers: {len(keeper_df)}")
        print(keeper_df[["year", "player_name", "position", "keeper_round",
                         "prev_year_round", "round_cost_saved"]].to_string(index=False))
        print(f"\nAverage keeper round: {keeper_df['keeper_round'].mean():.1f}")
    print()

    # Generate report
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    report = generate_report(cat_df, split_df, winner_df, draft_picks_df, draft_summary_df,
                             value_df, retention_df, keeper_df)
    report_path = ANALYSIS_DIR / "league_history_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report written to: {report_path}")


if __name__ == "__main__":
    main()
