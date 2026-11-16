import { onScopeDispose, ref, shallowRef } from 'vue';
import { api, ApiError } from './api';
import { resolveDisplayTimezone } from './timezones';
import type { ChartPoint } from './charts';
import type { Configuration, ConfigurationSaveResult, Snapshot } from './models';

export function useDashboard() {
  const configuration = shallowRef<Configuration | null>(null);
  const snapshot = shallowRef<Snapshot | null>(null);
  const livePoints = shallowRef<ChartPoint[]>([]);
  const error = ref<string | null>(null);
  const displayTimezone = ref('UTC');
  let disposed = false;
  let timer: ReturnType<typeof setTimeout>;

  function updateDisplayTimezone() {
    const timezone = resolveDisplayTimezone(window, configuration.value?.mode,
      snapshot.value?.timezone ?? configuration.value?.settings?.timezone ?? configuration.value?.location?.timezone ?? '');
    if (timezone !== displayTimezone.value) displayTimezone.value = timezone;
  }
  function onVisibilityChange() { if (!document.hidden) updateDisplayTimezone(); }
  function acceptConfiguration(value: Configuration) {
    configuration.value = value;
    updateDisplayTimezone();
  }
  function acceptSavedConfiguration(value: ConfigurationSaveResult) {
    acceptConfiguration(value);
    if (value.monitoring_changed) livePoints.value = [];
  }
  async function loadConfiguration() {
    const value = await api.getConfiguration();
    if (!disposed) acceptConfiguration(value);
    return value;
  }
  async function poll() {
    try {
      const value = await api.getSnapshot();
      if (disposed) return;
      snapshot.value = value;
      error.value = null;
      if (configuration.value) configuration.value = { ...configuration.value, location: value.location };
      if (value.calculated_at !== null && livePoints.value.at(-1)?.at !== value.calculated_at) {
        livePoints.value = [...livePoints.value, { at: value.calculated_at,
          estimated_power: value.realtime?.estimated_power ?? null, actual_power: value.realtime?.actual_power ?? null }];
      }
      livePoints.value = livePoints.value.filter(point => point.at >= Date.now() / 1000 - 1800).slice(-600);
    } catch (failure) {
      if (!disposed) error.value = failure instanceof ApiError ? failure.code : 'error';
    } finally {
      if (!disposed) {
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
    .then(() => { if (!disposed) void poll(); });
  return { configuration, snapshot, livePoints, error, displayTimezone, loadConfiguration, acceptConfiguration, acceptSavedConfiguration };
}
