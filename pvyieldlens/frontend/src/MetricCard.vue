<script setup lang="ts">
defineProps<{ label: string; unit?: string; context?: string; primary?: boolean }>();
</script>

<template>
  <article class="metric" :class="{ 'metric-primary': primary }">
    <span class="metric-label">{{ label }}</span>
    <div><strong><slot /></strong><span v-if="unit" class="unit">{{ unit }}</span></div>
    <p v-if="context" class="metric-context">{{ context }}</p>
  </article>
</template>
