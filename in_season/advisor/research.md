# Research — In-Season Advisor Overhaul

Status: Phase 1 (Research) per `plans/cc-workflow.md`. This document is the review surface.
Target subdir: `in_season/advisor/`. Mode: research-only (no implementation).
Author: CC. Date started: 2026-05-31. **Rev 2 (2026-05-31): incorporated Teddy's annotations — every
`USER:` note is addressed inline (`> ✅ CC:`), the resolved decisions are consolidated in §9, and three
new research tracks (scheduled-Routine execution, IL/two-way/Vegas-pitching, the existing uncertainty
engine) are folded into §§4,7,8.**
**Rev 3 (2026-05-31): second annotation round — corrected the simulator method (sampling vs talent
uncertainty; bootstrap recent real lines — §8 D5), corrected the IL/bench-stash rule (§7.13),
in-season empirical replacement-level renorm (§4.4 #3), self-critique-with-teeth (§8 D2), no morning
re-check (§9b.5), and added player-props research (§7.4c).**

> Note on the workflow: we're following the *spirit* of `cc-workflow.md` (research → plan → annotate →
> implement; never implement before plan approval), not its geospatial specifics. The eventual Plan's
> test/validation section will use domain-appropriate smoke fixtures — Ohtani two-way slotting, IL
> eligibility, a scheduled-run dry-run, win-probability-simulator sanity checks — not CRS/units/dtype
> checks. (Per Teddy's §0 annotation.)

---

## 0. Problem framing (proof of understanding)

### The task in my own words

We previously built an in-season "daily newsletter" pipeline (`in_season/daily_digest/`) for an
8-team ESPN H2H Most-Categories keeper league. It fetches live data, computes a WERTH (z-score)
valuation, assembles a JSON "briefing book," and runs three fixed-persona Claude agents
(**Tactician → Actuary → Synthesizer**) that emit a daily newsletter published to GitHub Pages.

Teddy **abandoned** it for two stated reasons:

1. **A crippling bias toward action** → over-churn → poor decisions. The system kept finding things
   to do, and doing things in an 8-team league (where drops are claimed instantly and replacement
   level is high) is mostly downside.
2. **Performative personas limited Claude's judgement.** Forcing the model into theatrical roles
   ("You are the Category Tactician…") with mandated output sections made it *perform analysis*
   rather than *think*. He wants a system where CC works "at its analytical and thoughtful best
   self," producing genuinely excellent daily recommendations — not a model playing a character to
   fill a template.

So the overhaul's job is to redesign the **decision/judgment/output layer** so that:

- "Do nothing" is the structurally easy, performatively-cheap default — not a paragraph the model
  has to argue for inside an action-shaped template.
- The model reasons as itself, with real tools and the ability to investigate, instead of one-shotting
  a giant structured document from a static JSON blob under a persona.
- The recommendations are grounded in actual best practice for in-season fantasy management.
- Deterministic computation (valuation, category math, eligibility, schedule) is reliable **code**;
  judgment under uncertainty is the **model's** job. The two are currently blurred.
- **It runs reliably, unattended, as a scheduled Claude Code Routine** (once daily, 1am CT) — the
  prior system was never automated and the execution environment imposes real constraints (§8 D11).

### What "done" looks like for the *whole project* (not this research phase)

A daily in-season advisor that Teddy trusts: it sets the lineup well every day, proposes transactions
only when they clear a real bar, says "nothing to do, here's what I'm watching" without ceremony when
that's correct, runs itself on schedule without babysitting, and whose decisions are logged and scored
on process so we can see whether it's actually good. Measured by: fewer, better transactions;
calibrated confidence; reliable unattended runs; and Teddy *using* it.

### What "done" looks like for *this research phase*

This document + `kb.md`, good enough that (a) a fresh CC instance could resume from
`cc-workflow.md` + `research.md` + `kb.md` alone, and (b) Teddy can annotate it to steer the Plan
phase. **No code, no final architecture commitment** — though Teddy's Rev-1 annotations have now
*resolved* most of the big architectural questions (§9), so the Plan can be concrete.

### Scope

**In scope (overhaul target):**
- The agent/judgment layer (`agents.py`, `prompts/*`).
- The output medium and framing (kill the "newsletter," keep a published actionable decision page —
  §8 D1).
- The run orchestration as it pertains to decision-making (`run_newsletter.py` steps 5b/6/6b).
- The decision-logging / calibration philosophy (`calibration.py`).
- How deterministic computation is split from model judgment.
- **Scheduled-Routine execution + unattended reliability** (NEW, per Teddy): research, testing, and
  validation so the whole thing runs cleanly as a Claude Code Routine kicked off on schedule. The
  scheduled virtual environment has constraints (auth, network allowlist, secrets, no nested
  `claude` subprocess, idempotency) that have bitten Teddy before. See §8 D11.
- **ESPN cookie auto-refresh + operational reliability** (NEW, per Teddy OQ10): moved from "separate
  track" into scope — the advisor must survive cookie expiry and run unattended.
- **Targeted "low-hanging fruit" improvements to the reused data/valuation layer** (NEW, per Teddy):
  not a full rewrite, but naming and fixing cheap, high-value defects (e.g., WERTH not distinguishing
  regulars from bench). See §4.4.

**Out of scope (keep / reuse, treat as a dependency — except the §4.4 cheap fixes):**
- The data-fetching layer is genuinely valuable and mostly worth keeping: `fetch_espn.py`,
  `fetch_fangraphs.py`, `fetch_savant.py`, `fetch_mlb.py`, `fetch_extras.py`, `fetch_weather.py`,
  `http_utils.py`, `config.py`.
- The valuation engine `ros_werth.py` and `preprocess.py` ID-bridging — reusable, though their
  *outputs*, how they're handed to the model, and the §4.4 cheap fixes are in scope.
- The pre-draft model (`model/`) and draft tool — not touched, **except** `model/correlated_uncertainty.py`
  is a reuse *source* for the in-season simulator (§8 D5).

**Explicit non-goals:** not rebuilding the projection/valuation methodology from scratch in this pass;
not adding auto-execution of moves to ESPN (the system stays advisory — Teddy confirmed OQ9 he wants
"actionable information," but a human still pulls the trigger).

### Constraints Teddy has set (this session + standing)

- MAX plan: call Claude via Claude Code, **never the paid API** (napkin / MEMORY). **This now has a
  sharp architectural consequence** — see §8 D11: the unattended run should be a Claude Code *Routine
  session that does the reasoning itself*, not Python shelling out to `claude --print` (which risks
  API-rate billing and the nested-session guard).
- Don't add subprocess timeouts on Claude calls — deep analytical work takes as long as it takes
  (MEMORY: `feedback_no_timeouts`).
- Python for tooling. All player references carry MLB team abbreviation.
- **One daily run, assume 1am CT** (Teddy OQ6). Implication to carry: at 1am CT the day's *probable
  pitchers* are known (good for streaming/SP decisions) but *confirmed batting orders* are not
  (posted hours before first pitch), and *Vegas lines* are early — so platoon/sit calls and implied
  totals use early data and can't react to late scratches (§7.4 caveat).
- Follow `cc-workflow.md` in spirit (research → plan → **annotate** → implement; never implement
  before the plan is approved).
  > ✅ CC: Acknowledged — adapting the spirit, not the geospatial letter (see top-of-doc note).

---

## 1. Core diagnosis — why the old system pushed toward action and performance

Teddy's two complaints are correct, and they're **architectural, not just prompt-wording** problems.
The prompts actually contain a *lot* of well-intentioned anti-churn language (see §1.3) — which is
exactly the tell: the anti-action guardrails are bolted onto a machine whose every structural
incentive points at action and performance. You can't fix that with more guardrail paragraphs.

### 1.1 The output is a *newsletter* — a daily publication that must be filled

The system's deliverable is a newsletter published to GitHub Pages every day
(`run_newsletter.py` → `agents.generate_newsletter()` → `publish.py`). A newsletter is a *performance
artifact*: it exists to be read, it has a masthead, tiers, a dashboard, emojis, a "60-second scan,"
and an Appendix. A publication that goes out daily creates structural pressure to **have content
every day**, independent of whether any decision is warranted. The medium *is* the bias.

The synthesizer prompt even tries to fight its own medium — "'No moves today' newsletters should still
be substantive… The dashboard, roster health, and opponent intelligence are valuable daily"
(`prompts/synthesizer.md:205`). That's the machine apologizing for existing on a day when the right
answer is "nothing to do." The honest output on a quiet day is one line; the newsletter format makes
one line feel like a failure, so the model performs thoroughness to fill the page.

### 1.2 Three fixed personas turn judgment into theater

`agents.py` instantiates three characters:

- **Tactician** (`prompts/tactician.md:3`) — "You are the **Category Tactician**." Its literal,
  stated purpose is to find moves: "This is where moves go. Every transaction should target an ATTACK
  category" (`tactician.md:65`); the daily lineup section "should be the most detailed section of
  your analysis" (`tactician.md:88`). A persona whose identity is *tactics* will always find tactics.
- **Actuary** (`prompts/actuary.md:3`) — "You are the **Actuary**… the counterbalance to aggressive
  tactical moves." Its identity is to veto. It must "Generate Risk Cards for each plausible add/drop
  move" (`agents.py:89`) — i.e., enumerate moves even to reject them, which still centers moves.
- **Synthesizer** (`prompts/synthesizer.md`) — staples the two together into tiers.

This is a *simulated debate*, and a fake one: the Tactician and Actuary never actually talk. They run
**in parallel** as independent one-shot calls (`agents.py:148`, `ThreadPoolExecutor(max_workers=2)`),
each seeing only the static briefing book, and the Synthesizer reads their two essays after the fact
(`agents.py:100-131`). There is no deliberation, no back-and-forth, no ability for one to ask the
other a question. The "two perspectives" are a rhetorical device, not a reasoning process. Worse, the
personas **fragment** one coherent judgment across three context-limited calls that can't converge —
the opposite of "one mind thinking carefully."

This is the heart of Teddy's "performative personas limited its judgement" complaint: the model is
cast as a character with a mandated viewpoint and a mandated multi-section script, so it *acts the
part* (the Tactician dutifully finds flips; the Actuary dutifully writes risk cards) instead of
forming the single best judgment a smart analyst would.

### 1.3 The anti-churn patches prove the architecture fights itself

Every prompt has substantial "do nothing is the default" machinery:
`tactician.md:26-30` ("The Default Recommendation Is No Moves"), `actuary.md:7-13` ("What is the
expected value of doing nothing?"), Trap 9 "The Action Bias" (`actuary.md:219-221`), the
Synthesizer's "Cardinal Rule: No Transactions Is the Default" (`synthesizer.md:17-27`) and "Anti-Churn
Guardrail" (`synthesizer.md:101-107`). The napkin even records a prior fix:
"[2026-03-26] Agent prompts have structural action bias — 'no moves' must be the default."

So the bias was already recognized and patched **at the prompt level** — and Teddy still abandoned the
project for over-churn. The lesson: **prompt-level "please don't churn" cannot overcome a machine
built to produce a daily action-shaped publication via action-shaped personas.** The overhaul must
remove the structural pressure, not add a sixth anti-churn paragraph.

### 1.4 Mandated false precision is its own kind of performance

The prompts demand quantitative outputs the model has no real basis to produce, then ask it to do
arithmetic it does poorly:

- "estimate P(win) for each category" and "Confidence: X/10" treated as **calibrated** predictions
  (`tactician.md:75`, `synthesizer.md:74-83`). The model is inventing probabilities. They *feel*
  rigorous and get logged to `calibration/predictions.csv`, but they're vibes dressed as numbers.
- "compute rate-stat dilution for every pitching recommendation" — the model is asked to do
  `(ER+er)/(IP+ip)*9` by hand in prose (`tactician.md:171-178`, `actuary.md:99-107`). LLMs are
  unreliable at this; it belongs in Python.
- Dozens of hardcoded heuristic thresholds stated as law: "Sunday Streaming Ban" unless cushion >0.50
  (`tactician.md:78`), "ERA Cushion Rule: …do NOT stream any pitcher with proj ERA > 3.80"
  (`tactician.md:73`), "never add a pitcher with BB/9 > 3.5" (`tactician.md:75`),
  "+0.5 multi-position bonus" (`ros_werth.py`). These substitute rigid, uncalibrated rules for the
  model's judgment — and the user's complaint is precisely that the system "limited its problem
  solving abilities."

Forcing fabricated precision doesn't just waste tokens; it **corrupts the calibration loop** (we're
scoring made-up numbers) and trains the reader to trust authority theater. The fix is to compute the
numbers that *can* be computed (rate-stat math, real P(win) from a simulator — §8 D4/D5) and let the
model be honestly qualitative where it can't.

### 1.5 The model can't actually investigate — it one-shots a frozen blob

The agents receive `json.dumps(briefing_book)` and nothing else (`agents.py:63-75`). No tools, no
ability to pull a player's game log, check a breaking injury, read a depth chart, or reason
iteratively. They must produce a complete multi-section verdict in a single forward pass on
`--model sonnet`. "CC at its analytical and thoughtful best self" is the *opposite* of this: it would
be an agent that can look things up, drill into the two or three decisions that actually matter today,
and stop. The static-blob/one-shot design caps how good the judgment can be regardless of the prompt.

### 1.6 Summary of the diagnosis

| Symptom Teddy named | Structural root cause |
|---|---|
| Bias to action / over-churn | Output is a daily *publication* that must be filled; personas whose identity is finding/vetoing moves; arithmetic of "moves" centered even when holding |
| Performative personas limiting judgment | Fixed theatrical roles + mandated multi-section scripts; a *fake* parallel "debate" that fragments one judgment across three blind one-shot calls |
| (latent) Poor decisions | Fabricated P(win)/confidence; LLM hand-arithmetic; rigid uncalibrated heuristics crowding out reasoning; no tools/iteration; calibration scoring invented numbers |

The fix direction (developed in §8): **collapse the personas into one analyst working as itself with
efficient tools; move all deterministic math into tested code; make the null decision the cheap
default; reframe the artifact from "newsletter" to "decision"; ground the judgment in real best
practice; and run it as a scheduled Claude Code Routine that *is* the analyst.**

---

## 2. The existing system — behavioral map

(Assembled from reading `agents.py` + all four prompts directly, and from a full pipeline survey.)

### 2.1 Daily pipeline flow (`run_newsletter.py`, ordered)

| Step | Does | Produces |
|---|---|---|
| 0 | If a matchup period just completed, log final category results from ESPN | `calibration/actuals.csv` rows |
| 1 | ESPN API: rosters (all 8 teams), our matchup, standings, ~250 FAs. **Hard gate: abort if roster/matchup missing** | `my_roster`, `opponent_roster`, `our_matchup`, `standings`, `free_agents` |
| 2 | FanGraphs RoS projections (ATC `ratcdc`, Steamer fallback) + current-season leaderboards | `ros_bat_raw`, `ros_pit_raw`, leaderboard actuals |
| 3 | MLB Stats API: today's probable pitchers, two-start pitchers this week, transactions | `probable_pitchers`, `two_starters`, `transactions_today` |
| 3b | Baseball Savant xStats (xBA/xSLG/xERA/xwOBA/barrel), sample-gated | `savant_signals` |
| 3c | NWS weather → PPD risk + HR modifier per game (domes skipped) | `game_weather` |
| 3d | Park factors (hardcoded), team wRC+, Vegas implied totals (optional), closer roles, platoon splits | extras |
| 4 | Compute RoS WERTH z-scores for rostered/FA/opponent players | `ros_hitters`, `ros_pitchers` |
| 5 | Assemble the **briefing book** JSON (the model's entire input substrate) | `briefing_book` |
| 5b | Inject calibration summary if available | `briefing_book["calibration_summary"]` |
| 6 | **Multi-agent generation**: Tactician + Actuary (parallel) → Synthesizer | `newsletter` text |
| 6b | Parse predicted category states + regex-extract P(win) from newsletter → log | `calibration/predictions.csv` |
| 7 | Save newsletter + briefing book | `output/*.txt`, `output/*.json` |
| 8 | Render HTML, publish to `docs/index.html`, archive with prev/next nav | GitHub Pages |

Notable: steps 0–5 are deterministic data/compute and are the **reusable** part. Steps 6/6b/8 are the
performative/judgment layer and are the **overhaul** target. Critically, the `claude --print`
subprocess calls inside step 6 are also the wrong *execution* model for an unattended Routine (§8 D11).

### 2.2 File-by-file roles (decision-layer focus)

- `agents.py` — Orchestrates the three Claude CLI calls. Parallel Tactician+Actuary, then Synthesizer.
  Has an MVP single-call fallback (`generate_mvp_newsletter`, `prompts/mvp_analyst.md`) and a no-Claude
  text fallback. Post-processes the newsletter with regex to fix the header's Day X/Y and Moves X/Y
  (`_validate_newsletter`, `agents.py:193-220`) — a smell that the model gets these wrong. Also scrapes
  an `## ISSUE LOG` section out of agent output into `output/agent_issue_log.md`.
- `prompts/tactician.md` — ~250 lines. Persona + binding "strategic_posture" + hardcoded pitching/
  hitting rules + mandated multi-section output. The action engine.
- `prompts/actuary.md` — ~280 lines. Persona + EV framework + sample-size gates + 10 named "traps" +
  Risk Card format. The veto engine.
- `prompts/synthesizer.md` — ~205 lines. Tiering (DO THIS / JUDGMENT / CONSIDER / VETO), calibrated
  confidence, anti-churn guardrail, and the full newsletter template.
- `prompts/mvp_analyst.md` — ~70 lines. The single-call fallback; notably *less* persona-heavy and
  closer to "an expert analyst, here's the data." Useful prior art for the collapse-to-one-mind idea.
- `preprocess.py` — ID bridging (ESPN↔MLBAM↔FanGraphs via SFBB map) + `build_briefing_book()` +
  `_compute_strategic_posture()` (deterministic posture from week + standings) + category triage
  bucketing with hardcoded thresholds.
- `ros_werth.py` — In-season z-score valuation (see §2.4).
- `calibration.py` — Logs predicted category status + P(win), logs actuals from ESPN after matchups,
  produces a calibration report (status accuracy, P(win) reliability by decile, per-triage-bucket).
- `publish.py` — Markdown/table → HTML, GitHub Pages publishing with prev/next chaining. (Reusable as
  the renderer for the new actionable decision page — D1.)

### 2.3 The briefing book — the information substrate handed to the model

`build_briefing_book()` produces a single JSON with (top-level keys, abbreviated):
`date, matchup_week, scoring_period_id, matchup_day, matchup_length_days, days_remaining,
matchup_start/end, moves_max, opponent, opponent_team_id, strategic_posture{posture,reason},
category_state{<cat>:{you,opp,status,margin}}, category_triage{winning_comfortably…losing_unrecoverable},
triage_counts, my_roster[player…], drop_candidates[], opponent_roster[], top_free_agents[],
streamable_pitchers_today[], two_start_pitchers_available[], transactions_today[], standings{teams},
opponent_tendencies, league_context, savant_regression_signals{}, game_weather{}, team_offensive_quality{},
vegas_lines{}, closer_roles{}, extreme_platoon_players{}, data_warnings[], calibration_summary, data_freshness{}`.

Each `my_roster`/`opponent_roster`/`free_agent` player object carries: `name, espn_id, mlbam_id,
positions[], status, lineup_slot, ros_werth, total_werth, z_scores{per-cat}, team, pct_owned,
pct_owned_change, games_remaining_this_week, regression_flags[]`.

This is a genuinely rich substrate — it's the project's biggest asset. The problem isn't the data;
it's that it's frozen, dumped whole, and reasoned over once by a persona. In the new design this
becomes the data/tool backend the analyst *queries* (compactly), not a blob it swallows (§8 D3/D4).

### 2.4 Valuation — RoS WERTH (`ros_werth.py`)

Z-score system (not SGP), chosen deliberately for an 8-team H2H-categories league with non-standard
cats (project history: SGP needs roto standings denominators we don't have). Mechanics: classify
SP/RP and hitter positions → starter pool = anyone rostered → convert rate stats (OBP, ERA, WHIP, KBB)
to playing-time-weighted "counting equivalents" before z-scoring → per-category z = (player−mean)/std
over the starter pool (std negated for lower-is-better) → replacement level = best FA at position →
`pos_adj_werth = |replacement| + total_werth + multi_pos_bonus`. Known wrinkles → see **§4.4
low-hanging fruit** (starter-pool conflates regulars/bench; multi-system disagreement computed but
never surfaced; hitter-vs-pitcher DV bias).

> ✅ CC (Teddy's annotation: name low-hanging fruit such as not discerning regulars from bench):
> Agreed and added — see new **§4.4**, which enumerates the cheap, high-value fixes to the reused
> layer and pulls them into scope.

### 2.5 Calibration loop (`calibration.py`)

Logs one row per category per day to `predictions.csv` (`predicted_status`, `predicted_p_win`,
`triage_bucket`, margins), with P(win) **regex-extracted from the newsletter prose** (brittle). After a
matchup completes, logs `actuals.csv` from ESPN. Report computes status accuracy, P(win) reliability by
decile, and per-triage-bucket win rates. Two deep problems for the overhaul: (a) it scores *fabricated*
P(win), and (b) it scores category *forecasts*, never the **decisions** (was an add/drop/start actually
+EV?). It measures the wrong thing. Teddy is open to a substantial redesign here (OQ7) → §8 D9.

---

## 3. Capabilities — what the current system genuinely does well

- **Rich, multi-source daily data fusion**: ESPN league state + FanGraphs RoS + Savant xStats +
  MLB probables/transactions + Vegas + weather + park + bullpen roles + platoon splits, all
  ID-bridged and cached with graceful fallback. This is the hard, valuable part and it mostly works.
- **A defensible in-season valuation** (RoS WERTH) with correct rate-stat handling.
- **Category-state awareness**: per-category you-vs-opp margins and triage bucketing, plus a
  deterministic season-phase "strategic posture."
- **A grounded uncertainty engine already exists** (`model/correlated_uncertainty.py`): 8-system
  cross-residual correlation matrices, per-player variance profiles, Cholesky-correlated Monte Carlo.
  Built for the draft, but it's the seed of the in-season win-probability simulator (§8 D5).
- **A calibration scaffold** (right idea, wrong target — see §2.5).
- **Robust ops hygiene**: hard data gate before generating, staleness warnings, cache pruning,
  no-timeout Claude calls, multiple fallbacks.

The overhaul should **keep all of §3** and rebuild only the judgment/output/execution layer on top.

---

## 4. Limitations & gaps

### 4.1 Decision-layer (the overhaul targets)
- Performative-newsletter framing forces daily content (§1.1).
- Fixed personas + fake parallel debate fragment judgment (§1.2).
- Fabricated P(win)/confidence + LLM hand-arithmetic + rigid heuristics (§1.4).
- No tools / no iteration / one-shot on a frozen blob (§1.5).
- Calibration scores the wrong thing (§2.5).
- Regex post-processing of model output (`agents.py:193-220`) — fragile coupling between prose format
  and downstream parsing.
- **Execution model wrong for automation**: Python shells out to `claude --print` (`agents.py:30-55`)
  — the nested-subprocess anti-pattern for an unattended Routine (§8 D11).

### 4.2 Data / signal gaps (carry into the new design as known limits)
- **No injury *timeline*** (status only, no return ETA), no roster/optionable status, no bullpen
  workload/rest, no umpire effects.
- **No IL-eligibility classification** in the data layer — the briefing book carries `status` but not
  "is this player IL-slot-eligible (IL/Out/Bereavement) vs DTD?", which is the binary that governs
  free stash vs costly bench hold (§7.13).
- **Two-way (Ohtani) handling** is not modeled for lineup feasibility or deployment (hit-day vs
  pitch-day) — see §8 D12 and §6.
- **Park factors hardcoded to 2024** (`fetch_extras.py`), static; wind direction not park-oriented in
  the weather HR modifier.
- **Multi-system projection disagreement computed but never used** — a ready-made uncertainty signal
  left on the floor (and `correlated_uncertainty.py` already turns it into per-category sigmas).
- **Lineup-slot / position-eligibility feasibility was never integration-tested** (the "Ohtani UTIL"
  case was explicitly flagged as critical and marked NOT STARTED). High risk of infeasible adds.
- **No real win-probability model** — P(win) is invented, not simulated.
- Season/league hardcoded (8 teams, 12 cats, 2026 schedule) — fine for now, not parameterized.

### 4.3 Ops gaps (NOW IN SCOPE — Teddy OQ10 "yes we need to improve this")
- ESPN cookie expiry has no auto-refresh; scheduler/automation never built. The draft tool shipped a
  day-of indexing bug (STATE_OF_REPO) — a cautionary tale that **untested day-of logic fails in
  production**; the new advisor needs a smoke test and a scheduled-run dry-run before trust.
- The scheduled virtual environment imposes constraints Teddy has hit before (network allowlist,
  secrets injection, no nested `claude`, permission auto-approval, idempotency). Fully characterized
  in §8 D11.

### 4.4 Low-hanging fruit — cheap, high-value fixes to the reused layer (NEW, per Teddy)

These are defects/omissions in the *kept* data/valuation layer that are inexpensive to fix and
materially improve decision quality. In scope as targeted fixes (not a rewrite):

1. **WERTH starter pool conflates regulars and bench** (`ros_werth.py`): "starter pool = anyone
   rostered" treats a benched scrub and a regular identically, distorting category means/stds and
   replacement level. Fix: weight or filter the pool by projected playing time / lineup role. *(Teddy
   named this one explicitly.)*
2. **Surface the multi-system disagreement that's already computed** (`fetch_fangraphs.py` /
   `correlated_uncertainty.py`) as a per-player uncertainty band — feeds both the analyst and the
   simulator (OQ5). Currently dead.
3. **Hitter-vs-pitcher DV bias** (STATE_OF_REPO: avg DV 10.58 hitters vs 4.83 pitchers) — partly from
   waiver-floor asymmetry + z-score compression. **In-season fix (Teddy):** now that we're deep into
   the season, anchor replacement level / the DV normalization to the **actual current FA pool** — we
   can observe who is really available and their YTD+RoS production, instead of pre-season empirical
   floors or projection-only FAs. This both corrects the hitter/pitcher DV gap and makes "replacement
   level" reflect reality. Supersedes the pre-season floor for in-season use; subsumes #4.
4. **Replacement level = single best FA at a position** can be skewed by pool composition; consider an
   (N+1)-th-best or small-average definition — and, per #3, compute it from the **observed in-season FA
   pool** rather than projections alone.
5. **Park factors stale (2024)** — refresh from current-season or live FanGraphs guts; cheap.
6. **Expose platoon split *detail*, not just an "extreme" flag** — the vs-LHP/vs-RHP projections are
   loaded but only a boolean surfaces; the lineup optimizer needs the magnitude.
7. **IL-eligibility flag** in the data layer (IL/Out/Bereavement vs DTD) so the analyst can apply the
   free-stash-vs-costly-bench rule (§7.13) without re-deriving it.
8. **Games-remaining / two-start data** is present but should also drive a *deterministic* lineup
   feasibility/optimization pre-pass (§8 D4) rather than being re-reasoned by the model.

---

## 5. Data invariants & gotchas (adapted from the cc-workflow checklist)

The cc-workflow checklist is geospatial; the fantasy-domain equivalents that *must not be
re-discovered* are:

- **ESPN has two ID numbering systems — never mix.** `eligibleSlots`→SLOT_MAP (0=C,1=1B,2=2B,3=3B,
  4=SS,5=OF,14=SP,15=RP); `defaultPositionId`→POS_MAP (different numbering). Filter eligibleSlots
  through `REAL_POSITION_SLOTS`. (napkin #1; CLAUDE.md)
- **Matchup dates come from `data/league_schedule_2026.json`, not ESPN API inference.** MP1=12d,
  MP15=14d, rest=7d. `moves_max` is per-matchup and must be read from the schedule, never hardcoded 7.
- **ESPN verified stat IDs**: OBP=17, WHIP=41, ERA=47, K=48, QS=63, K/BB=82, SVHD=83, SBN=25.
- **Rate stats must be converted to counting equivalents before z-scoring** (OBPc/ERAc/WHIPc/KBBc).
  Never z-score raw rate stats.
- **All 12 categories every time**: R/HR/TB/RBI/SBN/OBP + K/QS/ERA/WHIP/K÷BB/SVHD; derive
  TB, SBN (SB−CS), SVHD (SV+HLD) from components.
- **ID bridge**: FanGraphs `xMLBAMID` → SFBB `MLBID` → ESPN `ESPNID`. Join on IDs, not names. A stale
  ID map silently yields WERTH=0 for unmatched players.
- **Savant sample gates**: ≥50 BBE (xBA/xSLG), ≥50 BF (xERA), ≥100 PA (BABIP), ≥40 IP (LOB%). Early
  season most signals fail the gate → rely on projections, not 1–2 week slices.
- **IL eligibility is binary** (NEW): MLB designation IL10/IL15/IL60/Out/Bereavement → IL-slot-eligible
  (off active roster, ~free to hold); **DTD or Active → NOT IL-eligible** (must sit active/bench, real
  cost). A *healthy* player left in an IL slot **blocks all FA/waiver adds** until cleared. Verify
  the exact rendered designations against live league data; the binary abstraction is robust.
- **Two-way (Ohtani) on ESPN = ONE entity, hitter OR pitcher per scoring day, never both at once**
  (NEW; unlike Yahoo/Fantrax/CBS-split). Drives lineup feasibility (§8 D12). **Verify against the live
  league settings** — this is the single most load-bearing eligibility assumption.
- **Game-time/weather**: weather beyond *today* is noise; don't use future forecasts for decisions.
  Game times are timezone-sensitive (weather estimated ~7pm local). A 1am-CT run can't see confirmed
  lineups or react to late scratches (§7.4).
- **`or` with pandas Series raises** — use explicit `is None` fallbacks (napkin User Directives).
- **Drops are irreversible in an 8-team league** — claimed within ~24h; treat as a one-way door.
- **MAX plan**: Claude Code only, never the paid API. No subprocess timeout on Claude calls. For
  automation, the Routine session *is* the analyst — avoid nested `claude --print` (§8 D11).

---

## 6. Known & suspected bugs / smells (file:line)

- `agents.py:193-220` `_validate_newsletter` regex-rewrites the header's "Day X/Y" and "Moves X/Y" —
  it exists because the model frequently emits wrong values. Symptom of asking the model to restate
  deterministic facts it should never have been given responsibility for.
- `calibration.py` P(win) extraction via regex over newsletter prose (survey: ~lines 99-118) — breaks
  if the format drifts; and scores fabricated numbers regardless.
- `ros_werth.py` "starter pool = anyone rostered" conflates regulars and bench (→ §4.4 #1).
- Multi-system disagreement (`fetch_fangraphs.py`, survey ~199-281) computed but never injected (→ §4.4 #2).
- **Position-eligibility feasibility never integration-tested**; two specific high-risk cases for the
  smoke fixture: (a) the "Ohtani UTIL" conflict / two-way either-or slotting (§8 D12), and (b) the
  **healthy-player-stuck-in-IL-slot blocking all adds** gotcha (§7.13).
- Park factors hardcoded 2024 (`fetch_extras.py:~29-60`) — silent staleness (→ §4.4 #5).

---

## 7. What best practice actually says (grounded web research synthesis)

Distilled from citation-backed surveys (FanGraphs/RotoGraphs, Pitcher List, RotoWire, FantasyPros,
CBS, ESPN, FantasyLabs/RotoGrinders, plus an academic action-bias anchor). Tailored to *this* league:
8 teams (shallow wire, high replacement level), H2H Most-Categories (each of 12 cats its own weekly
W/L), QS not W, SVHD not pure SV.

1. **"Do nothing" is the correct default, with a hard academic anchor.** Bar-Eli et al. (2007,
   *J. Economic Psychology*), "Action bias among elite soccer goalkeepers": across 286 elite penalty
   kicks, keepers dove ~94% of the time and stayed center ~6% — yet staying center had the *highest*
   save rate (~33% vs ~13–14% diving). Norm theory: inaction that fails feels worse than action that
   fails, so agents over-act against their own EV *even at high stakes*. The fantasy parallel is exact.
   Caveat: no study quantifies "fewer moves → more wins" for the median fantasy manager specifically;
   the case is convergent (action bias + regression math + expert testimony). (https://mpra.ub.uni-muenchen.de/4477/)

2. **Reduce every decision to a comparable value delta, not vibes.** Measure two players with one
   metric (dollar values / standings-gain / EV), don't eyeball. Supports a WERTH/EV-delta framing for
   every add/drop/start. (ESPN DFS decisions; Columbia/Haugh, http://www.columbia.edu/~mh2078/DFS_Revision_1_May2019.pdf)

3. **Gate reactions behind stabilization thresholds.** xwOBA ~50–60 BBE, HR rate ~300 PA, ISO ~550 PA;
   pitchers prefer xERA/FIP/K-BB over ERA in small samples. Matches the existing Savant gates → keep
   them. (Athlon; FanGraphs Community.)

4. **Vegas implied *team* total is the single best daily HITTER signal** — it already integrates
   pitcher, park, weather, lineup, so don't double-count those. Flag only park *tails* (Coors up;
   pitcher parks down). (FantasyLabs; RotoGrinders; RotoWire.) **Caveat for our 1am-CT run:** implied
   totals assume posted lineups and shift with late scratches; we use early lines and can't re-pull at
   lineup lock — treat as a strong prior, not gospel.
   > ✅ CC (Teddy "Love this"): kept as a primary signal and made symmetric for pitching ↓.

   **4b. Symmetric pitching signal (NEW — Teddy: "can this also influence pitching favorability?
   thinking symmetrically").** Yes, confirmed by the research. For a streaming/started pitcher the
   primary Vegas signal is the **OPPONENT's implied team total** (how few runs the opposing offense is
   expected to score) — lower → better ERA/WHIP and higher QS odds. Secondary: the **game total
   (over/under)** as a ratio-protection filter (low total = pitcher-friendly environment; hard-block
   Coors et al.), and the **pitcher's own-team moneyline** as a QS tilt (favored → deeper leash →
   higher QS probability, but QS is earned on the starter's own line, so keep QS-prob and
   favored-status distinct). Encode hitter & pitcher favorability as **one symmetric module**:
   own-team total high = good for the hitter; opponent total low = good for the pitcher. (TeamTotals;
   FantasyLabs; Pitcher List streamer ranks; theScore; MLB.com QS glossary.)

   **4c. Player props — valuable but conditional; investigate before committing (NEW — Teddy: "do we
   have QS props / batter HR/TB odds?").** Research result: The Odds API (which we already use for
   totals/moneylines) *does* expose rich MLB player-prop markets via its per-event endpoint — **direct**
   signals for HR (`batter_home_runs`), TB (`batter_total_bases`), R (`batter_runs_scored`), RBI
   (`batter_rbis`), SB (`batter_stolen_bases`), and **K** (`pitcher_strikeouts`); and clean **component
   proxies** for the pitcher ratios — ERA/WHIP/K÷BB reconstructable from `pitcher_earned_runs` /
   `pitcher_hits_allowed` / `pitcher_walks` / `pitcher_outs`. Three hard caveats decide whether it's
   worth it:
   1. **No QS market, no SVHD market.** QS must be *proxied* as ≈ P(outs ≥ 18) × P(ER ≤ 3) from the
      outs + earned-runs props; **SVHD has no market signal at all** (keep our `closer_roles`
      heuristics). SBN ≈ SB (no caught-stealing market).
   2. **Cost — not free.** Props are per-event and billed per market returned; the free tier (~500
      credits/mo ≈ 16/day) can't cover a daily slate. A focused **pitcher**-prop pull (~6 markets ×
      ~15 games ≈ 90 credits/day, ~2,700/mo) needs the ~$30/mo plan; a full slate ~6,300/mo.
      BALLDONTLIE's ~$9.99/mo MLB-only tier (rate-limited, batch-friendly) is a cheaper alternative to
      verify.
   3. **Timing collides with the 1am-CT run (the real blocker).** Props post *late* — usually game-day
      morning/midday, not the night before — and *batter* props are the latest. A 1am run will often
      hit empty/thin prop boards. **Pitcher** props (esp. strikeouts) post earliest *and* target our
      weakest projection area (start-level pitcher variance), so they're the only piece likely to pay
      off at 1am.
   **Verdict for the Plan:** before paying or wiring anything in, run a **one-week 1am-CT fill-rate
   probe**; if pitcher props reliably populate at 1am, integrate **pitcher props only** (K direct +
   QS/ERA/WHIP/K÷BB proxies) as a market-implied cross-check on the simulator's pitcher outputs;
   otherwise skip. Batter props are deferred given the timing. (The Odds API markets + V4 cost docs;
   BALLDONTLIE.) → tracked in §9b.

   USER: Let's ignore props then and stick to team money lines, team totals, etc that are posted by 1am and free.

5. **Streaming SP must be asymmetric and ratio-aware.** One 4-IP/7-ER stream can flip ERA *and* WHIP
   *and* K÷BB at once. Approve a stream only when projected ratios *beat* (not match) your rostered
   alternative. Pitcher List bar: a "successful" stream ≈ QS + K/inn + sub-1.20 WHIP, expected to work
   "over half the time." Shallow 8-team wire → smaller per-stream edge (waiver SPs are worse), same
   downside → **fewer, higher-conviction streams**. Two-start weeks double EV *and* blow-up risk →
   *higher* bar. (Pitcher List; RotoWire WHIP/ERA; divided expert opinion on two-start in shallow leagues.)

6. **Condition aggression on win probability (contest-structure rule).** Favored in a category/matchup
   → minimize variance (hold, don't stream); underdog or playoff-elimination → *deliberately* raise
   variance (riskier streams, chase swing cats). The single most useful strategic frame — and it
   becomes *computable* once the simulator (§8 D5) gives real P(win). (Haugh.)

7. **Plan the week opponent-conditioned around swing categories.** Classify all 12 cats as
   already-won / already-lost / live-swing; spend streams/adds/variance only on live-swing cats; never
   pad a clinched lead. Un-puntable power cluster R/HR/TB/RBI (correlated); SBN and SVHD are the
   punt-friendly levers; QS and K÷BB can be conceded matchup-by-matchup. Aim ~7 of 12, not a sweep.
   (FantasyPros categories primer + punting; CBS "FBT.") Validates the existing triage idea — but as
   *model-reasoned* planning, not hardcoded thresholds.

8. **Weight the opportunity cost of dropping real players heavily — doubly so in an 8-team league.**
   "Wait an extra day or two"; the premature-drop penalty exceeds one more bad game; hold
   emerging-skill breakouts and young high-ceiling players longer than veterans; in a shallow league a
   dropped useful player is likely claimed and the replacement only marginally better. (RotoWire/Anderson;
   Podhorzer.)

9. **Separate buy-low signal from mechanical decline.** Trigger buy-low only when xwOBA/Statcast
   diverges *favorably* AND there's no bat-speed drop / adverse batted-ball shift. High bar in a
   shallow league. (RotoGraphs/Podhorzer.)

10. **FAAB/adds against the calendar + contention state**; bid light on hot-hand grabs ("most fizzle");
    hoard reserves toward the stretch run; bid to fair value, never panic. (Shawn Childs.)

11. **Bullpen is the one place active monitoring pays.** Role changes (committee resolutions, new
    closer) are real signal; prioritize elite-*ratio* relievers (help SVHD + three ratio cats even
    with zero saves); handcuff the *role* via the top holds-getter with save upside. SVHD (vs pure SV)
    is itself the volatility mitigation. (CBS Bullpen Report; Pitcher List saves+holds; RotoBaller.)

12. **Judge process, not outcomes.** A −EV move that happened to work is still a process error, and
    vice versa. Build calibration around *decision* EV + calibration, not whether a stream "worked."
    (FantasyPros/Waterloo.)

13. **IL slots are near-free; bench stashes are full-cost (NEW — Teddy's IR/injury annotation).** This
    is a roster-construction lever the old system ignored. Mechanics + strategy:
    - **ESPN IL-slot eligibility is binary** (see §5): IL/Out/Bereavement → can occupy a 3×IL slot,
      which is *additive capacity that doesn't count against the active roster*; **DTD/Active → cannot
      be IL-stashed**, so a banged-up DTD player burns an active/bench spot.
    - **An IL stash's true cost ≈ 0 weekly production** — only (a) the add-budget to acquire and (b) a
      *contingent roster crunch at activation* (a full roster forces a drop to activate). So "fill all
      3 IL slots with the highest-ceiling injured players available" is almost always right; the only
      discipline needed is pre-planning the return cliff when ≥2 stashes return together.
    - **Holding an injured player is usually free or cheap — drop only *marginal* ones (Teddy's
      pushback was correct; this corrects an overstatement in Rev 2).** First, a **multi-week** injury
      is almost always **IL-eligible**, so the player goes on a **free IL slot** and you simply keep
      him — the "drop?" question never arises. Teddy's example is exactly right: a top-60 bat out three
      weeks → IL-stash and **hold**, obviously; never swap a star for a ~200-ranked replacement for the
      rest of the season, least of all with high-leverage playoff weeks ahead. The genuinely-costly
      case is **narrow**: a player who is **not** IL-eligible (DTD / lingering day-to-day, no IL
      placement) *or* a player hurt when all 3 IL slots are already full. Even then, value him by
      **full RoS value including the high-leverage playoff weeks**, not "back this matchup" — a star's
      RoS value dwarfs a streamer's, so **hold the star**. The shallow-league "replacement is strong"
      logic meaningfully bites only for **marginal** injured players (healthy value at/near waiver
      replacement), not for studs.
    - **The real forcing function is a roster-spot crunch (IL full *and* bench full).** Then the
      question is not "drop the injured star" but "**which is my single worst roster spot right now**" —
      usually a marginal bench player or a low-value IL occupant. Drop the worst asset; keep the best
      ones, healthy or not. Net rule: **default to holding any clearly-above-replacement injured
      player**; drop an injured player only when his *healthy* RoS value is already at/below the waiver
      replacement.
    - **Shallow-8-team adjustment (important):** replacement level is high, so *raise* the bar for
      occupying active/bench spots with injured players (you can almost always find a competent
      waiver replacement) and *lower* the bar for using the free IL slots. Maximize IL utilization,
      minimize bench stashing. (Deep leagues invert the bench calculus.)
    - **Gotcha to monitor every run:** a player who's been activated by his MLB team but is still
      sitting in your IL slot silently **blocks all your waiver/FA adds** — flag and clear.
    (RotoWire stashing guide; ESPN IL support docs; FantasyPros/RotoBaller IL-stash columns.)

**The through-line:** best practice is *patient, EV-driven, variance-aware, opponent-conditioned,
sample-size-disciplined, and IL-savvy* — almost the inverse of a daily action-shaped newsletter. The
good news: points 2–8, 11, and 13 essentially endorse the *data* the system already gathers (or cheap
additions to it); what's wrong is the *judgment wrapper*.

> ✅ CC (Teddy's IR annotation): addressed in full as §7.13 above, with design consequences in §8 D12
> and a data-layer fix in §4.4 #7 (IL-eligibility flag) and a smoke-test case in §6. **Rev 3:** Teddy's
> follow-up correctly flagged that the bench-drop rule was overstated — corrected above (multi-week
> injuries are IL-eligible and held for free; drop only marginal injured players, never stars).

---

## 8. Design directions for the overhaul

Most of the big questions are now **resolved** by Teddy's annotations (§9). Directions below are
updated to reflect those decisions; remaining trade-offs are flagged for the Plan.

### D1. Reframe the artifact: from "newsletter" to a published *decision page*. [RESOLVED]
**Decision (Teddy OQ1+OQ9):** keep a **daily published page** (reuse `publish.py` as a renderer), but
it is **actionable-only — not a newsletter**. It may be **truly empty** when holding is correct, and
on such days it must still carry a *short justification*: the single **highest-value marginal move
considered and why it didn't clear the bar** ("closest call: X — not made because Y"). No dashboard
ritual, no Appendix-to-fill. This keeps the published-page habit while removing the
fill-the-page performance pressure. Detail available on drill-down, not front-loaded.

### D2. One analyst working as itself; the skeptic is an internal step, not a second persona. [RESOLVED]
**Decision (Teddy OQ2):** "one Claude analyst asking the right questions and with the tools needed to
succeed." Drop Tactician/Actuary/Synthesizer. The adversarial check becomes a *self-critique step the
one analyst performs on its own concrete proposals* ("here's the move I'm leaning toward — now try to
refute it before I commit"), not a parallel blind persona. Simpler, cheaper, less theatrical, and it
keeps judgment in one coherent context.
> ✅ CC (Teddy): the self-critique must have **teeth** — if the refutation is persuasive, the analyst
> *actually updates and changes the recommendation*, not logs a ritual "I considered the downside"
> paragraph and proceeds anyway. To keep it honest (and not re-import the performance problem we're
> removing from the personas), the decision log (D9) should record when a leaning was **overturned** by
> self-critique — that's the observable proof the skepticism is real. Concretely: the analyst states a
> tentative call, runs an explicit refutation pass, and emits a *possibly different* final call plus a
> one-line note if it changed its mind.

### D3. Tool-using — but efficient, purpose-built tools that minimize token spend. [RESOLVED]
**Decision (Teddy OQ3):** the analyst is agentic but its tools are **narrow and cheap** — they return
compact, decision-relevant summaries, not raw dumps. Examples: `get_player_recent_form(id)` → a few
lines, not a game log; `compute_stream_impact(pitcher, vs_team)` → the pre-computed ERA/WHIP/K÷BB
deltas vs the actual rostered alternative; `lineup_feasibility(proposed)` → pass/fail + reason;
`matchup_winprob(roster_change?)` → simulator output. The analyst pulls only what the day's 2–3 real
decisions require. (Reuses the existing fetchers/valuation as tool backends.)

### D4. Hard split: deterministic math in **code**, judgment in the **model**. [RESOLVED in spirit]
Everything that's arithmetic or lookup moves to Python and is handed over as a *fact*: rate-stat
dilution before/after, category margins, games-remaining, **lineup-slot feasibility + two-way
slotting + IL eligibility**, eligibility chains, schedule/moves_max, days-remaining. The model never
recomputes or restates these (kills the `_validate_newsletter` regex hack). A **deterministic lineup
pre-pass** proposes the obvious optimal lineup (off-day coverage, two-start, feasibility); the model
only adjudicates the genuinely judgmental swaps (platoon, category-protection sits, ratio risk).

### D5. Build the Monte-Carlo matchup win-probability simulator — by reusing `correlated_uncertainty.py`. [RESOLVED: scope it]
**Decision (Teddy D5/OQ4/OQ5):** scope option A — build a simulator that produces genuine per-category
and overall matchup **P(win)** and the **EV of a candidate move**.

**Teddy's correction is right and changes the method (verified).** `correlated_uncertainty.py`'s
cross-system residual matrix models **projection / talent uncertainty** — *how unsure we are about a
player's true full-season rate* (if the systems disagree about his HR they also disagree about his TB).
That is the correct structure for **draft** value. It is **not** the dominant source of **week-ahead**
variance. Over a ~6-game / 1–2-start window (~25 PA for a hitter), realized outcomes are dominated by
**sampling randomness of discrete events** — Poisson/binomial-ish counts, exactly as Teddy says — and
the within-week cross-category correlation is induced by **shared playing time** (sit → all his
counting stats drop together) and **within-game event co-occurrence** (a multi-hit game brings R/TB/RBI
with it), *not* by season-long talent disagreement. So we reuse the engine's **machinery and its
talent layer as a secondary component**, not its correlation matrix as the primary generator.

**Corrected two-layer simulator (scoping for the Plan):**
- **Primary = empirical bootstrap of recent real game/start lines** (Teddy's suggestion), scaled to
  games/starts remaining in the matchup window:
  - *Hitters:* resample real recent healthy **game lines** (R/HR/TB/RBI/SB/CS/H/BB/PA drawn *together*).
    Because each draw is a real line, cross-category correlation **and** playing-time structure come for
    free — no explicit matrix needed. Ratio cats are correct by construction (sum H/BB/PA across draws,
    *then* compute weekly OBP — no rate-averaging error).
  - *Pitchers:* bootstrap real recent **start lines** (IP/ER/H/BB/K, QS flag) from the **last ~10
    healthy starts** (Teddy); sum over starts-remaining; ERA/WHIP/K÷BB aggregate from summed components.
- **Secondary = talent/rate overlay (where the existing engine plugs in):** pure bootstrap overfits a
  hot/cold streak and ignores true talent, so **shrink** each player's empirical distribution toward
  his **RoS projection** (projection = mean anchor; bootstrap = shape/spread), widening for thin
  samples / role uncertainty. `correlated_uncertainty.py` supplies the *rate* uncertainty band and the
  shrink weight (multi-system disagreement, per-player σ) — its proper job. For players with too few
  recent games (call-ups, returnees), fall back to projection ± correlated talent noise (where the
  Cholesky machinery *does* belong).
- **Aggregate:** sum player draws → team category totals for the window; add **banked**
  `category_state`; simulate the opponent the same way (possibly coarser); → per-category P(win) +
  overall record distribution.
- **Settled by Teddy:** **ignore inter-player correlation in v1**; **~200 sims** is plenty for daily
  P(win) stability (no need for the draft's 2000); **bootstrap pitchers from last ~10 healthy starts**.
- **Inputs we already have:** `category_state` (banked), `games_remaining_this_week`, probables /
  two-start, lineup slots.
- **Remaining scoping for the Plan:** the shrink weight (recent sample vs projection) and how many
  recent games to pool; modeling **games-played within the window** (off-days / sit risk — the biggest
  single lever); **SVHD** is lumpy and game-state-driven (bootstrap is crude here — flag as a known v1
  weakness, lean on `closer_roles`); opponent-modeling fidelity; runtime inside a Routine.
- **Payoff:** makes §7.6 (contest-structure aggression) and §7.5 (stream EV vs the rostered
  alternative) *computed*, not vibed; and gives D1's "closest call and why" a real number.

### D6. Invert the action incentive structurally — but distinguish reactive churn from purposeful streaming. [RESOLVED tension]
The system *starts from* "hold / keep current lineup" and requires any deviation to clear an explicit,
computed bar; producing no transaction is the zero-effort path. **But (Teddy's D10 pushback) streaming
is legitimate, often-required churn.** The reconciliation:
- Anti-churn targets **reactive, low-value churn** — slump-dropping, hot-hand chasing, fiddling a
  bench that costs nothing. That's what we suppress.
- **Deliberate streaming churn that clears the asymmetric ratio-aware bar (§7.5), fits the
  swing-category plan (§7.7), and is sized to the contest-structure posture (§7.6) is +EV and
  encouraged**, budgeted against `moves_max`. The simulator (D5) is what tells the two apart: a stream
  is "purposeful" iff `matchup_winprob(after) − matchup_winprob(before) > bar`, net of the
  irreversibility/opportunity-cost premium.
- Net: the default is hold, but the bar is a *computed EV threshold*, not "never transact." Underdog
  weeks and live-swing pitching categories will legitimately trigger streams.

### D7. Keep principles, drop rigid heuristics. [RESOLVED — Teddy "Agreed"]
Convert hardcoded thresholds (Sunday Streaming Ban, "ERA>3.80," "BB/9>3.5," numeric posture cutoffs)
into *reasoning principles the model applies with judgment*, grounded in §7. Keep only genuinely
invariant hard constraints as code: lineup-slot feasibility, two-way slotting, IL eligibility,
sample-size gates, drop irreversibility, "weather beyond today is noise." Heuristics become priors the
model can override with a stated reason — restoring the problem-solving latitude Teddy wants.

### D8. Encode the high-value strategic frames as first-class inputs.
- **Vegas as a symmetric module:** own-team implied total = primary daily-*hitter* signal; opponent
  implied total = primary streaming-*pitcher* signal; game total = ratio-protection filter; own-team
  moneyline = QS tilt (§7.4 + §7.4b). [Teddy-confirmed symmetry.]
- **Player props (pitcher-only, conditional):** if the 1am fill-rate probe passes, fold in
  market-implied pitcher signals (K direct; QS/ERA/WHIP/K÷BB via component proxies) as a cross-check on
  the simulator's pitcher outputs (§7.4c). Batter props deferred (timing); no QS/SVHD market.
- Asymmetric, ratio-aware streaming gate computed against the *actual* rostered alternative (§7.5).
- Contest-structure aggression: favored→low variance, underdog/elimination→high variance (§7.6),
  now computable via D5.
- Weekly swing-category planning: live-swing vs decided cats; ~7-of-12 target (§7.7).
- Opportunity-cost-weighted, calendar-aware drop/FAAB logic (§7.8, §7.10).
- **IL/injury logic:** free IL stashes vs costly bench holds; activation-crunch pre-planning;
  IL-block monitoring (§7.13). [NEW]
- Bullpen role-change monitoring as the one high-value active task (§7.11).

### D9. Fix the calibration target: log *decisions*, score *process*. [RESOLVED — Teddy "open to substantial redesign"]
Log every recommendation (start/sit, add/drop, **hold**) with: the simulator's computed P(win) before
and the projected EV of the action, the analyst's qualitative confidence, the "closest call" on hold
days, and (later) the realized category outcome. Score **decision quality + confidence calibration**
over time — not regex-scraped category P(win). Minimal schema sketch (for the Plan to refine):
`date, decision_id, type{start|sit|add|drop|hold|stream}, player(s), winprob_before, ev_estimate,
confidence, rationale_ref, realized_outcome (filled at matchup close)`. This is what lets us prove the
new system beats both the old one and a naive "set-and-forget."

### D10. Cadence: ONE daily run at 1am CT, with an internal cheap/deep split. [RESOLVED]
**Decision (Teddy OQ6):** a single daily run at 1am CT (not separate scheduled passes). *Within* that
run, separate the near-trivial **deterministic lineup pre-pass** (D4 — off-days, two-start, feasibility;
almost always a few obvious swaps) from the **judgmental transaction/streaming analysis** (D6) that
fires only when something clears the bar. The 1am timing means probable pitchers are known (streaming
decisions OK) but confirmed lineups/late scratches are not (§5/§7.4 caveat). **Teddy (OQ9b.5): no
morning re-check** — the advisor sets the best lineup it can from probables/projected lineups and
**commits at 1am**. It may still *note* a platoon-risk start for Teddy's optional manual eyeball, but
the system does not re-run to chase confirmed orders.

### D11. Execution architecture: the scheduled Routine session *is* the analyst (no nested `claude`). [NEW — RESOLVED direction]
This is the crux of "runs cleanly as a Routine" (Teddy §0 + OQ10). Research findings (verify
version-specific details against current docs at build time):
- **Run it as a Claude Code Routine** (Anthropic-hosted, scheduled trigger, daily 1am CT) — unattended,
  no terminal, permissions auto-approved at creation, output captured in the session transcript.
- **Do NOT keep the Python→`claude --print` subprocess pattern.** A scheduled Claude session spawning
  nested `claude --print` hits the `CLAUDECODE=1` "cannot be launched inside another Claude Code
  session" guard, and headless `claude -p` may bill at **API rates** (violating MAX-only) under the
  current usage split. Instead: **the Routine session itself does the reasoning** — Python is reduced
  to data-fetch + deterministic compute + efficient *tools*, and the Claude session (the analyst,
  D2/D3) reads the prepared data and decides. This *converges* the judgment redesign and the execution
  fix into one architecture.
- **Environment constraints to design for (the "virtual env constraints" Teddy hit):**
  - **Network allowlist:** hosted Routines restrict outbound network; ESPN/FanGraphs/Savant/MLB/Odds
    domains likely must be added as custom allowed domains. Verify and enumerate in the Plan.
  - **Secrets:** ESPN auth cookies + `ODDS_API_KEY` must be injected via the Routine's environment
    config (not committed). Pairs with the **cookie auto-refresh** need (OQ10).
  - **MCP availability:** claude.ai connectors work in Routines but **not** in headless `claude -p`;
    local `claude mcp add` servers work in neither. Don't depend on interactively-authed MCP for the
    unattended path.
  - **Idempotency:** a re-trigger re-runs; code "skip if already published today." "Green run" ≠
    "succeeded" — write an explicit success marker / commit and verify it.
  - **Local-cron alternative** (if we ever run on Teddy's machine instead): minimal env, `claude` may
    not be on PATH, permission prompts hang — all avoidable but must be handled. Hosted Routine is the
    recommended default.
- **Open items for the Plan:** confirm MAX-plan Routine billing is subscription (not API) at build
  time; confirm the external-API allowlist; decide hosted-Routine vs local-cron; design cookie refresh.

### D12. Make two-way (Ohtani) and IL handling first-class, deterministic, and tested. [NEW]
- **Two-way:** model Ohtani (per ESPN, **verify live**) as ONE entity eligible for a hitting slot OR a
  P slot per day — **never both simultaneously**. Default: **hit every day** unless a same-day start
  is the clearly higher-EV side (favorable matchup by §7.4b, pitching counting-cats live-swing). The
  deterministic feasibility code (D4) must never emit him in UTIL and P at once. Valuation:
  deployment-adjusted, no double-count (value his bat on hit-days + his chosen starts, plus a *small*
  shallow-league flexibility bonus). The repo already has prior two-way z-score work (commit
  `30b5d34`) to build on.
- **IL:** deterministic IL-eligibility classification (§5 binary) feeds the free-stash-vs-costly-bench
  logic (§7.13); the feasibility code surfaces the "healthy player blocking adds" condition and the
  activation-crunch pre-plan.
- **Both are gating smoke-test fixtures** (Teddy OQ8): an Ohtani two-way slotting case and an
  IL-eligibility/blocking case must pass before any lineup recommendation is trusted.

### What to reuse vs. rebuild (scoping the eventual plan)
- **Reuse largely as-is:** all `fetch_*`, `http_utils`, `config`, `preprocess` ID-bridge +
  briefing-book assembly (becomes the tool/data backend); `ros_werth` (with §4.4 fixes);
  `model/correlated_uncertainty.py` (as the simulator's variance/correlation engine).
- **Rebuild:** `agents.py` + `prompts/*` → one tool-using analyst (D2/D3); `publish.py` framing →
  actionable decision page (D1); `calibration.py` target → decision log (D9); `run_newsletter.py`
  steps 6/6b/8; **the execution model** → Routine-session-as-analyst, no nested `claude` (D11).
- **New:** the matchup win-probability simulator (D5); a deterministic feasibility/lineup pre-pass
  incl. two-way + IL (D4/D12); the decision log (D9); the Routine config + cookie refresh (D11).

---

## 9. Decisions resolved by Teddy's annotations, and remaining open questions

### 9a. Resolved decisions (from Rev-1 annotations)
1. **Output medium (OQ1+OQ9):** a daily **published page**, **actionable-only (no newsletter)**, which
   may be **truly empty** but must then give the closest-call-and-why. → D1.
2. **Architecture (OQ2):** **one** Claude analyst, asking the right questions, tool-equipped;
   self-critique replaces the second persona. → D2.
3. **Agentic depth (OQ3):** tool-using with **efficient, narrow tools** that minimize token spend;
   heavy deterministic work pre-computed. → D3/D4.
4. **Win-probability model (OQ4):** **yes, build it**, reusing `correlated_uncertainty.py`. → D5.
5. **Valuation (OQ5):** keep **RoS WERTH + parameterized uncertainty grounded from logical estimates**
   (= the multi-system variance model). → D5 + §4.4 #2.
6. **Cadence (OQ6):** **one daily run, 1am CT.** → D10.
7. **Calibration (OQ7):** **substantial redesign** to decision-logging + process-scoring. → D9.
8. **Feasibility + two-way (OQ8):** **testing required**; explicit Ohtani two-way handling + IL cases
   as gating smoke fixtures. → D12 / §6.
9. **No newsletter (OQ9):** confirmed; actionable info only. → D1.
10. **Ops reliability (OQ10):** **in scope** — ESPN cookie refresh + reliable scheduled execution. → D11.
11. **Scheduled Routine in scope (§0):** research/test/validate clean unattended runs given env
    constraints. → D11.
12. **Low-hanging fruit in scope (§2.4):** name + fix cheap defects in the reused layer. → §4.4.
13. **IR/injury value (§7):** free IL stashes vs costly bench holds, fully worked. → §7.13 / D12 / §4.4 #7.
14. **Vegas pitching symmetry (D8):** confirmed and encoded as one symmetric module. → §7.4b / D8.

**Rev-3 additions:**
15. **Simulator method corrected:** week-ahead variance is *sampling* (bootstrap recent real lines),
    not the talent-uncertainty correlation matrix; reuse the engine as a secondary talent overlay.
    Ignore inter-player correlation; ~200 sims; bootstrap pitchers from last ~10 healthy starts. → D5.
16. **IL/bench rule corrected:** multi-week injuries are IL-eligible → free stash → hold; drop only
    *marginal* injured players, never stars. → §7.13.
17. **Self-critique has teeth:** it can overturn the leaning; the decision log records when it did. → D2.
18. **In-season replacement level** renormed from the *actual observed FA pool*. → §4.4 #3/#4.
19. **No morning re-check:** commit the lineup at 1am from probables. → D10 / §9b.5.

### 9b. Remaining open questions for the Plan
1. **Simulator scoping specifics** (granularity, per-start vs rate-scaling, inter-player correlation,
   sim count, runtime budget inside a Routine). → D5.
2. **Routine operational unknowns to verify at build time:** MAX-plan Routine billing is
   subscription-not-API; the external-API network allowlist (ESPN/FanGraphs/Savant/MLB/Odds);
   hosted-Routine vs local-cron; **ESPN cookie auto-refresh design** (the hardest ops piece). → D11.
3. **Live ESPN settings verification:** the two-way Ohtani either-or model and the exact IL-eligible
   designations must be confirmed against the live league, not assumed. → D12 / §5.
4. **Decision-log schema** final shape and how realized outcomes are joined at matchup close. → D9.
5. **1am-CT information limits — RESOLVED (Teddy):** accept early-data (1am) lineup-setting; **no
   morning re-check**. Commit at 1am from probables/projected lineups. → D10.
6. **How much §4.4 low-hanging fruit to fix in v1** vs defer (each is cheap but they add up).
7. **Player props — investigate before integrating:** run the 1am-CT fill-rate probe; decide
   pitcher-props-only vs skip; choose The Odds API ($30/mo) vs BALLDONTLIE ($9.99/mo MLB) if we proceed.
   Accept the no-QS/no-SVHD-market gaps. → §7.4c / D8.

---

## Appendix — provenance of this research

- Read directly by CC: `in_season/daily_digest/agents.py`, `prompts/{tactician,actuary,synthesizer,
  mvp_analyst}.md`; `model/correlated_uncertainty.py`; napkin; `cc-workflow.md`.
- Pipeline/data map + briefing-book schema + capabilities/limitations: dedicated read-only survey of
  `run_newsletter.py`, `config.py`, `http_utils.py`, all `fetch_*`, `ros_werth.py`, `preprocess.py`,
  `calibration.py`, `publish.py`, real `output/briefing_book_current.json` / `predictions.csv`.
- Project history/intent/known-problems: survey of `STATE_OF_REPO.md`, `plans/{ROADMAP,
  daily_newsletter_build_plan,plan}.md`, `research/{daily_newsletter_infrastructure,research,
  data_assessment,flaim_assessment}.md`, `CLAUDE.md`.
- Best-practice §7: citation-backed web research (Bar-Eli 2007; Haugh; Pitcher List; RotoWire/Anderson;
  FanGraphs/Podhorzer; FantasyPros; CBS; RotoGrinders/FantasyLabs).
- Rev-2 additions: (a) scheduled-Routine execution + headless-env constraints
  (Claude Code docs on routines/headless; CLAUDECODE nested-session issue) — version-specific details
  flagged "verify at build time"; (b) IL mechanics/strategy + two-way ESPN handling + Vegas pitching
  symmetry (ESPN support docs; RotoWire/FantasyPros/RotoBaller; Pitcher List; TeamTotals/FantasyLabs);
  (c) read of `model/correlated_uncertainty.py` to scope simulator reuse.
