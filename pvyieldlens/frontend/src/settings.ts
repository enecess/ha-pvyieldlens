import type { Configuration, ConfigurationUpdate, MonitoringSettings } from './models';

export type SettingsSection = 'connection' | 'panels' | 'sources' | 'monitoring' | 'forecast';
export interface SettingsDraft {
  monitoring: { [Key in Exclude<keyof MonitoringSettings, 'timezone'>]: string };
  connection: { url: string; token: string };
  forecast: { enabled: boolean; tilt_deg: string; azimuth_deg: string; noct_c: string };
}

export function draftFromConfiguration(value: Configuration): SettingsDraft {
  const settings = value.settings;
  return {
    monitoring: {
      rated_power_w: settings ? String(settings.rated_power_w) : '',
      temperature_coefficient_pct_per_c: settings ? String(settings.temperature_coefficient_pct_per_c) : '',
      power_entity: settings?.power_entity ?? '', temperature_entity: settings?.temperature_entity ?? '',
      irradiance_entity: settings?.irradiance_entity ?? '', interval_minutes: String(settings?.interval_minutes ?? 5),
      realtime_window_seconds: String(settings?.realtime_window_seconds ?? 60), update_seconds: String(settings?.update_seconds ?? 5),
      power_max_age_seconds: String(settings?.power_max_age_seconds ?? 300),
      temperature_max_age_seconds: String(settings?.temperature_max_age_seconds ?? 900),
      irradiance_max_age_seconds: String(settings?.irradiance_max_age_seconds ?? 300),
    },
    connection: { url: value.connection.url, token: '' },
    forecast: {
      enabled: value.forecast_settings.enabled,
      tilt_deg: value.forecast_settings.tilt_deg === null ? '' : String(value.forecast_settings.tilt_deg),
      azimuth_deg: value.forecast_settings.azimuth_deg === null ? '' : String(value.forecast_settings.azimuth_deg),
      noct_c: String(value.forecast_settings.noct_c),
    },
  };
}

export function hasSettingsChanges(draft: SettingsDraft, baseline: SettingsDraft): boolean {
  const numericValue = (value: string) => value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : value;
  const urlValue = (value: string) => value.replace(/\/+$/, '') || value;
  return Object.entries(draft.monitoring).some(([key, value]) => key.endsWith('_entity')
    ? value.trim() !== baseline.monitoring[key as keyof SettingsDraft['monitoring']].trim()
    : numericValue(value) !== numericValue(baseline.monitoring[key as keyof SettingsDraft['monitoring']]))
    || urlValue(draft.connection.url) !== urlValue(baseline.connection.url)
    || draft.connection.token !== baseline.connection.token
    || draft.forecast.enabled !== baseline.forecast.enabled
    || (['tilt_deg', 'azimuth_deg', 'noct_c'] as const).some(key => numericValue(draft.forecast[key]) !== numericValue(baseline.forecast[key]));
}

export function configurationUpdateFromDraft(draft: SettingsDraft, context: { mode: 'app' | 'docker'; timezone: string }): ConfigurationUpdate {
  return {
    settings: {
      rated_power_w: Number(draft.monitoring.rated_power_w),
      temperature_coefficient_pct_per_c: Number(draft.monitoring.temperature_coefficient_pct_per_c),
      power_entity: draft.monitoring.power_entity.trim(), temperature_entity: draft.monitoring.temperature_entity.trim(),
      irradiance_entity: draft.monitoring.irradiance_entity.trim(),
      interval_minutes: Number(draft.monitoring.interval_minutes) as MonitoringSettings['interval_minutes'],
      realtime_window_seconds: Number(draft.monitoring.realtime_window_seconds), update_seconds: Number(draft.monitoring.update_seconds),
      power_max_age_seconds: Number(draft.monitoring.power_max_age_seconds),
      temperature_max_age_seconds: Number(draft.monitoring.temperature_max_age_seconds),
      irradiance_max_age_seconds: Number(draft.monitoring.irradiance_max_age_seconds), timezone: context.timezone,
    },
    ...(context.mode === 'app' ? {} : { connection: { ...draft.connection } }),
    forecast_settings: {
      enabled: draft.forecast.enabled,
      tilt_deg: draft.forecast.tilt_deg === '' ? null : Number(draft.forecast.tilt_deg),
      azimuth_deg: draft.forecast.azimuth_deg === '' ? null : Number(draft.forecast.azimuth_deg),
      noct_c: Number(draft.forecast.noct_c),
    },
  };
}
