import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { effectScope, ref } from 'vue';
import { setImmediate } from 'node:timers';
import { useDashboard } from '../../pvyieldlens/frontend/src/dashboard';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';
import { api, ApiError } from '../../pvyieldlens/frontend/src/api';
import type { Configuration, Snapshot } from '../../pvyieldlens/frontend/src/models';

const configuration: Configuration = {
  settings: { rated_power_w: 5000, temperature_coefficient_pct_per_c: -0.35,
    power_entity: 'sensor.power', temperature_entity: 'sensor.temp', irradiance_entity: 'sensor.sun',
    interval_minutes: 1, realtime_window_seconds: 60, update_seconds: 1,
    power_max_age_seconds: 300, temperature_max_age_seconds: 900, irradiance_max_age_seconds: 300, timezone: 'UTC' },
  forecast_settings: { enabled: false, tilt_deg: null, azimuth_deg: null, noct_c: 45 },
  location: null, mode: 'docker', connection: { url: 'http://ha', token_set: true },
};
const snapshot: Snapshot = {
  configured: true, connected: true, error: null, history_available: true, calculated_at: 10000,
  revision: 1, statistics: null, realtime: {
    start: 9940, end: 10000, valid_seconds: 60, estimated_energy_wh: 83.33333333333333,
    actual_energy_wh: 75, estimated_power: 5000, actual_power: 4500, pr: 90, optimizable_power: 500,
    coverage_percent: 100, quality: 'complete', reason: null,
  },
  energy: { daily_kwh: 0, total_kwh: 0, daily_complete: true, day: '2026-11-14', timezone: 'UTC',
    daily_valid_seconds: 0, total_valid_seconds: 0, settled_until: 10000 }, sources: [], timezone: 'UTC', location: null,
  forecast: { status: 'disabled', refreshing: false, fetched_at: null, calculated_at: 10000, last_error: null,
    timezone: null, today: null, remaining_today: null, tomorrow: null, seven_days: null },
};
const scopes: ReturnType<typeof effectScope>[] = [];
const flushPromises = () => new Promise<void>(resolve => setImmediate(resolve));
function start() {
  let dashboard!: ReturnType<typeof useDashboard>;
  const page = ref('live');
  const theme = ref('light');
  const scope = effectScope();
  scopes.push(scope);
  scope.run(() => { dashboard = useDashboard(); });
  return { get dashboard() { return dashboard; }, page, theme };
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(10000 * 1000);
  vi.stubGlobal('fetch', vi.fn(async (path: string) => new Response(JSON.stringify(path.endsWith('config') ? configuration : {
    ...snapshot, calculated_at: Date.now() / 1000,
    realtime: Date.now() / 1000 % 2 === 1 ? null : snapshot.realtime,
  }), { status: 200 })));
});
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); document.body.replaceChildren(); });

it('continues snapshot polling in Settings and stops on app disposal', async () => {
  const { dashboard, page } = start();
  await flushPromises();
  page.value = 'settings';
  await vi.advanceTimersByTimeAsync(2000);
  expect(dashboard.snapshot.value?.calculated_at).toBe(10002);
  expect(dashboard.livePoints.value.map(point => point.at)).toEqual([10000, 10001, 10002]);
  scopes.splice(0).forEach(scope => scope.stop());
  await vi.advanceTimersByTimeAsync(2000);
  expect(dashboard.snapshot.value?.calculated_at).toBe(10002);
});

it('keeps null gaps, at most 600 readings, and only the last 1800 seconds', async () => {
  const { dashboard } = start();
  await flushPromises();
  await vi.advanceTimersByTimeAsync(601000);
  expect(dashboard.livePoints.value).toHaveLength(600);
  expect(dashboard.livePoints.value[0]).toEqual({ at: 10002, estimated_power: 5000, actual_power: 4500, window: snapshot.realtime });
  expect(dashboard.livePoints.value[1]).toEqual({ at: 10003, estimated_power: null, actual_power: null });
  dashboard.acceptConfiguration({ ...configuration, settings: { ...configuration.settings!, update_seconds: 60 } });
  await vi.advanceTimersByTimeAsync(1801000);
  expect(dashboard.livePoints.value.every(point => point.at >= Date.now() / 1000 - 1800)).toBe(true);
  expect(dashboard.livePoints.value.length).toBeGreaterThan(1);
});

it('preserves readings across forecast-only saves, language and theme changes, and resets for monitoring saves', async () => {
  const { dashboard, theme } = start();
  await flushPromises();
  await vi.advanceTimersByTimeAsync(2000);
  const initial = [...dashboard.livePoints.value];
  expect(initial.map(point => point.actual_power)).toEqual([4500, null, 4500]);
  dashboard.acceptSavedConfiguration({ ...configuration, monitoring_changed: false });
  useI18n().setLanguage('de');
  theme.value = 'dark';
  expect(dashboard.livePoints.value).toEqual(initial);
  dashboard.acceptSavedConfiguration({ ...configuration, monitoring_changed: true });
  expect(dashboard.livePoints.value).toEqual([]);
});

