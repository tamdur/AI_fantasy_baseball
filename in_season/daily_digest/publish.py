"""
Publish newsletter to docs/ for GitHub Pages.

Converts the plain-text newsletter to a minimal static HTML page.
Archives previous index.html before overwriting.
Each page has prev/next navigation links forming a chain.
"""

import re
import shutil
import logging
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR, ROOT

log = logging.getLogger(__name__)

DOCS_DIR = ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"


def publish_newsletter(newsletter_text, briefing_book=None):
    """
    Publish newsletter text as docs/index.html (GitHub Pages).
    Archives the previous index.html and wires up prev/next navigation.
    Returns the path to the published file.
    """
    DOCS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    index_path = DOCS_DIR / "index.html"

    # Archive previous newsletter if it exists
    archived_name = None
    if index_path.exists():
        archived_name = _archive_previous(index_path)

    # Extract metadata from briefing book or newsletter
    today = datetime.now().strftime("%Y-%m-%d")
    opponent = ""
    matchup_week = ""
    if briefing_book:
        today = briefing_book.get("date", today)
        opponent = briefing_book.get("opponent", "")
        matchup_week = briefing_book.get("matchup_week", "")

    title = f"Daily Briefing — {today}"
    if opponent:
        title += f" vs {opponent}"

    # Determine prev link for the new index.html
    prev_href = f"archive/{archived_name}" if archived_name else ""

    # Convert newsletter text to HTML
    html = _render_html(newsletter_text, title, today, matchup_week,
                        prev_href=prev_href, next_href="",
                        is_archive=False)

    index_path.write_text(html, encoding="utf-8")
    log.info(f"Published newsletter to {index_path}")

    # Update the archived page's "next" link to point to new index
    if archived_name:
        _update_next_link(ARCHIVE_DIR / archived_name, "../index.html")

    return index_path


def _archive_previous(index_path):
    """
    Move previous index.html to archive/ with date-based filename.
    Returns the archive filename (e.g., "2026-03-26.html").
    """
    content = index_path.read_text(encoding="utf-8")

    # Extract date from the page title or content
    m = re.search(r'(\d{4}-\d{2}-\d{2})', content)
    if m:
        archive_date = m.group(1)
    else:
        archive_date = datetime.now().strftime("%Y-%m-%d")

    archive_name = f"{archive_date}.html"
    archive_path = ARCHIVE_DIR / archive_name

    # Handle same-day re-runs with numeric suffixes
    if archive_path.exists():
        suffix = 2
        while (ARCHIVE_DIR / f"{archive_date}-{suffix}.html").exists():
            suffix += 1
        archive_name = f"{archive_date}-{suffix}.html"
        archive_path = ARCHIVE_DIR / archive_name

    # Before copying, rewrite the page's nav links for its new archive location.
    # The prev link (if any) needs to be relative to archive/ not docs/.
    content = _rewrite_links_for_archive(content)

    archive_path.write_text(content, encoding="utf-8")
    log.info(f"Archived previous newsletter to {archive_name}")
    return archive_name


def _rewrite_links_for_archive(html):
    """Rewrite nav href paths when moving index.html into archive/."""
    # "archive/2026-03-25.html" -> "2026-03-25.html" (now a sibling)
    html = re.sub(r'href="archive/([^"]+)"', r'href="\1"', html)
    return html


def _update_next_link(archive_path, next_href):
    """Update an archived page's 'next' nav link."""
    if not archive_path.exists():
        return
    content = archive_path.read_text(encoding="utf-8")

    # Unhide the next link and set its href
    content = re.sub(
        r'<a href="[^"]*" class="nav-link nav-next"[^>]*>',
        f'<a href="{next_href}" class="nav-link nav-next">',
        content,
    )
    # Remove hidden attribute if present
    content = content.replace('class="nav-link nav-next" hidden>', 'class="nav-link nav-next">')

    archive_path.write_text(content, encoding="utf-8")


def _get_sorted_archives():
    """Get archive files sorted chronologically."""
    if not ARCHIVE_DIR.exists():
        return []
    return sorted(ARCHIVE_DIR.glob("*.html"))


# ---- HTML Rendering ----

