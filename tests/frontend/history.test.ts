import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import { setImmediate } from 'node:timers';
import HistoryPage from '../../pvyieldlens/frontend/src/HistoryPage.vue';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';
import type { Configuration, Snapshot } from '../../pvyieldlens/frontend/src/models';

const summary = { start: 1794326400, end: 1794326580, estimated_energy_kwh: 0.08,
  actual_energy_kwh: 0.07, pr: 87.5, data_completeness_percent: 60, valid_seconds: 180 };
const window = { revision: 1, start: 1794326400, end: 1794326580, valid_seconds: 180,
  estimated_energy_wh: 60, actual_energy_wh: 60, estimated_power_w: 1200, actual_power_w: 1200,
  pr: 100, optimizable_power_w: 0, data_completeness_percent: 100, quality: 'complete', reason: null,
  source_start: 1794326280, source_end: 1794326580 };
const empty = { start: null, end: null, estimated_energy_kwh: null, actual_energy_kwh: null,
  pr: null, data_completeness_percent: null, valid_seconds: 0 };
const view = (period: string) => ({ windows: [window], summary, requested_range: { start: window.start, end: window.end },
  period, home_timezone: 'Asia/Shanghai', today: '2026-11-11', boundary_unavailable: false,
  days: period === '7d' || period === '30d' ? Array.from({ length: period === '7d' ? 7 : 30 }, (_, i) => ({
    day: new Date(Date.UTC(2026, 10, 11 - (period === '7d' ? 6 : 29) + i)).toISOString().slice(0, 10),
    start: window.start - ((period === '7d' ? 6 : 29) - i) * 86400, end: window.start + (i + 1) * 86400,
    summary: i === 1 ? { ...summary, estimated_energy_kwh: 0, actual_energy_kwh: 0, pr: null }
      : i === 2 ? { ...empty, boundary_unavailable: true } : i === 3 ? summary : empty,
    in_progress: i === (period === '7d' ? 6 : 29), boundary_unavailable: i === 2,
  })) : [] });
let host: HTMLDivElement;
let app: ReturnType<typeof createApp>;
let props: { active: boolean; configuration: Configuration; snapshot: Snapshot; language: 'en'; theme: 'light'; displayTimezone: string };
let requests: string[];
const flush = async () => { await new Promise<void>(resolve => setImmediate(resolve)); await nextTick(); await nextTick(); };
const select = async (period: string) => {
  const field = host.querySelector<HTMLSelectElement>('#history-range')!;
  field.value = period; field.dispatchEvent(new Event('change')); await flush();
};
beforeEach(async () => {
  useI18n().setLanguage('en');
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(600);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(260);
  requests = [];
  vi.stubGlobal('fetch', async (url: string) => {
    requests.push(url);
    return new Response(JSON.stringify(view(new URL(url, 'http://test/').searchParams.get('period') ?? '')));
  });
  props = reactive({ active: true, configuration: { monitoring_settings: { home_timezone: 'Asia/Shanghai' } } as Configuration,
    snapshot: { revision: 1, latest_settled_window: window, home_timezone: 'Asia/Shanghai', energy_totals: { day: '2026-11-11' } } as Snapshot,
    language: 'en', theme: 'light', displayTimezone: 'America/Los_Angeles' });
  host = document.createElement('div'); document.body.append(host);
  app = createApp({ render: () => null });
});
const mount = async () => { app = createApp({ render: () => h(HistoryPage, props) }); app.mount(host); await flush(); };
afterEach(() => { app.unmount(); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('defaults to Today and shows server actual energy first without the totals fold', async () => {
  await mount();
  expect(requests).toEqual(['api/history?period=today']);
  expect([...host.querySelectorAll('.metric-label')].map(node => node.textContent)).toEqual([
    'Range actual energy', 'Estimated energy in range', 'PR in range', 'Data completeness']);
  expect(host.querySelector('#history-actual-energy')?.textContent).toBe('0.07');
  expect(host.querySelector('#history-pr')?.textContent).toBe('87.5');
  expect(host.querySelector('#history-totals')).toBeNull();
  expect(host.querySelector('#history-home-timezone')?.textContent).toContain('Asia/Shanghai');
  expect(host.querySelector('#history-chart .chart-hit-area')?.getAttribute('aria-valuemin')).toBe('1794326400');
  expect(host.querySelector('#history-chart .chart-hit-area')?.getAttribute('aria-valuemax')).toBe('1794326580');
});

it('requests named presets and keeps detail charts below calendar-only daily panels', async () => {
  await mount();
  for (const period of ['24h', '7d', '30d', 'today']) {
    await select(period);
    expect(requests.at(-1)).toBe(`api/history?period=${period}`);
    expect(host.querySelectorAll('.daily-history-chart').length).toBe(['7d', '30d'].includes(period) ? 2 : 0);
    expect(host.querySelectorAll('#history-chart svg, #pr-chart svg')).toHaveLength(2);
    if (period === '30d') expect(host.querySelectorAll('#daily-energy-chart .daily-column')).toHaveLength(30);
  }
});

it('invalidates calendar cache at HA midnight without a new settlement and reformats without fetching', async () => {
  await mount();
  props.snapshot = { ...props.snapshot, energy_totals: { ...props.snapshot.energy, day: '2026-11-12' } };
  await flush(); expect(requests).toHaveLength(2);
  props.theme = 'light'; props.displayTimezone = 'UTC'; useI18n().setLanguage('de');
  await flush(); expect(requests).toHaveLength(2);
  props.active = false; await flush(); props.active = true; await flush();
  expect(requests).toHaveLength(2);
});

it('retains fragment provenance in detail inspection', async () => {
  await mount();
  host.querySelector('.chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  await flush();
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Range boundary fragment');
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Original settled window');
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('07:58');
});

it('preserves empty slots, real zero bars, null PR gaps and keyboard access to unavailable dates', async () => {
  await mount(); await select('7d');
  expect(host.querySelectorAll('#daily-energy-chart .daily-bar')).toHaveLength(4);
  expect(host.querySelectorAll('#daily-energy-chart .daily-bar[height="0"]')).toHaveLength(2);
  expect(Number(host.querySelectorAll('#daily-energy-chart .daily-bar')[2].getAttribute('height'))).toBeGreaterThan(150);
  expect(host.querySelectorAll('#daily-pr-chart .daily-pr-point')).toHaveLength(1);
  const hit = host.querySelector('#daily-energy-chart .chart-hit-area')!;
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true })); await flush();
  expect(host.querySelector('#daily-energy-chart .chart-tooltip')?.textContent).toContain('— kWh');
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); await flush();
  expect(host.querySelector('#daily-energy-chart .chart-tooltip')?.textContent).toContain('0 kWh');
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); await flush();
  expect(host.querySelector('#daily-energy-chart .chart-tooltip')?.textContent).toContain('cannot be allocated exactly');
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true })); await flush();
  expect(host.querySelector('#daily-energy-chart .chart-tooltip')?.textContent).toContain('No settled periods');
});

