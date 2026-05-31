# Plan — In-Season Advisor Overhaul

Phase 2 (Plan) per `plans/cc-workflow.md`. Companion to `research.md` (Rev 3) and `kb.md`.
Target subdir: `in_season/advisor/`. **Do not implement until this plan is annotated and approved.**
Author: CC. Date: 2026-05-31.

This plan is grounded in the exact current interfaces (extracted from `config.py`, `model/league.py`,
`ros_werth.py`, `preprocess.py`, `run_newsletter.py`, `fetch_espn.py`, `fetch_extras.py`,
`calibration.py`, `publish.py`, `model/correlated_uncertainty.py`). File:line refs in research.md §2/§8.

---

## 1. Approach

**The one-paragraph version.** Keep the entire data/fetch layer in `in_season/daily_digest/` as a
backend. Build a new `in_season/advisor/` package that is the *judgment + execution* layer. A Python
**prepare** step reuses the existing fetchers + `compute_ros_werth` (with the §4.4 fixes) and adds two
new deterministic engines — a **feasibility/lineup optimizer** (two-way + IL aware) and a **Monte-Carlo
matchup simulator** (bootstrap of recent real game lines, talent overlay) — then writes a **compact
decision context** to a run-scratch path (ephemeral, *not* committed to the repo — full persistence
model in §1.1) and exposes a handful of **thin CLI tools**. The daily run is a **scheduled
Claude Code Routine whose session *is* the analyst**: it runs prepare, reads the compact context, calls
the tools for the 2–3 decisions that actually matter, reasons as itself with a self-critique-with-teeth
pass, writes a **decision-log** row, and renders a published **actionable decision page** (which may be
honestly empty + a "closest call" line). No personas, no nested `claude --print`, no fabricated
P(win) — the probabilities come from the simulator, the arithmetic from code, the judgment from one
mind. (Grounding: research.md §8 D1–D12.)

**Why this fits the system.**
- The data layer is the project's biggest asset and mostly works (research.md §3) → reuse, don't rewrite.
- The judgment failures were structural (publication-to-fill, personas, fabricated precision, no tools)
  → replace exactly that layer (research.md §1).
- The MAX-plan + unattended-Routine constraint *forces* "session-is-the-analyst," which is also the
  judgment design we want — one architecture serves both (research.md §8 D11).
- Deterministic math (feasibility, dilution, banked totals, P(win)) becomes tested code; the model
  never restates a computed fact (kills the `_validate_newsletter` regex hack).

**Tool surface decision: thin CLI subcommands, not MCP.** The analyst calls tools via Bash
(`python -m advisor.tools winprob --add 12345 --drop 67890`), each returning compact JSON. Rationale:
works headless in a Routine with zero MCP-auth friction (research.md D11), trivially testable, cheap on
tokens (the analyst pulls only what it needs). MCP (a committed stdio `.mcp.json` server) is the
fallback if we later want richer typing — noted as a trade-off, not chosen now.

### 1.1 Persistence model under a CC Routine (resolves the §1 / §3.1 "to disk" annotations)

The Routine runs in an **ephemeral checkout of the GitHub repo**. The governing rule: *anything that must
survive to the next run or be seen by Teddy must be `git`-committed and pushed; everything else lives in
run-scratch and is discarded when the environment is torn down.* Three tiers:

**Tier 1 — Committed, persisted state (must survive across runs; budget ≈ a few KB/day, per Teddy):**
- `docs/index.html` + `docs/archive/<date>.html` — the published decision page (already the model; the
  one human-facing artifact).
- `advisor/log/decisions.csv` — append-only decision log, ~0–5 rows/day (well under budget).
- `advisor/log/records/<date>.json` — *optional* compact per-day record (winprob headline + moves +
  closest-call) **capped at a few KB** for audit/calibration. This is the "few-KB JSON in the repo"
  Teddy allows; keep it tight, or skip it if `decisions.csv` already suffices.
- `calibration/actuals.csv` updates at matchup close (already small).

  → Total committed per day stays well within the "few KB" budget. The **full decision context, gamelog
  caches, and raw API dumps are NEVER committed.**

