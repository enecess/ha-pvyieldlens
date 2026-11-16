import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import { setImmediate } from 'node:timers';
import ForecastPage from '../../pvyieldlens/frontend/src/pages/ForecastPage.vue';
import type { ForecastSummary, ForecastView } from '../../pvyieldlens/frontend/src/models';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';
import fixture from './forecast-payload.json';

// Generated verbatim from tests/test_forecast_browser.py::forecast_payload().
const payload = () => structuredClone(fixture) as ForecastView;
const cleanup: (() => void)[] = [];
const flush = async () => { await new Promise<void>(resolve => setImmediate(resolve)); await nextTick(); };
function mount(view = payload()) {
  const props = reactive<{ active: boolean; summary: ForecastSummary | null; language: 'en'; theme: 'light' | 'dark'; displayTimezone: string }>({
    active: true, summary: structuredClone(view), language: 'en', theme: 'light', displayTimezone: 'UTC',
  });
  const host = document.createElement('div');
  document.body.append(host);
  const app = createApp({ render: () => h(ForecastPage, props) });
  app.mount(host);
  cleanup.push(() => { app.unmount(); host.remove(); });
  return { props, host };
}
const text = (host: HTMLElement, selector: string) => host.querySelector(selector)?.textContent;
const select = (host: HTMLElement, day = '2026-11-03') => host.querySelector<HTMLButtonElement>(`[data-day="${day}"]`)!.click();
let view: ForecastView;
let requests: string[];
beforeEach(() => {
  view = payload();
  requests = [];
  useI18n().setLanguage('en');
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(260);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', async (path: string, options?: RequestInit) => {
    requests.push(`${options?.method ?? 'GET'} ${path}`);
    return new Response(JSON.stringify(path.endsWith('/refresh') ? { scheduled: true, status: view.status } : view));
  });
});
afterEach(() => { cleanup.splice(0).forEach(dispose => dispose()); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('preserves the selected date through theme changes and a matching refreshed batch', async () => {
  const { props, host } = mount();
  await flush();
  expect(text(host, '#forecast-remaining')).toBe('39.68');
  select(host);
  await nextTick();
  props.theme = 'dark';
  await flush();
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
  host.querySelector<HTMLButtonElement>('#forecast-refresh')!.click();
  await flush();
  expect(host.querySelector<HTMLButtonElement>('#forecast-refresh')!.disabled).toBe(true);
  props.summary = { ...view, refreshing: true };
  await flush();
  view = { ...view, fetched_at: view.fetched_at! + 3600, calculated_at: view.calculated_at + 3600 };
  props.summary = structuredClone(view);
  await flush();
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
  expect(text(host, '#forecast-day-total')).toBe('89.28 kWh');
  expect(requests).toEqual(['GET api/forecast', 'POST api/forecast/refresh', 'GET api/forecast']);
});

it('updates lightweight energy and time without replacing the detailed chart or fetching again', async () => {
  const { props, host } = mount();
  await flush();
  const chart = host.querySelector('#forecast-chart svg');
  expect(chart).not.toBeNull();
  props.summary = { ...view, calculated_at: view.calculated_at + 1200,
    remaining_today: { ...view.remaining_today!, kwh: 38.44 } };
  await flush();
  expect(text(host, '#forecast-remaining')).toBe('38.44');
  expect(host.querySelector('#forecast-chart svg')).toBe(chart);
  expect(requests).toEqual(['GET api/forecast']);
});

it('finishes a scheduled refresh when the next snapshot already contains the completed batch', async () => {
  const { props, host } = mount();
  await flush();
  host.querySelector<HTMLButtonElement>('#forecast-refresh')!.click();
  await flush();
  expect(host.querySelector<HTMLButtonElement>('#forecast-refresh')!.disabled).toBe(true);
  view = { ...view, fetched_at: view.fetched_at! + 3600, calculated_at: view.calculated_at + 3600 };
  props.summary = structuredClone(view);
  await flush();
  expect(host.querySelector<HTMLButtonElement>('#forecast-refresh')!.disabled).toBe(false);
  expect(text(host, '#forecast-day-total')).toBe('89.28 kWh');
});

it('keeps a newer detailed response and selection when a light snapshot is older', async () => {
  const older = payload();
  view.fetched_at! += 3600;
  view.calculated_at += 3600;
  view.remaining_today!.kwh = 31.11;
  const { props, host } = mount(older);
  await flush();
  select(host);
  props.summary = { ...older, calculated_at: older.calculated_at + 1 };
  await flush();
  expect(text(host, '#forecast-remaining')).toBe('31.11');
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
  expect(requests).toEqual(['GET api/forecast']);
});

it('refreshes calendar boundaries at midnight while retaining a still-valid selection', async () => {
  const { props, host } = mount();
  await flush();
  select(host);
  view = { ...view, calculated_at: view.calculated_at + 86400,
    today: view.tomorrow, seven_days: { ...view.seven_days!, end: view.seven_days!.end + 86400 },
    days: view.days.slice(1) };
  props.summary = structuredClone(view);
  await flush();
  expect(host.querySelector('#forecast-days button')?.getAttribute('data-day')).toBe('2026-11-02');
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
  view = { ...view, calculated_at: view.calculated_at + 86400,
    today: view.days[3], days: view.days.slice(3) };
  props.summary = structuredClone(view);
  await flush();
  expect(host.querySelector('#forecast-days button')?.getAttribute('aria-pressed')).toBe('true');
  expect(requests).toHaveLength(3);
});

it('shows partial and unavailable totals as unavailable even when a numeric partial sum exists', async () => {
  view.status = 'partial';
  view.remaining_today = { ...view.remaining_today!, quality: 'partial', kwh: 12.34 };
  view.tomorrow = { ...view.tomorrow!, quality: 'unavailable', kwh: 0 };
  view.seven_days = { ...view.seven_days!, quality: 'partial', kwh: 100 };
  view.days[2] = { ...view.days[2], quality: 'partial', kwh: 40, coverage_percent: 50 };
  const { host } = mount(view);
  await flush();
  select(host);
  await nextTick();
  expect(text(host, '#forecast-remaining')).toBe('—');
  expect(text(host, '#forecast-tomorrow')).toBe('—');
  expect(text(host, '#forecast-seven-days')).toBe('— kWh');
  expect(text(host, '#forecast-day-total')).toBe('— kWh');
  expect(text(host, '#forecast-day-coverage')).toContain('50%');
});

it('inspects one original hourly row at a time without changing daily energy', async () => {
  view.intervals[0].power_w = 0;
  view.intervals[0].energy_kwh = 0;
  const { host } = mount();
  await flush();
  const beforeTotals = text(host, '#forecast-day-total');
  const hit = host.querySelector('.chart-hit-area')!;
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Forecast power0 W');
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Forecast power3,720 W');
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('3.72 kWh');
  expect(text(host, '#forecast-day-total')).toEqual(beforeTotals);
});

it('changes only fetched display time and the conditional note when viewer timezone changes', async () => {
  const { props, host } = mount();
  await flush();
  select(host);
  await flush();
  const before = text(host, '#forecast-day-total');
  const chart = host.querySelector('#forecast-chart svg');
  const row = host.querySelector('#forecast-rows time')?.textContent;
  props.displayTimezone = 'America/Los_Angeles';
  await flush();
  expect(text(host, '#forecast-fetched')).toContain('Oct 31');
  expect(text(host, '#forecast-home-time-note')).toContain('UTC');
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
  expect(text(host, '#forecast-day-total')).toBe(before);
  expect(host.querySelector('#forecast-chart svg')).toBe(chart);
  expect(host.querySelector('#forecast-rows time')?.textContent).toBe(row);
  expect(requests).toEqual(['GET api/forecast']);
  props.displayTimezone = 'Etc/UTC';
  await flush();
  expect(host.querySelector('#forecast-home-time-note')).toBeNull();
  expect(text(host, '#forecast-fetched')).not.toMatch(/GMT|UTC/);
});
