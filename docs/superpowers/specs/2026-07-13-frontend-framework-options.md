# Frontend framework options for an "awwwards"-quality static site

**Status:** decision doc (no code in this change) · **Issue:** #82 · **Date:** 2026-07-13

The ask: the predefined Astro + Starlight docs layout limits how good the site
can look, but the site must stay **static and deployable on GitHub Pages**. This
evaluates 5–10 ways to get a premium, custom-designed site under that
constraint, judged on migration cost from what exists today, design freedom, GH
Pages compatibility, build speed, and the i18n story.

**What we'd be migrating from/keeping.** The valuable, framework-agnostic parts
are the *data layer* (`src/lib/coffees.ts` reads `data/products.yaml` +
`roasters.yaml` at build time), the *table* (`CoffeeTable.astro`, vanilla JS),
the *i18n label maps* (`src/lib/i18n.ts`), and the *e2e suite*
(`e2e/coffee-table.spec.ts`). The pain is **Starlight's docs chrome** (sidebar,
docs typography, search) fighting a data product — the CLAUDE.md `ponytail` note
already flags this. So the real question is how much to replace, not whether
Astro is wrong (it isn't).

---

## Options

### 1. Astro, drop Starlight — custom design on the same build/data layer
Keep Astro and the data layer; replace the Starlight integration with
hand-built layouts, header/footer, and page templates. Starlight's free wins
(i18n routing, language picker, search) become small bespoke pieces.
- **Migration:** medium — reimplement i18n routing + language picker + nav;
  `CoffeeTable`/`coffees.ts`/`i18n.ts` port almost unchanged.
- **Design freedom:** high. **GH Pages:** identical (static `dist/`).
- **Build speed:** unchanged or faster (less to build). **i18n:** rebuild the
  routing we currently get free — the main cost.

### 2. Astro + Tailwind v4 + a real design system
Option 1, plus Tailwind v4 and a small token-driven design system (the brand
palette in `Design.md` becomes design tokens). Custom hero, table, and content
pages.
- **Migration:** medium (= option 1 + Tailwind adoption). **Design freedom:**
  high, and *consistent* — tokens enforce the brand. **GH Pages:** identical.
- **Build speed:** Tailwind v4 is fast. **i18n:** same as option 1.

### 3. Astro + interactive islands (React/Svelte) only where needed
Orthogonal to 1/2: keep pages static HTML, add a framework island **only** for
the genuinely interactive bits (the table's filter/sort, the #59 map). Most of
the site ships zero JS.
- **Migration:** low-to-medium — the table could stay vanilla or become one
  island. **Design freedom:** high. **GH Pages:** identical. **Build speed:**
  minimal island cost. **i18n:** same as option 1.

### 4. SvelteKit, static adapter (`adapter-static`)
Full rebuild in SvelteKit, prerendered to static.
- **Migration:** high — rebuild table, i18n, data loading, e2e. **Design
  freedom:** high. **GH Pages:** works (prerender everything; set `paths.base`).
  **Build speed:** good. **i18n:** `@inlang/paraglide` or hand-rolled — new stack.

### 5. Next.js static export (`output: 'export'`)
- **Migration:** high, and a heavier framework than the site needs. **Design
  freedom:** high. **GH Pages:** works with `output: export` + `basePath`, but
  the export path has sharp edges (no Image optimization, dynamic routes need
  `generateStaticParams`). **i18n:** App Router i18n is manual for export.
  Poor fit — most of Next's value is server-side, which we can't use.

### 6. Nuxt static (`nuxi generate`)
- **Migration:** high. **Design freedom:** high. **GH Pages:** works. **i18n:**
  `@nuxtjs/i18n` is strong. Reasonable, but a full Vue rebuild for no advantage
  over staying in Astro.

### 7. Eleventy (11ty) + hand-rolled design
Minimal, fast static generator; bring your own everything.
- **Migration:** high — lose Astro components, rebuild data pipeline in 11ty
  data files, no component islands without extra tooling. **Design freedom:**
  total. **Build speed:** excellent. **i18n:** fully manual. Great for a blog,
  a step *down* in ergonomics for a component-driven data app.

### 8. Keep Starlight, heavy theme overrides (status quo path)
Push the current MD3 theme + `custom.css` further.
- **Migration:** none. **Design freedom:** low-to-medium — always fighting
  Starlight's docs assumptions (sidebar, article layout, TOC). **The ceiling
  that prompted this issue.**

---

## Comparison at a glance

| # | Option | Migration | Design ceiling | GH Pages | i18n cost |
|---|---|---|---|---|---|
| 1 | Astro, drop Starlight | med | high | native | rebuild routing |
| 2 | Astro + Tailwind v4 + DS | med | high+ | native | rebuild routing |
| 3 | Astro + islands where needed | low–med | high | native | unchanged |
| 4 | SvelteKit static | high | high | ok | new stack |
| 5 | Next.js export | high | high | sharp edges | manual |
| 6 | Nuxt generate | high | high | ok | good |
| 7 | Eleventy | high | total | native | manual |
| 8 | Starlight overrides | none | low–med | native | free (today) |

---

## Recommendation

**Compose options 1 + 2 + 3, incrementally — do not switch frameworks.**

1. **Drop Starlight** (option 1) — reclaim the layout. This is the change that
   actually raises the ceiling; everything else is fighting the docs chrome.
2. **Adopt Tailwind v4 + brand design tokens** (option 2) for a consistent,
   premium custom design driven by `Design.md`.
3. **Keep pages static, add islands only for the table and map** (option 3) so
   the site stays fast and mostly zero-JS.

Rationale: the pain is Starlight, not Astro. Staying in Astro preserves the
data layer, the `CoffeeTable` logic, the i18n label maps, and the e2e suite —
a full framework migration (4–7) throws those away to buy design freedom we
already get by dropping one integration. The one real cost is reimplementing
the i18n URL routing and language picker Starlight gives for free; that's a
bounded, one-time task and the price of the ceiling.

**Suggested sequencing (follow-up issues):** (a) de-Starlight the layout behind
the existing pages; (b) introduce Tailwind v4 + tokens; (c) redesign hero +
content pages (dovetails with #83); (d) table/map as islands. Each step keeps
the site shippable — no big-bang rewrite.
