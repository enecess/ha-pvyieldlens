from datetime import datetime

import pytest
from pydantic import ValidationError

from pvyieldlens.forecast import ForecastAngleIssue, ForecastBatch, WeatherSample, calculate_forecast, forecast_view
from pvyieldlens.settings import ForecastSettings, HALocation
from forecast_fixtures import constant_intervals, forecast_input


@pytest.mark.parametrize('seconds,energy', [(900, 0.93), (1200, 1.24), (3600, 3.72)])
def test_quarter_hour_noct_and_arbitrary_duration_energy(seconds, energy):
    row, = calculate_forecast(forecast_input(), (
        WeatherSample(at=0, irradiance_w_m2=800, air_temperature_c=20),
        WeatherSample(at=seconds, irradiance_w_m2=800, air_temperature_c=20),
    ))
    assert (row.start, row.end, row.cell_temperature_c) == (0, seconds, 45)
    assert row.forecast_power_w == pytest.approx(3720)
    assert row.forecast_energy_kwh == pytest.approx(energy)
    assert row.quality == 'complete'


def test_forecast_configuration_boundaries():
    empty = ForecastSettings()
    assert empty.geometry_sources is None
    mixed = ForecastSettings(tilt_entity='sensor.tilt', azimuth_deg=180)
    assert mixed.geometry_sources == ('sensor.tilt', 180)
    assert ForecastSettings.model_validate_json(mixed.model_dump_json()) == mixed
    for tilt in (0, 90):
        assert ForecastSettings(tilt_deg=tilt, azimuth_deg=0).geometry_sources == (tilt, 0)
    assert ForecastSettings(tilt_deg=25).geometry_sources is None


@pytest.mark.parametrize('changes', [
    {'tilt_deg': True}, {'azimuth_deg': False}, {'noct_c': True},
    {'tilt_deg': -0.1}, {'tilt_deg': 90.1}, {'azimuth_deg': -0.1}, {'azimuth_deg': 360},
    {'noct_c': 20}, {'noct_c': 80.1},
    {'tilt_deg': 0, 'tilt_entity': 'sensor.tilt'},
    {'tilt_deg': 0, 'azimuth_deg': 0, 'azimuth_entity': 'number.azimuth'},
    *({'tilt_entity': entity} for entity in ('', 'sensor.', 'sensor.Tilt', 'switch.tilt', 'sensor.pvyieldlens_tilt')),
    *({field: value} for field in ('tilt_deg', 'azimuth_deg', 'noct_c')
      for value in (float('nan'), float('inf'), float('-inf'))),
])
def test_forecast_rejects_invalid_configuration(changes):
    with pytest.raises(ValidationError):
        ForecastSettings(**changes)


def test_weather_uses_right_endpoint_irradiance_and_mean_endpoint_temperature():
    row, = calculate_forecast(forecast_input(), (
        WeatherSample(at=0, irradiance_w_m2=None, air_temperature_c=10),
        WeatherSample(at=3600, irradiance_w_m2=800, air_temperature_c=30),
    ))
    assert row.irradiance_w_m2 == 800
    assert row.air_temperature_c == 20
    assert row.cell_temperature_c == 45
    assert row.forecast_power_w == pytest.approx(3720)


@pytest.mark.parametrize('irradiance,left_air,right_air,coefficient', [
    (None, 20, 20, -0.35), (800, None, 20, -0.35),
    (800, 20, None, -0.35), (800, 30, 30, -5),
])
def test_missing_weather_or_negative_correction_leaves_interval_unavailable(irradiance, left_air, right_air, coefficient):
    row, = calculate_forecast(forecast_input(pmax_temperature_coefficient_pct_per_c=coefficient), (
        WeatherSample(at=0, irradiance_w_m2=800, air_temperature_c=left_air),
        WeatherSample(at=3600, irradiance_w_m2=irradiance, air_temperature_c=right_air),
    ))
    assert row.forecast_power_w is None
    assert row.forecast_energy_kwh is None
    assert row.quality == 'unavailable'


def test_zero_irradiance_and_above_rated_power_are_valid():
    night, bright = calculate_forecast(forecast_input(), (
        WeatherSample(at=0, irradiance_w_m2=None, air_temperature_c=0),
        WeatherSample(at=3600, irradiance_w_m2=0, air_temperature_c=0),
        WeatherSample(at=7200, irradiance_w_m2=1200, air_temperature_c=0),
    ))
    assert (night.forecast_power_w, night.forecast_energy_kwh, night.quality) == (0, 0, 'complete')
    assert bright.forecast_power_w == pytest.approx(5737.5)
    assert bright.forecast_energy_kwh == pytest.approx(5.7375)


