<script setup lang="ts">
import { computed, onUnmounted, ref, shallowRef, watch } from 'vue';
import MetricCard from './MetricCard.vue';
import PowerChart from './PowerChart.vue';
import DailyHistoryChart from './DailyHistoryChart.vue';
import HistoryRangeControl from './components/HistoryRangeControl.vue';
import { api, ApiError } from './api';
import type { ChartPoint, ChartSeries, ChartTooltip } from './charts';
import type { Configuration, HistorySelection, HistoryView, HistoryWindow, Snapshot } from './models';
import { useI18n, type Language } from './i18n';
import type { ColorMode } from './theme';
import { formatTimes } from './timezones';

const props = defineProps<{
  active: boolean; configuration: Configuration | null; snapshot: Snapshot | null; language: Language; theme: ColorMode; displayTimezone: string;
}>();
const { t } = useI18n();
const selection = ref<HistorySelection>({ period: 'today' });
const aggregation = ref<'day' | 'settlement'>('settlement');
const view = shallowRef<HistoryView | null>(null);
const summary = computed(() => view.value?.summary);
const points = computed(() => view.value?.windows.filter(window => window.start >= view.value!.requested_range.start && window.end <= view.value!.requested_range.end)
  .map((window, index, windows) => ({ ...window, at: window.end, window, breakBefore: index > 0 && window.start > windows[index - 1].end })) ?? []);
const calendar = computed(() => selection.value.period === '7d' || selection.value.period === '30d');
const daily = computed(() => calendar.value && aggregation.value === 'day');
const error = ref<string | null>(null);
const visible = ref(!document.hidden);
const updateVisibility = () => { visible.value = !document.hidden; };
document.addEventListener('visibilitychange', updateVisibility);
onUnmounted(() => { document.removeEventListener('visibilitychange', updateVisibility); pendingRequest = null; });
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
const energyGap = computed(() => summary.value?.estimated_energy_kwh == null || summary.value.actual_energy_kwh == null ? null
  : summary.value.estimated_energy_kwh - summary.value.actual_energy_kwh);
const prChange = computed(() => view.value?.comparison?.pr_change_pp);
const boundaries = computed(() => {
  if (!view.value) return '';
  return formatTimes([view.value.requested_range.start, view.value.requested_range.end], props.language,
    selection.value.period === '24h' ? props.displayTimezone : homeTimezone.value, {
      year: 'numeric', month: 'short', day: 'numeric', ...(!calendar.value ? { hour: '2-digit', minute: '2-digit' } as const : {}),
    }).join(' – ');
});
const tooltip = (point: ChartPoint): ChartTooltip => {
  const window = point.window as HistoryWindow;
  return { title: formatTimes([window.start, window.end], props.language, props.displayTimezone, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).join(' – '), rows: [
    { label: t('estimated_power'), value: number(window.estimated_power_w) + ' W', color: powerSeries[0].color },
    { label: t('actual_power'), value: number(window.actual_power_w) + ' W', color: powerSeries[1].color },
    { label: t('pr'), value: number(window.pr) + ' %' },
  ] };
};
function selectRange(value: HistorySelection) {
  selection.value = value;
  aggregation.value = calendar.value ? 'day' : 'settlement';
}
const context = computed(() => props.snapshot && props.configuration?.monitoring_settings ? JSON.stringify([
  props.snapshot.revision, props.snapshot.latest_settled_window?.revision, props.snapshot.latest_settled_window?.end,
  props.snapshot.energy_totals.day, props.snapshot.home_timezone, props.configuration.monitoring_settings, selection.value,
]) : null);
watch([() => props.active, visible, context, () => props.snapshot], async ([active, isVisible, key], previous) => {
  if (!active || !isVisible || !key) { pendingRequest = null; return; }
  const rollingWindowExpired = selection.value.period === '24h' && points.value.some(point =>
    point.start < Date.now() / 1000 - 86400);
  if (pendingRequest?.key === key) return;
  if (key === lastKey && (error.value ? previous?.[0] && previous?.[1] : !rollingWindowExpired)) return;
  const request = { key };
  pendingRequest = request;
  try {
    const result = await api.getHistoryView(selection.value, true);
    if (pendingRequest !== request) return;
    view.value = result; error.value = null; lastKey = key;
  } catch (failure) {
    if (pendingRequest === request) {
      error.value = failure instanceof ApiError ? failure.code : 'error';
      lastKey = key;
    }
  } finally {
    if (pendingRequest === request) pendingRequest = null;
  }
}, { immediate: true });
</script>

