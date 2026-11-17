<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue';
import MetricCard from './MetricCard.vue';
import PowerChart from './PowerChart.vue';
import DailyHistoryChart from './DailyHistoryChart.vue';
import { api, ApiError } from './api';
import type { ChartPoint, ChartSeries, ChartTooltip } from './charts';
import type { Configuration, HistoryPeriod, HistoryView, HistoryWindow, Snapshot } from './models';
import { useI18n, type Language } from './i18n';
import type { ColorMode } from './theme';
import { formatTimes } from './timezones';

const props = defineProps<{
  active: boolean; configuration: Configuration | null; snapshot: Snapshot | null; language: Language; theme: ColorMode; displayTimezone: string;
}>();
const { t } = useI18n();
const range = ref<HistoryPeriod>('today');
const points = shallowRef<(ChartPoint & { start: number })[]>([]);
const view = shallowRef<HistoryView | null>(null);
const summary = computed(() => view.value?.summary);
const detailRange = computed(() => points.value.length ? { start: points.value[0].start, end: points.value.at(-1)!.at } : undefined);
const error = ref<string | null>(null);
const homeTimezone = computed(() => new Intl.DateTimeFormat('en', {
  timeZone: view.value?.home_timezone ?? props.snapshot?.home_timezone ?? props.configuration?.monitoring_settings?.home_timezone ?? 'UTC',
}).resolvedOptions().timeZone);
const powerSeries: ChartSeries[] = [
  { key: 'estimated_power_w', label: 'estimated_power', color: 'var(--pv-estimated)' },
  { key: 'actual_power_w', label: 'actual_power', color: 'var(--pv-actual)' },
];
const prSeries: ChartSeries[] = [{ key: 'pr', label: 'pr', color: 'var(--pv-actual)' }];
let lastKey: string | null = null;
let pendingRequest: { key: string } | null = null;
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const settled = computed(() => props.snapshot?.latest_settled_window?.end == null ? '—'
  : formatTimes([props.snapshot.latest_settled_window.end], props.language, props.displayTimezone, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })[0]);
