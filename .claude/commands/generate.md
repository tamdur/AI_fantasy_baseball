Run the full daily newsletter pipeline and publish to GitHub Pages.

Steps:
1. Run the newsletter pipeline: `python3 in_season/daily_digest/run_newsletter.py`
2. If the pipeline succeeds, stage the docs/ changes: `git add docs/`
3. Commit with message: `Newsletter YYYY-MM-DD`
4. Push to origin/main
5. Report the GitHub Pages URL: https://tamdur.github.io/AI_fantasy_baseball/

If the pipeline fails, show the error from the pipeline log at `in_season/daily_digest/output/pipeline.log` and do NOT commit or push.
