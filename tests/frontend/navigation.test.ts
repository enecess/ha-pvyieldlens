import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createApp, nextTick } from 'vue';
import { setImmediate } from 'node:timers';
import App from '../../pvyieldlens/frontend/src/App.vue';
import DiscardChangesDialog from '../../pvyieldlens/frontend/src/components/DiscardChangesDialog.vue';
import { useI18n } from '../../pvyieldlens/frontend/src/i18n';

const configuration = {
  monitoring_settings: { total_max_power_at_stc_w: 5000, pmax_temperature_coefficient_pct_per_c: -0.35,
    actual_power_entity: 'sensor.power', module_temperature_entity: 'sensor.temp', irradiance_entity: 'sensor.sun',
    settlement_interval_minutes: 1, live_window_seconds: 60, update_interval_seconds: 1,
    actual_power_max_age_seconds: 300, module_temperature_max_age_seconds: 900, irradiance_max_age_seconds: 300, home_timezone: 'UTC' },
  forecast_settings: { tilt_deg: null, azimuth_deg: null, tilt_entity: null, azimuth_entity: null, noct_c: 45, pr_history_days: 14 },
  location: null, mode: 'docker', connection: { url: 'http://ha', token_set: false },
};
let app: ReturnType<typeof createApp>;
let host: HTMLDivElement;
let reads: number;
const flush = async () => { await new Promise<void>(resolve => setImmediate(resolve)); await nextTick(); };
const click = async (selector: string) => { host.querySelector<HTMLElement>(selector)!.click(); await flush(); };
const input = async (value: string) => {
  const field = host.querySelector<HTMLInputElement>('[name=total_max_power_at_stc_w]')!;
  field.value = value;
  field.dispatchEvent(new Event('input', { bubbles: true }));
  await flush();
};
beforeEach(async () => {
  reads = 0;
  useI18n().setLanguage('en');
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  HTMLElement.prototype.scrollTo = function (options: ScrollToOptions | number, top?: number) {
    this.scrollTop = typeof options === 'number' ? top ?? 0 : options.top ?? this.scrollTop;
  };
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  vi.stubGlobal('fetch', async (path: string) => {
    if (path.endsWith('config')) { reads++; return new Response(JSON.stringify(configuration)); }
    return new Response(JSON.stringify({ error: 'error' }), { status: 503 });
  });
  host = document.createElement('div');
  document.body.append(host);
  app = createApp(App);
  app.mount(host);
  await flush();
  await click('#settings-button');
});
afterEach(() => { app.unmount(); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('keeps the selected page and edited draft until discard is confirmed, then loads a fresh form', async () => {
  await input('6100');
  await click('#history-tab');
  expect(host.querySelector('#settings-button')?.getAttribute('aria-current')).toBe('page');
  expect(host.querySelector<HTMLDialogElement>('dialog')?.open).toBe(true);
  await click('#keep-editing');
  expect(host.querySelector<HTMLInputElement>('[name=total_max_power_at_stc_w]')!.value).toBe('6100');
  await click('#history-tab');
  await click('#discard-changes');
  expect(host.querySelector('#history-tab')?.getAttribute('aria-current')).toBe('page');
  expect(host.querySelector<HTMLInputElement>('[name=total_max_power_at_stc_w]')!.value).toBe('5000');
  const before = reads;
  await click('#settings-button');
  expect(reads).toBe(before + 1);
  expect(host.querySelector<HTMLInputElement>('[name=total_max_power_at_stc_w]')!.value).toBe('5000');
});

it('treats a same-page Settings request as a no-op without a read or draft reset', async () => {
  await input('6100');
  const before = reads;
  await click('#settings-button');
  expect(reads).toBe(before);
  expect(host.querySelector<HTMLInputElement>('[name=total_max_power_at_stc_w]')!.value).toBe('6100');
  expect(host.querySelector<HTMLDialogElement>('dialog')?.open ?? false).toBe(false);
});

it('resets content scrolling only after a destination is accepted', async () => {
  const content = host.querySelector<HTMLElement>('#content-scroll');
  expect(content).not.toBeNull();
  content!.scrollTop = 120;
  await input('6100');
  await click('#settings-button');
  expect(content!.scrollTop).toBe(120);
  await click('#history-tab');
  expect(content!.scrollTop).toBe(120);
  await click('#keep-editing');
  expect(content!.scrollTop).toBe(120);
  await click('#history-tab');
  await click('#discard-changes');
  expect(content!.scrollTop).toBe(0);
  content!.scrollTop = 240;
  await click('#history-tab');
  expect(content!.scrollTop).toBe(240);
  await click('#live-tab');
  expect(content!.scrollTop).toBe(0);
});

it.each(['fresh', 'reverted'])('leaves a %s clean form immediately', async state => {
  if (state === 'reverted') { await input('6100'); await input('5000.0'); }
  await click('#history-tab');
  expect(host.querySelector('#history-tab')?.getAttribute('aria-current')).toBe('page');
  expect(host.querySelector<HTMLDialogElement>('dialog')?.open ?? false).toBe(false);
});

it('routes the brand through the same guard and cancels the anchor navigation', async () => {
  await input('6100');
  const event = new MouseEvent('click', { bubbles: true, cancelable: true });
  host.querySelector('.brand')!.dispatchEvent(event);
  await flush();
  expect(event.defaultPrevented).toBe(true);
  expect(host.querySelector<HTMLDialogElement>('dialog')?.open).toBe(true);
  await click('#discard-changes');
  expect(host.querySelector('#live-tab')?.getAttribute('aria-current')).toBe('page');
});

it('opens the confirmation when it is initially requested on mount', async () => {
  app.unmount();
  app = createApp(DiscardChangesDialog, { open: true, targetLabel: 'History' });
  app.mount(host);
  await flush();
  expect(host.querySelector<HTMLDialogElement>('dialog')!.open).toBe(true);
});

it('retains Efficiency range and aggregation while visiting Dashboard and Settings', async () => {
  await click('#history-tab');
  await click('#history-range [data-value="7d"]');
  await click('#history-aggregation [data-value=settlement]');
  await click('#live-tab');
  await click('#settings-button');
  await click('#history-tab');
  expect(host.querySelector('#history-range [data-value="7d"]')?.getAttribute('aria-pressed')).toBe('true');
  expect(host.querySelector('#history-aggregation [data-value=settlement]')?.getAttribute('aria-pressed')).toBe('true');
});
