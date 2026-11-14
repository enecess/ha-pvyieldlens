<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { Activity, ChartNoAxesCombined, Languages, Settings, Sun, SunMoon } from 'lucide-vue-next';
import { createThemeController, type ThemePreference } from './theme';
import { useDashboard } from './dashboard';
import { useI18n, type LanguageChoice } from './i18n';
import LivePage from './LivePage.vue';
import HistoryPage from './HistoryPage.vue';
import ForecastPage from './pages/ForecastPage.vue';
import SettingsPage from './pages/SettingsPage.vue';
import type { SettingsSection } from './settings';

type Page = 'live' | 'history' | 'forecast' | 'settings';
const page = ref<Page>('live');
const settingsSection = ref<SettingsSection>('connection');
const settingsState = ref({ dirty: false, busy: false });
const settingsPage = ref<InstanceType<typeof SettingsPage>>();
const theme = createThemeController(window);
const { preference, mode, source } = theme;
const { configuration, snapshot, livePoints, error, acceptConfiguration, acceptSavedConfiguration } = useDashboard();
const { languageChoice, language, t, setLanguage } = useI18n();
const warnings = computed(() => [error.value, snapshot.value?.error,
  snapshot.value?.history_available === false ? 'history_unavailable' : null,
  snapshot.value?.energy.daily_complete === false ? 'daily_energy_incomplete' : null,
].filter((value): value is string => Boolean(value)));
onUnmounted(theme.dispose);

function changeTheme(event: Event) {
  theme.setPreference((event.target as HTMLSelectElement).value as ThemePreference);
}
function changeLanguage(event: Event) { setLanguage((event.target as HTMLSelectElement).value as LanguageChoice); }
function showPage(value: Page) {
  if (page.value === value || settingsState.value.busy) return;
  page.value = value;
  window.scrollTo(0, 0);
}
function openForecastSettings(section: 'forecast') {
  settingsSection.value = section;
  showPage('settings');
}
</script>

<template>
  <header class="app-header">
    <a class="brand" href="./" aria-label="PVYieldLens home">
      <span class="brand-icon"><Sun :size="22" aria-hidden="true" /></span>
      PVYieldLens
    </a>
    <nav id="data-navigation" :aria-label="t('data_pages')">
      <button id="live-tab" :disabled="settingsState.busy" :aria-current="page === 'live' ? 'page' : undefined" @click="showPage('live')">
        <Activity :size="17" aria-hidden="true" />{{ t('live_page') }}
      </button>
      <button id="history-tab" :disabled="settingsState.busy" :aria-current="page === 'history' ? 'page' : undefined" @click="showPage('history')">
        <ChartNoAxesCombined :size="17" aria-hidden="true" />{{ t('history') }}
      </button>
      <button id="forecast-tab" :disabled="settingsState.busy" :aria-current="page === 'forecast' ? 'page' : undefined" @click="showPage('forecast')">
        <Sun :size="17" aria-hidden="true" />{{ t('forecast') }}
      </button>
    </nav>
    <div class="utilities">
      <label class="theme-control" for="theme-select">
        <SunMoon :size="16" aria-hidden="true" />
        <span class="sr-only">{{ t('theme_mode') }}</span>
        <select id="theme-select" :value="preference" :aria-label="t('theme_mode')" @change="changeTheme">
          <option value="auto">{{ t('auto') }}</option>
          <option value="light">{{ t('light') }}</option>
          <option value="dark">{{ t('dark') }}</option>
        </select>
      </label>
      <label class="language-picker"><Languages :size="16" aria-hidden="true" /><select id="language-select" :value="languageChoice" :aria-label="t('language')" @change="changeLanguage">
        <option value="auto">{{ t('auto') }}</option><option value="en">English</option><option value="zh">中文</option><option value="fr">Français</option><option value="de">Deutsch</option><option value="pl">Polski</option><option value="it">Italiano</option>
      </select></label>
      <button id="settings-button" :disabled="settingsState.busy" :aria-current="page === 'settings' ? 'page' : undefined" @click="showPage('settings')">
        <Settings :size="17" aria-hidden="true" />{{ t('settings') }}
      </button>
    </div>
  </header>
  <div class="context-bar">
    <span id="connection-state" role="status"><span class="status-dot" :class="{ good: snapshot?.connected && !error }"></span>{{ t(!configuration?.settings ? 'unconfigured' : snapshot?.connected && !error ? 'live' : 'offline') }}</span>
    <span id="theme-mode" :data-source="source">{{ t(`theme_source_${source}`) }} · {{ t(mode) }}</span>
  </div>
  <main :class="{ 'settings-active': page === 'settings' }" :data-configuration-ready="configuration !== null" :data-snapshot-ready="snapshot !== null">
    <div v-show="warnings.length" id="banner" class="banner" role="status">{{ warnings.map(key => t(key)).join(' ') }}</div>
    <LivePage v-show="page === 'live'" :active="page === 'live'" :configuration="configuration" :snapshot="snapshot" :points="livePoints" :language="language" :theme="mode" @open-settings="showPage('settings')" />
    <HistoryPage v-show="page === 'history'" :active="page === 'history'" :configuration="configuration" :snapshot="snapshot" :language="language" :theme="mode" />
    <ForecastPage v-show="page === 'forecast'" :active="page === 'forecast'" :summary="snapshot?.forecast ?? null" :language="language" :theme="mode" @open-settings="openForecastSettings" />
    <SettingsPage v-show="page === 'settings'" ref="settingsPage" :active="page === 'settings'" :initial-section="settingsSection" :location="configuration?.location ?? null" @loaded="acceptConfiguration" @saved="acceptSavedConfiguration" @state-change="settingsState = $event" />
  </main>
</template>
