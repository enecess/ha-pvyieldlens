import { describe, expect, it } from 'vitest';
import { configurationUpdateFromDraft, draftFromConfiguration, hasSettingsChanges } from '../../pvyieldlens/frontend/src/settings';
import type { Configuration } from '../../pvyieldlens/frontend/src/models';

const configuration: Configuration = {
  monitoring_settings: { total_max_power_at_stc_w: 5000, pmax_temperature_coefficient_pct_per_c: -0.35,
    actual_power_entity: 'sensor.power', module_temperature_entity: 'sensor.temp', irradiance_entity: 'sensor.sun',
    settlement_interval_minutes: 1, live_window_seconds: 60, update_interval_seconds: 1,
    actual_power_max_age_seconds: 300, module_temperature_max_age_seconds: 900, irradiance_max_age_seconds: 300, home_timezone: 'UTC' },
  forecast_settings: { enabled: true, tilt_deg: 25, azimuth_deg: 180, noct_c: 45 },
  location: null, mode: 'docker', connection: { url: 'http://ha', token_set: true },
};

describe('settings drafts', () => {
  it('starts with blank physical parameters on first installation', () => {
    const draft = draftFromConfiguration({ ...configuration, monitoring_settings: null });
    expect(draft.monitoring.total_max_power_at_stc_w).toBe('');
    expect(draft.monitoring.pmax_temperature_coefficient_pct_per_c).toBe('');
    expect(draft.monitoring.actual_power_entity).toBe('');
    expect(draft.forecast.noct_c).toBe('45');
  });
  it('keeps all editable numbers as strings and replacement credentials blank', () => {
    const draft = draftFromConfiguration(configuration);
    expect(draft.monitoring.total_max_power_at_stc_w).toBe('5000');
    expect(draft.monitoring.pmax_temperature_coefficient_pct_per_c).toBe('-0.35');
    expect(draft.forecast).toEqual({ enabled: true, tilt_deg: '25', azimuth_deg: '180', noct_c: '45' });
    expect(draft.connection).toEqual({ url: 'http://ha', token: '' });
    expect(Object.values(draft.monitoring).every(value => typeof value === 'string')).toBe(true);
    expect(draft.monitoring).not.toHaveProperty('home_timezone');
  });

  it.each([['5000.0', false], ['', true], ['invalid', true], ['6100', true], ['5000', false]])(
    'compares rated power %s by its valid numeric value', (value, dirty) => {
      const baseline = draftFromConfiguration(configuration);
      const draft = draftFromConfiguration(configuration);
      draft.monitoring.total_max_power_at_stc_w = '6100';
      draft.monitoring.total_max_power_at_stc_w = value;
      expect(hasSettingsChanges(draft, baseline)).toBe(dirty);
    },
  );

  it('detects a replacement token and restores the blank saved credential draft', () => {
    const baseline = draftFromConfiguration(configuration);
    const draft = draftFromConfiguration(configuration);
    draft.connection.token = 'replacement-token';
    expect(hasSettingsChanges(draft, baseline)).toBe(true);
    expect(draftFromConfiguration(configuration).connection.token).toBe('');
    draft.connection.token = '';
    expect(hasSettingsChanges(draft, baseline)).toBe(false);
  });

  it.each([['http://ha/', false], ['http://ha///', false], ['http://ha/path/', true], ['http://HA', true]])(
    'compares connection URL %s with only server trailing-slash normalization', (url, dirty) => {
      const baseline = draftFromConfiguration(configuration);
      const draft = draftFromConfiguration(configuration);
      draft.connection.url = url;
      expect(hasSettingsChanges(draft, baseline)).toBe(dirty);
    },
  );

  it.each(['/', '///'])('keeps incomplete URL %s dirty against an empty saved connection', url => {
    const baseline = draftFromConfiguration({ ...configuration, connection: { url: '', token_set: false } });
    const draft = structuredClone(baseline);
    draft.connection.url = url;
    expect(hasSettingsChanges(draft, baseline)).toBe(true);
  });

  it('compares the effective angle independently of preset presentation', () => {
    const baseline = draftFromConfiguration(configuration);
    const draft = draftFromConfiguration(configuration);
    draft.forecast.azimuth_deg = '180.0';
    expect(hasSettingsChanges(draft, baseline)).toBe(false);
    expect(draft).not.toHaveProperty('direction');
  });

  it('ignores live location and presentation or discovery data', () => {
    const baseline = draftFromConfiguration(configuration);
    const updated = { ...configuration,
      location: { origin: 'http://ha', latitude: 1, longitude: 2, location_name: 'Renamed', home_timezone: 'Asia/Shanghai' },
      language: 'fr', theme: 'dark', entities: [{ entity_id: 'sensor.other', name: 'Other', unit: 'W', state: '1' }],
    };
    expect(hasSettingsChanges(draftFromConfiguration(updated), baseline)).toBe(false);
  });

  it('preserves null optional geometry without turning blanks into zero', () => {
    const draft = draftFromConfiguration({ ...configuration,
      forecast_settings: { enabled: false, tilt_deg: null, azimuth_deg: null, noct_c: 45 } });
    expect(draft.forecast.tilt_deg).toBe('');
    expect(draft.forecast.azimuth_deg).toBe('');
    expect(configurationUpdateFromDraft(draft, { mode: 'docker', home_timezone: 'Asia/Shanghai' })).toEqual({
      monitoring_settings: { ...configuration.monitoring_settings, home_timezone: 'Asia/Shanghai' },
      connection: { url: 'http://ha', token: '' },
      forecast_settings: { enabled: false, tilt_deg: null, azimuth_deg: null, noct_c: 45 },
    });
    draft.forecast.tilt_deg = '0';
    draft.forecast.azimuth_deg = '0';
    expect(hasSettingsChanges(draft, draftFromConfiguration({ ...configuration,
      forecast_settings: { enabled: false, tilt_deg: null, azimuth_deg: null, noct_c: 45 } }))).toBe(true);
  });

  it('converts only a valid payload and omits external credentials in App mode', () => {
    const draft = draftFromConfiguration(configuration);
    draft.forecast.tilt_deg = '90';
    draft.forecast.azimuth_deg = '359.9';
    expect(configurationUpdateFromDraft(draft, { mode: 'app', home_timezone: 'UTC' })).toEqual({
      monitoring_settings: configuration.monitoring_settings,
      forecast_settings: { enabled: true, tilt_deg: 90, azimuth_deg: 359.9, noct_c: 45 },
    });
  });
});
