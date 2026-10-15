import { expect, test } from '@playwright/test';

// The guided tour (site-tour.js): every step must find its element – a renamed or removed part of the UI fails here.
test('the guided tour walks through every part of the app', async ({ page }) => {
  const skipped: string[] = [];
  page.on('console', (m) => { if (m.text().includes('[site-tour]')) skipped.push(m.text()); });
  await expect.poll(async () => (await (await page.request.get('/api/health')).json()).history, { timeout: 60_000 }).toBe('ready');
  await page.goto('/?tour=start');
  const tour = page.locator('[data-site-tour="monitor"]');
  const titles: string[] = [];
  while (titles.length < 30) {
    const bubble = tour.locator('section.bubble');
    await expect(bubble).toBeVisible();
    const step = await bubble.getAttribute('data-step');
    titles.push((await tour.locator('h2').textContent()) ?? '');
    await tour.getByTestId('tour-next').click();
    if ((await tour.count()) === 0) break;
    await expect(bubble).not.toHaveAttribute('data-step', step!, { timeout: 10_000 });
  }
  expect(skipped).toEqual([]);
  expect(titles).toHaveLength(11);
  expect(titles[0]).toBe('Hallo! Kurz zum Problem');
  expect(await page.evaluate(() => localStorage.getItem('site-tour:monitor'))).toBe('done');
  await expect(page.getByTestId('tour-launcher')).toBeVisible();
});
