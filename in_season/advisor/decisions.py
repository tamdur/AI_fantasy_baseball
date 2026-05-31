"""Decision log + process scoring (plan §3.5, §7, replaces the calibration target D9).

The advisor logs every DECISION (including holds) and scores its PROCESS over time —
confidence calibration, EV estimate vs realized, and self-critique overturn rate — rather
than scoring a fabricated P(win). The log is Tier-1 committed (``advisor/log/decisions.csv``,
~0–5 rows/day); an optional compact daily record (``records/<date>.json``, ≤ few KB) keeps
an audit trail. ``realized_outcome`` is backfilled at matchup close.
"""

import csv
import json
import logging

from advisor import config as cfg
from advisor import validation

log = logging.getLogger("advisor.decisions")

FIELDS = [
    "date", "decision_id", "matchup_period", "type", "tier", "players",
    "winprob_overall_before", "winprob_overall_after", "ev_estimate",
    "confidence_qual", "overturned_by_selfcritique", "rationale_ref", "realized_outcome",
]

_VALID_TYPES = {"start", "sit", "stream", "add", "drop", "hold"}
_VALID_TIERS = {"tweak", "stream", "significant", "hold"}


def decision_to_row(d, *, date, matchup_period, index):
    """Normalize an analyst decision dict into a log row (all FIELDS present)."""
    players = d.get("players", [])
    if isinstance(players, (list, tuple)):
        players = ";".join(str(p) for p in players)
    return {
        "date": date,
        "decision_id": d.get("decision_id", f"{date}-{index}"),
        "matchup_period": matchup_period,
        "type": d.get("type", "hold"),
        "tier": d.get("tier", "hold"),
        "players": players,
        "winprob_overall_before": d.get("winprob_before"),
        "winprob_overall_after": d.get("winprob_after"),
        "ev_estimate": d.get("ev_estimate"),
        "confidence_qual": d.get("confidence", "med"),
        "overturned_by_selfcritique": bool(d.get("overturned", False)),
        "rationale_ref": (d.get("rationale") or d.get("one_liner") or "")[:300],
        "realized_outcome": d.get("realized_outcome", ""),
    }


def log_decisions(decisions, *, date, matchup_period, path=None):
    """Append decision rows to the Tier-1 CSV (writing the header if new). Returns rows."""
    path = path or cfg.DECISIONS_CSV
    cfg.ensure_log_dirs()
    rows = [decision_to_row(d, date=date, matchup_period=matchup_period, index=i)
            for i, d in enumerate(decisions)]
    new_file = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(rows)
    log.info("Logged %d decisions -> %s", len(rows), path)
    return rows


def write_daily_record(context, decisions, *, date, closest_call=None, path=None):
    """Write a compact (≤ few KB) Tier-1 audit record for the day. Returns the path."""
    path = path or cfg.records_path(date)
    cfg.ensure_log_dirs()
    wp = (context or {}).get("winprob", {}).get("overall", {})
    record = {
        "date": date,
        "p_win_matchup": wp.get("p_win_matchup"),
        "expected_cats_won": wp.get("expected_cats_won"),
        "moves": [{"type": d.get("type"), "tier": d.get("tier"),
                   "players": d.get("players"), "ev": d.get("ev_estimate"),
                   "confidence": d.get("confidence"), "overturned": d.get("overturned", False)}
                  for d in decisions if d.get("type") != "hold"],
        "closest_call": closest_call,
    }
    with open(path, "w") as f:
        json.dump(record, f, indent=2, default=str)
    return path


def load_decisions(path=None):
    path = path or cfg.DECISIONS_CSV
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def score_process(through_matchup=None, path=None):
    """Process-quality report over logged decisions with realized outcomes (plan §7).

    Reports: confidence-bucket hit rates, EV-vs-realized where both exist, self-critique
    overturn rate, and (if numeric P(win) snapshots exist) a reliability/Brier summary.
    """
    rows = load_decisions(path)
    if through_matchup is not None:
        rows = [r for r in rows if _to_int(r.get("matchup_period")) is not None
                and _to_int(r["matchup_period"]) <= through_matchup]
    realized = [r for r in rows if (r.get("realized_outcome") or "") != ""]

    # Confidence-bucket hit rate (realized win fraction by qualitative confidence).
    buckets = {}
    for r in realized:
        c = r.get("confidence_qual", "med")
        b = buckets.setdefault(c, {"n": 0, "hits": 0})
        b["n"] += 1
        b["hits"] += 1 if _is_win(r.get("realized_outcome")) else 0
    conf_hit = {c: {"n": v["n"], "hit_rate": round(v["hits"] / v["n"], 3)}
                for c, v in buckets.items() if v["n"]}

    moves = [r for r in rows if r.get("type") not in ("hold", None, "")]
    overturn_rate = (round(sum(1 for r in rows if _truthy(r.get("overturned_by_selfcritique")))
                           / len(rows), 3) if rows else None)

    # Numeric reliability if winprob_overall_after + realized are present.
    pairs = [(float(r["winprob_overall_after"]), _is_win(r.get("realized_outcome")))
             for r in realized if _is_float(r.get("winprob_overall_after"))]
    reliability = validation.reliability(pairs) if pairs else None

    return {
        "n_decisions": len(rows), "n_moves": len(moves), "n_realized": len(realized),
        "confidence_hit_rate": conf_hit, "selfcritique_overturn_rate": overturn_rate,
        "reliability": reliability,
    }


def _to_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _is_float(x):
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _is_win(x):
    return str(x).strip().upper() in ("W", "WIN", "1", "TRUE", "GOOD")


def _truthy(x):
    return str(x).strip().lower() in ("true", "1", "yes")
