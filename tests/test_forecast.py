from datetime import datetime

import pytest
from pydantic import ValidationError

from pvyieldlens.forecast import ForecastBatch, WeatherSample, calculate_forecast, forecast_view
from pvyieldlens.settings import ForecastSettings, HALocation
from forecast_fixtures import constant_intervals, forecast_input


def test_noct_uses_datasheet_percent_once():
    row, = calculate_forecast(forecast_input(), (
        WeatherSample(at=0, poa_w_m2=800, air_temperature_c=20),
        WeatherSample(at=3600, poa_w_m2=800, air_temperature_c=20),
    ))
    assert (row.start, row.end, row.cell_temperature_c) == (0, 3600, 45)
    assert row.power_w == pytest.approx(3720)
    assert row.energy_kwh == pytest.approx(3.72)
    assert row.quality == 'complete'


def test_forecast_configuration_boundaries():
    defaults = ForecastSettings()
    assert not defaults.enabled
    assert (defaults.tilt_deg, defaults.azimuth_deg, defaults.noct_c) == (None, None, 45)
    for tilt in (0, 90):
        assert ForecastSettings(enabled=True, tilt_deg=tilt, azimuth_deg=0).tilt_deg == tilt
    for missing in ({}, {'tilt_deg': 25}, {'azimuth_deg': 180}):
        with pytest.raises(ValidationError):
            ForecastSettings(enabled=True, **missing)


@pytest.mark.parametrize('changes', [
    {'enabled': 1}, {'tilt_deg': True}, {'azimuth_deg': False}, {'noct_c': True},
    {'tilt_deg': -0.1}, {'tilt_deg': 90.1}, {'azimuth_deg': -0.1}, {'azimuth_deg': 360},
    {'noct_c': 20}, {'noct_c': 80.1},
    *({field: value} for field in ('tilt_deg', 'azimuth_deg', 'noct_c')
      for value in (float('nan'), float('inf'), float('-inf'))),
])
def test_forecast_rejects_invalid_configuration(changes):
    with pytest.raises(ValidationError):
        ForecastSettings(**changes)


def test_weather_uses_right_endpoint_poa_and_mean_endpoint_temperature():
    row, = calculate_forecast(forecast_input(), (
        WeatherSample(at=0, poa_w_m2=None, air_temperature_c=10),
        WeatherSample(at=3600, poa_w_m2=800, air_temperature_c=30),
    ))
    assert row.poa_w_m2 == 800
    assert row.air_temperature_c == 20
    assert row.cell_temperature_c == 45
    assert row.power_w == pytest.approx(3720)


@pytest.mark.parametrize('poa,left_air,right_air,coefficient', [
    (None, 20, 20, -0.35), (800, None, 20, -0.35),
    (800, 20, None, -0.35), (800, 30, 30, -5),
])
def test_missing_weather_or_negative_correction_leaves_interval_unavailable(poa, left_air, right_air, coefficient):
    row, = calculate_forecast(forecast_input(temperature_coefficient_pct_per_c=coefficient), (
        WeatherSample(at=0, poa_w_m2=800, air_temperature_c=left_air),
        WeatherSample(at=3600, poa_w_m2=poa, air_temperature_c=right_air),
    ))
    assert row.power_w is None
    assert row.energy_kwh is None
    assert row.quality == 'unavailable'


def test_zero_irradiance_and_above_rated_power_are_valid():
    night, bright = calculate_forecast(forecast_input(), (
        WeatherSample(at=0, poa_w_m2=None, air_temperature_c=0),
        WeatherSample(at=3600, poa_w_m2=0, air_temperature_c=0),
        WeatherSample(at=7200, poa_w_m2=1200, air_temperature_c=0),
    ))
    assert (night.power_w, night.energy_kwh, night.quality) == (0, 0, 'complete')
    assert bright.power_w == pytest.approx(5737.5)
    assert bright.energy_kwh == pytest.approx(5.7375)


