<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, shallowReactive, shallowRef, watch } from 'vue';
import { Check, ChevronDown, Clock3, Compass, Database, Plug, RefreshCw, RotateCcw, Sun } from 'lucide-vue-next';
import { api, ApiError } from '../api';
import SensorInput from '../components/SensorInput.vue';
import { useI18n } from '../i18n';
import { configurationUpdateFromDraft, draftFromConfiguration, forecastAxes, hasSettingsChanges, normalizeConnectionUrl, type SettingsSection } from '../settings';
import type { Configuration, ConfigurationSaveResult, ConnectionResult, HALocation } from '../models';

const props = defineProps<{ active: boolean; initialSection: SettingsSection; location: HALocation | null }>();
const emit = defineEmits<{
  loaded: [value: Configuration]; saved: [value: ConfigurationSaveResult];
  'state-change': [value: { dirty: boolean; busy: boolean }];
}>();
const { t, language } = useI18n();
const configuration = shallowRef<Configuration | null>(null);
const baseline = shallowRef(draftFromConfiguration({ monitoring_settings: null, forecast_settings: {
  tilt_deg: null, azimuth_deg: null, tilt_entity: null, azimuth_entity: null, noct_c: 45, pr_history_days: 14,
}, location: null, mode: 'docker', connection: { url: '', token_set: false } }));
const draft = ref(structuredClone(baseline.value));
const form = ref<HTMLFormElement>();
const scroll = ref<HTMLElement>();
const categories = ref<HTMLElement>();
const actions = ref<HTMLElement>();
const activeSection = ref<SettingsSection>('connection');
const monitoringOpen = ref(false);
const monitoringHelpOpen = ref(false);
const direction = ref('');
const busy = ref(false);
const saveResult = ref('');
const discoveryFailure = ref<{ key: string; code: string } | null>(null);
const discoveryRequest = ref<string | null>(null);
const connections = shallowReactive(new Map<string, ConnectionResult>());
const dirty = computed(() => hasSettingsChanges(draft.value, baseline.value));
const editable = computed(() => configuration.value !== null && !busy.value);
const dockerConnection = computed(() => configuration.value?.mode !== 'app');
const connectionUrl = computed(() => normalizeConnectionUrl(draft.value.connection.url.trim()));
const savedTokenAvailable = computed(() => {
  const saved = configuration.value?.connection;
  return Boolean(saved?.token_set && connectionUrl.value === normalizeConnectionUrl(saved.url.trim()));
});
const tokenRequired = computed(() => dockerConnection.value && !savedTokenAvailable.value);
const connectionKey = computed(() => dockerConnection.value
  ? JSON.stringify([connectionUrl.value, draft.value.connection.token, !draft.value.connection.token && savedTokenAvailable.value])
  : 'app');
const discovered = computed(() => connections.get(connectionKey.value));
const connectionStatus = computed(() => discoveryRequest.value === connectionKey.value ? 'connecting'
  : discoveryFailure.value?.key === connectionKey.value ? discoveryFailure.value.code : discovered.value ? 'connection_verified' : '');
const savedLocation = computed(() => {
  const value = props.location;
  const savedUrl = configuration.value?.connection.url;
  return value && savedUrl && normalizeConnectionUrl(value.origin) === normalizeConnectionUrl(savedUrl) ? value : null;
});
const coordinates = computed(() => {
  const value = savedLocation.value;
  if (!value) return '—';
  const number = new Intl.NumberFormat(language.value, { maximumFractionDigits: 5 });
  return `${number.format(value.latitude)}, ${number.format(value.longitude)}`;
});
const sections = [
  { key: 'connection', label: 'connection', icon: Plug }, { key: 'modules', label: 'pv_modules', icon: Sun },
  { key: 'sources', label: 'inputs', icon: Database }, { key: 'forecast', label: 'forecast', icon: Compass },
  { key: 'monitoring', label: 'monitoring', icon: Clock3 },
] as const;
const sensorFields = [
  { key: 'actual_power_entity', label: 'actual_power_sensor', units: ['W', 'kW'] },
  { key: 'irradiance_entity', label: 'irradiance_sensor', units: ['W/m²', 'W/m2', 'W/m^2', 'kW/m²', 'kW/m2'] },
  { key: 'module_temperature_entity', label: 'module_temperature_sensor', units: ['°C', '°F', 'K'] },
] as const;
const sensorOptions = computed(() => sensorFields.map(field => ({ ...field,
  entities: (discovered.value?.entities ?? []).filter(entity => entity.entity_id.startsWith('sensor.')
    && !entity.entity_id.startsWith('sensor.pvyieldlens_')
    && (field.units as readonly string[]).includes(entity.unit ?? '')),
})));
const angleOptions = computed(() => (discovered.value?.entities ?? []).filter(entity => entity.angle_deg !== undefined));
const anglePattern = '(?:sensor|number|input_number)\\.[a-z0-9_]+';
const angleSelections = computed(() => {
  const number = new Intl.NumberFormat(language.value, { maximumSignificantDigits: 21, useGrouping: false });
  return Object.fromEntries(forecastAxes.map(axis => {
    const id = draft.value.forecast[`${axis}_entity`].trim();
    const entity = angleOptions.value.find(entity => entity.entity_id === id);
    const angle = entity?.angle_deg;
    return [axis, id && t('angle_entity_reading', { entity: entity?.name || id,
      value: angle == null || (axis === 'tilt' && angle > 90) ? t('angle_reading_unavailable') : `${number.format(angle)}°`,
    })];
  }));
});
const temperatureConfigured = computed(() => draft.value.monitoring.module_temperature_entity.trim() !== '');
const timeoutFields = computed(() => ([
  { key: 'actual_power_max_age_seconds', label: 'actual_power_max_age' }, { key: 'module_temperature_max_age_seconds', label: 'module_temperature_max_age' },
  { key: 'irradiance_max_age_seconds', label: 'irradiance_max_age' },
] as const).filter(field => field.key !== 'module_temperature_max_age_seconds' || temperatureConfigured.value));
let scrollFrame = 0;

