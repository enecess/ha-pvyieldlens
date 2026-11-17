import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import { setImmediate } from 'node:timers';
import HistoryPage from '../../pvyieldlens/frontend/src/HistoryPage.vue';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';
import type { Configuration, Snapshot } from '../../pvyieldlens/frontend/src/models';

const summary = { start: 1794326400, end: 1794326580, estimated_energy_kwh: 0.08,
  actual_energy_kwh: 0.09, pr: 112.5, data_completeness_percent: 60, valid_seconds: 180 };
const window = { revision: 1, start: 1794326400, end: 1794326580, valid_seconds: 180,
  estimated_energy_wh: 80, actual_energy_wh: 90, estimated_power_w: 1600, actual_power_w: 1800,
  pr: 112.5, optimizable_power_w: -200, data_completeness_percent: 60, quality: 'partial', reason: 'missing_data',
  source_start: 1794326280, source_end: 1794326580 };
const empty = { start: null, end: null, estimated_energy_kwh: null, actual_energy_kwh: null,
  pr: null, data_completeness_percent: null, valid_seconds: 0 };
const view = (period: string) => ({ windows: [window], summary, requested_range: { start: window.start, end: window.end },
  comparison: { summary: { ...summary, pr: 100 }, requested_range: { start: 1, end: 100 }, pr_change_pp: 12.5 },
  period, home_timezone: 'Asia/Shanghai', today: '2026-11-11', boundary_unavailable: false,
  days: period === '7d' || period === '30d' ? Array.from({ length: period === '7d' ? 7 : 30 }, (_, i) => ({
    day: new Date(Date.UTC(2026, 10, 11 - (period === '7d' ? 6 : 29) + i)).toISOString().slice(0, 10),
    start: window.start - 86400, end: window.end,
    summary: i === 1 ? { ...summary, estimated_energy_kwh: 0, actual_energy_kwh: 0, pr: null }
      : i === 3 ? { ...summary, pr: 80 } : empty,
    in_progress: i === (period === '7d' ? 6 : 29), boundary_unavailable: i === 2,
  })) : [] });
let host: HTMLDivElement;
let app: ReturnType<typeof createApp>;
let props: { active: boolean; configuration: Configuration; snapshot: Snapshot; language: 'en'; theme: 'light'; displayTimezone: string };
const flush = async () => { await new Promise<void>(resolve => setImmediate(resolve)); await nextTick(); await nextTick(); };
const click = async (selector: string) => { host.querySelector<HTMLElement>(selector)!.click(); await flush(); };
const select = async (period: string) => click('#history-range [data-value="' + period + '"]');
beforeEach(() => {
  useI18n().setLanguage('en');
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(600);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(220);
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(view(new URL(url, 'http://test/').searchParams.get('period') ?? '')))));
  props = reactive({ active: true, configuration: { monitoring_settings: { settlement_interval_minutes: 5, home_timezone: 'Asia/Shanghai' } } as Configuration,
    snapshot: { revision: 1, latest_settled_window: window, home_timezone: 'Asia/Shanghai', energy_totals: { day: '2026-11-11' } } as Snapshot,
    language: 'en', theme: 'light', displayTimezone: 'America/Los_Angeles' });
  host = document.createElement('div'); document.body.append(host);
});
const mount = async () => { app = createApp({ render: () => h(HistoryPage, props) }); app.mount(host); await flush(); };
afterEach(() => { app?.unmount(); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('defaults to Today with exactly three PR-focused cards and two charts', async () => {
  await mount();
  expect(fetch).toHaveBeenCalledWith('api/history?period=today&compare=true', expect.anything());
  expect([...host.querySelectorAll('.metric-label')].map(node => node.textContent)).toEqual([
    'PR in range', 'PR change from previous period', 'Estimated − actual energy']);
  expect(host.querySelector('#history-pr')?.textContent).toBe('112.5');
  expect(host.querySelector('#history-pr-change')?.textContent).toBe('+12.5');
  expect(host.querySelector('#history-energy-gap')?.textContent).toBe('-0.01');
  expect(host.querySelectorAll('.history-grid > article')).toHaveLength(2);
  expect(host.querySelectorAll('.reference-line')).toHaveLength(1);
  expect(host.querySelector('#history-home-timezone')?.textContent).toContain('Asia/Shanghai');
  expect(host.textContent).not.toMatch(/quality|completeness|included settled|cannot be allocated/i);
});

it('links both charts when switching daily and settlement modes and preserves selection through navigation', async () => {
  await mount(); await select('7d');
  expect(host.querySelectorAll('.daily-history-chart')).toHaveLength(2);
  expect(host.querySelector('#daily-energy-chart .daily-column')).not.toBeNull();
  useI18n().setLanguage('zh'); await flush();
  expect(host.querySelector('#history-aggregation')?.textContent).toContain('每天汇总');
  expect(host.querySelector('#history-aggregation')?.textContent).toContain('每 5 分钟');
  const requests = vi.mocked(fetch).mock.calls.length;
  await click('#history-aggregation [data-value=settlement]');
  expect(host.querySelectorAll('.daily-history-chart')).toHaveLength(0);
  expect(host.querySelectorAll('#history-chart svg, #pr-chart svg')).toHaveLength(2);
  expect(host.querySelector('#history-chart svg text')?.textContent).toBeTruthy();
  expect(host.querySelector('#history-chart svg')?.textContent).toContain('W');
  host.querySelector('#pr-chart .chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  await flush(); expect(host.querySelector('#pr-chart .chart-tooltip')?.textContent).toContain('112.5 %');
  expect(fetch).toHaveBeenCalledTimes(requests);
  props.active = false; await flush(); props.active = true; await flush();
  expect(host.querySelector('#history-aggregation [data-value=settlement]')?.getAttribute('aria-pressed')).toBe('true');
  expect(fetch).toHaveBeenCalledTimes(requests);
  await select('7d');
  expect(host.querySelectorAll('.daily-history-chart')).toHaveLength(2);
  await select('30d');
  expect(host.querySelectorAll('#daily-energy-chart .daily-column')).toHaveLength(30);
});

it('shows a placeholder when there is no comparable prior PR and keeps true zero energy', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...view('today'), comparison: null,
    summary: { ...empty, estimated_energy_kwh: 0, actual_energy_kwh: 0 } })));
  await mount();
  expect(host.querySelector('#history-pr-change')?.textContent).toBe('—');
  expect(host.querySelector('#history-pr')?.textContent).toBe('—');
  expect(host.querySelector('#history-energy-gap')?.textContent).toBe('0');
});