def test_forecast_batch_roundtrip_preserves_inputs_weather_and_fetch_time():
    inputs = forecast_input()
    intervals = calculate_forecast(inputs, (
        WeatherSample(at=0, poa_w_m2=800, air_temperature_c=20),
        WeatherSample(at=3600, poa_w_m2=800, air_temperature_c=20),
    ))
    batch = ForecastBatch(inputs=inputs, fetched_at=123, intervals=intervals)
    assert ForecastBatch.model_validate_json(batch.model_dump_json()) == batch
    with pytest.raises(ValidationError):
        batch.fetched_at = 456


@pytest.mark.parametrize('changes', [
    {'latitude': True}, {'longitude': float('nan')}, {'latitude': 90.1},
    {'longitude': -180.1}, {'timezone': 'not/a/timezone'},
])
def test_location_rejects_invalid_site_values(changes):
    with pytest.raises(ValidationError):
        HALocation.model_validate({
            'origin': 'http://ha.test', 'latitude': 0, 'longitude': 0, 'timezone': 'UTC', **changes,
        })


def test_forecast_days_follow_local_calendar():
    inputs = forecast_input(timezone='Asia/Kathmandu')
    now = datetime.fromisoformat('2026-06-01T20:00:00+00:00').timestamp()
    start = datetime.fromisoformat('2026-06-01T18:15:00+00:00').timestamp()
    batch = ForecastBatch(inputs=inputs, fetched_at=now, intervals=constant_intervals(start - 900, start + 7 * 86400 + 2700))
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), now)
    assert tuple(day.day for day in view.days) == (
        '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05',
        '2026-06-06', '2026-06-07', '2026-06-08',
    )
    assert view.timezone == 'Asia/Kathmandu'
    assert view.today.start == start
    assert view.seven_days.end == start + 7 * 86400
    assert (view.intervals[0].start, view.intervals[0].end) == (start, start + 2700)
    assert view.intervals[0].energy_kwh == pytest.approx(2.79)
    assert view.intervals[-1].end == start + 7 * 86400
    assert view.seven_days.kwh == pytest.approx(624.96)
    assert view.status == 'ready'


def test_remaining_energy_clips_current_interval():
    inputs = forecast_input()
    intervals = (*constant_intervals(13 * 3600, 14 * 3600), *constant_intervals(14 * 3600, 86400, power_w=0))
    batch = ForecastBatch(inputs=inputs, fetched_at=13 * 3600, intervals=intervals)
    settings = ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180)
    first = forecast_view(batch, inputs, settings, 13 * 3600 + 20 * 60)
    later = forecast_view(batch, inputs, settings, 13 * 3600 + 40 * 60)
    assert first.remaining_today.start == 48000
    assert first.remaining_today.kwh == pytest.approx(2.48)
    assert first.remaining_today.coverage_percent == 100
    assert first.remaining_today.quality == 'complete'
    assert later.remaining_today.kwh == pytest.approx(1.24)
    assert first.today.kwh is None
    assert first.fetched_at == later.fetched_at == 13 * 3600
    assert first.calculated_at == 48000
    assert later.calculated_at == 49200


@pytest.mark.parametrize('timezone,start,end,energy', [
    ('Asia/Kathmandu', '2026-06-01T18:15:00+00:00', '2026-06-02T18:15:00+00:00', 89.28),
    ('America/New_York', '2026-03-08T05:00:00+00:00', '2026-03-09T04:00:00+00:00', 85.56),
    ('America/New_York', '2026-11-01T04:00:00+00:00', '2026-11-02T05:00:00+00:00', 93.0),
])
def test_non_hour_timezone_and_dst_day_lengths(timezone, start, end, energy):
    inputs = forecast_input(timezone=timezone)
    start = datetime.fromisoformat(start).timestamp()
    end = datetime.fromisoformat(end).timestamp()
    batch = ForecastBatch(inputs=inputs, fetched_at=start, intervals=constant_intervals(start - 900, end + 2700))
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=0, azimuth_deg=0), start)
    assert (view.today.start, view.today.end) == (start, end)
    assert view.today.kwh == pytest.approx(energy)
    assert view.today.coverage_percent == 100
    assert view.today.quality == 'complete'


