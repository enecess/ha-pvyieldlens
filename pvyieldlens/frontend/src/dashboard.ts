import { onScopeDispose, ref, shallowRef } from 'vue';
import { api, ApiError } from './api';
import { resolveDisplayTimezone } from './timezones';
import type { ChartPoint } from './charts';
import type { Configuration, ConfigurationSaveResult, Snapshot } from './models';

export function useDashboard() {
  const configuration = shallowRef<Configuration | null>(null);
  const snapshot = shallowRef<Snapshot | null>(null);
  const livePoints = shallowRef<ChartPoint[]>([]);
  const liveRange = ref({ start: Date.now() / 1000 - 600, end: Date.now() / 1000 });
  const liveSeriesError = ref<string | null>(null);
  const error = ref<string | null>(null);
  const displayTimezone = ref('UTC');
  let disposed = false;
  let timer: ReturnType<typeof setTimeout>;
  let context = {};
  let latestRevision = -1;
  let pendingContextSettings = false;
  let lastPollAt = Date.now() / 1000;
  let pendingSeed: { context: object; readyAtStart: boolean } | null = null;
  let refreshSeed = false;
  let recoveringSeed = false;
  const snapshotTimes = new Set<number>();

  function updateDisplayTimezone() {
    const timezone = resolveDisplayTimezone(window, configuration.value?.mode,
      snapshot.value?.home_timezone ?? configuration.value?.monitoring_settings?.home_timezone ?? configuration.value?.location?.home_timezone ?? '');
    if (timezone !== displayTimezone.value) displayTimezone.value = timezone;
  }
  function onVisibilityChange() {
    if (document.hidden) return;
    updateDisplayTimezone();
    if (Date.now() / 1000 - lastPollAt > 2 * (configuration.value?.monitoring_settings?.update_interval_seconds ?? 5)) void seed();
  }
  function trimPoints() {
    const end = Date.now() / 1000;
    liveRange.value = { start: end - 600, end };
    livePoints.value = livePoints.value.filter(point => point.at >= end - 600);
    snapshotTimes.forEach(at => { if (at < end - 600) snapshotTimes.delete(at); });
  }
  async function seed(recovery = false) {
    if (disposed || !configuration.value) return;
    if (pendingSeed?.context === context) {
      if (recovery) refreshSeed = true;
      return;
    }
    const request = { context, readyAtStart: Boolean(snapshot.value?.connected && snapshot.value.live_window) };
    pendingSeed = request;
    try {
      const result = await api.getLiveSeries();
      if (disposed || request.context !== context || pendingSeed !== request) return;
      if (result.context && result.context.revision < latestRevision) return;
      if (result.context && configuration.value) {
        if (latestRevision >= 0 && result.context.revision > latestRevision ||
          !pendingContextSettings && JSON.stringify(result.context.monitoring_settings) !== JSON.stringify(configuration.value.monitoring_settings)) {
          // A seed can discover a monitoring change made by another client.
          context = {};
          request.context = context;
          livePoints.value = [];
          snapshotTimes.clear();
          snapshot.value = null;
        }
        configuration.value = { ...configuration.value, monitoring_settings: result.context.monitoring_settings };
        latestRevision = result.context.revision;
        pendingContextSettings = false;
        updateDisplayTimezone();
      }
      const points = new Map(result.points.map(point => [point.at, { at: point.at,
        estimated_power_w: point.estimated_power_w, actual_power_w: point.actual_power_w, window: point } as ChartPoint]));
      livePoints.value.filter(point => snapshotTimes.has(point.at) || point.at > result.range.end)
        .forEach(point => points.set(point.at, point));
      livePoints.value = [...points.values()].sort((left, right) => left.at - right.at)
        .map((point, index, values) => ({ ...point,
          breakBefore: index > 0 && point.at - values[index - 1].at > 2 * (result.step_seconds ?? configuration.value?.monitoring_settings?.update_interval_seconds ?? 5) }));
      trimPoints();
      liveSeriesError.value = null;
      recoveringSeed = result.recovering;
      if (result.recovering && !request.readyAtStart && snapshot.value?.connected && snapshot.value.live_window) refreshSeed = true;
    } catch {
      if (!disposed && request.context === context && pendingSeed === request) liveSeriesError.value = 'live_series_load_failed';
    } finally {
      if (pendingSeed === request) {
        pendingSeed = null;
        if (refreshSeed && !disposed && request.context === context) {
          refreshSeed = false;
          recoveringSeed = false;
          void seed();
        }
      }
    }
  }
  function acceptConfiguration(value: Configuration) {
    configuration.value = value;
    updateDisplayTimezone();
  }
  function acceptSavedConfiguration(value: ConfigurationSaveResult) {
    acceptConfiguration(value);
    if (value.monitoring_changed) {
      context = {};
      latestRevision = -1;
      pendingContextSettings = false;
      livePoints.value = [];
      snapshot.value = null;
      snapshotTimes.clear();
      liveSeriesError.value = null;
      refreshSeed = false;
      recoveringSeed = false;
      trimPoints();
      void seed();
    }
  }
  async function loadConfiguration() {
    const value = await api.getConfiguration();
    if (!disposed) acceptConfiguration(value);
    return value;
  }
  async function poll() {
    const requestContext = context;
    try {
      const value = await api.getSnapshot();
      if (disposed || requestContext !== context || value.revision < latestRevision) return;
      const reconnected = (snapshot.value?.connected === false || error.value !== null) && value.connected;
      const revisionChanged = latestRevision >= 0 && value.revision > latestRevision;
      if (revisionChanged) {
        context = {};
        livePoints.value = [];
        snapshotTimes.clear();
        liveSeriesError.value = null;
        refreshSeed = false;
        recoveringSeed = false;
        // The new seed supplies settings for these newly accepted raw snapshots.
        pendingContextSettings = true;
      }
      latestRevision = value.revision;
      snapshot.value = value;
      error.value = null;
      if (configuration.value) configuration.value = { ...configuration.value, location: value.location };
      if (value.calculated_at !== null) {
        snapshotTimes.add(value.calculated_at);
        livePoints.value = [...livePoints.value.filter(point => point.at !== value.calculated_at), { at: value.calculated_at,
          estimated_power_w: value.live_window?.estimated_power_w ?? null, actual_power_w: value.live_window?.actual_power_w ?? null,
          ...(value.live_window ? { window: value.live_window } : {}),
          ...(livePoints.value.find(point => point.at === value.calculated_at)?.breakBefore ||
            Date.now() / 1000 - lastPollAt > 2 * (configuration.value?.monitoring_settings?.update_interval_seconds ?? 5) ? { breakBefore: true } : {}) }]
          .sort((left, right) => left.at - right.at);
      }
      if (revisionChanged || reconnected || recoveringSeed && value.connected && value.live_window) {
        recoveringSeed = false;
        void seed(true);
      }
    } catch (failure) {
      if (!disposed && requestContext === context) {
        error.value = failure instanceof ApiError ? failure.code : 'error';
        const at = Date.now() / 1000;
        snapshotTimes.add(at);
        livePoints.value = [...livePoints.value.filter(point => point.at !== at), { at, estimated_power_w: null, actual_power_w: null }];
      }
    } finally {
      if (!disposed) {
        trimPoints();
        lastPollAt = Date.now() / 1000;
        updateDisplayTimezone();
        timer = setTimeout(poll, (configuration.value?.monitoring_settings?.update_interval_seconds ?? 5) * 1000);
      }
    }
  }

  document.addEventListener('visibilitychange', onVisibilityChange);
  onScopeDispose(() => {
    disposed = true;
    clearTimeout(timer);
    document.removeEventListener('visibilitychange', onVisibilityChange);
  });
  void loadConfiguration().catch(failure => { if (!disposed) error.value = failure instanceof ApiError ? failure.code : 'error'; })
    .then(() => { if (!disposed) { void seed(); void poll(); } });
  return { configuration, snapshot, livePoints, liveRange, liveSeriesError, error, displayTimezone, acceptConfiguration, acceptSavedConfiguration };
}
