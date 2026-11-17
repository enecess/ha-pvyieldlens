import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import { setImmediate } from 'node:timers';
import LivePage from '../../pvyieldlens/frontend/src/LivePage.vue';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';
import type { Configuration, Snapshot } from '../../pvyieldlens/frontend/src/models';

const configuration: Configuration = {
  monitoring_settings: { total_max_power_at_stc_w: 5000, pmax_temperature_coefficient_pct_per_c: -0.35,
    actual_power_entity: 'sensor.power', module_temperature_entity: 'sensor.temp', irradiance_entity: 'sensor.sun',
    settlement_interval_minutes: 1, live_window_seconds: 60, update_interval_seconds: 60,
    actual_power_max_age_seconds: 300, module_temperature_max_age_seconds: 900, irradiance_max_age_seconds: 300, home_timezone: 'UTC' },
  forecast_settings: { enabled: false, tilt_deg: null, azimuth_deg: null, noct_c: 45, pr_history_days: 14 },
  location: null, mode: 'docker', connection: { url: 'http://ha', token_set: true },
};
const diagnostics = (observedAt = 10000, reportedAt: number | null = 10000, state = '4.5') => ({
  observed_at: observedAt,
  sources: [{ entity_id: 'sensor.power', state, unit: 'kW', reported_at: reportedAt, valid: true },
    { entity_id: 'sensor.temp', state: '40', unit: '°C', reported_at: reportedAt, valid: true },
    { entity_id: 'sensor.sun', state: 'unavailable', unit: null, reported_at: null, valid: false }],
});
const response = (payload: ReturnType<typeof diagnostics>) => new Response(JSON.stringify(payload));
const flush = () => new Promise<void>(resolve => setImmediate(resolve));
function deferred() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>(done => { resolve = done; });
  return { promise, resolve };
}

