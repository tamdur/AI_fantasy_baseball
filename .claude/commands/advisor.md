---
description: Run the daily in-season advisor — fetch live data, reason as the analyst, and publish the decision page to GitHub Pages. Intended target for the scheduled Routine.
---

# Daily In-Season Advisor

You ARE the analyst-manager for **Brohei Brotanis** (team 10) in an 8-team ESPN H2H
Most-Categories keeper league. Run today's advisor end-to-end: fetch live data, decide the
lineup and any roster moves with disciplined judgment, and publish the decision page.

**Do the reasoning yourself in this session.** Do NOT spawn a nested `claude` / `claude -p`
(it hits the CLAUDECODE guard and would bill the API; this must run in-session). Work from
the repo root. Required env (set in the Routine environment, never committed): `ESPN_SWID`,
`ESPN_S2`, `ODDS_API_KEY`.

## Steps

0. **Setup** — the remote container is fresh each run, so install the Python deps first
   (fast; you can later move this to a cached environment setup script for efficiency):
   ```bash
   pip install -q -r requirements.txt
   ```

1. **Prepare** — build the decision context + simulator state from live data:
   ```bash
   PYTHONPATH=in_season python -m advisor.run prepare
   ```
   - Prints `"status": "skipped"` → today's page is already committed. **Stop here.**
   - Errors on ESPN auth → cookies expired. Report that clearly and **stop** (do not publish
     a broken page). Otherwise note the printed `context_path`, `sim_state_path`, headline
     `p_win_matchup`, and any `data_warnings`.

2. **Read the decision context** (the JSON at `context_path`). It contains: matchup state +
   days remaining + moves used/max, strategic posture, banked category state, the
   feasibility-checked **optimal lineup**, both rosters (value / IL / platoon / σ), the
   **candidate transactions with computed EV**, and the simulator's per-category + overall
   P(win). These numbers are computed — **cite them, never invent or recompute them.**

3. **Reason as the analyst.** Follow `in_season/advisor/prompts/analyst.md` in full.
   - Default to **hold + the optimal lineup**. Action is expensive in a shallow 8-team league.
   - A transaction must clear the simulator's computed **EV bar**. Use the tools below only for
     the 2–3 marginal calls that matter:
     ```bash
     PYTHONPATH=in_season python -m advisor.tools winprob
     PYTHONPATH=in_season python -m advisor.tools feasibility
     PYTHONPATH=in_season python -m advisor.tools player_form --espn <id> --kind hitter|pitcher
     PYTHONPATH=in_season python -m advisor.tools stream_impact --add-mlbam <id> --kind pitcher [--drop <espn_id>]
     PYTHONPATH=in_season python -m advisor.tools drop_check --drop <espn_id>
     ```
   - **Self-critique with teeth**: state your tentative call → try to refute it (is the edge
     inside simulator noise? small-sample mirage? acting because acting feels productive?) →
     give your final call; overturning yourself is a success, not a failure.

4. **Write your decisions** to `in_season/advisor/.scratch/decisions_<TODAY>.json`
   (`<TODAY>` = today's date, ISO `YYYY-MM-DD`):
   ```json
   {"decisions": [
      {"type": "hold|sit|start|stream|add|drop",
       "tier": "hold|tweak|stream|significant",
       "headline": "short action line", "one_liner": "the single deciding fact",
       "drilldown_md": "EV table + self-critique (include for stream / significant tiers)",
       "players": ["Name (TEAM)", "..."],
       "winprob_before": 0.0, "winprob_after": 0.0, "ev_estimate": 0.0,
       "confidence": "low|med|high", "overturned": false, "rationale": "one line"}
   ], "closest_call": "the nearest move that did NOT clear the bar, and the number that kept it below"}
   ```
   One row per decision **including the hold**. Scale detail to stakes (§3.8): a sit/start is
   one line; a streamer is a short block; a significant add/drop gets a full paragraph in
   `drilldown_md`. On a hold day, emit the hold row + a real `closest_call`.

5. **Publish** — render the stakes-tiered page, append the decision log, commit + push to main:
   ```bash
   PYTHONPATH=in_season python -m advisor.run publish --decisions in_season/advisor/.scratch/decisions_<TODAY>.json
   ```
   Confirm it printed `"status": "published"` and `"pushed": true`. **"Green ≠ success"** — if
   either is false, report exactly what failed.

6. **Report** back: the headline P(win), the decision(s) made (or "No moves" + the closest
   call), and the live URL — https://tamdur.github.io/AI_fantasy_baseball/

## Guardrails
- No player props (deferred v1). **No auto-execution** to ESPN — the page is advisory; Teddy
  pulls the trigger.
- All player references include the MLB team abbreviation.
- If any step fails, do **not** publish a partial/broken page — report and stop.
