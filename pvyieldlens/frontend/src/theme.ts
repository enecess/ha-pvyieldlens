import { readonly, ref, type Ref } from 'vue';

export type ThemePreference = 'auto' | 'light' | 'dark';
export type ColorMode = 'light' | 'dark';
export type ThemeSource = 'ha' | 'system' | 'manual';

export interface ThemeController {
  preference: Readonly<Ref<ThemePreference>>;
  mode: Readonly<Ref<ColorMode>>;
  source: Readonly<Ref<ThemeSource>>;
  setPreference(value: ThemePreference): void;
  dispose(): void;
}

export function createThemeController(host: Window): ThemeController {
  const preference = ref<ThemePreference>('auto');
  const mode = ref<ColorMode>('light');
  const source = ref<ThemeSource>('system');
  const system = host.matchMedia('(prefers-color-scheme: dark)');
  let parentDocument: Document | undefined;
  try {
    parentDocument = host.parent === host ? undefined : host.parent.document;
  } catch {
    // Cross-origin hosts cannot expose their HA instance.
  }
  try {
    const saved = host.localStorage.getItem('pvyieldlens.theme');
    if (saved === 'light' || saved === 'dark') preference.value = saved;
  } catch {
    // Storage restrictions leave the session preference usable.
  }

  function update() {
    const hass = (parentDocument?.querySelector('home-assistant') as (Element & { hass?: unknown }) | null)?.hass;
    let haDark: boolean | undefined;
    if (hass && typeof hass === 'object') {
      const selected = 'selectedTheme' in hass ? hass.selectedTheme : undefined;
      const themes = 'themes' in hass ? hass.themes : undefined;
      if (selected && typeof selected === 'object' && 'dark' in selected && typeof selected.dark === 'boolean') {
        haDark = selected.dark;
      } else if (themes && typeof themes === 'object' && 'darkMode' in themes && typeof themes.darkMode === 'boolean') {
        haDark = themes.darkMode;
      }
    }
    source.value = preference.value !== 'auto' ? 'manual' : haDark === undefined ? 'system' : 'ha';
    mode.value = preference.value !== 'auto' ? preference.value : (haDark ?? system.matches) ? 'dark' : 'light';
    host.document.documentElement.dataset.theme = mode.value;
    host.document.documentElement.style.colorScheme = mode.value;
  }

  const observer = new MutationObserver(update);
  if (parentDocument) {
    observer.observe(parentDocument.documentElement, { attributes: true, attributeFilter: ['style', 'class'] });
    observer.observe(parentDocument.head, { attributes: true, attributeFilter: ['content'], childList: true, subtree: true });
  }
  system.addEventListener('change', update);
  update();

  return {
    preference: readonly(preference),
    mode: readonly(mode),
    source: readonly(source),
    setPreference(value) {
      preference.value = value;
      try {
        host.localStorage.setItem('pvyieldlens.theme', value);
      } catch {
        // Keep manual control available when storage is blocked or full.
      }
      update();
    },
    dispose() {
      observer.disconnect();
      system.removeEventListener('change', update);
    },
  };
}
