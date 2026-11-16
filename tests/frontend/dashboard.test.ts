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
const history = (end = 10000, step = 5) => ({ configured: true, recovering: false,
  range: { start: end - 600, end }, step_seconds: step,
  context: { revision: 1, settings: configuration.settings! },
  points: Array.from({ length: 600 / step + 1 }, (_, index) => ({ at: end - 600 + index * step, ...snapshot.realtime! })),
});
const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200 });
function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>(done => { resolve = done; });
  return { promise, resolve };
}
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
  useI18n().setLanguage('en');
  vi.stubGlobal('fetch', vi.fn(async (path: string) => response(path.endsWith('config') ? configuration : path.endsWith('live-history') ? { ...history(), points: [] } : {
    ...snapshot, calculated_at: Date.now() / 1000,
    realtime: Date.now() / 1000 % 2 === 1 ? null : snapshot.realtime,
  })));
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

it('keeps all 601 one-second endpoints and rolls exactly ten minutes at slow polling rates', async () => {
  const { dashboard } = start();
  await flushPromises();
  await vi.advanceTimersByTimeAsync(601000);
  expect(dashboard.livePoints.value).toHaveLength(601);
  expect(dashboard.livePoints.value[0].at).toBe(10001);
  expect(dashboard.livePoints.value[0].window).toBeUndefined();
  dashboard.acceptConfiguration({ ...configuration, settings: { ...configuration.settings!, update_seconds: 60 } });
  await vi.advanceTimersByTimeAsync(601000);
  expect(dashboard.livePoints.value.every(point => point.at >= Date.now() / 1000 - 600)).toBe(true);
  expect(dashboard.livePoints.value.length).toBeGreaterThan(1);
  expect(dashboard.liveRange.value.end - dashboard.liveRange.value.start).toBe(600);
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
    path.endsWith('live-history') ? Promise.resolve(response({ ...history(), points: [] })) :
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

it('loads_ten_minutes_before_accumulating', async () => {
  vi.stubGlobal('fetch', async (path: string) => response(path.endsWith('config') ? configuration : path.endsWith('live-history') ? history() : snapshot));
  const { dashboard } = start();
  await flushPromises();
  expect(dashboard.livePoints.value).toHaveLength(121);
  expect(dashboard.livePoints.value[0]).toMatchObject({ at: 9400, window: snapshot.realtime });
  expect(dashboard.liveRange.value).toEqual({ start: 9400, end: 10000 });
});

it('newer_snapshots_win_over_late_seed', async () => {
  const seed = deferred();
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) : path.endsWith('live-history') ? seed.promise : response({ ...snapshot,
    calculated_at: Date.now() / 1000, realtime: { ...snapshot.realtime!, actual_power: 4800 } }));
  const { dashboard } = start();
  await flushPromises();
  await vi.advanceTimersByTimeAsync(2000);
  seed.resolve(response(history()));
  await flushPromises();
  const points = dashboard.livePoints.value;
  expect(points.filter(point => point.at === 10000)).toHaveLength(1);
  expect(points.find(point => point.at === 10000)?.actual_power).toBe(4800);
  expect(points.at(-1)?.at).toBe(10002);
  expect(points.every(point => point.at >= 9402)).toBe(true);
  expect(dashboard.snapshot.value?.realtime?.actual_power).toBe(4800);
});

it('rejects_obsolete_monitoring_context', async () => {
  const seeds = [deferred(), deferred()];
  const snapshots = [deferred(), deferred()];
  let seedIndex = 0, snapshotIndex = 0;
  vi.stubGlobal('fetch', (path: string) => path.endsWith('config') ? Promise.resolve(response(configuration)) :
    path.endsWith('live-history') ? seeds[seedIndex++].promise : snapshots[snapshotIndex++].promise);
  const { dashboard } = start();
  await flushPromises();
  dashboard.acceptSavedConfiguration({ ...configuration, monitoring_changed: true,
    settings: { ...configuration.settings!, rated_power_w: 6000 } });
  snapshots[0].resolve(response(snapshot));
  seeds[0].resolve(response(history()));
  await flushPromises();
  expect(dashboard.livePoints.value).toEqual([]);
  expect(dashboard.snapshot.value).toBeNull();
  seeds[1].resolve(response({ ...history(), context: { revision: 2, settings: { ...configuration.settings!, rated_power_w: 6000 } }, points: [] }));
  await flushPromises();
  await vi.advanceTimersByTimeAsync(1000);
  snapshots[1].resolve(response({ ...snapshot, revision: 2, realtime: { ...snapshot.realtime!, actual_power: 5400 } }));
  await flushPromises();
  expect(dashboard.snapshot.value?.realtime?.actual_power).toBe(5400);
  expect(dashboard.livePoints.value).toHaveLength(1);
});

