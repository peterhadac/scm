# GitHub Actions CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two GitHub Actions workflows that scrape coffee data on a schedule and deploy the Astro site to GitHub Pages, per `docs/superpowers/specs/2026-06-30-ci-workflows-design.md`.

**Architecture:** Two independent workflow files. `scrape.yml` runs daily, scrapes, and pushes a data commit only when `_data/coffees.json` actually changed. `pages.yml` runs on every push to `main` (including scrape.yml's own pushes), builds the Astro site, and deploys it to GitHub Pages via the Actions-based deploy flow (not the classic branch-based one).

**Tech Stack:** GitHub Actions (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`), Python 3.12, Node 22.

## Global Constraints

- `scrape.yml`: `on: schedule: cron '0 6 * * *'` + `workflow_dispatch`. `permissions: contents: write`.
- `pages.yml`: `on: push: branches: [main]` + `workflow_dispatch`. `permissions: contents: read, pages: write, id-token: write`.
- The data-commit guard uses a scoped `git add _data/coffees.json` (not `-am`) before committing, so it can never sweep up unrelated working-tree state.
- `playwright install --with-deps chromium` runs unconditionally in `scrape.yml` (one roaster needs it; not worth conditionally parsing `roasters.yaml` in-workflow).
- `actions/setup-node@v4` pins `node-version: '22'`.
- `actions/setup-python@v5` pins `python-version: '3.12'`.
- GitHub Pages must be enabled with `build_type: workflow` before `pages.yml` can deploy — this is a controller action via `gh api`, not a file in this repo.
- `ANTHROPIC_API_KEY` repo secret is a user prerequisite, set outside this plan (never pasted into chat or committed).
- Verification is static linting via `actionlint` (v1.7.12, installed at `~/go/bin/actionlint`, on `PATH`) — no live `workflow_dispatch` trigger (real API spend + live site scraping; the user runs it themselves later).

---

### Task 1: Enable GitHub Pages and add the deploy workflow

**Files:**
- Create: `.github/workflows/pages.yml`

**Interfaces:**
- Produces: a syntactically valid workflow file that `pages.yml`'s own future runs will use — no code interface, this is infrastructure-only. Task 2 is fully independent of this task (different file, no shared state).

- [ ] **Step 1: Enable GitHub Pages with the Actions build type**

```bash
gh api repos/peterhadac/scm/pages -X POST -f build_type=workflow
```

Expected: JSON response with `"build_type": "workflow"` (or, if Pages already exists in some other state, a 409 — in that case run the PATCH form instead: `gh api repos/peterhadac/scm/pages -X PUT -f build_type=workflow` and expect the same `"build_type": "workflow"` in the response).

- [ ] **Step 2: Create the workflow file**

`.github/workflows/pages.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
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

- [ ] **Step 3: Lint the workflow with actionlint**

`actionlint` (v1.7.12, installed at `~/go/bin/actionlint`, already on `PATH`) does full GitHub Actions validation — invalid action refs/versions, bad expressions, permission mistakes, and (when `shellcheck` is present) shell-script issues in `run:` blocks. `shellcheck` is not installed on this machine, so actionlint will skip that part and note it — that's expected, not a failure.

```bash
actionlint .github/workflows/pages.yml
```

Expected output: nothing printed, exit code 0 (actionlint is silent on success — a non-empty output or non-zero exit means a real issue to fix).

- [ ] **Step 4: Confirm the local build this workflow depends on still works**

```bash
npm run build
```

Expected: exits 0, `dist/` is created (this confirms `npm ci && npm run build` — the exact commands the workflow runs — succeed on the current `package.json`/`package-lock.json`).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/pages.yml
git commit -m "feat: add pages.yml — build and deploy Astro site to GitHub Pages"
```

---

### Task 2: Add the daily scrape workflow

**Files:**
- Create: `.github/workflows/scrape.yml`

**Interfaces:**
- Consumes: `scraper/requirements.txt`, `scraper/scrape.py` (already exist, unchanged by this task).
- Produces: nothing consumed by later tasks — this is the final task in this plan.

- [ ] **Step 1: Create the workflow file**

`.github/workflows/scrape.yml`:

```yaml
name: Scrape coffee data

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

- [ ] **Step 2: Lint the workflow with actionlint**

```bash
actionlint .github/workflows/scrape.yml
```

Expected output: nothing printed, exit code 0.

- [ ] **Step 3: Confirm the commands this workflow runs actually work locally**

```bash
.venv/bin/pip install -r scraper/requirements.txt -q
.venv/bin/python -m pytest scraper/test_scrape.py -q
```

Expected: `11 passed` (this is the same dependency set and the same `scraper/scrape.py` the workflow invokes — a green local test run is the closest verification available without spending real API calls or touching live roaster sites).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/scrape.yml
git commit -m "feat: add scrape.yml — daily cron scrape with guarded data commit"
```

- [ ] **Step 5: Report the two prerequisites that remain outside this plan**

In your final report, remind the user (don't attempt to do these yourself):
1. Set the `ANTHROPIC_API_KEY` repository secret: `gh secret set ANTHROPIC_API_KEY` (or via the GitHub UI under Settings → Secrets and variables → Actions).
2. Once the secret is set, they can manually trigger `scrape.yml` via `gh workflow run scrape.yml` or the Actions tab to verify the full pipeline end-to-end for real.

---

## Self-Review

**Spec coverage:**
- `scrape.yml` schedule/permissions/steps/scoped-commit-guard → Task 2.
- `pages.yml` triggers/permissions/steps → Task 1.
- Pages-enablement prerequisite (`gh api`, `build_type: workflow`) → Task 1 Step 1.
- `ANTHROPIC_API_KEY` secret prerequisite → Task 2 Step 5 (reported, not automated, per spec).
- Static-lint-only verification, no live trigger → Task 1 Step 3, Task 2 Step 2 (both use `actionlint`, installed once ahead of Task 1).

**Placeholder scan:** No TBD/TODO; every step has exact YAML, exact commands, and exact expected output.

**Type consistency:** N/A (no shared functions/types between the two tasks — they are independent files with no code interface, as declared in each task's Interfaces block).
