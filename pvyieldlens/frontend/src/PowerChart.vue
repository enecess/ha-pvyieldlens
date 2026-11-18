<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { plot, type ChartHandle, type ChartPoint, type ChartSeries, type ChartTooltip } from './charts';
import { catalogs, translate, type Language } from './i18n';
import type { ColorMode } from './theme';

const props = defineProps<{
  id: string; points: ChartPoint[]; series: ChartSeries[]; unit: string; active: boolean;
  language: Language; timezone: string; theme: ColorMode; currentTime?: number;
  tooltip?: (point: ChartPoint) => ChartTooltip;
  range?: { start: number; end: number }; selection?: 'nearest' | 'interval'; coverage?: 'points' | 'windows';
}>();
const host = ref<HTMLElement>();
let resize: ResizeObserver;
let handle: ChartHandle | undefined;
let dimensions = '';
function draw() {
  const focused = host.value?.contains(document.activeElement);
  const selectedAt = handle?.selectedAt();
  handle?.dispose();
  handle = undefined;
  if (!props.active || !host.value) return;
  dimensions = `${host.value.clientWidth},${host.value.clientHeight}`;
  if (!host.value.clientWidth || !host.value.clientHeight) return;
  handle = plot(host.value, props.points, props.series, props.unit, {
    language: props.language, timezone: props.timezone, translate: key => translate(catalogs, props.language, key),
    tooltip: props.tooltip, currentTime: props.currentTime, range: props.range, selection: props.selection, coverage: props.coverage, selectedAt,
  });
  if (focused) host.value.querySelector<SVGElement>('.chart-hit-area')?.focus({ preventScroll: true });
}
watch([
  () => props.points, () => props.series, () => props.unit, () => props.active, () => props.language,
  () => props.timezone, () => props.theme, () => props.tooltip, () => props.range, () => props.selection,
  () => props.coverage, () => props.currentTime !== undefined,
], () => nextTick(draw), { flush: 'post' });
watch(() => props.currentTime, (value, previous) => {
  if (props.active && value !== undefined && previous !== undefined) handle?.updateTime(value);
});
onMounted(() => {
  resize = new ResizeObserver(() => {
    if (host.value && dimensions !== `${host.value.clientWidth},${host.value.clientHeight}`) draw();
  });
  resize.observe(host.value!);
  draw();
});
onUnmounted(() => { resize.disconnect(); handle?.dispose(); });
</script>

<template><div :id="id" ref="host" class="chart"></div></template>
