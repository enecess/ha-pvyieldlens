<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { ChevronDown, X } from 'lucide-vue-next';
import { useI18n } from '../i18n';
import type { SourceEntity } from '../models';

const props = withDefaults(defineProps<{
  name: string; label: string; entities: SourceEntity[]; active: boolean; disabled: boolean;
  pattern?: string; required?: boolean; help?: string;
}>(), { required: true, pattern: 'sensor\\.[a-z0-9_]+' });
const model = defineModel<string>({ required: true });
const { t } = useI18n();
const optionalSuffix = computed(() => props.required ? '' : t('optional_sensor_suffix'));
const fullLabel = computed(() => props.label + optionalSuffix.value);
const input = ref<HTMLInputElement>();
const popup = ref<HTMLElement>();
const open = ref(false);
const activeIndex = ref(-1);
const placement = ref({ left: '0px', top: '0px', width: '0px', maxHeight: '240px', transform: '' });
const inputId = computed(() => `sensor-${props.name}`);
const listId = computed(() => `${inputId.value}-options`);
const filtered = computed(() => {
  const query = model.value.trim().toLocaleLowerCase();
  return props.entities.filter(entity => entity.entity_id.toLocaleLowerCase().includes(query)
    || entity.name.toLocaleLowerCase().includes(query));
});

watch(filtered, () => { activeIndex.value = -1; });
watch(() => props.active && !props.disabled, available => { if (!available) open.value = false; });
watch(open, async (visible, _, onCleanup) => {
  if (!visible) { activeIndex.value = -1; return; }
  window.addEventListener('resize', positionPopup);
  document.addEventListener('scroll', positionPopup, true);
  onCleanup(() => {
    window.removeEventListener('resize', positionPopup);
    document.removeEventListener('scroll', positionPopup, true);
  });
  await nextTick();
  positionPopup();
});

function positionPopup() {
  const rect = input.value!.getBoundingClientRect();
  const bounds = input.value!.closest<HTMLElement>('#settings-scroll')!.getBoundingClientRect();
  const viewport = input.value!.closest<HTMLElement>('#content-scroll')!.getBoundingClientRect();
  const bottom = Math.min(viewport.bottom - 8, bounds.bottom, document.querySelector('#settings-actions')!.getBoundingClientRect().top - 6);
  if (rect.bottom <= Math.max(viewport.top, bounds.top) || rect.top >= bottom) { open.value = false; return; }
  const above = Math.max(0, rect.top - viewport.top - 14);
  const below = Math.max(0, bottom - rect.bottom - 6);
  const upward = below < Math.min(240, above);
  const height = Math.min(240, upward ? above : below);
  placement.value = {
    left: `${Math.max(8, rect.left)}px`, width: `${Math.min(rect.width, window.innerWidth - 16)}px`,
    top: `${upward ? rect.top - 6 : rect.bottom + 6}px`, maxHeight: `${height}px`, transform: upward ? 'translateY(-100%)' : '',
  };
}

function show() {
  const container = input.value!.closest<HTMLElement>('#settings-scroll')!;
  const rect = input.value!.getBoundingClientRect();
  const top = Math.max(container.getBoundingClientRect().top, input.value!.closest<HTMLElement>('#content-scroll')!.getBoundingClientRect().top) + 8;
  const bottom = Math.min(window.innerHeight - 8, document.querySelector('#settings-actions')!.getBoundingClientRect().top - 12);
  container.scrollTo({ top: container.scrollTop + (rect.bottom > bottom ? rect.bottom - bottom : rect.top < top ? rect.top - top : 0), behavior: 'instant' });
  open.value = true;
}

function edit(event: Event) {
  model.value = (event.target as HTMLInputElement).value;
  activeIndex.value = -1;
  show();
}

function update(value: string) {
  input.value!.value = value;
  input.value!.dispatchEvent(new Event('input', { bubbles: true }));
  open.value = false;
}

function clear() {
  update('');
  input.value!.focus();
}

async function keydown(event: KeyboardEvent) {
  if (event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key === 'Escape' && open.value) { event.preventDefault(); open.value = false; }
  else if (event.key === 'Tab') open.value = false;
  else if (event.key === 'Enter' && open.value) {
    event.preventDefault();
    if (activeIndex.value >= 0) update(filtered.value[activeIndex.value]!.entity_id);
  } else if (!event.shiftKey && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
    event.preventDefault();
    show();
    activeIndex.value = event.key === 'ArrowDown' ? Math.min(activeIndex.value + 1, filtered.value.length - 1)
      : activeIndex.value < 0 ? filtered.value.length - 1 : Math.max(0, activeIndex.value - 1);
    positionPopup();
    await nextTick();
    popup.value?.querySelector('[aria-selected=true]')?.scrollIntoView({ block: 'nearest' });
  }
}
</script>

<template>
  <div class="sensor-field">
    <label :for="inputId">{{ label }}<span v-if="optionalSuffix" class="sensor-optional">{{ optionalSuffix }}</span></label>
    <div class="sensor-combobox">
      <input :id="inputId" ref="input" :name="name" :value="model" role="combobox" aria-autocomplete="list"
        :aria-expanded="open" :aria-controls="listId" :aria-activedescendant="open && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined"
        :pattern="pattern" :placeholder="t(name.startsWith('forecast_') ? 'search_entities' : 'select_source')" autocomplete="off"
        :required="required" :disabled="disabled" :aria-describedby="help ? inputId + '-help' : undefined"
        @input="edit" @focus="show" @click="show" @blur="open = false" @keydown="keydown">
      <button v-if="!disabled && model.trim()" class="sensor-clear" type="button" :aria-label="t('clear_entity', { field: fullLabel })" @click="clear">
        <X :size="16" aria-hidden="true" />
      </button>
      <ChevronDown :size="14" aria-hidden="true" />
    </div>
    <small v-if="help" :id="inputId + '-help'" class="sensor-help">{{ help }}</small>
    <Teleport to="body">
      <div v-if="open" ref="popup" class="sensor-suggestions" :style="placement">
        <div :id="listId" role="listbox" :aria-label="fullLabel">
          <div v-for="(entity, index) in filtered" :id="`${listId}-${index}`" :key="entity.entity_id" role="option"
            :aria-selected="index === activeIndex" class="sensor-option" @mousedown.prevent @click="update(entity.entity_id)">
            <span class="sensor-option-heading"><span>{{ entity.name }}</span><span class="sensor-option-unit">{{ entity.unit }}</span></span>
            <span class="sensor-option-id">{{ entity.entity_id }}</span>
          </div>
        </div>
        <p v-if="!filtered.length" class="sensor-empty" role="status">{{ t(name.startsWith('forecast_') ? 'no_matching_entities' : 'no_matching_sensors') }}</p>
      </div>
    </Teleport>
  </div>
</template>