def test_forecast_batch_roundtrip_preserves_inputs_weather_and_fetch_time():
    inputs = forecast_input()
    intervals = calculate_forecast(inputs, (
        WeatherSample(at=0, irradiance_w_m2=800, air_temperature_c=20),
        WeatherSample(at=3600, irradiance_w_m2=800, air_temperature_c=20),
    ))
    batch = ForecastBatch(inputs=inputs, fetched_at=123, intervals=intervals, weather_samples=())
    assert ForecastBatch.model_validate_json(batch.model_dump_json()) == batch
    with pytest.raises(ValidationError):
        batch.fetched_at = 456


@pytest.mark.parametrize('changes', [
    {'latitude': True}, {'longitude': float('nan')}, {'latitude': 90.1},
    {'longitude': -180.1}, {'home_timezone': 'not/a/home_timezone'},
])
def test_location_rejects_invalid_site_values(changes):
    with pytest.raises(ValidationError):
        HALocation.model_validate({
            'origin': 'http://ha.test', 'latitude': 0, 'longitude': 0, 'home_timezone': 'UTC', **changes,
        })


def test_quarter_hour_forecast_days_follow_fractional_local_calendar_and_clip_boundaries():
    inputs = forecast_input(home_timezone='Asia/Kathmandu')
    now = datetime.fromisoformat('2026-06-01T20:00:00+00:00').timestamp()
    start = datetime.fromisoformat('2026-06-01T18:15:00+00:00').timestamp()
    batch = ForecastBatch(inputs=inputs, fetched_at=now, intervals=constant_intervals(start - 300, start + 7 * 86400 + 600, interval_seconds=900), weather_samples=())
    view = forecast_view(batch, inputs.location, now)
    assert tuple(day.day for day in view.days) == (
        '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05',
        '2026-06-06', '2026-06-07', '2026-06-08',
    )
    assert view.home_timezone == 'Asia/Kathmandu'
    assert view.today.start == start
    assert view.seven_days.end == start + 7 * 86400
    assert (view.intervals[0].start, view.intervals[0].end) == (start, start + 600)
    assert view.intervals[0].forecast_energy_kwh == pytest.approx(0.62)
    assert (view.intervals[-1].start, view.intervals[-1].end) == (start + 7 * 86400 - 300, start + 7 * 86400)
    assert view.intervals[-1].forecast_energy_kwh == pytest.approx(0.31)
    assert view.seven_days.forecast_energy_kwh == pytest.approx(624.96)
    assert view.status == 'ready'


def test_quarter_hour_remaining_energy_clips_current_interval():
    inputs = forecast_input()
    intervals = (*constant_intervals(13 * 3600, 14 * 3600, interval_seconds=900),
                 *constant_intervals(14 * 3600, 86400, forecast_power_w=0, interval_seconds=900))
    batch = ForecastBatch(inputs=inputs, fetched_at=13 * 3600, intervals=intervals, weather_samples=())
    first = forecast_view(batch, inputs.location, 13 * 3600 + 20 * 60)
    later = forecast_view(batch, inputs.location, 13 * 3600 + 40 * 60)
    assert first.remaining_today.start == 48000
    assert first.remaining_today.forecast_energy_kwh == pytest.approx(2.48)
    assert first.remaining_today.data_completeness_percent == 100
    assert first.remaining_today.quality == 'complete'
    assert later.remaining_today.forecast_energy_kwh == pytest.approx(1.24)
    assert first.today.forecast_energy_kwh is None
    assert first.fetched_at == later.fetched_at == 13 * 3600
    assert first.calculated_at == 48000
    assert later.calculated_at == 49200


@pytest.mark.parametrize('home_timezone,start,end,energy', [
    ('Asia/Kathmandu', '2026-06-01T18:15:00+00:00', '2026-06-02T18:15:00+00:00', 89.28),
    ('America/New_York', '2026-03-08T05:00:00+00:00', '2026-03-09T04:00:00+00:00', 85.56),
    ('America/New_York', '2026-11-01T04:00:00+00:00', '2026-11-02T05:00:00+00:00', 93.0),
])
def test_quarter_hour_non_hour_timezone_and_dst_day_lengths(home_timezone, start, end, energy):
    inputs = forecast_input(home_timezone=home_timezone)
    start = datetime.fromisoformat(start).timestamp()
    end = datetime.fromisoformat(end).timestamp()
    batch = ForecastBatch(inputs=inputs, fetched_at=start, intervals=constant_intervals(start - 900, end + 900, interval_seconds=900), weather_samples=())
    view = forecast_view(batch, inputs.location, start)
    assert (view.today.start, view.today.end) == (start, end)
    assert len(tuple(row for row in view.intervals if start <= row.start < end)) == (end - start) / 900
    assert all(row.end - row.start == 900 for row in view.intervals)
    assert view.today.forecast_energy_kwh == pytest.approx(energy)
    assert view.today.data_completeness_percent == 100
    assert view.today.quality == 'complete'


