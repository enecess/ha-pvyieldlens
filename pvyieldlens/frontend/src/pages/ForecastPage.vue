<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue';
import { RefreshCw, Settings } from 'lucide-vue-next';
import MetricCard from '../MetricCard.vue';
import PowerChart from '../PowerChart.vue';
import { api, ApiError } from '../api';
import type { ChartPoint, ChartSeries } from '../charts';
import type { EnergyForecast, ForecastSummary, ForecastView } from '../models';
import { useI18n, type Language } from '../i18n';
import type { ColorMode } from '../theme';

const props = defineProps<{ active: boolean; summary: ForecastSummary | null; language: Language; theme: ColorMode }>();
defineEmits<{ 'open-settings': [section: 'forecast'] }>();
const { t } = useI18n();
const detail = shallowRef<ForecastView | null>(null);
const selectedDay = ref<string | null>(null);
const error = ref<string | null>(null);
const refreshPending = ref<'submitting' | 'scheduled' | null>(null);
let pendingRequest: Promise<void> | null = null;
const key = (view: ForecastSummary | null) => `${view?.fetched_at}|${view?.timezone}|${view?.today?.start}|${view?.seven_days?.end}`;
const view = computed(() => props.summary && (!detail.value || props.summary.calculated_at >= detail.value.calculated_at)
  ? props.summary : detail.value);
