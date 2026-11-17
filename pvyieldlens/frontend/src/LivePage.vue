<script setup lang="ts">
import { computed, onUnmounted, ref, shallowRef, watch } from 'vue';
import { ArrowUpRight } from 'lucide-vue-next';
import MetricCard from './MetricCard.vue';
import PowerChart from './PowerChart.vue';
import DailyHistoryChart from './DailyHistoryChart.vue';
import HistoryRangeControl from './components/HistoryRangeControl.vue';
import type { ChartPoint, ChartSeries, ChartTooltip } from './charts';
import type { Configuration, GenerationView, HistorySelection, HistoryView, Snapshot } from './models';
import { api, ApiError } from './api';
import { useI18n, type Language } from './i18n';
import type { ColorMode } from './theme';
import { formatTimes } from './timezones';

const props = defineProps<{
  active: boolean; configuration: Configuration | null; snapshot: Snapshot | null;
  language: Language; theme: ColorMode; points: ChartPoint[]; displayTimezone: string;
  range: { start: number; end: number }; seriesError: string | null;
}>();
defineEmits<{ 'open-settings': [] }>();
const { t } = useI18n();
const live = computed(() => props.snapshot?.live_window);
const settings = computed(() => props.configuration?.monitoring_settings);
const generation = shallowRef<GenerationView | null>(null);
const history = shallowRef<HistoryView | null>(null);
const selection = ref<HistorySelection>({ period: '7d' });
const generationError = ref<string | null>(null);
const historyError = ref<string | null>(null);
const visible = ref(!document.hidden);
const updateVisibility = () => { visible.value = !document.hidden; };
document.addEventListener('visibilitychange', updateVisibility);
onUnmounted(() => { document.removeEventListener('visibilitychange', updateVisibility); generationRequest = null; historyRequest = null; });
const context = computed(() => props.snapshot && settings.value ? JSON.stringify([
  props.snapshot.revision, props.snapshot.latest_settled_window?.revision, props.snapshot.latest_settled_window?.end,
  props.snapshot.energy_totals.day, props.snapshot.home_timezone, settings.value,
]) : null);
const historyKey = computed(() => JSON.stringify([context.value, selection.value]));
let generationKey: string | null = null;
let lastHistoryKey: string | null = null;
let generationRequest: object | null = null;
let historyRequest: object | null = null;
watch([() => props.active, visible, context], async ([active, isVisible, key]) => {
  generationRequest = null;
  if (!active || !isVisible || !key || key === generationKey) return;
  const request = {};
  generationRequest = request;
  try {
    const result = await api.getGenerationData();
    if (generationRequest !== request) return;
    generation.value = result; generationError.value = null; generationKey = key;
  } catch (failure) {
    if (generationRequest === request) generationError.value = failure instanceof ApiError ? failure.code : 'error';
  }
}, { immediate: true });
watch([() => props.active, visible, historyKey], async ([active, isVisible, key]) => {
  historyRequest = null;
  if (!active || !isVisible || !context.value || key === lastHistoryKey) return;
  const request = {};
  historyRequest = request;
  try {
    const result = await api.getHistoryView(selection.value, false);
    if (historyRequest !== request) return;
    history.value = result; historyError.value = null; lastHistoryKey = key;
  } catch (failure) {
    if (historyRequest === request) historyError.value = failure instanceof ApiError ? failure.code : 'error';
  }
}, { immediate: true });
const powerSeries: ChartSeries[] = [
  { key: 'estimated_power_w', label: 'estimated_power', color: 'var(--pv-estimated)' },
  { key: 'actual_power_w', label: 'actual_power', color: 'var(--pv-actual)' },
];
const irradianceSeries: ChartSeries[] = [{ key: 'irradiance_w_m2', label: 'irradiance', color: 'var(--pv-estimated)' }];
const temperatureSeries: ChartSeries[] = [{ key: 'module_temperature_c', label: 'module_temperature', color: 'var(--pv-temperature)' }];
const generationPower = computed(() => generation.value?.windows.map((window, index, windows) => ({
  ...window, at: window.end, window, breakBefore: index > 0 && window.start > windows[index - 1].end,
})) ?? []);
const generationInputs = computed(() => generation.value?.inputs.map((point, index, inputs) => ({
  ...point, at: point.end, breakBefore: index > 0 && point.start > inputs[index - 1].end,
})) ?? []);
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const updated = computed(() => props.snapshot?.calculated_at == null ? '—'
  : formatTimes([props.snapshot.calculated_at], props.language, props.displayTimezone, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })[0]);
