# Claude Code Working Agreement — Downstream

This file defines how Teddy and Claude Code (CC) collaborate on scientific code for Downstream. **Read it in full before touching code in any session that uses it.** Paste it into context at session start, or reference its path.

The workflow is adapted from Boris Tane's research → plan → annotate → implement loop, with three Downstream-specific additions: a scientific-coding spine (geospatial + numerical correctness baked into every phase), a mode toggle (ripthrough vs. checkpoint), and a per-task knowledge-base doc that CC owns and maintains as its own working memory.

The non-negotiable principle, unchanged from Boris: **CC never writes implementation code until Teddy has reviewed and approved a written plan.**

## One-sentence summary

Read the relevant code and data assumptions deeply, write a plan (including tests and a smoke fixture), annotate the plan until it's right, then execute the whole thing end-to-end with continuous test/lint/smoke checking, and keep a living kb of what you learned along the way.

---

## Session start protocol

At the start of every session CC must:

1. Read this file and confirm the workflow.
2. Ask Teddy for the **target subdirectory** for this task. All work artifacts (`research.md`, `plan.md`, `kb.md`, code) live under that subdir unless Teddy says otherwise.
3. Check whether a `kb.md` already exists in that subdir. **If yes, read it in full before any other action.** It is CC's own prior-session memory and almost always contains directly load-bearing information.
4. Confirm the operating mode (ripthrough vs. checkpoint — see below). If Teddy didn't specify, **default to ripthrough**.
5. State back to Teddy in one or two lines: target subdir, kb status (read / new / missing), and mode. Then proceed.

Do not skip this protocol even on what feels like a small task. The KB read in particular has high ROI per token and prevents repeated mistakes.

---

## Operating modes

Two modes govern how often CC stops for human review.

**Ripthrough mode (default).** Hard stop only at end of plan (for plan approval). After approval, CC executes the full implementation end-to-end without stopping, marking todos complete as it goes. Use this when the plan is well-scoped and Teddy doesn't need intermediate go/no-go decisions.

**Checkpoint mode.** Hard stops at three points: end of research, end of plan, and end of each implementation phase as listed in the plan's todo list. At each stop CC summarizes what it did, what it learned (with kb updates), and what comes next, then waits for explicit "continue" from Teddy. Use this for exploratory work, novel methods, or anything where the right next step depends on what the previous step revealed.

**Declaring mode.** Teddy can say "ripthrough mode" or "checkpoint mode" at any point. He can also call specific stops in ripthrough: "stop after research", "stop after plan" (this is implicit in both modes), "stop between phases." CC should restate the mode and any custom stops back in one line before starting.

**Mode is sticky within a session.** If Teddy switches mid-session, CC confirms the switch and proceeds.

---

## Phase 1 — Research

**Goal:** build deep, written understanding of the relevant code and data before any planning.

**CC's job:**

1. Read the target code and any referenced data deeply. Not a skim. The signal-phrases that produce real depth are "deeply", "intricacies", "all specifics", "go through everything"; if Teddy uses them, take them literally.
2. Write findings to `research.md` in the target subdir. The chat is not a substitute — the file is the review surface.
3. If no `kb.md` exists in the subdir, create one now (template below) and seed it with anything generalizable from this research pass.
4. Update existing `kb.md` with any new invariants, gotchas, or data-shape facts surfaced during research.

**Required content in `research.md`:**

