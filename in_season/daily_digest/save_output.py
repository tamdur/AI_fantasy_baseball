"""
Save the newsletter to a text file (user preference: no email, just file output).
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR

log = logging.getLogger(__name__)


def save_newsletter(newsletter_text: str, briefing_book: dict):
    """
    Save newsletter and briefing book to output directory.
    Returns path to the newsletter file.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # Save newsletter as readable txt
    newsletter_path = OUTPUT_DIR / f"newsletter_{today}.txt"
    opponent = briefing_book.get("opponent", "Unknown")
    week = briefing_book.get("matchup_week", "?")

    header = (
        f"⚾ Daily Briefing — Week {week} vs {opponent} — {today}\n"
        f"{'=' * 60}\n\n"
    )

    newsletter_path.write_text(header + newsletter_text, encoding="utf-8")
    log.info(f"Newsletter saved: {newsletter_path}")

    # Save briefing book JSON for debugging
    briefing_path = OUTPUT_DIR / f"briefing_book_{today}.json"
    with open(briefing_path, "w") as f:
        json.dump(briefing_book, f, indent=2, default=str)
    log.info(f"Briefing book saved: {briefing_path}")

    return newsletter_path
