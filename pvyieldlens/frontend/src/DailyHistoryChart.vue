<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { HistoryDay } from './models';
import { catalogs, translate, type Language } from './i18n';
import type { ColorMode } from './theme';
import { formatTimes } from './timezones';

const props = defineProps<{
  days: HistoryDay[]; mode: 'energy' | 'pr'; active: boolean; language: Language; theme: ColorMode; timezone: string;
}>();
const t = (key: string, values?: Record<string, string | number>) => translate(catalogs, props.language, key, values);
const host = ref<HTMLElement>();
const tip = ref<HTMLElement>();
const hit = ref<SVGElement>();
const width = ref(600);
const height = ref(260);
const selected = ref<number | null>(null);
const tipStyle = ref({ left: '0px', top: '0px', maxHeight: '260px', pointerEvents: 'none' as 'none' | 'auto' });
let resize: ResizeObserver;
const number = (value: number | null, digits = 1) => value == null ? '—' :
  new Intl.NumberFormat(props.language, { maximumFractionDigits: digits }).format(value);
const date = (day: string, full = false) => new Intl.DateTimeFormat(props.language, {
  timeZone: 'UTC', ...(full ? { year: 'numeric' as const, month: 'short' as const, day: 'numeric' as const }
    : { month: 'numeric' as const, day: 'numeric' as const }),
}).format(new Date(`${day}T12:00:00Z`));
const plotWidth = computed(() => Math.max(1, width.value - 60));
const plotHeight = computed(() => Math.max(1, height.value - 50));
const slot = computed(() => plotWidth.value / Math.max(1, props.days.length));
const x = (index: number) => 48 + (index + 0.5) * slot.value;
const values = computed(() => props.days.flatMap(day => props.mode === 'energy'
  ? [day.summary.estimated_energy_kwh, day.summary.actual_energy_kwh] : [day.summary.pr]).filter((value): value is number => value != null));
const maximum = computed(() => (Math.max(0, ...values.value) || 1) * 1.1);
const y = (value: number) => 16 + (maximum.value - value) / maximum.value * plotHeight.value;
const rows = computed(() => props.days.map((day, index) => ({ day, index, label: date(day.day),
  bars: [ { value: day.summary.estimated_energy_kwh, color: 'var(--pv-estimated)' },
    { value: day.summary.actual_energy_kwh, color: 'var(--pv-actual)' } ].filter(item => item.value != null),
})));
const prPath = computed(() => props.days.map((day, index) => day.summary.pr == null ? ''
  : `${index === 0 || props.days[index - 1].summary.pr == null ? 'M' : 'L'}${x(index)},${y(day.summary.pr)}`).join(' '));
const ticks = computed(() => Math.max(1, Math.ceil(props.days.length / Math.max(2, Math.floor(plotWidth.value / 70)))));
const selectedDay = computed(() => selected.value == null ? null : props.days[selected.value]);
const cutoff = (day: HistoryDay) => t('history_cutoff', { time: day.summary.end == null ? '—' : formatTimes([
  day.summary.end,
], props.language, props.timezone, { hour: '2-digit', minute: '2-digit' })[0] });
const span = computed(() => {
  const summary = selectedDay.value?.summary;
  return summary?.start == null || summary.end == null ? t('history_no_periods') : formatTimes([
    summary.start, summary.end,
  ], props.language, props.timezone, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }).join(' – ');
});
async function positionTip() {
  await nextTick();
  if (!host.value || !tip.value || selected.value == null) return;
  const box = host.value.getBoundingClientRect();
  const viewport = host.value.closest('#content-scroll')?.getBoundingClientRect();
  const top = Math.max(0, (viewport?.top ?? 0) - box.top);
  const bottom = Math.min(box.height, (viewport?.bottom ?? window.innerHeight) - box.top, window.innerHeight - box.top);
  const available = Math.max(1, bottom - top);
  tipStyle.value = { left: `${Math.max(0, Math.min(x(selected.value) + 12, box.width - tip.value.offsetWidth))}px`,
    top: `${top}px`, maxHeight: `${available}px`, pointerEvents: tip.value.scrollHeight > available ? 'auto' : 'none' };
}
function pointer(event: PointerEvent) {
  if (event.type === 'pointermove' && event.pointerType === 'touch') return;
  const box = hit.value!.getBoundingClientRect();
  selected.value = Math.max(0, Math.min(props.days.length - 1, Math.floor((event.clientX - box.left) / box.width * props.days.length)));
  void positionTip();
}
function keyboard(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'].includes(event.key)) return;
  event.preventDefault();
  if (event.key === 'Escape') { selected.value = null; hit.value?.focus({ preventScroll: true }); return; }
  selected.value = event.key === 'Home' ? 0 : event.key === 'End' ? props.days.length - 1
    : selected.value == null ? 0 : Math.max(0, Math.min(props.days.length - 1, selected.value + (event.key === 'ArrowRight' ? 1 : -1)));
}
const outside = (event: Event) => { if (!host.value?.contains(event.target as Node)) selected.value = null; };
watch(() => [props.days, props.active], () => { selected.value = null; });
watch(() => [selected.value, props.language, props.timezone, props.theme, width.value, height.value], positionTip, { flush: 'post' });
onMounted(() => {
  resize = new ResizeObserver(() => {
    if (host.value?.clientWidth) { width.value = host.value.clientWidth; height.value = host.value.clientHeight; }
  });
  resize.observe(host.value!);
  width.value = host.value!.clientWidth || 600; height.value = host.value!.clientHeight || 260;
  document.addEventListener('pointerdown', outside);
  host.value!.closest('#content-scroll')?.addEventListener('scroll', positionTip);
});
onBeforeUnmount(() => {
  resize.disconnect(); document.removeEventListener('pointerdown', outside);
  host.value?.closest('#content-scroll')?.removeEventListener('scroll', positionTip);
});
</script>

