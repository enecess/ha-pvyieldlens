<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from '../i18n';

const props = defineProps<{ open: boolean; targetLabel: string }>();
const emit = defineEmits<{ cancel: []; discard: [] }>();
const { t } = useI18n();
const dialog = ref<HTMLDialogElement>();
let trigger: HTMLElement | null = null;

watch([() => props.open, dialog], ([open, element]) => {
  if (!element) return;
  if (open) {
    trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
  } else if (element.open) {
    element.close();
    trigger?.focus({ preventScroll: true });
  }
}, { flush: 'post' });
</script>

<template>
  <dialog id="discard-dialog" ref="dialog" aria-labelledby="discard-title" aria-describedby="discard-description" @cancel="emit('cancel')">
    <h2 id="discard-title">{{ t('discard_title') }}</h2>
    <p id="discard-description">{{ t('discard_description', { page: targetLabel }) }}</p>
    <div class="dialog-actions">
      <button id="keep-editing" type="button" class="secondary" :autofocus="open" @click="emit('cancel')">{{ t('keep_editing') }}</button>
      <button id="discard-changes" type="button" class="primary" @click="emit('discard')">{{ t('discard_switch') }}</button>
    </div>
  </dialog>
</template>