def test_missing_interval_invalidates_only_affected_totals():
    inputs = forecast_input()
    intervals = constant_intervals(0, 7 * 86400)
    missing = intervals[12].model_copy(update={
        'poa_w_m2': None, 'cell_temperature_c': None, 'power_w': None,
        'energy_kwh': None, 'quality': 'unavailable',
    })
    night = intervals[24].model_copy(update={
        'poa_w_m2': 0.0, 'power_w': 0.0, 'energy_kwh': 0.0,
    })
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=(
        *intervals[:12], missing, *intervals[13:24], night, *intervals[25:],
    ))
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), 13 * 3600)
    assert view.today.kwh is None
    assert view.today.quality == 'partial'
    assert view.today.coverage_percent == pytest.approx(23 / 24 * 100)
    assert view.remaining_today.kwh == pytest.approx(40.92)
    assert view.tomorrow.kwh == pytest.approx(85.56)
    assert view.tomorrow.quality == 'complete'
    assert view.seven_days.kwh is None
    assert view.status == 'stale'
    assert view.days[0].kwh is None
    assert view.days[1].kwh == pytest.approx(85.56)
    assert view.intervals[12].power_w is None
    assert view.intervals[24].power_w == 0


def test_missing_whole_day_has_zero_coverage_without_invalidating_tomorrow():
    inputs = forecast_input()
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=constant_intervals(86400, 7 * 86400))
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), 0)
    assert (view.today.kwh, view.today.coverage_percent, view.today.quality) == (None, 0, 'unavailable')
    assert view.tomorrow.kwh == pytest.approx(89.28)
    assert view.seven_days.kwh is None
    assert view.seven_days.coverage_percent == pytest.approx(6 / 7 * 100)
    assert view.status == 'partial'


def test_view_empty_states_do_not_invent_weather():
    inputs = forecast_input()
    settings = ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180)
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=constant_intervals(0, 7 * 86400))
    disabled = forecast_view(batch, inputs, ForecastSettings(), 0)
    location = forecast_view(batch, None, settings, 0)
    loading = forecast_view(None, inputs, settings, 0, refreshing=True)
    failed = forecast_view(None, inputs, settings, 0, last_error='weather_unavailable')
    mismatch = forecast_view(batch, forecast_input(origin='http://other.test'), settings, 0)
    assert disabled.status == 'disabled'
    assert location.status == 'location_unavailable'
    assert location.timezone is None
    assert location.today is None
    assert location.days == location.intervals == ()
    assert loading.status == 'loading'
    assert loading.refreshing
    assert failed.status == 'unavailable'
    assert failed.last_error == 'weather_unavailable'
    assert mismatch.status == 'loading'
    for view in (disabled, loading, failed, mismatch):
        assert view.today.kwh is None
        assert view.today.coverage_percent == 0
        assert view.intervals == ()
        assert view.fetched_at is None


@pytest.mark.parametrize('age,last_error,expected', [
    (7199, None, 'ready'), (7200, None, 'stale'), (1, 'weather_unavailable', 'stale'),
])
def test_staleness_keeps_complete_totals_and_original_fetch_time(age, last_error, expected):
    inputs = forecast_input()
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=constant_intervals(0, 7 * 86400))
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180),
                         age, refreshing=True, last_error=last_error)
    assert view.status == expected
    assert view.today.quality == 'complete'
    assert view.today.kwh == pytest.approx(89.28)
    assert view.fetched_at == 0
    assert view.refreshing
    assert view.last_error == last_error


