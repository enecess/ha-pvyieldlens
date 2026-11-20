from datetime import datetime, time, timedelta
from math import ceil
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from .correction import ForecastCorrection
from .engine import estimated_power, noct_temperature
from .settings import AngleEntityId, HALocation

ForecastAxis = Literal['tilt', 'azimuth']
ForecastPrerequisite = Literal['configuration_required', 'location_unavailable']


class _ForecastModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)


class ForecastInput(_ForecastModel):
    location: HALocation
    total_max_power_at_stc_w: float = Field(gt=0, le=1_000_000_000)
    pmax_temperature_coefficient_pct_per_c: float = Field(ge=-5, le=5)
    tilt_deg: float = Field(ge=0, le=90)
    azimuth_deg: float = Field(ge=0, lt=360)
    noct_c: float = Field(gt=20, le=80)


class WeatherSample(_ForecastModel):
    at: float
    irradiance_w_m2: float | None = Field(ge=0)
    air_temperature_c: float | None
    weather_code: int | None = None


class ForecastInterval(_ForecastModel):
    start: float
    end: float
    irradiance_w_m2: float | None
    air_temperature_c: float | None
    cell_temperature_c: float | None
    forecast_power_w: float | None
    forecast_energy_kwh: float | None
    quality: Literal['complete', 'unavailable']


class CorrectedForecastInterval(ForecastInterval):
    corrected_forecast_power_w: float | None
    corrected_forecast_energy_kwh: float | None


class ForecastData(_ForecastModel):
    intervals: tuple[ForecastInterval, ...]
    weather_samples: tuple[WeatherSample, ...]


class ForecastBatch(ForecastData):
    inputs: ForecastInput
    fetched_at: float
    tilt_entity: AngleEntityId | None = None
    azimuth_entity: AngleEntityId | None = None
    angles_read_at: float | None = None


def calculate_forecast(inputs: ForecastInput, samples: tuple[WeatherSample, ...]) -> tuple[ForecastInterval, ...]:
    intervals = []
    for left, right in zip(samples, samples[1:]):
        irradiance = right.irradiance_w_m2
        air = (left.air_temperature_c + right.air_temperature_c) / 2 if (
            left.air_temperature_c is not None and right.air_temperature_c is not None
        ) else None
        cell = noct_temperature(air, irradiance, inputs.noct_c) if air is not None and irradiance is not None else None
        power = estimated_power(inputs.total_max_power_at_stc_w, inputs.pmax_temperature_coefficient_pct_per_c / 100, cell, irradiance) if (
            cell is not None and irradiance is not None
        ) else None
        intervals.append(ForecastInterval(
            start=left.at, end=right.at, irradiance_w_m2=irradiance, air_temperature_c=air,
            cell_temperature_c=cell, forecast_power_w=power,
            forecast_energy_kwh=power * (right.at - left.at) / 3_600_000 if power is not None else None,
            quality='complete' if power is not None else 'unavailable',
        ))
    return tuple(intervals)


class EnergyForecast(_ForecastModel):
    start: float
    end: float
    forecast_energy_kwh: float | None
    corrected_forecast_energy_kwh: float | None
    data_completeness_percent: float
    quality: Literal['complete', 'partial', 'unavailable']


class DailyWeather(_ForecastModel):
    weather_code: int | None
    air_temperature_min_c: float | None
    air_temperature_max_c: float | None
    quality: Literal['complete', 'partial', 'unavailable']


class ForecastDay(EnergyForecast):
    day: str
    weather: DailyWeather | None = None


class ForecastGeometry(_ForecastModel):
    tilt_deg: float
    azimuth_deg: float
    read_at: float


class ForecastAngleIssue(_ForecastModel):
    axis: ForecastAxis
    entity_id: AngleEntityId


class ForecastView(_ForecastModel):
    status: ForecastPrerequisite | Literal['loading', 'ready', 'partial', 'stale', 'unavailable']
    refreshing: bool
    fetched_at: float | None
    calculated_at: float
    last_error: str | None
    home_timezone: str | None
    today: EnergyForecast | None
    remaining_today: EnergyForecast | None
    tomorrow: EnergyForecast | None
    seven_days: EnergyForecast | None
    days: tuple[ForecastDay, ...]
    intervals: tuple[CorrectedForecastInterval, ...]
    correction: ForecastCorrection | None
    geometry: ForecastGeometry | None = None
    unavailable_angles: tuple[ForecastAngleIssue, ...] = ()


