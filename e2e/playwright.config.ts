import { defineConfig, devices } from '@playwright/test';

// Runs inside the app container's network namespace (ops.sh), so the app is at localhost:8000.
export default defineConfig({
  testDir: '.',
  timeout: 45_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: { baseURL: process.env.BASE_URL ?? 'http://localhost:8000', trace: 'retain-on-failure', locale: 'de-DE', timezoneId: 'Europe/Berlin' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] }, testIgnore: /layout\.spec/ },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, testMatch: /layout\.spec/ },
  ],
});