def test_daily_weather_uses_raw_hourly_temperature():
    inputs = forecast_input()
    samples = tuple(WeatherSample(at=index * 3600, poa_w_m2=800,
        air_temperature_c=10 if index % 2 == 0 else 30, weather_code=61 if index == 23 else 0)
        for index in range(7 * 24 + 1))
    batch = ForecastBatch(inputs=inputs, fetched_at=120, intervals=calculate_forecast(inputs, samples), weather_samples=samples)
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), 180)
    day = view.days[0]
    assert day.weather.weather_code == 61
    assert day.weather.temperature_min_c == 10
    assert day.weather.temperature_max_c == 30
    assert day.weather.quality == 'complete'
    assert batch.intervals[0].air_temperature_c == 20
    assert day.kwh == pytest.approx(89.28)
    assert view.today.kwh == day.kwh
    assert 'weather' not in view.today.model_dump()
    assert 'weather' not in view.tomorrow.model_dump()
    assert 'weather_samples' not in view.model_dump()


@pytest.mark.parametrize('timezone,start,end,first,last,count', [
    ('America/New_York', '2026-03-08T05:00:00+00:00', '2026-03-09T04:00:00+00:00', 5, 27, 23),
    ('America/New_York', '2026-11-01T04:00:00+00:00', '2026-11-02T05:00:00+00:00', 4, 28, 25),
    ('Asia/Kathmandu', '2026-06-01T18:15:00+00:00', '2026-06-02T18:15:00+00:00', 19, 42, 24),
])
def test_weather_days_follow_dst_and_fractional_timezone(timezone, start, end, first, last, count):
    inputs = forecast_input(timezone=timezone)
    start, end = datetime.fromisoformat(start).timestamp(), datetime.fromisoformat(end).timestamp()
    base = start // 86400 * 86400
    samples = tuple(WeatherSample(at=base+index*3600, poa_w_m2=800,
        air_temperature_c=float(index), weather_code=61 if index == last else 0) for index in range(216))
    batch = ForecastBatch(inputs=inputs, fetched_at=start, intervals=constant_intervals(base, base+215*3600), weather_samples=samples)
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), start)
    assert (view.today.start, view.today.end) == (start, end)
    members = tuple(sample for sample in samples if start <= sample.at < end)
    assert len(members) == count
    assert (members[0].at, members[-1].at) == (base+first*3600, base+last*3600)
    assert view.days[0].weather.temperature_min_c == first
    assert view.days[0].weather.temperature_max_c == last
    assert view.days[0].weather.weather_code == 61
    assert view.days[0].weather.quality == 'complete'
    assert view.today.kwh == pytest.approx(count * 3.72)


@pytest.mark.parametrize('missing,code,minimum,maximum,quality', [
    ('code', None, 0, 23, 'partial'), ('temperature', 0, None, None, 'partial'),
    ('sample', None, None, None, 'partial'), ('all', None, None, None, 'unavailable'),
])
def test_missing_weather_field_does_not_erase_other_field_or_power(missing, code, minimum, maximum, quality):
    inputs = forecast_input()
    samples = tuple(WeatherSample(at=index*3600, poa_w_m2=800,
        air_temperature_c=None if missing == 'all' or missing == 'temperature' and index == 12 else float(index),
        weather_code=None if missing == 'all' or missing == 'code' and index == 12 else 0)
        for index in range(24) if missing != 'sample' or index != 12)
    batch = ForecastBatch(inputs=inputs, fetched_at=120, intervals=constant_intervals(0, 7*86400), weather_samples=samples)
    view = forecast_view(batch, inputs, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), 180)
    assert view.status == 'ready'
    assert view.today.kwh == pytest.approx(89.28)
    assert view.days[0].weather.model_dump() == dict(weather_code=code, temperature_min_c=minimum,
        temperature_max_c=maximum, quality=quality)
    assert view.days[1].weather is None
