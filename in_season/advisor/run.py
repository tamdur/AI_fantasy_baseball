"""Advisor run orchestration (plan §3.7, §5).

The unattended daily run is a Claude Code **Routine whose session IS the analyst** — there
is no nested ``claude --print`` (that would hit the CLAUDECODE guard and risk API billing).
This module provides the deterministic bookends the session calls:

  python -m advisor.run prepare [--date D] [--force]
      Build the decision context + sim state into Tier-2 scratch. Idempotent: skips if the
      day's page is already committed (docs/archive/<date>.html) — the cross-run guard (§1.1).
  python -m advisor.run publish --decisions <file.json> [--date D] [--dry-run] [--no-push]
      Render the stakes-tiered page, log decisions, write the daily record, and (real run)
      git-commit+push the Tier-1 artifacts. --dry-run renders a scratch preview, no commit.
  python -m advisor.run score      # process-quality report from the decision log
  python -m advisor.run check      # validate ESPN creds + claude availability

Run with cwd = in_season/ (so ``advisor`` is importable) or PYTHONPATH=in_season. Git runs
at the repo root regardless.
"""

import sys
import json
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import date as _date

from advisor import config as cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("advisor.run")


def _today():
    return _date.today().isoformat()


def _parse_payload(path):
    """Analyst decisions file -> (decisions list, closest_call). Accepts a bare list or
    {"decisions": [...], "closest_call": "..."}."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data, None
    return data.get("decisions", []), data.get("closest_call")


def cmd_prepare(args):
    date = args.date
    if not args.force and cfg.archive_page_path(date).exists():
        print(json.dumps({"status": "skipped", "reason": "already published today", "date": date}))
        return 0
    from advisor import context as C
    ctx = C.build_decision_context(date)
    cfg.scratch_path(f"PREPARED_{date}").write_text("ok")  # within-run handoff marker
    wp = (ctx.get("winprob") or {}).get("overall", {})
    print(json.dumps({
        "status": "prepared", "date": date,
        "context_path": str(cfg.context_path(date)),
        "sim_state_path": str(cfg.sim_state_path(date)),
        "p_win_matchup": wp.get("p_win_matchup"),
        "streamer_candidates": len(ctx.get("candidates", {}).get("streamers_today", [])),
        "data_warnings": ctx.get("data_warnings", []),
    }, indent=2))
    return 0


def cmd_publish(args):
    date = args.date
    from advisor import decisions as D, render as R
    ctx = json.loads(cfg.context_path(date).read_text())
    decisions, closest = _parse_payload(args.decisions) if args.decisions else ([], None)
    matchup = ctx.get("matchup_week")
    html = R.render_decision_page(ctx, decisions, closest_call=closest)

    if args.dry_run:
        preview = cfg.scratch_path(f"preview_{date}.html")
        preview.write_text(html, encoding="utf-8")
        print(json.dumps({"status": "dry-run", "preview": str(preview),
                          "n_decisions": len(decisions)}, indent=2))
        return 0

    R.publish_page(html, date)
    D.log_decisions(decisions, date=date, matchup_period=matchup)
    D.write_daily_record(ctx, decisions, date=date, closest_call=closest)
    pushed = True if args.no_push else _git_commit_push(date)
    print(json.dumps({"status": "published", "date": date, "n_decisions": len(decisions),
                      "pushed": (pushed if not args.no_push else False)}, indent=2))
    return 0


def cmd_score(args):
    from advisor import decisions as D
    print(json.dumps(D.score_process(through_matchup=args.through), indent=2, default=str))
    return 0


def cmd_check(args):
    try:
        from config import validate_config
        issues = validate_config()
    except Exception as e:
        issues = [f"config import failed: {e}"]
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2))
    return 1 if issues else 0


# --- git push-back (Tier-1 persistence; plan §1.1) ---

def _git(*args):
    return subprocess.run(["git", *args], cwd=str(cfg.ROOT), capture_output=True, text=True)


def _git_commit_push(date):
    """Commit the Tier-1 artifacts and push. Pull --rebase first to avoid drift. Returns
    True on a successful push (or 'nothing to commit')."""
    _git("add", str(cfg.DOCS_DIR), str(cfg.LOG_DIR))
    commit = _git("commit", "-m", f"Advisor decision page {date}")
    if commit.returncode != 0 and "nothing to commit" in (commit.stdout + commit.stderr):
        log.info("nothing to commit for %s", date)
        return True
    _git("pull", "--rebase")
    push = _git("push")
    if push.returncode != 0:
        log.error("git push failed: %s", push.stderr.strip())
        return False
    return True


def build_parser():
    p = argparse.ArgumentParser(prog="advisor.run")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("prepare")
    pr.add_argument("--date", default=_today())
    pr.add_argument("--force", action="store_true", help="rebuild even if already published")
    pr.set_defaults(fn=cmd_prepare)

    pub = sub.add_parser("publish")
    pub.add_argument("--decisions", help="path to the analyst decisions JSON")
    pub.add_argument("--date", default=_today())
    pub.add_argument("--dry-run", action="store_true", help="render a scratch preview, no commit")
    pub.add_argument("--no-push", action="store_true", help="commit/render but do not git push")
    pub.set_defaults(fn=cmd_publish)

    sc = sub.add_parser("score")
    sc.add_argument("--through", type=int, default=None, help="only matchups <= this period")
    sc.set_defaults(fn=cmd_score)

    ck = sub.add_parser("check")
    ck.set_defaults(fn=cmd_check)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
