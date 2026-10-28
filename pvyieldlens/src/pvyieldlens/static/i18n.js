export const languages = ['en', 'zh', 'fr', 'de', 'pl', 'it'];

export function selectLanguage(preferences = []) {
  return preferences.map(tag => tag.toLowerCase().split('-')[0]).find(tag => languages.includes(tag)) || 'en';
}

export function translate(catalogs, language, key, parameters = {}) {
  const message = catalogs[language]?.[key] ?? catalogs.en[key] ?? catalogs.en.error ?? 'An error occurred.';
  return message.replace(/\{(\w+)\}/g, (match, name) => String(parameters[name] ?? match));
}

export function formatCoefficient(value, language) {
  return `${new Intl.NumberFormat(language, { maximumFractionDigits: 5 }).format(value)} %/°C`;
}