const cleanup: (() => void)[] = [];
const reading: Snapshot = {
  configured: true, connected: true, error: null, history_available: true, calculated_at: 10000, revision: 1,
  latest_settled_window: null, live_window: null,
  energy_totals: { estimated_energy_today_kwh: 0, estimated_energy_lifetime_kwh: 0, today_allocation_complete: true, day: '2026-11-14', home_timezone: 'UTC',
    today_valid_seconds: 0, lifetime_valid_seconds: 0, settled_until: 10000 },
  sources: [{ entity_id: 'sensor.power', state: '4500', unit: 'W', reported_at: 10000, valid: true }],
  home_timezone: 'UTC', location: null,
  forecast: { status: 'disabled', refreshing: false, fetched_at: null, calculated_at: 10000, last_error: null,
    home_timezone: null, today: null, remaining_today: null, tomorrow: null, seven_days: null },
};
function mount() {
  const props = reactive({ active: true, configuration: structuredClone(configuration) as Configuration | null, snapshot: structuredClone(reading),
    language: 'en' as const, theme: 'light' as const, displayTimezone: 'UTC', seriesError: null,
    range: { start: 9400, end: 10000 }, points: [{ at: 10000, actual_power_w: 4500 }] });
  const host = document.createElement('div');
  document.body.append(host);
  const app = createApp({ render: () => h(LivePage, props) });
  app.mount(host);
  cleanup.push(() => { app.unmount(); host.remove(); });
  const details = host.querySelector<HTMLDetailsElement>('#source-diagnostics')!;
  const expand = async (open = true) => { details.open = open; details.dispatchEvent(new Event('toggle')); await flush(); };
  return { props, host, expand, sourceAge: () => host.querySelector('#source-rows td:last-child')?.textContent };
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date', 'performance'] });
  vi.setSystemTime(10000000);
  useI18n().setLanguage('en');
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(260);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.stubGlobal('fetch', vi.fn(async () => response(diagnostics())));
});
afterEach(() => { cleanup.splice(0).forEach(dispose => dispose()); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('refreshes an unchanged source report after one second without a snapshot or chart rebuild', async () => {
  const fetchSpy = vi.mocked(fetch).mockResolvedValueOnce(response(diagnostics(10000, 9990)))
    .mockResolvedValueOnce(response(diagnostics(10001, 10001)));
  const { host, sourceAge, expand, props } = mount();
  await expand();
  const originalSvg = host.querySelector('#live-chart svg');
  expect(originalSvg).not.toBeNull();
  expect(sourceAge()).toBe('10 s');
  expect(host.querySelector('#source-rows td:nth-child(2)')?.textContent).toBe('4.5 kW');
  await vi.advanceTimersByTimeAsync(1000);
  expect(sourceAge()).toBe('Just now');
  expect(fetchSpy).toHaveBeenCalledTimes(2);
  expect(fetchSpy.mock.calls.every(([path]) => path === 'api/source-diagnostics')).toBe(true);
  expect(fetchSpy.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
  expect(props.snapshot.calculated_at).toBe(10000);
  expect(props.snapshot.sources[0].reported_at).toBe(10000);
  expect(host.querySelector('#live-chart svg')).toBe(originalSvg);
});

it('uses HA time and monotonic elapsed seconds despite a different or changing browser wall clock', async () => {
  vi.setSystemTime(900000000000);
  vi.mocked(fetch).mockResolvedValueOnce(response(diagnostics(10000.75, 9998.5))).mockReturnValue(deferred().promise);
  const { sourceAge, expand } = mount();
  await expand();
  expect(sourceAge()).toBe('2 s');
  await vi.advanceTimersByTimeAsync(1000);
  expect(sourceAge()).toBe('3 s');
  vi.setSystemTime(1000);
  await vi.advanceTimersByTimeAsync(2000);
  expect(sourceAge()).toBe('5 s');
});

it('keeps diagnostic values and report times independent of snapshot updates and localizes just now', async () => {
  const { props, sourceAge, expand, host } = mount();
  await expand();
  props.snapshot = { ...props.snapshot, sources: [{ ...props.snapshot.sources[0], state: '8000', reported_at: 10 }] };
  await nextTick();
  expect(sourceAge()).toBe('Just now');
  expect(host.querySelector('#source-rows td:nth-child(2)')?.textContent).toBe('4.5 kW');
  expect(props.snapshot.sources[0].valid).toBe(true);
  useI18n().setLanguage('zh');
  await nextTick();
  expect(sourceAge()).toBe('刚刚');
});

it('requests only expanded, active, visible configured diagnostics and stops on unmount', async () => {
  const { props, expand } = mount();
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch).not.toHaveBeenCalled();
  props.configuration = null;
  await expand();
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch).not.toHaveBeenCalled();
  props.configuration = structuredClone(configuration);
  await flush();
  expect(fetch).toHaveBeenCalledTimes(1);
  await expand(false);
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch).toHaveBeenCalledTimes(1);
  await expand();
  expect(fetch).toHaveBeenCalledTimes(2);
  props.active = false;
  await flush();
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch).toHaveBeenCalledTimes(2);
  props.active = true;
  await flush();
  expect(fetch).toHaveBeenCalledTimes(3);
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  document.dispatchEvent(new Event('visibilitychange'));
  await flush();
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch).toHaveBeenCalledTimes(3);
  hidden.mockReturnValue(false);
  document.dispatchEvent(new Event('visibilitychange'));
  await flush();
  expect(fetch).toHaveBeenCalledTimes(4);
  cleanup.splice(0).forEach(dispose => dispose());
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetch).toHaveBeenCalledTimes(4);
  expect(vi.getTimerCount()).toBe(0);
});