it.each([0, null])('keeps server actual energy %s distinct from unavailable outer boundaries', async value => {
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ ...view('today'), windows: [],
    summary: { ...empty, actual_energy_kwh: value }, boundary_unavailable: true })));
  await mount();
  expect(host.querySelector('#history-actual-energy')?.textContent).toBe(value === 0 ? '0' : '—');
  expect(host.querySelector('#history-boundary-unavailable')?.textContent).toContain('cannot be allocated exactly');
  expect(host.querySelector('#history-chart .chart-empty')).not.toBeNull();
});

it('breaks daily PR paths at null dates instead of connecting across missing days', async () => {
  vi.stubGlobal('fetch', async (url: string) => {
    const result = view(new URL(url, 'http://test/').searchParams.get('period')!);
    result.days = result.days.map((day, index) => ({ ...day,
      summary: [1, 3, 4].includes(index) ? summary : empty }));
    return new Response(JSON.stringify(result));
  });
  await mount(); await select('7d');
  expect(host.querySelector('#daily-pr-chart path.series')?.getAttribute('d')?.trim()).toMatch(/^M[^M]+M[^M]+L[^M]+$/);
  expect(host.querySelectorAll('#daily-pr-chart .daily-pr-point')).toHaveLength(3);
});

it('retires daily chart scroll callbacks across repeated calendar and non-calendar transitions', async () => {
  host.id = 'content-scroll';
  const add = host.addEventListener.bind(host);
  const remove = host.removeEventListener.bind(host);
  const listeners = new Map<EventListenerOrEventListenerObject, EventListener>();
  let scrollCalls = 0;
  vi.spyOn(host, 'addEventListener').mockImplementation((type, listener, options) => {
    if (type !== 'scroll') { add(type, listener, options); return; }
    const wrapped: EventListener = event => {
      scrollCalls++;
      if (typeof listener === 'function') listener.call(host, event);
      else listener.handleEvent(event);
    };
    listeners.set(listener, wrapped);
    add(type, wrapped, options);
  });
  vi.spyOn(host, 'removeEventListener').mockImplementation((type, listener, options) => {
    remove(type, type === 'scroll' ? listeners.get(listener) ?? listener : listener, options);
  });
  await mount();
  for (const period of ['7d', 'today', '30d', '24h', '7d', '24h', '30d', 'today']) {
    await select(period);
    scrollCalls = 0;
    host.dispatchEvent(new Event('scroll'));
    await flush();
    expect(scrollCalls, `scroll callbacks after selecting ${period}`).toBe(period.endsWith('d') ? 2 : 0);
  }
});
