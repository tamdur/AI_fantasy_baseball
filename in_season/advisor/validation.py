"""Calibration / validation harness (plan §7).

The keystone check is *reliability*: when the simulator says a category is a 70%
win, does it win ~70% of the time? ``reliability`` is pure (predicted-p, outcome)
→ reliability-by-bin + Brier score, so it validates either the simulator's
pre-matchup per-cat P(win) against realized category results OR the decision log's
confidence over time.

The full simulator-vs-history *replay* (re-simulate completed matchups from archived
rosters+gamelogs) needs accrued history the new advisor does not have yet; once the
decision log + per-cat P(win) snapshots accumulate, feed them here. ``load_actuals``
reads the existing ``calibration/actuals.csv`` when present (it is gitignored, so this
is a local validation step — kb).
"""

import csv
import logging
from pathlib import Path

from advisor import config as cfg

log = logging.getLogger("advisor.validation")


def reliability(pairs, n_bins=10):
    """(predicted_p, outcome_bool) pairs -> calibration report.

    Returns {n, brier, calibration_error (mean |pred-obs| over non-empty bins),
    bins:[{lo, hi, predicted, observed, count}]}. ``outcome`` is truthy for a win.
    """
    pairs = [(float(p), 1.0 if o else 0.0) for p, o in pairs if p is not None]
    n = len(pairs)
    if n == 0:
        return {"n": 0, "brier": None, "calibration_error": None, "bins": []}

    brier = sum((p - o) ** 2 for p, o in pairs) / n

    bins = []
    cal_err_terms = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        # last bin is closed on the right so p == 1.0 lands somewhere
        in_bin = [(p, o) for p, o in pairs
                  if (lo <= p < hi) or (b == n_bins - 1 and p == 1.0)]
        if not in_bin:
            continue
        pred = sum(p for p, _ in in_bin) / len(in_bin)
        obs = sum(o for _, o in in_bin) / len(in_bin)
        bins.append({"lo": round(lo, 2), "hi": round(hi, 2),
                     "predicted": round(pred, 4), "observed": round(obs, 4),
                     "count": len(in_bin)})
        cal_err_terms.append(abs(pred - obs))

    cal_err = sum(cal_err_terms) / len(cal_err_terms) if cal_err_terms else None
    return {"n": n, "brier": round(brier, 4),
            "calibration_error": round(cal_err, 4) if cal_err is not None else None,
            "bins": bins}


def load_actuals(path=None):
    """Read calibration/actuals.csv if present. Returns list of row dicts (else [])."""
    path = Path(path) if path else (cfg.ROOT / "in_season" / "daily_digest" / "calibration"
                                    / "actuals.csv")
    if not path.exists():
        log.info("actuals not found at %s (local-only validation; gitignored)", path)
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def pairs_from_predictions(prediction_rows, actual_rows):
    """Join per-(matchup_period, category) predicted_p_win to realized result -> pairs.

    Mirrors the legacy predictions.csv / actuals.csv schema so the backtest can run on
    whatever history exists. ``result`` 'W' -> win=1, 'L'/'T' -> 0.
    """
    realized = {(str(r.get("matchup_period")), r.get("category")): r.get("result")
                for r in actual_rows}
    pairs = []
    for r in prediction_rows:
        key = (str(r.get("matchup_period")), r.get("category"))
        if key not in realized:
            continue
        try:
            p = float(r.get("predicted_p_win"))
        except (TypeError, ValueError):
            continue
        pairs.append((p, realized[key] == "W"))
    return pairs


def format_report(rep):
    """One-line-per-bin reliability table for a decision-page / log appendix."""
    if not rep or rep.get("n", 0) == 0:
        return "Calibration: no data yet."
    lines = [f"Calibration (n={rep['n']}, Brier={rep['brier']}, "
             f"cal_err={rep['calibration_error']}):"]
    for b in rep["bins"]:
        lines.append(f"  p≈{b['lo']:.1f}-{b['hi']:.1f}: predicted {b['predicted']:.2f} "
                     f"vs observed {b['observed']:.2f}  (n={b['count']})")
    return "\n".join(lines)
