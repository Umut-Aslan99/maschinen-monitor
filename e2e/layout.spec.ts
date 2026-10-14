import { expect, test } from '@playwright/test';

for (const path of ['/', '/maschine/SGM-01', '/stillstaende', '/alarme']) {
  test(`no sideways scrolling on ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator('main h1')).toBeVisible();
    await page.waitForTimeout(500);
    const width = await page.evaluate(() => document.documentElement.clientWidth);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}

test('theme toggle switches and survives a reload', async ({ page }) => {
  await page.goto('/');
  const theme = () => page.evaluate(() => document.documentElement.dataset.theme ?? null);
  const settled = async () => {
    // Colours fade; wait until two readings agree.
    let last = '';
    for (;;) {
      const now = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      if (now === last) return now;
      last = now;
      await page.waitForTimeout(150);
    }
  };
  const before = await settled();
  await page.locator('.tool').click();
  const chosen = await theme();
  const after = await settled();
  expect(after).not.toBe(before);
  await page.reload();
  expect(await theme()).toBe(chosen);
  expect(await settled()).toBe(after);
});
