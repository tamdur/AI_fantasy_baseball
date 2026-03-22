---
name: Valuation Approach Decision
description: Decision to use z-score (WERTH) methodology ported from Mr. Cheatsheet, not SGP, for H2H categories valuation
type: project
---

Use z-score (WERTH) methodology, not SGP, as the core valuation approach.

**Why:** SGP requires historical roto standings data and was designed for roto leagues. Z-scores only need projections, work better for H2H categories, and are easier to adapt to non-standard categories. Mr. Cheatsheet's implementation is proven and handles all our categories.

**How to apply:** Port Mr. Cheatsheet's formula chain to Python: rate stat conversion → starter pool mean/stdev → per-category z-scores → total WERTH → position-adjusted WERTH. Layer H2H-specific intelligence (category balance, consistency, opponent tracking) on top.
