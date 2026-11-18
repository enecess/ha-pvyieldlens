import { afterEach, expect, it, vi } from 'vitest';
import { createApp, h, nextTick, reactive } from 'vue';
import { plot, type ChartPoint, type ChartOptions, type ChartSeries } from '../../pvyieldlens/frontend/src/charts';
import PowerChart from '../../pvyieldlens/frontend/src/PowerChart.vue';

const series = [{ key: 'actual_power_w' as const, label: 'Power', color: 'blue' }];
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

it('picks the nearest original singleton within six CSS pixels after SVG scaling', () => {
  const points = [{ at: 40, actual_power_w: 0 }, { at: 41, actual_power_w: 17.3, breakBefore: true }];
  let selected: ChartPoint | undefined;
  const { host, handle } = chart(points, { range: { start: 0, end: 100 }, tooltip: point => {
    selected = point;
    return { title: String(point.at), rows: [{ label: 'Power', value: String(point.actual_power_w) }] };
  } });
  vi.spyOn(host.querySelector('svg')!, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 0, 600, 130));
  const move = (clientX: number) => host.querySelector('.chart-hit-area')!.dispatchEvent(new MouseEvent('pointermove', { clientX }));
  // x(40) = 504 SVG units = 352 CSS px including the 100px offset.
  move(346);
  expect(handle.selectedAt()).toBe(40);
  expect(selected).toBe(points[0]);
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Power0');
  move(355);
  expect(selected).toBe(points[1]);
  move(364);
  expect(handle.selectedAt()).toBeNull();
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('— W');
});

it('limits pixel tolerance to visible finite singleton glyphs and keeps keyboard records', () => {
  const { host, handle } = chart([
    { at: -0.1, actual_power_w: 10 },
    { at: 20, actual_power_w: null, breakBefore: true },
    { at: 40, actual_power_w: Number.NaN, breakBefore: true },
    { at: 60, actual_power_w: 10, breakBefore: true }, { at: 80, actual_power_w: 20 },
  ], { range: { start: 0, end: 100 } });
  [0, 20.1, 40.1, 80.1].forEach(at => {
    inspect(host, at, 0, 100);
    expect(handle.selectedAt()).toBeNull();
    expect(host.querySelector('.chart-tooltip')?.textContent).toContain('— W');
  });
  const hit = host.querySelector('.chart-hit-area')!;
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
  expect(handle.selectedAt()).toBe(80);
  hit.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
  expect(handle.selectedAt()).toBe(60);
});

it.each(['mouse', 'touch'])('keeps a covered continuous run authoritative over a nearby singleton for %s', pointerType => {
  const points = [{ at: 40, actual_power_w: 10 }, { at: 45, actual_power_w: 20, breakBefore: true }, { at: 46, actual_power_w: 30 }];
  const { host, handle } = chart(points, { range: { start: 0, end: 1000 } });
  const hit = host.querySelector('.chart-hit-area')!;
  const clientX = 48 + 45.1 / 1000 * 1140;
  (pointerType === 'touch' ? ['pointerdown', 'pointerup'] : ['pointermove']).forEach(type => {
    const event = new MouseEvent(type, { clientX, clientY: 20 });
    Object.defineProperty(event, 'pointerType', { value: pointerType });
    hit.dispatchEvent(event);
  });
  expect(handle.selectedAt()).toBe(45);
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('20 W');
});

it.each(['mouse', 'touch'])('retains null-split singleton picking before an unavailable record for %s', pointerType => {
  const { host, handle } = chart([{ at: 40, actual_power_w: 0 }, { at: 41, actual_power_w: null }, { at: 80, actual_power_w: null }],
    { range: { start: 0, end: 1000 } });
  const hit = host.querySelector('.chart-hit-area')!;
  (pointerType === 'touch' ? ['pointerdown', 'pointerup'] : ['pointermove']).forEach(type => {
    const event = new MouseEvent(type, { clientX: 48 + 40 / 1000 * 1140 + 1, clientY: 20 });
    Object.defineProperty(event, 'pointerType', { value: pointerType });
    hit.dispatchEvent(event);
  });
  expect(handle.selectedAt()).toBe(40);
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('0 W');
});

