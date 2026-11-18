import type { Configuration, ConfigurationUpdate, MonitoringSettings } from './models';

export type SettingsSection = 'connection' | 'modules' | 'sources' | 'monitoring' | 'forecast';
export const forecastAxes = ['tilt', 'azimuth'] as const;
type AngleSource = 'fixed' | 'entity';
export interface SettingsDraft {
  monitoring: { [Key in Exclude<keyof MonitoringSettings, 'home_timezone'>]: string };
  connection: { url: string; token: string };
  forecast: {
    tilt_deg: string; azimuth_deg: string; noct_c: string; pr_history_days: string;
    tilt_source: AngleSource; azimuth_source: AngleSource; tilt_entity: string; azimuth_entity: string;
  };
}

export function draftFromConfiguration(value: Configuration): SettingsDraft {
  const settings = value.monitoring_settings;
  const forecast = value.forecast_settings;
  return {
    monitoring: {
      total_max_power_at_stc_w: settings ? String(settings.total_max_power_at_stc_w) : '',
      pmax_temperature_coefficient_pct_per_c: settings ? String(settings.pmax_temperature_coefficient_pct_per_c) : '',
      actual_power_entity: settings?.actual_power_entity ?? '', module_temperature_entity: settings?.module_temperature_entity ?? '',
      irradiance_entity: settings?.irradiance_entity ?? '', settlement_interval_minutes: String(settings?.settlement_interval_minutes ?? 5),
      live_window_seconds: String(settings?.live_window_seconds ?? 60), update_interval_seconds: String(settings?.update_interval_seconds ?? 5),
      actual_power_max_age_seconds: String(settings?.actual_power_max_age_seconds ?? 300),
      module_temperature_max_age_seconds: String(settings?.module_temperature_max_age_seconds ?? 900),
      irradiance_max_age_seconds: String(settings?.irradiance_max_age_seconds ?? 300),
    },
    connection: { url: value.connection.url, token: '' },
    forecast: {
      tilt_source: forecast.tilt_entity ? 'entity' : 'fixed',
      azimuth_source: forecast.azimuth_entity ? 'entity' : 'fixed',
      tilt_entity: forecast.tilt_entity ?? '',
      azimuth_entity: forecast.azimuth_entity ?? '',
      tilt_deg: forecast.tilt_deg === null ? '' : String(forecast.tilt_deg),
      azimuth_deg: forecast.azimuth_deg === null ? '' : String(forecast.azimuth_deg),
      noct_c: String(forecast.noct_c),
      pr_history_days: String(forecast.pr_history_days),
    },
  };
}

export function normalizeConnectionUrl(url: string): string {
  return url.replace(/\/+$/, '');
}

export function hasSettingsChanges(draft: SettingsDraft, baseline: SettingsDraft): boolean {
  const numericValue = (value: string) => value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : value;
  const urlValue = (value: string) => normalizeConnectionUrl(value) || value;
  return Object.entries(draft.monitoring).some(([key, value]) => key.endsWith('_entity')
    ? value.trim() !== baseline.monitoring[key as keyof SettingsDraft['monitoring']].trim()
    : numericValue(value) !== numericValue(baseline.monitoring[key as keyof SettingsDraft['monitoring']]))
    || urlValue(draft.connection.url) !== urlValue(baseline.connection.url)
    || draft.connection.token !== baseline.connection.token
    || forecastAxes.some(axis => {
      const source = draft.forecast[`${axis}_source`];
      return source !== baseline.forecast[`${axis}_source`] || (source === 'entity'
        ? draft.forecast[`${axis}_entity`].trim() !== baseline.forecast[`${axis}_entity`].trim()
        : numericValue(draft.forecast[`${axis}_deg`]) !== numericValue(baseline.forecast[`${axis}_deg`]));
    })
    || (['noct_c', 'pr_history_days'] as const).some(key => numericValue(draft.forecast[key]) !== numericValue(baseline.forecast[key]));
}

export function configurationUpdateFromDraft(draft: SettingsDraft, context: { mode: 'app' | 'docker'; home_timezone: string }): ConfigurationUpdate {
  const forecast = draft.forecast;
  return {
    monitoring_settings: {
      total_max_power_at_stc_w: Number(draft.monitoring.total_max_power_at_stc_w),
      pmax_temperature_coefficient_pct_per_c: Number(draft.monitoring.pmax_temperature_coefficient_pct_per_c),
      actual_power_entity: draft.monitoring.actual_power_entity.trim(),
      module_temperature_entity: draft.monitoring.module_temperature_entity.trim() || null,
      irradiance_entity: draft.monitoring.irradiance_entity.trim(),
      settlement_interval_minutes: Number(draft.monitoring.settlement_interval_minutes) as MonitoringSettings['settlement_interval_minutes'],
      live_window_seconds: Number(draft.monitoring.live_window_seconds), update_interval_seconds: Number(draft.monitoring.update_interval_seconds),
      actual_power_max_age_seconds: Number(draft.monitoring.actual_power_max_age_seconds),
      module_temperature_max_age_seconds: Number(draft.monitoring.module_temperature_max_age_seconds),
      irradiance_max_age_seconds: Number(draft.monitoring.irradiance_max_age_seconds), home_timezone: context.home_timezone,
    },
    ...(context.mode === 'app' ? {} : { connection: { ...draft.connection } }),
    forecast_settings: {
      tilt_deg: forecast.tilt_source === 'fixed' && forecast.tilt_deg !== '' ? Number(forecast.tilt_deg) : null,
      azimuth_deg: forecast.azimuth_source === 'fixed' && forecast.azimuth_deg !== '' ? Number(forecast.azimuth_deg) : null,
      tilt_entity: forecast.tilt_source === 'entity' ? forecast.tilt_entity.trim() : null,
      azimuth_entity: forecast.azimuth_source === 'entity' ? forecast.azimuth_entity.trim() : null,
      noct_c: Number(forecast.noct_c),
      pr_history_days: Number(forecast.pr_history_days),
    },
  };
}
