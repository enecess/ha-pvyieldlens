import type { Configuration } from './models';
import type { Language } from './i18n';

export function resolveDisplayTimezone(host: Window, mode: Configuration['mode'] | undefined, homeTimezone: string): string {
  const home = homeTimezone ? new Intl.DateTimeFormat('en', { timeZone: homeTimezone }).resolvedOptions().timeZone : 'UTC';
  let preference: 'server' | 'local' | undefined;
  try {
    const hass = host.parent === host ? undefined
      : (host.parent.document.querySelector('home-assistant') as (Element & { hass?: unknown }) | null)?.hass;
    if (hass && typeof hass === 'object' && 'locale' in hass) {
      const locale = hass.locale;
      if (locale && typeof locale === 'object' && 'time_zone' in locale
        && (locale.time_zone === 'server' || locale.time_zone === 'local')) preference = locale.time_zone;
    }
  } catch {
    // Cross-origin hosts cannot expose the current viewer's HA preferences.
  }
  if (preference === 'server' || preference !== 'local' && mode !== 'docker') return home;
  return new Intl.DateTimeFormat().resolvedOptions().timeZone || home;
}

export function formatTimes(instants: readonly number[], language: Language, timezone: string,
  options: Intl.DateTimeFormatOptions): string[] {
  const dates = instants.map(at => new Date(at * 1000));
  const format = new Intl.DateTimeFormat(language, { ...options, timeZone: timezone, timeZoneName: undefined });
  const offsetFormat = new Intl.DateTimeFormat(language, { timeZone: timezone, timeZoneName: 'shortOffset' });
  const localFormat = new Intl.DateTimeFormat('en', { timeZone: timezone, year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3, hourCycle: 'h23' });
  const keys = dates.map(date => localFormat.format(date));
  const offsets = dates.map(date => offsetFormat.formatToParts(date).find(part => part.type === 'timeZoneName')!.value);
  const repeated = new Map<string, Set<string>>();
  keys.forEach((key, index) => {
    if (!repeated.has(key)) repeated.set(key, new Set());
    repeated.get(key)!.add(offsets[index]);
  });
  return dates.map((date, index) => {
    const label = format.format(date);
    return repeated.get(keys[index])!.size > 1
      || index > 0 && offsets[index - 1] !== offsets[index]
      || index < dates.length - 1 && offsets[index + 1] !== offsets[index] ? `${label} ${offsets[index]}` : label;
  });
}