const pointLabels = computed(() => {
  const labels = formatTimes(props.points.map(point => point.at), props.language, props.displayTimezone, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
  return new Map(props.points.map((point, index) => [point.at, labels[index]]));
});
const tooltip = (point: ChartPoint): ChartTooltip => ({ title: pointLabels.value.get(point.at)!, rows: [
  { label: t('estimated_power'), value: number(point.window?.estimated_power_w) + ' W', color: powerSeries[0].color },
  { label: t('actual_power'), value: number(point.window?.actual_power_w) + ' W', color: powerSeries[1].color },
  { label: t('pr'), value: number(point.window?.pr) + ' %' },
  { label: t('optimizable_power'), value: number(point.window?.optimizable_power_w) + ' W' },
] });
</script>

<template>
  <section id="live-page" aria-labelledby="live-heading">
    <section v-show="configuration !== null && !settings" id="setup-empty" class="panel setup-empty">
      <h2>{{ t('empty_setup') }}</h2><p class="muted">{{ t('source_semantics') }}</p>
      <button id="open-settings" class="primary" @click="$emit('open-settings')">{{ t('open_settings') }}<ArrowUpRight :size="16" aria-hidden="true" /></button>
    </section>
    <div class="section-heading">
      <div><p class="eyebrow">{{ t('pv_modules') }} / {{ t('live_page') }}</p><h1 id="live-heading">{{ t('live_page') }}</h1>
        <p class="muted">{{ t('dashboard_hint') }}</p></div>
      <span id="updated" class="muted">{{ t('updated', { time: updated }) }}</span>
    </div>
    <div class="dashboard-grid">
      <div class="metrics live-metrics">
        <MetricCard :label="t('actual_power')" :value="number(live?.actual_power_w)" unit="W" :context="t('rolling_average', { seconds: settings?.live_window_seconds ?? 60 })" primary><span id="live-actual">{{ number(live?.actual_power_w) }}</span></MetricCard>
        <MetricCard :label="t('estimated_power')" :value="number(live?.estimated_power_w)" unit="W" :context="t('rolling_average', { seconds: settings?.live_window_seconds ?? 60 })"><span id="live-estimated">{{ number(live?.estimated_power_w) }}</span></MetricCard>
        <MetricCard :label="t('pr')" :value="number(live?.pr)" unit="%" :context="t('actual_over_estimated')"><span id="live-pr">{{ number(live?.pr) }}</span></MetricCard>
        <MetricCard :label="t('optimizable_power')" :value="number(live?.optimizable_power_w)" unit="W" :context="t('estimated_minus_actual')"><span id="live-optimizable-power">{{ number(live?.optimizable_power_w) }}</span></MetricCard>
      </div>
      <article class="panel live-panel">
        <div class="panel-heading"><h2>{{ t('live_data') }}</h2><div class="legend"><span class="estimated-dot">{{ t('estimated_power') }}</span><span class="actual-dot">{{ t('actual_power') }}</span></div></div>
        <p v-if="seriesError" id="live-series-error" class="muted" role="status">{{ t(seriesError) }}</p>
        <PowerChart id="live-chart" :points="points" :range="range" :series="powerSeries" unit="W" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" :tooltip="tooltip" />
        <p id="live-hint" class="chart-footer muted">{{ t('live_data_hint', { window: settings?.live_window_seconds ?? 60, interval: settings?.update_interval_seconds ?? 5 }) }}</p>
      </article>
      <article id="generation-data" class="panel generation-data">
        <div class="panel-heading"><h2>{{ t('generation_data') }}</h2></div>
        <p v-if="generationError" role="status" class="muted">{{ t(generationError) }}</p>
        <div class="generation-charts">
          <section class="generation-power">
            <div class="legend"><span class="estimated-dot">{{ t('estimated_power') }}</span><span class="actual-dot">{{ t('actual_power') }}</span></div>
            <PowerChart id="generation-power-chart" :points="generationPower" :range="generation?.requested_range" :series="powerSeries" unit="W" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" coverage="windows" />
          </section>
          <section>
            <div class="legend"><span class="estimated-dot">{{ t('irradiance') }}</span></div>
            <PowerChart id="generation-irradiance-chart" :points="generationInputs" :range="generation?.requested_range" :series="irradianceSeries" unit="W/m²" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" />
          </section>
          <section class="generation-temperature">
            <div class="legend"><span class="temperature-dot">{{ t('module_temperature') }}</span></div>
            <PowerChart id="generation-temperature-chart" :points="generationInputs" :range="generation?.requested_range" :series="temperatureSeries" unit="°C" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" />
          </section>
        </div>
      </article>
      <article class="panel dashboard-history">
        <div class="panel-heading"><h2>{{ t('historical_energy') }}</h2>
          <HistoryRangeControl id="dashboard-energy-range" v-model="selection" :presets="['7d', '30d', 'custom']" :today="snapshot?.energy_totals.day ?? ''" />
        </div>
        <p v-if="historyError" role="status" class="muted">{{ t(historyError) }}</p>
        <div class="energy-summary"><p class="muted">{{ t('actual_energy') }} <strong>{{ number(history?.summary.actual_energy_kwh, 2) }} kWh</strong> · {{ t('estimated_energy') }} <strong>{{ number(history?.summary.estimated_energy_kwh, 2) }} kWh</strong></p>
          <div class="legend"><span class="estimated-dot">{{ t('estimated_energy') }}</span><span class="actual-dot">{{ t('actual_energy') }}</span></div></div>
        <DailyHistoryChart id="dashboard-energy-chart" :days="history?.days ?? []" mode="energy" :active="active" :language="language" :theme="theme" :timezone="history?.home_timezone ?? snapshot?.home_timezone ?? 'UTC'" />
      </article>
    </div>
  </section>
</template>