**Tier 2 — Run-scratch (ephemeral; gitignored dir or system temp; discarded after the run):**
- `decision_context_<date>.json` — built by `run prepare`, read by the analyst in the **same run**, then
  discarded. May be tens of KB; never committed. *(This is exactly the "to disk" operation the §1/§3.1
  notes flagged — it's intra-run scratch, not repo state.)*
- gamelog + HTTP JSON caches — potentially large; **within-run only** (cold across runs). The cold-cache
  wall-time cost is accepted (annotation #1; no subprocess timeout per standing constraint).
- Resolved via one `ADVISOR_SCRATCH` dir, default `<repo>/advisor/.scratch/` (gitignored) or
  `$TMPDIR/advisor/`, configurable so local dev and the Routine env agree.

**Tier 3 — Idempotency keyed off COMMITTED state, not a scratch marker.** Because each run is a fresh
checkout, an ephemeral SUCCESS marker would not survive a retry in a new environment. So the cross-run
guard is *"does `docs/archive/<date>.html` already exist (committed)?"* → if yes, skip. (A scratch
SUCCESS marker is still written for the prepare→render handoff within a run, but it is not the cross-run
guard.)

**Git implication:** the Routine needs push credentials and should `git pull --rebase` (or fetch+reset)
before committing, to avoid drift; a single daily writer + tiny diffs = low conflict risk. Commit to
`main` directly or to a dedicated `advisor-output` branch — an ops choice deferred to Phase 5.
`.gitignore` must exclude the scratch dir and all caches.

---

## 2. New package layout

```
in_season/advisor/
  __init__.py
  config.py            # advisor-specific paths/constants; imports daily_digest config + model/league
  context.py           # build_decision_context(): reuse fetchers+WERTH+sim+feasibility → compact JSON
  valuation.py         # §4.4 fixes wrapping/extending ros_werth (regulars-vs-bench, FA-pool replacement)
  feasibility.py       # deterministic lineup optimizer: eligibility, two-way Ohtani, IL slotting
  simulator.py         # bootstrap MC matchup win-prob + EV-of-move (reuses correlated_uncertainty bits)
  gamelogs.py          # NEW fetch: recent per-player game/start logs (MLB Stats API) for the bootstrap
  tools.py             # CLI: `python -m advisor.tools <winprob|stream_impact|player_form|feasibility|...>`
  decisions.py         # decision log (schema + write + process-scoring report)
  render.py            # actionable decision page (adapts daily_digest/publish.py)
  run.py               # `prepare` entrypoint (+ `--dry-run`); writes context to scratch; idempotency
  prompts/
    analyst.md         # the single analyst system prompt (principles, not rigid rules)
  routine.md           # the scheduled Routine prompt (what the Claude session executes)
  log/                 # Tier-1 COMMITTED: decisions.csv, records/<date>.json (≤few KB/day) — §1.1
  .scratch/            # Tier-2 EPHEMERAL (gitignored): decision_context_<date>.json, gamelog/HTTP cache
  tests/
    fixtures/          # tiny synthetic rosters/gamelogs incl. Ohtani + injured star + streamer
    test_feasibility.py  test_simulator.py  test_il.py  test_context.py  test_smoke.py
  research.md  plan.md  kb.md
```

**Import strategy / reuse.** `advisor/` imports the daily_digest backend. Because daily_digest modules
use bare imports (`from config import …`), `advisor/config.py` inserts the daily_digest dir on
`sys.path` once (a small, documented shim), then re-exports what we need. Shared league constants come
from `model/league.py` (already the canonical source: `NUM_TEAMS=8`, `ROSTER_SLOTS`,
`HITTING_CATS/PITCHING_CATS/ALL_CATS`, `LOWER_IS_BETTER`, `load_id_map`, `join_ids`). **Risk flagged in
§6.**

**Reuse vs. new (from research.md §8):**
- *Reuse as-is:* `fetch_espn/fangraphs/savant/mlb/extras/weather`, `http_utils`, `config`, `preprocess`
  (`build_briefing_book`, `compute_category_state`, `_compute_strategic_posture`, `_add_games_remaining`),
  `compute_ros_werth`, `model/correlated_uncertainty.py` (machinery only), `publish.py` (renderer).
- *New:* `feasibility.py`, `simulator.py`, `gamelogs.py`, `tools.py`, `decisions.py`, `context.py`,
  `run.py`, `prompts/analyst.md`, `routine.md`.
- *Retire:* `agents.py` + `prompts/{tactician,actuary,synthesizer,mvp_analyst}.md` (replaced by the
  analyst + Routine); `run_newsletter.py` steps 6/6b/8 (replaced by run.py/decisions/render); the
  `calibration.py` *target* (predictions.csv P(win)-from-prose) → superseded by `decisions.py`.

---

## 3. Key data structures & signatures

### 3.1 Decision context (the compact substrate the analyst reads)
`context.build_decision_context(date) -> dict` written to Tier-2 scratch
`$ADVISOR_SCRATCH/decision_context_<date>.json` (ephemeral, gitignored — §1.1).
Compact (≪ the old briefing book): pre-computed facts + simulator outputs + the deterministic optimal
lineup, so the analyst reasons rather than computes.

```python
{
  "date": "2026-05-31", "matchup_week": 10, "matchup_day": 3, "matchup_length_days": 7,
  "days_remaining": 4, "moves_used": 1, "moves_max": 7,
  "opponent": "...", "strategic_posture": {"posture": "OPTIMIZE", "reason": "..."},

  # Simulator output (the real P(win) — replaces fabricated numbers)
  "winprob": {
    "overall": {"p_win_matchup": 0.61, "record_dist": {"7-5": 0.18, "8-4": 0.12, ...},
                "expected_cats_won": 6.8},
    "by_cat": {"HR": {"p_win": 0.34, "you_proj": 11.2, "opp_proj": 12.9, "banked_you": 6, "status":"live-swing"},
               "ERA": {"p_win": 0.78, ...}, ...}      # status ∈ {clinched, lost, live-swing}
  },

  # Deterministic optimal lineup (feasibility-guaranteed) — analyst confirms/adjusts judgmental swaps
  "lineup_today": {
    "assignments": [{"slot":"UTIL","espn_id":..,"name":"Ohtani","mode":"HIT","plays_today":true}, ...],
    "il_slotted": [{"espn_id":..,"name":"...","il_eligible":true}],
    "bench": [...], "off_today": [...], "two_way": {"espn_id":..,"chosen":"HIT","alt":"PITCH","reason":"..."},
    "judgmental_swaps": [  # the only lineup items needing model judgment
       {"type":"platoon","sit":..,"start":..,"obp_gap":0.05,"cat_affected":"OBP"}],
    "feasible": true
  },

  # Candidate transactions, each with COMPUTED EV (analyst decides whether any clears the bar)
  "candidates": {
    "streamers_today": [{"espn_id":..,"name":"..","vs_team":"..","opp_implied_total":3.6,
                         "stream_impact":{"d_p_overall":+0.018,"d_ERA":-0.01,"d_WHIP":-0.00,
                         "ratio_safe":true},"two_start":false}],
    "adds": [...], "drop_candidates": [{"espn_id":..,"name":"..","healthy_ros_werth":..,
                         "above_replacement":bool,"il_eligible":bool,"injury_status":"DAY_TO_DAY"}]
  },

  # Compact signals (not dumped wholesale)
  "swing_categories": ["HR","QS","SVHD"], "vegas": {"...compact..."},
  "bullpen_changes": [...], "data_warnings": [...]
  # props field removed — deferred entirely for v1 (annotation #4; no free 1am-available source)
}
# PERSISTENCE: this context is Tier-2 RUN-SCRATCH (ephemeral, gitignored), NOT committed — see §1.1.
# Only the rendered page + decisions.csv (+ optional ≤few-KB daily record) are committed to the repo,
# which keeps the per-day repo footprint within Teddy's "few KB" budget.
```

### 3.2 Feasibility / lineup optimizer (`feasibility.py`)
```python
IL_SLOT_ID = 17  # SLOT_MAP

def il_eligible(raw_eligible_slots: list[int]) -> bool:
    """Robust IL test: ESPN marks IL-eligible players with slot 17 in eligibleSlots.
    (Preferred over parsing injuryStatus strings.)"""
    return IL_SLOT_ID in raw_eligible_slots

def optimal_daily_lineup(roster: list[Player], plays_today: dict[espn_id,bool],
                         two_way_ids: set[int], context) -> Lineup:
    """Assign players to ROSTER_SLOTS respecting eligibleSlots (via SLOT_MAP) and who plays today.
    - IL-eligible & injured -> IL slots (off active; do NOT count vs active roster).
    - Two-way entity (Ohtani): ONE slot per day — choose HIT vs PITCH by higher EV (sim); NEVER both.
    - Greedy/bipartite max-value assignment of active players to slots by today's contribution.
    Returns assignments + bench + off_today + two_way choice + judgmental_swaps + feasible flag."""

def lineup_feasibility(assignment: Lineup) -> tuple[bool, str]:
    """Hard checks: every required active slot filled by an eligible, playing player; no player in two
    active slots; two-way not double-slotted; IL slots only hold il_eligible players; no healthy player
    occupying an IL slot (would block adds)."""
```
Note: `fetch_espn._parse_player` currently filters `eligibleSlots` through `REAL_POSITION_SLOTS`
(drops 17). We add a captured `raw_eligible_slots` (or `il_eligible` bool) to the parsed player — a
small additive change in the parse (research.md §4.4 #7).

### 3.3 Simulator (`simulator.py`) — bootstrap + talent overlay (research.md §8 D5, Teddy-corrected)
```python
def player_week_draws(gamelog: GameLog, proj: ProjRates, sigma: dict, games_remaining: int,
                      n: int, rng) -> dict[str, np.ndarray]:
    """n correlated weekly COMPONENT draws for one player, summed over games_remaining.
    Primary: bootstrap real recent game/start COMPONENT lines (hitters: 1B/2B/3B/HR/BB/SB/CS/PA/R/RBI;
             pitchers: IP/ER/H/BB/K/QS) -> draws preserve within-game correlation & PT for free.
    Overlay: shrink the bootstrap mean toward `proj` (projection=anchor, bootstrap=shape); widen by
             `sigma` (from correlated_uncertainty per-player σ) for thin samples / role uncertainty.
    Fallback (call-ups/returnees, <K recent games): draw from proj ± correlated talent noise."""

def simulate_matchup(my_active, opp_active, banked: dict[str,float],
                     games_remaining: dict[espn_id,int], n: int = 200, seed=None) -> WinProb:
    """Sum player COMPONENT draws -> team component totals -> derive the 12 cats (ratios = sum
    components THEN divide; never average ratios). Add `banked` (category_state you/opp).
    P(win_cat) = mean over sims that my_total beats opp_total (respect LOWER_IS_BETTER).
    Overall = distribution of #cats won; p_win_matchup = P(#won >= 7) [or > opp, with tie handling]."""

def ev_of_move(base_active, move: Move, ...) -> dict:
    """Re-simulate with the move applied (add streamer's projected start / drop+add) ->
    {d_p_overall, d_cat:{...}, ratio_safe}. This is the computed bar streaming must clear (D6)."""
```
Reuses from `correlated_uncertainty.py`: `build_cholesky_factor`, `simulate_player_outcomes` shape, the
per-player σ profiles and per-category floors — **as the talent overlay only**, not the primary weekly
generator (the Teddy correction). `n=200` (Teddy). Ignore inter-player correlation v1 (Teddy).

### 3.4 Recent game logs (`gamelogs.py`) — NEW data dependency
```python
def fetch_recent_gamelogs(mlbam_id: int, kind: str, n_games: int = 30|10,
                          season: int = 2026, backfill_season: int = 2025) -> GameLog:
    """MLB Stats API people/{id}/stats?stats=gameLog&group=hitting|pitching&season={season}.
    Hitters: last ~30 healthy games (component lines). Pitchers: last ~10 healthy starts.
    PRIOR-SEASON FALLBACK (annotation #1): if the current-season healthy sample is thin
    (returnees, call-ups, early season), top up from `backfill_season` until the pool reaches the
    target n. Cached in Tier-2 scratch (http_utils JSON cache, within-run only). Healthy filter =
    exclude 0-PA / DNP rows."""
```
This is the one genuinely new external fetch. MLB Stats API is already used (`fetch_mlb.py`), free, and
returns MLBAM IDs (our join key) — low risk, but it's a new call path and a cost on the daily run.
**Wall-time discipline (annotation #1 — "minimize wall time, runs most easily"):** fetch logs only for
**relevant** players — my active roster, the opponent's active roster, and a *bounded* streamer/add
candidate set — never the whole FA universe; within-run cache so a player fetched twice in a run hits
the cache; cold across runs is accepted (the cache is Tier-2 scratch, not committed). No subprocess/HTTP
timeout caps (standing constraint); the 1am batch window absorbs the cost.

### 3.5 Decision log (`decisions.py`) — replaces the calibration target (D9)
```
advisor/log/decisions.csv  (Tier-1 committed, append-only, ~0–5 rows/day — §1.1)  columns:
  date, decision_id, matchup_period, type{start|sit|stream|add|drop|hold},
  tier{tweak|stream|significant|hold},      # drives render density (§3.8)
  players, winprob_overall_before, winprob_overall_after, ev_estimate,
  confidence_qual{low|med|high},            # qualitative is the headline (annotation #6);
                                            #   rationale may cite p_win/Δ quantities where they help
  overturned_by_selfcritique(bool), rationale_ref, realized_outcome   # realized filled at matchup close
```
```python
def log_decisions(context, analyst_decisions: list[Decision]) -> None
def score_process(through_matchup: int) -> str   # confidence calibration + EV-vs-realized + vs baselines
```

### 3.6 The analyst (`prompts/analyst.md`) — one mind, principles not rules
Skeleton (full prompt in implementation): role = expert in-season manager for THIS league; **default =
hold / keep the optimal lineup**; any transaction must clear the simulator's computed EV bar; reason
with the §7 principles (Vegas-symmetric, ratio-aware streaming, contest-structure variance, swing-cat
plan, IL-savvy, opportunity-cost-weighted) as *judgment*, not thresholds; **self-critique with teeth**
(state tentative call → refute → possibly-changed final call + note if overturned); tools available via
Bash; output = the actionable decision (lineup confirmation + 0..n transactions + watching + closest
call if empty) + the decision-log rows. No fabricated numbers — cite simulator/tool outputs.

### 3.7 Execution (`routine.md` + `run.py`)
Routine prompt instructs the session to: `python -m advisor.run prepare` (writes the context to Tier-2
scratch) → read `decision_context_<date>.json` from scratch → reason (analyst.md) using `advisor.tools`
→ append rows to `advisor/log/decisions.csv` → `python -m advisor.render` → `git pull --rebase` then
commit/push the **Tier-1** artifacts (`docs/` page + `decisions.csv` + optional `records/<date>.json`).
**Idempotency is keyed off committed state** (§1.1 Tier 3): skip the run if `docs/archive/<date>.html`
already exists. `run.py --dry-run` does everything except the `git` push (renders to scratch, no commit).

### 3.8 Decision page — stakes-scaled detail + the drill-down mechanism (annotation #5)

**Principle (Teddy): every published action carries enough to decide, and detail scales with stakes.**
Four tiers, by how consequential / reversible the move is:

- **Lineup tweak / sit–start (low stakes):** ONE line. `Sit Rooker (UTIL) vs LHP — start Meneses. OBP
  gap −.048 today.` Action + the single deciding fact. No paragraph.
- **Streamer add (medium stakes):** a 2–3 line block — the pickup + opponent/Vegas total + the
  **computed** Δ (e.g., `+0.018 P(win); QS lean +0.4; ratios safe`) + the drop and why it's the worst
  roster spot + moves remaining (`4 of 7 left`).
- **Significant add/drop (high stakes — dropping a real player, a multi-cat swing, anything near the
  ~24h-irreversible line):** a full **paragraph** — the EV case, the opportunity cost, the
  **self-critique** (what would make this wrong), and qualitative confidence. This is where the
  reasoning lives.
- **Hold day (no moves):** `No moves.` + ONE "closest call" line — the candidate nearest the bar and the
  number that kept it below (e.g., `Closest: stream Lugo vs SD, +0.006 P(win) — below the +0.02 bar;
  held.`).

**Drill-down mechanism (the part the annotation asked me to detail).** The page is static HTML published
to GitHub Pages (no JS runtime), so "drill-down" = **native progressive disclosure via
`<details>`/`<summary>`**, not a custom widget:
- The **headline action + one-line rationale** is the always-visible `<summary>`.
- The **supporting numbers** — per-cat Δ table, bootstrap sample size, opponent's banked totals, the
  alternatives considered and their EV — live in the collapsed `<details>` body: one click to expand,
  zero JS, works on mobile, prints cleanly.
- **Stakes decide how much goes in the body, but the mechanism is constant.** A sit/start has an empty
  or one-number drill-down; a significant add/drop has the full EV table + self-critique. So the page
  *scans* in ~10 s (all headlines visible, fixed density) while depth is opt-in per item.
- `render.py` emits one `<details>` block per decision. The analyst's decision-log row supplies both the
  `<summary>` (headline + one-liner) and the `<details>` body (the numbers it cited). **Nothing is
  fabricated** — the body is the same simulator/tool output the analyst already used.

**`render.py` contract:** input = the analyst's decisions, each shaped
`{tier, headline, one_liner, drilldown_md}` + the winprob header; output = a page where the top-level
scan is all headlines and depth is one `<details>` click away, with the "closest call" as a first-class
element on empty days. The four tiers map to `tier ∈ {tweak, stream, significant, hold}` so the renderer
picks the right density automatically.

---

## 4. File changes (concrete)

| File | Change | Role |
|---|---|---|
| `advisor/config.py` | NEW | sys.path shim to daily_digest; re-export SLOT_MAP/ROSTER_SLOTS/cats; advisor paths |
| `advisor/context.py` | NEW | `build_decision_context()` — orchestrates fetch→WERTH(§4.4)→sim→feasibility→compact JSON |
| `advisor/valuation.py` | NEW | wraps `compute_ros_werth`; §4.4 #1 regulars-vs-bench pool; #2 per-player σ band; #3/#4 FA-pool replacement |
| `advisor/feasibility.py` | NEW | IL classification (slot 17), two-way slotting, optimal daily lineup, feasibility checks; §4.4 #6 platoon magnitude, #8 games-remaining |
| `advisor/simulator.py` | NEW | bootstrap weekly draws + talent overlay; `simulate_matchup`, `ev_of_move` |
| `advisor/gamelogs.py` | NEW | recent per-player game/start logs (MLB Stats API) |
| `advisor/tools.py` | NEW | CLI: winprob / stream_impact / player_form / feasibility / drop_check |
| `advisor/decisions.py` | NEW | decision-log schema (+ `tier`) + write to committed `advisor/log/decisions.csv` + `score_process` |
| `advisor/render.py` | NEW | stakes-tiered decision page + `<details>` drill-down (§3.8); wraps `publish.publish_newsletter` renderer |
| `.gitignore` | MODIFY | exclude `advisor/.scratch/` + caches (Tier-2 ephemeral — §1.1) |
| `fetch_extras.py` | MODIFY (additive) | §4.4 #5 current-season park-factor refresh path |
| `advisor/run.py` | NEW | `prepare` + `--dry-run`; idempotency keyed off committed `docs/archive/<date>.html` (§1.1) |
| `advisor/prompts/analyst.md` | NEW | single analyst system prompt |
| `advisor/routine.md` | NEW | the scheduled Routine prompt |
| `fetch_espn.py` `_parse_player` | MODIFY (additive) | capture `raw_eligible_slots`/`il_eligible` (don't drop slot 17) |
| `daily_digest/agents.py` + 4 prompts | RETIRE (leave in place, unused) | replaced; not deleted (archive, don't delete) |
| `advisor/tests/*` | NEW | smoke fixture + unit/property/regression tests |

Out-of-scope-to-change (kept as backend): all other `fetch_*` (except the additive `fetch_extras`
park-refresh, §4.4 #5), `preprocess.py`, `ros_werth.py` core, `correlated_uncertainty.py`,
`http_utils.py`, `publish.py` internals. Backend changes are strictly *additive* (new optional fields),
never signature-breaking — preserves the daily_digest pipeline if we ever need it.

### 4a. The eight §4.4 fixes — all in scope for v1 (annotation #3)

Each lands with its test green before the next ("validate along the way"). They cluster naturally by
module, so they fold into the existing phases rather than a separate workstream.

| # | Fix (research.md §4.4) | Lives in | Phase | Test / assertion |
|---|---|---|---|---|
| 1 | Starter pool conflates regulars & bench → weight/filter pool by projected PT / lineup role | `valuation.py` (wraps `compute_ros_werth`) | P2 | `test_context.py`: pool excludes bench scrubs; replacement level shifts vs naive |
| 2 | Surface the already-computed multi-system disagreement as a per-player σ band (currently dead) → feeds analyst **and** simulator overlay | `valuation.py` → context `players[].sigma_band`; consumed by `simulator` | P2 | `test_simulator.py`: σ band present; widens thin-sample draws |
| 3 | Hitter/pitcher DV bias → anchor replacement level to the **observed in-season FA pool** (YTD+RoS), supersedes pre-season floors; **subsumes #4** | `valuation.py` (FA-pool replacement) | P2 | `test_context.py`: replacement from observed FA pool; H/P DV gap narrows |
| 4 | Replacement = single best FA → (N+1)-th-best / small-average from the observed FA pool | `valuation.py` (folded into #3) | P2 | same fixture as #3 |
| 5 | Park factors stale (2024) → refresh from current-season FanGraphs guts | `fetch_extras` refresh path / `context.py` | P1 | smoke: park-factor dict current-season; ratio-safety uses it |
| 6 | Platoon split **magnitude**, not just an "extreme" boolean → optimizer needs the gap | `_parse_player` + `context.py`; consumed by `feasibility.judgmental_swaps` | P0→P1 | `test_feasibility.py`: platoon swap uses the OBP magnitude |
| 7 | IL-eligibility flag in the data layer (slot 17) | `fetch_espn._parse_player` (additive) + `feasibility.il_eligible` | P0→P1 | `test_il.py` |
| 8 | Games-remaining / two-start drives the **deterministic** feasibility pre-pass (not model-reasoned) | `feasibility.optimal_daily_lineup` + `context` | P1 | `test_feasibility.py`, smoke |

Note #3 supersedes #4 (one observed-FA-pool replacement computation satisfies both). All eight are
deterministic data/valuation fixes — none touches the analyst's judgment surface.

---

## 5. Test plan (cc-workflow spirit — domain fixtures, not geospatial)

**Smoke fixture + smoke test (`tests/test_smoke.py`, runs < 1 min, the highest-ROI test):**
A tiny synthetic context: 1 matchup, ~6 of my players incl. **Ohtani (two-way)**, **an injured
top-60 star** (IL-eligible), **a DTD marginal player**, **a streamer FA**, **a normal bat**; ~6 opponent
players; fixed RNG seed; tiny synthetic gamelogs. Asserts invariants: (a) optimal lineup is **feasible**;
(b) Ohtani is in exactly one active slot, never UTIL+P; (c) the IL star is in an IL slot (off active),
the DTD marginal player is not IL-slotted; (d) simulator returns per-cat `p_win ∈ [0,1]`, overall
record-dist sums ≈ 1, deterministic under the seed; (e) `ev_of_move` for the streamer returns finite
`d_p_overall`; (f) the decision page renders to HTML with a non-empty "closest call" on a hold day.

**Unit tests:**
- `test_il.py`: `il_eligible([…,17])` True / without 17 False; healthy-in-IL-slot → feasibility fails
  (blocks-adds condition surfaced).
- `test_feasibility.py`: Ohtani either/or (cannot double-slot); eligibleSlots respected via SLOT_MAP;
  off-day player not assigned to active slot; MI/CI/UTIL flex resolution.
- `test_simulator.py`: ratio cats aggregate components **then** divide (golden check vs hand calc);
  banked totals added once (no double-count); `LOWER_IS_BETTER` handled; reproducible under seed.
- `test_context.py`: ID-bridge coverage (no silent WERTH=0 for rostered players → assert match rate),
  compact-context keys present, swing-category classification.

**Property tests (`hypothesis`):** `p_win ∈ [0,1]`; adding a strictly-dominant player never *decreases*
`p_win_matchup` beyond MC noise (monotonicity, tolerance from n=200); more games-remaining → wider
component spread; empty-move day always renders a valid page.

**Regression fixture:** golden `simulate_matchup` output for fixed seed + fixed fixture inputs; assert
closeness with explicit `atol` (e.g., p_win within ±0.03 at n=200, or n=5000 for the golden lock).

**Scheduled-run dry-run:** `python -m advisor.run --dry-run` executes prepare→(stub analyst)→render
locally without publish/commit and asserts a SUCCESS marker + valid artifacts. Plus a **documented
manual Routine test** (one real 1am-style run) before trusting automation — the draft-tool day-of bug
(research.md §4.3) is the cautionary precedent.

---

## 6. Domain & numerical risk list (adapted checklist)

- **ID-bridge staleness → silent WERTH=0** (research.md §5): `test_context.py` asserts rostered-player
  match rate ≥ threshold; warn on misses.
- **ESPN two ID systems** + **IL via slot 17, not string parsing** (more robust than `injuryStatus`,
  whose raw values ACTIVE/INJURY_RESERVE/DAY_TO_DAY/OUT are ambiguous for "OUT today" vs "on IL"). Verify
  against live data in the manual Routine test.
- **Two-way double-slot** — hard feasibility check + smoke fixture.
- **Rate-stat aggregation** — always sum components then divide; never average ERA/WHIP/OBP/KBB across
  players or games (the classic error; `_convert_rate_stats` already does counting-equivalents for
  WERTH, but the *simulator* must aggregate components directly).
- **Bootstrap small-sample** — explicit fallback to projection ± talent noise; log which path used.
- **Banked + remaining double-count** — add `category_state` exactly once; assert in tests.
- **RNG determinism** — seed per run (record the seed in the decision context); tests use fixed seeds.
- **SVHD lumpiness** — bootstrap is crude for saves/holds; lean on `closer_roles`; flagged v1 weakness.
- **Timezone / 1am cadence** — "today's games" computed in the right TZ; no confirmed lineups, no
  re-check (research.md §9b.5). Vegas uses 1am data (props deferred — annotation #4).
- **Ephemeral-checkout persistence** (§1.1) — only Tier-1 artifacts are committed; idempotency is keyed
  off the committed `docs/archive/<date>.html`, **not** a scratch marker (a scratch marker wouldn't
  survive a retry in a fresh environment). Scratch dir + caches are gitignored.
- **Routine env** (research.md D11): network allowlist (add ESPN/FanGraphs/Savant/MLB/Odds domains),
  secrets via env config (ESPN cookies, ODDS_API_KEY), **no nested `claude --print`**,
  "green ≠ success" → verify Tier-1 artifacts exist before declaring success.
  **Verify MAX-plan Routine billing is subscription at build time.**
- **Git push-back from the Routine** — needs credentials + `pull --rebase` before commit to avoid drift
  (single daily writer, tiny diffs → low conflict risk); `main` vs `advisor-output` branch is a Phase-5
  ops choice.
- **MAX-only** — no paid API anywhere; all reasoning is the Routine session.
- **sys.path shim** to import daily_digest — keep it one place; risk of import-order surprises; covered
  by a context import smoke test.

---

## 7. Validation plan (is the advice *right*, separate from the code being correct?)

- **Simulator calibration backtest:** replay completed matchups (we have `calibration/actuals.csv` +
  `category_state` history) → does the simulator's pre-matchup per-cat P(win) match realized win rates
  (reliability by decile)? This validates the keystone before we trust its EV bar.
- **Baseline comparison (process-scored):** compare the advisor's logged decisions against a **naive
  "set best feasible lineup, never transact"** baseline on realized category outcomes. Bar = "beats the
  naive baseline," not "any signal." (The old pipeline is retired and is *not* a comparison target —
  annotation #7.)
- **Decision-log calibration over time** (D9): confidence{low/med/high} vs realized hit rate; EV
  estimate vs realized Δ; fraction of moves overturned by self-critique (sanity that skepticism bites).
- **Sanity checks:** simulator mean cat totals ≈ projection×games_remaining + banked; a clinched cat
  shows P(win)→1; a streamer that improves ratios shows `d_p_overall > 0`.

---

## 8. Considerations & trade-offs

- **One analyst vs. multi-agent** (chosen: one): simpler, cheaper, no fake debate; self-critique gives
  the adversarial benefit without fragmenting judgment (research.md D2).
- **CLI tools vs. MCP** (chosen: CLI): zero Routine-auth friction, testable, cheap; MCP deferred.
- **Bootstrap vs. parametric simulator** (chosen: bootstrap): captures real sampling variance +
  cross-cat correlation for free; parametric/Gaussian-talent is the wrong generator (Teddy, D5).
- **Deliberately not doing:** player props **entirely** (no free source at the 1am cadence — annotation
  #4, research §7.4c); trade suggestions; auto-execution to ESPN (stays advisory); parameterizing the
  league for other formats; inter-player correlation in the sim (v1). *(Park-factor refresh is now IN
  scope — §4.4 #5; all eight §4.4 fixes ship in v1 per annotation #3.)*
- **Direct cutover, no shadow week (annotation #7):** the old pipeline is useless and won't be
  maintained; the advisor replaces it directly. Safety gate = the manual Routine dry-run (§5) + the
  smoke/calibration tests, **not** a parallel shadow comparison. Old files (`agents.py`,
  `run_newsletter.py`, the 4 prompts) are left in place but deprecated/unused (archive-don't-delete) —
  not kept running.
- **New dependency:** recent game logs (MLB Stats API) — small but real added fetch + runtime.
- **Phasing risk:** the simulator (P2) and feasibility (P1) gate most value; do them first and test hard.

---

## 9. Resolved in annotation round 1 (Teddy)

1. **Game-log source / window:** MLB Stats API `gameLog` (free; returns MLBAM IDs). **Optimize for wall
   time / ease of running** over source purity. Window: hitters last ~30 games, pitchers last ~10
   starts; **fall back to prior season (2025)** when the current-season healthy sample is thin. Fetch
   only relevant players; within-run cache; cache is scratch, not committed. (§3.4, §1.1.)
2. **Hosting:** hosted **Claude Code Routine** (not local cron). This is what drives the §1.1
   persistence model — git push for state, network allowlist + env secrets in Phase 5.
3. **§4.4 scope:** do **all eight** fixes, each landed with its test green before the next. None
   deferred. Enumerated and phase-assigned in **§4a**.
4. **Player props:** **deferred entirely** for v1 — no free source at the 1am cadence. Removed from the
   context schema (§3.1) and the phase plan; revisit only if a free game-day-AM source appears.
5. **Decision-page detail:** **stakes-scaled** — one line for a sit/start, a short block for a streamer,
   a full paragraph for a significant add/drop, "No moves + closest call" on a hold day; **drill-down
   via native `<details>` progressive disclosure** (headline always visible, numbers one click away, no
   JS). Full design + the requested drill-down explanation in **§3.8**.
6. **Confidence:** qualitative **{low/med/high}** is the headline; the rationale may cite simulator
   quantities (p_win, Δ) where they help. No schema change — `confidence_qual` stays (§3.5).
7. **Cutover:** **direct** — the old pipeline is retired, not maintained, no shadow week. Safety gate =
   manual Routine dry-run + tests (§5, §8). Old files archived-in-place, not deleted.

### Still genuinely open — verify at BUILD time (not plan-blocking)
- MAX-plan Routine billing is subscription (no per-token API metering) — confirm before trusting the
  unattended path.
- Hosted-Routine outbound network allowlist covers ESPN / FanGraphs / Savant / MLB Stats / Odds domains.
- ESPN cookie (`ESPN_SWID` / `ESPN_S2`) auto-refresh design — the hardest ops piece; injected via env.
- Live ESPN settings: Ohtani single-entity either/or model + exact IL-eligible slot-17 designations
  (verify against live data in the manual Routine test).
- Git push from the Routine: credentials + `pull --rebase` before commit; `main` vs `advisor-output`
  branch (§1.1).

---

## 10. Todo list (phased; CC marks complete during implementation)

**Phase 0 — Scaffolding & context backbone**
- [ ] `advisor/__init__.py`, `advisor/config.py` (sys.path shim, re-exports, **`ADVISOR_SCRATCH`** +
      Tier-1 committed-log paths per §1.1)
- [ ] `.gitignore`: exclude `advisor/.scratch/` + all caches
- [ ] `advisor/context.build_decision_context()` v0: reuse fetch→`compute_ros_werth`→preprocess → compact
      context written to **Tier-2 scratch** (no sim/feasibility yet); import smoke test
- [ ] Additive `fetch_espn._parse_player`: capture `raw_eligible_slots` / `il_eligible` (§4.4 #7) +
      platoon-split magnitude (§4.4 #6)

**Phase 1 — Deterministic feasibility + lineup (highest correctness risk)**
- [ ] `feasibility.il_eligible`, `optimal_daily_lineup`, `lineup_feasibility` (two-way + IL); consume
      games-remaining (§4.4 #8) + platoon magnitude (§4.4 #6)
- [ ] `tests/test_il.py`, `tests/test_feasibility.py`; Ohtani + IL fixtures
- [ ] §4.4 #5 park-factor refresh (data fix + test)

**Phase 2 — Valuation fixes + matchup win-probability simulator (keystone)**
- [ ] `valuation.py`: §4.4 #1 regulars-vs-bench pool, #3+#4 FA-pool replacement, #2 surface per-player σ
      band — each with `test_context.py` assertions (validate-along-the-way, annotation #3)
- [ ] `gamelogs.fetch_recent_gamelogs` (within-run cache, prior-season fallback, relevant-players-only)
- [ ] `simulator.player_week_draws` (bootstrap + talent overlay via #2 σ + fallback)
- [ ] `simulator.simulate_matchup`, `ev_of_move`; reuse correlated_uncertainty σ/Cholesky as overlay
- [ ] `tests/test_simulator.py` + property + regression-golden; **calibration backtest** (§7)

**Phase 3 — The analyst + tools**
- [ ] `tools.py` CLI subcommands (winprob, stream_impact, player_form, feasibility, drop_check)
- [ ] `prompts/analyst.md` (principles, default-hold, self-critique-with-teeth, **stakes-scaled output**)
- [ ] wire candidates + computed EV (D6 bar) into context

**Phase 4 — Decision page + decision log**
- [ ] `decisions.py` (schema incl. `tier`, `log_decisions`, `score_process`); committed
      `advisor/log/decisions.csv` (+ optional ≤few-KB `records/<date>.json`) per §1.1
- [ ] `render.py` (stakes-tiered page + `<details>` drill-down + empty-with-closest-call; reuse publish
      renderer) — §3.8

**Phase 5 — Execution as Routine + ops**
- [ ] `run.py` (`prepare`, `--dry-run`, **idempotency keyed off committed `docs/archive/<date>.html`**,
      scratch handoff marker)
- [ ] `routine.md` (the Routine prompt); no nested `claude --print`
- [ ] git push-back (credentials, `pull --rebase`, branch choice); ESPN cookie auto-refresh;
      network-allowlist + secrets doc; **manual Routine dry-run**
- [ ] build-time verifications (§9 open list); validation: naive-baseline comparison + decision-log
      calibration scaffolding

**Phase 6 — Explicitly deferred (NOT v1)**
- [ ] player props (no free 1am source) — revisit only if a source appears
- [ ] inter-player correlation in the simulator
- [ ] MCP tool surface (only if richer typing is ever wanted)
```
