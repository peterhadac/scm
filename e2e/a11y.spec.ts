import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Accessibility gate (issue #63): fail on serious/critical axe violations
// on the pages that matter most — the table (the product) in both locales.
// Minor/moderate findings are reported in CI logs but don't fail, so the
// gate stays actionable instead of noisy.

async function seriousViolations(page: import('@playwright/test').Page) {
  // The rows' staggered entry animation blends ancestor opacity into
  // axe's computed colors — scanning mid-fade reports phantom contrast
  // failures (two identical badges measured 3.02 vs 4.09 during the
  // fade). Let the animation finish before measuring steady state.
  await page.waitForTimeout(2000);
  const results = await new AxeBuilder({ page })
    // Ko-fi's injected donate widget (iframe without title, img without
    // alt, sub-4.5:1 button text) is third-party DOM we can't fix here.
    .exclude('[id^="kofi-wo-container"]')
    .analyze();
  const gate = results.violations.filter((v) =>
    ['serious', 'critical'].includes(v.impact ?? ''),
  );
  const minor = results.violations.filter((v) => !gate.includes(v));
  if (minor.length) {
    console.log(
      'axe (non-gating):',
      minor.map((v) => `${v.impact}:${v.id}(${v.nodes.length})`).join(', '),
    );
  }
  // Readable failure output: rule id, impact, and the first offending node.
  return gate.map(
    (v) => `${v.impact}:${v.id} x${v.nodes.length} e.g. ${v.nodes[0]?.target?.join(' ')}`,
  );
}

test('coffees page has no serious/critical a11y violations', async ({ page }) => {
  await page.goto('/scm/coffees/');
  await expect(page.locator('#coffee-table')).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);
});

test('Slovak coffees page has no serious/critical a11y violations', async ({ page }) => {
  await page.goto('/scm/sk/coffees/');
  await expect(page.locator('#coffee-table')).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);
});
