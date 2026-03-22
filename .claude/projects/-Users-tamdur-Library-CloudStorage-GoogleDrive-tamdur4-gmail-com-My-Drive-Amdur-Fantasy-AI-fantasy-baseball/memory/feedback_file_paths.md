---
name: File Path Typo Correction
description: User corrected that existing-tools files are in the project directory, not ~/fantasy-baseball-research/
type: feedback
---

When prompts reference file paths like `~/fantasy-baseball-research/existing-tools/`, the actual files are in the project working directory under `existing-tools/`.

**Why:** User's prompt had a typo in the path.

**How to apply:** Always check the project directory first when file paths seem off. Don't search the entire filesystem without asking.
