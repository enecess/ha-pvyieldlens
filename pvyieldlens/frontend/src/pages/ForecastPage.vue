<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue';
import { CircleHelp, Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSnow, CloudSun, RefreshCw, Settings, Sun } from 'lucide-vue-next';
import PowerChart from '../PowerChart.vue';
import { api, ApiError } from '../api';
import type { ChartPoint, ChartSeries, ChartTooltip } from '../charts';
import type { EnergyForecast, ForecastDay, ForecastSummary, ForecastView } from '../models';
import { useI18n, type Language } from '../i18n';
import type { ColorMode } from '../theme';
import { formatTimes } from '../timezones';

const props = defineProps<{ active: boolean; summary: ForecastSummary | null; language: Language; theme: ColorMode; displayTimezone: string }>();
defineEmits<{ 'open-settings': [section: 'modules' | 'forecast'] }>();
const { t } = useI18n();
const detail = shallowRef<ForecastView | null>(null);
const selectedDay = ref<string | null>(null);
const error = ref<string | null>(null);
const refreshPending = ref<'submitting' | 'scheduled' | null>(null);
let pendingRequest: Promise<void> | null = null;
const key = (view: ForecastSummary | null) => JSON.stringify([
  view?.fetched_at, view?.home_timezone, view?.today?.start, view?.seven_days?.end,
  view?.geometry?.tilt_deg, view?.geometry?.azimuth_deg, view?.geometry?.read_at,
  view?.correction?.pr, view?.correction?.history_days, view?.correction?.start, view?.correction?.end,
]);
const view = computed(() => props.summary && (!detail.value || props.summary.calculated_at >= detail.value.calculated_at)
  ? props.summary : detail.value);
const todayStart = computed(() => view.value?.today?.start);
const isToday = (day: ForecastDay) => day.start === todayStart.value;
const homeTimezone = computed(() => new Intl.DateTimeFormat('en', {
  timeZone: view.value?.home_timezone ?? 'UTC',
}).resolvedOptions().timeZone);
const differentTimezone = computed(() => homeTimezone.value !== new Intl.DateTimeFormat('en', {
  timeZone: props.displayTimezone,
}).resolvedOptions().timeZone);
const status = computed(() => view.value?.status ?? 'loading');
const angleUnavailable = computed(() => view.value?.last_error === 'forecast_angle_unavailable');
const configurationRequired = computed(() => status.value === 'configuration_required');
const prerequisiteMissing = computed(() => configurationRequired.value || status.value === 'location_unavailable');
const operationalStatus = computed(() => prerequisiteMissing.value || status.value === 'loading'
  || status.value === 'unavailable' && !angleUnavailable.value);
const errorMessage = computed(() => {
  const requestError = error.value ? t(error.value) : '';
  if (angleUnavailable.value) {
    const angles = view.value!.unavailable_angles.map(({ axis, entity_id }) =>
      `${t(axis === 'tilt' ? 'forecast_tilt' : 'forecast_direction')} (${entity_id})`).join(' · ');
    const angleError = t(view.value!.geometry ? 'forecast_angle_unavailable_cached' : 'forecast_angle_unavailable', { angles });
    return requestError ? `${requestError} ${angleError}` : angleError;
  }
  return requestError || (view.value?.last_error ? t('forecast_fetch_failed') : '');
});
const refreshing = computed(() => refreshPending.value !== null || Boolean(view.value?.refreshing));
const days = computed(() => detail.value && key(view.value) === key(detail.value) ? detail.value.days : []);
const selected = computed(() => days.value.find(day => day.day === selectedDay.value));
const selectedIsToday = computed(() => selected.value !== undefined && isToday(selected.value));
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const energy = (total: EnergyForecast | null | undefined, corrected = false) =>
  number(corrected ? total?.corrected_forecast_energy_kwh : total?.forecast_energy_kwh, 3);
