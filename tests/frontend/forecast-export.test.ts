import { expect, it } from 'vitest';
import { buildForecastCsv } from '../../pvyieldlens/frontend/src/forecastExport';

const start = Date.parse('2026-11-18T08:30:00Z') / 1000;
const original = 'forecast_power_w';
const corrected = 'corrected_forecast_power_w';
const intervals = [0, 600.5, 1600, 2400.5].map((watts, index) => ({
  start: start + index * 900,
  end: start + (index + 1) * 900,
  forecast_power_w: watts,
  corrected_forecast_power_w: watts / 2,
}));

it('serializes aligned steps and the chosen power series', () => {
  const original15 = buildForecastCsv(intervals, { start, stepMinutes: 15, steps: 2, power: original });
  const original30 = buildForecastCsv(intervals, { start, stepMinutes: 30, steps: 2, power: original });
  const original60 = buildForecastCsv(intervals, { start, stepMinutes: 60, steps: 1, power: original });
  const corrected30 = buildForecastCsv(intervals, { start, stepMinutes: 30, steps: 2, power: corrected });

  expect(original15).toEqual({ ok: true, end: start + 1800,
    csv: '2026-11-18 08:30:00+00:00,0\n2026-11-18 08:45:00+00:00,600.5\n' });
  expect(original30).toEqual({ ok: true, end: start + 3600,
    csv: '2026-11-18 08:30:00+00:00,300.25\n2026-11-18 09:00:00+00:00,2000.25\n' });
  expect(original60).toEqual({ ok: true, end: start + 3600,
    csv: '2026-11-18 08:30:00+00:00,1150.25\n' });
  expect(corrected30).toEqual({ ok: true, end: start + 3600,
    csv: '2026-11-18 08:30:00+00:00,150.125\n2026-11-18 09:00:00+00:00,1000.125\n' });
});

it('weights partial overlaps', () => {
  const shiftedIntervals = [120, 280, 600].map((watts, index) => ({
    start: start + index * 900 - 450,
    end: start + (index + 1) * 900 - 450,
    forecast_power_w: watts,
    corrected_forecast_power_w: watts / 2,
  }));

  expect(buildForecastCsv(shiftedIntervals, { start, stepMinutes: 30, steps: 1, power: original })).toEqual({
    ok: true,
    end: start + 1800,
    csv: '2026-11-18 08:30:00+00:00,320\n',
  });
});

it('reports the first uncovered step', () => {
  const withNull = intervals.map((interval, index) => index === 1
    ? { ...interval, corrected_forecast_power_w: null }
    : interval);
  const withGap = intervals.filter((_, index) => index !== 1);
  const request = { start, stepMinutes: 15, steps: 4, power: corrected } as const;

  expect(buildForecastCsv(withNull, request)).toEqual({ ok: false, unavailableAt: start + 900 });
  expect(buildForecastCsv(withGap, request)).toEqual({ ok: false, unavailableAt: start + 900 });
  expect(buildForecastCsv(intervals, { start, stepMinutes: 30, steps: 3, power: original }))
    .toEqual({ ok: false, unavailableAt: start + 3600 });
});