const timezone = computed(() => view.value?.timezone ?? 'UTC');
const status = computed(() => view.value?.status ?? 'loading');
const refreshing = computed(() => refreshPending.value !== null || Boolean(view.value?.refreshing));
const days = computed(() => detail.value && key(view.value) === key(detail.value) ? detail.value.days : []);
const selected = computed(() => days.value.find(day => day.day === selectedDay.value));
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const energy = (total: EnergyForecast | null | undefined) => number(total?.quality === 'complete' ? total.kwh : null, 3);
const date = (at: number) => new Intl.DateTimeFormat(props.language, {
  month: 'short', day: 'numeric', timeZone: timezone.value,
}).format(new Date(at * 1000));
const time = (at: number) => new Intl.DateTimeFormat(props.language, {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  hourCycle: 'h23', timeZone: timezone.value, timeZoneName: 'longOffset',
}).format(new Date(at * 1000));
const intervalTime = (at: number) => new Intl.DateTimeFormat(props.language, {
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: timezone.value, timeZoneName: 'longOffset',
}).format(new Date(at * 1000));
const maximum = computed(() => Math.max(1, ...days.value.map(day => day.quality === 'complete' ? day.kwh ?? 0 : 0)));
const rows = computed(() => {
  const day = selected.value;
  if (!day || !detail.value) return [];
  return detail.value.intervals.filter(row => row.end > day.start && row.start < day.end)
    .map(row => ({ ...row, start: Math.max(row.start, day.start), end: Math.min(row.end, day.end),
      energy_kwh: row.energy_kwh == null ? null : row.energy_kwh *
        (Math.min(row.end, day.end) - Math.max(row.start, day.start)) / (row.end - row.start) }));
});
const points = computed<ChartPoint[]>(() => rows.value.flatMap(row => [
  { at: row.start, power_w: row.power_w, interval: row }, { at: row.end, power_w: row.power_w, interval: row },
]));
const series: ChartSeries[] = [{ key: 'power_w', label: 'forecast_power', color: 'var(--pv-theoretical)' }];
const currentTime = computed(() => {
  // Scalar snapshots advance the retained time marker without rebuilding the series.
  void view.value?.calculated_at;
  return Date.now() / 1000;
});
const tooltip = (point: ChartPoint) => {
  const row = point.interval!;
  return `${time(row.start)} – ${time(row.end)} · ${t('forecast_poa')}: ${number(row.poa_w_m2)} W/m² · ${t('forecast_air')}: ${number(row.air_temperature_c)} °C · ${t('forecast_cell')}: ${number(row.cell_temperature_c)} °C · ${t('forecast_power')}: ${number(row.power_w)} W · ${t('forecast_interval_energy')}: ${number(row.energy_kwh, 3)} kWh`;
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
    <div class="section-heading"><div><p class="eyebrow">SOLAR / {{ t('forecast') }}</p><h1 id="forecast-heading">{{ t('forecast') }}</h1>
      <p class="muted">{{ t('forecast_intro') }}</p></div>
      <button id="forecast-refresh" class="secondary" :disabled="refreshing || status === 'disabled' || status === 'location_unavailable'" @click="refreshForecast">
        <RefreshCw :size="15" aria-hidden="true" />{{ t('forecast_refresh') }}</button></div>
    <div class="metrics forecast-metrics">
      <MetricCard :label="t('forecast_remaining')" :value="energy(view?.remaining_today)" unit="kWh" primary><span id="forecast-remaining">{{ energy(view?.remaining_today) }}</span></MetricCard>
      <MetricCard :label="t('forecast_tomorrow')" :value="energy(view?.tomorrow)" unit="kWh"><span id="forecast-tomorrow">{{ energy(view?.tomorrow) }}</span></MetricCard>
    </div>
    <div class="forecast-status-line"><p id="forecast-status" role="status" :data-status="status"><span class="status-dot" :class="{ good: status === 'ready' }"></span>{{ t(`forecast_status_${status}`) }}</p>
      <span id="forecast-refresh-state" class="muted" role="status">{{ refreshing ? t('forecast_refreshing') : '' }}</span></div>
    <p id="forecast-error" class="muted" role="status">{{ error ? t(error) : view?.last_error ? t('forecast_fetch_failed') : '' }}</p>
    <div v-show="days.length" id="forecast-data">
      <article class="panel"><div class="panel-heading"><h2>{{ t('forecast_daily') }}</h2><span class="muted">{{ t('forecast_seven_days') }} <strong id="forecast-seven-days">{{ energy(view?.seven_days) }} kWh</strong></span></div>
        <p class="muted">{{ t('forecast_calendar_help') }}</p>
        <div id="forecast-days" role="group" :aria-label="t('forecast_daily')">
          <button v-for="day in days" :key="day.day" type="button" :data-day="day.day" :aria-pressed="day.day === selectedDay"
            :aria-label="`${date(day.start)}: ${energy(day)} kWh · ${t(day.quality)}`" @click="selectedDay = day.day">
            <span class="day-label">{{ date(day.start) }}</span>
            <span class="day-bar-track" aria-hidden="true"><span class="day-bar" :class="{ unavailable: day.quality !== 'complete' || day.kwh === null }"
              :style="{ height: `${day.quality !== 'complete' || day.kwh === null ? 100 : Math.max(1, day.kwh / maximum * 100)}%` }"></span></span>
            <span>{{ energy(day) }}</span>
          </button>
        </div>
      </article>
      <article class="panel forecast-hourly"><div class="panel-heading"><h2><span id="forecast-day-heading">{{ selected ? date(selected.start) : '' }}</span> · {{ t('forecast_hourly') }}</h2>
        <strong id="forecast-day-total">{{ energy(selected) }} kWh</strong></div>
        <p id="forecast-day-coverage" class="muted">{{ selected ? `${t(selected.quality)} · ${t('coverage')} ${number(selected.coverage_percent)}%` : '' }}</p>
        <PowerChart id="forecast-chart" :points="points" :series="series" unit="W" :active="active && days.length > 0" :language="language" :timezone="timezone" :theme="theme" :current-time="currentTime" :tooltip="tooltip" />
        <p class="muted">{{ t('forecast_marker_help') }}</p>
        <details id="forecast-details"><summary id="forecast-details-label">{{ t('forecast_details') }}</summary>
          <p id="forecast-details-help" class="muted">{{ t('forecast_details_help') }}</p><p id="forecast-scroll-hint" class="muted">{{ t('forecast_scroll') }}</p>
          <div class="table-scroll" tabindex="0" role="region" aria-labelledby="forecast-details-label"><table aria-labelledby="forecast-details-label" aria-describedby="forecast-details-help"><thead><tr>
            <th>{{ t('forecast_period') }}</th><th>{{ t('forecast_poa') }} (W/m²)</th><th>{{ t('forecast_air') }} (°C)</th><th>{{ t('forecast_cell') }} (°C)</th><th>{{ t('forecast_power') }} (W)</th><th>{{ t('forecast_interval_energy') }} (kWh)</th>
          </tr></thead><tbody id="forecast-rows"><tr v-for="row in rows" :key="row.start"><td>
            <time :datetime="new Date(row.start * 1000).toISOString()" :aria-label="time(row.start)" :title="time(row.start)">{{ intervalTime(row.start) }}</time>
            <time :datetime="new Date(row.end * 1000).toISOString()" :aria-label="time(row.end)" :title="time(row.end)">→ {{ row.end === selected?.end ? `${date(row.end)} ` : '' }}{{ intervalTime(row.end) }}</time>
          </td><td>{{ number(row.poa_w_m2) }}</td><td>{{ number(row.air_temperature_c) }}</td><td>{{ number(row.cell_temperature_c) }}</td><td>{{ number(row.power_w) }}</td><td>{{ number(row.energy_kwh, 3) }}</td></tr></tbody></table></div>
        </details>
      </article>
    </div>
    <div class="inline-notes forecast-meta muted"><span id="forecast-fetched">{{ view?.fetched_at == null ? t('forecast_never_fetched') : t('forecast_fetched', { time: time(view.fetched_at) }) }}</span>
      <span id="forecast-timezone">{{ t('timezone') }}: {{ timezone }}</span><a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">{{ t('forecast_attribution') }}</a></div>
    <button id="open-forecast-settings" class="secondary" @click="$emit('open-settings', 'forecast')"><Settings :size="15" aria-hidden="true" />{{ t('forecast_configure') }}</button>
  </section>
</template>