const date = (at: number) => new Intl.DateTimeFormat(props.language, {
  month: 'short', day: 'numeric', timeZone: homeTimezone.value,
}).format(new Date(at * 1000));
const weatherTypes = {
  clear: { icon: Sun, label: 'weather_clear' },
  mainlyClear: { icon: CloudSun, label: 'weather_mainly_clear' },
  partlyCloudy: { icon: CloudSun, label: 'weather_partly_cloudy' },
  overcast: { icon: Cloud, label: 'weather_overcast' },
  fog: { icon: CloudFog, label: 'weather_fog' },
  drizzle: { icon: CloudDrizzle, label: 'weather_drizzle' },
  freezingDrizzle: { icon: CloudDrizzle, label: 'weather_freezing_drizzle' },
  rain: { icon: CloudRain, label: 'weather_rain' },
  freezingRain: { icon: CloudRain, label: 'weather_freezing_rain' },
  snow: { icon: CloudSnow, label: 'weather_snow' },
  showers: { icon: CloudRain, label: 'weather_showers' },
  snowShowers: { icon: CloudSnow, label: 'weather_snow_showers' },
  thunderstorm: { icon: CloudLightning, label: 'weather_thunderstorm' },
  unknown: { icon: CircleHelp, label: 'weather_unknown' },
};
const weatherCodes: Partial<Record<number, keyof typeof weatherTypes>> = {
  0: 'clear', 1: 'mainlyClear', 2: 'partlyCloudy', 3: 'overcast', 45: 'fog', 48: 'fog',
  51: 'drizzle', 53: 'drizzle', 55: 'drizzle', 56: 'freezingDrizzle', 57: 'freezingDrizzle',
  61: 'rain', 63: 'rain', 65: 'rain', 66: 'freezingRain', 67: 'freezingRain',
  71: 'snow', 73: 'snow', 75: 'snow', 77: 'snow', 80: 'showers', 81: 'showers', 82: 'showers',
  85: 'snowShowers', 86: 'snowShowers', 95: 'thunderstorm', 96: 'thunderstorm', 97: 'thunderstorm', 99: 'thunderstorm',
};
const weatherType = (day: ForecastDay) => weatherTypes[
  day.weather?.weather_code == null ? 'unknown' : weatherCodes[day.weather.weather_code] ?? 'unknown'];
const temperature = (value: number | null | undefined) => value == null ? '—' : `${number(value)}°`;
const dayLabel = (day: ForecastDay) => `${new Intl.DateTimeFormat(props.language, {
  dateStyle: 'long', timeZone: homeTimezone.value,
}).format(new Date(day.start * 1000))}: ${t(weatherType(day).label)} · ${t('forecast_air_temperature_range', {
  high: number(day.weather?.air_temperature_max_c), low: number(day.weather?.air_temperature_min_c),
})} · ${t('forecast_original_energy')} ${energy(day)} kWh · ${t('forecast_corrected_energy')} ${energy(day, true)} kWh`;
const updateTime = (at: number) => formatTimes([at], props.language, props.displayTimezone, {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})[0];
const fetchedTime = computed(() => view.value?.fetched_at == null ? t('forecast_never_fetched')
  : t('forecast_fetched', { time: updateTime(view.value.fetched_at) }));
const geometryText = computed(() => {
  if (!view.value?.geometry) return '';
  const { tilt_deg, azimuth_deg } = view.value.geometry;
  const degrees = new Intl.NumberFormat(props.language, { maximumSignificantDigits: 21, useGrouping: false });
  return t('forecast_geometry', { tilt: `${degrees.format(tilt_deg)}°`, azimuth: `${degrees.format(azimuth_deg)}°` });
});
const maximum = computed(() => Math.max(1, ...days.value.flatMap(day =>
  [day.forecast_energy_kwh ?? 0, day.corrected_forecast_energy_kwh ?? 0])));