def test_missing_quarter_hour_interval_invalidates_only_affected_totals():
    inputs = forecast_input()
    intervals = constant_intervals(0, 7 * 86400, interval_seconds=900)
    missing = intervals[48].model_copy(update={
        'irradiance_w_m2': None, 'cell_temperature_c': None, 'forecast_power_w': None,
        'forecast_energy_kwh': None, 'quality': 'unavailable',
    })
    night = intervals[96].model_copy(update={
        'irradiance_w_m2': 0.0, 'forecast_power_w': 0.0, 'forecast_energy_kwh': 0.0,
    })
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=(
        *intervals[:48], missing, *intervals[49:96], night, *intervals[97:],
    ), weather_samples=())
    view = forecast_view(batch, inputs.location, 13 * 3600)
    assert view.today.forecast_energy_kwh is None
    assert view.today.quality == 'partial'
    assert view.today.data_completeness_percent == pytest.approx(95 / 96 * 100)
    assert view.remaining_today.forecast_energy_kwh == pytest.approx(40.92)
    assert view.tomorrow.forecast_energy_kwh == pytest.approx(88.35)
    assert view.tomorrow.quality == 'complete'
    assert view.seven_days.forecast_energy_kwh is None
    assert view.status == 'stale'
    assert view.days[0].forecast_energy_kwh is None
    assert view.days[1].forecast_energy_kwh == pytest.approx(88.35)
    assert view.intervals[48].forecast_power_w is None
    assert view.intervals[96].forecast_power_w == 0


def test_missing_whole_day_has_zero_coverage_without_invalidating_tomorrow():
    inputs = forecast_input()
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=constant_intervals(86400, 7 * 86400), weather_samples=())
    view = forecast_view(batch, inputs.location, 0)
    assert (view.today.forecast_energy_kwh, view.today.data_completeness_percent, view.today.quality) == (None, 0, 'unavailable')
    assert view.tomorrow.forecast_energy_kwh == pytest.approx(89.28)
    assert view.seven_days.forecast_energy_kwh is None
    assert view.seven_days.data_completeness_percent == pytest.approx(6 / 7 * 100)
    assert view.status == 'partial'


def test_view_empty_states_do_not_invent_weather():
    inputs = forecast_input()
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=constant_intervals(0, 7 * 86400), weather_samples=())
    configuration = forecast_view(batch, 'configuration_required', 0)
    location = forecast_view(batch, 'location_unavailable', 0)
    loading = forecast_view(None, inputs.location, 0, refreshing=True)
    failed = forecast_view(None, inputs.location, 0, last_error='weather_unavailable')
    assert configuration.status == 'configuration_required'
    assert location.status == 'location_unavailable'
    for view in (configuration, location):
        assert view.home_timezone is None
        assert view.today is None
        assert view.days == view.intervals == ()
    assert loading.status == 'loading'
    assert loading.refreshing
    assert failed.status == 'unavailable'
    assert failed.last_error == 'weather_unavailable'
    for view in (loading, failed):
        assert view.today.forecast_energy_kwh is None
        assert view.today.data_completeness_percent == 0
        assert view.intervals == ()
        assert view.fetched_at is None


@pytest.mark.parametrize('irradiance', [None, 0], ids=['missing', 'zero'])
def test_angle_failure_requires_overlapping_cached_power(irradiance):
    inputs = forecast_input()
    batch = ForecastBatch(
        inputs=inputs, fetched_at=-1, tilt_entity='sensor.tilt', angles_read_at=-2, weather_samples=(),
        intervals=calculate_forecast(inputs, (
            WeatherSample(at=-3600, irradiance_w_m2=800, air_temperature_c=20),
            WeatherSample(at=0, irradiance_w_m2=800, air_temperature_c=20),
            WeatherSample(at=3600, irradiance_w_m2=irradiance, air_temperature_c=20),
            WeatherSample(at=7200, irradiance_w_m2=None, air_temperature_c=20),
        )),
    )
    issues = (ForecastAngleIssue(axis='tilt', entity_id='sensor.tilt'),)
    view = forecast_view(batch, inputs.location, 0,
                         last_error='forecast_angle_unavailable', unavailable_angles=issues)
    assert view.last_error == 'forecast_angle_unavailable'
    assert view.unavailable_angles == issues
    if irradiance is None:
        assert view.status == 'unavailable'
        assert view.intervals == ()
        assert view.geometry is None
        assert view.fetched_at is None
        assert view.today.forecast_energy_kwh is None
    else:
        assert view.status == 'stale'
        assert tuple(row.forecast_power_w for row in view.intervals) == (0, None)
        assert view.geometry.model_dump() == {'tilt_deg': 25, 'azimuth_deg': 180, 'read_at': -2}
        assert view.fetched_at == -1


