# Design audit follow-ups

Source: the 20-item shadcn/Tailwind design audit run against this repo. This
PR ships the items that were safe to verify end-to-end (`pnpm build` passes,
102/102 pages) in one pass. The rest are listed here so they aren't silently
dropped.

## Shipped in this PR

- Tailwind CSS (v4), scoped to `src/components/ui/*` only — Preflight is
  intentionally not loaded, since it would reset typography/spacing globally
  across the still-Starlight-rendered docs pages. Theme re-pointed at the six
  Design.md hex values, not shadcn's default zinc/slate palette.
- `src/components/ui/Button.astro` and `Badge.astro` (shadcn-shaped API,
  `class-variance-authority` variants), replacing:
  - the hero's `.action.primary` / `.action.secondary` pill buttons
    (`index.astro`, `sk/index.astro`)
  - the four `.ct-badge--washed/--honey/--natural/--other` CSS blocks in
    `CoffeeTable.astro`
- Deduped the `.hero-image` drop-shadow filter (was declared identically in
  both `custom.css`'s global `.hero-image svg` rule and each hero page's
  scoped `<style>`).
- Escape-to-close on the coffee table's filters popover, with focus returned
  to the trigger.
- `aria-live="polite"` on the theme-toggle's label span, so a screen reader
  announces Auto/Light/Dark changes instead of only re-reading on demand.
- Swapped `@fontsource-variable/dm-sans` (full variable weight axis) for
  `@fontsource/dm-sans`'s static 300/400/500 weights, matching Design.md's
  own typography table exactly.

## Not in this PR — needs its own reviewed pass

- **Retire the ~150 `--md-sys-color-*` tokens and 111 `!important`
  overrides** in `custom.css`. This is the biggest item and the riskiest:
  it's load-bearing for every still-Starlight-rendered page, not just the
  migrated ones, and needs to happen alongside (not before) finishing the
  Starlight-to-Layout.astro migration tracked in issue #121.
- **Popover/Select/Command for the filters panel and dropdowns** (would
  need a React or Preact integration added to Astro for Radix — a bigger
  addition than this PR's zero-new-framework scope).
- **Card, `Button`-ify the remaining CTAs, Input** — same shape as the
  Button/Badge swap here, deliberately left for a follow-up PR so this one
  stays reviewable.
- **Lint rule banning raw hex outside the Tailwind theme file** (67 current
  occurrences) — worth a `stylelint` rule once the token migration above is
  done, not before.
- **`@axe-core/playwright` against every filter/sort state in CI**, not just
  default render.
- **Documented scaling threshold** for the coffee table's O(rows) filtering
  before roaster count grows much past ~30.
- **Stale-price flag on touch** — the `title`-tooltip explanation needs a
  tap-visible alternative (e.g. an inline caption), a UX call worth its own
  review rather than bundling into a CSS-stack PR.
- **One more voice moment** (empty-state / weekly digest copy) — a content
  change, not a code change.
