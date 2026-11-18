import type { ForecastInterval } from './models';

export const forecastExportSteps = [15, 30, 60] as const;
export type ForecastExportStep = typeof forecastExportSteps[number];
export type ForecastExportPower = 'forecast_power_w' | 'corrected_forecast_power_w';

export function buildForecastCsv(
  intervals: readonly Pick<ForecastInterval, 'start' | 'end' | ForecastExportPower>[],
  request: { start: number; stepMinutes: ForecastExportStep; steps: number; power: ForecastExportPower },
): { ok: true; csv: string; end: number } | { ok: false; unavailableAt: number } {
  const stepSeconds = request.stepMinutes * 60;
  const end = request.start + request.steps * stepSeconds;
  const rows = [];
  let intervalIndex = 0;

  for (let stepStart = request.start; stepStart < end; stepStart += stepSeconds) {
    const stepEnd = stepStart + stepSeconds;
    let coveredUntil = stepStart;
    let weightedPower = 0;
    let wholeStepPower: number | undefined;

    while (coveredUntil < stepEnd) {
      const interval = intervals[intervalIndex];
      if (interval && interval.end <= coveredUntil) {
        intervalIndex += 1;
        continue;
      }

      const power = interval?.[request.power];
      if (!interval || interval.start > coveredUntil || power == null) {
        return { ok: false, unavailableAt: stepStart };
      }

      const overlapEnd = Math.min(interval.end, stepEnd);
      if (coveredUntil === stepStart && overlapEnd === stepEnd) {
        wholeStepPower = power;
        break;
      }

      weightedPower += power * (overlapEnd - coveredUntil);
      coveredUntil = overlapEnd;
    }

    const utc = new Date(stepStart * 1000).toISOString().slice(0, 19).replace('T', ' ');
    rows.push(`${utc}+00:00,${wholeStepPower ?? weightedPower / stepSeconds}\n`);
  }

  return { ok: true, csv: rows.join(''), end };
}
