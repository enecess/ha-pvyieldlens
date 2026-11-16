<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { ChevronDown } from 'lucide-vue-next';
import { useI18n } from '../i18n';
import type { SourceEntity } from '../models';

const props = defineProps<{
  name: string; label: string; entities: SourceEntity[]; active: boolean; disabled: boolean;
}>();
const model = defineModel<string>({ required: true });
const { t } = useI18n();
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
  const bottom = Math.min(window.innerHeight - 8, bounds.bottom, document.querySelector('#settings-actions')!.getBoundingClientRect().top - 6);
  if (rect.bottom <= Math.max(0, bounds.top) || rect.top >= bottom) { open.value = false; return; }
  const above = Math.max(0, rect.top - 14);
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
  const top = Math.max(8, container.getBoundingClientRect().top + 8);
  const bottom = Math.min(window.innerHeight - 8, document.querySelector('#settings-actions')!.getBoundingClientRect().top - 12);
  container.scrollTo({ top: container.scrollTop + (rect.bottom > bottom ? rect.bottom - bottom : rect.top < top ? rect.top - top : 0), behavior: 'instant' });
  open.value = true;
}

function edit(event: Event) {
  model.value = (event.target as HTMLInputElement).value;
  activeIndex.value = -1;
  show();
}

function select(entity: SourceEntity) {
  input.value!.value = entity.entity_id;
  input.value!.dispatchEvent(new Event('input', { bubbles: true }));
  open.value = false;
}

async function keydown(event: KeyboardEvent) {
  if (event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key === 'Escape' && open.value) { event.preventDefault(); open.value = false; }
  else if (event.key === 'Tab') open.value = false;
  else if (event.key === 'Enter' && open.value) {
    event.preventDefault();
    if (activeIndex.value >= 0) select(filtered.value[activeIndex.value]!);
  } else if (!event.shiftKey && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
    event.preventDefault();
    show();
    activeIndex.value = event.key === 'ArrowDown' ? Math.min(activeIndex.value + 1, filtered.value.length - 1)
      : activeIndex.value < 0 ? filtered.value.length - 1 : Math.max(0, activeIndex.value - 1);
    await nextTick();
    popup.value?.querySelector('[aria-selected=true]')?.scrollIntoView({ block: 'nearest' });
  }
}
</script>

<template>
  <div class="sensor-field">
    <label :for="inputId">{{ label }}</label>
    <div class="sensor-combobox">
      <input :id="inputId" ref="input" :name="name" :value="model" role="combobox" aria-autocomplete="list"
        :aria-expanded="open" :aria-controls="listId" :aria-activedescendant="open && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined"
        pattern="sensor\.[a-z0-9_]+" :placeholder="t('select_source')" autocomplete="off" required :disabled="disabled"
        @input="edit" @focus="show" @click="show" @blur="open = false" @keydown="keydown">
      <ChevronDown :size="14" aria-hidden="true" />
    </div>
    <Teleport to="body">
      <div v-if="open" ref="popup" class="sensor-suggestions" :style="placement">
        <div :id="listId" role="listbox" :aria-label="label">
          <div v-for="(entity, index) in filtered" :id="`${listId}-${index}`" :key="entity.entity_id" role="option"
            :aria-selected="index === activeIndex" class="sensor-option" @mousedown.prevent @click="select(entity)">
            <span class="sensor-option-heading"><span>{{ entity.name }}</span><span class="sensor-option-unit">{{ entity.unit }}</span></span>
            <span class="sensor-option-id">{{ entity.entity_id }}</span>
          </div>
        </div>
        <p v-if="!filtered.length" class="sensor-empty" role="status">{{ t('no_matching_sensors') }}</p>
      </div>
    </Teleport>
  </div>
</template>
