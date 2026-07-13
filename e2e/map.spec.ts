import { test, expect } from '@playwright/test';

// Smoke test for the roaster map (issue #59): Leaflet initializes, city
// markers render, and the SK mirror works. Marker count mirrors the number
// of distinct cities in roasters.yaml metadata — asserted as "some", not an
// exact number, so adding a roaster doesn't break the suite.

test('roaster map renders city markers', async ({ page }) => {
  await page.goto('/scm/map/');
  await expect(page.locator('#roaster-map .leaflet-container, .leaflet-container')).toBeVisible();
  const markers = page.locator('.leaflet-interactive');
  expect(await markers.count()).toBeGreaterThan(0);

  // Popup opens and contains a roaster link.
  await markers.first().click();
  await expect(page.locator('.leaflet-popup')).toBeVisible();
  expect(await page.locator('.leaflet-popup a').count()).toBeGreaterThan(0);
});

test('Slovak map mirror renders', async ({ page }) => {
  await page.goto('/scm/sk/map/');
  await expect(page.locator('.leaflet-container')).toBeVisible();
});
