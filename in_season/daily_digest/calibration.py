"""
Calibration logging for newsletter predictions.

Records predicted vs actual outcomes after each matchup completes.
Run `log_predictions()` daily (called by run_newsletter.py) to snapshot predictions.
Run `log_actuals()` after each matchup ends to record what actually happened.
Run `calibration_report()` after 5+ matchups to assess prediction quality.
"""

import csv
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

from config import OUTPUT_DIR, MY_TEAM_ID

log = logging.getLogger(__name__)

CALIBRATION_DIR = OUTPUT_DIR.parent / "calibration"
PREDICTIONS_CSV = CALIBRATION_DIR / "predictions.csv"
ACTUALS_CSV = CALIBRATION_DIR / "actuals.csv"

PREDICTIONS_FIELDS = [
    "date", "matchup_period", "opponent", "category",
    "predicted_status", "predicted_p_win", "our_value", "opp_value",
    "margin", "triage_bucket",
]

ACTUALS_FIELDS = [
    "matchup_period", "category",
    "final_our_value", "final_opp_value", "result",  # "win", "loss", "tie"
]


def _ensure_dir():
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_csv(path, fields):
    """Create CSV with header if it doesn't exist."""
    _ensure_dir()
    if not path.exists():
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()


def log_predictions(briefing_book, newsletter_text=None):
    """
    Snapshot today's predicted category states from the briefing book.
    Called daily by run_newsletter.py after the newsletter is generated.

    Also attempts to extract P(win) estimates from the newsletter text
    if the dashboard table is parseable.
    """
    _ensure_csv(PREDICTIONS_CSV, PREDICTIONS_FIELDS)

    today = briefing_book.get("date", date.today().isoformat())
    matchup_period = briefing_book.get("matchup_week")
    opponent = briefing_book.get("opponent", "")
    category_state = briefing_book.get("category_state", {})
    triage = briefing_book.get("category_triage", {})

    # Build reverse triage lookup: category -> bucket
    cat_to_bucket = {}
    for bucket, cats in triage.items():
        for cat in cats:
            cat_to_bucket[cat] = bucket

    # Try to extract P(win) from newsletter dashboard table
    p_win_map = {}
    if newsletter_text:
        p_win_map = _extract_p_win_from_newsletter(newsletter_text)

    rows = []
    for cat, state in category_state.items():
        rows.append({
            "date": today,
            "matchup_period": matchup_period,
            "opponent": opponent,
            "category": cat,
            "predicted_status": state.get("status", ""),
            "predicted_p_win": p_win_map.get(cat, ""),
            "our_value": state.get("you", ""),
            "opp_value": state.get("opp", ""),
            "margin": state.get("margin", ""),
            "triage_bucket": cat_to_bucket.get(cat, ""),
        })

    with open(PREDICTIONS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PREDICTIONS_FIELDS)
        writer.writerows(rows)

    log.info(f"Calibration: logged {len(rows)} category predictions for MP {matchup_period}")


def _extract_p_win_from_newsletter(text):
    """
    Try to extract P(win) percentages from the MATCHUP DASHBOARD table.
    Returns dict of category -> percentage string.
    """
    p_win = {}
    # Look for lines like: R      | XX     | XX     | ...    | ~75%   | ...
    # Or: R     | +1.77z   | PROTECT          | 65%    | ...
    # Or: K/BB  | +0.87z   | LOCK             | 88%    | ...
    for line in text.split("\n"):
        # Match category name at start (including K/BB), then find percentage
        m = re.match(r'\s*([\w/]+)\s*\|.*?~?(\d{1,3})%', line)
        if m:
            cat = m.group(1).strip()
            pct = m.group(2)
            # Normalize K/BB -> KBB
            cat = cat.replace("/", "")
            if cat in ("R", "HR", "TB", "RBI", "SBN", "OBP", "K", "QS", "ERA", "WHIP", "KBB", "SVHD"):
                p_win[cat] = int(pct)
    return p_win


def log_actuals(matchup_period, category_results):
    """
    Record actual matchup results after a matchup completes.

    Args:
        matchup_period: int, the matchup period ID
        category_results: dict of category -> {"our": value, "opp": value, "result": "win"/"loss"/"tie"}
    """
    _ensure_csv(ACTUALS_CSV, ACTUALS_FIELDS)

    rows = []
    for cat, result in category_results.items():
        rows.append({
            "matchup_period": matchup_period,
            "category": cat,
            "final_our_value": result.get("our", ""),
            "final_opp_value": result.get("opp", ""),
            "result": result.get("result", ""),
        })

    with open(ACTUALS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ACTUALS_FIELDS)
        writer.writerows(rows)

    log.info(f"Calibration: logged {len(rows)} actual results for MP {matchup_period}")


