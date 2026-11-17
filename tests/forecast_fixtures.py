from math import ceil

from pydantic import JsonValue

from pvyieldlens.forecast import ForecastInput, ForecastInterval
from pvyieldlens.settings import HALocation


def forecast_input(*, home_timezone: str = 'UTC', origin: str = 'http://ha.test',
                   latitude: float = 0.0, longitude: float = 0.0,
                   total_max_power_at_stc_w: float = 5000.0,
                   pmax_temperature_coefficient_pct_per_c: float = -0.35,
                   tilt_deg: float = 25.0, azimuth_deg: float = 180.0,
                   noct_c: float = 45.0) -> ForecastInput:
    return ForecastInput(
        location=HALocation(origin=origin, latitude=latitude, longitude=longitude, home_timezone=home_timezone),
        total_max_power_at_stc_w=total_max_power_at_stc_w,
        pmax_temperature_coefficient_pct_per_c=pmax_temperature_coefficient_pct_per_c,
        tilt_deg=tilt_deg, azimuth_deg=azimuth_deg, noct_c=noct_c,
    )


def constant_intervals(start: float, end: float, forecast_power_w: float = 3720.0,
                       *, interval_seconds: int = 3600) -> tuple[ForecastInterval, ...]:
    return tuple(ForecastInterval(
        start=left, end=min(left + interval_seconds, end), irradiance_w_m2=800.0,
        air_temperature_c=20.0, cell_temperature_c=45.0, forecast_power_w=forecast_power_w,
        forecast_energy_kwh=forecast_power_w * (min(left + interval_seconds, end) - left) / 3_600_000,
        quality='complete',
    ) for left in (start + index * interval_seconds for index in range(ceil((end - start) / interval_seconds))))


def forecast_payload(start: float, hours: int = 216, irradiance_w_m2: float | None = 800.0,
                     air_temperature_c: float | None = 20.0, weather_code: int | None = None) -> dict[str, JsonValue]:
    return {
        'latitude': 0.0, 'longitude': 0.0, 'generationtime_ms': 0.1,
        'utc_offset_seconds': 0, 'timezone': 'GMT', 'timezone_abbreviation': 'GMT', 'elevation': 0.0,
        'minutely_15_units': {'time': 'unixtime', 'global_tilted_irradiance': 'W/m²', 'temperature_2m': '°C'},
        'minutely_15': {
            'time': [start + index * 900 for index in range(hours * 4 + 1)],
            'global_tilted_irradiance': [irradiance_w_m2] * (hours * 4 + 1),
            'temperature_2m': [air_temperature_c] * (hours * 4 + 1),
        },
        'hourly_units': {'time': 'unixtime', 'global_tilted_irradiance': 'W/m²', 'temperature_2m': '°C',
                         **({'weather_code': 'wmo code'} if weather_code is not None else {})},
        'hourly': {
            'time': [start + index * 3600 for index in range(hours + 1)],
            'global_tilted_irradiance': [irradiance_w_m2] * (hours + 1),
            'temperature_2m': [air_temperature_c] * (hours + 1),
            **({'weather_code': [weather_code] * (hours + 1)} if weather_code is not None else {}),
        },
    }