@pytest.mark.parametrize('age,last_error,expected', [
    (7199, None, 'ready'), (7200, None, 'stale'), (1, 'weather_unavailable', 'stale'),
])
def test_staleness_keeps_complete_totals_and_original_fetch_time(age, last_error, expected):
    inputs = forecast_input()
    batch = ForecastBatch(inputs=inputs, fetched_at=0, intervals=constant_intervals(0, 7 * 86400), weather_samples=())
    view = forecast_view(batch, inputs.location, age, refreshing=True, last_error=last_error)
    assert view.status == expected
    assert view.today.quality == 'complete'
    assert view.today.forecast_energy_kwh == pytest.approx(89.28)
    assert view.fetched_at == 0
    assert view.refreshing
    assert view.last_error == last_error


def test_weather_sampling_uses_raw_hourly_temperature_with_quarter_hour_power():
    inputs = forecast_input()
    samples = tuple(WeatherSample(at=index * 3600, irradiance_w_m2=800,
        air_temperature_c=10 if index % 2 == 0 else 30, weather_code=61 if index == 23 else 0)
        for index in range(7 * 24 + 1))
    batch = ForecastBatch(inputs=inputs, fetched_at=120, intervals=constant_intervals(0, 7 * 86400, interval_seconds=900), weather_samples=samples)
    view = forecast_view(batch, inputs.location, 180)
    day = view.days[0]
    assert day.weather.weather_code == 61
    assert day.weather.air_temperature_min_c == 10
    assert day.weather.air_temperature_max_c == 30
    assert day.weather.quality == 'complete'
    assert batch.intervals[0].air_temperature_c == 20
    assert len(tuple(row for row in view.intervals if row.start < 86400)) == 96
    assert day.forecast_energy_kwh == pytest.approx(89.28)
    assert view.today.forecast_energy_kwh == day.forecast_energy_kwh
    assert 'weather' not in view.today.model_dump()
    assert 'weather' not in view.tomorrow.model_dump()
    assert 'weather_samples' not in view.model_dump()


@pytest.mark.parametrize('home_timezone,start,end,first,last,count', [
    ('America/New_York', '2026-03-08T05:00:00+00:00', '2026-03-09T04:00:00+00:00', 5, 27, 23),
    ('America/New_York', '2026-11-01T04:00:00+00:00', '2026-11-02T05:00:00+00:00', 4, 28, 25),
    ('Asia/Kathmandu', '2026-06-01T18:15:00+00:00', '2026-06-02T18:15:00+00:00', 19, 42, 24),
])
def test_weather_sampling_days_follow_dst_and_fractional_timezone(home_timezone, start, end, first, last, count):
    inputs = forecast_input(home_timezone=home_timezone)
    start, end = datetime.fromisoformat(start).timestamp(), datetime.fromisoformat(end).timestamp()
    base = start // 86400 * 86400
    samples = tuple(WeatherSample(at=base+index*3600, irradiance_w_m2=800,
        air_temperature_c=float(index), weather_code=61 if index == last else 0) for index in range(216))
    batch = ForecastBatch(inputs=inputs, fetched_at=start, intervals=constant_intervals(base, base+215*3600, interval_seconds=900), weather_samples=samples)
    view = forecast_view(batch, inputs.location, start)
    assert (view.today.start, view.today.end) == (start, end)
    members = tuple(sample for sample in samples if start <= sample.at < end)
    assert len(members) == count
    assert len(tuple(row for row in view.intervals if row.start < end)) == count * 4
    assert (members[0].at, members[-1].at) == (base+first*3600, base+last*3600)
    assert view.days[0].weather.air_temperature_min_c == first
    assert view.days[0].weather.air_temperature_max_c == last
    assert view.days[0].weather.weather_code == 61
    assert view.days[0].weather.quality == 'complete'
    assert view.today.forecast_energy_kwh == pytest.approx(count * 3.72)


