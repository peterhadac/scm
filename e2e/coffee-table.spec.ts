import { test, expect, type Page } from '@playwright/test';

// Smoke tests for CoffeeTable.astro's client-side logic (issue #43) — the
// ~1,100-line component whose filtering/sorting/i18n behaviour previously
// had no check beyond "the site builds". Runs against the real built site
// (real data/products.yaml), so assertions avoid exact counts/values and
// check invariants instead.

const visibleRows = (page: Page) =>
  page.locator('#coffee-table tbody tr:not([hidden])');

async function openFilters(page: Page) {
  // The filter selects live inside a collapsed <details> panel.
  await page.locator('#filters-toggle summary').click();
}

async function gotoTable(page: Page, path: string) {
  await page.goto(path);
  // The component's <script> populates #result-count on init — clicking or
  // selecting before that runs would race the listener attachment.
  await expect(page.locator('#result-count')).not.toHaveText('');
}

test('table renders rows from products.yaml', async ({ page }) => {
  await gotoTable(page, '/scm/coffees/');
  await expect(page.locator('#coffee-table')).toBeVisible();
  expect(await visibleRows(page).count()).toBeGreaterThan(0);
});

test('origin filter narrows rows to the selected origin only', async ({ page }) => {
  await gotoTable(page, '/scm/coffees/');
  const total = await visibleRows(page).count();
  await openFilters(page);

  const originSelect = page.locator('#filter-origin');
  // Options are populated client-side from the rows' data-origin keys.
  const firstOrigin = await originSelect
    .locator('option:not([value=""])')
    .first()
    .getAttribute('value');
  expect(firstOrigin).toBeTruthy();
  await originSelect.selectOption(firstOrigin!);

  const rows = visibleRows(page);
  const filtered = await rows.count();
  expect(filtered).toBeGreaterThan(0);
  expect(filtered).toBeLessThanOrEqual(total);
  for (const origin of await rows.evaluateAll((trs) => trs.map((tr) => (tr as HTMLElement).dataset.origin))) {
    expect(origin).toBe(firstOrigin);
  }
});

test('table defaults to cheapest-first and the price header flips direction', async ({ page }) => {
  await gotoTable(page, '/scm/coffees/');
  const priceHeader = page.locator('button[data-sort="price"]');
  const prices = async () =>
    (await visibleRows(page).evaluateAll((trs) =>
      trs.map((tr) => parseFloat((tr as HTMLElement).dataset.price || '0')),
    ));

  // The component initializes with sortState {price, asc} — cheapest first.
  const initial = await prices();
  expect(initial).toEqual([...initial].sort((a, b) => a - b));

  // Clicking the already-active price header flips to descending…
  await priceHeader.click();
  const desc = await prices();
  expect(desc).toEqual([...desc].sort((a, b) => b - a));

  // …and clicking again flips back to ascending.
  await priceHeader.click();
  const asc = await prices();
  expect(asc).toEqual([...asc].sort((a, b) => a - b));
});

test('the Blends page shows only Blend rows (issue #92)', async ({ page }) => {
  await gotoTable(page, '/scm/coffees/blends/');
  const rows = visibleRows(page);
  expect(await rows.count()).toBeGreaterThan(0);
  for (const origin of await rows.evaluateAll((trs) => trs.map((tr) => (tr as HTMLElement).dataset.origin))) {
    expect(origin).toBe('Blend');
  }
});

test('the Filter and Espresso pages exclude blends (issue #92)', async ({ page }) => {
  for (const path of ['/scm/coffees/filter/', '/scm/coffees/espresso/']) {
    await gotoTable(page, path);
    const origins = await visibleRows(page).evaluateAll((trs) =>
      trs.map((tr) => (tr as HTMLElement).dataset.origin),
    );
    expect(origins.length).toBeGreaterThan(0);
    expect(origins).not.toContain('Blend');
  }
});

test('Slovak locale renders the table and filters still match on English keys', async ({ page }) => {
  await gotoTable(page, '/scm/sk/coffees/');
  await expect(page.locator('#coffee-table')).toBeVisible();
  expect(await visibleRows(page).count()).toBeGreaterThan(0);

  await openFilters(page);
  const originSelect = page.locator('#filter-origin');
  const firstOrigin = await originSelect
    .locator('option:not([value=""])')
    .first()
    .getAttribute('value');
  expect(firstOrigin).toBeTruthy();
  await originSelect.selectOption(firstOrigin!);

  const rows = visibleRows(page);
  expect(await rows.count()).toBeGreaterThan(0);
  // The option VALUE stays the canonical English key from products.yaml
  // even on /sk — switching language must never change which rows match.
  for (const origin of await rows.evaluateAll((trs) => trs.map((tr) => (tr as HTMLElement).dataset.origin))) {
    expect(origin).toBe(firstOrigin);
  }
});
