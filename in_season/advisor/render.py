"""Actionable decision page — stakes-scaled with native ``<details>`` drill-down (§3.8).

The top-level scan is all headlines (fixed density, ~10s read); depth is one click away
per item. No JS — published static to GitHub Pages. Detail scales with stakes: a sit/start
is one line; a significant add/drop carries a full drill-down (EV table + self-critique);
a hold day shows "No moves." + one closest-call line.

``render_decision_page`` is pure (context + decisions -> HTML, testable); ``publish_page``
writes ``docs/index.html`` + ``docs/archive/<date>.html`` (Tier-1 committed) with prev/next nav.
"""

import html
import logging
from datetime import datetime

from advisor import config as cfg

log = logging.getLogger("advisor.render")

_TIER_LABEL = {"tweak": "Lineup", "stream": "Streaming", "significant": "Roster move",
               "hold": "Hold"}


def _esc(x):
    return html.escape(str(x if x is not None else ""))


def _winprob_header(context):
    wp = (context.get("winprob") or {}).get("overall", {})
    p = wp.get("p_win_matchup")
    pct = f"{p * 100:.0f}%" if isinstance(p, (int, float)) else "—"
    cats = wp.get("expected_cats_won")
    mu = context.get("moves_used")
    moves_str = f"{mu if mu is not None else '?'}/{context.get('moves_max')}"
    meta = (f"Week {context.get('matchup_week')}, day {context.get('matchup_day')} of "
            f"{context.get('matchup_length_days')} · {context.get('days_remaining')}d left · "
            f"vs {_esc(context.get('opponent'))} · moves {moves_str}")
    return (f'<div class="hdr"><div class="pwin">{pct}<span>P(win)</span></div>'
            f'<div class="meta">{meta}<br>expected categories won: '
            f'{_esc(round(cats, 1) if isinstance(cats,(int,float)) else "—")}</div></div>')


def _winprob_cats(context):
    by_cat = (context.get("winprob") or {}).get("by_cat", {})
    if not by_cat:
        return ""
    chips = []
    for cat in cfg.ALL_CATS:
        d = by_cat.get(cat)
        if not d:
            continue
        status = d.get("status", "")
        cls = {"clinched": "clinched", "lost": "lost"}.get(status, "live")
        chips.append(f'<span class="chip {cls}" title="P(win)={d.get("p_win")}">'
                     f'{cat} {int(round((d.get("p_win") or 0)*100))}%</span>')
    return '<div class="cats">' + "".join(chips) + "</div>"


def _decision_block(d):
    headline = _esc(d.get("headline") or d.get("type", "decision"))
    one = _esc(d.get("one_liner") or "")
    tier = d.get("tier", "tweak")
    conf = _esc(d.get("confidence", ""))
    label = _TIER_LABEL.get(tier, tier)
    drill = d.get("drilldown_md")
    summary = (f'<div class="dline"><span class="tag {tier}">{label}</span>'
               f'<b>{headline}</b>'
               + (f' <span class="conf">({conf})</span>' if conf else "")
               + (f'<div class="one">{one}</div>' if one else "") + "</div>")
    if drill:
        body = _esc(drill).replace("\n", "<br>")
        return (f'<details class="dec {tier}"><summary>{summary}</summary>'
                f'<div class="drill">{body}</div></details>')
    return f'<div class="dec {tier}">{summary}</div>'


def render_decision_page(context, decisions, closest_call=None):
    """Pure: context + analyst decisions -> the decision-page HTML string."""
    decisions = decisions or []
    moves = [d for d in decisions if d.get("type") != "hold"]
    date = context.get("date", "")

    parts = [_winprob_header(context), _winprob_cats(context)]
    if not moves:
        cc = closest_call or _first_closest(decisions)
        parts.append('<div class="hold"><b>No moves.</b>'
                     + (f'<div class="cc">Closest call: {_esc(cc)}</div>' if cc else "")
                     + "</div>")
    else:
        # Order by stakes (significant first), so the consequential items lead.
        order = {"significant": 0, "stream": 1, "tweak": 2, "hold": 3}
        for d in sorted(moves, key=lambda x: order.get(x.get("tier"), 9)):
            parts.append(_decision_block(d))
        holds = [d for d in decisions if d.get("type") == "hold"]
        cc = closest_call or _first_closest(holds)
        if cc:
            parts.append(f'<div class="cc">Also considered: {_esc(cc)}</div>')

    for w in context.get("data_warnings", []) or []:
        parts.append(f'<div class="warn">⚠ {_esc(w)}</div>')

    return _PAGE_TEMPLATE.format(date=_esc(date), body="\n".join(parts),
                                 generated=datetime.now().strftime("%Y-%m-%d %H:%M"))