- **Problem framing.** CC's own restatement of the task — what we're doing, why, and what "done" looks like — written so a fresh CC instance reading only `cc-workflow.md` + `research.md` + `kb.md` could pick up where the last session left off without seeing the original chat. This is a proof-of-understanding section, not a transcription of Teddy's prompt. Include: task in CC's own words, success criteria (how we'll know it worked), explicit scope boundaries (what's in, what's deliberately out), constraints Teddy specified in the session, and any open questions about scope or intent that the plan will need to resolve. Update this section if scope shifts during research.
- What the code/system does at a behavioral level, not just structural.
- File-by-file roles for files relevant to the task.
- **Data-side assumptions and invariants explicitly captured.** For scientific work this is the single highest-ROI section. Specifically:
  - **CRS** of every spatial dataset (EPSG code if known; flag as "unknown — needs check" if not). Geographic vs. projected. Whether distance/area math is happening in a CRS where it is or isn't valid.
  - **Coordinate order** for every interface that takes points or bounding boxes (lon/lat vs. lat/lon). This is a recurring footgun across libraries — `shapely`/`geopandas` use (x=lon, y=lat); many external APIs and metadata files use (lat, lon).
  - **Units** of every numeric column or array. Meters vs. degrees, m/s vs. mph vs. knots, return-period years vs. annual exceedance probability, dB vs. linear.
  - **Dtypes and ranges.** Especially float32 vs. float64, signed vs. unsigned int, and the nodata sentinel for any raster (often -9999, 255, NaN — never assume).
  - **Time conventions.** UTC vs. local, naive vs. tz-aware, epoch base, calendar (proleptic Gregorian, noleap for some climate data).
- Known and suspected bugs, with file:line references.
- Open questions that the plan needs to answer.

**Stop condition (checkpoint mode only):** at end of research, summarize findings in chat and wait for Teddy to confirm before drafting the plan.

---

## Phase 2 — Plan

**Goal:** produce a written plan detailed enough that implementation is mechanical.

**CC writes `plan.md` in the target subdir. Required sections:**

1. **Approach.** Prose explanation of the technical strategy and why it fits this system. Reference `research.md` findings.
2. **File changes.** Every file to be created/modified, with the role of each change.
3. **Code snippets.** Show the actual shape of key changes — function signatures, data-structure definitions, key transformations. Not full implementations, but enough that the design choices are visible and reviewable.
4. **Test plan.** This is non-negotiable for scientific code:
   - **Smoke fixture and smoke test.** A tiny synthetic input (e.g., one structure, one storm, one terrain tile, a 10×10 raster) that runs the full pipeline in well under a minute and asserts invariants — output shape, dtype, finite-valued, in plausible range, deterministic under fixed seed. This is the highest-ROI test type for scientific code; spec it before any other test.
   - **Unit tests** for every I/O boundary and any function that transforms units, coordinate systems, or dtypes. Test the easy-to-flip cases explicitly (lon/lat order, CRS mismatch behavior, nodata-handling, NaN-handling).
   - **Property-based tests** where invariants are clean (output ≥ 0, monotonicity, symmetry, idempotence under repeated application). `hypothesis` is the default.
   - **Regression fixtures** if behavior depends on numerical values that should be locked in — save a small golden output and assert closeness with explicit `atol`/`rtol`.
5. **Validation plan.** How will we know the science is right, separate from the code being correct? For ML this means train/eval split strategy (spatial CV blocks if there's any geographic structure — random splits leak), calibration check, baseline-vs-model comparison, and at least one sanity plot or distribution check.
6. **Geospatial / numerical risk list.** Walk the checklist below and explicitly flag which items apply to this task and how the plan handles each one.
7. **Considerations and trade-offs.** What's deliberately not being done. What alternative approaches were considered and rejected. What's deferred to a follow-up.
8. **Todo list.** Granular task breakdown grouped into phases. CC will mark items complete during implementation.

**Plan grounding:** before writing the plan, read source files. If Teddy shared a reference implementation (open-source repo, paper, or another file in the project), study it first and write the plan around adopting/adapting that pattern rather than designing from scratch.

### The annotation cycle

This is the most important part of the workflow.

After CC writes the plan, Teddy opens `plan.md` in his editor and adds inline notes directly into the document. Notes vary from two words ("not optional") to paragraphs (constraint explanations, alternative approaches, data-shape examples).

Then Teddy returns and says something like: *"I added notes to the plan, address all the notes and update the document accordingly. Don't implement yet."*

**CC's behavior:**

1. Read every annotation. Address each one explicitly in the updated plan — accept, modify, or push back with a reason.
2. If a note conflicts with something elsewhere in the plan, fix the conflict, don't leave both versions.
3. Update the todo list if scope changed.
4. **Do not start implementation.** The `don't implement yet` guard is enforced even when it feels obvious the plan is good.
5. Reply in chat with a short summary of changes made and any annotations that need further discussion.

The cycle typically repeats 1–6 times. CC's posture during this cycle is **not** "defend the original plan" — Teddy has system context CC doesn't. But CC should push back honestly when a note would introduce a real problem (e.g., "this annotation removes the CRS check, but the test plan depends on it — proposing we keep the check and remove the redundant reprojection instead").

**Stop condition (both modes):** after the annotation cycle and before implementation, CC says some variant of *"Plan looks ready. Approve to implement?"* and waits for explicit go from Teddy. This is the one hard stop in both modes.

---

## Phase 3 — Implementation

When Teddy says go, CC executes. The default implementation directive (CC should follow even if Teddy uses a shorter phrasing like "go" or "implement it"):

> Implement the full plan. Mark each todo item complete in `plan.md` as you finish it. Do not stop until all phases and tasks are completed. Update `kb.md` with anything learned during implementation that a future session would benefit from. Run the smoke test after every meaningful change; run the full test suite at the end of each phase. Run `ruff check` and `mypy` (if configured in the repo) after each phase. Do not add filler comments or docstrings that restate the code; write docstrings only where the why is non-obvious. Type-hint every public function. No bare `except`; no mutable default arguments; no silent dtype or CRS coercions.

**During implementation:**

- The plan is the source of truth for progress. Update it, don't just track in chat.
- Run the smoke test continuously. If it breaks, stop the affected phase, diagnose, fix, then continue.
- Run `pytest -x --ff` (fail-fast, failed-first) during active development; full `pytest` at phase end.
- If `pyproject.toml` or `setup.cfg` configures `ruff` and/or `mypy`, run them at phase end and fix issues before marking the phase complete. If they're not configured, don't add them silently — flag it as a kb entry and continue.
- If a step in the plan turns out to be wrong (data assumption violated, library doesn't behave as expected), **stop, update the plan with what was learned, propose the revised approach, and wait for Teddy's go** — even in ripthrough mode. Ripthrough means no stops for routine progress, not no stops for newly-discovered facts that invalidate the plan.

**Checkpoint mode adds:** hard stop at the end of each phase listed in the plan's todo list. Summarize what was done, surface any deviations from plan, propose the next phase, wait for go.

### Feedback during implementation

Teddy's role shifts to supervisor; his prompts become short. Examples:

- "You didn't implement the deduplication step."
- "This belongs in the preprocessing module, not the model module. Move it."
- "wider"
- "the legend is overlapping the colorbar"

CC has full session context, so terse corrections are sufficient. Address them and continue. Don't pad with verbose acknowledgments.

For visual / plot work, Teddy may attach screenshots. Treat the screenshot as ground truth for what's visible; ask before changing anything that isn't shown.

**Reference-by-pointer is preferred over describing from scratch.** "This plot should look like the one in `notebooks/exploratory_v1.ipynb`" is more precise than five sentences of description. Read the reference before changing the target.

### Revert and re-scope

When implementation goes off the rails, do not try to patch. If Teddy says something like *"revert and let's try again with X"*, discard the working changes (`git restore`, `git checkout`) and re-scope with the narrower instruction. Narrowing scope after a revert produces better results than incrementally fixing a bad approach.

---

## Standing geospatial / numerical checklist

Reference list. CC walks this during research (data assumption capture) and during planning (risk list). Add to `kb.md` any task-specific instances of these that come up.

**Spatial:**

- CRS declared explicitly on every spatial input and output. EPSG code preferred over WKT.
- Distance/area/buffer math performed in an equal-area or local projected CRS, not in geographic degrees.
- Coordinate order verified at every interface boundary — especially when pulling from external APIs, reading metadata fields, or constructing geometries from raw tuples.
- Vector geometry validity checked (`is_valid`); `make_valid` or `buffer(0)` applied where needed; document the fix in `kb.md`.
- Raster stacks aligned (matching CRS, transform, resolution, extent, nodata) before any cell-wise operation. Mis-aligned rasters silently produce nonsense.
- Antimeridian and polar edge cases considered for any feature with global or wide-area scope.
- Nearest-neighbor and within-radius queries built on spatial indexes (`STRtree`, `GeoSeries.sindex`) for any non-tiny dataset.

**Numerical:**

- Dtype explicit and documented for arrays in hot paths. Float32 vs. float64 matters for both numerics and memory.
- NaN handling explicit — propagate, drop, or impute, never silently coerce.
- Raster nodata sentinel checked separately from NaN. Convert sentinel → NaN early in the pipeline and propagate NaN from there.
- Integer overflow considered for index math on large arrays.
- Random seeds set for any stochastic step. Both `numpy.random.default_rng(seed)` and any framework-specific seeds (`torch.manual_seed`, etc.).
- Floating-point comparisons use `np.isclose` / `math.isclose` with explicit tolerance, never `==`.

**ML-specific:**

- Train/test/val splits respect spatial (and temporal) structure. Random splits leak when nearby samples are correlated, which is almost always for property-cat data. Use spatial CV blocks or hold-out-by-storm / hold-out-by-region as appropriate.
- Feature columns audited for leakage from the target.
- Calibration checked, not just predictive accuracy. A model that ranks correctly but is miscalibrated is dangerous for downstream multipliers.
- Baseline comparison required. "Better than a sensible baseline" is the bar, not "any predictive signal."
- Reproducibility: pin `numpy`, `torch`/`tensorflow`/`jax`, and any geospatial libs in `pyproject.toml`. Pin the random seed. Save the trained model with its config and the data version it was trained on.

---

## The knowledge base — `kb.md`

The kb is CC's own working memory. Audience is future CC instances (post-compaction or new sessions), not Teddy. Teddy can read it, but CC should write for itself: terse, specific, no narrative padding.

**One kb per task subdirectory.** When a learning generalizes beyond the current task (e.g., "all Downstream rasters use -9999 nodata"), CC should still note it locally first and surface it to Teddy with a suggestion that it belongs in a higher-scope kb or in repo-level `CLAUDE.md`. Don't promote autonomously.

### Required sections (kb template)

```markdown
# kb — <task name>

Last updated: <ISO date>
Active size: <approx line count>

## Index
- Project invariants
- Gotchas
- Decisions
- Don't-do
- Open questions
- Archive (superseded entries — keep, don't delete)

## Project invariants
Things that are true across this task/subdir and should never have to be re-discovered.
Format: terse statement + (optional) why-it-matters one-liner.

- All coordinates EPSG:4326 unless explicitly tagged in column name (e.g., `_3857`).
- Raster nodata sentinel is -9999 for elevation, 255 for landcover.
- Wind speeds in m/s throughout; convert at I/O boundaries only.

## Gotchas
Pitfalls encountered. Each entry stamped with date.
Format: <date> — <what bit us> — <fix or workaround>

- 2026-05-14 — `gpd.read_file` returned (lon, lat) tuples but the storm-track CSV uses (lat, lon). Added explicit swap with assert at the read boundary.

## Decisions
Mini-ADRs for non-obvious choices.
Format: <date> — <decision> — <alternatives considered> — <why this one>

- 2026-05-14 — Use `rasterio` over `rioxarray` for the alignment step — rioxarray's lazy dask backend was adding latency for our small tiles — revisit if tile sizes grow.

## Don't-do
Things that were tried and don't work, or things we explicitly chose against. Keep CC from re-suggesting them.

- Don't use `geopandas.sjoin` with the default `op='intersects'` for point-in-polygon — use `op='within'` for clarity, otherwise boundary cases differ between libraries.

## Open questions
Unresolved items. Should resolve or be archived within a few sessions.

- Is the storm-track interpolation supposed to use great-circle or rhumb-line? Defaulted to great-circle; flag at next review.

## Archive
Superseded entries. Keep so future CC doesn't re-derive the same conclusion and so we can see why something changed.

- [2026-04-30, superseded 2026-05-14] Used float64 throughout — changed to float32 in hot paths after profiling showed 2x memory pressure with no accuracy loss.
```

### Update triggers

CC must update `kb.md` when any of the following happen:

1. A new invariant about the system or data is discovered or confirmed.
2. A gotcha bites — even a small one. Record it the moment it's found, not at the end of the session.
3. A non-obvious decision is made. Log it as a mini-ADR.
4. A path was explored and rejected — capture the rejection so it's not re-tried.
5. The plan or research turned out to be wrong about something. Update kb with the corrected fact.
6. Teddy provides domain knowledge in chat that future sessions would need.

Updating happens during the work, not at the end. A retrospective kb pass at session end is a fallback, not the primary mechanism.

### Pruning policy

The kb is meant to stay useful, not exhaustive. Hard rules:

- **Target size: 200–400 lines.** When approaching 400, prune.
- **Pruning style: collapse, archive, don't delete silently.** Duplicate gotchas collapse to one entry. Superseded decisions move to the Archive section with the date of supersession. Stale "open questions" that have been resolved get folded into Invariants or Decisions and removed from Open.
- **Promote heavily-cited entries to the top of their section.** The first three entries in each section should be the most frequently-relevant.
- **Run a maintenance pass when:** size exceeds target, after a major refactor of the underlying code, or when CC notices the kb is contradicting itself (which means something changed that wasn't archived).
- **Surface to Teddy:** if a maintenance pass would remove or archive more than ~20% of entries, summarize the proposed changes and confirm with Teddy before applying.

### Read triggers

CC must read `kb.md` (in full) at:

1. Session start, per the session-start protocol.
2. After auto-compaction, before resuming work.
3. Before starting any sub-task that touches code or data the kb has entries about.

---

## File-naming defaults

For each task subdirectory, the default artifact set is:

- `research.md` — Phase 1 output.
- `plan.md` — Phase 2 output (single file across annotation cycles; preserve history via git, not by spawning `plan-v2.md`).
- `kb.md` — living knowledge base.

If the subdir houses multiple distinct tasks, CC may use more specific names (e.g., `research-wind-multiplier-mvp.md`, `plan-wind-multiplier-mvp.md`, `kb-wind-multiplier-mvp.md`) and should mention the choice in chat at first use.

**Never backdate files.** Per the Downstream legal posture, file timestamps may matter; create files in the present and let git record history. Don't reorganize folder structures in a way that obscures when things were created.

---

## Things CC should not do without explicit Teddy approval

- Start writing implementation code before the plan is approved.
- Refactor unrelated files while implementing a planned change.
- Add a new dependency that isn't already in `pyproject.toml`.
- Change function signatures of any function called from outside the current module.
- Modify or remove an existing test.
- Delete entries from `kb.md` (archive, don't delete).
- Reorganize the repo's folder structure.

For each of these: stop, propose, wait for go.

---

## Workflow in one paragraph

Confirm target subdir and mode at session start, read any existing `kb.md` first. Research deeply and write `research.md`, starting with CC's own restatement of the task and success criteria (so a fresh instance can resume from artifacts alone) and capturing data/CRS/units/dtype assumptions explicitly. Write `plan.md` with approach, file changes, code snippets, a smoke fixture and test plan, a validation plan, an explicit walk of the geospatial/numerical checklist, considerations, and a granular todo list. Iterate on the plan via inline annotations until Teddy approves — `don't implement yet` is enforced. On approval, execute the full plan, updating todos and kb as you go, running the smoke test continuously and the test suite plus lint/typecheck at the end of each phase. Stop if a new fact invalidates the plan; otherwise run to completion. Maintain `kb.md` as terse, pruned, future-CC-readable memory.
