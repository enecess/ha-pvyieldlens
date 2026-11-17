export interface MonitoringSettings {
  total_max_power_at_stc_w: number;
  pmax_temperature_coefficient_pct_per_c: number;
  actual_power_entity: string;
  module_temperature_entity: string;
  irradiance_entity: string;
  settlement_interval_minutes: 1 | 5 | 10;
  live_window_seconds: number;
  update_interval_seconds: number;
  actual_power_max_age_seconds: number;
  module_temperature_max_age_seconds: number;
  irradiance_max_age_seconds: number;
  home_timezone: string;
}

export interface ForecastSettings {
  enabled: boolean;
  tilt_deg: number | null;
  azimuth_deg: number | null;
  noct_c: number;
}

export interface HALocation {
  origin: string;
  latitude: number;
  longitude: number;
  location_name: string | null;
  home_timezone: string;
}

export interface Configuration {
  monitoring_settings: MonitoringSettings | null;
  forecast_settings: ForecastSettings;
  location: HALocation | null;
  mode: 'app' | 'docker';
  connection: { url: string; token_set: boolean };
}

export interface ConfigurationSaveResult extends Configuration {
  monitoring_changed: boolean;
}

export interface ConnectionInput { url: string; token?: string }
export interface SourceEntity { entity_id: string; name: string; unit: string | null; state: string }
export interface ConnectionResult { home_timezone: string; location: HALocation | null; entities: SourceEntity[] }
export interface ConfigurationUpdate {
  monitoring_settings: MonitoringSettings;
  connection?: ConnectionInput | null;
  forecast_settings: ForecastSettings;
}

export interface WindowResult {
  start: number;
  end: number;
  valid_seconds: number;
  estimated_energy_wh: number;
  actual_energy_wh: number;
  estimated_power_w: number | null;
  actual_power_w: number | null;
  pr: number | null;
  optimizable_power_w: number | null;
  data_completeness_percent: number;
  quality: string;
  reason: string | null;
}

export interface HistoryWindow extends WindowResult { revision: number; source_start?: number; source_end?: number }
export interface HistorySummary {
  start: number | null;
  end: number | null;
  estimated_energy_kwh: number | null;
  actual_energy_kwh: number | null;
  pr: number | null;
  data_completeness_percent: number | null;
  valid_seconds: number;
}
export interface HistoryResponse {
  windows: HistoryWindow[];
  summary: HistorySummary;
  requested_range: { start: number; end: number };
}
export type HistoryPeriod = 'today' | '24h' | '7d' | '30d';
export interface HistoryDay {
  day: string;
  start: number;
  end: number;
  summary: HistorySummary;
  in_progress: boolean;
  boundary_unavailable: boolean;
}
export interface HistoryView extends HistoryResponse {
  period: HistoryPeriod;
  home_timezone: string;
  today: string;
  boundary_unavailable: boolean;
  days: HistoryDay[];
}

export interface LiveSeriesResponse {
  configured: boolean;
  recovering: boolean;
  range: { start: number; end: number };
  step_seconds: number | null;
  context: { revision: number; monitoring_settings: MonitoringSettings } | null;
  points: (WindowResult & { at: number })[];
}

export interface ForecastInterval {
  start: number;
  end: number;
  irradiance_w_m2: number | null;
  air_temperature_c: number | null;
  cell_temperature_c: number | null;
  forecast_power_w: number | null;
  forecast_energy_kwh: number | null;
  quality: 'complete' | 'unavailable';
}
export interface EnergyForecast {
  start: number;
  end: number;
  forecast_energy_kwh: number | null;
  data_completeness_percent: number;
  quality: 'complete' | 'partial' | 'unavailable';
}
export interface DailyWeather {
  weather_code: number | null;
  air_temperature_min_c: number | null;
  air_temperature_max_c: number | null;
  quality: 'complete' | 'partial' | 'unavailable';
}
export interface ForecastDay extends EnergyForecast { day: string; weather: DailyWeather | null }
export interface ForecastView {
  status: 'disabled' | 'location_unavailable' | 'loading' | 'ready' | 'partial' | 'stale' | 'unavailable';
  refreshing: boolean;
  fetched_at: number | null;
  calculated_at: number;
  last_error: string | null;
  home_timezone: string | null;
  today: EnergyForecast | null;
  remaining_today: EnergyForecast | null;
  tomorrow: EnergyForecast | null;
  seven_days: EnergyForecast | null;
  days: ForecastDay[];
  intervals: ForecastInterval[];
}
export type ForecastSummary = Omit<ForecastView, 'days' | 'intervals'>;
export interface ForecastRefreshResult { scheduled: boolean; status: ForecastView['status'] }

export interface Snapshot {
  configured: boolean;
  connected: boolean;
  error: string | null;
  history_available: boolean;
  calculated_at: number | null;
  revision: number;
  latest_settled_window: HistoryWindow | null;
  live_window: WindowResult | null;
  energy_totals: {
    estimated_energy_today_kwh: number;
    estimated_energy_lifetime_kwh: number;
    day: string;
    home_timezone: string;
    today_valid_seconds: number;
    today_allocation_complete: boolean;
    lifetime_valid_seconds: number;
    settled_until: number | null;
  };
  sources: { entity_id: string; state: string; unit: string | null; reported_at: number; valid: boolean }[];
  home_timezone: string;
  location: HALocation | null;
  forecast: ForecastSummary;
}