it('waits for a snapshot to complete before starting the configured polling delay', async () => {
  const pending: ((response: Response) => void)[] = [];
  vi.stubGlobal('fetch', (path: string) => path.endsWith('config') ? Promise.resolve(new Response(JSON.stringify(configuration))) :
    new Promise<Response>(resolve => pending.push(resolve)));
  const { dashboard } = start();
  await flushPromises();
  await vi.advanceTimersByTimeAsync(2000);
  expect(dashboard.snapshot.value).toBeNull();
  expect(pending).toHaveLength(1);
  pending[0](new Response(JSON.stringify({ ...snapshot, calculated_at: 10002 })));
  await flushPromises();
  await vi.advanceTimersByTimeAsync(999);
  expect(pending).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(pending).toHaveLength(2);
  pending[1](new Response(JSON.stringify({ ...snapshot, calculated_at: 10003 })));
  await flushPromises();
  expect(dashboard.livePoints.value.map(point => point.at)).toEqual([10002, 10003]);
});

it('shares concurrent configuration reads but fetches fresh configuration after completion', async () => {
  const first = api.getConfiguration();
  const concurrent = api.getConfiguration();
  expect(first).toBe(concurrent);
  expect((await first).settings?.rated_power_w).toBe(5000);
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ ...configuration,
    settings: { ...configuration.settings!, rated_power_w: 6000 } })));
  expect((await api.getConfiguration()).settings?.rated_power_w).toBe(6000);
});

it('preserves backend error codes and validated field paths at the API boundary', async () => {
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ error: 'invalid_configuration',
    fields: ['settings.rated_power_w', 4] }), { status: 422 }));
  const failure = await api.saveConfiguration({ settings: configuration.settings! }).catch(error => error as unknown);
  expect(failure).toBeInstanceOf(ApiError);
  expect(failure).toMatchObject({ code: 'invalid_configuration', fields: ['settings.rated_power_w'] });
});

it('resolves viewer time on configuration, completed failed polls and foreground without extra requests', async () => {
  const ha = document.createElement('home-assistant');
  const preference = { time_zone: 'local' };
  Object.assign(ha, { hass: { locale: preference } });
  const frame = document.createElement('iframe');
  document.body.append(frame);
  frame.contentDocument!.body.append(ha);
  vi.spyOn(window, 'parent', 'get').mockReturnValue(frame.contentWindow!);
  const Native = Intl.DateTimeFormat;
  vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(function (locales, options) {
    return new Native(locales, { ...options, timeZone: options?.timeZone ?? 'America/Los_Angeles' });
  });
  vi.stubGlobal('fetch', async (path: string) => new Response(JSON.stringify(path.endsWith('config') ? configuration : { ...snapshot, timezone: 'Asia/Shanghai' })));
  const { dashboard } = start();
  await flushPromises();
  dashboard.acceptConfiguration({ ...configuration, mode: 'app',
    settings: { ...configuration.settings!, timezone: 'Asia/Shanghai' } });
  expect(dashboard.displayTimezone?.value).toBe('America/Los_Angeles');
  const readings = dashboard.livePoints.value;
  const home = dashboard.configuration.value!.settings;
  preference.time_zone = 'server';
  const requests = vi.fn(async () => { throw new TypeError('Offline'); });
  vi.stubGlobal('fetch', requests);
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.displayTimezone?.value).toBe('Asia/Shanghai');
  expect(dashboard.configuration.value!.settings).toBe(home);
  expect(dashboard.livePoints.value).toBe(readings);
  expect(requests).toHaveBeenCalledTimes(1);
  preference.time_zone = 'local';
  document.dispatchEvent(new Event('visibilitychange'));
  expect(dashboard.displayTimezone?.value).toBe('America/Los_Angeles');
  expect(requests).toHaveBeenCalledTimes(1);
  scopes.splice(0).forEach(scope => scope.stop());
  preference.time_zone = 'server';
  document.dispatchEvent(new Event('visibilitychange'));
  expect(dashboard.displayTimezone?.value).toBe('America/Los_Angeles');
  frame.remove();
});

it('uses the latest household snapshot zone and keeps early app fallback in household time', async () => {
  const { dashboard } = start();
  await flushPromises();
  dashboard.acceptConfiguration({ ...configuration, mode: 'app',
    settings: { ...configuration.settings!, timezone: 'Asia/Shanghai' } });
  expect(dashboard.displayTimezone?.value).toBe('UTC');
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ ...snapshot, timezone: 'Asia/Shanghai' })));
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.displayTimezone?.value).toBe('Asia/Shanghai');
});