def _convert_body(newsletter_text):
    """Convert plain-text newsletter to HTML body content."""
    body = newsletter_text
    body = body.replace("&", "&amp;")
    body = body.replace("<", "&lt;")
    body = body.replace(">", "&gt;")

    # Bold
    body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', body)
    body = re.sub(r'__(.+?)__', r'<strong>\1</strong>', body)

    # Section headers with box-drawing chars
    body = re.sub(r'^(━+.+━+)$', r'<h2>\1</h2>', body, flags=re.MULTILINE)
    body = re.sub(r'^(━━━.+━━━)$', r'<h3>\1</h3>', body, flags=re.MULTILINE)

    # Dashboard tables
    lines = body.split("\n")
    in_table = False
    result_lines = []
    for line in lines:
        stripped = line.strip()
        if "|" in stripped and not stripped.startswith("<"):
            if not in_table:
                result_lines.append('<div class="table-wrap"><table>')
                in_table = True
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]
            if all(c.replace("-", "").replace(" ", "") == "" for c in cells):
                continue
            row = "".join(f"<td>{c}</td>" for c in cells)
            result_lines.append(f"<tr>{row}</tr>")
        else:
            if in_table:
                result_lines.append("</table></div>")
                in_table = False
            result_lines.append(line)
    if in_table:
        result_lines.append("</table></div>")
    body = "\n".join(result_lines)

    # Bullet points
    body = re.sub(r'^• (.+)$', r'<li>\1</li>', body, flags=re.MULTILINE)
    body = re.sub(r'(<li>.*</li>\n?)+', lambda m: f'<ul>{m.group(0)}</ul>', body)

    # Emoji markers
    body = body.replace("⚠", '<span class="warn">⚠</span>')
    body = body.replace("🔴", '<span class="crit">🔴</span>')
    body = body.replace("🟡", '<span class="note">🟡</span>')
    body = body.replace("🟢", '<span class="ok">🟢</span>')

    # Paragraphs
    body = re.sub(r'\n\n+', '</p><p>', body)
    body = f"<p>{body}</p>"

    return body


def _render_html(newsletter_text, title, date_str, matchup_week,
                 prev_href="", next_href="", is_archive=False):
    """Render full HTML page with prev/next navigation."""
    body = _convert_body(newsletter_text)

    # Navigation links
    prev_hidden = ' hidden' if not prev_href else ''
    next_hidden = ' hidden' if not next_href else ''

    # Archive list for footer
    archives = _get_sorted_archives()
    archive_links_html = ""
    if archives:
        links = []
        for a in reversed(archives[-15:]):
            name = a.stem
            if is_archive:
                links.append(f'<a href="{a.name}">{name}</a>')
            else:
                links.append(f'<a href="archive/{a.name}">{name}</a>')
        archive_links_html = " · ".join(links)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: "SF Mono", "Menlo", "Consolas", monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #e0dcd4;
  background: #1a1a2e;
  max-width: 760px;
  margin: 0 auto;
  padding: 1.5rem;
}}
header {{
  text-align: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #333;
}}
header h1 {{ font-size: 20px; font-weight: 700; }}
header .date {{ color: #8a8580; font-size: 13px; }}
.issue-nav {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  font-size: 14px;
}}
.nav-link {{
  color: #8a8580;
  text-decoration: none;
  padding: 4px 0;
}}
.nav-link:hover {{ color: #d4a574; }}
.nav-link[hidden] {{ visibility: hidden; }}
h2 {{
  font-size: 15px;
  color: #d4a574;
  margin: 1.5rem 0 0.5rem;
  letter-spacing: 0.5px;
}}
h3 {{
  font-size: 14px;
  color: #d4a574;
  margin: 1.2rem 0 0.3rem;
}}
p {{ margin-bottom: 0.5rem; white-space: pre-wrap; }}
ul {{ list-style: none; margin: 0.5rem 0; }}
li {{ padding-left: 1.2rem; position: relative; margin-bottom: 0.5rem; white-space: normal; }}
li::before {{ content: "•"; position: absolute; left: 0; color: #d4a574; }}
strong {{ color: #fff; }}
.warn {{ color: #e6c44d; }}
.crit {{ color: #e05555; }}
.note {{ color: #e6c44d; }}
.ok {{ color: #5cb85c; }}
.table-wrap {{
  overflow-x: auto;
  margin: 0.5rem 0;
}}
table {{
  border-collapse: collapse;
  font-size: 13px;
  width: 100%;
}}
td {{
  padding: 3px 8px;
  border-bottom: 1px solid #2a2a40;
  white-space: nowrap;
}}
tr:first-child td {{ color: #8a8580; font-weight: 600; border-bottom: 1px solid #444; }}
footer {{
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid #333;
  font-size: 12px;
  color: #666;
}}
footer a {{ color: #8a8580; text-decoration: none; }}
footer a:hover {{ color: #d4a574; }}
.archive-list {{ margin-top: 0.5rem; line-height: 2; }}
</style>
</head>
<body>
<header>
  <h1>⚾ Brohei Brotanis — Daily Briefing</h1>
  <div class="date">{date_str} · Week {matchup_week}</div>
</header>
<nav class="issue-nav">
  <a href="{prev_href}" class="nav-link nav-prev"{prev_hidden}>← Previous</a>
  <a href="{next_href}" class="nav-link nav-next"{next_hidden}>Next →</a>
</nav>
<main>
{body}
</main>
<footer>
  <nav class="issue-nav">
    <a href="{prev_href}" class="nav-link nav-prev"{prev_hidden}>← Previous</a>
    <a href="{next_href}" class="nav-link nav-next"{next_hidden}>Next →</a>
  </nav>
  <div class="archive-list">Past briefings: {archive_links_html if archive_links_html else "<em>none yet</em>"}</div>
  <p style="margin-top:0.5rem">Generated by <a href="https://github.com/tamdur/AI_fantasy_baseball">AI Fantasy Baseball</a></p>
</footer>
</body>
</html>"""