const boundaries = computed(() => {
  if (summary.value?.start == null || summary.value.end == null) return t('history_no_periods');
  const [start, end] = formatTimes([summary.value.start, summary.value.end], props.language, props.displayTimezone, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
  return t('history_boundaries', { start, end });
});
const pointLabels = computed(() => {
  const labels = formatTimes(points.value.flatMap(point => [point.window!.start, point.window!.end]), props.language, props.displayTimezone, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
  return new Map(points.value.map((point, index) => [point.at, `${labels[index * 2]} – ${labels[index * 2 + 1]}`]));
});
const tooltip = (point: ChartPoint): ChartTooltip => {
  const window = point.window as HistoryWindow;
  return { title: pointLabels.value.get(point.at)!, rows: [
  { label: t('estimated_power'), value: `${number(window.estimated_power_w)} W`, color: powerSeries[0].color },
  { label: t('actual_power'), value: `${number(window.actual_power_w)} W`, color: powerSeries[1].color },
  { label: t('pr'), value: `${number(window.pr)} %` },
  { label: t('data_completeness'), value: `${number(window.data_completeness_percent)} %` },
  { label: t('data_quality'), value: t(window.quality) },
  ...(window.source_start != null ? [
    { label: t('history_fragment'), value: t('history_fragment_help') },
    { label: t('original_settled_window'), value: formatTimes([
      window.source_start,
      window.source_end!,
    ], props.language, props.displayTimezone, {
      year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    }).join(' – ') },
  ] : []),
] };
};

watch(() => [props.active, range.value, props.snapshot, props.configuration?.monitoring_settings], async () => {
  if (!props.active || !props.snapshot || !props.configuration) { pendingRequest = null; return; }
  const key = `${props.snapshot.revision}|${props.snapshot.latest_settled_window?.revision}|${props.snapshot.latest_settled_window?.end}|${range.value}|${props.snapshot.energy_totals.day}|${props.snapshot.home_timezone}|${JSON.stringify(props.configuration.monitoring_settings)}`;
  if (key === lastKey && !(range.value === '24h' && points.value.some(point => point.start < Date.now() / 1000 - 86400))) { pendingRequest = null; return; }
  if (pendingRequest?.key === key) return;
  const request = { key };
  pendingRequest = request;
  try {
    const result = await api.getHistoryPeriod(range.value);
    if (pendingRequest !== request) return;
    points.value = result.windows.filter(point => point.start >= result.requested_range.start && point.end <= result.requested_range.end)
      .map((point, index, windows) => ({ ...point, at: point.end, window: point,
        breakBefore: index > 0 && point.start > windows[index - 1].end }));
    view.value = result;
    error.value = null;
    lastKey = key;
  } catch (failure) {
    if (pendingRequest !== request) return;
    error.value = failure instanceof ApiError ? failure.code : 'error';
  } finally {
    if (pendingRequest === request) pendingRequest = null;
  }
}, { immediate: true });
</script>

<template>
  <section id="history-page" aria-labelledby="history-heading">
    <div class="section-heading"><div><p class="eyebrow">{{ t('pv_modules') }} / {{ t('history') }}</p><h1 id="history-heading">{{ t('history') }}</h1>
      <p id="history-hint" class="muted">{{ t('history_interval_hint', { interval: configuration?.monitoring_settings?.settlement_interval_minutes ?? 5 }) }}</p></div>
      <select id="history-range" v-model="range" :aria-label="t('history')"><option value="today">{{ t('today') }}</option><option value="24h">{{ t('last_24h') }}</option><option value="7d">{{ t('last_7d') }}</option><option value="30d">{{ t('last_30d') }}</option></select></div>
    <p v-if="range !== '24h' && homeTimezone !== displayTimezone" id="history-home-timezone" class="muted">{{ t('history_home_time', { timezone: homeTimezone }) }}</p>
    <p v-if="error" class="banner" role="status">{{ t(error) }}</p>
    <div class="metrics history-metrics">
      <MetricCard :label="t('range_actual_energy')" :value="number(summary?.actual_energy_kwh, 3)" unit="kWh" primary><span id="history-actual-energy">{{ number(summary?.actual_energy_kwh, 3) }}</span></MetricCard>
      <MetricCard :label="t('range_estimated_energy')" :value="number(summary?.estimated_energy_kwh, 3)" unit="kWh"><span id="history-energy">{{ number(summary?.estimated_energy_kwh, 3) }}</span></MetricCard>
      <MetricCard :label="t('range_pr')" :value="number(summary?.pr)" unit="%"><span id="history-pr">{{ number(summary?.pr) }}</span></MetricCard>
      <MetricCard :label="t('data_completeness')" :value="`${number(summary?.data_completeness_percent)}%`"><span id="history-data-completeness" :title="t('monitoring_data_completeness_help')">{{ number(summary?.data_completeness_percent) }}%</span></MetricCard>
    </div>
    <p id="history-boundaries" class="muted">{{ boundaries }}</p>
    <p v-if="view?.boundary_unavailable" id="history-boundary-unavailable" class="banner" role="status">{{ t('history_boundary_unavailable') }}</p>
    <div class="history-grid">
      <template v-if="range === '7d' || range === '30d'">
        <article class="panel"><div class="panel-heading"><h2>{{ t('history_daily_energy') }}</h2><div class="legend"><span class="estimated-dot">{{ t('estimated_energy') }}</span><span class="actual-dot">{{ t('actual_energy') }}</span></div></div>
          <DailyHistoryChart id="daily-energy-chart" :days="view?.days ?? []" mode="energy" :active="active" :language="language" :theme="theme" :timezone="homeTimezone" /></article>
        <article class="panel"><div class="panel-heading"><h2>{{ t('history_daily_pr') }}</h2></div>
          <DailyHistoryChart id="daily-pr-chart" :days="view?.days ?? []" mode="pr" :active="active" :language="language" :theme="theme" :timezone="homeTimezone" /></article>
      </template>
      <article class="panel"><div class="panel-heading"><h2>{{ t('power_chart') }}</h2><div class="legend"><span class="actual-dot">{{ t('actual_power') }}</span><span class="estimated-dot">{{ t('estimated_power') }}</span></div></div>
        <PowerChart id="history-chart" :points="points" :series="powerSeries" unit="W" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" :tooltip="tooltip" :range="detailRange" coverage="windows" /></article>
      <article class="panel"><div class="panel-heading"><h2>{{ t('pr_chart') }}</h2></div>
        <PowerChart id="pr-chart" :points="points" :series="prSeries" unit="%" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" :tooltip="tooltip" :range="detailRange" coverage="windows" /></article>
    </div>
    <div class="inline-notes muted"><span id="last-settled">{{ t('last_settled', { time: settled }) }}</span><span>{{ t('settled_hint') }}</span></div>
  </section>
</template>
