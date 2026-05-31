"""In-season advisor package.

The judgment + execution layer for the fantasy-baseball in-season system. Reuses
the ``daily_digest`` data/fetch backend and the shared ``model/league`` constants.
See ``research.md`` / ``plan.md`` / ``kb.md`` in this directory for the design.

Import shim: the ``daily_digest`` backend uses bare imports (``from config import
...``, ``import fetch_espn``). Importing this package puts ``daily_digest`` on
``sys.path`` so those resolve when advisor modules import the backend. ``daily_digest``
in turn shims ``model/`` onto the path, so ``from league import ...`` works too.
"""

import sys as _sys
from pathlib import Path as _Path

_DAILY_DIGEST = _Path(__file__).resolve().parent.parent / "daily_digest"
if str(_DAILY_DIGEST) not in _sys.path:
    _sys.path.insert(0, str(_DAILY_DIGEST))
