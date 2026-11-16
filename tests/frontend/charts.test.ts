import { afterEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import { plot, type ChartPoint, type ChartOptions, type ChartSeries } from '../../pvyieldlens/frontend/src/charts';
import PowerChart from '../../pvyieldlens/frontend/src/PowerChart.vue';

const series = [{ key: 'actual_power' as const, label: 'Power', color: 'blue' }];
const options = { language: 'en' as const, timezone: 'UTC', translate: (key: string) => key };
const cleanup: (() => void)[] = [];
afterEach(() => { cleanup.splice(0).forEach(dispose => dispose()); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function chart(data: ChartPoint[], extra: Partial<ChartOptions> = {}, displayedSeries: ChartSeries[] = series) {
  const host = document.createElement('div');
  document.body.append(host);
  Object.defineProperties(host, { clientWidth: { value: 1200 }, clientHeight: { value: 260 } });
  const handle = plot(host, data, displayedSeries, 'W', { ...options, ...extra });
  cleanup.push(() => { handle?.dispose?.(); host.remove(); });
  return { host, handle };
}
function inspect(host: HTMLElement, at: number, start: number, end: number) {
  host.querySelector('.chart-hit-area')?.dispatchEvent(new MouseEvent('pointermove', {
    clientX: 48 + (at - start) / (end - start) * 1140, clientY: 20,
  }));
}

it('reports unavailable between broken runs and outside point coverage', () => {
  const tooltip = vi.fn((point: ChartPoint) => ({ title: String(point.at), rows: [{ label: 'Power', value: String(point.actual_power) }] }));
  const { host, handle } = chart([
    { at: 20, actual_power: 10 }, { at: 40, actual_power: 20 },
    { at: 80, actual_power: 30, breakBefore: true }, { at: 100, actual_power: 40 },
  ], { range: { start: 0, end: 120 }, tooltip });
  [0, 10, 60, 110, 120].forEach(at => {
    inspect(host, at, 0, 120);
    expect(host.querySelector('.chart-tooltip')?.textContent).toContain('unavailable');
    expect(host.querySelector('.chart-tooltip')?.textContent).toContain('— W');
    expect(host.querySelectorAll('.active-series-marker[visibility="visible"]')).toHaveLength(0);
    expect(handle.selectedAt()).toBeNull();
  });
  expect(tooltip).not.toHaveBeenCalled();
  inspect(host, 35, 0, 120);
  expect(handle.selectedAt()).toBe(40);
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Power20');
  inspect(host, 80, 0, 120);
  expect(handle.selectedAt()).toBe(80);
});

it('uses settlement coverage without rejecting valid interval edges or crossing a missing settlement', () => {
  const window = { start: 20, end: 40, actual_power: 10, estimated_power: 20, pr: 50, optimizable_power: 10,
    actual_energy_wh: 1, estimated_energy_wh: 2, valid_seconds: 20, coverage_percent: 100,
    quality: 'complete' as const, reason: null };
  const { host, handle } = chart([
    { at: 40, actual_power: 10, window },
    { at: 60, actual_power: 20, window: { ...window, start: 40, end: 60 } },
    { at: 140, actual_power: 30, window: { ...window, start: 80, end: 140 }, breakBefore: true },
  ], { range: { start: 0, end: 160 }, coverage: 'windows' });
  [0, 10, 70, 150, 160].forEach(at => {
    inspect(host, at, 0, 160);
    expect(host.querySelector('.chart-tooltip')?.textContent).toContain('unavailable');
  });
  [[20, 40], [40, 40], [41, 40], [60, 60], [80, 140], [100, 140], [140, 140]].forEach(([at, expected]) => {
    inspect(host, at, 0, 160);
    expect(handle.selectedAt()).toBe(expected);
  });
});

it('smooths_without_overshoot', () => {
  const points = [0, 80, 100, 20, 0].map((actual_power, index) => ({ at: [0, 20, 90, 150, 300][index], actual_power }));
  const beforeTotals = structuredClone(points);
  const { host } = chart(points);
  const path = host.querySelector('path.series')!.getAttribute('d')!;
  expect(path).toContain('C');
  expect(path).not.toMatch(/NaN|Infinity/);
  const afterTotals = points;
  expect(beforeTotals).toEqual(afterTotals);
  expect(host.querySelectorAll('path.series')).toHaveLength(series.length);
  expect(chart([{ at: 0, actual_power: 0 }]).host.querySelector('.series-point')).not.toBeNull();
  expect(chart(points.slice(0, 2)).host.querySelector('path.series')!.getAttribute('d')).toContain('L');
  const pr = plot(host, [{ at: 0, pr: 125 }, { at: 1, pr: 0 }], [{ key: 'pr', label: 'PR', color: 'blue' }], '%', options);
  expect(host.textContent).toContain('138');
  expect(host.querySelector('path.series')!.getAttribute('d')).not.toMatch(/NaN|Infinity/);
  pr.dispose();
});

it('retains_missing_segments_before_thinning', () => {
  const points = Array.from({ length: 1201 }, (_, at) => ({ at, actual_power: at === 501 ? null : at % 100 }));
  const { host } = chart(points);
  expect(host.querySelector('path.series')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
  const broken = chart([{ at: 0, actual_power: 0 }, { at: 1, actual_power: 10, breakBefore: true }]);
  expect(broken.host.querySelector('path.series')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
});

it('inspects_raw_points_omitted_by_thinning', () => {
  const rawPoints = Array.from({ length: 1201 }, (_, at) => ({ at, actual_power: at === 502 ? 0 : at }));
  let tooltipPoint: ChartPoint | undefined;
  const { host, handle } = chart(rawPoints, { tooltip: (point: ChartPoint) => {
    tooltipPoint = point;
    return { title: String(point.at), rows: [{ label: 'Power', value: String(point.actual_power) }] };
  } });
  inspect(host, 502, 0, 1200);
  expect(tooltipPoint?.at).toBe(rawPoints[502].at);
  expect(tooltipPoint?.actual_power).toBe(rawPoints[502].actual_power);
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Power0');
  expect(handle.selectedAt()).toBe(502);
  handle.dispose();
  expect(host.querySelector('.chart-tooltip')).toBeNull();
  inspect(host, 503, 0, 1200);
  expect(tooltipPoint?.at).toBe(502);
});

it('uses_half_open_forecast_intervals', () => {
  const points = [0, 3600].map(start => ({ at: start + 1800, power_w: start ? 200 : 100,
    interval: { start, end: start + 3600, power_w: start ? 200 : 100, energy_kwh: 0.1,
      poa_w_m2: 800, air_temperature_c: 20, cell_temperature_c: 45, quality: 'complete' as const } }));
  let intervalAtBoundary: ChartPoint | undefined;
  const { host } = chart(points, { range: { start: 0, end: 7200 }, selection: 'interval',
    tooltip: (point: ChartPoint) => { intervalAtBoundary = point; return { title: String(point.at), rows: [] }; } },
  [{ key: 'power_w', label: 'Forecast power', color: 'blue' }]);
  inspect(host, 3600, 0, 7200);
  expect(intervalAtBoundary?.interval?.start).toBe(3600);
  inspect(host, 7200, 0, 7200);
  expect(intervalAtBoundary?.interval?.start).toBe(3600);
  const missing = chart([{ at: 50, actual_power: null }], { range: { start: 0, end: 100 },
    tooltip: () => ({ title: 'Unavailable', rows: [{ label: 'Power', value: '—' }] }) });
  inspect(missing.host, 50, 0, 100);
  expect(missing.host.querySelector('.chart-tooltip')?.textContent).toBe('UnavailablePower—');
  expect(missing.host.querySelector('path.series')!.getAttribute('d')).toBe('');
  expect(chart([]).handle.selectedAt()).toBeNull();
});

it('preserves_selection_on_redraw', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1200);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(260);
  const props = reactive({ id: 'test-chart', points: [{ at: 0, actual_power: 0 }, { at: 1, actual_power: 10 }],
    series, unit: 'W', active: true, language: 'en' as const, timezone: 'UTC', theme: 'light' as 'light' | 'dark', currentTime: 0 });
  const host = document.createElement('div');
  document.body.append(host);
  const app = createApp({ render: () => h(PowerChart, props) });
  app.mount(host);
  cleanup.push(() => { app.unmount(); host.remove(); });
  host.querySelector<SVGElement>('.chart-hit-area')!.focus();
  inspect(host, 1, 0, 1);
  const before = host.querySelector('.chart-tooltip')?.textContent;
  expect(before).toContain('10');
  const svg = host.querySelector('svg');
  props.currentTime = 1;
  await nextTick();
  expect(host.querySelector('svg')).toBe(svg);
  props.theme = 'dark';
  await nextTick(); await nextTick();
  expect(host.querySelector('.chart-tooltip')?.textContent).toBe(before);
  expect(document.activeElement).toBe(host.querySelector('.chart-hit-area'));
  props.points = [{ at: 0, actual_power: 0 }];
  await nextTick(); await nextTick();
  expect(host.querySelector('.chart-tooltip')?.hasAttribute('hidden')).toBe(true);
  inspect(host, 0, 0, 1);
  props.active = false;
  await nextTick(); await nextTick();
  expect(host.querySelector('.chart-tooltip')).toBeNull();
});

it('waits for measurable chart dimensions before drawing during navigation', async () => {
  let resized = () => {};
  vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { resized = callback; } observe() {} disconnect() {} });
  const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(1200);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(260);
  const host = document.createElement('div');
  document.body.append(host);
  const props = reactive({ id: 'sizing-chart', points: [{ at: 0, actual_power: 0 }],
    series, unit: 'W', active: true, language: 'en' as const, timezone: 'UTC', theme: 'light' as const });
  const app = createApp({ render: () => h(PowerChart, props) });
  app.mount(host);
  cleanup.push(() => { app.unmount(); host.remove(); });
  const initial = host.querySelector('svg');
  width.mockReturnValue(0);
  resized();
  props.points = [{ at: 0, actual_power: 100 }];
  await nextTick(); await nextTick();
  expect(host.querySelector('svg')).toBe(initial);
  width.mockReturnValue(1200);
  resized();
  expect(host.querySelector('svg')).not.toBe(initial);
  host.querySelector('.chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('100 W');
  expect([...host.querySelectorAll('rect')].every(rect => Number(rect.getAttribute('width')) >= 0)).toBe(true);
});

it('keeps unavailable gaps and distinct second-level labels in a short power series', () => {
  const host = document.createElement('div');
  document.body.append(host);
  Object.defineProperties(host, { clientWidth: { value: 1200 }, clientHeight: { value: 260 } });
  // JSDOM has no SVG text layout; supply measured-width geometry for tick collision checks.
  const bounds = vi.spyOn(SVGElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
    return new DOMRect(Number(this.getAttribute('x') ?? 0), 0, 60, 12);
  });
  try {
    plot(host, [
      { at: 1793491200, actual_power: 10 }, { at: 1793491201, actual_power: null },
      { at: 1793491202, actual_power: 20 }, { at: 1793491203, actual_power: 30 },
    ], [{ key: 'actual_power', label: 'Power', color: 'blue' }], 'W', {
      language: 'en', timezone: 'UTC', translate: key => key,
    });
    expect(host.querySelector('path')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
    const ticks = [...host.querySelectorAll('.time-tick')].map(node => node.textContent);
    expect(ticks.length).toBeGreaterThan(1);
    expect(new Set(ticks).size).toBe(ticks.length);
    expect(ticks).toContain('12:00:03 AM');
  } finally {
    bounds.mockRestore();
    host.remove();
  }
});

it('distinguishes repeated local clock ticks when the plotted window spans a DST offset change', () => {
  const host = document.createElement('div');
  document.body.append(host);
  Object.defineProperties(host, { clientWidth: { value: 1200 }, clientHeight: { value: 260 } });
  const bounds = vi.spyOn(SVGElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
    return new DOMRect(Number(this.getAttribute('x') ?? 0), 0, 60, 12);
  });
  try {
    plot(host, [{ at: 1793511000, actual_power: 10 }, { at: 1793514600, actual_power: 20 }],
      [{ key: 'actual_power', label: 'Power', color: 'blue' }], 'W', {
        language: 'en', timezone: 'America/New_York', translate: key => key,
      });
    const ticks = [...host.querySelectorAll('.time-tick')].map(node => node.textContent);
    expect(ticks[0]).toMatch(/01:30.*GMT-4/);
    expect(ticks.at(-1)).toMatch(/01:30.*GMT-5/);
    inspect(host, 1793514600, 1793511000, 1793514600);
    expect(host.querySelector('.chart-tooltip')!.textContent).toMatch(/01:30.*GMT-5/);
  } finally {
    bounds.mockRestore();
    host.remove();
  }
});
