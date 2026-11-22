// M0 smoke tests: the browser shows the ticking world, and its controls keep working during
// an artificial "inference wait" (plans/R1.md §7, M0 exit criteria).
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
import type { AckRecord } from '../../../aiautonomy/interfaces/net/commands';
import type { CommandType } from '../../../aiautonomy/interfaces/net/protocol';
import type { ViewState } from '../../../aiautonomy/interfaces/render/view';

const SCREENSHOT = fileURLToPath(new URL('../../../test-results/m0-running.png', import.meta.url));
/** Ack latency budget for controls (plans/R1.md §7, M0). */
const ACK_BUDGET_MS = 100;

let pageErrors: string[] = [];

test.beforeEach(({ page }) => {
  pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') pageErrors.push(message.text());
  });
});

test.afterEach(() => {
  expect(pageErrors).toEqual([]);
});

async function tick(page: Page): Promise<number> {
  return Number(await page.getByTestId('tick').getAttribute('data-tick'));
}

async function runId(page: Page): Promise<string> {
  return (await page.getByTestId('run-id').getAttribute('data-run-id')) ?? '';
}

async function view(page: Page): Promise<ViewState | null> {
  return page.evaluate(() => window.__aia?.view ?? null);
}

async function acks(page: Page, type: CommandType): Promise<AckRecord[]> {
  return page.evaluate((t) => (window.__aia?.acks ?? []).filter((a) => a.type === t), type);
}

/** Click a control and return the ack of the command it sent. */
async function clickForAck(page: Page, testId: string, type: CommandType): Promise<AckRecord> {
  const before = (await acks(page, type)).length;
  await page.getByTestId(testId).click();
  await expect.poll(async () => (await acks(page, type)).length).toBe(before + 1);
  const record = (await acks(page, type)).at(-1);
  if (record === undefined) throw new Error(`no ack for ${type}`);
  return record;
}

/** Open the app and reset to a fresh idle run at tick 0; returns its run id. */
async function freshRun(page: Page): Promise<string> {
  await page.goto('/');
  await expect(page.getByTestId('connection')).toHaveAttribute('data-connection', 'open');
  await expect(page.getByTestId('run-id')).not.toHaveAttribute('data-run-id', '');
  const previous = await runId(page);
  await page.getByTestId('btn-reset').click();
  await expect.poll(() => runId(page)).not.toBe(previous);
  await expect(page.getByTestId('run-state')).toHaveAttribute('data-state', 'idle');
  await expect(page.getByTestId('tick')).toHaveAttribute('data-tick', '0');
  return runId(page);
}

test('loads, renders the WebGL map and shows the engine snapshot @req VIS-01 @req ARCH-03', async ({
  page,
}) => {
  await page.goto('/');
  const map = page.getByTestId('map');
  await expect(map).toBeVisible();
  await expect(map).toHaveAttribute('data-webgl', 'ok');
  await expect(page.getByTestId('connection')).toHaveAttribute('data-connection', 'open');
  await expect.poll(() => page.evaluate(() => window.__aia?.moverCount ?? 0)).toBeGreaterThan(0);
  await expect.poll(() => page.evaluate(() => window.__aia?.frames ?? 0)).toBeGreaterThan(30);
  await expect(page.getByTestId('run-state')).not.toHaveAttribute('data-state', 'unknown');
  await expect(page.getByTestId('clock')).toHaveText(/^Day \d+ · \d{2}:\d{2}$/);
  await expect(page.getByTestId('engine-stamp')).toHaveText(/^engine \S+/);
  await expect(page.getByTestId('fps')).not.toHaveAttribute('data-fps', '0');
  await expect(page.locator('#panel-playback-label')).toHaveText('03 · playback');
});