it.each([
  { edge: 'left', at: 0.4, expectedAt: 3, points: [
    { at: -1, actual_power_w: 10 }, { at: 2, actual_power_w: null }, { at: 3, actual_power_w: 20 }, { at: 80, actual_power_w: null },
  ] },
  { edge: 'right', at: 999.6, expectedAt: 997, points: [
    { at: 920, actual_power_w: null }, { at: 997, actual_power_w: 20 }, { at: 998, actual_power_w: null }, { at: 1001, actual_power_w: 10 },
  ] },
].flatMap(test => ['mouse', 'touch'].map(pointerType => ({ ...test, pointerType }))))(
  'keeps a visible singleton when covered nearest is outside the $edge range edge for $pointerType',
  ({ at, expectedAt, points, pointerType }) => {
    const { host, handle } = chart(points, { range: { start: 0, end: 1000 } });
    const hit = host.querySelector('.chart-hit-area')!;
    (pointerType === 'touch' ? ['pointerdown', 'pointerup'] : ['pointermove']).forEach(type => {
      const event = new MouseEvent(type, { clientX: 48 + at / 1000 * 1140, clientY: 20 });
      Object.defineProperty(event, 'pointerType', { value: pointerType });
      hit.dispatchEvent(event);
    });
    expect(handle.selectedAt()).toBe(expectedAt);
    expect(host.querySelector('.chart-tooltip')?.textContent).toContain('20 W');
  },
);

