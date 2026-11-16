<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, shallowReactive, shallowRef, watch } from 'vue';
import { Check, Clock3, Compass, Database, Plug, RefreshCw, RotateCcw, Sun } from 'lucide-vue-next';
import { api, ApiError } from '../api';
import SensorInput from '../components/SensorInput.vue';
import { useI18n } from '../i18n';
import { configurationUpdateFromDraft, draftFromConfiguration, hasSettingsChanges, type SettingsSection } from '../settings';
import type { Configuration, ConfigurationSaveResult, ConnectionResult, HALocation } from '../models';

const props = defineProps<{ active: boolean; initialSection: SettingsSection; location: HALocation | null }>();
const emit = defineEmits<{
  loaded: [value: Configuration]; saved: [value: ConfigurationSaveResult];
  'state-change': [value: { dirty: boolean; busy: boolean }];
}>();
const { t, language } = useI18n();
const configuration = shallowRef<Configuration | null>(null);
const baseline = shallowRef(draftFromConfiguration({ settings: null, forecast_settings: {
  enabled: false, tilt_deg: null, azimuth_deg: null, noct_c: 45,
}, location: null, mode: 'docker', connection: { url: '', token_set: false } }));
const draft = ref(structuredClone(baseline.value));
const form = ref<HTMLFormElement>();
const scroll = ref<HTMLElement>();
const activeSection = ref<SettingsSection>('connection');
const direction = ref('');
const busy = ref(false);
const saveResult = ref('');
const discoveryFailure = ref<{ key: string; code: string } | null>(null);
const discoveryRequest = ref<string | null>(null);
const connections = shallowReactive(new Map<string, ConnectionResult>());
const dirty = computed(() => hasSettingsChanges(draft.value, baseline.value));
const editable = computed(() => configuration.value !== null && !busy.value);
const connectionKey = computed(() => {
  if (configuration.value?.mode === 'app') return 'app';
  const url = draft.value.connection.url.trim().replace(/\/+$/, '');
  return JSON.stringify([url, draft.value.connection.token, !draft.value.connection.token
    && Boolean(configuration.value?.connection.token_set) && url === configuration.value?.connection.url.trim().replace(/\/+$/, '')]);
});
const discovered = computed(() => connections.get(connectionKey.value));
const connectionStatus = computed(() => discoveryRequest.value === connectionKey.value ? 'connecting'
  : discoveryFailure.value?.key === connectionKey.value ? discoveryFailure.value.code : discovered.value ? 'connected' : '');
const locationText = computed(() => {
  const value = props.location;
  const number = new Intl.NumberFormat(language.value, { maximumFractionDigits: 5 });
  return value ? `${value.location_name || t('ha_location')} · ${number.format(value.latitude)}, ${number.format(value.longitude)}` : t('location_unavailable');
});
const sections = [
  { key: 'connection', label: 'connection', icon: Plug }, { key: 'panels', label: 'solar', icon: Sun },
  { key: 'sources', label: 'inputs', icon: Database }, { key: 'monitoring', label: 'monitoring', icon: Clock3 },
  { key: 'forecast', label: 'forecast', icon: Compass },
] as const;
const sensorFields = [
  { key: 'power_entity', label: 'power_source', units: ['W', 'kW'] },
  { key: 'temperature_entity', label: 'temp_source', units: ['°C', '°F', 'K'] },
  { key: 'irradiance_entity', label: 'irr_source', units: ['W/m²', 'W/m2', 'W/m^2', 'kW/m²', 'kW/m2'] },
] as const;
const sensorOptions = computed(() => sensorFields.map(field => ({ ...field,
  entities: (discovered.value?.entities ?? []).filter(entity => !entity.entity_id.startsWith('sensor.pvyieldlens_')
    && (field.units as readonly string[]).includes(entity.unit ?? '')),
})));
const timeoutFields = [
  { key: 'power_max_age_seconds', label: 'power_age' }, { key: 'temperature_max_age_seconds', label: 'temp_age' },
  { key: 'irradiance_max_age_seconds', label: 'irr_age' },
] as const;
let scrollFrame = 0;

