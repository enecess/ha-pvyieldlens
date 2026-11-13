from math import ceil

from pydantic import JsonValue

from pvyieldlens.forecast import ForecastInput, ForecastInterval
from pvyieldlens.settings import HALocation


def forecast_input(*, timezone: str = 'UTC', origin: str = 'http://ha.test',
                   latitude: float = 0.0, longitude: float = 0.0,
                   rated_power_w: float = 5000.0,
                   temperature_coefficient_pct_per_c: float = -0.35,
                   tilt_deg: float = 25.0, azimuth_deg: float = 180.0,
                   noct_c: float = 45.0) -> ForecastInput:
    return ForecastInput(
        location=HALocation(origin=origin, latitude=latitude, longitude=longitude, timezone=timezone),
        rated_power_w=rated_power_w,
        temperature_coefficient_pct_per_c=temperature_coefficient_pct_per_c,
        tilt_deg=tilt_deg, azimuth_deg=azimuth_deg, noct_c=noct_c,
    )


def constant_intervals(start: float, end: float, power_w: float = 3720.0) -> tuple[ForecastInterval, ...]:
    return tuple(ForecastInterval(
        start=left, end=min(left + 3600, end), poa_w_m2=800.0,
        air_temperature_c=20.0, cell_temperature_c=45.0, power_w=power_w,
        energy_kwh=power_w * (min(left + 3600, end) - left) / 3_600_000,
        quality='complete',
    ) for left in (start + index * 3600 for index in range(ceil((end - start) / 3600))))


def hourly_payload(start: float, hours: int = 216, poa_w_m2: float | None = 800.0,
                   air_temperature_c: float | None = 20.0) -> dict[str, JsonValue]:
    return {
        'latitude': 0.0, 'longitude': 0.0, 'generationtime_ms': 0.1,
        'utc_offset_seconds': 0, 'timezone': 'GMT', 'timezone_abbreviation': 'GMT', 'elevation': 0.0,
        'hourly_units': {'time': 'unixtime', 'global_tilted_irradiance': 'W/m²', 'temperature_2m': '°C'},
        'hourly': {
            'time': [start + index * 3600 for index in range(hours + 1)],
            'global_tilted_irradiance': [poa_w_m2] * (hours + 1),
            'temperature_2m': [air_temperature_c] * (hours + 1),
        },
    }