it('reseeds a higher polling revision while connected and keeps only raw updates from that context', async () => {
  const currentSeed = deferred();
  let revision = 1;
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) :
    path.endsWith('live-history') ? (revision === 1 ? response(history()) : currentSeed.promise) :
    response({ ...snapshot, revision, calculated_at: Date.now() / 1000,
      realtime: { ...snapshot.realtime!, actual_power: revision === 1 ? 4500 : 5400 } }));
  const { dashboard } = start();
  await flushPromises();
  expect(dashboard.livePoints.value).toHaveLength(121);
  revision = 2;
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.snapshot.value).toMatchObject({ connected: true, revision: 2 });
  expect(dashboard.livePoints.value.map(point => [point.at, point.actual_power])).toEqual([[10001, 5400]]);
  await vi.advanceTimersByTimeAsync(1000);
  currentSeed.resolve(response({ ...history(10001), context: { revision: 2,
    settings: { ...configuration.settings!, rated_power_w: 6000 } },
    points: [9999, 10001].map(at => ({ at, ...snapshot.realtime!, actual_power: 5200 })) }));
  await flushPromises();
  expect(dashboard.configuration.value?.settings?.rated_power_w).toBe(6000);
  expect(dashboard.livePoints.value.map(point => [point.at, point.actual_power])).toEqual([[9999, 5200], [10001, 5400], [10002, 5400]]);
  expect(dashboard.snapshot.value).toMatchObject({ revision: 2, calculated_at: 10002 });
});

it('rejects an old in-flight seed after a higher polling revision initiates a new context', async () => {
  const seeds = [deferred(), deferred()];
  let revision = 1, seedCalls = 0;
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) :
    path.endsWith('live-history') ? seeds[seedCalls++].promise : response({ ...snapshot, revision,
      calculated_at: Date.now() / 1000, realtime: { ...snapshot.realtime!, actual_power: revision === 1 ? 4500 : 5400 } }));
  const { dashboard } = start();
  await flushPromises();
  revision = 2;
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.livePoints.value.map(point => [point.at, point.actual_power])).toEqual([[10001, 5400]]);
  expect(seedCalls).toBe(2);
  seeds[0].resolve(response(history()));
  await flushPromises();
  expect(dashboard.livePoints.value.map(point => [point.at, point.actual_power])).toEqual([[10001, 5400]]);
  expect(dashboard.snapshot.value?.revision).toBe(2);
  seeds[1].resolve(response({ ...history(10001), context: { revision: 2,
    settings: { ...configuration.settings!, realtime_window_seconds: 120 } }, points: [] }));
  await flushPromises();
  expect(dashboard.configuration.value?.settings?.realtime_window_seconds).toBe(120);
  expect(dashboard.livePoints.value.map(point => [point.at, point.actual_power])).toEqual([[10001, 5400]]);
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.snapshot.value).toMatchObject({ connected: true, revision: 2, calculated_at: 10002 });
});

it('rejects a seed revision older than the accepted snapshot and adopts current seed settings', async () => {
  const seed = deferred();
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) : path.endsWith('live-history') ? seed.promise : response({ ...snapshot, revision: 3 }));
  const { dashboard } = start();
  await flushPromises();
  seed.resolve(response(history()));
  await flushPromises();
  expect(dashboard.livePoints.value).toHaveLength(1);
  expect(dashboard.configuration.value?.settings?.rated_power_w).toBe(5000);
  vi.stubGlobal('fetch', async (path: string) => response(path.endsWith('live-history') ? { ...history(), context: {
    revision: 3, settings: { ...configuration.settings!, rated_power_w: 6100 } } } : { ...snapshot, revision: 3 }));
  vi.setSystemTime(10010000);
  document.dispatchEvent(new Event('visibilitychange'));
  await flushPromises();
  expect(dashboard.configuration.value?.settings?.rated_power_w).toBe(6100);
});