@pytest.mark.parametrize('missing,code,minimum,maximum,quality', [
    ('code', None, 0, 23, 'partial'), ('temperature', 0, None, None, 'partial'),
    ('sample', None, None, None, 'partial'), ('all', None, None, None, 'unavailable'),
])
def test_missing_weather_field_does_not_erase_other_field_or_power(missing, code, minimum, maximum, quality):
    inputs = forecast_input()
    samples = tuple(WeatherSample(at=index*3600, irradiance_w_m2=800,
        air_temperature_c=None if missing == 'all' or missing == 'temperature' and index == 12 else float(index),
        weather_code=None if missing == 'all' or missing == 'code' and index == 12 else 0)
        for index in range(24) if missing != 'sample' or index != 12)
    batch = ForecastBatch(inputs=inputs, fetched_at=120, intervals=constant_intervals(0, 7*86400), weather_samples=samples)
    view = forecast_view(batch, inputs.location, 180)
    assert view.status == 'ready'
    assert view.today.forecast_energy_kwh == pytest.approx(89.28)
    assert view.days[0].weather.model_dump() == dict(weather_code=code, air_temperature_min_c=minimum,
        air_temperature_max_c=maximum, quality=quality)
    assert view.days[1].weather is None


@pytest.mark.parametrize('value', [3, 90])
def test_pr_history_days_roundtrip(value):
    assert ForecastSettings.model_validate_json(ForecastSettings(pr_history_days=value).model_dump_json()).pr_history_days == value
    assert ForecastSettings.model_validate_json('{}').pr_history_days == 14


@pytest.mark.parametrize('value', [2, 91, 3.5, True])
def test_pr_history_days_rejects_noninteger_or_outside_bounds(value):
    with pytest.raises(ValidationError):
        ForecastSettings(pr_history_days=value)


@pytest.mark.parametrize('pr', [0, 80, 110, None])
def test_correction_scales_raw_quarter_hours_and_clipped_totals_once(pr):
    from pvyieldlens.correction import ForecastCorrection

    inputs = forecast_input(home_timezone='Asia/Kathmandu')
    batch = ForecastBatch(inputs=inputs, fetched_at=10, angles_read_at=5,
        intervals=constant_intervals(-86400 + 300, 8 * 86400, interval_seconds=900),
        weather_samples=tuple(WeatherSample(at=at, irradiance_w_m2=800, air_temperature_c=20, weather_code=0)
                              for at in range(-5 * 3600, 19 * 3600, 3600)))
    correction = ForecastCorrection(pr=pr, history_days=14, start=-14 * 86400, end=0)
    view = forecast_view(batch, inputs.location, 123,
                         correction=correction, refreshing=True)
    compact = forecast_view(batch, inputs.location, 123, correction=correction, refreshing=True, include_details=False)
    assert compact.days == compact.intervals == ()
    assert compact.model_dump(exclude={'days', 'intervals'}) == view.model_dump(exclude={'days', 'intervals'})
    assert view.days[0].weather.quality == 'complete'
    assert view.correction == correction
    for row in view.intervals:
        assert row.corrected_forecast_power_w == (pytest.approx(row.forecast_power_w * pr / 100) if pr is not None else None)
        assert row.corrected_forecast_energy_kwh == (pytest.approx(row.forecast_energy_kwh * pr / 100) if pr is not None else None)
    for total in (view.today, view.remaining_today, view.tomorrow, view.seven_days, *view.days):
        assert total.corrected_forecast_energy_kwh == (pytest.approx(total.forecast_energy_kwh * pr / 100) if pr is not None else None)
    assert batch.intervals[0].forecast_power_w == 3720
    assert 'correction' not in batch.model_dump()


def test_correction_preserves_missing_forecast_even_with_zero_factor():
    from pvyieldlens.correction import ForecastCorrection

    inputs = forecast_input()
    rows = constant_intervals(0, 8 * 86400, interval_seconds=900)
    missing = rows[0].model_copy(update={'forecast_power_w': None, 'forecast_energy_kwh': None, 'quality': 'unavailable'})
    batch = ForecastBatch(inputs=inputs, fetched_at=10, intervals=(missing, *rows[1:]), weather_samples=())
    correction = ForecastCorrection(pr=0, history_days=14, start=-14 * 86400, end=0)
    view = forecast_view(batch, inputs.location, 120, correction=correction)
    compact = forecast_view(batch, inputs.location, 120, correction=correction, include_details=False)
    assert compact.days == compact.intervals == ()
    assert compact.model_dump(exclude={'days', 'intervals'}) == view.model_dump(exclude={'days', 'intervals'})
    assert view.intervals[0].corrected_forecast_power_w is None
    assert view.intervals[0].corrected_forecast_energy_kwh is None
    assert view.today.corrected_forecast_energy_kwh is None
    assert view.tomorrow.corrected_forecast_energy_kwh == 0
