import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import LivePage from '../../pvyieldlens/frontend/src/LivePage.vue';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';
import type { Snapshot } from '../../pvyieldlens/frontend/src/models';

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
  const props = reactive({ active: true, configuration: null, snapshot: structuredClone(reading),
    language: 'en' as const, theme: 'light' as const, displayTimezone: 'UTC', seriesError: null,
    range: { start: 9400, end: 10000 }, points: [{ at: 10000, actual_power_w: 4500 }] });
  const host = document.createElement('div');
  document.body.append(host);
  const app = createApp({ render: () => h(LivePage, props) });
  app.mount(host);
  cleanup.push(() => { app.unmount(); host.remove(); });
  return { props, host, sourceAge: () => host.querySelector('#source-rows td:last-child')?.textContent };
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(10000000);
  useI18n().setLanguage('en');
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(260);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
});
afterEach(() => { cleanup.splice(0).forEach(dispose => dispose()); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('updates_source_age_without_requests_or_chart_rebuilds', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');
  const { host, sourceAge } = mount();
  await nextTick();
  const originalSvg = host.querySelector('#live-chart svg');
  expect(originalSvg).not.toBeNull();
  const requestCountBefore = fetchSpy.mock.calls.length;
  expect(sourceAge()).toBe('Just now');
  await vi.advanceTimersByTimeAsync(1000);
  expect(sourceAge()).toBe('1 s');
  await vi.advanceTimersByTimeAsync(1000);
  expect(sourceAge()).toBe('2 s');
  expect(fetchSpy).toHaveBeenCalledTimes(requestCountBefore);
  expect(host.querySelector('#live-chart svg')).toBe(originalSvg);
});

it.each([[999, 'Just now'], [1000, '1 s'], [-1000, 'Just now']])('uses floored elapsed age at %i milliseconds', async (elapsed, expected) => {
  vi.setSystemTime(10000000 + elapsed);
  const { sourceAge } = mount();
  expect(sourceAge()).toBe(expected);
});

it('updates immediately for a new report and localizes just now', async () => {
  const { props, sourceAge } = mount();
  await vi.advanceTimersByTimeAsync(3000);
  props.snapshot = { ...props.snapshot, sources: [{ ...props.snapshot.sources[0], reported_at: 10003 }] };
  await nextTick();
  expect(sourceAge()).toBe('Just now');
  expect(props.snapshot.sources[0].valid).toBe(true);
  useI18n().setLanguage('zh');
  await nextTick();
  expect(sourceAge()).toBe('刚刚');
});

it('stops inactive and hidden timers, refreshes immediately on return, and cleans up on unmount', async () => {
  const { props, sourceAge } = mount();
  props.active = false;
  await nextTick();
  expect(vi.getTimerCount()).toBe(0);
  vi.setSystemTime(10012000);
  props.active = true;
  await nextTick();
  expect(sourceAge()).toBe('12 s');
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  document.dispatchEvent(new Event('visibilitychange'));
  expect(vi.getTimerCount()).toBe(0);
  vi.setSystemTime(10022000);
  hidden.mockReturnValue(false);
  document.dispatchEvent(new Event('visibilitychange'));
  await nextTick();
  expect(sourceAge()).toBe('22 s');
  cleanup.splice(0).forEach(dispose => dispose());
  expect(vi.getTimerCount()).toBe(0);
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
