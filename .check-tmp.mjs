import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
await page.goto('http://localhost:4322/coffees/', { waitUntil: 'networkidle' });

const vars = await page.evaluate(() => {
  const cs = getComputedStyle(document.documentElement);
  const keys = ['--md-sys-color-background','--md-sys-color-primary','--md-sys-color-secondary','--md-sys-color-tertiary','--md-sys-color-surface-variant','--font-serif','--font-mono'];
  const out = {};
  for (const k of keys) out[k] = cs.getPropertyValue(k).trim();
  out['html-data-theme'] = document.documentElement.getAttribute('data-theme');
  return out;
});
console.log(JSON.stringify(vars, null, 2));

await page.screenshot({ path: '/tmp/claude-1000/-home-phadac-git-scm/0391478d-e280-4877-a650-b116bbda6267/scratchpad/coffees-light.png', fullPage: false });

// Force dark and re-check
await page.emulateMedia({ colorScheme: 'dark' });
await page.reload({ waitUntil: 'networkidle' });
const varsDark = await page.evaluate(() => {
  const cs = getComputedStyle(document.documentElement);
  return {
    bg: cs.getPropertyValue('--md-sys-color-background').trim(),
    secondary: cs.getPropertyValue('--md-sys-color-secondary').trim(),
    theme: document.documentElement.getAttribute('data-theme'),
  };
});
console.log('DARK', JSON.stringify(varsDark, null, 2));
await page.screenshot({ path: '/tmp/claude-1000/-home-phadac-git-scm/0391478d-e280-4877-a650-b116bbda6267/scratchpad/coffees-dark.png', fullPage: false });

await browser.close();
