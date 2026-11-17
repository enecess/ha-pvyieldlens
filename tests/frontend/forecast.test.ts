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
    remaining_today: { ...view.remaining_today!, forecast_energy_kwh: 38.44 } };
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
  view.remaining_today!.forecast_energy_kwh = 31.11;
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

it('keeps incomplete totals unavailable while omitting quality and coverage presentation', async () => {
  view.status = 'partial';
  view.remaining_today = { ...view.remaining_today!, quality: 'partial', forecast_energy_kwh: null, corrected_forecast_energy_kwh: null };
  view.tomorrow = { ...view.tomorrow!, quality: 'unavailable', forecast_energy_kwh: null, corrected_forecast_energy_kwh: null };
  view.seven_days = { ...view.seven_days!, quality: 'partial', forecast_energy_kwh: null, corrected_forecast_energy_kwh: null };
  view.days[2] = { ...view.days[2], quality: 'partial', forecast_energy_kwh: null, corrected_forecast_energy_kwh: null, data_completeness_percent: 50 };
  const { host } = mount(view);
  await flush();
  select(host);
  await nextTick();
  expect(text(host, '#forecast-remaining')).toBe('—');
  expect(text(host, '#forecast-tomorrow')).toBe('—');
  expect(text(host, '#forecast-seven-days')).toBe('— kWh');
  expect(text(host, '#forecast-day-total')).toBe('— kWh');
  expect(host.textContent).not.toMatch(/partial|stale|completeness|coverage|quality/i);
  expect(host.querySelector('#forecast-day-data-completeness')).toBeNull();
  [...host.querySelectorAll('#forecast-days button')].forEach(card => {
    expect(card.getAttribute('aria-label')).not.toMatch(/complete|partial|quality|coverage/i);
  });
});

