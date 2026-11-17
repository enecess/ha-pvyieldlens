from sys import float_info
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .forecast import ForecastData, ForecastInput, WeatherSample, calculate_forecast


class _HourlyUnits(BaseModel):
    model_config = ConfigDict(strict=True)

    global_tilted_irradiance: Literal['W/m²']
    temperature_2m: Literal['°C']
    weather_code: JsonValue = None


class _HourlyData(BaseModel):
    model_config = ConfigDict(strict=True)

    time: list[Annotated[float, Field(allow_inf_nan=False)]] = Field(min_length=2)
    global_tilted_irradiance: list[JsonValue]
    temperature_2m: list[JsonValue]
    weather_code: JsonValue = None


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

    async def fetch(self, inputs: ForecastInput) -> ForecastData:
        response = await self.http.get('https://api.open-meteo.com/v1/forecast', params={
            'latitude': inputs.location.latitude, 'longitude': inputs.location.longitude,
            'tilt': inputs.tilt_deg, 'azimuth': inputs.azimuth_deg - 180,
            'hourly': 'global_tilted_irradiance,temperature_2m,weather_code',
            'temperature_unit': 'celsius', 'timezone': 'UTC', 'timeformat': 'unixtime',
            'past_days': 1, 'forecast_days': 8,
        }, timeout=20)
        response.raise_for_status()
        parsed = _ForecastResponse.model_validate(response.json())
        hourly = parsed.hourly
        if any(right - left != 3600 for left, right in zip(hourly.time, hourly.time[1:])):
            raise ValueError('open_meteo_non_hourly_timestamps')
        known_codes = {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
                       71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 97, 99}
        codes = tuple(value if type(value) is int and value in known_codes else None
                      for value in hourly.weather_code) if (
            parsed.hourly_units.weather_code == 'wmo code' and isinstance(hourly.weather_code, list)
            and len(hourly.weather_code) == len(hourly.time)
        ) else (None,) * len(hourly.time)
        samples = tuple(WeatherSample(
            at=at, irradiance_w_m2=_weather_number(poa, minimum=0), air_temperature_c=_weather_number(air),
            weather_code=code,
        ) for at, poa, air, code in zip(hourly.time, hourly.global_tilted_irradiance, hourly.temperature_2m, codes, strict=True))
        return ForecastData(intervals=calculate_forecast(inputs, samples), weather_samples=samples)

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()
