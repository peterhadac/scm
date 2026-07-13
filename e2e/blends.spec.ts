import { test, expect, type Page } from '@playwright/test';

// Blends category split (issue #92): blends MOVE to /coffees/blends/ —
// they must all be there, and none may remain on the single-origin
// filter/espresso pages. "All" deliberately keeps them (it stays literal).

const rowOrigins = (page: Page) =>
  page
    .locator('#coffee-table tbody tr:not([hidden])')
    .evaluateAll((trs) => trs.map((tr) => (tr as HTMLElement).dataset.origin));

test('blends page shows only Blend rows', async ({ page }) => {
  await page.goto('/scm/coffees/blends/');
  await expect(page.locator('#coffee-table')).toBeVisible();
  const origins = await rowOrigins(page);
  expect(origins.length).toBeGreaterThan(0);
  expect(origins.every((o) => o === 'Blend')).toBe(true);
});

test('filter and espresso pages contain no blends', async ({ page }) => {
  for (const path of ['/scm/coffees/filter/', '/scm/coffees/espresso/']) {
    await page.goto(path);
    await expect(page.locator('#coffee-table')).toBeVisible();
    const origins = await rowOrigins(page);
    expect(origins.length).toBeGreaterThan(0);
    expect(origins.includes('Blend')).toBe(false);
  }
});

test('All page still includes blends and Slovak blends mirror renders', async ({ page }) => {
  await page.goto('/scm/coffees/');
  await expect(page.locator('#coffee-table')).toBeVisible();
  expect((await rowOrigins(page)).includes('Blend')).toBe(true);

  await page.goto('/scm/sk/coffees/blends/');
  await expect(page.locator('#coffee-table')).toBeVisible();
  const skOrigins = await rowOrigins(page);
  expect(skOrigins.length).toBeGreaterThan(0);
  expect(skOrigins.every((o) => o === 'Blend')).toBe(true);
});