test('start advances ticks, pause stops them and step advances exactly one @req VIS-04', async ({
  page,
}) => {
  await freshRun(page);
  const state = page.getByTestId('run-state');
  await page.getByTestId('btn-start').click();
  await expect(state).toHaveAttribute('data-state', 'running');
  await expect.poll(() => tick(page)).toBeGreaterThanOrEqual(2);

  await page.getByTestId('btn-pause').click();
  await expect(state).toHaveAttribute('data-state', 'paused');
  await page.waitForTimeout(500);
  const stopped = await tick(page);
  await page.waitForTimeout(1500);
  expect(await tick(page)).toBe(stopped);

  await page.getByTestId('btn-step').click();
  await expect(page.getByTestId('tick')).toHaveAttribute('data-tick', String(stopped + 1));
  await page.waitForTimeout(800);
  expect(await tick(page)).toBe(stopped + 1);
  await expect(state).toHaveAttribute('data-state', 'paused');
});

test('controls are acked in under 100 ms during an inference wait @req VIS-04 @req ARCH-03', async ({
  page,
}) => {
  await freshRun(page);
  const state = page.getByTestId('run-state');
  const waiting = page.getByTestId('waiting');
  await page.getByTestId('btn-start').click();

  // Running and blocked in an inference wait: pause and speed are acked at once.
  await expect(waiting).toBeVisible({ timeout: 15_000 });
  const pause = await clickForAck(page, 'btn-pause', 'pause');
  const speed = await clickForAck(page, 'speed-2x', 'set_speed');
  await expect(waiting).toBeVisible();
  expect(pause).toMatchObject({ ok: true });
  expect(speed).toMatchObject({ ok: true });
  expect(pause.latency_ms).toBeLessThan(ACK_BUDGET_MS);
  expect(speed.latency_ms).toBeLessThan(ACK_BUDGET_MS);
  // Both take effect: the pause at the tick boundary after the wait.
  await expect(state).toHaveAttribute('data-state', 'paused');
  await expect(page.getByTestId('speed-2x')).toHaveAttribute('aria-pressed', 'true');
  await expect(waiting).toBeHidden();

  // Paused: step until a stepped tick has to wait, then step again during that wait.
  for (let i = 0; i < 6 && !(await waiting.isVisible()); i++) {
    const before = await tick(page);
    const step = await clickForAck(page, 'btn-step', 'step');
    expect(step.latency_ms).toBeLessThan(ACK_BUDGET_MS);
    await expect
      .poll(async () => (await tick(page)) > before || (await waiting.isVisible()))
      .toBe(true);
  }
  await expect(waiting).toBeVisible();
  const stepDuringWait = await clickForAck(page, 'btn-step', 'step');
  const speedDuringWait = await clickForAck(page, 'speed-1x', 'set_speed');
  await expect(waiting).toBeVisible();
  expect(stepDuringWait.latency_ms).toBeLessThan(ACK_BUDGET_MS);
  expect(speedDuringWait).toMatchObject({ ok: true });
  expect(speedDuringWait.latency_ms).toBeLessThan(ACK_BUDGET_MS);
  await expect(waiting).toBeHidden();
});

test('reset returns to tick 0 with a new run id @req VIS-04', async ({ page }) => {
  const first = await freshRun(page);
  await page.getByTestId('btn-start').click();
  await expect.poll(() => tick(page)).toBeGreaterThanOrEqual(2);
  await page.getByTestId('btn-reset').click();
  await expect.poll(() => runId(page)).not.toBe(first);
  await expect(page.getByTestId('tick')).toHaveAttribute('data-tick', '0');
  await expect(page.getByTestId('run-state')).toHaveAttribute('data-state', 'idle');
});