def forecast_view(batch: ForecastBatch | None, site: HALocation | ForecastPrerequisite, now: float, *,
                  correction: ForecastCorrection | None = None, refreshing: bool = False,
                  last_error: str | None = None, unavailable_angles: tuple[ForecastAngleIssue, ...] = (),
                  include_details: bool = True) -> ForecastView:
    if isinstance(site, str):
        return ForecastView(
            status=site, refreshing=False, fetched_at=None, calculated_at=now, last_error=last_error,
            home_timezone=None, today=None, remaining_today=None, tomorrow=None, seven_days=None,
            days=(), intervals=(), correction=correction, unavailable_angles=unavailable_angles,
        )
    ratio = correction.pr / 100 if correction is not None and correction.pr is not None else None
    zone = ZoneInfo(site.home_timezone)
    local_today = datetime.fromtimestamp(now, zone).date()
    boundaries = tuple(datetime.combine(local_today + timedelta(days=offset), time.min, zone).timestamp()
                       for offset in range(8))
    usable = batch
    rows = tuple(row for row in usable.intervals if row.end > boundaries[0] and row.start < boundaries[-1]) if usable else ()
    if last_error == 'forecast_angle_unavailable' and not any(row.forecast_power_w is not None for row in rows):
        usable = None
        rows = ()

    def total(start: float, end: float) -> EnergyForecast:
        overlap_start, overlap_end = max(start, boundaries[0]), min(end, boundaries[-1])
        parts = tuple((row.forecast_power_w, min(row.end, overlap_end) - max(row.start, overlap_start))
                      for row in rows if row.forecast_power_w is not None and row.end > overlap_start and row.start < overlap_end)
        covered_seconds = sum(seconds for _, seconds in parts)
        complete = abs(covered_seconds - (end - start)) < 1e-6
        energy = sum(power * seconds for power, seconds in parts) / 3_600_000 if complete else None
        return EnergyForecast(
            start=start, end=end,
            forecast_energy_kwh=energy,
            corrected_forecast_energy_kwh=energy * ratio if energy is not None and ratio is not None else None,
            data_completeness_percent=covered_seconds / (end - start) * 100,
            quality='complete' if complete else 'partial' if covered_seconds else 'unavailable',
        )

    today = total(boundaries[0], boundaries[1])
    tomorrow = total(boundaries[1], boundaries[2])
    seven_days = total(boundaries[0], boundaries[-1])
    days = []
    intervals = []
    if include_details:
        day_totals = (today, tomorrow, *(total(start, end) for start, end in zip(boundaries[2:], boundaries[3:])))
        for offset, day_total in enumerate(day_totals):
            start, end = day_total.start, day_total.end
            samples = {sample.at: sample for sample in usable.weather_samples if start <= sample.at < end} if usable else {}
            expected = tuple(range(ceil(start / 3600) * 3600, ceil(end / 3600) * 3600, 3600))
            temperatures = tuple(samples[at].air_temperature_c for at in expected
                                 if at in samples and samples[at].air_temperature_c is not None)
            codes = tuple(samples[at].weather_code for at in expected
                          if at in samples and samples[at].weather_code is not None)
            weather = DailyWeather(
                weather_code=max(codes) if len(codes) == len(expected) else None,
                air_temperature_min_c=min(temperatures) if len(temperatures) == len(expected) else None,
                air_temperature_max_c=max(temperatures) if len(temperatures) == len(expected) else None,
                quality='complete' if len(codes) == len(temperatures) == len(expected) else
                'partial' if codes or temperatures else 'unavailable',
            ) if samples else None
            days.append(ForecastDay(day=(local_today + timedelta(days=offset)).isoformat(), weather=weather,
                                    **day_total.model_dump()))
        for row in rows:
            start, end = max(row.start, boundaries[0]), min(row.end, boundaries[-1])
            power = row.forecast_power_w
            energy = power * (end - start) / 3_600_000 if power is not None else None
            intervals.append(CorrectedForecastInterval(
                **(row.model_dump() | {'start': start, 'end': end, 'forecast_energy_kwh': energy}),
                corrected_forecast_power_w=power * ratio if power is not None and ratio is not None else None,
                corrected_forecast_energy_kwh=energy * ratio if energy is not None and ratio is not None else None,
            ))
    if usable is None:
        status = 'unavailable' if last_error else 'loading'
    elif last_error or now - usable.fetched_at >= 7200:
        status = 'stale'
    else:
        status = 'ready' if seven_days.quality == 'complete' else seven_days.quality
    return ForecastView(
        status=status, refreshing=refreshing, fetched_at=usable.fetched_at if usable else None,
        calculated_at=now, last_error=last_error, home_timezone=site.home_timezone,
        today=today,
        remaining_today=total(now, boundaries[1]),
        tomorrow=tomorrow, seven_days=seven_days, days=tuple(days), intervals=tuple(intervals), correction=correction,
        geometry=ForecastGeometry(tilt_deg=usable.inputs.tilt_deg, azimuth_deg=usable.inputs.azimuth_deg,
                                  read_at=usable.angles_read_at) if usable and usable.angles_read_at is not None else None,
        unavailable_angles=unavailable_angles,
    )