<template>
  <div ref="host" class="chart daily-history-chart" @pointerleave="event => { if (event.pointerType !== 'touch') selected = null; }">
    <svg v-if="active && days.length" :viewBox="`0 0 ${width} ${height}`" role="group" :aria-label="t(mode === 'energy' ? 'history_daily_energy' : 'history_daily_pr')">
      <g v-for="index in 5" :key="index"><line class="grid" x1="48" :x2="width - 12" :y1="y(maximum * (index - 1) / 4)" :y2="y(maximum * (index - 1) / 4)" />
        <text x="38" :y="y(maximum * (index - 1) / 4) + 4" text-anchor="end">{{ number(maximum * (index - 1) / 4, mode === 'energy' ? 3 : 1) }}</text></g>
      <text x="48" y="9">{{ mode === 'energy' ? 'kWh' : '%' }}</text>
      <path v-if="mode === 'pr'" class="series" :d="prPath" stroke="var(--pv-actual)" />
      <g v-for="row in rows" :key="row.day.day" class="daily-column" :data-day="row.day.day" :aria-current="row.day.in_progress ? 'date' : undefined">
        <template v-if="mode === 'energy'"><rect v-for="(bar, index) in row.bars" :key="index" class="daily-bar"
          :x="x(row.index) + (bar.color === 'var(--pv-estimated)' ? -slot * 0.32 : slot * 0.02)" :y="y(bar.value!)"
          :width="slot * 0.3" :height="y(0) - y(bar.value!)" :fill="bar.color" /></template>
        <circle v-else-if="row.day.summary.pr != null" class="daily-pr-point" :cx="x(row.index)" :cy="y(row.day.summary.pr)" r="3" fill="var(--pv-actual)" />
        <text v-if="row.index === days.length - 1 || row.index % ticks === 0 && (days.length - 1 - row.index) * slot >= 70" :x="x(row.index)" :y="height - 8"
          :text-anchor="row.index === 0 ? 'start' : row.index === days.length - 1 ? 'end' : 'middle'">{{ row.label }}{{ row.day.in_progress ? '*' : '' }}</text>
      </g>
      <line v-if="selected != null" class="chart-guide" :x1="x(selected)" :x2="x(selected)" y1="16" :y2="height - 34" />
      <rect ref="hit" class="chart-hit-area" x="48" y="16" :width="plotWidth" :height="plotHeight" fill="transparent" tabindex="0" role="slider"
        :aria-label="t('history_day_inspect')" aria-valuemin="0" :aria-valuemax="days.length - 1" :aria-valuenow="selected ?? 0"
        :aria-valuetext="selectedDay ? `${date(selectedDay.day, true)} · ${number(selectedDay.summary.actual_energy_kwh, 3)} kWh · ${number(selectedDay.summary.pr)} %` : t('history_day_inspect')"
        @pointermove="pointer" @pointerdown="pointer" @pointercancel="selected = null" @keydown="keyboard" @blur="event => { if (event.relatedTarget !== tip) selected = null; }" />
    </svg>
    <div v-else-if="active" class="chart-empty">{{ t('history_no_periods') }}</div>
    <div v-if="selectedDay" ref="tip" class="chart-tooltip daily-tooltip" :style="tipStyle" tabindex="0" role="status" @keydown.esc="selected = null; hit?.focus()">
      <strong>{{ date(selectedDay.day, true) }}<template v-if="selectedDay.in_progress"> · {{ t('today') }} · {{ cutoff(selectedDay) }}</template></strong>
      <div><span>{{ t('estimated_energy') }}</span><span>{{ number(selectedDay.summary.estimated_energy_kwh, 3) }} kWh</span></div>
      <div><span>{{ t('actual_energy') }}</span><span>{{ number(selectedDay.summary.actual_energy_kwh, 3) }} kWh</span></div>
      <div><span>{{ t('pr') }}</span><span>{{ number(selectedDay.summary.pr) }} %</span></div>
      <div><span>{{ t('data_completeness') }}</span><span>{{ number(selectedDay.summary.data_completeness_percent) }} %</span></div>
      <p class="daily-span">{{ t('included_settled_span') }}: {{ span }}</p>
      <p v-if="selectedDay.boundary_unavailable">{{ t('history_day_unavailable') }}</p>
    </div>
    <p v-if="days.at(-1)?.in_progress" class="daily-cutoff muted">* {{ t('today') }} · {{ cutoff(days.at(-1)!) }}</p>
  </div>
</template>
