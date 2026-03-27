"""
Shared HTTP utilities: rate limiting and JSON file caching.
Used by all fetch_*.py modules.
"""

import json
import time
import logging
from datetime import datetime, timedelta

from config import OUTPUT_DIR

log = logging.getLogger(__name__)


# ---- Rate Limiting ----

class RateLimiter:
    """Simple per-domain rate limiter."""

    def __init__(self, min_interval):
        self.min_interval = min_interval
        self._last_request_time = 0.0

    def wait(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def mark(self):
        self._last_request_time = time.time()

    def throttle(self):
        """Call before each request: waits if needed, then marks."""
        self.wait()
        self.mark()


# ---- JSON File Caching ----

def cache_path(name):
    """Path for a named cache file in the output directory."""
    return OUTPUT_DIR / f"cache_{name}.json"


def cache_valid(name, max_hours):
    """Check if a cache file exists and is younger than max_hours."""
    p = cache_path(name)
    if not p.exists():
        return False
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    return (datetime.now() - mtime) < timedelta(hours=max_hours)


def load_cache(name):
    """Load JSON from a named cache file."""
    with open(cache_path(name)) as f:
        return json.load(f)


def save_cache(name, data):
    """Save data as JSON to a named cache file."""
    with open(cache_path(name), "w") as f:
        json.dump(data, f, default=str)
