<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { plot, type ChartPoint, type ChartSeries } from './charts';
import { catalogs, translate, type Language } from './i18n';
import type { ColorMode } from './theme';

const props = defineProps<{
  id: string; points: ChartPoint[]; series: ChartSeries[]; unit: string; active: boolean;
  language: Language; timezone: string; theme: ColorMode; currentTime?: number;
  tooltip?: (point: ChartPoint) => string;
}>();
const host = ref<HTMLElement>();
let resize: ResizeObserver;
let updateTime: ((at: number) => void) | undefined;
let dimensions = '';
function draw() {
  if (!props.active || !host.value) return;
  updateTime = plot(host.value, props.points, props.series, props.unit, {
    language: props.language, timezone: props.timezone, translate: key => translate(catalogs, props.language, key),
    tooltip: props.tooltip, currentTime: props.currentTime,
  });
  dimensions = `${host.value.clientWidth},${host.value.clientHeight}`;
}
watch(() => [props.points, props.series, props.unit, props.active, props.language, props.timezone, props.theme, props.tooltip],
  () => nextTick(draw), { flush: 'post' });
watch(() => props.currentTime, value => { if (props.active && value !== undefined) updateTime?.(value); });
onMounted(() => {
  resize = new ResizeObserver(() => {
    if (host.value && dimensions !== `${host.value.clientWidth},${host.value.clientHeight}`) draw();
  });
  resize.observe(host.value!);
  draw();
});
onUnmounted(() => resize.disconnect());
</script>

<template><div :id="id" ref="host" class="chart"></div></template>
