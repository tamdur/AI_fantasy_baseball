# kb — in-season advisor overhaul

Last updated: 2026-05-31 (plan annotation round 1)
Active size: ~165 lines

## Index
- Project invariants
- Resolved design decisions
- Resolved in plan annotation round 1
- Gotchas
- Decisions (process)
- Don't-do
- Open questions
- Archive

## Project invariants
Things true across this task that shouldn't have to be re-discovered.

- Goal: rebuild the **judgment + output + execution** layer of the in-season system so the model works
  as its own thoughtful self, "do nothing" is the cheap default, decisions are EV-grounded, and it
  runs unattended as a scheduled Routine. Diagnosis: `research.md` §1; directions §8; resolved
  decisions §9a; open questions §9b.
- Scope split: **reuse** data layer (`fetch_*`, `http_utils`, `config`, `preprocess`), `ros_werth`
  (with §4.4 cheap fixes), and `model/correlated_uncertainty.py` (as simulator engine). **Rebuild**
  `agents.py`, `prompts/*`, output framing (`publish.py`), `calibration.py` target,
  `run_newsletter.py` steps 6/6b/8, and the execution model.
- League: 8-team ESPN H2H Most-Categories keeper. 12 cats: R/HR/TB/RBI/SBN/OBP + K/QS/ERA/WHIP/K÷BB/
  SVHD. 22 reg weeks + 2 playoff rounds. Top 4 of 8 make playoffs. Team = Brohei Brotanis (id 10).
  Slots: C,1B,2B,3B,SS,MI,CI,5×OF,UTIL,9×P,3×BE,3×IL.
- 8-team ⇒ shallow wire, high replacement level ⇒ reactive churn is mostly downside; drops ~irreversible
  (claimed ~24h). Most important strategic fact.
- **IL eligibility is binary:** IL10/IL15/IL60/Out/Bereavement = IL-slot-eligible (off active roster,
  ~free to hold); DTD/Active = NOT eligible (real bench/active cost). A *healthy* player left in an IL
  slot BLOCKS all FA/waiver adds until cleared. Maximize IL use, minimize bench stashing in shallow
  league. **But: HOLD stars** — multi-week injuries are IL-eligible (free stash); drop only *marginal*
  injured players (healthy value ≤ waiver replacement), never a top-N talent. Forcing function = IL+bench
  both full → drop your single worst roster spot, not the star. (research.md §7.13)
- **Player props** (The Odds API): rich MLB markets exist (HR/TB/R/RBI/SB/K direct; ERA/WHIP/K÷BB via
  pitcher component props) BUT no QS market (proxy = P(outs≥18)×P(ER≤3)), no SVHD market, SBN≈SB. NOT
  free-tier feasible (~$30/mo Odds API or ~$9.99/mo BALLDONTLIE). Props post LATE (game-day AM) → collide
  with 1am run; pitcher props earliest. Verdict: probe fill-rate first, then pitcher-props-only or skip.
  (research.md §7.4c)
- **Two-way (Ohtani) on ESPN = ONE entity, hitter OR pitcher per day, NEVER both at once** (unlike
  Yahoo/Fantrax/CBS-split). Default: hit daily unless a same-day start is clearly higher-EV. VERIFY
  against live league settings — load-bearing eligibility assumption. (research.md §5, D12)
- **Vegas is symmetric:** own-team implied total = best daily HITTER signal; opponent implied total =
  best streaming-PITCHER signal (lower=better ERA/WHIP/QS); game total = ratio-protection filter
  (block Coors); own moneyline = QS tilt. One symmetric module. (research.md §7.4/§7.4b)
- ESPN two ID systems — never mix: `eligibleSlots`→SLOT_MAP, `defaultPositionId`→POS_MAP. Filter via
  `REAL_POSITION_SLOTS`.
- Matchup dates/`moves_max` from `data/league_schedule_2026.json` (MP1=12d, MP15=14d, else 7d), NOT
  ESPN API inference. Never hardcode 7.
- ESPN stat IDs: OBP=17, WHIP=41, ERA=47, K=48, QS=63, K/BB=82, SVHD=83, SBN=25.
- ID bridge: FanGraphs `xMLBAMID` → SFBB `MLBID` → ESPN `ESPNID`. Join on IDs, not names. Stale map ⇒
  silent WERTH=0.
- Rate stats → counting equivalents (OBPc/ERAc/WHIPc/KBBc) before z-scoring.
- Savant gates: ≥50 BBE (xBA/xSLG), ≥50 BF (xERA), ≥100 PA (BABIP), ≥40 IP (LOB%).
- MAX plan: Claude Code only, never paid API. No subprocess timeout on Claude calls.
- Repo on Google Drive: file reads occasionally ETIMEDOUT (retry); git throws stale `.git/*.lock` even
  with no git running (`rm -f .git/index.lock .git/HEAD.lock`). Long git/ls auto-background.
- Branch: `in_season_revision` off `main`.

## Resolved design decisions (Teddy's Rev-1 annotations — see research.md §9a)
- Output = daily PUBLISHED PAGE, actionable-only, NO newsletter; may be truly empty but must give the
  "closest call considered + why it didn't clear the bar."
