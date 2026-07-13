# Usage analytics plan

**Status:** plan (activation is a human step) · **Issue:** #84 · **Date:** 2026-07-13

## Summary

The instrumentation already exists — PR #77 wired **GoatCounter** into the
build. It's privacy-friendly, cookieless, no consent banner needed, and free
for this scale. The *only* missing step is activation: the `GOATCOUNTER_CODE`
repository variable isn't set, so `astro.config.mjs` emits no analytics script
and nothing is being collected yet.

## 1. Activation (the missing 10 minutes)

1. Create a free account at <https://www.goatcounter.com/> and pick a site code
   (e.g. `slovakcoffeemap` → `https://slovakcoffeemap.goatcounter.com`).
2. In the repo: **Settings → Secrets and variables → Actions → Variables →**
   add repository **variable** `GOATCOUNTER_CODE` = the chosen code (a
   *variable*, not a secret — it's a public site code, and `pages.yml` reads it
   as `${{ vars.GOATCOUNTER_CODE }}`).
3. Trigger a Pages rebuild (any push to `main`, or run the `pages.yml` workflow
   manually). From then on `astro.config.mjs` injects the GoatCounter script and
   data flows.

No code change is required — the gating is already conditional on the variable.

## 2. What gets measured today (once activated)

- **Pageviews** per page and per locale (EN vs `/sk/…`), so we can see whether
  the Slovak or English pages carry traffic.
- **Referrers** — where visitors arrive from (search, socials, roaster links).
- **Outbound roaster clicks** — `astro.config.mjs` fires an `out:<host><path>`
  GoatCounter event on every outbound roaster link click. These are the
  **referral-pitch numbers** for #57: concrete "we sent N clicks to your shop
  this month" figures to open partnership conversations with.

## 3. Public dashboard (optional, free)

GoatCounter can make a site's stats **public** (Settings → "Allow public
access"). Turning this on gives a transparency page we can link from the About
or footer — matches the project's open, non-creepy posture and lets roasters
verify the referral numbers themselves rather than taking our word for it.
Recommended once there's meaningful traffic.

## 4. What GoatCounter can't tell you

- **Per-user funnels / retention / cohorts** — it's aggregate pageview
  analytics, not product analytics. No "did the same visitor return and click a
  roaster three weeks later".
- **On-page interactions beyond the outbound-click event** — e.g. which filters
  people use in the table. If that becomes interesting, add more explicit
  `goatcounter.count(...)` event calls (cheap, same pattern already in
  `astro.config.mjs`).

**Escalation path:** if per-visitor funnels ever matter, Plausible (~€9/mo,
also cookieless) or PostHog (has a generous free tier, heavier) are the usual
next step. Not needed now — GoatCounter covers the current questions (traffic,
referrers, and the referral-click numbers) at zero cost.

## Recommendation

Activate GoatCounter (step 1), leave the escalation options on the shelf.
Revisit a public dashboard once traffic is non-trivial and revisit Plausible
only if a real per-user-funnel question appears.
