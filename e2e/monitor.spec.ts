import { expect, test, type Page } from '@playwright/test';

interface Card { id: string; state: string | null }

test.beforeAll(async ({ request }) => {
  // The stack just started: wait until the history of the last days has been generated.
  await expect.poll(async () => (await (await request.get('/api/health')).json()).history, { timeout: 60_000 }).toBe('ready');
});

/** A machine that is producing right now – faults can only be triggered on those. */
async function runningMachine(page: Page): Promise<string | undefined> {
  const overview = (await (await page.request.get('/api/overview')).json()) as { machines: Card[] };
  // Prefer machines whose cooldown cannot be hit by a retry of this test: last ones first.
  return overview.machines.map((m) => m).reverse().find((m) => m.state === 'run')?.id;
}

test('hall shows six machines live with state, OEE and history', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('live')).toHaveText('Live');
  await expect(page.locator('.machine')).toHaveCount(6);
  await expect(page.getByTestId('hall-oee')).toHaveText(/\d+,\d %/);
  for (const card of await page.locator('.machine').all()) {
    await expect(card.getByTestId('state')).not.toContainText('Unbekannt');
    await expect(card.locator('.oee')).toContainText('%');
  }
  // History was backfilled on start: the 7-day OEE per shift has bars.
  await page.locator('.machine').first().click();
  await expect(page.getByRole('img', { name: /OEE je Schicht, (1\d|2\d) Schichten/ })).toBeVisible();
});

test('a fault triggered on a machine shows up live everywhere and can be acknowledged', async ({ page, browser }) => {
  const id = await runningMachine(page);
  test.skip(!id, 'No machine is producing right now (all on break) – nothing to trigger a fault on.');

  // A second visitor watches the hall.
  const other = await (await browser.newContext()).newPage();
  await other.goto('/');
  await expect(other.getByTestId('live')).toHaveText('Live');

  await page.goto(`/maschine/${id}`);
  await page.getByTestId('fault-reason').selectOption('HYD');
  await page.getByTestId('fault').click();
  await expect(page.getByTestId('fault-msg')).toContainText('Störung Hydraulik');
  await expect(page.getByTestId('state').first()).toContainText('Störung', { timeout: 10_000 });
  await expect(page.getByTestId('state').first()).toContainText('Störung Hydraulik');

  // The other visitor sees the state change and a toast for the critical alarm.
  await expect(other.getByTestId(`machine-${id}`).getByTestId('state')).toContainText('Störung');
  await expect(other.locator('.toast')).toContainText('Hydraulik: Druck außerhalb Toleranz');

  // Second trigger right away is refused (cooldown / not running).
  await expect(page.getByTestId('fault')).toBeDisabled();

  await page.goto('/alarme');
  const alarm = page.getByTestId('active-alarms').locator('li', { hasText: id! }).filter({ hasText: 'Hydraulik: Druck' });
  await alarm.getByRole('button', { name: 'Quittieren' }).click();
  await expect(alarm).toContainText('quittiert');
  await other.close();
});

test('an unexplained stop is classified and leaves the list', async ({ page }) => {
  await page.goto('/stillstaende');
  const list = page.getByTestId('unclassified').locator('li');
  await expect(list.first()).toBeVisible();
  const before = await list.count();
  test.skip(before === 1 && (await list.first().textContent())!.includes('Alle Stillstände'), 'nothing to classify');
  await list.first().getByTestId('classify-reason').selectOption({ label: 'Materialmangel' });
  await list.first().getByRole('button', { name: 'Zuordnen' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'als „Materialmangel“ zugeordnet' })).toBeVisible();
  await expect(list).toHaveCount(before - 1);
});

test('the problem machine: hydraulics is a top downtime reason of SGM-01', async ({ page }) => {
  await page.goto('/stillstaende');
  await page.getByTestId('pareto-machine').selectOption('SGM-01');
  const reasons = page.getByTestId('pareto').locator('.hbar > span:first-child');
  await expect(reasons.first()).toBeVisible();
  const top2 = (await reasons.allTextContents()).slice(0, 2);
  expect(top2).toContain('Störung Hydraulik');
  // Every chart has a table view with the same numbers.
  await page.getByRole('button', { name: 'Tabelle' }).click();
  await expect(page.locator('table.data tbody tr').first()).toBeVisible();
});

test('machine page: ranges, state timeline, signal charts with limits, table view', async ({ page }) => {
  await page.goto('/maschine/SGM-01');
  await expect(page.getByTestId('machine-oee')).toHaveText(/%/);
  await expect(page.getByTestId('signal-oil_temp').locator('svg path').first()).toHaveAttribute('d', /^M/);
  await expect(page.getByTestId('signal-oil_temp')).toContainText('Kritisch 60 °C');
  // Live: new samples arrive every 2 seconds.
  const label = page.getByTestId('signal-oil_temp').getByRole('img');
  const first = await label.getAttribute('aria-label');
  await expect.poll(async () => (await page.getByTestId('signal-power').locator('svg path').last().getAttribute('d'))?.length ?? 0, { timeout: 10_000 }).toBeGreaterThan(0);
  expect(first).toMatch(/Hydrauliköl: zuletzt \d+,\d °C/);

  await page.getByRole('button', { name: '24 h' }).click();
  await expect(page.getByRole('img', { name: /Zustandsverlauf mit \d{2,} Abschnitten/ })).toBeVisible();
  await page.getByTestId('signal-oil_temp').getByRole('button', { name: 'Tabelle' }).click();
  await expect(page.getByTestId('signal-oil_temp').locator('table tbody tr')).toHaveCount(60);
});

test('no request leaves the site and nothing violates the security policy', async ({ page }) => {
  const problems: string[] = [];
  page.on('console', (m) => { if (m.type() === 'error') problems.push(m.text().slice(0, 200)); });
  page.on('request', (r) => { if (!r.url().startsWith('http://localhost:8000') && !r.url().startsWith('ws://localhost:8000') && !r.url().startsWith('data:')) problems.push(r.url()); });
  for (const path of ['/', '/maschine/CNC-01', '/stillstaende', '/alarme']) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
  }
  expect(problems).toEqual([]);
  const res = await page.request.get('/');
  expect(res.headers()['content-security-policy']).toContain("script-src 'self'");
});
