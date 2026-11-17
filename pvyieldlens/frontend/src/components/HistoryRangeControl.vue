<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { CalendarDays, ChevronDown } from 'lucide-vue-next';
import type { HistoryPeriod, HistorySelection } from '../models';
import { useI18n } from '../i18n';

const props = defineProps<{ modelValue: HistorySelection; presets: readonly HistoryPeriod[]; today: string; id: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: HistorySelection] }>();
const { t } = useI18n();
const host = ref<HTMLElement>();
const open = ref(false);
const start = ref('');
const end = ref('');
const error = computed(() => {
  if (!start.value || !end.value || start.value > end.value || end.value > props.today) return 'range_invalid';
  // UTC ordinals count calendar dates independently of household DST offsets.
  return (Date.parse(end.value + 'T00:00:00Z') - Date.parse(start.value + 'T00:00:00Z')) / 86400000 >= 90 ? 'range_too_long' : null;
});
const customLabel = computed(() => props.modelValue.period === 'custom'
  ? props.modelValue.start_date + ' – ' + props.modelValue.end_date : t('custom_range'));
function choose(period: HistoryPeriod) {
  if (period === 'custom') {
    start.value = props.modelValue.period === 'custom' ? props.modelValue.start_date : props.today;
    end.value = props.modelValue.period === 'custom' ? props.modelValue.end_date : props.today;
    open.value = !open.value;
  } else {
    open.value = false;
    emit('update:modelValue', { period });
  }
}
function close() { open.value = false; host.value?.querySelector<HTMLButtonElement>('[data-value=custom]')?.focus(); }
function apply() {
  if (error.value) return;
  emit('update:modelValue', { period: 'custom', start_date: start.value, end_date: end.value });
  close();
}
const outside = (event: Event) => { if (!host.value?.contains(event.target as Node)) open.value = false; };
document.addEventListener('pointerdown', outside);
onUnmounted(() => document.removeEventListener('pointerdown', outside));
</script>

<template>
  <div :id="id" ref="host" class="history-range-control" @keydown.esc.prevent="close">
    <div class="segmented" role="group" :aria-label="t('time_range')">
      <template v-for="period in presets" :key="period">
        <button v-if="period === 'custom'" type="button" data-value="custom"
          :aria-pressed="modelValue.period === period" :aria-expanded="open" :aria-controls="id + '-panel'" aria-haspopup="dialog" @click="choose(period)">
          <CalendarDays :size="14" aria-hidden="true" /><span>{{ customLabel }}</span><ChevronDown :size="12" aria-hidden="true" />
        </button>
        <button v-else type="button" :data-value="period" :aria-pressed="modelValue.period === period" @click="choose(period)">
          {{ t(period === 'today' ? 'today' : period === '24h' ? 'last_24h' : period === '7d' ? 'last_7d' : 'last_30d') }}
        </button>
      </template>
    </div>
    <div v-if="open" :id="id + '-panel'" class="range-calendar" role="dialog" :aria-labelledby="id + '-heading'">
      <h3 :id="id + '-heading'">{{ t('custom_range_heading') }}</h3>
      <div class="range-fields">
        <label :for="id + '-start'">{{ t('start_date') }}<input :id="id + '-start'" v-model="start" type="date" :max="today" /></label>
        <label :for="id + '-end'">{{ t('end_date') }}<input :id="id + '-end'" v-model="end" type="date" :max="today" /></label>
      </div>
      <p class="muted">{{ t('custom_range_help') }}</p>
      <p v-if="error" class="range-error" role="status">{{ t(error) }}</p>
      <div class="range-actions"><button :id="id + '-cancel'" type="button" class="secondary" @click="close">{{ t('cancel') }}</button>
        <button :id="id + '-apply'" type="button" class="primary" :disabled="!!error" @click="apply">{{ t('apply_range') }}</button></div>
    </div>
  </div>
</template>