- ONE Claude analyst with efficient tools; self-critique replaces the 2nd persona (no Tactician/
  Actuary/Synthesizer).
- Tool-using but tools are NARROW/CHEAP (compact summaries, pre-computed facts) to minimize tokens.
- BUILD the Monte-Carlo matchup win-prob simulator, but **method corrected (Teddy)**: week-ahead
  variance is SAMPLING randomness (Poisson/binomial over ~6 games), NOT the talent-uncertainty
  cross-residual matrix. Primary engine = **bootstrap resample recent real game/start lines** (hitters:
  recent healthy game lines; pitchers: last ~10 healthy starts) scaled to games/starts-remaining — this
  preserves cross-category correlation + playing-time + correct ratio aggregation for free. Secondary =
  shrink toward RoS projection using `correlated_uncertainty.py`'s per-player σ (talent overlay only;
  Cholesky fallback for thin-sample players). Ignore inter-player correlation v1; ~200 sims. Add banked
  `category_state`; sim opponent same way → per-cat P(win) + record dist. SVHD lumpy = known v1 weakness.
- Keep RoS WERTH + parameterized uncertainty (= multi-system disagreement variance).
- ONE daily run at 1am CT (probables known; confirmed lineups/late scratches NOT — accept early data).
- Substantial calibration redesign → log DECISIONS, score PROCESS (winprob_before, ev_estimate,
  confidence, realized_outcome).
- Execution: run as a Claude Code ROUTINE where the session IS the analyst; Python = data/tools.
  Cookie auto-refresh + reliability in scope.
- Anti-churn ≠ no-streaming: suppress reactive churn; deliberate streaming that clears the computed EV
  bar (via simulator) is encouraged, budgeted vs moves_max.
- Self-critique has TEETH: it can overturn the leaning; log when it did (not a ritual paragraph).
- In-season replacement level renormed from the ACTUAL observed FA pool (not pre-season floors).
- No morning re-check: commit lineup at 1am from probables; may note platoon risk for optional eyeball.

## Resolved in plan annotation round 1 (Teddy — see plan.md §9)
- **Persistence under a CC Routine (NEW invariant — plan §1.1):** the Routine runs in an EPHEMERAL repo
  checkout. Only **Tier-1** survives = git-committed (`docs/` page, `advisor/log/decisions.csv`, optional
  ≤few-KB `records/<date>.json`, `calibration/actuals.csv`); budget ≈ a few KB/day. **Tier-2** =
  run-scratch, gitignored, discarded (`decision_context_<date>.json` read by the analyst same run;
  gamelog/HTTP caches — within-run only, cold across runs accepted). **Idempotency keyed off committed
  `docs/archive/<date>.html`**, NOT a scratch marker (wouldn't survive a fresh-env retry). Scratch dir =
  `$ADVISOR_SCRATCH` (default `<repo>/advisor/.scratch/`). Git push needs creds + `pull --rebase`.
- All **eight** §4.4 fixes ship in v1 (plan §4a), each with its test green before the next. #3 (FA-pool
  replacement) subsumes #4.
- **Player props DEFERRED ENTIRELY** for v1 (no free 1am source) — removed from context schema + phases.
- Hosting = **hosted CC Routine** (not local cron).
- Game logs: MLB Stats API gameLog, optimize for wall time, hitters ~30g / pitchers ~10 starts,
  **prior-season (2025) fallback** when sample thin, fetch relevant players only.
- **Decision page = stakes-scaled** (1 line sit/start → paragraph for significant add/drop; "No moves +
  closest call" on holds). **Drill-down = native `<details>`/`<summary>` progressive disclosure** (no JS;
  headline visible, numbers one click away). Decision-log row gains a `tier{tweak|stream|significant|
  hold}` field driving render density. (plan §3.8)
- Confidence = qualitative **{low/med/high}** headline; rationale may cite p_win/Δ. No schema change.
- **Direct cutover, no shadow week** — old pipeline retired/archived-in-place, not maintained.

## Gotchas
- 2026-05-31 — DON'T keep Python→`claude --print` subprocess for the unattended run: nested call hits
  `CLAUDECODE=1` "cannot launch inside another Claude Code session" guard; headless `claude -p` may
  bill at API rates (violates MAX-only). Fix = Routine session does the reasoning itself. (research.md D11)
- 2026-05-31 — Hosted Routines restrict outbound network; ESPN/FanGraphs/etc. likely need to be added
  as custom allowed domains. Secrets (ESPN cookies, ODDS_API_KEY) injected via Routine env config.
  "Green run" ≠ "succeeded" — write a success marker. Verify MAX Routine billing at build time.
- 2026-05-31 — git stale-lock + ETIMEDOUT on Google Drive path (see invariants). `rm -f .git/*.lock`.
- 2026-05-31 — `agents.py:193-220` regex-rewrites model's Day/Moves header b/c model gets facts wrong
  → new design hands computed facts over, never asks model to restate them (D4).