watch(temperatureConfigured, configured => {
  if (!configured) draft.value.monitoring.module_temperature_max_age_seconds = baseline.value.monitoring.module_temperature_max_age_seconds;
});
watch(tokenRequired, async () => {
  const invalid = form.value?.querySelectorAll('[aria-invalid="true"]:required:invalid');
  await nextTick();
  invalid?.forEach(field => {
    if (field.matches(':optional:valid')) field.removeAttribute('aria-invalid');
  });
});
watch([dirty, busy], ([dirty, busy]) => emit('state-change', { dirty, busy }), { immediate: true });
watch(() => props.active, active => {
  if (!active) return;
  monitoringOpen.value = false;
  monitoringHelpOpen.value = false;
  void loadConfiguration(true);
}, { immediate: true });
watch(saveResult, (result, _, onCleanup) => {
  if (result !== 'saved') return;
  const timeout = setTimeout(() => { saveResult.value = ''; }, 3000);
  onCleanup(() => clearTimeout(timeout));
}, { flush: 'sync' });
onUnmounted(() => cancelAnimationFrame(scrollFrame));

function inputValue(event: Event) { return (event.target as HTMLInputElement).value; }
function clearValidation() {
  form.value?.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select').forEach(input => {
    input.setCustomValidity(''); input.removeAttribute('aria-invalid');
  });
  saveResult.value = '';
}
function edit(event: Event) {
  const input = event.target;
  if (input instanceof HTMLInputElement || input instanceof HTMLSelectElement) {
    input.setCustomValidity(''); input.removeAttribute('aria-invalid');
  }
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
    await scrollToSection(props.initialSection, false);
    revealShortSettingsForm();
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
    const atEnd = container.scrollTop + container.clientHeight >= container.scrollHeight - 2;
    const section = atEnd ? headings.at(-1)
      : headings.filter(section => section.querySelector('h2')!.getBoundingClientRect().top <= activationTop).at(-1);
    activeSection.value = (section?.dataset.settingsSection as SettingsSection | undefined) ?? 'connection';
  });
}
async function scrollToSection(section: SettingsSection, smooth = true) {
  if (section === 'monitoring') {
    monitoringOpen.value = true;
    await nextTick();
  }
  const container = scroll.value;
  const heading = container?.querySelector(`[data-settings-section=${section}] h2`);
  if (!container || !heading) return;
  container.scrollTo({ top: container.scrollTop + heading.getBoundingClientRect().top - container.getBoundingClientRect().top - 20,
    behavior: smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'instant' });
  trackScroll();
}
function revealShortSettingsForm() {
  if (matchMedia('(max-width: 600px) and (max-height: 600px)').matches) {
    categories.value!.scrollIntoView({ block: 'start', behavior: 'instant' });
  }
}
async function revealInvalid(input: HTMLInputElement | HTMLSelectElement) {
  if (input.closest('#monitoring-fields')) monitoringOpen.value = true;
  await nextTick();
  revealShortSettingsForm();
  input.focus({ preventScroll: true });
  const container = scroll.value!;
  const bounds = container.getBoundingClientRect();
  const field = input.getBoundingClientRect();
  const visibleBottom = Math.min(bounds.bottom, actions.value!.getBoundingClientRect().top);
  const offset = Math.max(0, Math.min(60, visibleBottom - bounds.top - field.height - 8));
  container.scrollTo({ top: container.scrollTop + field.top - bounds.top - offset, behavior: 'instant' });
  trackScroll();
}