def log_actuals_from_espn(matchup_period):
    """
    Fetch final matchup results from ESPN and log them.
    Call this after a matchup period completes.
    """
    from fetch_espn import fetch_matchup_scores
    from config import SCORING_CAT_IDS, STATS_MAP, LOWER_IS_BETTER

    our_matchup, _ = fetch_matchup_scores(matchup_period_id=matchup_period)
    if not our_matchup:
        log.warning(f"No matchup data found for MP {matchup_period}")
        return

    # Determine our side
    if our_matchup["home_team_id"] == MY_TEAM_ID:
        our_key, opp_key = "home_value", "away_value"
    else:
        our_key, opp_key = "away_value", "home_value"

    results = {}
    for cat_name, cat_data in our_matchup["categories"].items():
        our_val = cat_data.get(our_key, 0) or 0
        opp_val = cat_data.get(opp_key, 0) or 0

        if cat_name in LOWER_IS_BETTER:
            if our_val < opp_val:
                result = "win"
            elif our_val > opp_val:
                result = "loss"
            else:
                result = "tie"
        else:
            if our_val > opp_val:
                result = "win"
            elif our_val < opp_val:
                result = "loss"
            else:
                result = "tie"

        results[cat_name] = {"our": our_val, "opp": opp_val, "result": result}

    log_actuals(matchup_period, results)
    return results


def calibration_report():
    """
    Generate a calibration summary comparing predictions vs actuals.
    Returns a text report. Call after 5+ matchups for meaningful data.
    """
    if not PREDICTIONS_CSV.exists() or not ACTUALS_CSV.exists():
        return "Insufficient data — need both predictions and actuals CSVs."

    import pandas as pd

    preds = pd.read_csv(PREDICTIONS_CSV)
    actuals = pd.read_csv(ACTUALS_CSV)

    if len(actuals) == 0:
        return "No actual results logged yet. Run log_actuals_from_espn() after a matchup completes."

    # Get the latest prediction per matchup_period + category (last day's snapshot)
    latest_preds = preds.sort_values("date").groupby(["matchup_period", "category"]).last().reset_index()

    # Join predictions to actuals
    merged = latest_preds.merge(
        actuals, on=["matchup_period", "category"], how="inner"
    )

    if len(merged) == 0:
        return "No overlapping data between predictions and actuals yet."

    lines = ["# Calibration Report", f"Generated: {datetime.now().isoformat()}", ""]

    # Overall accuracy: how often did predicted_status match result?
    status_map = {"winning": "win", "losing": "loss", "tied": "tie"}
    merged["predicted_result"] = merged["predicted_status"].map(status_map)
    correct = (merged["predicted_result"] == merged["result"]).sum()
    total = len(merged)
    lines.append(f"## Overall Status Accuracy: {correct}/{total} ({correct/total:.0%})")
    lines.append("")

    # P(win) calibration (if we have P(win) data)
    if "predicted_p_win" in merged.columns:
        pwin = merged[merged["predicted_p_win"].notna() & (merged["predicted_p_win"] != "")]
        if len(pwin) > 0:
            pwin = pwin.copy()
            pwin["predicted_p_win"] = pd.to_numeric(pwin["predicted_p_win"], errors="coerce")
            pwin = pwin.dropna(subset=["predicted_p_win"])
            pwin["won"] = (pwin["result"] == "win").astype(int)

            # Bin by P(win) decile
            bins = [0, 20, 40, 60, 80, 100]
            labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]
            pwin["bin"] = pd.cut(pwin["predicted_p_win"], bins=bins, labels=labels, include_lowest=True)
            cal = pwin.groupby("bin", observed=True).agg(
                predicted_mean=("predicted_p_win", "mean"),
                actual_win_rate=("won", "mean"),
                count=("won", "count"),
            )
            lines.append("## P(win) Calibration")
            lines.append("| Predicted | Actual Win% | N |")
            lines.append("|-----------|------------|---|")
            for idx, row in cal.iterrows():
                lines.append(f"| {idx} | {row['actual_win_rate']:.0%} | {int(row['count'])} |")
            lines.append("")

    # Per-triage-bucket accuracy
    if "triage_bucket" in merged.columns:
        lines.append("## Accuracy by Triage Bucket")
        for bucket in ["winning_comfortably", "winning_narrow", "too_close_to_call", "losing_flippable", "losing_unrecoverable"]:
            subset = merged[merged["triage_bucket"] == bucket]
            if len(subset) > 0:
                wins = (subset["result"] == "win").sum()
                lines.append(f"  {bucket}: {wins}/{len(subset)} won ({wins/len(subset):.0%})")
        lines.append("")

    report = "\n".join(lines)

    # Save report
    _ensure_dir()
    report_path = CALIBRATION_DIR / "calibration_report.md"
    report_path.write_text(report)
    log.info(f"Calibration report saved to {report_path}")

    return report