it('keeps only one request in flight while a diagnostic read is pending', async () => {
  const pending = deferred();
  vi.mocked(fetch).mockReturnValueOnce(pending.promise);
  const { sourceAge, expand } = mount();
  await expand();
  await vi.advanceTimersByTimeAsync(5000);
  expect(fetch).toHaveBeenCalledTimes(1);
  pending.resolve(response(diagnostics()));
  await flush();
  expect(sourceAge()).toBe('Just now');
  await vi.advanceTimersByTimeAsync(999);
  expect(fetch).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it.each(['collapsed', 'inactive', 'hidden', 'source'] as const)('discards late replies from an old %s context', async context => {
  const pending = deferred();
  vi.mocked(fetch).mockReturnValueOnce(pending.promise).mockResolvedValue(response(diagnostics(10020, 10020, '6')));
  const { props, expand, host, sourceAge } = mount();
  await expand();
  const signal = vi.mocked(fetch).mock.calls[0]?.[1]?.signal;
  if (context === 'collapsed') await expand(false);
  if (context === 'inactive') props.active = false;
  const hidden = vi.spyOn(document, 'hidden', 'get');
  if (context === 'hidden') { hidden.mockReturnValue(true); document.dispatchEvent(new Event('visibilitychange')); }
  if (context === 'source') props.configuration!.monitoring_settings!.actual_power_entity = 'sensor.new_power';
  await flush();
  expect(signal?.aborted).toBe(true);
  if (context === 'collapsed') await expand();
  if (context === 'inactive') props.active = true;
  if (context === 'hidden') { hidden.mockReturnValue(false); document.dispatchEvent(new Event('visibilitychange')); }
  await flush();
  expect(sourceAge()).toBe('Just now');
  expect(host.querySelector('#source-rows td:nth-child(2)')?.textContent).toBe('6 kW');
  pending.resolve(response(diagnostics(10000, 9000, '1')));
  await flush();
  expect(sourceAge()).toBe('Just now');
  expect(host.querySelector('#source-rows td:nth-child(2)')?.textContent).toBe('6 kW');
});

it('retains and advances known ages after a failed refresh, shows an error, and recovers', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(response(diagnostics(10000, 9990)))
    .mockRejectedValueOnce(new TypeError('Network read failed'))
    .mockResolvedValueOnce(response(diagnostics(10002, 10002)));
  const { sourceAge, expand, host } = mount();
  await expand();
  expect(sourceAge()).toBe('10 s');
  await vi.advanceTimersByTimeAsync(1000);
  expect(sourceAge()).toBe('11 s');
  expect(host.querySelector('#source-diagnostics [role=status]')?.textContent).toContain('Cannot reach Home Assistant');
  await vi.advanceTimersByTimeAsync(1000);
  expect(sourceAge()).toBe('Just now');
  expect(host.querySelector('#source-diagnostics [role=status]')).toBeNull();
});

it('renders unavailable ages for missing timestamps while preserving raw units and valid zero', async () => {
  vi.mocked(fetch).mockResolvedValue(response(diagnostics(10000, null, '0')));
  const { sourceAge, expand, host } = mount();
  await expand();
  expect(sourceAge()).toBe('—');
  expect(host.querySelector('#source-rows td:nth-child(2)')?.textContent).toBe('0 kW');
  expect(host.querySelector('#source-rows tr:last-child td:nth-child(2)')?.textContent).toBe('Unavailable');
  expect(host.textContent).not.toMatch(/undefined|NaN/);
});

it('shows the new live quantities with distinct missing and valid zero values', async () => {
  const { props, host } = mount();
  props.snapshot.live_window = { start: 9940, end: 10000, valid_seconds: 60,
    estimated_energy_wh: 62, actual_energy_wh: 55.8, estimated_power_w: 3720,
    actual_power_w: 3348, optimizable_power_w: 372, pr: 90,
    data_completeness_percent: 100, quality: 'complete', reason: null };
  await nextTick();
  expect(host.querySelector('#live-estimated')?.textContent).toBe('3,720');
  expect(host.querySelector('#live-actual')?.textContent).toBe('3,348');
  expect(host.querySelector('#live-optimizable-power')?.textContent).toBe('372');
  expect(host.textContent).toContain('Estimated power');
  expect(host.textContent).toContain('Optimizable power');
  props.snapshot.live_window = { ...props.snapshot.live_window, estimated_power_w: 0, actual_power_w: 0,
    optimizable_power_w: 0, pr: null, reason: 'zero_estimated_power' };
  await nextTick();
  expect(host.querySelector('#live-estimated')?.textContent).toBe('0');
  expect(host.querySelector('#live-pr')?.textContent).toBe('—');
  props.snapshot.live_window = null;
  await nextTick();
  expect(host.querySelector('#live-estimated')?.textContent).toBe('—');
  expect(host.textContent).not.toMatch(/undefined|NaN/);
});
