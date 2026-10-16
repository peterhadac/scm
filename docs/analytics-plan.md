# Usage statistics plan (issue #84)

**Status: the infrastructure already shipped in PR #77 (merged). Nothing is
being collected yet because the one activation step below hasn't happened.**

## 1. Activate (the only missing step, ~10 minutes)

1. Create a free account at [goatcounter.com](https://www.goatcounter.com/)
   and pick a site code — suggested: `slovakcoffeemap` (gives the dashboard
   at `https://slovakcoffeemap.goatcounter.com`).
2. In the repo: Settings → Secrets and variables → Actions → **Variables**
   (not Secrets — it's not sensitive) → New repository variable:
   `GOATCOUNTER_CODE` = `slovakcoffeemap`.
3. Re-run the Pages deploy (or wait for the next push/scrape). The build
   only emits the analytics scripts when the variable is set, so local dev
   builds and forks stay clean.

## 2. What gets measured from that moment

| Signal | Where | Why it matters |
| --- | --- | --- |
| Pageviews per page + locale | GoatCounter dashboard | Which sections earn traffic (table vs. digest vs. origins vs. map); EN vs. SK split |
| Referrers | dashboard | Where visitors come from (Google, Reddit, roaster links back) |
| Browser/screen sizes | dashboard | Whether mobile really dominates (informs table UX priorities) |
| **Outbound roaster clicks** | events named `out:<host><path>` | The "we sent you N clicks last month" number behind referral pitches (issue #57, template in `docs/referral-outreach-sk.md`) |

GoatCounter is cookie-less and doesn't profile users, so no consent banner
is needed under GDPR/ePrivacy — one reason it was chosen over GA4.

## 3. Recommended follow-ups (cheap, optional)

- **Public dashboard**: GoatCounter Settings → "Allow anyone to view this
  site's statistics". A transparency page fitting the project's open ethos;
  link it from About-the-data.
- **Monthly referral digest**: once ~3 months of `out:` events exist, pull
  the top-clicked roasters (GoatCounter has a CSV/API export) and start the
  first referral conversations (#57).
- **Goal check-ins**: the numbers that matter quarterly — weekly unique
  visitors, % SK locale, digest-page return visits, outbound CTR from the
  table. Don't build dashboards for these; read them off GoatCounter.

## 4. Known limits and the escalation path

GoatCounter won't do per-user funnels, retention cohorts, or A/B tests.
That's acceptable at this traffic scale; if it ever isn't, the migration is
one script tag swap to Plausible (~€9/mo, also cookie-less) — the site-side
integration pattern from PR #77 (env-gated head script) transfers as-is.