<template>
  <section id="history-page" aria-labelledby="history-heading">
    <div class="section-heading"><div><p class="eyebrow">{{ t('pv_modules') }} / {{ t('history') }}</p><h1 id="history-heading">{{ t('history') }}</h1></div>
      <HistoryRangeControl id="history-range" :model-value="selection" @update:model-value="selectRange" :presets="['today', '24h', '7d', '30d']" :today="snapshot?.energy_totals.day ?? ''" /></div>
    <p v-if="selection.period !== '24h' && homeTimezone !== displayTimezone" id="history-home-timezone" class="muted">{{ t('history_home_time', { timezone: homeTimezone }) }}</p>
    <p v-if="error" class="banner" role="status">{{ t(error) }}</p>
    <div class="metrics history-metrics">
      <MetricCard :label="t('range_pr')" :value="number(summary?.pr)" unit="%" :context="t('range_pr_formula')" primary><span id="history-pr">{{ number(summary?.pr) }}</span></MetricCard>
      <MetricCard :label="t('pr_change')" :value="number(prChange)" :unit="t('percentage_points')" :context="t(selection.period === 'today' ? 'compare_yesterday' : selection.period === '24h' ? 'compare_24h' : 'compare_days', { days: selection.period === '30d' ? 30 : 7 })">
        <span id="history-pr-change">{{ prChange == null ? '—' : (prChange > 0 ? '+' : '') + number(prChange) }}</span></MetricCard>
      <MetricCard :label="t('energy_gap')" :value="number(energyGap, 3)" unit="kWh" :context="t('estimated_minus_actual_energy')"><span id="history-energy-gap">{{ number(energyGap, 3) }}</span></MetricCard>
    </div>
    <div class="history-toolbar"><p id="history-range-caption" class="muted">{{ boundaries }}</p>
      <div v-if="calendar" id="history-aggregation" class="segmented" role="group" :aria-label="t('aggregation')">
        <button type="button" data-value="day" :aria-pressed="aggregation === 'day'" @click="aggregation = 'day'">{{ t('daily_summary') }}</button>
        <button type="button" data-value="settlement" :aria-pressed="aggregation === 'settlement'" @click="aggregation = 'settlement'">{{ t('every_minutes', { minutes: configuration?.monitoring_settings?.settlement_interval_minutes ?? 5 }) }}</button>
      </div>
    </div>
    <div class="history-grid">
      <article class="panel"><div class="panel-heading"><h2>{{ t('pr_chart') }}</h2><div class="legend"><span class="actual-dot">{{ t('pr') }}</span><span class="reference-dot">{{ t('pr_reference') }}</span></div></div>
        <DailyHistoryChart v-if="daily" id="daily-pr-chart" :days="view?.days ?? []" mode="pr" :active="active" :language="language" :theme="theme" :timezone="homeTimezone" />
        <PowerChart v-else id="pr-chart" :points="points" :series="prSeries" unit="%" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" :tooltip="tooltip" :range="view?.requested_range" coverage="windows" /></article>
      <article class="panel"><div class="panel-heading"><h2>{{ t('generation_comparison') }}</h2><div class="legend"><span class="estimated-dot">{{ t(daily ? 'estimated_energy' : 'estimated_power') }}</span><span class="actual-dot">{{ t(daily ? 'actual_energy' : 'actual_power') }}</span></div></div>
        <p class="muted energy-summary">{{ t('actual_energy') }} <strong id="history-actual-energy">{{ number(summary?.actual_energy_kwh, 3) }}</strong> kWh · {{ t('estimated_energy') }} <strong id="history-energy">{{ number(summary?.estimated_energy_kwh, 3) }}</strong> kWh</p>
        <DailyHistoryChart v-if="daily" id="daily-energy-chart" :days="view?.days ?? []" mode="energy" :active="active" :language="language" :theme="theme" :timezone="homeTimezone" />
        <PowerChart v-else id="history-chart" :points="points" :series="powerSeries" unit="W" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" :tooltip="tooltip" :range="view?.requested_range" coverage="windows" /></article>
    </div>
  </section>
</template>