- 2026-05-31 — `calibration.py` regex-extracts P(win) from prose AND scores fabricated numbers — wrong
  target (D9).

## Decisions (process)
- 2026-05-31 — Subdir `in_season/advisor/` (reframe from newsletter→advisor). Renameable pre-code.
- 2026-05-31 — Phase 1 research only; artifacts `research.md`+`kb.md`. No impl before plan approval.
- 2026-05-31 — "cc-workflow" = `plans/cc-workflow.md` working agreement, NOT the Workflow tool. Follow
  its SPIRIT (geospatial specifics don't apply; test plan uses Ohtani/IL/Routine smoke fixtures).
- 2026-05-31 — Rev 2: addressed all 19 USER annotations; ran 3 research tracks (Routines, IL/two-way/
  Vegas, uncertainty engine).
- 2026-05-31 — Rev 3: corrected simulator method (bootstrap) + IL/bench rule; props research.
- 2026-05-31 — Phase 2: drafted `plan.md` (grounded in exact interfaces). Awaiting annotation; NO
  implementation until approved. Key plan choices: new `in_season/advisor/` package = judgment+execution
  layer, daily_digest stays as data/fetch backend (imported via sys.path shim); **tool surface = thin
  CLI subcommands** (`python -m advisor.tools …`) the analyst calls via Bash (not MCP); IL-eligibility
  detected via **slot 17 in eligibleSlots** (robust, not injuryStatus strings); simulator aggregates
  ratio cats by **summing components then dividing**; NEW dep = recent game logs via MLB Stats API
  gameLog for the bootstrap. Phases P0 scaffold → P1 feasibility → P2 simulator → P3 analyst+tools →
  P4 page+log → P5 Routine/ops → P6 props/deferred.
- Key extracted interfaces (for impl): `compute_ros_werth(ros_bat,ros_pit,rostered_espn_ids,fa_espn_ids)
  → (hitters_df,pitchers_df)` w/ z_*/total_werth/pos_adj_werth/repl_level/is_starter/primary_position/
  pitcher_type; `build_briefing_book(...)` huge sig → briefing dict; `model/league.py` ROSTER_SLOTS=
  {C1,1B1,2B1,SS1,3B1,OF5,MI1,CI1,UTIL1,P9,BE3,IL3}, NUM_TEAMS=8; SLOT_MAP 17=IL; `fetch_espn._parse_player`
  returns injury_status∈{ACTIVE,INJURY_RESERVE,DAY_TO_DAY,OUT} (currently DROPS slot 17 — must capture);
  `publish_newsletter(text,briefing)` renders docs/index.html+archive; calibration predictions.csv/
  actuals.csv schemas known. ESPN creds = env ESPN_SWID/ESPN_S2; ODDS_API_KEY env.

## Don't-do
- Don't fix action-bias with more "please don't churn" prompt text — it's architectural.
- Don't keep the 3 personas / fake parallel debate.
- Don't ask the model to do rate-stat arithmetic or invent calibrated P(win) — compute it (simulator).
- Don't re-derive park/weather effects in the model when Vegas implied totals already integrate them.
- Don't depend on interactively-authed MCP for the unattended Routine path (not available headless).
- Don't emit Ohtani in UTIL and P simultaneously (ESPN single-entity either/or).
- Don't IL-stash a DTD player (mechanically impossible); don't leave a healthy player in an IL slot
  (blocks all adds).
- Don't auto-execute moves to ESPN — stays advisory (human pulls trigger).
- Don't use `correlated_uncertainty.py`'s cross-residual correlation matrix as the PRIMARY week-ahead
  generator — that's talent uncertainty, not sampling randomness. Bootstrap recent real lines instead.
- Don't drop an injured STAR off the bench — multi-week injuries are IL-eligible (free stash); the
  shallow-league "drop injured guys" logic applies only to marginal players.
- Don't commit Tier-2 scratch (decision_context JSON, gamelog/HTTP caches) to the repo — gitignored,
  ephemeral. Only Tier-1 (page, decisions.csv, optional ≤few-KB record) is committed. (plan §1.1)
- Don't key idempotency off a scratch SUCCESS marker — fresh-env retries won't see it; key off committed
  `docs/archive/<date>.html`.
- Props deferred entirely for v1 (was: "probe 1am fill-rate") — don't build any props path until a free
  game-day-AM source exists.

## Open questions (genuinely unresolved; the round-1-resolved ones moved up to Resolved/Decisions)
- **Verify at BUILD time** (plan §9 open list): MAX Routine billing = subscription (no API metering);
  external-API network allowlist; ESPN cookie auto-refresh design (hardest ops piece); git push creds +
  `pull --rebase` + `main` vs `advisor-output` branch.
- Verify live ESPN settings: Ohtani either-or model; exact IL-eligible slot-17 designations.
- Decision-log realized-outcome join at matchup close (schema otherwise fixed in plan §3.5).
- Simulator scoping (tunable during P2): shrink weight (recent sample vs projection), exact # recent
  games to pool, within-window games-played modeling, opponent fidelity, Routine runtime budget.

## Archive
(none yet)
