<script setup lang="ts">
import { onUnmounted, ref } from 'vue';
import { Activity, ChartNoAxesCombined, Settings, Sun, SunMoon } from 'lucide-vue-next';
import { createThemeController, type ThemePreference } from './theme';

type Page = 'live' | 'history' | 'forecast' | 'settings';
const page = ref<Page>('live');
const theme = createThemeController(window);
const { preference, mode, source } = theme;
onUnmounted(theme.dispose);

function changeTheme(event: Event) {
  theme.setPreference((event.target as HTMLSelectElement).value as ThemePreference);
}
</script>

<template>
  <header class="app-header">
    <a class="brand" href="./" aria-label="PVYieldLens home">
      <span class="brand-icon"><Sun :size="22" aria-hidden="true" /></span>
      PVYieldLens
    </a>
    <nav id="data-navigation" aria-label="Data pages">
      <button id="live-tab" :aria-current="page === 'live' ? 'page' : undefined" @click="page = 'live'">
        <Activity :size="17" aria-hidden="true" />Live
      </button>
      <button id="history-tab" :aria-current="page === 'history' ? 'page' : undefined" @click="page = 'history'">
        <ChartNoAxesCombined :size="17" aria-hidden="true" />History
      </button>
      <button id="forecast-tab" :aria-current="page === 'forecast' ? 'page' : undefined" @click="page = 'forecast'">
        <Sun :size="17" aria-hidden="true" />Forecast
      </button>
    </nav>
    <div class="utilities">
      <label class="theme-control" for="theme-select">
        <SunMoon :size="16" aria-hidden="true" />
        <span class="sr-only">Theme mode</span>
        <select id="theme-select" :value="preference" @change="changeTheme">
          <option value="auto">Auto</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
      </label>
      <button id="settings-button" :aria-current="page === 'settings' ? 'page' : undefined" @click="page = 'settings'">
        <Settings :size="17" aria-hidden="true" />Settings
      </button>
    </div>
  </header>
  <div class="context-bar">
    <span>Photovoltaic performance</span>
    <span id="theme-mode" :data-source="source">{{ source === 'ha' ? 'Home Assistant' : source === 'system' ? 'System' : 'Manual' }} · {{ mode === 'dark' ? 'Dark' : 'Light' }}</span>
  </div>
  <main>
    <section v-if="page === 'live'" id="live-page" aria-labelledby="live-heading">
      <h1 id="live-heading">Live</h1>
      <div class="empty-panel"><p>No live readings to display.</p></div>
    </section>
    <section v-else-if="page === 'history'" id="history-page" aria-labelledby="history-heading">
      <h1 id="history-heading">History</h1>
      <div class="empty-panel"><p>No history to display.</p></div>
    </section>
    <section v-else-if="page === 'forecast'" id="forecast-page" aria-labelledby="forecast-heading">
      <h1 id="forecast-heading">Forecast</h1>
      <div class="empty-panel"><p>No forecast to display.</p></div>
    </section>
    <section v-else id="settings-page" aria-labelledby="settings-heading">
      <h1 id="settings-heading">Settings</h1>
      <div class="empty-panel"><p>Configuration is not loaded.</p></div>
    </section>
  </main>
</template>