watch([dirty, busy], ([dirty, busy]) => emit('state-change', { dirty, busy }), { immediate: true });
watch(() => props.active, active => { if (active) void loadConfiguration(true); }, { immediate: true });
watch(saveResult, (result, _, onCleanup) => {
  if (result !== 'saved') return;
  const timeout = setTimeout(() => { saveResult.value = ''; }, 3000);
  onCleanup(() => clearTimeout(timeout));
}, { flush: 'sync' });
onUnmounted(() => cancelAnimationFrame(scrollFrame));

function inputValue(event: Event) { return (event.target as HTMLInputElement).value; }
function clearValidation() {
  form.value?.querySelectorAll<HTMLInputElement>('input').forEach(input => {
    input.setCustomValidity(''); input.removeAttribute('aria-invalid');
  });
  saveResult.value = '';
}
function edit(event: Event) {
  const input = event.target;
  if (input instanceof HTMLInputElement) { input.setCustomValidity(''); input.removeAttribute('aria-invalid'); }
  saveResult.value = '';
}
function restoreDraft() {
  draft.value = structuredClone(baseline.value);
  direction.value = ['0', '90', '180', '270'].includes(draft.value.forecast.azimuth_deg)
    ? draft.value.forecast.azimuth_deg : draft.value.forecast.azimuth_deg ? 'custom' : '';
  clearValidation();
}
function adoptConfiguration(value: Configuration) {
  configuration.value = value;
  baseline.value = draftFromConfiguration(value);
  restoreDraft();
}
function discardDraft() { restoreDraft(); }
defineExpose({ discardDraft });

async function loadConfiguration(entering = false) {
  if (busy.value) return;
  busy.value = true;
  try {
    const value = await api.getConfiguration();
    adoptConfiguration(value);
    emit('loaded', value);
  } catch (failure) {
    saveResult.value = failure instanceof ApiError ? failure.code : 'error';
  } finally { busy.value = false; }
  if (entering && props.active) {
    await nextTick();
    scrollToSection(props.initialSection, false);
    if (matchMedia('(max-width: 600px) and (max-height: 600px)').matches) {
      document.querySelector('#settings-heading')!.scrollIntoView({ block: 'start' });
    }
    const saved = configuration.value;
    if (saved && (saved.mode === 'app' || saved.connection.url && saved.connection.token_set)) void discoverEntities();
  }
}

async function discoverEntities(manual = false) {
  if (!editable.value || discoveryRequest.value !== null || !manual && discovered.value) return;
  const key = connectionKey.value;
  discoveryRequest.value = key;
  discoveryFailure.value = null;
  try {
    const result = await api.discoverEntities(configuration.value?.mode === 'app' ? null : { ...draft.value.connection });
    connections.set(key, result);
  } catch (failure) {
    discoveryFailure.value = { key, code: failure instanceof ApiError ? failure.code : 'error' };
  } finally { discoveryRequest.value = null; }
}

function trackScroll() {
  if (scrollFrame) return;
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = 0;
    const container = scroll.value;
    if (!container || !props.active) return;
    const headings = [...container.querySelectorAll<HTMLElement>('[data-settings-section]')];
    const activationTop = container.getBoundingClientRect().top + 24;
    activeSection.value = container.scrollTop + container.clientHeight >= container.scrollHeight - 2 ? 'forecast'
      : (headings.filter(section => section.querySelector('h2')!.getBoundingClientRect().top <= activationTop).at(-1)?.dataset.settingsSection as SettingsSection | undefined) ?? 'connection';
  });
}
function scrollToSection(section: SettingsSection, smooth = true) {
  const container = scroll.value;
  const heading = container?.querySelector(`[data-settings-section=${section}] h2`);
  if (!container || !heading) return;
  container.scrollTo({ top: container.scrollTop + heading.getBoundingClientRect().top - container.getBoundingClientRect().top - 20,
    behavior: smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'instant' });
  trackScroll();
}
async function revealInvalid(input: HTMLInputElement) {
  if (input.name === 'forecast_azimuth_deg') direction.value = 'custom';
  await nextTick();
  const container = scroll.value!;
  container.scrollTo({ top: container.scrollTop + input.getBoundingClientRect().top - container.getBoundingClientRect().top - 60, behavior: 'instant' });
  input.focus({ preventScroll: true });
  trackScroll();
}

