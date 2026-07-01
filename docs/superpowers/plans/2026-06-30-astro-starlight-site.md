# Astro + Starlight Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Astro + Starlight site that renders `_data/coffees.json` as a filterable, sortable table, per `docs/superpowers/specs/2026-06-30-astro-starlight-site-design.md`.

**Architecture:** A Starlight (Astro docs theme) site with the `starlight-theme-md3` plugin already installed. Hand-authored project files (no `create-astro` scaffold — more deterministic for this plan than relying on an interactive CLI's current flag set). Splash homepage at `/`, the actual coffee table at `/coffees/`. Data is a plain build-time `import` of `_data/coffees.json` in production, swapped for `_data/coffees.sample.json` in dev via Vite's `import.meta.env.DEV`.

**Tech Stack:** Astro (latest), `@astrojs/starlight` (latest), `starlight-theme-md3` (already installed, `^0.2.0`), vanilla JS (no client framework).

> **Post-implementation note (2026-06-30):** the theme seed below (`#6f4e37`) reflects what was planned, not what shipped — the project owner rebranded to `#FF6037` ("Toxic Orange") plus a full named palette during implementation. See `docs/superpowers/specs/2026-06-30-astro-starlight-site-design.md` and `CLAUDE.md` for the current value. Left as-is here as a historical record of the original plan.

## Global Constraints

- Full Starlight docs template — sidebar nav and search stay enabled (not a stripped single-page app).
- Splash homepage (`template: splash`) at `/`; the coffee table lives at `/coffees/`, not at the root.
- `_data/coffees.json` is the real (untouched) scraper-output path; `_data/coffees.sample.json` is dev-only sample data. Selected via `import.meta.env.DEV` — no new env var.
- No client framework. Filtering/sorting is vanilla JS inside a `<script>` tag in `CoffeeTable.astro`.
- The `last_seen` field is not a visible table column.
- `astro.config.mjs`: `site: 'https://peterhadac.github.io'`, `base: '/scm'` (matches the `origin` remote `github.com/peterhadac/scm.git`).
- Theme plugin: `starlight-theme-md3` with `seed: '#6f4e37'`, `variant: 'tonalSpot'` (already decided in `CLAUDE.md`).
- Internal links (sidebar `link`, hero `actions[].link`) are written **without** the `/scm` base prefix — Starlight prepends `base` automatically.

> **Post-implementation correction (2026-07-01):** the line above was wrong for hero action links specifically — only sidebar `link` config auto-prepends `base`; `index.mdx`'s `hero.actions[].link` does not, and needed the `/scm` prefix hardcoded (`link: /scm/coffees/`) to avoid a 404 on the live site. See the spec's matching correction note.

---

### Task 1: Astro + Starlight scaffold with a working splash homepage

**Files:**
- Modify: `package.json`
- Create: `astro.config.mjs`
- Create: `tsconfig.json`
- Create: `src/content.config.ts`
- Create: `src/content/docs/index.mdx`

**Interfaces:**
- Produces: a working `npm run dev` server serving the Starlight splash page at `http://localhost:4321/scm/`. Later tasks add the sidebar entry and `/coffees/` route on top of this `astro.config.mjs` and content collection.

- [ ] **Step 1: Install Astro and Starlight**

```bash
npm install astro @astrojs/starlight
```

Expected: `package.json` now lists `astro` and `@astrojs/starlight` under `dependencies` alongside the existing `starlight-theme-md3`.

- [ ] **Step 2: Add npm scripts**

Edit `package.json` to add a `"scripts"` block (keep the existing `"dependencies"` block as-is):

```json
{
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview"
  },
  "dependencies": {
    "astro": "^5.0.0",
    "@astrojs/starlight": "^0.32.0",
    "starlight-theme-md3": "^0.2.0"
  }
}
```

(Use whatever exact versions `npm install` actually wrote in Step 1 — don't downgrade or change them, just confirm the `scripts` block is present.)

- [ ] **Step 3: Create `tsconfig.json`**

```json
{
  "extends": "astro/tsconfigs/strict"
}
```

- [ ] **Step 4: Create `astro.config.mjs`**

```js
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import md3Theme from 'starlight-theme-md3';

export default defineConfig({
  site: 'https://peterhadac.github.io',
  base: '/scm',
  integrations: [
    starlight({
      title: 'Slovak Coffee Map',
      plugins: [md3Theme({ seed: '#6f4e37', variant: 'tonalSpot' })],
    }),
  ],
});
```

- [ ] **Step 5: Create the content collection config**

`src/content.config.ts`:

```ts
import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({ loader: docsLoader(), schema: docsSchema() }),
};
```

- [ ] **Step 6: Create the splash homepage**

`src/content/docs/index.mdx`:

```mdx
---
title: Slovak Coffee Map
description: Daily-updated catalogue of coffees available on the Slovak market.
template: splash
hero:
  tagline: Every coffee currently in stock from Slovak roasters, in one filterable table.
  actions:
    - text: Browse coffees
      link: /coffees/
      icon: right-arrow
      variant: primary
---
```

- [ ] **Step 7: Verify the dev server serves the homepage**

```bash
npm run dev &
DEV_PID=$!
sleep 3
curl -s http://localhost:4321/scm/ | grep -q "Slovak Coffee Map" && echo "PASS" || echo "FAIL"
kill $DEV_PID
```

Expected output: `PASS`

- [ ] **Step 8: Commit**

```bash
git add package.json package-lock.json astro.config.mjs tsconfig.json src/content.config.ts src/content/docs/index.mdx
git commit -m "feat: scaffold Astro + Starlight with splash homepage"
```

---

### Task 2: Coffee data + static table on `/coffees/`

**Files:**
- Create: `_data/coffees.sample.json`
- Create: `src/components/CoffeeTable.astro`
- Create: `src/content/docs/coffees.mdx`
- Modify: `astro.config.mjs` (add sidebar entry)

**Interfaces:**
- Consumes: `astro.config.mjs` from Task 1 (extends the existing `starlight({...})` config object).
- Produces: `CoffeeTable.astro` renders a `<table id="coffee-table">` with one `<tbody><tr data-roaster=".." data-origin=".." data-process=".." data-price="..">` per coffee — Task 3's filter/sort script depends on exactly these element ids and `data-*` attribute names.

- [ ] **Step 1: Write the sample data**

`_data/coffees.sample.json` — 9 rows spanning all 5 roasters, including some `null` origin/process/weight_g to exercise the table's fallback rendering:

```json
[
  {
    "name": "Etiópia Yirgacheffe",
    "roaster": "Kavoholik",
    "origin": "Etiópia",
    "process": "Umytá",
    "price": 12.90,
    "weight_g": 250,
    "url": "https://kavoholik.sk/coffee/etiopia-yirgacheffe",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Kolumbia Huila",
    "roaster": "Ready After",
    "origin": "Kolumbia",
    "process": null,
    "price": 14.50,
    "weight_g": 250,
    "url": "https://www.readyafter.sk/produkty/kolumbia-huila",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Brazília Cerrado",
    "roaster": "Kaffa Roastery",
    "origin": "Brazília",
    "process": "Prírodná",
    "price": 11.00,
    "weight_g": null,
    "url": "https://kaffaroastery.sk/coffees/brazilia-cerrado",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Kenya AA",
    "roaster": "Suca Roastery",
    "origin": "Keňa",
    "process": "Umytá",
    "price": 16.20,
    "weight_g": 250,
    "url": "https://www.sucaroastery.sk/coffee/kenya-aa",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Guatemala Huehuetenango",
    "roaster": "Coffeein",
    "origin": "Guatemala",
    "process": "Umytá",
    "price": 15.90,
    "weight_g": 250,
    "url": "https://www.coffeein.sk/coffee/guatemala-huehuetenango",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Honduras Marcala",
    "roaster": "Kavoholik",
    "origin": null,
    "process": null,
    "price": 13.40,
    "weight_g": 250,
    "url": "https://kavoholik.sk/coffee/honduras-marcala",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Ethiopia Natural",
    "roaster": "Ready After",
    "origin": "Etiópia",
    "process": "Prírodná",
    "price": 15.00,
    "weight_g": 250,
    "url": "https://www.readyafter.sk/produkty/ethiopia-natural",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Rwanda Washed",
    "roaster": "Kaffa Roastery",
    "origin": "Rwanda",
    "process": "Umytá",
    "price": 17.50,
    "weight_g": 250,
    "url": "https://kaffaroastery.sk/coffees/rwanda-washed",
    "last_seen": "2026-06-30"
  },
  {
    "name": "Peru Organic",
    "roaster": "Suca Roastery",
    "origin": "Peru",
    "process": "Umytá",
    "price": 13.90,
    "weight_g": 1000,
    "url": "https://www.sucaroastery.sk/coffee/peru-organic",
    "last_seen": "2026-06-30"
  }
]
```

- [ ] **Step 2: Write the static table component**

`src/components/CoffeeTable.astro`:

```astro
---
import sampleCoffees from '../../_data/coffees.sample.json';
import prodCoffees from '../../_data/coffees.json';

const coffees = import.meta.env.DEV ? sampleCoffees : prodCoffees;
---
<table id="coffee-table">
  <thead>
    <tr>
      <th>Coffee</th>
      <th>Roaster</th>
      <th>Origin</th>
      <th>Process</th>
      <th>Price</th>
      <th>Weight</th>
    </tr>
  </thead>
  <tbody>
    {coffees.map((c) => (
      <tr
        data-roaster={c.roaster}
        data-origin={c.origin ?? ''}
        data-process={c.process ?? ''}
        data-price={c.price}
      >
        <td><a href={c.url} target="_blank" rel="noopener noreferrer">{c.name}</a></td>
        <td>{c.roaster}</td>
        <td>{c.origin ?? '—'}</td>
        <td>{c.process ?? '—'}</td>
        <td>€{c.price.toFixed(2)}</td>
        <td>{c.weight_g ? `${c.weight_g}g` : '—'}</td>
      </tr>
    ))}
  </tbody>
</table>
```

- [ ] **Step 3: Write the coffees page**

`src/content/docs/coffees.mdx`:

```mdx
---
title: Coffees
description: Browse and filter every coffee currently in stock from Slovak roasters.
---

import CoffeeTable from '../../components/CoffeeTable.astro';

<CoffeeTable />
```

- [ ] **Step 4: Add the sidebar entry**

In `astro.config.mjs`, add `sidebar` to the existing `starlight({...})` call:

```js
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import md3Theme from 'starlight-theme-md3';

export default defineConfig({
  site: 'https://peterhadac.github.io',
  base: '/scm',
  integrations: [
    starlight({
      title: 'Slovak Coffee Map',
      plugins: [md3Theme({ seed: '#6f4e37', variant: 'tonalSpot' })],
      sidebar: [{ label: 'Coffees', link: '/coffees/' }],
    }),
  ],
});
```

- [ ] **Step 5: Verify the table renders sample data**

```bash
npm run dev &
DEV_PID=$!
sleep 3
curl -s http://localhost:4321/scm/coffees/ | grep -q "Etiópia Yirgacheffe" && echo "PASS" || echo "FAIL"
curl -s http://localhost:4321/scm/coffees/ | grep -q 'data-roaster="Kavoholik"' && echo "PASS" || echo "FAIL"
kill $DEV_PID
```

Expected output: `PASS` (twice)

- [ ] **Step 6: Commit**

```bash
git add _data/coffees.sample.json src/components/CoffeeTable.astro src/content/docs/coffees.mdx astro.config.mjs
git commit -m "feat: add coffees page with static table from sample data"
```

---

### Task 3: Filter dropdowns and price sort (vanilla JS)

**Files:**
- Modify: `src/components/CoffeeTable.astro`

**Interfaces:**
- Consumes: `<tr data-roaster data-origin data-process data-price>` rows and `<table id="coffee-table">` from Task 2 — read directly via `document.querySelector`, no data passed in separately.

- [ ] **Step 1: Add filter/sort controls and the script**

Replace the contents of `src/components/CoffeeTable.astro` with:

```astro
---
import sampleCoffees from '../../_data/coffees.sample.json';
import prodCoffees from '../../_data/coffees.json';

const coffees = import.meta.env.DEV ? sampleCoffees : prodCoffees;
---
<div class="filters">
  <label>
    Roaster
    <select id="filter-roaster"><option value="">All</option></select>
  </label>
  <label>
    Origin
    <select id="filter-origin"><option value="">All</option></select>
  </label>
  <label>
    Process
    <select id="filter-process"><option value="">All</option></select>
  </label>
  <button id="sort-price" type="button" data-dir="asc">Sort by price ▲</button>
</div>
<p id="empty-state" hidden>No coffees match the selected filters.</p>
<table id="coffee-table">
  <thead>
    <tr>
      <th>Coffee</th>
      <th>Roaster</th>
      <th>Origin</th>
      <th>Process</th>
      <th>Price</th>
      <th>Weight</th>
    </tr>
  </thead>
  <tbody>
    {coffees.map((c) => (
      <tr
        data-roaster={c.roaster}
        data-origin={c.origin ?? ''}
        data-process={c.process ?? ''}
        data-price={c.price}
      >
        <td><a href={c.url} target="_blank" rel="noopener noreferrer">{c.name}</a></td>
        <td>{c.roaster}</td>
        <td>{c.origin ?? '—'}</td>
        <td>{c.process ?? '—'}</td>
        <td>€{c.price.toFixed(2)}</td>
        <td>{c.weight_g ? `${c.weight_g}g` : '—'}</td>
      </tr>
    ))}
  </tbody>
</table>

<script>
  const table = document.getElementById('coffee-table')!;
  const tbody = table.querySelector('tbody')!;
  const rows = Array.from(tbody.querySelectorAll<HTMLTableRowElement>('tr'));
  const emptyState = document.getElementById('empty-state')!;

  function populateSelect(id: string, attr: 'roaster' | 'origin' | 'process') {
    const select = document.getElementById(id) as HTMLSelectElement;
    const values = [...new Set(rows.map((r) => r.dataset[attr]).filter(Boolean))].sort();
    for (const value of values) {
      const option = document.createElement('option');
      option.value = value as string;
      option.textContent = value as string;
      select.appendChild(option);
    }
  }
  populateSelect('filter-roaster', 'roaster');
  populateSelect('filter-origin', 'origin');
  populateSelect('filter-process', 'process');

  const roasterSelect = document.getElementById('filter-roaster') as HTMLSelectElement;
  const originSelect = document.getElementById('filter-origin') as HTMLSelectElement;
  const processSelect = document.getElementById('filter-process') as HTMLSelectElement;
  const sortButton = document.getElementById('sort-price') as HTMLButtonElement;

  function applyFilters() {
    const roaster = roasterSelect.value;
    const origin = originSelect.value;
    const process = processSelect.value;
    let visibleCount = 0;
    for (const row of rows) {
      const matches =
        (!roaster || row.dataset.roaster === roaster) &&
        (!origin || row.dataset.origin === origin) &&
        (!process || row.dataset.process === process);
      row.hidden = !matches;
      if (matches) visibleCount++;
    }
    emptyState.hidden = visibleCount !== 0;
  }

  function applySort() {
    const dir = sortButton.dataset.dir;
    const sorted = [...rows].sort((a, b) => {
      const diff = parseFloat(a.dataset.price!) - parseFloat(b.dataset.price!);
      return dir === 'asc' ? diff : -diff;
    });
    for (const row of sorted) tbody.appendChild(row);
  }

  roasterSelect.addEventListener('change', applyFilters);
  originSelect.addEventListener('change', applyFilters);
  processSelect.addEventListener('change', applyFilters);
  sortButton.addEventListener('click', () => {
    sortButton.dataset.dir = sortButton.dataset.dir === 'asc' ? 'desc' : 'asc';
    sortButton.textContent = sortButton.dataset.dir === 'asc' ? 'Sort by price ▲' : 'Sort by price ▼';
    applySort();
  });

  applyFilters();
</script>
```

- [ ] **Step 2: Structural smoke check**

```bash
npm run dev &
DEV_PID=$!
sleep 3
curl -s http://localhost:4321/scm/coffees/ | grep -q 'id="filter-roaster"' && echo "PASS" || echo "FAIL"
curl -s http://localhost:4321/scm/coffees/ | grep -q 'id="sort-price"' && echo "PASS" || echo "FAIL"
kill $DEV_PID
```

Expected output: `PASS` (twice)

- [ ] **Step 3: Manual browser verification**

This sub-project's chosen test strategy (per the design spec) is manual browser verification — filtering/sorting is client-side DOM behavior a curl smoke check can't exercise. Use the `run` or `verify` skill (or open `http://localhost:4321/scm/coffees/` directly) and confirm all six:

1. Table renders all 9 sample rows on load.
2. The Roaster dropdown, used alone, filters to only that roaster's rows.
3. The Origin dropdown, used alone, filters to only that origin's rows.
4. The Process dropdown, used alone, filters to only that process's rows.
5. Clicking "Sort by price" reorders rows ascending, then descending on a second click.
6. Selecting a Roaster *and* a Process that don't co-occur in the sample data (e.g. "Kavoholik" + "Prírodná") shows the empty state message and no rows.

- [ ] **Step 4: Commit**

```bash
git add src/components/CoffeeTable.astro
git commit -m "feat: add filter dropdowns and price sort to coffee table"
```

---

## Self-Review

**Spec coverage:**
- Full Starlight docs template, sidebar+search → Task 1 (no example-page deletion needed; nothing was scaffolded to delete since the project is hand-authored, not CLI-scaffolded).
- Splash homepage + `/coffees/` → Task 1 Step 6 (homepage), Task 2 Step 3 (coffees page).
- Dev-only sample data via `import.meta.env.DEV` → Task 2 Step 2.
- Table columns (name/roaster/origin/process/price/weight, no `last_seen`) → Task 2 Step 2.
- Dynamic dropdowns, composable filters, sort toggle, empty state → Task 3 Step 1.
- Manual browser verification per the spec's 6 points → Task 3 Step 3 (same 6 points, verbatim).

**Placeholder scan:** No TBD/TODO markers; every step has complete, runnable code or an exact command with expected output.

**Type consistency:** `CoffeeTable.astro`'s element ids (`coffee-table`, `filter-roaster`, `filter-origin`, `filter-process`, `sort-price`, `empty-state`) and `data-*` attribute names (`data-roaster`, `data-origin`, `data-process`, `data-price`) are identical between Task 2's static version and Task 3's interactive replacement — Task 3 fully replaces the file rather than patching it, so there's no drift between the two versions to reconcile.