def _first_closest(decisions):
    for d in decisions or []:
        if d.get("closest_call"):
            return d["closest_call"]
    return None


def publish_page(html_str, date, *, docs_dir=None, archive_dir=None):
    """Write index.html + archive/<date>.html (Tier-1 committed) with prev/next nav."""
    docs_dir = docs_dir or cfg.DOCS_DIR
    archive_dir = archive_dir or cfg.DOCS_ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(p.stem for p in archive_dir.glob("*.html"))
    nav = _nav_html(existing, date)
    page = html_str.replace("<!--NAV-->", nav)
    (archive_dir / f"{date}.html").write_text(page, encoding="utf-8")
    (docs_dir / "index.html").write_text(page, encoding="utf-8")
    log.info("Published decision page for %s", date)
    return docs_dir / "index.html"


def _nav_html(existing_dates, date):
    dates = sorted(set(existing_dates) | {date})
    i = dates.index(date)
    prev_l = (f'<a href="{dates[i-1]}.html">&larr; {dates[i-1]}</a>' if i > 0 else "<span></span>")
    next_l = (f'<a href="{dates[i+1]}.html">{dates[i+1]} &rarr;</a>'
              if i < len(dates) - 1 else "<span></span>")
    return f'<div class="nav">{prev_l}<span>{date}</span>{next_l}</div>'


_PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brohei Brotanis — {date}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:680px;margin:0 auto;
   padding:16px;color:#1a1a1a;background:#fafafa;line-height:1.45}}
 .nav{{display:flex;justify-content:space-between;font-size:.85rem;margin-bottom:12px;color:#666}}
 .nav a{{color:#2b6cb0;text-decoration:none}}
 .hdr{{display:flex;gap:14px;align-items:center;border-bottom:2px solid #e2e2e2;padding-bottom:12px}}
 .pwin{{font-size:2.2rem;font-weight:700;color:#2b6cb0;line-height:1}}
 .pwin span{{display:block;font-size:.6rem;color:#888;font-weight:400;letter-spacing:.05em}}
 .meta{{font-size:.85rem;color:#555}}
 .cats{{display:flex;flex-wrap:wrap;gap:5px;margin:12px 0}}
 .chip{{font-size:.72rem;padding:2px 7px;border-radius:10px;background:#eef;border:1px solid #dde}}
 .chip.live{{background:#fff6e0;border-color:#f0d890}}
 .chip.clinched{{background:#e3f6e3;border-color:#b6e0b6;color:#2a6}}
 .chip.lost{{background:#f6e3e3;border-color:#e0b6b6;color:#a44}}
 .dec{{margin:10px 0;padding:10px 12px;background:#fff;border:1px solid #e6e6e6;border-radius:8px}}
 details.dec summary{{cursor:pointer;list-style:none}}
 details.dec summary::-webkit-details-marker{{display:none}}
 .tag{{font-size:.62rem;text-transform:uppercase;letter-spacing:.04em;padding:1px 6px;border-radius:4px;
   margin-right:7px;background:#eee;color:#666}}
 .tag.significant{{background:#fde0e0;color:#b33}} .tag.stream{{background:#e0ecfd;color:#36c}}
 .tag.tweak{{background:#eee;color:#777}}
 .one{{font-size:.85rem;color:#555;margin-top:3px}}
 .conf{{font-size:.78rem;color:#999}}
 .drill{{margin-top:10px;padding-top:10px;border-top:1px dashed #ddd;font-size:.85rem;color:#444}}
 .hold{{margin:18px 0;padding:14px;background:#fff;border:1px solid #e6e6e6;border-radius:8px;font-size:1.05rem}}
 .cc{{font-size:.85rem;color:#666;margin-top:8px}}
 .warn{{font-size:.78rem;color:#a60;background:#fff8ec;border:1px solid #f0e0c0;padding:6px 9px;
   border-radius:6px;margin-top:10px}}
 footer{{margin-top:24px;font-size:.72rem;color:#aaa;text-align:center}}
</style></head><body>
<!--NAV-->
{body}
<footer>Generated {generated} · advisor</footer>
</body></html>"""
