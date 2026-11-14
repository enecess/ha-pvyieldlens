<script setup lang="ts">
import { computed } from 'vue';
import { Radio, ArrowUpRight } from 'lucide-vue-next';
import MetricCard from './MetricCard.vue';
import PowerChart from './PowerChart.vue';
import type { ChartPoint, ChartSeries } from './charts';
import type { Configuration, Snapshot } from './models';
import { useI18n, type Language } from './i18n';
import type { ColorMode } from './theme';

const props = defineProps<{
  active: boolean; configuration: Configuration | null; snapshot: Snapshot | null;
  language: Language; theme: ColorMode; points: ChartPoint[];
}>();
defineEmits<{ 'open-settings': [] }>();
const { t } = useI18n();
const live = computed(() => props.snapshot?.realtime);
const settings = computed(() => props.configuration?.settings);
const timezone = computed(() => props.snapshot?.timezone ?? settings.value?.timezone ?? 'UTC');
const powerSeries: ChartSeries[] = [
  { key: 'estimated_power', label: 'estimated', color: 'var(--pv-theoretical)' },
  { key: 'actual_power', label: 'actual', color: 'var(--pv-actual)' },
];
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const updated = computed(() => props.snapshot?.calculated_at == null ? '—' : new Intl.DateTimeFormat(props.language, {
  hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: timezone.value,
}).format(new Date(props.snapshot.calculated_at * 1000)));
</script>

<template>
  <section id="live-page" aria-labelledby="live-heading">
    <section v-show="configuration !== null && !settings" id="setup-empty" class="panel setup-empty">
      <h2>{{ t('empty_setup') }}</h2><p class="muted">{{ t('source_semantics') }}</p>
      <button id="open-settings" class="primary" @click="$emit('open-settings')">{{ t('open_settings') }}<ArrowUpRight :size="16" aria-hidden="true" /></button>
    </section>
    <div class="section-heading">
      <div><p class="eyebrow">SOLAR / {{ t('live_page') }}</p><h1 id="live-heading">{{ t('realtime') }}</h1>
        <p id="live-hint" class="muted">{{ t('realtime_hint', { window: settings?.realtime_window_seconds ?? 60, interval: settings?.update_seconds ?? 5 }) }}</p></div>
      <span id="updated" class="muted">{{ t('updated', { time: updated }) }}</span>
    </div>
    <div class="metrics live-metrics">
      <MetricCard :label="t('actual')" :value="number(live?.actual_power)" unit="W" :context="settings?.power_entity" primary><span id="live-actual">{{ number(live?.actual_power) }}</span></MetricCard>
      <MetricCard :label="t('estimated')" :value="number(live?.estimated_power)" unit="W" :context="t('stat_value_hint')"><span id="live-estimated">{{ number(live?.estimated_power) }}</span></MetricCard>
      <MetricCard :label="t('pr')" :value="number(live?.pr)" unit="%"><span id="live-pr">{{ number(live?.pr) }}</span></MetricCard>
      <MetricCard :label="t('opportunity')" :value="number(live?.optimizable_power)" unit="W"><span id="live-opportunity">{{ number(live?.optimizable_power) }}</span></MetricCard>
    </div>
    <article class="panel live-panel">
      <div class="panel-heading"><h2>{{ t('power_chart') }}</h2><div class="legend"><span class="actual-dot">{{ t('actual') }}</span><span class="theoretical-dot">{{ t('estimated') }}</span></div></div>
      <PowerChart id="live-chart" :points="points" :series="powerSeries" unit="W" :active="active" :language="language" :timezone="timezone" :theme="theme" />
      <p v-if="live?.reason" id="live-reason" class="muted">{{ t(live.reason) }}</p>
      <div class="live-status muted"><span id="live-quality"><span class="status-dot" :class="{ good: live?.quality === 'complete' }"></span>{{ t(live?.quality ?? 'waiting') }}</span>
        <span><span id="live-coverage" :title="t('coverage_help')">{{ t('coverage') }} {{ number(live?.coverage_percent) }}%</span> · {{ timezone }}</span></div>
    </article>
    <details id="source-diagnostics" class="panel quality-panel">
      <summary><Radio :size="16" aria-hidden="true" />{{ t('diagnostics') }}</summary>
      <div class="panel-heading"><h2>{{ t('quality') }}</h2><span id="timezone-note" class="muted">{{ t('timezone') }}: {{ timezone }}</span></div>
      <div class="table-scroll"><table><thead><tr><th>{{ t('source') }}</th><th>{{ t('value') }}</th><th>{{ t('age') }}</th></tr></thead>
        <tbody id="source-rows"><tr v-for="source in snapshot?.sources ?? []" :key="source.entity_id"><td>{{ source.entity_id }}</td><td>{{ source.valid ? `${number(Number(source.state), 2)} ${source.unit ?? ''}` : t('unavailable') }}</td><td>{{ number(Math.max(0, Date.now() / 1000 - source.reported_at), 0) }} s</td></tr></tbody>
        <tbody v-show="!snapshot?.sources.length" id="source-empty"><tr><td colspan="3" class="source-empty muted">{{ t('no_sensor_data') }}</td></tr></tbody>
      </table></div>
    </details>
  </section>
</template>