it('reports unavailable between broken runs and outside point coverage', () => {
  const tooltip = vi.fn((point: ChartPoint) => ({ title: String(point.at), rows: [{ label: 'Power', value: String(point.actual_power_w) }] }));
  const { host, handle } = chart([
    { at: 20, actual_power_w: 10 }, { at: 40, actual_power_w: 20 },
    { at: 80, actual_power_w: 30, breakBefore: true }, { at: 100, actual_power_w: 40 },
  ], { range: { start: 0, end: 120 }, tooltip });
  [0, 10, 60, 110, 120].forEach(at => {
    inspect(host, at, 0, 120);
    expect(host.querySelector('.chart-tooltip')?.textContent).toContain('— W');
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

it.each([
  {
    scenario: 'one local date', startUtc: '2026-11-17T23:00:00Z', duration: 8100, hitOffset: 2100,
    uncoveredTitle: '07:02:55', pointTitle: '07:35:00',
  },
  {
    scenario: 'across local midnight', startUtc: '2026-11-18T15:55:00Z', duration: 900, hitOffset: 480,
    uncoveredTitle: '2026年11月18日 23:57:55', pointTitle: '2026年11月19日 00:03:00',
  },
])('uses the same default tooltip time format $scenario', ({ startUtc, duration, hitOffset, uncoveredTitle, pointTitle }) => {
  const start = Date.parse(startUtc) / 1000;
  const end = start + duration;
  const pointAt = start + hitOffset;
  const { host, handle } = chart([start + 300, pointAt, pointAt + 300].map(at => ({ at, irradiance_w_m2: null })),
    { language: 'zh', timezone: 'Asia/Shanghai', range: { start, end } },
    [{ key: 'irradiance_w_m2', label: 'Irradiance', color: 'blue' }]);

  inspect(host, start + 175.25, start, end);
  expect(host.querySelector('.chart-tooltip strong')?.textContent).toBe(uncoveredTitle);
  expect(handle.selectedAt()).toBeNull();

  inspect(host, pointAt + 0.25, start, end);
  expect(host.querySelector('.chart-tooltip strong')?.textContent).toBe(pointTitle);
  expect(handle.selectedAt()).toBe(pointAt);
});

it('uses settlement coverage without rejecting valid interval edges or crossing a missing settlement', () => {
  const window = { start: 20, end: 40, actual_power_w: 10, estimated_power_w: 20, pr: 50, optimizable_power_w: 10,
    actual_energy_wh: 1, estimated_energy_wh: 2, valid_seconds: 20, data_completeness_percent: 100,
    quality: 'complete' as const, reason: null };
  const { host, handle } = chart([
    { at: 40, actual_power_w: 10, window },
    { at: 60, actual_power_w: 20, window: { ...window, start: 40, end: 60 } },
    { at: 140, actual_power_w: 30, window: { ...window, start: 80, end: 140 }, breakBefore: true },
  ], { range: { start: 0, end: 160 }, coverage: 'windows' });
  [0, 10, 70, 150, 160].forEach(at => {
    inspect(host, at, 0, 160);
    expect(host.querySelector('.chart-tooltip')?.textContent).toContain('— W');
  });
  [[20, 40], [40, 40], [41, 40], [60, 60], [80, 140], [100, 140], [140, 140]].forEach(([at, expected]) => {
    inspect(host, at, 0, 160);
    expect(handle.selectedAt()).toBe(expected);
  });
});

it('smooths_without_overshoot', () => {
  const points = [0, 80, 100, 20, 0].map((actual_power_w, index) => ({ at: [0, 20, 90, 150, 300][index], actual_power_w }));
  const beforeTotals = structuredClone(points);
  const { host } = chart(points);
  const path = host.querySelector('path.series')!.getAttribute('d')!;
  expect(path).toContain('C');
  expect(path).not.toMatch(/NaN|Infinity/);
  const afterTotals = points;
  expect(beforeTotals).toEqual(afterTotals);
  expect(host.querySelectorAll('path.series')).toHaveLength(series.length);
  expect(chart([{ at: 0, actual_power_w: 0 }]).host.querySelector('.series-point')).not.toBeNull();
  expect(chart(points.slice(0, 2)).host.querySelector('path.series')!.getAttribute('d')).toContain('L');
  const pr = plot(host, [{ at: 0, pr: 125 }, { at: 1, pr: 0 }], [{ key: 'pr', label: 'PR', color: 'blue' }], '%', options);
  expect(host.textContent).toContain('138');
  expect(host.querySelector('path.series')!.getAttribute('d')).not.toMatch(/NaN|Infinity/);
  pr.dispose();
});

it('retains_missing_segments_before_thinning', () => {
  const points = Array.from({ length: 1201 }, (_, at) => ({ at, actual_power_w: at === 501 ? null : at % 100 }));
  const { host } = chart(points);
  expect(host.querySelector('path.series')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
  const broken = chart([{ at: 0, actual_power_w: 0 }, { at: 1, actual_power_w: 10, breakBefore: true }]);
  expect(broken.host.querySelector('path.series')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
});

it('inspects_raw_points_omitted_by_thinning', () => {
  const rawPoints = Array.from({ length: 1201 }, (_, at) => ({ at, actual_power_w: at === 502 ? 0 : at }));
  let tooltipPoint: ChartPoint | undefined;
  const { host, handle } = chart(rawPoints, { tooltip: (point: ChartPoint) => {
    tooltipPoint = point;
    return { title: String(point.at), rows: [{ label: 'Power', value: String(point.actual_power_w) }] };
  } });
  inspect(host, 502, 0, 1200);
  expect(tooltipPoint?.at).toBe(rawPoints[502].at);
  expect(tooltipPoint?.actual_power_w).toBe(rawPoints[502].actual_power_w);
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Power0');
  expect(handle.selectedAt()).toBe(502);
  handle.dispose();
  expect(host.querySelector('.chart-tooltip')).toBeNull();
  inspect(host, 503, 0, 1200);
  expect(tooltipPoint?.at).toBe(502);
});

it('uses_half_open_forecast_intervals', () => {
  const points = [0, 900].map(start => ({ at: start + 450, forecast_power_w: start ? 200 : 100,
    corrected_forecast_power_w: start ? 180 : 90,
    interval: { start, end: start + 900, forecast_power_w: start ? 200 : 100, forecast_energy_kwh: 0.025,
      corrected_forecast_power_w: start ? 180 : 90, corrected_forecast_energy_kwh: 0.0225,
      irradiance_w_m2: 800, air_temperature_c: 20, cell_temperature_c: 45, quality: 'complete' as const } }));
  let intervalAtBoundary: ChartPoint | undefined;
  const { host } = chart(points, { range: { start: 0, end: 1800 }, selection: 'interval',
    tooltip: (point: ChartPoint) => { intervalAtBoundary = point; return { title: String(point.at), rows: [] }; } },
  [{ key: 'forecast_power_w', label: 'Forecast power', color: 'blue' }]);
  inspect(host, 900, 0, 1800);
  expect(intervalAtBoundary?.interval?.start).toBe(900);
  inspect(host, 1800, 0, 1800);
  expect(intervalAtBoundary?.interval?.start).toBe(900);
  const missing = chart([{ at: 50, actual_power_w: null }], { range: { start: 0, end: 100 },
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
  const props = reactive({ id: 'test-chart', points: [{ at: 0, actual_power_w: 0 }, { at: 1, actual_power_w: 10 }],
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
  props.points = [{ at: 0, actual_power_w: 0 }];
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
  const props = reactive({ id: 'sizing-chart', points: [{ at: 0, actual_power_w: 0 }],
    series, unit: 'W', active: true, language: 'en' as const, timezone: 'UTC', theme: 'light' as const });
  const app = createApp({ render: () => h(PowerChart, props) });
  app.mount(host);
  cleanup.push(() => { app.unmount(); host.remove(); });
  const initial = host.querySelector('svg');
  width.mockReturnValue(0);
  resized();
  props.points = [{ at: 0, actual_power_w: 100 }];
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
      { at: 1793491200, actual_power_w: 10 }, { at: 1793491201, actual_power_w: null },
      { at: 1793491202, actual_power_w: 20 }, { at: 1793491203, actual_power_w: 30 },
    ], [{ key: 'actual_power_w', label: 'Power', color: 'blue' }], 'W', {
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
    plot(host, [{ at: 1793511000, actual_power_w: 10 }, { at: 1793514600, actual_power_w: 20 }],
      [{ key: 'actual_power_w', label: 'Power', color: 'blue' }], 'W', {
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

it('draws the 100 percent reference without limiting PR or changing raw values', () => {
  const points = [{ at: 10, pr: 125 }, { at: 20, pr: null }, { at: 30, pr: 80 }];
  const { host } = chart(points, {}, [{ key: 'pr', label: 'PR', color: 'blue' }]);
  expect(host.querySelectorAll('.reference-line')).toHaveLength(1);
  expect(host.querySelector('path.series')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
  host.querySelector('.chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('125 W');
  expect(points[0].pr).toBe(125);
});

it('keeps input units and missing curves independent from power', () => {
  const { host } = chart([{ at: 10, irradiance_w_m2: 0, module_temperature_c: null },
    { at: 20, irradiance_w_m2: 800, module_temperature_c: 25 }], {}, [
      { key: 'irradiance_w_m2', label: 'Irradiance', color: 'orange' }]);
  expect(host.querySelectorAll('path.series')).toHaveLength(1);
  host.querySelector('.chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Irradiance0 W');
  expect(host.querySelector('.chart-tooltip')?.textContent).not.toContain('data_quality');
});
it('keeps negative module temperatures inside the plotted domain and preserves null gaps', () => {
  const points = [{ at: 10, module_temperature_c: -20 }, { at: 20, module_temperature_c: null },
    { at: 30, module_temperature_c: -5 }];
  const { host } = chart(points, {}, [{ key: 'module_temperature_c', label: 'Module temperature', color: 'teal' }]);
  expect(host.textContent).toContain('-20');
  expect(host.querySelector('path.series')!.getAttribute('d')!.match(/M/g)).toHaveLength(2);
  [...host.querySelectorAll('.series-point')].forEach(point => {
    expect(Number(point.getAttribute('cy'))).toBeGreaterThanOrEqual(16);
    expect(Number(point.getAttribute('cy'))).toBeLessThanOrEqual(226);
  });
  host.querySelector('.chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('-20');
  expect(points[0].module_temperature_c).toBe(-20);
});

it('plots original and corrected forecasts with independent null gaps and uncapped values', () => {
  const { host } = chart([
    { at: 0, forecast_power_w: 100, corrected_forecast_power_w: 120 },
    { at: 900, forecast_power_w: 100, corrected_forecast_power_w: null },
    { at: 1800, forecast_power_w: 0, corrected_forecast_power_w: 0 },
  ], {}, [{ key: 'forecast_power_w', label: 'Original forecast power', color: 'orange' },
    { key: 'corrected_forecast_power_w', label: 'Corrected forecast power', color: 'green' }]);
  expect(host.querySelectorAll('path.series')).toHaveLength(2);
  expect(host.querySelectorAll('path.series')[1].getAttribute('d')!.match(/M/g)).toHaveLength(2);
  host.querySelector('.chart-hit-area')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
  expect(host.querySelector('.chart-tooltip')?.textContent).toContain('Corrected forecast power120 W');
});