it.each([
  { revision: 2, settings: { ...configuration.settings!, rated_power_w: 6000 } },
  { revision: 1, settings: { ...configuration.settings!, realtime_window_seconds: 120 } },
])('replaces incompatible accepted points and rejects a late snapshot when seed adopts $settings', async (adopted) => {
  const nextSeed = deferred();
  const oldPoll = deferred();
  let seedCalls = 0, pollCalls = 0;
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) : path.endsWith('live-history') ?
    (++seedCalls === 1 ? response(history()) : nextSeed.promise) :
    (++pollCalls === 1 ? response({ ...snapshot, realtime: { ...snapshot.realtime!, actual_power: 4800 } }) : oldPoll.promise));
  const { dashboard } = start();
  await flushPromises();
  expect(dashboard.livePoints.value.find(point => point.at === 10000)?.actual_power).toBe(4800);
  await vi.advanceTimersByTimeAsync(1000);
  vi.setSystemTime(10004000);
  document.dispatchEvent(new Event('visibilitychange'));
  const regenerated = { ...history(), context: adopted,
    points: [{ at: 10000, ...snapshot.realtime!, start: 10000 - adopted.settings.realtime_window_seconds, actual_power: 4200 }] };
  nextSeed.resolve(response(regenerated));
  await flushPromises();
  expect(dashboard.livePoints.value).toHaveLength(1);
  expect(dashboard.livePoints.value[0]).toMatchObject({ at: 10000, actual_power: 4200, window: regenerated.points[0] });
  expect(dashboard.configuration.value?.settings).toEqual(adopted.settings);
  expect(dashboard.snapshot.value).toBeNull();
  oldPoll.resolve(response({ ...snapshot, calculated_at: 10004, realtime: { ...snapshot.realtime!, actual_power: 4900 } }));
  await flushPromises();
  expect(dashboard.snapshot.value).toBeNull();
  expect(dashboard.livePoints.value).toHaveLength(1);
  expect(dashboard.livePoints.value[0].actual_power).toBe(4200);
});

it('reseeds_after_resume_without_losing_live_updates', async () => {
  const resumed = deferred();
  let calls = 0;
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) : path.endsWith('live-history') ?
    (++calls === 1 ? response(history()) : resumed.promise) : response({ ...snapshot, calculated_at: Date.now() / 1000 }));
  const { dashboard } = start();
  await flushPromises();
  vi.setSystemTime(10020000);
  document.dispatchEvent(new Event('visibilitychange'));
  document.dispatchEvent(new Event('visibilitychange'));
  await vi.advanceTimersByTimeAsync(1000);
  resumed.resolve(response(history(10020)));
  await flushPromises();
  expect(dashboard.livePoints.value.at(-1)?.at).toBe(10021);
  expect(dashboard.livePoints.value[0].at).toBe(9425);
  expect(dashboard.liveRange.value).toEqual({ start: 9421, end: 10021 });
  expect(calls).toBe(2);
});

it.each(['failed', 'pending'])('keeps a resume break through duplicate snapshots while the seed is %s, then fills it', async (outcome) => {
  const pending = deferred();
  let seeds = 0, calculatedAt = 10000;
  vi.stubGlobal('fetch', async (path: string) => {
    if (path.endsWith('config')) return response(configuration);
    if (path.endsWith('live-history')) {
      seeds++;
      if (seeds === 2) return outcome === 'pending' ? pending.promise : new Response('{}', { status: 503 });
      return response(history(Date.now() / 1000, 1));
    }
    return response({ ...snapshot, calculated_at: calculatedAt });
  });
  const { dashboard } = start();
  await flushPromises();
  calculatedAt = 10020;
  vi.setSystemTime(10020000);
  document.dispatchEvent(new Event('visibilitychange'));
  await flushPromises();
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.livePoints.value.find(point => point.at === 10020)?.breakBefore).toBe(true);
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.livePoints.value.find(point => point.at === 10020)?.breakBefore).toBe(true);
  if (outcome === 'pending') pending.resolve(response(history(10022, 1)));
  else {
    expect(dashboard.liveHistoryError.value).toBe('live_history_error');
    vi.setSystemTime(10030000);
    document.dispatchEvent(new Event('visibilitychange'));
  }
  await flushPromises();
  expect(dashboard.livePoints.value.find(point => point.at === 10020)?.breakBefore).toBe(false);
  expect(dashboard.liveHistoryError.value).toBeNull();
});

