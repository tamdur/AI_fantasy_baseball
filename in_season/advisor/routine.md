# Advisor Daily Routine

Scheduled ~1:00 AM CT. **This session is the analyst** — you do the reasoning yourself. Do
**not** spawn `claude --print` / nested Claude (it hits the CLAUDECODE guard and risks API
billing; this whole system is MAX-plan-only). Work from `in_season/` (so `advisor` imports);
git runs at the repo root.

## Steps

1. **Prepare.** Run:
   ```
   cd in_season && python -m advisor.run prepare
   ```
   - If it prints `"status": "skipped"` (today's page is already committed), **stop** — the
     run already happened. Idempotency is keyed off `docs/archive/<date>.html`, not a marker.
   - Otherwise it builds the compact decision context + sim state into scratch and prints the
     paths + headline P(win) + any `data_warnings`. If it errors on ESPN auth, the cookies
     expired — surface that clearly and stop (don't publish a broken page).

2. **Read the context.** Open the `context_path` JSON. It has the matchup state, the
   feasibility-checked optimal lineup, both rosters with value/IL/platoon/σ, the candidate
   transactions with **computed EV**, and the simulator's per-cat + overall P(win).

3. **Reason as the analyst.** Follow `prompts/analyst.md` in full. Default to **hold + the
   optimal lineup**. Probe only the 2–3 marginal decisions that matter, using the tools:
   `python -m advisor.tools winprob | feasibility | player_form | stream_impact | drop_check`.
   Do the self-critique-with-teeth. Most days conclude "No moves."

4. **Write your decisions** to a scratch JSON file, e.g. `advisor/.scratch/decisions_<date>.json`:
   ```json
   {"decisions": [
      {"type":"hold","tier":"hold","confidence":"high",
       "winprob_before":0.61,"winprob_after":0.61,"overturned":false,
       "rationale":"set optimal lineup; no move cleared the EV bar"}
   ], "closest_call":"stream Lugo vs SD, +0.006 P(win) — below the ~+0.02 bar; held"}
   ```
   One row per decision (including the hold). For a real add/drop, include `headline`,
   `one_liner`, `drilldown_md` (the EV table + your self-critique), `players`, `ev_estimate`.
   Stakes-scale the detail (§3.8): a sit/start is one line; a significant move gets a paragraph.

5. **Publish.** Run:
   ```
   cd in_season && python -m advisor.run publish --decisions advisor/.scratch/decisions_<date>.json
   ```
   This renders the stakes-tiered page → `docs/`, appends the decision log, writes the daily
   record, and `git pull --rebase` + commit + push the Tier-1 artifacts. "Green ≠ success":
   confirm it printed `"status": "published"` and `"pushed": true`.

## Notes / ops

- **Secrets** (env): `ESPN_SWID`, `ESPN_S2`, `ODDS_API_KEY`. Injected via the Routine env
  config — never committed. If ESPN auth fails, the cookies need refreshing (the hardest ops
  piece; see kb / plan §9 build-time list).
- **Network allowlist:** the hosted Routine must allow ESPN (`lm-api-reads.fantasy.espn.com`),
  FanGraphs, Baseball Savant, `statsapi.mlb.com`, and The Odds API.
- **No props** in v1 (deferred — annotation #4). **No auto-execution** to ESPN: the page is
  advisory; you pull the trigger.
- A dry run (no commit) for testing: `python -m advisor.run publish --decisions <file> --dry-run`
  renders a scratch preview only.