it('keeps daily empty slots, zero bars, PR gaps and removes tooltip quality and included-span copy', async () => {
  await mount(); await select('7d');
  expect(host.querySelector('#daily-energy-chart .daily-cutoff')?.textContent).toContain('Asia/Shanghai');
  expect(host.querySelectorAll('#daily-energy-chart .daily-column')).toHaveLength(7);
  expect(host.querySelectorAll('#daily-energy-chart .daily-bar[height="0"]')).toHaveLength(2);
  expect(host.querySelectorAll('#daily-pr-chart .daily-pr-point')).toHaveLength(1);
  const hit = host.querySelector('#daily-energy-chart .chart-hit-area')!;
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true })); await flush();
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('— kWh');
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); await flush();
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('0 kWh');
  expect(host.querySelector('.chart-tooltip')?.textContent).not.toMatch(/completeness|quality|included|allocated/i);
});

it('keeps_new_history_range_when_old_request_finishes', async () => {
  let resolve!: (value: Response) => void;
  vi.mocked(fetch).mockReturnValueOnce(new Promise<Response>(done => { resolve = done; }));
  await mount(); await select('7d');
  resolve(new Response(JSON.stringify({ ...view('today'), summary: { ...summary, pr: 1 } }))); await flush();
  expect(host.querySelector('#history-pr')?.textContent).toBe('112.5');
  expect(host.querySelector('#daily-energy-chart .daily-cutoff')?.textContent).toContain('Asia/Shanghai');
  expect(host.querySelectorAll('#daily-energy-chart .daily-column')).toHaveLength(7);
});

it('refreshes only on visible settlement, configuration and household-date changes', async () => {
  await mount(); expect(fetch).toHaveBeenCalledTimes(1);
  props.snapshot = { ...props.snapshot, calculated_at: 999 }; await flush(); expect(fetch).toHaveBeenCalledTimes(1);
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  document.dispatchEvent(new Event('visibilitychange'));
  props.snapshot = { ...props.snapshot, energy_totals: { ...props.snapshot.energy_totals, day: '2026-11-12' } };
  await flush(); expect(fetch).toHaveBeenCalledTimes(1);
  hidden.mockReturnValue(false); document.dispatchEvent(new Event('visibilitychange')); await flush();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('refreshes rolling history when an old whole window leaves the 24 hour range', async () => {
  const clock = vi.spyOn(Date, 'now').mockReturnValue((window.start + 86400) * 1000);
  await mount(); await select('24h');
  const requests = vi.mocked(fetch).mock.calls.length;
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...view('24h'), windows: [], summary: empty })));
  clock.mockReturnValue((window.start + 86401) * 1000);
  props.snapshot = { ...props.snapshot };
  await flush();
  expect(fetch).toHaveBeenCalledTimes(requests + 1);
  expect(host.querySelector('#history-chart .chart-empty')).not.toBeNull();
});
it('does not retry a failed rolling read on unrelated snapshot arrivals', async () => {
  const clock = vi.spyOn(Date, 'now').mockReturnValue((window.start + 86400) * 1000);
  await mount(); await select('24h');
  vi.mocked(fetch).mockRejectedValue(new TypeError('Offline'));
  clock.mockReturnValue((window.start + 86401) * 1000);
  props.snapshot = { ...props.snapshot }; await flush();
  const requests = vi.mocked(fetch).mock.calls.length;
  expect(host.querySelector('[role=status]')?.textContent).toBeTruthy();
  props.snapshot = { ...props.snapshot }; await flush();
  expect(fetch).toHaveBeenCalledTimes(requests);
  props.snapshot = { ...props.snapshot, revision: 2 }; await flush();
  expect(fetch).toHaveBeenCalledTimes(requests + 1);
});
