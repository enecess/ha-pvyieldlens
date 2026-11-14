import { afterEach, describe, expect, it } from 'vitest';
import { createThemeController } from '../../pvyieldlens/frontend/src/theme';

const disposals: (() => void)[] = [];

function themeHost(systemDark: boolean, dark: boolean | undefined, resolvedDark: boolean) {
  const ha = document.createElement('home-assistant');
  const hass = {
    selectedTheme: { theme: 'default', dark },
    themes: { default_theme: 'default', default_dark_theme: null, themes: {}, darkMode: resolvedDark, theme: 'default' },
  };
  Object.assign(ha, { hass });
  const frame = document.createElement('iframe');
  document.body.append(ha, frame);
  const host = frame.contentWindow!;
  const media = new EventTarget();
  Object.assign(media, { matches: systemDark, media: '(prefers-color-scheme: dark)' });
  Object.assign(host, { matchMedia: () => media });
  const meta = document.createElement('meta');
  meta.name = 'color-scheme';
  meta.content = resolvedDark ? 'dark' : 'light';
  document.head.append(meta);
  const controller = createThemeController(host);
  disposals.push(controller.dispose);
  return {
    host, controller,
    async apply(next: boolean | undefined, resolved: boolean) {
      hass.selectedTheme.dark = next;
      hass.themes.darkMode = resolved;
      document.documentElement.style.backgroundColor = resolved ? 'rgb(17, 17, 17)' : 'rgb(255, 255, 255)';
      meta.content = resolved ? 'dark' : 'light';
      await new Promise<void>(resolve => queueMicrotask(resolve));
    },
    system(next: boolean) {
      Object.assign(media, { matches: next });
      media.dispatchEvent(new Event('change'));
    },
  };
}

afterEach(() => {
  disposals.splice(0).forEach(dispose => dispose());
  document.body.replaceChildren();
  document.head.querySelectorAll('meta[name="color-scheme"]').forEach(meta => meta.remove());
  document.documentElement.removeAttribute('style');
  localStorage.clear();
});

describe('HA theme mode', () => {
  it('ha_light_overrides_system_dark', () => {
    const { host, controller } = themeHost(true, false, false);
    expect(controller.mode.value).toBe('light');
    expect(controller.source.value).toBe('ha');
    expect(host.document.documentElement.dataset.theme).toBe('light');
    expect(host.document.documentElement.style.colorScheme).toBe('light');
  });

  it('ha_dark_overrides_system_light', () => {
    const { controller } = themeHost(false, true, true);
    expect(controller.mode.value).toBe('dark');
    expect(controller.source.value).toBe('ha');
  });

  it('ha_auto_tracks_resolved_mode', async () => {
    const { controller, apply } = themeHost(false, undefined, true);
    expect(controller.mode.value).toBe('dark');
    await apply(undefined, false);
    expect(controller.mode.value).toBe('light');
    expect(controller.source.value).toBe('ha');
    await apply(true, true);
    expect(controller.mode.value).toBe('dark');
  });

  it('local_override_and_return_to_auto', async () => {
    const { host, controller, apply, system } = themeHost(false, true, true);
    controller.setPreference('light');
    await apply(undefined, true);
    system(true);
    expect(controller.mode.value).toBe('light');
    expect(controller.source.value).toBe('manual');
    expect(host.localStorage.getItem('pvyieldlens.theme')).toBe('light');
    controller.setPreference('auto');
    expect(controller.mode.value).toBe('dark');
    expect(controller.source.value).toBe('ha');
    expect(host.localStorage.getItem('pvyieldlens.theme')).toBe('auto');
  });

  it('unavailable_parent_and_storage', () => {
    const { host, controller, system } = themeHost(true, undefined, true);
    controller.dispose();
    Object.defineProperty(host, 'parent', { get() { throw new DOMException('Cross origin', 'SecurityError'); } });
    Object.defineProperty(host, 'localStorage', { get() { throw new DOMException('Blocked', 'SecurityError'); } });
    const fallback = createThemeController(host);
    disposals.push(fallback.dispose);
    expect(fallback.preference.value).toBe('auto');
    expect(fallback.mode.value).toBe('dark');
    expect(fallback.source.value).toBe('system');
    system(false);
    expect(fallback.mode.value).toBe('light');
    fallback.setPreference('dark');
    expect(fallback.mode.value).toBe('dark');
    expect(fallback.source.value).toBe('manual');
  });

  it('missing_or_invalid_ha_uses_system_and_invalid_storage_means_auto', () => {
    localStorage.setItem('pvyieldlens.theme', 'invalid');
    const { host, controller, system } = themeHost(true, undefined, true);
    controller.dispose();
    Object.assign(document.querySelector('home-assistant')!, { hass: { selectedTheme: { dark: 'false' }, themes: { darkMode: 'true' } } });
    const fallback = createThemeController(host);
    disposals.push(fallback.dispose);
    expect(fallback.preference.value).toBe('auto');
    expect(fallback.source.value).toBe('system');
    expect(fallback.mode.value).toBe('dark');
    system(false);
    expect(fallback.mode.value).toBe('light');
  });

  it('restores_a_saved_manual_preference', () => {
    localStorage.setItem('pvyieldlens.theme', 'light');
    const { controller } = themeHost(true, true, true);
    expect(controller.preference.value).toBe('light');
    expect(controller.mode.value).toBe('light');
    expect(controller.source.value).toBe('manual');
  });

  it('missing_ha_uses_system_and_disposal_stops_system_updates', () => {
    const { host, controller, system } = themeHost(false, undefined, false);
    controller.dispose();
    document.querySelector('home-assistant')!.remove();
    const fallback = createThemeController(host);
    disposals.push(fallback.dispose);
    expect(fallback.source.value).toBe('system');
    system(true);
    expect(fallback.mode.value).toBe('dark');
    fallback.dispose();
    system(false);
    expect(fallback.mode.value).toBe('dark');
    expect(host.document.documentElement.dataset.theme).toBe('dark');
  });

  it('dispose_stops_updates', async () => {
    const { host, controller, apply, system } = themeHost(false, false, false);
    controller.dispose();
    await apply(true, true);
    system(true);
    expect(controller.mode.value).toBe('light');
    expect(host.document.documentElement.dataset.theme).toBe('light');
  });
});