test('cancel asks for confirmation and ends the run as interrupted @req VIS-04', async ({
  page,
}) => {
  await freshRun(page);
  const state = page.getByTestId('run-state');
  await page.getByTestId('btn-start').click();
  await expect(state).toHaveAttribute('data-state', 'running');
  await page.getByTestId('btn-cancel').click();
  await expect(page.getByTestId('btn-cancel-keep')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(state).toHaveAttribute('data-state', 'running');
  await page.getByTestId('btn-cancel').click();
  await page.getByTestId('btn-cancel-confirm').click();
  await expect(state).toHaveAttribute('data-state', 'interrupted');
  await expect(page.getByTestId('btn-start')).toBeDisabled();
  await expect(page.getByTestId('btn-reset')).toBeEnabled();
});

test('controls work from the keyboard with a visible focus ring @req VIS-04', async ({ page }) => {
  await freshRun(page);
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  });
  for (let i = 0; i < 12; i++) {
    const focused = await page.evaluate(() => document.activeElement?.getAttribute('data-testid'));
    if (focused === 'btn-start') break;
    await page.keyboard.press('Tab');
  }
  const start = page.getByTestId('btn-start');
  await expect(start).toBeFocused();
  expect(await start.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe('none');
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('run-state')).toHaveAttribute('data-state', 'running');
});

test('camera pans, zooms and resets with the button and the keyboard @req VIS-01', async ({
  page,
}) => {
  await page.goto('/');
  await expect.poll(() => view(page)).not.toBeNull();
  const home = await view(page);
  if (home === null) throw new Error('no view');

  await page.mouse.move(640, 400);
  await page.mouse.down();
  await page.mouse.move(760, 460, { steps: 6 });
  await page.mouse.up();
  const dragged = await view(page);
  expect(dragged?.cx).toBeLessThan(home.cx);
  expect(dragged?.cy).toBeGreaterThan(home.cy);

  await page.mouse.wheel(0, -400);
  await expect.poll(async () => (await view(page))?.height ?? 0).toBeLessThan(home.height);

  await page.getByTestId('btn-reset-view').click();
  await expect.poll(() => view(page)).toEqual(home);

  await page.getByTestId('map').focus();
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Equal'); // "=" zooms in like "+"
  await expect.poll(() => view(page)).not.toEqual(home);
  await page.keyboard.press('Home');
  await expect.poll(() => view(page)).toEqual(home);
  await page.keyboard.press('Minus');
  await expect.poll(() => view(page)).not.toEqual(home);
  await page.keyboard.press('0');
  await expect.poll(() => view(page)).toEqual(home);
});

test('clicking a mover selects it and fills the inspector @req VIS-01', async ({ page }) => {
  await freshRun(page);
  expect(await page.evaluate(() => window.__aia?.focusMover(0) ?? false)).toBe(true);
  const point = await page.evaluate(() => window.__aia?.moverScreenPosition(0) ?? null);
  if (point === null) throw new Error('no mover on screen');
  await page.mouse.click(point.x, point.y);
  const inspector = page.getByTestId('inspector');
  await expect(inspector).toBeVisible();
  const selected = await page.evaluate(() => window.__aia?.selectedId ?? '');
  expect(selected).not.toBe('');
  await expect(page.getByTestId('inspector-id')).toHaveText(selected);
  await expect(inspector.locator('dt').first()).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(inspector).toBeHidden();
});

test('sends FPS and ack-latency telemetry every 5 s @req ARCH-03', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('connection')).toHaveAttribute('data-connection', 'open');
  await expect.poll(() => acks(page, 'telemetry'), { timeout: 8_000 }).toHaveLength(1);
  expect((await acks(page, 'telemetry'))[0]).toMatchObject({ ok: true, error: null });
});

test('screenshot of the running app', async ({ page }) => {
  await freshRun(page);
  await page.getByTestId('btn-start').click();
  await expect.poll(() => tick(page)).toBeGreaterThanOrEqual(3);
  // Select a mover in the open middle of the map so the highlight and inspector show.
  const point = await page.evaluate(() => {
    const aia = window.__aia;
    for (let i = 0; aia !== undefined && i < aia.moverCount; i++) {
      const p = aia.moverScreenPosition(i);
      if (p !== null && p.x > 380 && p.x < 960 && p.y > 140 && p.y < 600) return p;
    }
    return null;
  });
  if (point !== null) {
    await page.mouse.click(point.x, point.y);
    await expect(page.getByTestId('inspector')).toBeVisible();
  }
  await page.waitForTimeout(600);
  await page.screenshot({ path: SCREENSHOT });
  await page.getByTestId('btn-pause').click();
});
