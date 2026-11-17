<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import { Radio, ArrowUpRight } from 'lucide-vue-next';
import MetricCard from './MetricCard.vue';
import PowerChart from './PowerChart.vue';
import type { ChartPoint, ChartSeries, ChartTooltip } from './charts';
import type { Configuration, Snapshot, SourceDiagnostics } from './models';
import { api } from './api';
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
const diagnostics = ref<SourceDiagnostics | null>(null);
const diagnosticsExpanded = ref(false);
const diagnosticsError = ref(false);
const visible = ref(!document.hidden);
const now = ref(performance.now());
let observedAtMonotonic = now.value;
const sourceContext = computed(() => settings.value ? JSON.stringify([
  settings.value.actual_power_entity, settings.value.module_temperature_entity, settings.value.irradiance_entity,
]) : null);
const updateVisibility = () => { visible.value = !document.hidden; };
document.addEventListener('visibilitychange', updateVisibility);
onUnmounted(() => { document.removeEventListener('visibilitychange', updateVisibility); });
watch([sourceContext, diagnosticsExpanded, () => props.active, visible], ([sources, expanded, active, isVisible], previous, onCleanup) => {
  if (sources !== previous?.[0]) {
    diagnostics.value = null;
    diagnosticsError.value = false;
  }
  if (!sources || !expanded || !active || !isVisible) return;
  const controller = new AbortController();
  let nextRead: ReturnType<typeof setTimeout> | undefined;
  now.value = performance.now();
  const clock = setInterval(() => { now.value = performance.now(); }, 1000);
  onCleanup(() => { controller.abort(); clearTimeout(nextRead); clearInterval(clock); });
  async function refresh() {
    try {
      const result = await api.getSourceDiagnostics(controller.signal);
      if (controller.signal.aborted) return;
      observedAtMonotonic = performance.now();
      now.value = observedAtMonotonic;
      diagnostics.value = result;
      diagnosticsError.value = false;
    } catch {
      if (!controller.signal.aborted) diagnosticsError.value = true;
    } finally {
      if (!controller.signal.aborted) nextRead = setTimeout(refresh, 1000);
    }
  }
  void refresh();
}, { immediate: true });
const powerSeries: ChartSeries[] = [
  { key: 'estimated_power_w', label: 'estimated_power', color: 'var(--pv-estimated)' },
  { key: 'actual_power_w', label: 'actual_power', color: 'var(--pv-actual)' },
];
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const sourceAge = (reportedAt: number | null) => {
  if (reportedAt === null || diagnostics.value?.observed_at == null) return '—';
  const elapsed = Math.max(0, diagnostics.value.observed_at + (now.value - observedAtMonotonic) / 1000 - reportedAt);
  return elapsed < 1 ? t('just_now') : `${number(Math.floor(elapsed), 0)} s`;
};
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
  { label: t('estimated_power'), value: `${number(point.window?.estimated_power_w)} W`, color: powerSeries[0].color },
  { label: t('actual_power'), value: `${number(point.window?.actual_power_w)} W`, color: powerSeries[1].color },
  { label: t('pr'), value: `${number(point.window?.pr)} %` },
  { label: t('optimizable_power'), value: `${number(point.window?.optimizable_power_w)} W` },
  { label: t('data_completeness'), value: `${number(point.window?.data_completeness_percent)} %` },
  { label: t('data_quality'), value: t(point.window?.quality ?? 'unavailable') },
] });
</script>

<template>
  <section id="live-page" aria-labelledby="live-heading">
    <section v-show="configuration !== null && !settings" id="setup-empty" class="panel setup-empty">
      <h2>{{ t('empty_setup') }}</h2><p class="muted">{{ t('source_semantics') }}</p>
      <button id="open-settings" class="primary" @click="$emit('open-settings')">{{ t('open_settings') }}<ArrowUpRight :size="16" aria-hidden="true" /></button>
    </section>
    <div class="section-heading">
      <div><p class="eyebrow">{{ t('pv_modules') }} / {{ t('live_page') }}</p><h1 id="live-heading">{{ t('live_data') }}</h1>
        <p id="live-hint" class="muted">{{ t('live_data_hint', { window: settings?.live_window_seconds ?? 60, interval: settings?.update_interval_seconds ?? 5 }) }}</p></div>
      <span id="updated" class="muted">{{ t('updated', { time: updated }) }}</span>
    </div>
    <div class="metrics live-metrics">
      <MetricCard :label="t('actual_power')" :value="number(live?.actual_power_w)" unit="W" :context="settings?.actual_power_entity" primary><span id="live-actual">{{ number(live?.actual_power_w) }}</span></MetricCard>
      <MetricCard :label="t('estimated_power')" :value="number(live?.estimated_power_w)" unit="W" :context="t('stat_value_hint')"><span id="live-estimated">{{ number(live?.estimated_power_w) }}</span></MetricCard>
      <MetricCard :label="t('pr')" :value="number(live?.pr)" unit="%"><span id="live-pr">{{ number(live?.pr) }}</span></MetricCard>
      <MetricCard :label="t('optimizable_power')" :value="number(live?.optimizable_power_w)" unit="W"><span id="live-optimizable-power">{{ number(live?.optimizable_power_w) }}</span></MetricCard>
    </div>
    <article class="panel live-panel">
      <div class="panel-heading"><h2>{{ t('power_chart') }}</h2><div class="legend"><span class="actual-dot">{{ t('actual_power') }}</span><span class="estimated-dot">{{ t('estimated_power') }}</span></div></div>
      <p v-if="seriesError" id="live-series-error" class="muted" role="status">{{ t(seriesError) }}</p>
      <PowerChart id="live-chart" :points="points" :range="range" :series="powerSeries" unit="W" :active="active" :language="language" :timezone="displayTimezone" :theme="theme" :tooltip="tooltip" />
      <p v-if="live?.reason" id="live-reason" class="muted">{{ t(live.reason) }}</p>
      <div class="live-status muted"><span id="live-quality"><span class="status-dot" :class="{ good: live?.quality === 'complete' }"></span>{{ t(live?.quality ?? 'waiting') }}</span>
        <span><span id="live-data-completeness" :title="t('monitoring_data_completeness_help')">{{ t('data_completeness') }} {{ number(live?.data_completeness_percent) }}%</span></span></div>
    </article>
    <details id="source-diagnostics" class="panel quality-panel" @toggle="diagnosticsExpanded = ($event.target as HTMLDetailsElement).open">
      <summary><Radio :size="16" aria-hidden="true" />{{ t('diagnostics') }}</summary>
      <div class="panel-heading"><h2>{{ t('sensors') }}</h2></div>
      <p v-if="diagnosticsError" id="source-diagnostics-error" class="muted" role="status">{{ t('ha_connection_failed') }}</p>
      <div class="table-scroll"><table><thead><tr><th>{{ t('source') }}</th><th>{{ t('value') }}</th><th>{{ t('time_since_last_report') }}</th></tr></thead>
        <tbody id="source-rows"><tr v-for="source in diagnostics?.sources ?? []" :key="source.entity_id"><td>{{ source.entity_id }}</td><td>{{ source.valid ? `${number(Number(source.state), 2)} ${source.unit ?? ''}` : t('unavailable') }}</td><td>{{ sourceAge(source.reported_at) }}</td></tr></tbody>
        <tbody v-show="!diagnostics?.sources.length" id="source-empty"><tr><td colspan="3" class="source-empty muted">{{ t('no_sensor_data') }}</td></tr></tbody>
      </table></div>
    </details>
  </section>
</template>
