from sys import float_info
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .forecast import ForecastInput, ForecastInterval, WeatherSample, calculate_forecast


class _HourlyUnits(BaseModel):
    model_config = ConfigDict(strict=True)

    global_tilted_irradiance: Literal['W/m²']
    temperature_2m: Literal['°C']


class _HourlyData(BaseModel):
    model_config = ConfigDict(strict=True)

    time: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(min_length=2)
    global_tilted_irradiance: list[JsonValue]
    temperature_2m: list[JsonValue]


class _ForecastResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    hourly_units: _HourlyUnits
    hourly: _HourlyData


def _weather_number(value: JsonValue, *, minimum: float = -float_info.max) -> float | None:
    return float(value) if type(value) in (int, float) and minimum <= value <= float_info.max else None


class OpenMeteoClient:
    def __init__(self, http: httpx.AsyncClient | None = None):
        """Accept a dedicated uncredentialed HTTP client whose ownership stays with the caller."""
        self.http = http or httpx.AsyncClient(timeout=20, trust_env=False)
        self._owns_http = http is None

    async def fetch(self, inputs: ForecastInput) -> tuple[ForecastInterval, ...]:
        response = await self.http.get('https://api.open-meteo.com/v1/forecast', params={
            'latitude': inputs.location.latitude, 'longitude': inputs.location.longitude,
            'tilt': inputs.tilt_deg, 'azimuth': inputs.azimuth_deg - 180,
            'hourly': 'global_tilted_irradiance,temperature_2m',
            'temperature_unit': 'celsius', 'timezone': 'UTC', 'timeformat': 'unixtime',
            'past_days': 1, 'forecast_days': 8,
        }, timeout=20)
        response.raise_for_status()
        hourly = _ForecastResponse.model_validate(response.json()).hourly
        if any(right - left != 3600 for left, right in zip(hourly.time, hourly.time[1:])):
            raise ValueError('open_meteo_non_hourly_timestamps')
        samples = tuple(WeatherSample(
            at=at, poa_w_m2=_weather_number(poa, minimum=0), air_temperature_c=_weather_number(air),
        ) for at, poa, air in zip(hourly.time, hourly.global_tilted_irradiance, hourly.temperature_2m, strict=True))
        return calculate_forecast(inputs, samples)

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