async function save() {
  if (!editable.value || !dirty.value) return;
  clearValidation();
  sensorFields.forEach(field => { draft.value.monitoring[field.key] = draft.value.monitoring[field.key].trim(); });
  await nextTick();
  const inputs = [...form.value!.querySelectorAll<HTMLInputElement>('input')];
  const azimuth = inputs.find(input => input.name === 'forecast_azimuth_deg')!;
  const noct = inputs.find(input => input.name === 'forecast_noct_c')!;
  azimuth.setCustomValidity(azimuth.value !== '' && azimuth.valueAsNumber >= 360 ? t('azimuth_help') : '');
  noct.setCustomValidity(noct.value !== '' && noct.valueAsNumber <= 20 ? t('noct_help') : '');
  const sources = inputs.filter(input => input.name.endsWith('_entity'));
  sources.forEach(input => input.setCustomValidity(input.value.startsWith('sensor.pvyieldlens_')
    || sources.some(other => other !== input && other.value === input.value && input.value !== '') ? t('invalid_configuration') : ''));
  const update = inputs.find(input => input.name === 'update_seconds')!;
  update.setCustomValidity(Number(draft.value.monitoring.update_seconds) > Number(draft.value.monitoring.realtime_window_seconds) ? t('invalid_configuration') : '');
  const invalid = inputs.find(input => input.willValidate && !input.validity.valid);
  if (invalid) { invalid.setAttribute('aria-invalid', 'true'); await revealInvalid(invalid); invalid.reportValidity(); return; }
  const key = connectionKey.value;
  const preview = discovered.value;
  busy.value = true;
  try {
    const value = await api.saveConfiguration(configurationUpdateFromDraft(draft.value, {
      mode: configuration.value!.mode, timezone: preview?.timezone ?? configuration.value!.settings?.timezone ?? 'UTC',
    }));
    adoptConfiguration(value);
    if (key !== connectionKey.value) {
      if (preview) connections.set(connectionKey.value, preview);
      else connections.delete(connectionKey.value);
    }
    emit('saved', value);
    saveResult.value = 'saved';
  } catch (failure) {
    saveResult.value = failure instanceof ApiError ? failure.code : 'error';
    const fields = failure instanceof ApiError ? failure.fields : [];
    const invalidInputs = inputs.filter(input => fields.some(field => field === `settings.${input.name}`
      || field === `forecast_settings.${input.name.replace(/^forecast_/, '')}` || field === `connection.${input.id.replace(/^ha-/, '')}`)
      || saveResult.value === 'connection_required' && input.id === 'ha-token');
    invalidInputs.forEach(input => input.setAttribute('aria-invalid', 'true'));
    busy.value = false;
    if (invalidInputs[0]) await revealInvalid(invalidInputs[0]);
  } finally { busy.value = false; }
}
</script>

