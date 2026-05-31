"""Advisor configuration: backend re-exports + advisor-specific paths.

Importing the advisor package puts the ``daily_digest`` backend on ``sys.path``
(see ``advisor/__init__.py``). This module re-exports the league constants and ID
utilities the advisor needs, and defines the advisor's own paths split into two
persistence tiers per ``plan.md`` §1.1:

* **Tier 1 — committed** (survives across Routine runs; budget ~few KB/day):
  ``LOG_DIR`` (``decisions.csv``, ``records/``) and the published page under
  ``docs/``.
* **Tier 2 — ephemeral scratch** (gitignored; discarded after the run):
  ``ADVISOR_SCRATCH`` (the day's decision-context JSON + gamelog/HTTP caches).

Idempotency for the unattended run is keyed off committed state
(``docs/archive/<date>.html``), never a scratch marker — a fresh checkout would
not see one.
"""

import os
import sys
from pathlib import Path

# --- Paths + import shim (idempotent; normally already done by advisor/__init__) ---
ADVISOR_DIR = Path(__file__).resolve().parent
IN_SEASON_DIR = ADVISOR_DIR.parent
DAILY_DIGEST_DIR = IN_SEASON_DIR / "daily_digest"
ROOT = IN_SEASON_DIR.parent
if str(DAILY_DIGEST_DIR) not in sys.path:
    sys.path.insert(0, str(DAILY_DIGEST_DIR))

# --- Backend re-exports (bare imports resolve to daily_digest/*) ---
import config as _dd  # daily_digest/config.py
from league import (  # daily_digest/config.py already inserted model/ on sys.path
    HITTING_CATS,
    PITCHING_CATS,
    ALL_CATS,
    LOWER_IS_BETTER,
    NUM_TEAMS,
    ROSTER_SLOTS,
    load_id_map,
    join_ids,
)

SLOT_MAP = _dd.SLOT_MAP
POS_MAP = _dd.POS_MAP
STATS_MAP = _dd.STATS_MAP
SCORING_CAT_IDS = _dd.SCORING_CAT_IDS
PRO_TEAM_ABBREV = _dd.PRO_TEAM_ABBREV
LEAGUE_ID = _dd.LEAGUE_ID
MY_TEAM_ID = _dd.MY_TEAM_ID
ESPN_COOKIES = _dd.ESPN_COOKIES

# Active (non-bench, non-IL) lineup slots and their counts — the roster the daily
# optimizer must fill. Derived from ROSTER_SLOTS minus the BE/IL holding slots.
ACTIVE_SLOTS = {k: v for k, v in ROSTER_SLOTS.items() if k not in ("BE", "IL")}
N_IL_SLOTS = ROSTER_SLOTS.get("IL", 0)
N_BENCH_SLOTS = ROSTER_SLOTS.get("BE", 0)

# --- Tier-1 committed paths (persisted across runs) ---
LOG_DIR = ADVISOR_DIR / "log"
RECORDS_DIR = LOG_DIR / "records"
DECISIONS_CSV = LOG_DIR / "decisions.csv"
DOCS_DIR = ROOT / "docs"
DOCS_ARCHIVE_DIR = DOCS_DIR / "archive"

# --- Tier-2 ephemeral scratch paths (gitignored; discarded after the run) ---
ADVISOR_SCRATCH = Path(os.environ.get("ADVISOR_SCRATCH", str(ADVISOR_DIR / ".scratch")))
GAMELOG_CACHE_DIR = ADVISOR_SCRATCH / "gamelog_cache"


def ensure_log_dirs():
    """Create the Tier-1 committed log dirs on demand."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_scratch():
    """Create the Tier-2 scratch dir tree on demand. Returns the scratch root."""
    ADVISOR_SCRATCH.mkdir(parents=True, exist_ok=True)
    GAMELOG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return ADVISOR_SCRATCH


def scratch_path(name: str) -> Path:
    """Path for a named file in the Tier-2 scratch dir (ephemeral, gitignored)."""
    ensure_scratch()
    return ADVISOR_SCRATCH / name


def context_path(date_str: str) -> Path:
    """Scratch path for a day's decision-context JSON (read by the analyst same run)."""
    return scratch_path(f"decision_context_{date_str}.json")


def archive_page_path(date_str: str) -> Path:
    """Committed path for a day's published page — the cross-run idempotency key (§1.1)."""
    return DOCS_ARCHIVE_DIR / f"{date_str}.html"
