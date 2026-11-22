import { existsSync } from 'node:fs';
import { chromium, defineConfig, devices } from '@playwright/test';

// Smoke tests of the built interface against the real engine with fake inference only: an
// artificial 1.5 s "inference wait" on every 5th tick, no model and no paid API (D2).
const ENGINE_PORT = 8788;
const PREVIEW_PORT = 4173;
const SYSTEM_CHROMIUM = '/usr/bin/chromium';

/** Playwright's bundled Chromium, or Debian's `chromium` where that download is blocked. */
function chromiumExecutable(): string | undefined {
  if (existsSync(chromium.executablePath())) return undefined;
  return existsSync(SYSTEM_CHROMIUM) ? SYSTEM_CHROMIUM : undefined;
}

export default defineConfig({
  testDir: 'tests/interfaces/e2e',
  outputDir: 'test-results/e2e',
  // One engine serves every test, so tests run one at a time; each starts a fresh run.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${PREVIEW_PORT}`,
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath: chromiumExecutable(),
      // Software WebGL: the sandbox and CI have no GPU.
      args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
    },
  },
  webServer: [
    {
      command: `uv run aia serve --host 127.0.0.1 --port ${ENGINE_PORT} --artificial-inference-wait-ms 1500 --artificial-inference-wait-every 5`,
      url: `http://127.0.0.1:${ENGINE_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `npm run build && npx vite preview --port ${PREVIEW_PORT}`,
      url: `http://127.0.0.1:${PREVIEW_PORT}`,
      env: { AIA_ENGINE_PORT: String(ENGINE_PORT) },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
