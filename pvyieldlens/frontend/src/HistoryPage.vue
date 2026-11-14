<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue';
import MetricCard from './MetricCard.vue';
import PowerChart from './PowerChart.vue';
import { api, ApiError } from './api';
import type { ChartPoint, ChartSeries } from './charts';
import type { Configuration, HistorySummary, Snapshot } from './models';
import { useI18n, type Language } from './i18n';
import type { ColorMode } from './theme';

const props = defineProps<{
  active: boolean; configuration: Configuration | null; snapshot: Snapshot | null; language: Language; theme: ColorMode;
}>();
const { t } = useI18n();
const range = ref('1');
const points = shallowRef<(ChartPoint & { start: number })[]>([]);
const summary = shallowRef<HistorySummary | null>(null);
const error = ref<string | null>(null);
const timezone = computed(() => props.snapshot?.timezone ?? props.configuration?.settings?.timezone ?? 'UTC');
const powerSeries: ChartSeries[] = [
  { key: 'estimated_power', label: 'estimated', color: 'var(--pv-theoretical)' },
  { key: 'actual_power', label: 'actual', color: 'var(--pv-actual)' },
];
const prSeries: ChartSeries[] = [{ key: 'pr', label: 'pr', color: 'var(--pv-actual)' }];
let lastKey: string | null = null;
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const stamp = (at: number | null | undefined) => at == null ? '—' : new Intl.DateTimeFormat(props.language, {
  hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: timezone.value,
}).format(new Date(at * 1000));
const boundaries = computed(() => {
  if (summary.value?.start == null || summary.value.end == null) return t('history_no_periods');
  const format = new Intl.DateTimeFormat(props.language, { year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: timezone.value });
  return t('history_boundaries', { start: format.format(new Date(summary.value.start * 1000)),
    end: format.format(new Date(summary.value.end * 1000)), timezone: timezone.value });
});

watch(() => [props.active, range.value, props.snapshot, props.configuration?.settings], async () => {
  if (!props.active || !props.snapshot || !props.configuration) return;
  const key = `${props.snapshot.revision}|${props.snapshot.statistics?.revision}|${props.snapshot.statistics?.end}|${range.value}|${JSON.stringify(props.configuration.settings)}`;
  const end = Date.now() / 1000;
  const start = Math.max(0, end - Number(range.value) * 86400);
  if (key === lastKey && !points.value.some(point => point.start < start)) return;
  try {
    const result = await api.getHistory(start, end);
    points.value = result.windows.filter(point => point.start >= result.requested_range.start && point.end <= result.requested_range.end)
      .map(point => ({ ...point, at: point.end }));
    summary.value = result.summary;
    error.value = null;
    lastKey = key;
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'error';
  }
}, { immediate: true });
</script>

<template>
  <section id="history-page" aria-labelledby="history-heading">
    <div class="section-heading"><div><p class="eyebrow">SOLAR / {{ t('history') }}</p><h1 id="history-heading">{{ t('statistics') }}</h1>
      <p id="statistics-hint" class="muted">{{ t('statistics_hint', { interval: configuration?.settings?.interval_minutes ?? 5 }) }}</p></div>
      <select id="history-range" v-model="range" :aria-label="t('history')"><option value="1">{{ t('last_24h') }}</option><option value="7">{{ t('last_7d') }}</option><option value="30">{{ t('last_30d') }}</option></select></div>
    <p v-if="error" class="banner" role="status">{{ t(error) }}</p>
    <div class="metrics history-metrics">
      <MetricCard :label="t('range_energy')" :value="number(summary?.estimated_energy_kwh, 3)" unit="kWh" primary><span id="history-energy">{{ number(summary?.estimated_energy_kwh, 3) }}</span></MetricCard>
      <MetricCard :label="t('range_pr')" :value="number(summary?.pr)" unit="%"><span id="history-pr">{{ number(summary?.pr) }}</span></MetricCard>
      <MetricCard :label="t('coverage')" :value="`${number(summary?.coverage_percent)}%`"><span id="stat-coverage" :title="t('coverage_help')">{{ number(summary?.coverage_percent) }}%</span></MetricCard>
    </div>
    <p id="history-boundaries" class="muted">{{ boundaries }}</p>
    <div class="history-grid">
      <article class="panel"><div class="panel-heading"><h2>{{ t('power_chart') }}</h2><div class="legend"><span class="actual-dot">{{ t('actual') }}</span><span class="theoretical-dot">{{ t('estimated') }}</span></div></div>
        <PowerChart id="history-chart" :points="points" :series="powerSeries" unit="W" :active="active" :language="language" :timezone="timezone" :theme="theme" /></article>
      <article class="panel"><div class="panel-heading"><h2>{{ t('pr_chart') }}</h2></div>
        <PowerChart id="pr-chart" :points="points" :series="prSeries" unit="%" :active="active" :language="language" :timezone="timezone" :theme="theme" /></article>
    </div>
    <div class="inline-notes muted"><span id="last-settled">{{ t('last_settled', { time: stamp(snapshot?.statistics?.end) }) }}</span><span>{{ t('settled_hint') }}</span></div>
    <details id="history-totals" class="panel totals-fold"><summary>{{ t('totals') }}</summary>
      <div class="fixed-totals"><div><span>{{ t('daily') }}</span><strong id="daily-energy">{{ number(snapshot?.energy.daily_kwh, 3) }}</strong><span class="unit">kWh</span></div>
        <div><span>{{ t('total') }}</span><strong id="total-energy">{{ number(snapshot?.energy.total_kwh, 3) }}</strong><span class="unit">kWh</span></div></div>
      <p class="muted">{{ t('totals_help') }}</p><p class="muted">{{ t('energy_help') }}</p>
    </details>
  </section>
</template>
