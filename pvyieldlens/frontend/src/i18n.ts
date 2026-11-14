import { computed, ref, watch } from 'vue';
import en from './locales/en.json';
import zh from './locales/zh.json';
import fr from './locales/fr.json';
import de from './locales/de.json';
import pl from './locales/pl.json';
import it from './locales/it.json';

export const languages = ['en', 'zh', 'fr', 'de', 'pl', 'it'] as const;
export type Language = typeof languages[number];
export type LanguageChoice = Language | 'auto';
type Catalogs = Partial<Record<Language, Record<string, string>>> & { en: Record<string, string> };
export const catalogs: Record<Language, Record<string, string>> = { en, zh, fr, de, pl, it };
const isLanguage = (value: string): value is Language => languages.some(language => language === value);

export function selectLanguage(preferences: readonly string[] = [], choice = 'auto'): Language {
  if (isLanguage(choice)) return choice;
  return preferences.map(tag => tag.toLowerCase().split('-')[0]).find(isLanguage) ?? 'en';
}

export function translate(messages: Catalogs, language: Language, key: string, parameters: Record<string, string | number> = {}) {
  return (messages[language]?.[key] ?? messages.en[key] ?? messages.en.error ?? 'An error occurred.')
    .replace(/\{(\w+)\}/g, (match, name: string) => String(parameters[name] ?? match));
}

const languageChoice = ref<LanguageChoice>('auto');
try {
  const saved = localStorage.getItem('pvyieldlens.language');
  if (saved && isLanguage(saved)) languageChoice.value = saved;
} catch {
  // Storage may be disabled in an embedded browser.
}
const preferences = ref(navigator.languages.length ? navigator.languages : [navigator.language || 'en']);
const language = computed(() => selectLanguage(preferences.value, languageChoice.value));
window.addEventListener('languagechange', () => { preferences.value = navigator.languages.length ? navigator.languages : [navigator.language || 'en']; });
watch(language, value => { document.documentElement.lang = value; }, { immediate: true });

export function useI18n() {
  return {
    languageChoice, language,
    t: (key: string, parameters?: Record<string, string | number>) => translate(catalogs, language.value, key, parameters),
    setLanguage(choice: LanguageChoice) {
      languageChoice.value = choice;
      try {
        if (choice === 'auto') localStorage.removeItem('pvyieldlens.language');
        else localStorage.setItem('pvyieldlens.language', choice);
      } catch {
        // Keep the in-memory preference when storage is unavailable.
      }
    },
  };
}
