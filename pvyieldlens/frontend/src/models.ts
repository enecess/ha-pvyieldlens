export interface MonitoringSettings {
  rated_power_w: number;
  temperature_coefficient_pct_per_c: number;
  power_entity: string;
  temperature_entity: string;
  irradiance_entity: string;
  interval_minutes: 1 | 5 | 10;
  realtime_window_seconds: number;
  update_seconds: number;
  power_max_age_seconds: number;
  temperature_max_age_seconds: number;
  irradiance_max_age_seconds: number;
  timezone: string;
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
  timezone: string;
}

export interface Configuration {
  settings: MonitoringSettings | null;
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
export interface ConnectionResult { timezone: string; location: HALocation | null; entities: SourceEntity[] }
export interface ConfigurationUpdate {
  settings: MonitoringSettings;
  connection?: ConnectionInput | null;
  forecast_settings?: ForecastSettings | null;
}

export interface WindowResult {
  start: number;
  end: number;
  valid_seconds: number;
  estimated_energy_wh: number;
  actual_energy_wh: number;
  estimated_power: number | null;
  actual_power: number | null;
  pr: number | null;
  optimizable_power: number | null;
  coverage_percent: number;
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
  coverage_percent: number | null;
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
  timezone: string;
  today: string;
  boundary_unavailable: boolean;
  days: HistoryDay[];
}

export interface LiveHistoryResponse {
  configured: boolean;
  recovering: boolean;
  range: { start: number; end: number };
  step_seconds: number | null;
  context: { revision: number; settings: MonitoringSettings } | null;
  points: (WindowResult & { at: number })[];
}

export interface ForecastInterval {
  start: number;
  end: number;
  poa_w_m2: number | null;
  air_temperature_c: number | null;
  cell_temperature_c: number | null;
  power_w: number | null;
  energy_kwh: number | null;
  quality: 'complete' | 'unavailable';
}
export interface EnergyForecast {
  start: number;
  end: number;
  kwh: number | null;
  coverage_percent: number;
  quality: 'complete' | 'partial' | 'unavailable';
}
export interface DailyWeather {
  weather_code: number | null;
  temperature_min_c: number | null;
  temperature_max_c: number | null;
  quality: 'complete' | 'partial' | 'unavailable';
}
export interface ForecastDay extends EnergyForecast { day: string; weather: DailyWeather | null }
export interface ForecastView {
  status: 'disabled' | 'location_unavailable' | 'loading' | 'ready' | 'partial' | 'stale' | 'unavailable';
  refreshing: boolean;
  fetched_at: number | null;
  calculated_at: number;
  last_error: string | null;
  timezone: string | null;
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
  statistics: HistoryWindow | null;
  realtime: WindowResult | null;
  energy: {
    daily_kwh: number;
    total_kwh: number;
    day: string;
    timezone: string;
    daily_valid_seconds: number;
    daily_complete: boolean;
    total_valid_seconds: number;
    settled_until: number | null;
  };
  sources: { entity_id: string; state: string; unit: string | null; reported_at: number; valid: boolean }[];
  timezone: string;
  location: HALocation | null;
  forecast: ForecastSummary;
}
