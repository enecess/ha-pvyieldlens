import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { resolveDisplayTimezone, formatTimes } from '../../pvyieldlens/frontend/src/timezones';

const NativeDateTimeFormat = Intl.DateTimeFormat;
const clock = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' } as const;
function hostWithPreference(preference?: unknown) {
  const ha = document.createElement('home-assistant');
  Object.assign(ha, { hass: { locale: { time_zone: preference } } });
  const frame = document.createElement('iframe');
  document.body.append(ha, frame);
  return frame.contentWindow!;
}
function hostWithoutAccess() {
  const frame = document.createElement('iframe');
  document.body.append(frame);
  Object.defineProperty(frame.contentWindow!, 'parent', {
    get() { throw new DOMException('Cross origin', 'SecurityError'); },
  });
  return frame.contentWindow!;
}
beforeEach(() => {
  vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(function (locales, options) {
    return new NativeDateTimeFormat(locales, { ...options, timeZone: options?.timeZone ?? 'America/Los_Angeles' });
  });
});
afterEach(() => { vi.restoreAllMocks(); document.body.replaceChildren(); });

it('uses_the_current_viewer_preference', () => {
  expect(resolveDisplayTimezone(hostWithPreference('server'), 'app', 'Asia/Shanghai')).toBe('Asia/Shanghai');
  document.body.replaceChildren();
  const host = hostWithPreference('local');
  expect(resolveDisplayTimezone(host, 'app', 'Asia/Shanghai')).toBe('America/Los_Angeles');
  Object.assign(document.querySelector('home-assistant')!, { hass: { locale: { time_zone: 'server' } } });
  expect(resolveDisplayTimezone(host, 'app', 'Asia/Shanghai')).toBe('Asia/Shanghai');
  expect(resolveDisplayTimezone(host, 'app', 'US/Eastern')).toBe('America/New_York');
});

it('falls_back_without_a_host', () => {
  const host = hostWithoutAccess();
  expect(resolveDisplayTimezone(host, 'app', 'Asia/Shanghai')).toBe('Asia/Shanghai');
  expect(resolveDisplayTimezone(host, 'docker', 'Asia/Shanghai')).toBe('America/Los_Angeles');
  expect(resolveDisplayTimezone(host, undefined, '')).toBe('UTC');
});

it('rechecks_a_late_host_and_rejects_unknown_preferences', () => {
  const host = hostWithPreference('America/New_York');
  const ha = document.querySelector('home-assistant')!;
  ha.remove();
  expect(resolveDisplayTimezone(host, 'app', 'Asia/Shanghai')).toBe('Asia/Shanghai');
  document.body.append(ha);
  expect(resolveDisplayTimezone(host, 'app', 'Asia/Shanghai')).toBe('Asia/Shanghai');
  Object.assign(ha, { hass: { locale: { time_zone: 'local' } } });
  expect(resolveDisplayTimezone(host, 'app', 'Asia/Shanghai')).toBe('America/Los_Angeles');
  Object.assign(ha, { hass: { locale: 'local' } });
  expect(resolveDisplayTimezone(host, 'app', 'Asia/Shanghai')).toBe('Asia/Shanghai');
});

it('uses_household_time_when_browser_resolution_is_unavailable', () => {
  vi.mocked(Intl.DateTimeFormat).mockImplementation(function (locales, options) {
    const formatter = new NativeDateTimeFormat(locales, options);
    if (!options?.timeZone) formatter.resolvedOptions = () => ({ ...new NativeDateTimeFormat().resolvedOptions(), timeZone: '' });
    return formatter;
  });
  expect(resolveDisplayTimezone(hostWithPreference('local'), 'app', 'Asia/Shanghai')).toBe('Asia/Shanghai');
  expect(resolveDisplayTimezone(window, 'docker', 'Asia/Shanghai')).toBe('Asia/Shanghai');
  expect(resolveDisplayTimezone(window, 'docker', '')).toBe('UTC');
});

it('adds_offsets_only_when_labels_need_them', () => {
  const plain = formatTimes([1794805200], 'en', 'Asia/Shanghai', clock);
  expect(plain[0]).not.toMatch(/GMT|UTC/);
  const repeated = formatTimes([
    Date.parse('2026-11-01T05:30:00Z') / 1000,
    Date.parse('2026-11-01T06:30:00Z') / 1000,
  ], 'en', 'America/New_York', clock);
  expect(repeated[0]).toMatch(/01:30.*(?:GMT|UTC)[−-]0?4/);
  expect(repeated[1]).toMatch(/01:30.*(?:GMT|UTC)[−-]0?5/);
  const changing = formatTimes([
    Date.parse('2026-11-01T05:15:00Z') / 1000,
    Date.parse('2026-11-01T06:45:00Z') / 1000,
  ], 'en', 'America/New_York', clock);
  expect(changing[0]).toMatch(/01:15.*(?:GMT|UTC)[−-]0?4/);
  expect(changing[1]).toMatch(/01:45.*(?:GMT|UTC)[−-]0?5/);
});

it('keeps_same_instant_duplicates_and_equal_clocks_on_other_dates_plain', () => {
  const at = Date.parse('2026-11-01T05:30:00Z') / 1000;
  expect(formatTimes([at, at], 'en', 'America/New_York', clock)).toEqual(['01:30', '01:30']);
  expect(formatTimes([at, at + 86400], 'en', 'Asia/Shanghai', clock)).toEqual(['13:30', '13:30']);
  expect(formatTimes([at], 'en', 'Asia/Shanghai', { ...clock, timeZone: 'UTC', timeZoneName: 'longOffset' })).toEqual(['13:30']);
});

it('supports_native_date_and_time_styles_when_disambiguating_offsets', () => {
  expect(formatTimes([
    Date.parse('2026-11-01T05:30:00Z') / 1000,
    Date.parse('2026-11-01T06:30:00Z') / 1000,
  ], 'en', 'America/New_York', { dateStyle: 'short', timeStyle: 'short', hourCycle: 'h23' }))
    .toEqual(['11/1/26, 01:30 GMT-4', '11/1/26, 01:30 GMT-5']);
});
