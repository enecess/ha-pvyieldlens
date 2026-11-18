<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { buildForecastCsv, forecastExportSteps, type ForecastExportPower, type ForecastExportStep } from '../forecastExport';
import { useI18n, type Language } from '../i18n';
import type { ForecastView } from '../models';
import { formatTimes } from '../timezones';

const props = defineProps<{
  open: boolean;
  forecast: ForecastView | null;
  language: Language;
  homeTimezone: string;
  staleFetchLabel: string;
}>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const dialog = ref<HTMLDialogElement>();
let trigger: HTMLElement | null = null;
const date = ref('');
const start = ref<number | ''>('');
const power = ref<ForecastExportPower>('forecast_power_w');
const stepMinutes = ref<ForecastExportStep>(30);
const steps = ref<number | ''>('');

const canCorrect = computed(() => props.forecast?.correction?.pr != null);
const dates = computed(() => {
  const format = new Intl.DateTimeFormat(props.language, { dateStyle: 'long', timeZone: props.homeTimezone });
  return props.forecast?.days.map(day => ({ ...day, label: format.format(day.start * 1000) })) ?? [];
});
const startTimes = computed(() => {
  const day = dates.value.find(day => day.day === date.value);
  if (!day || !props.forecast) return [];
  return props.forecast.intervals
    .filter(row => row.start >= day.start && row.start < day.end && row.start % 900 === 0 && row.forecast_power_w != null)
    .map(row => row.start);
});
const startLabels = computed(() => formatTimes(startTimes.value, props.language, props.homeTimezone, {
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
}));
const timestamp = computed(() => new Intl.DateTimeFormat(props.language, {
  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  hourCycle: 'h23', timeZone: props.homeTimezone, timeZoneName: 'shortOffset',
}));
const result = computed(() => {
  if (!props.open || !props.forecast || start.value === '' || !startTimes.value.includes(start.value) ||
    steps.value === '' || !Number.isSafeInteger(steps.value) || steps.value <= 0 ||
    power.value === 'corrected_forecast_power_w' && !canCorrect.value) return null;
  return buildForecastCsv(props.forecast.intervals, {
    start: start.value, stepMinutes: stepMinutes.value, steps: steps.value, power: power.value,
  });
});

watch([() => props.open, dialog], ([open, element]) => {
  if (!element) return;
  if (open) {
    date.value = props.forecast?.days[0]?.day ?? '';
    start.value = '';
    power.value = 'forecast_power_w';
    stepMinutes.value = 30;
    steps.value = '';
    trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
  } else if (element.open) {
    element.close();
    trigger?.focus({ preventScroll: true });
  }
}, { flush: 'post' });

function downloadForecast() {
  if (!result.value?.ok) return;
  const url = URL.createObjectURL(new Blob([result.value.csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'data_weather_forecast.csv';
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
</script>

<template>
  <dialog id="forecast-export-dialog" ref="dialog" aria-labelledby="forecast-export-title"
    aria-describedby="forecast-export-description" @cancel.prevent="emit('close')">
    <h2 id="forecast-export-title">{{ t('forecast_export_title') }}</h2>
    <p id="forecast-export-description" class="muted">{{ t('forecast_export_description') }}</p>
    <form class="form-section forecast-export-form" @submit.prevent="downloadForecast">
      <div>
        <label>
          <span>{{ t('forecast_export_power') }}</span>
          <select id="forecast-export-power" v-model="power"
            :aria-describedby="forecast && !canCorrect ? 'forecast-export-correction' : undefined">
            <option value="forecast_power_w">{{ t('forecast_original') }}</option>
            <option value="corrected_forecast_power_w" :disabled="!canCorrect">{{ t('forecast_corrected') }}</option>
          </select>
        </label>
        <small v-if="forecast && !canCorrect" id="forecast-export-correction">{{ t('forecast_export_no_correction') }}</small>
      </div>
      <div class="form-grid forecast-export-fields">
        <label>
          <span>{{ t('forecast_export_date') }}</span>
          <select id="forecast-export-date" v-model="date" required :autofocus="open" :disabled="!dates.length" @change="start = ''">
            <option v-for="day in dates" :key="day.day" :value="day.day">{{ day.label }}</option>
          </select>
        </label>
        <label>
          <span>{{ t('forecast_export_start') }}</span>
          <select id="forecast-export-start" v-model="start" required :disabled="!startTimes.length">
            <option value="" disabled>{{ t(startTimes.length ? 'forecast_export_choose_start' : 'forecast_export_no_starts') }}</option>
            <option v-for="(at, index) in startTimes" :key="at" :value="at">{{ startLabels[index] }}</option>
          </select>
        </label>
        <label>
          <span>{{ t('forecast_export_step') }}</span>
          <select id="forecast-export-step" v-model="stepMinutes">
            <option v-for="minutes in forecastExportSteps" :key="minutes" :value="minutes">
              {{ t('forecast_export_minutes', { minutes }) }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ t('forecast_export_steps') }}</span>
          <input id="forecast-export-steps" v-model.number="steps" type="number" min="1" step="1" inputmode="numeric" required />
        </label>
      </div>
      <div class="forecast-export-preview" role="status">
        <template v-if="result?.ok">
          <p>{{ t('forecast_export_window', { start: timestamp.format(Number(start) * 1000), end: timestamp.format(result.end * 1000) }) }}</p>
          <p>{{ t('forecast_export_rows', { rows: new Intl.NumberFormat(language).format(Number(steps)) }) }}</p>
        </template>
        <p v-else-if="result">{{ t('forecast_export_gap', { time: timestamp.format(result.unavailableAt * 1000) }) }}</p>
        <p v-else-if="!forecast">{{ t('forecast_export_no_detail') }}</p>
      </div>
      <p class="muted">{{ t('forecast_export_format') }}</p>
      <p v-if="staleFetchLabel" class="muted">{{ staleFetchLabel }}</p>
      <div class="dialog-actions">
        <button type="button" class="secondary" @click="emit('close')">{{ t('cancel') }}</button>
        <button type="submit" class="primary" :disabled="!result?.ok">{{ t('forecast_export_download') }}</button>
      </div>
    </form>
  </dialog>
</template>