async function save() {
  if (!editable.value || !dirty.value) return;
  clearValidation();
  sensorFields.forEach(field => { draft.value.monitoring[field.key] = draft.value.monitoring[field.key].trim(); });
  forecastAxes.forEach(axis => {
    if (draft.value.forecast[`${axis}_source`] === 'entity') {
      draft.value.forecast[`${axis}_entity`] = draft.value.forecast[`${axis}_entity`].trim();
    }
  });
  await nextTick();
  const inputs = [...form.value!.querySelectorAll('input')];
  const azimuth = inputs.find(input => input.name === 'forecast_azimuth_deg');
  const noct = inputs.find(input => input.name === 'forecast_noct_c')!;
  azimuth?.setCustomValidity(azimuth.valueAsNumber >= 360 ? t('azimuth_help') : '');
  noct.setCustomValidity(noct.value !== '' && noct.valueAsNumber <= 20 ? t('noct_help') : '');
  const sources = inputs.filter(input => sensorFields.some(field => field.key === input.name));
  sources.forEach(input => input.setCustomValidity(input.value.startsWith('sensor.pvyieldlens_')
    || sources.some(other => other !== input && other.value === input.value && input.value !== '') ? t('invalid_configuration') : ''));
  const update = inputs.find(input => input.name === 'update_interval_seconds')!;
  update.setCustomValidity(Number(draft.value.monitoring.update_interval_seconds) > Number(draft.value.monitoring.live_window_seconds) ? t('invalid_configuration') : '');
  const invalid = [...form.value!.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select')]
    .find(input => input.willValidate && !input.validity.valid);
  if (invalid) { invalid.setAttribute('aria-invalid', 'true'); await revealInvalid(invalid); invalid.reportValidity(); return; }
  const key = connectionKey.value;
  const preview = discovered.value;
  busy.value = true;
  try {
    const value = await api.saveConfiguration(configurationUpdateFromDraft(draft.value, {
      mode: configuration.value!.mode, home_timezone: preview?.home_timezone ?? configuration.value!.monitoring_settings?.home_timezone ?? 'UTC',
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
    busy.value = false;
    if (draft.value.forecast.azimuth_source === 'fixed' && fields.includes('forecast_settings.azimuth_deg')) direction.value = 'custom';
    await nextTick();
    const invalidInputs = [...form.value!.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select')]
      .filter(input => fields.some(field => field === `monitoring_settings.${input.name}`
      || field === `forecast_settings.${input.name.replace(/^forecast_/, '')}` || field === `connection.${input.id.replace(/^ha-/, '')}`)
      || saveResult.value === 'connection_required' && input.id === 'ha-token');
    invalidInputs.forEach(input => input.setAttribute('aria-invalid', 'true'));
    if (invalidInputs[0]) await revealInvalid(invalidInputs[0]);
  } finally { busy.value = false; }
}
</script>

<template>
  <section id="settings-page" aria-labelledby="settings-heading">
    <div class="section-heading"><div><p class="eyebrow">PVYieldLens</p><h1 id="settings-heading">{{ t('settings') }}</h1><p class="muted">{{ t('source_semantics') }}</p></div></div>
    <div class="settings-body">
      <nav id="settings-categories" ref="categories" :aria-label="t('settings_categories')">
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
                <div v-show="dockerConnection" id="connection-fields" class="form-grid">
                  <label><span>{{ t('ha_url') }}</span><input id="ha-url" v-model="draft.connection.url" type="url" placeholder="http://homeassistant.local:8123" autocomplete="url" :required="dockerConnection" :disabled="!dockerConnection"></label>
                  <label><span>{{ t('ha_token') }}</span><input id="ha-token" v-model="draft.connection.token" type="password" autocomplete="new-password" :required="tokenRequired" :disabled="!dockerConnection"><small>{{ t('token_help') }}</small></label>
                </div>
                <div class="connection-actions"><button id="load-entities" class="secondary" type="button" :disabled="discoveryRequest !== null" @click="discoverEntities(true)"><RefreshCw :size="14" aria-hidden="true" />{{ t(discoveryRequest !== null ? 'connecting' : 'connect') }}</button><span id="connection-result" role="status">{{ connectionStatus ? t(connectionStatus) : '' }}</span></div>
              </section>
              <section class="form-section panel" data-settings-section="modules">
                <h2><Sun :size="18" aria-hidden="true" />{{ t('pv_modules') }}</h2>
                <div class="form-grid">
                  <label><span>{{ t('total_max_power_at_stc') }}</span><div class="input-unit"><input name="total_max_power_at_stc_w" type="number" min="1" max="1000000000" step="any" required :value="draft.monitoring.total_max_power_at_stc_w" @input="draft.monitoring.total_max_power_at_stc_w = inputValue($event)"><span>W</span></div><small>{{ t('rated_power_help') }}</small></label>
                  <label><span>{{ t('pmax_temperature_coefficient') }}</span><div class="input-unit"><input name="pmax_temperature_coefficient_pct_per_c" type="number" min="-5" max="5" step="any" required :value="draft.monitoring.pmax_temperature_coefficient_pct_per_c" @input="draft.monitoring.pmax_temperature_coefficient_pct_per_c = inputValue($event)"><span>%/°C</span></div><small>{{ t('pmax_temperature_coefficient_help') }}</small></label>
                  <fieldset v-for="axis in forecastAxes" :key="axis" class="angle-field">
                    <legend>{{ t(axis === 'tilt' ? 'forecast_tilt' : 'forecast_direction') }}</legend>
                    <div class="angle-controls">
                      <label><span>{{ t('angle_source') }}</span>
                        <select v-model="draft.forecast[`${axis}_source`]" :name="`forecast_${axis}_source`"><option value="fixed">{{ t('angle_source_fixed') }}</option><option value="entity">{{ t('angle_source_entity') }}</option></select>
                      </label>
                      <div v-if="draft.forecast[`${axis}_source`] === 'entity'">
                        <SensorInput v-model="draft.forecast[`${axis}_entity`]" :name="`forecast_${axis}_entity`" :label="t(`forecast_${axis}_entity`)"
                          :entities="angleOptions" :pattern="anglePattern" :active="active" :disabled="!editable" />
                        <small v-if="angleSelections[axis]" class="angle-reading">{{ angleSelections[axis] }}</small>
                        <small>{{ t('angle_entity_help') }} {{ t(`${axis}_help`) }}</small>
                      </div>
                      <label v-else-if="axis === 'tilt'"><span>{{ t('forecast_tilt') }}</span>
                        <div class="input-unit"><input name="forecast_tilt_deg" type="number" min="0" max="90" step="any" required :value="draft.forecast.tilt_deg" @input="draft.forecast.tilt_deg = inputValue($event)"><span>°</span></div><small>{{ t('tilt_help') }}</small>
                      </label>
                      <template v-else>
                        <label><span>{{ t('forecast_direction') }}</span><select id="forecast-direction" v-model="direction" required @change="direction === 'custom' || (draft.forecast.azimuth_deg = direction)"><option value="">{{ t('direction_unset') }}</option><option value="0">{{ t('north') }}</option><option value="90">{{ t('east') }}</option><option value="180">{{ t('south') }}</option><option value="270">{{ t('west') }}</option><option value="custom">{{ t('custom') }}</option></select><small v-if="direction !== 'custom'">{{ t('azimuth_help') }}</small></label>
                        <label v-if="direction === 'custom'" id="forecast-azimuth-row"><span>{{ t('forecast_azimuth') }}</span><div class="input-unit"><input name="forecast_azimuth_deg" type="number" min="0" step="any" required :value="draft.forecast.azimuth_deg" @input="draft.forecast.azimuth_deg = inputValue($event)"><span>°</span></div><small>{{ t('azimuth_help') }}</small></label>
                      </template>
                    </div>
                  </fieldset>
                  <label><span>{{ t('forecast_noct') }}</span><div class="input-unit"><input name="forecast_noct_c" type="number" min="20" max="80" step="any" required :value="draft.forecast.noct_c" @input="draft.forecast.noct_c = inputValue($event)"><span>°C</span></div><small>{{ t('noct_help') }}</small></label>
                </div>
              </section>
              <section class="form-section panel" data-settings-section="sources">
                <h2><Database :size="18" aria-hidden="true" />{{ t('inputs') }}</h2>
                <div class="sensor-fields">
                  <SensorInput v-for="field in sensorOptions" :key="field.key" v-model="draft.monitoring[field.key]" :name="field.key" :label="t(field.label)"
                    :entities="field.entities" :required="field.key !== 'module_temperature_entity'"
                    :help="field.key === 'module_temperature_entity' ? t('module_temperature_estimate_help') : undefined"
                    :active="active" :disabled="!editable" />
                </div>
              </section>
              <section class="form-section panel" data-settings-section="forecast">
                <h2><Compass :size="18" aria-hidden="true" />{{ t('forecast') }}</h2><p class="muted">{{ t('forecast_help') }}</p>
                <dl id="forecast-location">
                  <div><dt>{{ t('ha_location') }}</dt><dd>{{ savedLocation?.location_name || '—' }}</dd></div>
                  <div><dt>{{ t('coordinates') }}</dt><dd class="location-coordinates">{{ coordinates }}</dd></div>
                  <div><dt>{{ t('home_timezone') }}</dt><dd>{{ savedLocation?.home_timezone ?? '—' }}</dd></div>
                </dl>
                <p class="muted">{{ t('location_help') }}</p>
                <div class="form-grid">
                  <label><span>{{ t('forecast_pr_history_days') }}</span><input name="forecast_pr_history_days" type="number" min="3" max="90" step="1" required :value="draft.forecast.pr_history_days" @input="draft.forecast.pr_history_days = inputValue($event)"><small>{{ t('pr_history_days_help') }}</small></label>
                </div>
              </section>
              <div class="settings-form-end">
                <section class="form-section panel" data-settings-section="monitoring">
                  <div class="monitoring-heading">
                    <h2><button id="monitoring-toggle" type="button" :aria-expanded="monitoringOpen" aria-controls="monitoring-fields" @click="monitoringOpen = !monitoringOpen">
                      <Clock3 :size="18" aria-hidden="true" /><span>{{ t('monitoring') }}</span><ChevronDown :size="16" aria-hidden="true" />
                    </button></h2>
                    <button id="monitoring-help-toggle" class="secondary" type="button" :aria-label="t('monitoring_help')"
                      :aria-expanded="monitoringHelpOpen" aria-controls="monitoring-help" @click="monitoringHelpOpen = !monitoringHelpOpen">?</button>
                  </div>
                  <dl v-show="monitoringHelpOpen" id="monitoring-help">
                    <dt>{{ t('settlement_interval') }}</dt><dd>{{ t('monitoring_settlement_help') }}</dd>
                    <dt>{{ t('live_window_duration') }}</dt><dd>{{ t('monitoring_average_help') }}</dd>
                    <dt>{{ t('update_interval') }}</dt><dd>{{ t('monitoring_update_help') }}</dd>
                    <dt>{{ t('advanced') }}</dt><dd>{{ t('monitoring_timeout_help') }}</dd>
                  </dl>
                  <div v-show="monitoringOpen" id="monitoring-fields">
                    <div class="form-grid three">
                      <label><span>{{ t('settlement_interval') }}</span><div class="input-unit"><select v-model="draft.monitoring.settlement_interval_minutes" name="settlement_interval_minutes" required><option value="1">1</option><option value="5">5</option><option value="10">10</option></select><span>{{ t('minutes') }}</span></div></label>
                      <label><span>{{ t('live_window_duration') }}</span><div class="input-unit"><input name="live_window_seconds" type="number" min="10" max="3600" required :value="draft.monitoring.live_window_seconds" @input="draft.monitoring.live_window_seconds = inputValue($event)"><span>s</span></div></label>
                      <label><span>{{ t('update_interval') }}</span><div class="input-unit"><input name="update_interval_seconds" type="number" min="1" max="60" required :value="draft.monitoring.update_interval_seconds" @input="draft.monitoring.update_interval_seconds = inputValue($event)"><span>s</span></div></label>
                    </div>
                    <div class="advanced-settings"><h3>{{ t('advanced') }}</h3><p class="muted">{{ t('hold_help') }}</p><div class="form-grid three"><label v-for="field in timeoutFields" :key="field.key"><span>{{ t(field.label) }}</span><div class="input-unit"><input :name="field.key" type="number" min="1" max="86400" required :value="draft.monitoring[field.key]" @input="draft.monitoring[field.key] = inputValue($event)"><span>s</span></div></label></div></div>
                  </div>
                </section>
              </div>
            </fieldset>
          </form>
        </div>
        <div id="settings-actions" ref="actions"><div class="settings-feedback"><span v-if="busy" role="status">{{ t('settings_loading') }}</span><span id="save-result" role="status">{{ saveResult ? t(saveResult) : '' }}</span></div><div class="settings-buttons"><button id="discard-settings-changes" class="secondary" type="button" :disabled="busy" @click="loadConfiguration()"><RotateCcw :size="15" aria-hidden="true" />{{ t('discard_changes') }}</button><button id="save-button" class="primary" form="settings-form" type="submit" :disabled="!editable || !dirty"><Check :size="16" aria-hidden="true" />{{ t(busy ? 'saving' : 'save') }}</button></div></div>
      </div>
    </div>
  </section>
</template>