it('keeps snapshots and a real gap when seed and snapshot requests fail, then retries on resume', async () => {
  let fail = false;
  vi.stubGlobal('fetch', async (path: string) => {
    if (path.endsWith('config')) return response(configuration);
    if (path.endsWith('live-history') || fail) throw new TypeError('Offline');
    return response(snapshot);
  });
  const { dashboard } = start();
  await flushPromises();
  expect(dashboard.liveHistoryError.value).toBe('live_history_error');
  expect(dashboard.snapshot.value?.realtime?.actual_power).toBe(4500);
  fail = true;
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.livePoints.value.at(-1)).toEqual({ at: 10001, estimated_power: null, actual_power: null });
  expect(dashboard.liveRange.value).toEqual({ start: 9401, end: 10001 });
  vi.stubGlobal('fetch', async (path: string) => response(path.endsWith('live-history') ? history(10010) : { ...snapshot, calculated_at: 10010 }));
  vi.setSystemTime(10010000);
  document.dispatchEvent(new Event('visibilitychange'));
  await flushPromises();
  expect(dashboard.liveHistoryError.value).toBeNull();
  expect(dashboard.livePoints.value.length).toBeGreaterThan(100);
});

it('retains a recovery refresh while the initial seed is in flight and coalesces triggers', async () => {
  const seeds = [deferred(), deferred()];
  let calls = 0;
  let connected = false;
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) : path.endsWith('live-history') ? seeds[calls++].promise :
    response({ ...snapshot, connected, realtime: connected ? snapshot.realtime : null, calculated_at: Date.now() / 1000 }));
  const { dashboard } = start();
  await flushPromises();
  connected = true;
  await vi.advanceTimersByTimeAsync(1000);
  seeds[0].resolve(response({ ...history(), recovering: true, points: [] }));
  await flushPromises();
  expect(calls).toBe(2);
  seeds[1].resolve(response(history(10001)));
  await flushPromises();
  expect(dashboard.livePoints.value.length).toBeGreaterThan(100);
  await vi.advanceTimersByTimeAsync(3000);
  expect(calls).toBe(2);
});

it('reseeds after a failed browser connection recovers without requiring an HA state change', async () => {
  let offline = false;
  let calls = 0;
  vi.stubGlobal('fetch', async (path: string) => {
    if (path.endsWith('config')) return response(configuration);
    if (path.endsWith('live-history')) { calls++; return response(history(Date.now() / 1000)); }
    if (offline) throw new TypeError('Offline');
    return response({ ...snapshot, calculated_at: Date.now() / 1000 });
  });
  const { dashboard } = start();
  await flushPromises();
  offline = true;
  await vi.advanceTimersByTimeAsync(1000);
  offline = false;
  await vi.advanceTimersByTimeAsync(1000);
  expect(dashboard.livePoints.value.find(point => point.at === 10001)?.actual_power).toBeNull();
  expect(calls).toBe(2);
  expect(dashboard.liveHistoryError.value).toBeNull();
});

it('retries a recovering seed once a connected snapshot is ready and ignores responses after disposal', async () => {
  const pending = deferred();
  let calls = 0;
  vi.stubGlobal('fetch', async (path: string) => path.endsWith('config') ? response(configuration) : path.endsWith('live-history') ?
    (++calls === 1 ? response({ ...history(), recovering: true }) : pending.promise) : response(snapshot));
  const { dashboard } = start();
  await flushPromises();
  await vi.advanceTimersByTimeAsync(1000);
  expect(calls).toBe(2);
  const points = dashboard.livePoints.value;
  scopes.splice(0).forEach(scope => scope.stop());
  pending.resolve(response(history(10001)));
  await flushPromises();
  expect(dashboard.livePoints.value).toBe(points);
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
  vi.stubGlobal('fetch', async (path: string) => response(path.endsWith('config') ? configuration : path.endsWith('live-history') ? { ...history(), points: [] } : { ...snapshot, timezone: 'Asia/Shanghai' }));
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
  expect(dashboard.livePoints.value.slice(0, readings.length)).toEqual(readings);
  expect(dashboard.livePoints.value.at(-1)).toMatchObject({ at: 10001, actual_power: null });
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
