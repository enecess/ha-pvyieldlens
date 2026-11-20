import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import { setImmediate } from 'node:timers';
import LivePage from '../../pvyieldlens/frontend/src/LivePage.vue';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';
import type { Configuration, Snapshot } from '../../pvyieldlens/frontend/src/models';

const window = { revision: 1, start: 100, end: 400, estimated_power_w: 2000, actual_power_w: 2100,
  pr: 105, optimizable_power_w: -100, quality: 'partial', reason: 'missing_data', data_completeness_percent: 60,
  valid_seconds: 180, estimated_energy_wh: 100, actual_energy_wh: 105 };
const generation = (sun = 800) => ({ windows: [window], inputs: [{ start: 100, end: 400,
  irradiance_w_m2: sun, module_temperature_c: null }], requested_range: { start: 100, end: 400 }, home_timezone: 'UTC' });
const history = (period = '7d') => ({ windows: [], days: [], period, today: '2026-11-17', home_timezone: 'UTC',
  requested_range: { start: 100, end: 400 }, summary: { estimated_energy_kwh: 10, actual_energy_kwh: 12, pr: 120 }, comparison: null });
const flush = async () => { await new Promise<void>(resolve => setImmediate(resolve)); await nextTick(); await nextTick(); };
const cleanup: (() => void)[] = [];
function deferred() { let resolve!: (value: Response) => void; const promise = new Promise<Response>(done => { resolve = done; }); return { promise, resolve }; }
function mount(active = true) {
  const props = reactive({ active, configuration: { monitoring_settings: { settlement_interval_minutes: 5, home_timezone: 'UTC',
    live_window_seconds: 60, update_interval_seconds: 5 } } as Configuration | null,
    snapshot: { revision: 1, calculated_at: 400, live_window: window, latest_settled_window: window,
      home_timezone: 'UTC', energy_totals: { day: '2026-11-17' } } as Snapshot,
    language: 'en' as const, theme: 'light' as const, displayTimezone: 'UTC', seriesError: null,
    range: { start: 100, end: 400 }, points: [{ ...window, at: 400, window }] });
  const host = document.createElement('div'); document.body.append(host);
  const app = createApp({ render: () => h(LivePage, props) }); app.mount(host);
  cleanup.push(() => { app.unmount(); host.remove(); });
  return { props, host };
}
beforeEach(() => {
  useI18n().setLanguage('en');
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(220);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.includes('generation-data') ? generation() : history()))));
});
afterEach(() => { cleanup.splice(0).forEach(dispose => dispose()); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('renders the dashboard charts without quality displays', async () => {
  const { host } = mount(); await flush();
  ['generation-power-chart', 'generation-irradiance-chart', 'generation-temperature-chart', 'dashboard-energy-chart'].forEach(id =>
    expect(host.querySelectorAll('#' + id)).toHaveLength(1));
  expect(fetch).toHaveBeenCalledWith('api/history?period=7d&include_windows=false', expect.anything());
  expect(host.querySelector('#live-actual')?.textContent).toBe('2,100');
  expect(host.querySelector('#live-pr')?.textContent).toBe('105');
  expect(host.querySelector('#generation-data')?.textContent).not.toMatch(/Today|Settled power|quality|completeness/i);
  expect(host.textContent).not.toMatch(/quality|completeness|included settled/i);
  host.querySelector('#generation-irradiance-chart .chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  await flush();
  expect(host.querySelector('#generation-irradiance-chart .chart-tooltip')?.textContent).toContain('800 W/m²');
  host.querySelector('#generation-temperature-chart .chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  await flush();
  expect(host.querySelector('#generation-temperature-chart .chart-tooltip')?.textContent).toContain('— °C');
});

it.each([
  ['generation-power-chart', '2,100 W'],
  ['generation-irradiance-chart', '800 W/m²'],
  ['generation-temperature-chart', '— °C'],
])('inspects the settlement window at its midpoint on %s', async (id, value) => {
  const { host } = mount();
  await flush();

  const chart = host.querySelector(`#${id}`)!;
  const hit = chart.querySelector('.chart-hit-area')!;
  const clientX = Number(hit.getAttribute('x')) + Number(hit.getAttribute('width')) / 2;
  hit.dispatchEvent(new MouseEvent('pointermove', { clientX }));

  expect(hit.getAttribute('aria-valuenow')).toBe('400');
  expect(chart.querySelector('.chart-tooltip')?.textContent).toContain(value);
});

it('applies valid inclusive custom dates, rejects invalid drafts and cancels without fetching', async () => {
  const { host } = mount(); await flush();
  const click = async (value: string) => { host.querySelector<HTMLElement>(value)!.click(); await flush(); };
  const setDate = async (suffix: string, value: string) => {
    const input = host.querySelector<HTMLInputElement>('#dashboard-energy-range-' + suffix)!;
    input.value = value; input.dispatchEvent(new Event('input')); await flush();
  };
  await click('#dashboard-energy-range [data-value=custom]');
  await setDate('start', '2026-08-01'); await setDate('end', '2026-11-17');
  expect(host.querySelector<HTMLButtonElement>('#dashboard-energy-range-apply')!.disabled).toBe(true);
  await setDate('start', '2026-08-20');
  expect(host.querySelector<HTMLButtonElement>('#dashboard-energy-range-apply')!.disabled).toBe(false);
  await setDate('start', '2026-08-19');
  expect(host.querySelector<HTMLButtonElement>('#dashboard-energy-range-apply')!.disabled).toBe(true);
  await click('#dashboard-energy-range-cancel');
  expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes('history'))).toHaveLength(1);
  await click('#dashboard-energy-range [data-value=custom]');
  await setDate('start', '2026-11-01'); await setDate('end', '2026-11-17');
  await click('#dashboard-energy-range-apply');
  expect(fetch).toHaveBeenLastCalledWith('api/history?period=custom&start_date=2026-11-01&end_date=2026-11-17&include_windows=false', expect.anything());
  expect(host.querySelector('#dashboard-energy-range [data-value=custom]')?.textContent).toContain('2026-11-01');
  await click('#dashboard-energy-range [data-value=custom]');
  await setDate('end', '2026-11-18');
  expect(host.querySelector<HTMLButtonElement>('#dashboard-energy-range-apply')!.disabled).toBe(true);
});

it.each([
  ['start', '2026-11-03', '2026-11-17'],
  ['end', '2026-11-15', '2026-11-16'],
])('hides accepted Dashboard history when a custom %s date changes', async (suffix, value, endDate) => {
  const saved = history('custom');
  const day = { day: endDate, start: 100, end: 400, summary: saved.summary,
    in_progress: endDate === saved.today, boundary_unavailable: false };
  const loaded = { ...saved, days: [day] };
  const pending = deferred();
  const originalQuery = 'period=custom&start_date=2026-11-01&end_date=' + endDate;
  let originalReply = () => Promise.resolve(new Response(JSON.stringify(loaded)));
  vi.mocked(fetch).mockImplementation(async url => {
    const query = String(url);
    if (query.includes('generation-data')) return new Response(JSON.stringify(generation()));
    if (query.includes(originalQuery)) return originalReply();
    if (query.includes('period=custom')) return pending.promise;
    return new Response(JSON.stringify(history()));
  });
  const { props, host } = mount(); await flush();
  const click = async (selector: string) => { host.querySelector<HTMLElement>(selector)!.click(); await flush(); };
  const setDate = async (field: string, date: string) => {
    const input = host.querySelector<HTMLInputElement>('#dashboard-energy-range-' + field)!;
    input.value = date; input.dispatchEvent(new Event('input')); await flush();
  };
  const open = () => click('#dashboard-energy-range [data-value=custom]');
  const apply = () => click('#dashboard-energy-range-apply');
  const summary = () => host.querySelector('.dashboard-history .energy-summary')?.textContent;
  const error = () => host.querySelector('.dashboard-history > [role=status]');
  await open(); await setDate('start', '2026-11-01'); await setDate('end', endDate); await apply();
  expect(summary()).toContain('12 kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(1);
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-cutoff')).toHaveLength(day.in_progress ? 1 : 0);
  await open(); await setDate(suffix, value); await apply();
  expect(host.querySelector('#dashboard-energy-range [data-value=custom]')?.textContent).toContain(value);
  expect(summary()).toContain('— kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(0);
  pending.resolve(new Response('{}', { status: 500 })); await flush();
  expect(error()?.textContent).toBe('Something went wrong. Please retry.');
  expect(summary()).toContain('— kWh');
  await open(); await setDate(suffix, suffix === 'start' ? '2026-11-01' : endDate); await apply();
  expect(summary()).toContain('12 kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(1);
  expect(error()).toBeNull();
  expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes(originalQuery))).toHaveLength(1);

  const rollover = deferred();
  originalReply = () => rollover.promise;
  props.snapshot = { ...props.snapshot, energy_totals: { ...props.snapshot.energy_totals, day: '2026-11-18' } };
  await flush();
  expect(summary()).toContain('12 kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(1);
  const past = { ...loaded, today: '2026-11-18', days: [{ ...day, in_progress: false }] };
  rollover.resolve(new Response(JSON.stringify(past))); await flush();
  expect(host.querySelector('#dashboard-energy-chart .daily-cutoff')).toBeNull();

  const timezoneChange = deferred();
  originalReply = () => timezoneChange.promise;
  props.snapshot = { ...props.snapshot, home_timezone: 'Asia/Shanghai' }; await flush();
  expect(summary()).toContain('— kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(0);
  timezoneChange.resolve(new Response(JSON.stringify({ ...past, home_timezone: 'Asia/Shanghai' })));
  await flush(); expect(summary()).toContain('12 kWh');
});

it('fetches only for visible active dataset contexts and ignores live-only updates', async () => {
  const { props } = mount(false); await flush(); expect(fetch).not.toHaveBeenCalled();
  props.active = true; await flush(); expect(fetch).toHaveBeenCalledTimes(2);
  props.snapshot = { ...props.snapshot, calculated_at: 405 }; await flush(); expect(fetch).toHaveBeenCalledTimes(2);
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  document.dispatchEvent(new Event('visibilitychange')); await flush();
  props.snapshot = { ...props.snapshot, revision: 2 }; await flush(); expect(fetch).toHaveBeenCalledTimes(2);
  hidden.mockReturnValue(false); document.dispatchEvent(new Event('visibilitychange')); await flush();
  expect(fetch).toHaveBeenCalledTimes(4);
  props.active = false; await flush(); props.active = true; await flush(); expect(fetch).toHaveBeenCalledTimes(4);
});

it('ignores_old_generation_response_after_context_changes', async () => {
  const old = deferred();
  vi.mocked(fetch).mockImplementation(async (url: string | URL | Request) => String(url).includes('generation-data') ? old.promise : new Response(JSON.stringify(history())));
  const { props, host } = mount(); await flush();
  vi.mocked(fetch).mockImplementation(async (url: string | URL | Request) => new Response(JSON.stringify(String(url).includes('generation-data') ? generation(900) : history())));
  props.snapshot = { ...props.snapshot, revision: 2 }; await flush();
  old.resolve(new Response(JSON.stringify(generation(10)))); await flush();
  host.querySelector('#generation-irradiance-chart .chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  await flush(); expect(host.querySelector('#generation-irradiance-chart .chart-tooltip')?.textContent).toContain('900 W/m²');
});

it.each(['7d', '30d'])('replaces Dashboard %s history at midnight with a fixed offline measurement timestamp', async period => {
  const previous = history(period);
  const day = { day: previous.today, start: 100, end: 400, summary: previous.summary,
    in_progress: true, boundary_unavailable: false };
  let dailyReply = () => Promise.resolve(new Response(JSON.stringify({ ...previous, days: [day] })));
  vi.mocked(fetch).mockImplementation(async url =>
    String(url).includes('generation-data') ? new Response(JSON.stringify(generation())) : dailyReply());
  const { props, host } = mount(); await flush();
  if (period === '30d') {
    host.querySelector<HTMLElement>('#dashboard-energy-range [data-value="30d"]')!.click();
    await flush();
  }
  const summary = () => host.querySelector('.dashboard-history .energy-summary')?.textContent;
  expect(summary()).toContain('12 kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(1);
  const requests = vi.mocked(fetch).mock.calls.length;
  const midnight = deferred();
  dailyReply = () => midnight.promise;
  const calculated = props.snapshot.calculated_at;
  props.snapshot = { ...props.snapshot, connected: false, energy_totals: { ...props.snapshot.energy_totals, day: '2026-11-18' } };
  await flush();
  expect(fetch).toHaveBeenCalledTimes(requests + 2);
  expect(summary()).toContain('— kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(0);
  midnight.resolve(new Response('{}', { status: 500 })); await flush();
  expect(host.querySelector('.dashboard-history > [role=status]')?.textContent).toBe('Something went wrong. Please retry.');
  expect(summary()).toContain('— kWh');

  const currentSummary = { ...previous.summary, actual_energy_kwh: 8 };
  dailyReply = () => Promise.resolve(new Response(JSON.stringify({ ...previous, today: '2026-11-18',
    summary: currentSummary, days: [{ ...day, day: '2026-11-18', summary: currentSummary }] })));
  props.snapshot = { ...props.snapshot, revision: 2 }; await flush();
  expect(props.snapshot.calculated_at).toBe(calculated);
  expect(summary()).toContain('8 kWh');
  expect(host.querySelectorAll('#dashboard-energy-chart .daily-column')).toHaveLength(1);
  expect(host.querySelector('.dashboard-history > [role=status]')).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(requests + 4);
  props.snapshot = { ...props.snapshot }; await flush();
  expect(fetch).toHaveBeenCalledTimes(requests + 4);
});
