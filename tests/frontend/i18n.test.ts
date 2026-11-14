import { afterEach, expect, it } from 'vitest';
import { catalogs, languages, selectLanguage, translate, useI18n } from '../../pvyieldlens/frontend/src/i18n';

afterEach(() => { useI18n().setLanguage('auto'); localStorage.clear(); });

it('selects supported regional preferences with English fallback', () => {
  expect(selectLanguage(['es-ES', 'de-AT'])).toBe('de');
  expect(selectLanguage(['fr-CA'])).toBe('fr');
  expect(selectLanguage(['zh-Hans-CN'])).toBe('zh');
  expect(selectLanguage(['pl-PL'])).toBe('pl');
  expect(selectLanguage(['it-IT'])).toBe('it');
  expect(selectLanguage(['es-ES'])).toBe('en');
  expect(selectLanguage([])).toBe('en');
});

it('keeps a manual preference until automatic selection is restored', () => {
  expect(selectLanguage(['de-DE'], 'fr')).toBe('fr');
  expect(selectLanguage(['de-DE'], 'auto')).toBe('de');
  expect(selectLanguage(['de-DE'], 'unknown')).toBe('de');
  const i18n = useI18n();
  i18n.setLanguage('fr');
  expect(useI18n().language.value).toBe('fr');
  expect(localStorage.getItem('pvyieldlens.language')).toBe('fr');
  i18n.setLanguage('auto');
  expect(localStorage.getItem('pvyieldlens.language')).toBeNull();
});

it('falls back per key without displaying untranslated keys', () => {
  expect(translate({ en: { hello: 'Hello {name}' }, de: {} }, 'de', 'hello', { name: 'Ada' })).toBe('Hello Ada');
  expect(translate({ en: { error: 'Please retry' } }, 'de', 'missing')).toBe('Please retry');
});

it('provides equal keys and placeholders in all six catalogs', () => {
  const keys = Object.keys(catalogs.en).sort();
  expect(languages).toEqual(['en', 'zh', 'fr', 'de', 'pl', 'it']);
  languages.forEach(language => {
    expect(Object.keys(catalogs[language]).sort()).toEqual(keys);
    keys.forEach(key => {
      expect(catalogs[language][key]).toBeTruthy();
      expect(catalogs[language][key].match(/\{\w+\}/g)).toEqual(catalogs.en[key].match(/\{\w+\}/g));
    });
  });
});
