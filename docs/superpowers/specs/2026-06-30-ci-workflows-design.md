# GitHub Actions CI — Design

## Context

Slovak Coffee Map's third and final sub-project: the GitHub Actions workflows that wire the already-built scraper and site together and actually publish the result. The scraper (`scraper/scrape.py`) and the Astro/Starlight site are both complete and committed; neither runs on a schedule or gets deployed without this glue. Most of this design was already locked in during earlier sessions and lives in `CLAUDE.md`'s "GitHub Actions" section — this spec captures the remaining decisions and a couple of implementation-precision refinements.

## Decisions

- **GitHub Pages enablement**: the controller (not a workflow file) enables Pages via `gh api repos/peterhadac/scm/pages` with `build_type: workflow` — GitHub Pages isn't enabled on the repo yet, and Actions-deployed Pages requires this build type rather than the classic branch-based source.
- **`ANTHROPIC_API_KEY` secret**: the user sets this themselves via `gh secret set` or the GitHub UI — never pasted into chat.
- **Commit guard precision**: use a scoped `git add _data/coffees.json` before the guarded commit, not CLAUDE.md's `git commit -am` — same intent (commit only the data file), but can't accidentally sweep up unrelated working-tree state in the runner.
- **`playwright install --with-deps chromium` is unconditional** in `scrape.yml` — one roaster (`Coffeein`) requires it, and parsing `roasters.yaml` in-workflow to conditionally skip a ~10-20s idempotent install isn't worth the complexity.
- **Node version**: `actions/setup-node@v4` pinned to Node 22, matching local dev (`node --version` → v22.22.0).
- **Verification**: YAML syntax/structure validation only (via `actionlint` if available). No live `workflow_dispatch` trigger — that costs real Claude API spend and hits live roaster sites, and requires the secret to be set first. The user triggers it themselves once ready.

> **Post-implementation update (2026-06-30):** the final whole-branch review caught a real gap this design missed — `scrape.yml`'s push uses the default `GITHUB_TOKEN` (via plain `actions/checkout`), and GitHub does not trigger other workflows' `on: push` for `GITHUB_TOKEN`-authenticated pushes (this prevents recursive runs). So the original `pages.yml` design below never actually fired after a scrape-driven data commit. Fixed by adding a `workflow_run` trigger to `pages.yml` that listens for `scrape.yml`'s completion, guarded to only build when that run succeeded — see the corrected `pages.yml` section below and `CLAUDE.md`. Ordinary human pushes to `main` were never affected by this gap (they use real user credentials).

## Architecture

```
.github/workflows/
  scrape.yml   ← daily cron (06:00 UTC) + workflow_dispatch; scrapes, commits, pushes
  pages.yml    ← on push to main + workflow_dispatch; builds Astro, deploys to Pages
```

### `scrape.yml`

```yaml
on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r scraper/requirements.txt
      - run: playwright install --with-deps chromium
      - run: python scraper/scrape.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git diff --quiet -- _data/coffees.json || (git add _data/coffees.json && git commit -m "data: $(date -u +%F)" && git push)
```

### `pages.yml`

```yaml
on:
  push:
    branches: [main]
  # GITHUB_TOKEN-authenticated pushes (like scrape.yml's data commits) don't
  # trigger on:push workflows — this workflow_run trigger closes that gap.
  workflow_run:
    workflows: ["Scrape coffee data"]   # must match scrape.yml's `name:`
    types: [completed]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    if: github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist/
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/deploy-pages@v4
        id: deployment
```

`pages.yml` fires on ordinary pushes to `main` (site/doc commits) and, separately, on `scrape.yml`'s completion (since that workflow's own push can't trigger `on: push`) — so any change that should appear on the live site triggers a rebuild either way. The `build` job's `if:` skips a rebuild when the referenced scrape run failed or was cancelled.

## Prerequisites (not automated by this sub-project)

1. Controller enables GitHub Pages with `build_type: workflow` via `gh api`.
2. User sets the `ANTHROPIC_API_KEY` repository secret themselves.

## Testing / Verification

- YAML syntax/structure validated (via `actionlint` if available on the system, else manual line-by-line check against this spec).
- No live trigger of either workflow as part of this sub-project — the user runs `workflow_dispatch` manually once the secret is set, at a time of their choosing (real API spend + live site scraping).