it('inspects one original quarter-hour row at a time without changing daily energy', async () => {
  view.intervals[0].forecast_power_w = 0;
  view.intervals[0].forecast_energy_kwh = 0;
  const { host } = mount();
  await flush();
  const beforeTotals = text(host, '#forecast-day-total');
  const hit = host.querySelector('.chart-hit-area')!;
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Original forecast power0 W');
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Original forecast power3,720 W');
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('0.93 kWh');
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Irradiance800 W/m²');
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Air temperature20 °C');
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Estimated cell temperature45 °C');
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

it('shows_weather_and_today_independently_of_selection', async () => {
  const { props, host } = mount();
  props.displayTimezone = 'America/Los_Angeles';
  await flush();
  const cards = [...host.querySelectorAll<HTMLButtonElement>('#forecast-days button')];
  expect(cards).toHaveLength(7);
  expect(cards.map(card => card.querySelector('.day-weather')?.textContent)).toEqual([
    'Clear sky', 'Overcast', 'Rain', 'Snow', 'Thunderstorm', 'Unknown weather', 'Fog',
  ]);
  expect(cards.map(card => card.querySelector('.day-temperature')?.textContent)).toEqual([
    '20° / 0°', '21° / 11°', '22° / 12°', '23° / 13°', '24° / 14°', '25° / 15°', '26° / 16°',
  ]);
  expect(cards.every(card => card.querySelector('.day-weather-icon'))).toBe(true);
  expect(cards[0].getAttribute('aria-current')).toBe('date');
  expect(cards[0].querySelector('.day-label')?.textContent).toBe('Today');
  expect(cards[0].getAttribute('aria-label')).toContain('November 1, 2026');
  expect(cards[0].getAttribute('aria-label')).toContain('Clear sky');
  expect(cards[0].getAttribute('aria-label')).toContain('Forecast air temperature: high 20 °C, low 0 °C');
  expect(cards[0].getAttribute('aria-label')).toContain('89.28 kWh');
  select(host);
  await flush();
  expect(cards[0].getAttribute('aria-current')).toBe('date');
  expect(cards[0].getAttribute('aria-pressed')).toBe('false');
  expect(cards[2].getAttribute('aria-pressed')).toBe('true');
  expect(cards[2].hasAttribute('aria-current')).toBe(false);
});

it('keeps_weather_through_scalar_updates', async () => {
  const { props, host } = mount();
  await flush();
  select(host);
  await flush();
  const chart = host.querySelector('#forecast-chart svg');
  const weather = text(host, '#forecast-days .day-weather');
  expect(weather).toBe('Clear sky');
  const { days, intervals, ...summary } = view;
  props.summary = { ...summary, calculated_at: view.calculated_at + 1200,
    remaining_today: { ...view.remaining_today!, forecast_energy_kwh: 38.44 } };
  await flush();
  expect(text(host, '#forecast-days .day-weather')).toBe(weather);
  expect(host.querySelector('#forecast-chart svg')).toBe(chart);
  expect(requests).toEqual(['GET api/forecast']);
  host.querySelector<HTMLButtonElement>('#forecast-refresh')!.click();
  await flush();
  view = { ...view, fetched_at: view.fetched_at! + 3600, calculated_at: view.calculated_at + 3600 };
  props.summary = structuredClone(view);
  await flush();
  expect(text(host, '#forecast-days .day-weather')).toBe('Clear sky');
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
});

it('shows neutral missing weather and preserves complete zero temperatures', async () => {
  view.days[0].weather = null;
  view.days[1].weather = { weather_code: 0, air_temperature_min_c: null, air_temperature_max_c: null, quality: 'partial' };
  view.days[2].weather = { weather_code: null, air_temperature_min_c: 0, air_temperature_max_c: 0, quality: 'partial' };
  const { host } = mount(view);
  await flush();
  const cards = [...host.querySelectorAll('#forecast-days button')];
  expect(cards[0].querySelector('.day-weather')?.textContent).toBe('Unknown weather');
  expect(cards[0].querySelector('.day-temperature')?.textContent).toBe('— / —');
  expect(cards[1].querySelector('.day-weather')?.textContent).toBe('Clear sky');
  expect(cards[1].querySelector('.day-temperature')?.textContent).toBe('— / —');
  expect(cards[2].querySelector('.day-temperature')?.textContent).toBe('0° / 0°');
  expect(text(host, '#forecast-day-total')).toBe('89.28 kWh');
});

function applyCorrection(pr: number | null) {
  view.correction = { ...view.correction!, pr };
  view.intervals = view.intervals.map(row => ({ ...row,
    corrected_forecast_power_w: pr === null || row.forecast_power_w === null ? null : row.forecast_power_w * pr / 100,
    corrected_forecast_energy_kwh: pr === null || row.forecast_energy_kwh === null ? null : row.forecast_energy_kwh * pr / 100 }));
  view.days = view.days.map(day => ({ ...day,
    corrected_forecast_energy_kwh: pr === null || day.forecast_energy_kwh === null ? null : day.forecast_energy_kwh * pr / 100 }));
  (['today', 'remaining_today', 'tomorrow', 'seven_days'] as const).forEach(key => {
    const total = view[key]!;
    view[key] = { ...total, corrected_forecast_energy_kwh: pr === null || total.forecast_energy_kwh === null
      ? null : total.forecast_energy_kwh * pr / 100 };
  });
}

it('pairs original and corrected fifteen-minute values without quality wording', async () => {
  useI18n().setLanguage('zh');
  const rawInterval = view.intervals[0];
  const correctedInterval = view.intervals[0];
  expect(rawInterval.forecast_energy_kwh).toBeCloseTo(0.93);
  expect(correctedInterval.corrected_forecast_energy_kwh).toBeCloseTo(0.837);
  const { host } = mount(view);
  await flush();
  expect(host.textContent).toContain('每 15 分钟预测');
  expect(host.textContent).toContain('修正预测');
  expect(host.textContent).not.toContain('PR 修正');
  expect(host.querySelectorAll('#forecast-rows tr')).toHaveLength(96);
  expect(text(host, '#forecast-remaining-corrected')).toBe('35.712');
  expect(text(host, '#forecast-tomorrow-corrected')).toBe('80.352');
  expect(text(host, '#forecast-seven-days-corrected')).toBe('562.464 kWh');
  expect(text(host, '#forecast-day-total-corrected')).toBe('80.352 kWh');
  expect(host.querySelectorAll('#forecast-chart path.series')).toHaveLength(2);
  const hit = host.querySelector('.chart-hit-area')!;
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('修正预测电量0.837 kWh');
  expect(host.querySelector('.chart-tooltip')?.textContent).not.toMatch(/质量|完整率/);
});

it.each([null, 0, 120])('keeps correction %s distinct from raw values', async pr => {
  applyCorrection(pr);
  const { host } = mount(view);
  await flush();
  expect(text(host, '#forecast-remaining')).toBe('39.68');
  expect(text(host, '#forecast-remaining-corrected')).toBe(pr === null ? '—' : pr === 0 ? '0' : '47.616');
  expect(text(host, '#forecast-day-total-corrected')).toBe(pr === null ? '— kWh' : pr === 0 ? '0 kWh' : '107.136 kWh');
  expect(host.querySelectorAll('#forecast-days .day-bar.corrected')).toHaveLength(7);
  expect(host.querySelector('#forecast-rows tr')?.textContent).toContain(pr === null ? '—' : pr === 0 ? '0' : '4,464');
});

it('updates_corrected_detail_without_refetching_weather', async () => {
  const { props, host } = mount();
  await flush();
  select(host);
  await flush();
  const fetchedAt = view.fetched_at;
  applyCorrection(80);
  view.calculated_at += 1;
  props.summary = structuredClone(view);
  await flush();
  expect(view.fetched_at).toBe(fetchedAt);
  expect(text(host, '#forecast-day-total-corrected')).toBe('71.424 kWh');
  expect(host.querySelector('#forecast-rows tr')?.textContent).toContain('2,976');
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
  expect(requests).toEqual(['GET api/forecast', 'GET api/forecast']);
});

it('does_not_trust_reset_revision_for_correction_identity', async () => {
  Object.assign(view.correction!, { revision: 1 });
  const { props, host } = mount();
  await flush();
  select(host);
  await flush();
  applyCorrection(110);
  Object.assign(view.correction!, { revision: 1 });
  props.summary = structuredClone(view);
  await flush();
  expect(text(host, '#forecast-day-total-corrected')).toBe('98.208 kWh');
  expect(host.querySelector('[data-day="2026-11-03"]')?.getAttribute('aria-pressed')).toBe('true');
  expect(requests).toHaveLength(2);
  view.correction!.history_days = 30;
  view.correction!.start -= 16 * 86400;
  props.summary = structuredClone(view);
  await flush();
  expect(requests).toHaveLength(3);
  view.correction!.end += 86400;
  props.summary = structuredClone(view);
  await flush();
  expect(requests).toHaveLength(4);
});

it('keeps weather available when energy is missing independently', async () => {
  view.days[0].forecast_energy_kwh = null;
  view.days[0].corrected_forecast_energy_kwh = null;
  view.intervals[0].forecast_power_w = null;
  view.intervals[0].corrected_forecast_power_w = null;
  view.intervals[0].forecast_energy_kwh = null;
  view.intervals[0].corrected_forecast_energy_kwh = null;
  const { host } = mount(view);
  await flush();
  expect(text(host, '#forecast-days .day-weather')).toBe('Clear sky');
  expect(text(host, '#forecast-day-total')).toBe('— kWh');
  expect(text(host, '#forecast-day-total-corrected')).toBe('— kWh');
  expect(host.querySelector('#forecast-rows tr')?.textContent).toContain('—');
});

it.each([92, 100])('retains all %s quarter-hour intervals on a DST day', async count => {
  const start = view.today!.start;
  const end = start + count * 900;
  view.days = [{ ...view.days[0], end }];
  view.intervals = Array.from({ length: count }, (_, index) => ({
    ...view.intervals[0], start: start + index * 900, end: start + (index + 1) * 900 }));
  const { host } = mount(view);
  await flush();
  expect(host.querySelectorAll('#forecast-rows tr')).toHaveLength(count);
  expect(host.querySelector('#forecast-rows tr:last-child time:last-child')?.getAttribute('datetime'))
    .toBe(new Date(end * 1000).toISOString());
});

it('clips both energies at non-grid household boundaries', async () => {
  const start = view.today!.start + 100;
  view.days = [{ ...view.days[0], start, end: start + 900 }];
  const { host } = mount(view);
  await flush();
  const rows = [...host.querySelectorAll('#forecast-rows tr')];
  expect(rows).toHaveLength(2);
  expect(rows[0].lastElementChild?.textContent).toBe('0.744');
  expect(rows[1].lastElementChild?.textContent).toBe('0.093');
});
