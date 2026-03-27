"""
Multi-agent newsletter generation via Claude Code CLI (MAX plan, no per-token cost).

Pipeline: Tactician → Actuary → Synthesizer
- Tactician and Actuary run in parallel (independent analyses)
- Synthesizer resolves disagreements and produces final newsletter
"""

import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import PROMPTS_DIR, OUTPUT_DIR

log = logging.getLogger(__name__)

CLAUDE_TIMEOUT = None  # No timeout — deep analytical work takes as long as it takes


def _load_prompt(name):
    """Load a system prompt from the prompts directory."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text()


def _call_claude(prompt, model="sonnet", label="agent"):
    """Call Claude Code CLI with a prompt via stdin. Returns response text."""
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", model, "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(OUTPUT_DIR),
        )

        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
            log.info(f"  [{label}] Response: {len(text)} chars")
            return text
        else:
            log.error(f"  [{label}] Failed (code {result.returncode}): {result.stderr[:300]}")
            return None

    except FileNotFoundError:
        log.error(f"  [{label}] 'claude' CLI not found")
        return None
    except Exception as e:
        log.error(f"  [{label}] Error: {e}")
        return None


# ---- Individual Agent Calls ----

def run_tactician(briefing_book: dict) -> str:
    """Category Tactician analysis."""
    system_prompt = _load_prompt("tactician")
    briefing_json = json.dumps(briefing_book, indent=2, default=str)

    prompt = f"""{system_prompt}

---

Here is today's briefing book data. Produce your full Tactician analysis following the output format specified above.

```json
{briefing_json}
```

Analyze now. Be specific — name players, cite z-scores, estimate P(win) for each category, compute rate-stat dilution for every pitching recommendation."""

    return _call_claude(prompt, model="sonnet", label="Tactician")


def run_actuary(briefing_book: dict) -> str:
    """Actuary risk analysis."""
    system_prompt = _load_prompt("actuary")
    briefing_json = json.dumps(briefing_book, indent=2, default=str)

    prompt = f"""{system_prompt}

---

Here is today's briefing book data. Produce your full Actuary risk analysis following the output format specified above. Generate Risk Cards for each plausible add/drop move. Flag all regression signals and negative-EV traps.

```json
{briefing_json}
```

Analyze now. Be quantitative — compute delta-EV for every proposed move, show rate-stat dilution tables, cite Savant/regression data where available."""

    return _call_claude(prompt, model="sonnet", label="Actuary")


def run_synthesizer(briefing_book: dict, tactician_output: str, actuary_output: str) -> str:
    """Synthesizer — resolves disagreements, produces final newsletter."""
    system_prompt = _load_prompt("synthesizer")
    briefing_json = json.dumps(briefing_book, indent=2, default=str)

    prompt = f"""{system_prompt}

---

Below are the analyses from the Category Tactician and the Actuary. Also included is the raw briefing book data for reference.

## TACTICIAN ANALYSIS:
{tactician_output}

## ACTUARY ANALYSIS:
{actuary_output}

## BRIEFING BOOK DATA:
```json
{briefing_json}
```

Now produce the final newsletter. Follow the exact output format from the system prompt:
1. Resolve agreements → Tier 1
2. Partial agreement with risk → Tier 2
3. Disagreements → Tier 3
4. Actuary vetoes → flag and explain
5. Include the Matchup Dashboard, Transaction Budget, Roster Health, and Appendix sections.

