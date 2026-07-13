# Frontend framework options (issue #82)

Peter's ask: the predefined Astro Starlight layout is limiting — what are
5–10 options for an "awwwesome"-quality site that stays fully static and
deployable on GitHub Pages?

## What we'd be migrating

The parts worth money today, and what each is coupled to:

| Asset | Coupled to |
| --- | --- |
| Build-time data layer (`coffees.ts`, `priceHistory.ts`, `digest.ts`, `origins.ts`, `mapData.ts`) | Plain TS + `js-yaml` — **framework-agnostic** |
| `CoffeeTable.astro` (~1,200 lines, vanilla-JS client script) | Astro component syntax; the client `<script>` is portable |
| EN/SK i18n (URL-based routing, `i18n.ts` string tables, localStorage persistence) | Half ours (`i18n.ts`), half **Starlight** (routing, language picker, translated chrome) |
| MD3 theme + brand palette (`starlight-theme-md3`, `custom.css`) | **Starlight** plugin system |
| Content pages (drinks, brew methods, about) | MDX under Starlight's content collections |
| Endpoints (`coffees.json`, `digest.xml`) | Astro `src/pages/*.ts` — trivial anywhere |
| e2e + a11y + Lighthouse CI | URL structure only |

Key observation: **the pain is Starlight's chrome (docs sidebar, search,
header, page shell), not Astro.** The data layer and endpoints port
anywhere; the table's logic ports easily; what fights every design
ambition is the docs-site frame around it.

## The options

### 1. Astro, drop Starlight — custom layout (RECOMMENDED)
Keep Astro, delete the Starlight integration, build our own `Layout.astro`
(header, footer, language switcher) and page designs. The CLAUDE.md
ponytail note has flagged this from day one: Starlight is a docs framework
and this is a data product.
- **Design freedom:** total. **Migration:** medium — rebuild chrome,
  sidebar→real nav, replace Starlight i18n routing with Astro's built-in
  `i18n` config (supported natively), lose Pagefind search (add back via
  `pagefind` directly if wanted).
- **Keeps:** every lib, endpoint, the table script, e2e URLs.

### 2. Option 1 + Tailwind v4 + a designed system
Same as (1) plus Tailwind for velocity and a proper design language
(spacing scale, type scale, components) implementing Design.md instead of
overriding MD3 tokens. This is the "awwwesome" lever — quality comes from
design investment, not framework choice.

### 3. Option 1 + interactive islands (Svelte or React) where earned
Astro islands for genuinely stateful UI: the table (filters/sort could
become declarative instead of 400 lines of imperative DOM), the map,
future price-history charts. Everything else stays zero-JS HTML.

### 4. SvelteKit + `adapter-static`
Full rewrite. Excellent DX, tiny bundles. But: every component and page
rewritten, i18n from scratch, MDX story weaker (mdsvex), and we'd
reimplement what Astro already gives us for free (content collections,
zero-JS defaults). High cost, no unique payoff for a mostly-static site.

### 5. Next.js `output: 'export'`
Industry-standard React. Static export forfeits most of Next's actual
advantages (ISR, server components with data), React runtime ships on
every page, i18n routing under static export is notoriously awkward.
Wrong tool for a content/data site.

### 6. Nuxt static (`nuxi generate`)
Vue equivalent of (5). Same verdict: full rewrite, runtime overhead,
nothing Astro doesn't already do better statically.

### 7. Eleventy + hand-rolled everything
Maximum control, zero magic, very fast builds. But no component model or
scoped styles out of the box, TS data layer needs wiring, i18n is DIY.
More artisanal effort for less capability than (1).

### 8. Keep Starlight, override harder (status quo path)
Starlight supports component overrides (we already override SiteTitle and
Footer) and full custom CSS. Ceiling: the docs-shaped page shell always
shows through — you can repaint a sidebar, not un-be one. Lowest effort,
lowest ceiling; the frustration behind this issue is evidence the ceiling
has been hit.

### 9. Astro + a premium theme as base (e.g. AstroWind-class landing themes)
Buy/adopt a designed theme for landing + content pages, keep our
components inside it. Fast path to "looks expensive", but themes fight
custom data UIs and the MD3 brand system; usually ends in (2) anyway with
extra baggage.

## Recommendation

**Composed 1 + 2 + 3, in that order, incrementally — no rewrite.**

1. **Phase A:** new `Layout.astro` + nav + Astro-native i18n routing; pages
   move off Starlight one by one (redirects keep URLs stable, e2e suite
   guards behavior). Landing page first (pairs with issue #83).
2. **Phase B:** Tailwind v4 + a design-system pass implementing Design.md
   directly (kills the recurring "MD3 token overrides" friction).
3. **Phase C (optional, per-component):** islands where state earns it —
   table first candidate, only if Phase B's design work wants richer
   interaction than the vanilla script sustains.

Rationale: preserves 100 % of the data layer, endpoints, tests, and URLs;
spends effort on the actual bottleneck (design freedom); each phase ships
independently and is abortable. Frameworks 4–7 buy a rewrite with no
capability we lack; 8 is the ceiling we're escaping; 9 converges to 2.

**Suggested next step:** accept/adjust this direction in review, then a
Phase A implementation issue with the page-by-page migration order.
