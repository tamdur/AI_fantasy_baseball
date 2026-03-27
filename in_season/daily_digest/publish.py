"""
Publish newsletter to docs/ for GitHub Pages.

Converts the plain-text newsletter to a minimal static HTML page.
Archives previous index.html before overwriting.
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
    Archives the previous index.html if it exists.
    Returns the path to the published file.
    """
    DOCS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    index_path = DOCS_DIR / "index.html"

    # Archive previous newsletter if it exists
    if index_path.exists():
        _archive_previous(index_path)

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

    # Convert newsletter text to HTML
    html = _render_html(newsletter_text, title, today, matchup_week)

    index_path.write_text(html, encoding="utf-8")
    log.info(f"Published newsletter to {index_path}")

    return index_path


def _archive_previous(index_path):
    """Move previous index.html to archive/ with date-based filename."""
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
        archive_path = ARCHIVE_DIR / f"{archive_date}-{suffix}.html"

    shutil.copy2(index_path, archive_path)
    log.info(f"Archived previous newsletter to {archive_path.name}")


def _render_html(newsletter_text, title, date_str, matchup_week):
    """Convert plain-text newsletter to clean HTML."""
    # Escape HTML entities in the newsletter text
    body = newsletter_text
    body = body.replace("&", "&amp;")
    body = body.replace("<", "&lt;")
    body = body.replace(">", "&gt;")

    # Convert markdown-style formatting
    # Bold: **text** or __text__
    body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', body)
    body = re.sub(r'__(.+?)__', r'<strong>\1</strong>', body)

    # Section headers with box-drawing chars
    body = re.sub(r'^(━+.+━+)$', r'<h2>\1</h2>', body, flags=re.MULTILINE)
    body = re.sub(r'^(━━━.+━━━)$', r'<h3>\1</h3>', body, flags=re.MULTILINE)

    # Dashboard tables: lines with | separators
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
            cells = [c for c in cells if c]  # remove empty edge cells
            if all(c.replace("-", "").replace(" ", "") == "" for c in cells):
                # Separator row — skip
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

    # Warning/info markers
    body = body.replace("⚠", '<span class="warn">⚠</span>')
    body = body.replace("🔴", '<span class="crit">🔴</span>')
    body = body.replace("🟡", '<span class="note">🟡</span>')
    body = body.replace("🟢", '<span class="ok">🟢</span>')

    # Paragraphs: double newlines
    body = re.sub(r'\n\n+', '</p><p>', body)
    body = f"<p>{body}</p>"

    # Build archive navigation
    archive_links = _build_archive_nav()

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
li {{ padding-left: 1.2rem; position: relative; margin-bottom: 0.5rem; }}
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
nav {{
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid #333;
  font-size: 12px;
  color: #666;
}}
nav a {{ color: #8a8580; text-decoration: none; }}
nav a:hover {{ color: #d4a574; }}
</style>
</head>
<body>
<header>
  <h1>⚾ Brohei Brotanis — Daily Briefing</h1>
  <div class="date">{date_str} · Week {matchup_week}</div>
</header>
<main>
{body}
</main>
<nav>
  <p>Archive: {archive_links}</p>
  <p>Generated by <a href="https://github.com/tamdur/AI_fantasy_baseball">AI Fantasy Baseball</a></p>
</nav>
</body>
</html>"""


def _build_archive_nav():
    """Build HTML links to archived newsletters."""
    if not ARCHIVE_DIR.exists():
        return ""
    archives = sorted(ARCHIVE_DIR.glob("*.html"), reverse=True)
    if not archives:
        return "<em>none yet</em>"
    links = []
    for a in archives[:10]:
        name = a.stem
        links.append(f'<a href="archive/{a.name}">{name}</a>')
    return " · ".join(links)