Be concise above the fold (60-second scan). The Appendix can be detailed."""

    return _call_claude(prompt, model="sonnet", label="Synthesizer")


# ---- Main Pipeline ----

def generate_newsletter(briefing_book: dict) -> str:
    """
    Full multi-agent pipeline: Tactician + Actuary (parallel) → Synthesizer.
    Falls back to single-call MVP if any agent fails.
    """
    log.info("Running multi-agent pipeline...")

    # Step 1: Run Tactician and Actuary in parallel
    tactician_output = None
    actuary_output = None

    log.info("  Dispatching Tactician and Actuary in parallel...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(run_tactician, briefing_book): "Tactician",
            executor.submit(run_actuary, briefing_book): "Actuary",
        }
        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                result = future.result()
                if agent_name == "Tactician":
                    tactician_output = result
                else:
                    actuary_output = result
            except Exception as e:
                log.error(f"  {agent_name} raised exception: {e}")

    # Save intermediate outputs for debugging
    if tactician_output:
        (OUTPUT_DIR / "tactician_output.txt").write_text(tactician_output, encoding="utf-8")
    if actuary_output:
        (OUTPUT_DIR / "actuary_output.txt").write_text(actuary_output, encoding="utf-8")

    # Step 2: If either agent failed, fall back to MVP single-call
    if not tactician_output or not actuary_output:
        log.warning("One or both agents failed — falling back to MVP single-call")
        return generate_mvp_newsletter(briefing_book)

    # Step 3: Run Synthesizer
    log.info("  Running Synthesizer...")
    newsletter = run_synthesizer(briefing_book, tactician_output, actuary_output)

    if not newsletter:
        log.warning("Synthesizer failed — falling back to MVP single-call")
        return generate_mvp_newsletter(briefing_book)

    # Step 4: Post-processing validation
    newsletter = _validate_newsletter(newsletter, briefing_book)

    # Step 5: Extract and save issue logs from agent outputs
    _save_issue_logs(tactician_output, actuary_output)

    log.info(f"Multi-agent newsletter complete: {len(newsletter)} chars")
    return newsletter


def _validate_newsletter(newsletter, briefing_book):
    """
    Post-processing validation on the generated newsletter.
    Fixes the header line Day X/Y and Moves X/Y using briefing book values.
    """
    import re

    matchup_day = briefing_book.get("matchup_day")
    matchup_length = briefing_book.get("matchup_length_days")
    moves_max = briefing_book.get("moves_max")

    if matchup_day and matchup_length:
        newsletter = re.sub(
            r'Day \d+/\d+',
            f'Day {matchup_day}/{matchup_length}',
            newsletter,
            count=1,
        )

    if moves_max:
        newsletter = re.sub(
            r'Moves:\s*(\d+)/\d+',
            lambda m: f'Moves: {m.group(1)}/{moves_max}',
            newsletter,
            count=1,
        )

    return newsletter


def _save_issue_logs(tactician_output, actuary_output):
    """Extract and append issue logs from agent outputs to a persistent file."""
    from datetime import datetime
    issue_log_path = OUTPUT_DIR / "agent_issue_log.md"
    issues_found = []

    for agent_name, output in [("Tactician", tactician_output), ("Actuary", actuary_output)]:
        if not output:
            continue
        # Look for ## ISSUE LOG section
        marker = "## ISSUE LOG"
        idx = output.find(marker)
        if idx == -1:
            continue
        log_section = output[idx + len(marker):].strip()
        # Extract lines that start with "- ["
        for line in log_section.split("\n"):
            line = line.strip()
            if line.startswith("- ["):
                issues_found.append(f"  {agent_name}: {line}")
            elif not line or line.startswith("#"):
                break  # end of issue log section

    if issues_found:
        today = datetime.now().strftime("%Y-%m-%d")
        entry = f"\n### {today}\n" + "\n".join(issues_found) + "\n"

        # Append to persistent log
        if issue_log_path.exists():
            existing = issue_log_path.read_text()
        else:
            existing = "# Agent Issue Log\n\nPersistent record of data gaps and workflow issues flagged by agents.\n"

        issue_log_path.write_text(existing + entry, encoding="utf-8")
        log.info(f"  Issue log: {len(issues_found)} issues recorded")
    else:
        log.info("  Issue log: no issues flagged (clean run)")


def generate_mvp_newsletter(briefing_book: dict) -> str:
    """Fallback: single Claude call (the Phase 1 MVP approach)."""
    system_prompt = _load_prompt("mvp_analyst")
    briefing_json = json.dumps(briefing_book, indent=2, default=str)

    prompt = f"""You are a fantasy baseball analyst. Read the system prompt and briefing book data below, then produce the daily newsletter.

SYSTEM PROMPT:
{system_prompt}

BRIEFING BOOK DATA:
```json
{briefing_json}
```

Produce the newsletter now following the exact output format specified in the system prompt. Be specific and actionable. Reference actual player names, projected stats, and category impacts. Include the APPENDIX with extended analyst reasoning at the end."""

    result = _call_claude(prompt, model="sonnet", label="MVP")
    if result:
        return result
    return _fallback_newsletter(briefing_book)


def _fallback_newsletter(briefing_book: dict) -> str:
    """Basic newsletter without Claude when CLI is unavailable."""
    lines = [
        "━━━ DAILY BRIEFING (FALLBACK — Claude Code unavailable) ━━━",
        f"Date: {briefing_book.get('date', 'unknown')}",
        f"Opponent: {briefing_book.get('opponent', 'unknown')}",
        "",
        "━━━ MATCHUP DASHBOARD ━━━",
    ]

    cat_state = briefing_book.get("category_state", {})
    for cat, state in cat_state.items():
        lines.append(f"  {cat:6s} | You: {state['you']:>8} | Opp: {state['opp']:>8} | {state['status'].upper()}")

    triage = briefing_book.get("category_triage", {})
    lines.append("")
    lines.append("━━━ CATEGORY TRIAGE ━━━")
    for bucket, cats in triage.items():
        if cats:
            lines.append(f"  {bucket}: {', '.join(cats)}")

    lines.append("")
    lines.append("━━━ DROP CANDIDATES ━━━")
    for p in briefing_book.get("drop_candidates", []):
        w = p.get("ros_werth", "?")
        lines.append(f"  {p['name']} — WERTH: {w}")

    lines.append("")
    lines.append("━━━ TOP FREE AGENTS ━━━")
    for p in briefing_book.get("top_free_agents", [])[:10]:
        w = p.get("ros_werth", "?")
        lines.append(f"  {p['name']} ({', '.join(p.get('positions', []))}) — WERTH: {w}")

    lines.append("")
    lines.append("⚠ Claude Code was unavailable. This is raw data only — no analyst recommendations.")
    return "\n".join(lines)