<template>
  <section id="settings-page" aria-labelledby="settings-heading">
    <div class="section-heading"><div><p class="eyebrow">PVYieldLens</p><h1 id="settings-heading">{{ t('settings') }}</h1><p class="muted">{{ t('source_semantics') }}</p></div></div>
    <div class="settings-body">
      <nav id="settings-categories" :aria-label="t('settings_categories')">
        <button v-for="(section, index) in sections" :key="section.key" type="button" :data-settings-category="section.key" :aria-pressed="activeSection === section.key" :aria-current="activeSection === section.key ? 'location' : undefined" :disabled="busy" @click="scrollToSection(section.key)">
          <component :is="section.icon" :size="16" aria-hidden="true" /><span>{{ t(section.label) }}</span><small>0{{ index + 1 }}</small>
        </button>
      </nav>
      <div class="settings-form-column">
        <div id="settings-scroll" ref="scroll" @scroll.passive="trackScroll">
          <form id="settings-form" ref="form" novalidate @submit.prevent="save" @input="edit" @change="edit">
            <fieldset :disabled="!editable">
              <section class="form-section panel" data-settings-section="connection">
                <h2><Plug :size="18" aria-hidden="true" />{{ t('connection') }}</h2>
                <p v-if="configuration?.mode === 'app'" id="app-connection-note" class="muted">{{ t('app_connection') }}</p>
                <div v-show="configuration?.mode !== 'app'" id="connection-fields" class="form-grid">
                  <label><span>{{ t('ha_url') }}</span><input id="ha-url" v-model="draft.connection.url" type="url" placeholder="http://homeassistant.local:8123" autocomplete="url" :disabled="configuration?.mode === 'app'"></label>
                  <label><span>{{ t('ha_token') }}</span><input id="ha-token" v-model="draft.connection.token" type="password" autocomplete="new-password" :disabled="configuration?.mode === 'app'"><small>{{ t('token_help') }}</small></label>
                </div>
                <div class="connection-actions"><button id="load-entities" class="secondary" type="button" :disabled="discoveryRequest !== null" @click="discoverEntities(true)"><RefreshCw :size="14" aria-hidden="true" />{{ t(discoveryRequest !== null ? 'connecting' : 'connect') }}</button><span id="connection-result" role="status">{{ connectionStatus ? t(connectionStatus) : '' }}</span></div>
              </section>
              <section class="form-section panel" data-settings-section="panels">
                <h2><Sun :size="18" aria-hidden="true" />{{ t('solar') }}</h2>
                <div class="form-grid">
                  <label><span>{{ t('rated_power') }}</span><div class="input-unit"><input name="rated_power_w" type="number" min="1" max="1000000000" step="any" required :value="draft.monitoring.rated_power_w" @input="draft.monitoring.rated_power_w = inputValue($event)"><span>W</span></div></label>
                  <label><span>{{ t('coefficient') }}</span><div class="input-unit"><input name="temperature_coefficient_pct_per_c" type="number" min="-5" max="5" step="any" required :value="draft.monitoring.temperature_coefficient_pct_per_c" @input="draft.monitoring.temperature_coefficient_pct_per_c = inputValue($event)"><span>%/°C</span></div><small>{{ t('coef_help') }}</small></label>
                </div>
              </section>
              <section class="form-section panel" data-settings-section="sources">
                <h2><Database :size="18" aria-hidden="true" />{{ t('inputs') }}</h2>
                <div class="sensor-fields">
                  <SensorInput v-for="field in sensorOptions" :key="field.key" v-model="draft.monitoring[field.key]" :name="field.key" :label="t(field.label)"
                    :entities="field.entities"
                    :active="active" :disabled="!editable" />
                </div>
              </section>
              <section class="form-section panel" data-settings-section="monitoring">
                <h2><Clock3 :size="18" aria-hidden="true" />{{ t('monitoring') }}</h2>
                <div class="form-grid three">
                  <label><span>{{ t('interval') }}</span><div class="input-unit"><select v-model="draft.monitoring.interval_minutes" name="interval_minutes"><option value="1">1</option><option value="5">5</option><option value="10">10</option></select><span>{{ t('minutes') }}</span></div></label>
                  <label><span>{{ t('realtime_window') }}</span><div class="input-unit"><input name="realtime_window_seconds" type="number" min="10" max="3600" required :value="draft.monitoring.realtime_window_seconds" @input="draft.monitoring.realtime_window_seconds = inputValue($event)"><span>s</span></div></label>
                  <label><span>{{ t('update_interval') }}</span><div class="input-unit"><input name="update_seconds" type="number" min="1" max="60" required :value="draft.monitoring.update_seconds" @input="draft.monitoring.update_seconds = inputValue($event)"><span>s</span></div></label>
                </div>
                <div class="advanced-settings"><h3>{{ t('advanced') }}</h3><p class="muted">{{ t('hold_help') }}</p><div class="form-grid three"><label v-for="field in timeoutFields" :key="field.key"><span>{{ t(field.label) }}</span><div class="input-unit"><input :name="field.key" type="number" min="1" max="86400" required :value="draft.monitoring[field.key]" @input="draft.monitoring[field.key] = inputValue($event)"><span>s</span></div></label></div></div>
              </section>
              <section class="form-section panel" data-settings-section="forecast">
                <h2><Compass :size="18" aria-hidden="true" />{{ t('forecast') }}</h2><p class="muted">{{ t('forecast_help') }}</p>
                <p id="forecast-location" class="readonly-row">{{ locationText }}</p>
                <p id="home-timezone" class="readonly-row">{{ t('home_timezone') }}: {{ location?.timezone ?? configuration?.settings?.timezone ?? '—' }}</p><p class="muted">{{ t('location_help') }}</p>
                <label class="checkbox-row"><span>{{ t('forecast_enabled') }}</span><input v-model="draft.forecast.enabled" name="forecast_enabled" type="checkbox"></label>
                <div class="form-grid">
                  <label><span>{{ t('forecast_tilt') }}</span><div class="input-unit"><input name="forecast_tilt_deg" type="number" min="0" max="90" step="any" :required="draft.forecast.enabled" :value="draft.forecast.tilt_deg" @input="draft.forecast.tilt_deg = inputValue($event)"><span>°</span></div></label>
                  <label><span>{{ t('forecast_direction') }}</span><select id="forecast-direction" v-model="direction" @change="direction === 'custom' || (draft.forecast.azimuth_deg = direction)"><option value="">{{ t('direction_unset') }}</option><option value="0">{{ t('north') }}</option><option value="90">{{ t('east') }}</option><option value="180">{{ t('south') }}</option><option value="270">{{ t('west') }}</option><option value="custom">{{ t('custom') }}</option></select></label>
                  <label v-show="direction === 'custom'" id="forecast-azimuth-row"><span>{{ t('forecast_azimuth') }}</span><div class="input-unit"><input name="forecast_azimuth_deg" type="number" min="0" step="any" :required="draft.forecast.enabled" :value="draft.forecast.azimuth_deg" @input="draft.forecast.azimuth_deg = inputValue($event)"><span>°</span></div><small>{{ t('azimuth_help') }}</small></label>
                  <label><span>{{ t('forecast_noct') }}</span><div class="input-unit"><input name="forecast_noct_c" type="number" min="20" max="80" step="any" required :value="draft.forecast.noct_c" @input="draft.forecast.noct_c = inputValue($event)"><span>°C</span></div><small>{{ t('noct_help') }}</small></label>
                </div>
              </section>
            </fieldset>
          </form>
        </div>
        <div id="settings-actions"><div class="settings-feedback"><span v-if="busy" role="status">{{ t('settings_loading') }}</span><span id="save-result" role="status">{{ saveResult ? t(saveResult) : '' }}</span></div><div class="settings-buttons"><button id="cancel-settings" class="secondary" type="button" :disabled="busy" @click="loadConfiguration()"><RotateCcw :size="15" aria-hidden="true" />{{ t('cancel_settings') }}</button><button id="save-button" class="primary" form="settings-form" type="submit" :disabled="!editable || !dirty"><Check :size="16" aria-hidden="true" />{{ t(busy ? 'saving' : 'save') }}</button></div></div>
      </div>
    </div>
  </section>
</template>