const rows = computed(() => {
  const day = selected.value;
  if (!day || !detail.value) return [];
  return detail.value.intervals.filter(row => row.end > day.start && row.start < day.end)
    .map(row => ({ ...row, start: Math.max(row.start, day.start), end: Math.min(row.end, day.end),
      forecast_energy_kwh: row.forecast_energy_kwh == null ? null : row.forecast_energy_kwh *
        (Math.min(row.end, day.end) - Math.max(row.start, day.start)) / (row.end - row.start),
      corrected_forecast_energy_kwh: row.corrected_forecast_energy_kwh == null ? null : row.corrected_forecast_energy_kwh *
        (Math.min(row.end, day.end) - Math.max(row.start, day.start)) / (row.end - row.start) }));
});
const formattedRows = computed(() => {
  const instants = rows.value.flatMap(row => [row.start, row.end]);
  const clocks = formatTimes(instants, props.language, homeTimezone.value, {
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
  const stamps = formatTimes(instants, props.language, homeTimezone.value, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
  return rows.value.map((row, index) => ({ ...row, startTime: clocks[index * 2], endTime: clocks[index * 2 + 1],
    startStamp: stamps[index * 2], endStamp: stamps[index * 2 + 1] }));
});
const rowLabels = computed(() => new Map(formattedRows.value.map(row => [row.start, row])));
const points = computed<ChartPoint[]>(() => rows.value.map(row => ({ at: (row.start + row.end) / 2, forecast_power_w: row.forecast_power_w,
  corrected_forecast_power_w: row.corrected_forecast_power_w, interval: row })));
const chartRange = computed(() => selected.value && { start: selected.value.start, end: selected.value.end });
const series: ChartSeries[] = [
  { key: 'forecast_power_w', label: 'forecast_power', color: 'var(--pv-estimated)' },
  { key: 'corrected_forecast_power_w', label: 'forecast_corrected_power', color: 'var(--pv-corrected)' },
];
const currentTime = computed(() => {
  if (!selectedIsToday.value) return undefined;
  // Scalar snapshots advance the retained time marker without rebuilding the series.
  void view.value?.calculated_at;
  return Date.now() / 1000;
});
const tooltip = (point: ChartPoint): ChartTooltip => {
  const row = point.interval!;
  const labels = rowLabels.value.get(row.start)!;
  return { title: `${labels.startStamp} – ${labels.endStamp}`, rows: [
    { label: t('forecast_power'), value: `${number(row.forecast_power_w)} W`, color: series[0].color },
    { label: t('forecast_corrected_power'), value: `${number(row.corrected_forecast_power_w)} W`, color: series[1].color },
    { label: t('forecast_original_energy'), value: `${number(row.forecast_energy_kwh, 3)} kWh`, color: series[0].color },
    { label: t('forecast_corrected_energy'), value: `${number(row.corrected_forecast_energy_kwh, 3)} kWh`, color: series[1].color },
    { label: t('irradiance'), value: `${number(row.irradiance_w_m2)} W/m²` },
    { label: t('air_temperature'), value: `${number(row.air_temperature_c)} °C` },
    { label: t('estimated_cell_temperature'), value: `${number(row.cell_temperature_c)} °C` },
  ] };
};

function loadForecast() {
  pendingRequest ??= api.getForecast().then(result => {
    detail.value = result;
    error.value = null;
  }, failure => { error.value = failure instanceof ApiError ? failure.code : 'error'; })
    .finally(() => { pendingRequest = null; });
  return pendingRequest;
}
watch(days, dates => {
  if (dates.length && !dates.some(day => day.day === selectedDay.value)) selectedDay.value = dates[0].day;
});
watch(() => [props.active, props.summary] as const, ([active, summary], previous) => {
  const refreshCompleted = summary && refreshPending.value === 'scheduled' && !summary.refreshing;
  if (summary && refreshPending.value === 'scheduled') refreshPending.value = null;
  if (!active) return;
  if (!detail.value || !previous?.[0] || summary && summary.calculated_at >= detail.value.calculated_at &&
    (key(summary) !== key(detail.value) || refreshCompleted || previous?.[1]?.refreshing && !summary.refreshing)) void loadForecast();
}, { immediate: true });

async function refreshForecast() {
  refreshPending.value = 'submitting';
  error.value = null;
  try {
    const result = await api.refreshForecast();
    refreshPending.value = result.scheduled ? 'scheduled' : null;
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'error';
    refreshPending.value = null;
  }
}
</script>

<template>
  <section id="forecast-page" aria-labelledby="forecast-heading">
    <div class="section-heading"><div><p class="eyebrow">{{ t('pv_modules') }} / {{ t('forecast') }}</p><h1 id="forecast-heading">{{ t('forecast') }}</h1>
      <p class="muted">{{ t('forecast_intro') }}</p></div>
      <button id="forecast-refresh" class="secondary" :disabled="!view || refreshing || prerequisiteMissing" @click="refreshForecast">
        <RefreshCw :size="15" aria-hidden="true" />{{ t('forecast_refresh') }}</button></div>
    <div class="metrics forecast-metrics">
      <article v-for="card in [{ id: 'forecast-remaining', label: 'forecast_remaining', total: view?.remaining_today },
        { id: 'forecast-tomorrow', label: 'forecast_tomorrow', total: view?.tomorrow }]" :key="card.id" class="metric">
        <span class="metric-label">{{ t(card.label) }}</span>
        <div class="forecast-pair">
          <div><span>{{ t('forecast_original') }}</span><div><strong :id="card.id">{{ energy(card.total) }}</strong><span class="unit">kWh</span></div></div>
          <div><span>{{ t('forecast_corrected') }}</span><div><strong :id="`${card.id}-corrected`" class="corrected-value">{{ energy(card.total, true) }}</strong><span class="unit">kWh</span></div></div>
        </div>
      </article>
    </div>
    <p v-if="view?.correction" id="forecast-correction" class="muted">{{ t('forecast_correction_context', {
      pr: view.correction.pr == null ? '—' : `${number(view.correction.pr)}%`, days: view.correction.history_days,
    }) }}</p>
    <div v-if="operationalStatus || refreshing" class="forecast-status-line">
      <p v-if="operationalStatus" id="forecast-status" role="status" :data-status="status">{{ t(`forecast_status_${status}`) }}</p>
      <span id="forecast-refresh-state" class="muted" role="status">{{ refreshing ? t('forecast_refreshing') : '' }}</span></div>
    <p id="forecast-error" class="muted" role="status">{{ errorMessage }}</p>
    <div v-show="days.length" id="forecast-data">
      <p v-if="differentTimezone" id="forecast-home-time-note" class="muted">{{ t('forecast_home_time_note', { timezone: homeTimezone }) }}</p>
      <article class="panel"><div class="panel-heading"><h2>{{ t('forecast_daily') }}</h2>
        <div class="legend"><span class="estimated-dot">{{ t('forecast_original_energy') }}</span><span class="corrected-dot">{{ t('forecast_corrected_energy') }}</span></div></div>
        <p id="forecast-calendar-help" class="muted">{{ t('forecast_calendar_help') }}</p>
        <div id="forecast-days" role="group" :aria-label="t('forecast_daily')">
          <button v-for="day in days" :key="day.day" type="button" :data-day="day.day" :aria-pressed="day.day === selectedDay"
            :aria-current="isToday(day) ? 'date' : undefined" :aria-label="dayLabel(day)"
            aria-describedby="forecast-calendar-help" @click="selectedDay = day.day">
            <span class="day-label">{{ isToday(day) ? t('today') : date(day.start) }}</span>
            <component :is="weatherType(day).icon" class="day-weather-icon" :size="24" aria-hidden="true" />
            <span class="day-weather">{{ t(weatherType(day).label) }}</span>
            <span class="day-temperature">{{ temperature(day.weather?.air_temperature_max_c) }} / {{ temperature(day.weather?.air_temperature_min_c) }}</span>
            <span class="day-bar-track" aria-hidden="true">
              <span class="day-bar" :class="{ unavailable: day.forecast_energy_kwh == null }"
                :style="{ height: day.forecast_energy_kwh == null ? '100%' : `${day.forecast_energy_kwh / maximum * 100}%` }"></span>
              <span class="day-bar corrected" :class="{ unavailable: day.corrected_forecast_energy_kwh == null }"
                :style="{ height: day.corrected_forecast_energy_kwh == null ? '100%' : `${day.corrected_forecast_energy_kwh / maximum * 100}%` }"></span>
            </span>
            <span class="day-energy">{{ energy(day) }}<small>kWh</small></span>
            <span class="day-energy corrected-value">{{ energy(day, true) }}<small>kWh</small></span>
          </button>
        </div>
        <div class="forecast-totals muted"><span>{{ t('forecast_seven_days') }}</span>
          <span>{{ t('forecast_original_energy') }} <strong id="forecast-seven-days">{{ energy(view?.seven_days) }} kWh</strong></span>
          <span>{{ t('forecast_corrected_energy') }} <strong id="forecast-seven-days-corrected" class="corrected-value">{{ energy(view?.seven_days, true) }} kWh</strong></span></div>
      </article>
      <article class="panel forecast-hourly"><div class="panel-heading"><h2><span id="forecast-day-heading">{{ selected && (selectedIsToday ? t('today') : date(selected.start)) }}</span> · {{ t('forecast_hourly') }}</h2>
        <div class="legend"><span class="estimated-dot">{{ t('forecast_power') }}</span><span class="corrected-dot">{{ t('forecast_corrected_power') }}</span></div></div>
        <div class="forecast-totals muted">
          <span>{{ t('forecast_original_energy') }} <strong id="forecast-day-total">{{ energy(selected) }} kWh</strong></span>
          <span>{{ t('forecast_corrected_energy') }} <strong id="forecast-day-total-corrected" class="corrected-value">{{ energy(selected, true) }} kWh</strong></span></div>
        <PowerChart id="forecast-chart" :points="points" :series="series" unit="W" :active="active && days.length > 0" :language="language" :timezone="homeTimezone" :theme="theme" :current-time="currentTime" :tooltip="tooltip" :range="chartRange" selection="interval" />
        <p v-if="selectedIsToday && points.length" id="forecast-marker-help" class="muted">{{ t('forecast_marker_help') }}</p>
        <details id="forecast-details"><summary id="forecast-details-label">{{ t('forecast_details') }}</summary>
          <p id="forecast-details-help" class="muted">{{ t('forecast_details_help') }}</p><p id="forecast-scroll-hint" class="muted">{{ t('forecast_scroll') }}</p>
          <div class="table-scroll" tabindex="0" role="region" aria-labelledby="forecast-details-label"><table aria-labelledby="forecast-details-label" aria-describedby="forecast-details-help"><thead><tr>
            <th>{{ t('forecast_period') }}</th><th>{{ t('irradiance') }} (W/m²)</th><th>{{ t('air_temperature') }} (°C)</th><th>{{ t('estimated_cell_temperature') }} (°C)</th><th>{{ t('forecast_power') }} (W)</th><th>{{ t('forecast_corrected_power') }} (W)</th><th>{{ t('forecast_original_energy') }} (kWh)</th><th>{{ t('forecast_corrected_energy') }} (kWh)</th>
          </tr></thead><tbody id="forecast-rows"><tr v-for="row in formattedRows" :key="row.start"><td>
            <time :datetime="new Date(row.start * 1000).toISOString()" :aria-label="row.startStamp" :title="row.startStamp">{{ row.startTime }}</time>
            <time :datetime="new Date(row.end * 1000).toISOString()" :aria-label="row.endStamp" :title="row.endStamp">→ {{ row.end === selected?.end ? `${date(row.end)} ` : '' }}{{ row.endTime }}</time>
          </td><td>{{ number(row.irradiance_w_m2) }}</td><td>{{ number(row.air_temperature_c) }}</td><td>{{ number(row.cell_temperature_c) }}</td><td>{{ number(row.forecast_power_w) }}</td><td>{{ number(row.corrected_forecast_power_w) }}</td><td>{{ number(row.forecast_energy_kwh, 3) }}</td><td>{{ number(row.corrected_forecast_energy_kwh, 3) }}</td></tr></tbody></table></div>
        </details>
      </article>
    </div>
    <div class="inline-notes forecast-meta muted">
      <p v-if="view?.geometry" class="forecast-geometry-notes">
        <span id="forecast-geometry">{{ geometryText }}</span>
        <span id="forecast-angle-read-at">{{ t('forecast_angle_read_at', { time: updateTime(view.geometry.read_at) }) }}</span>
        <span>{{ t('forecast_geometry_approximation') }}</span>
      </p>
      <span id="forecast-fetched">{{ fetchedTime }}</span>
      <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">{{ t('forecast_attribution') }}</a></div>
    <button id="open-forecast-settings" class="secondary" @click="$emit('open-settings', configurationRequired ? 'modules' : 'forecast')"><Settings :size="15" aria-hidden="true" />{{ t(configurationRequired ? 'forecast_configure_modules' : 'forecast_configure') }}</button>
  </section>
</template>
