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
  const liveHistoryError = ref<string | null>(null);
  const error = ref<string | null>(null);
  const displayTimezone = ref('UTC');
  let disposed = false;
  let timer: ReturnType<typeof setTimeout>;
  let context = {};
  let latestRevision = -1;
  let lastPollAt = Date.now() / 1000;
  let pendingSeed: { context: object; readyAtStart: boolean } | null = null;
  let refreshSeed = false;
  let recoveringSeed = false;
  const snapshotTimes = new Set<number>();

  function updateDisplayTimezone() {
    const timezone = resolveDisplayTimezone(window, configuration.value?.mode,
      snapshot.value?.timezone ?? configuration.value?.settings?.timezone ?? configuration.value?.location?.timezone ?? '');
    if (timezone !== displayTimezone.value) displayTimezone.value = timezone;
  }
  function onVisibilityChange() {
    if (document.hidden) return;
    updateDisplayTimezone();
    if (Date.now() / 1000 - lastPollAt > 2 * (configuration.value?.settings?.update_seconds ?? 5)) void seed();
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
    const request = { context, readyAtStart: Boolean(snapshot.value?.connected && snapshot.value.realtime) };
    pendingSeed = request;
    try {
      const result = await api.getLiveHistory();
      if (disposed || request.context !== context || pendingSeed !== request) return;
      if (result.context && result.context.revision < latestRevision) return;
      if (result.context && configuration.value) {
        if (latestRevision >= 0 && result.context.revision > latestRevision ||
          JSON.stringify(result.context.settings) !== JSON.stringify(configuration.value.settings)) {
          // A seed can discover a monitoring change made by another client.
          context = {};
          request.context = context;
          livePoints.value = [];
          snapshotTimes.clear();
          snapshot.value = null;
        }
        configuration.value = { ...configuration.value, settings: result.context.settings };
        latestRevision = result.context.revision;
        updateDisplayTimezone();
      }
      const points = new Map(result.points.map(point => [point.at, { at: point.at,
        estimated_power: point.estimated_power, actual_power: point.actual_power, window: point } as ChartPoint]));
      livePoints.value.filter(point => snapshotTimes.has(point.at) || point.at > result.range.end)
        .forEach(point => points.set(point.at, point));
      livePoints.value = [...points.values()].sort((left, right) => left.at - right.at)
        .map((point, index, values) => ({ ...point,
          breakBefore: index > 0 && point.at - values[index - 1].at > 2 * (result.step_seconds ?? configuration.value?.settings?.update_seconds ?? 5) }));
      trimPoints();
      liveHistoryError.value = null;
      recoveringSeed = result.recovering;
      if (result.recovering && !request.readyAtStart && snapshot.value?.connected && snapshot.value.realtime) refreshSeed = true;
    } catch {
      if (!disposed && request.context === context && pendingSeed === request) liveHistoryError.value = 'live_history_error';
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
      livePoints.value = [];
      snapshot.value = null;
      snapshotTimes.clear();
      liveHistoryError.value = null;
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
      latestRevision = value.revision;
      snapshot.value = value;
      error.value = null;
      if (configuration.value) configuration.value = { ...configuration.value, location: value.location };
      if (value.calculated_at !== null) {
        snapshotTimes.add(value.calculated_at);
        livePoints.value = [...livePoints.value.filter(point => point.at !== value.calculated_at), { at: value.calculated_at,
          estimated_power: value.realtime?.estimated_power ?? null, actual_power: value.realtime?.actual_power ?? null,
          ...(value.realtime ? { window: value.realtime } : {}),
          ...(livePoints.value.find(point => point.at === value.calculated_at)?.breakBefore ||
            Date.now() / 1000 - lastPollAt > 2 * (configuration.value?.settings?.update_seconds ?? 5) ? { breakBefore: true } : {}) }]
          .sort((left, right) => left.at - right.at);
      }
      if (reconnected || recoveringSeed && value.connected && value.realtime) {
        recoveringSeed = false;
        void seed(true);
      }
    } catch (failure) {
      if (!disposed && requestContext === context) {
        error.value = failure instanceof ApiError ? failure.code : 'error';
        const at = Date.now() / 1000;
        snapshotTimes.add(at);
        livePoints.value = [...livePoints.value.filter(point => point.at !== at), { at, estimated_power: null, actual_power: null }];
      }
    } finally {
      if (!disposed) {
        trimPoints();
        lastPollAt = Date.now() / 1000;
        updateDisplayTimezone();
        timer = setTimeout(poll, (configuration.value?.settings?.update_seconds ?? 5) * 1000);
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
  return { configuration, snapshot, livePoints, liveRange, liveHistoryError, error, displayTimezone, loadConfiguration, acceptConfiguration, acceptSavedConfiguration };
}
