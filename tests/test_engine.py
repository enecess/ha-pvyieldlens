import pytest
from pydantic import ValidationError

from pvyieldlens.settings import Settings
from pvyieldlens.engine import Observation, calculate, estimated_power


def settings(**changes):
    return Settings.model_validate({
        'rated_power_w': 5000, 'temperature_coefficient_pct_per_c': -0.35,
        'power_entity': 'sensor.power', 'temperature_entity': 'sensor.temp',
        'irradiance_entity': 'sensor.sun', 'power_max_age_seconds': 900,
        'irradiance_max_age_seconds': 900, **changes,
    })


def samples(power=3348, temp=45, sun=800, at=0):
    return [Observation('sensor.power', at, power), Observation('sensor.temp', at, temp),
            Observation('sensor.sun', at, sun)]


def test_datasheet_percent_and_roundtrip():
    config = Settings.model_validate_json(settings().model_dump_json())
    result = calculate(config, samples(), 0, 60)
    assert config.temperature_coefficient_pct_per_c == -0.35
    assert result.estimated_power == pytest.approx(3720)
    assert result.pr == pytest.approx(90)
    assert result.optimizable_power == pytest.approx(372)
    assert result.estimated_energy_wh == pytest.approx(62)


def test_weights_duration_not_record_count():
    result = calculate(settings(), samples(power=1000) + [Observation('sensor.power', 540, 0)], 0, 600)
    assert result.actual_power == pytest.approx(900)
    assert result.actual_energy_wh == pytest.approx(150)


def test_calculates_before_averaging_inputs():
    observations = samples(power=1000, temp=25, sun=1000) + [
        Observation('sensor.temp', 30, 65), Observation('sensor.sun', 30, 500)]
    result = calculate(settings(), observations, 0, 60)
    assert result.estimated_power == pytest.approx(3575)


def test_partial_coverage_is_not_zero_filled():
    result = calculate(settings(power_max_age_seconds=30), samples(), 0, 60)
    assert result.coverage_percent == 50
    assert result.estimated_power == pytest.approx(3720)
    assert result.estimated_energy_wh == pytest.approx(31)
    assert result.quality == 'partial'


def test_repeated_report_does_not_fill_expired_gap():
    observations = samples() + [Observation('sensor.power', 40, 3348)]
    result = calculate(settings(power_max_age_seconds=30), observations, 0, 60)
    assert result.valid_seconds == 50


def test_invalid_event_ends_hold_and_no_future_data_used():
    observations = samples() + [Observation('sensor.sun', 20, None), Observation('sensor.sun', 70, 800)]
    assert calculate(settings(), observations, 0, 60).valid_seconds == 20


def test_zero_denominator_and_negative_opportunity():
    night = calculate(settings(), samples(power=0, sun=0), 0, 60)
    assert night.estimated_power == 0
    assert night.pr is None
    assert night.reason == 'zero_expected_power'
    bright = calculate(settings(), samples(power=4000), 0, 60)
    assert bright.pr > 100
    assert bright.optimizable_power == pytest.approx(-280)


@pytest.mark.parametrize('changes', [
    {'rated_power_w': float('nan')}, {'rated_power_w': True},
    {'interval_minutes': 3}, {'realtime_window_seconds': 10, 'update_seconds': 20},
    {'power_entity': 'sensor.pvyieldlens_pr'}, {'power_entity': 'light.power'},
])
def test_rejects_invalid_configuration(changes):
    with pytest.raises(ValidationError):
        settings(**changes)


@pytest.mark.parametrize('temperature,irradiance,expected', [
    (45, 800, 3720), (25, 0, 0), (-10, 1200, 6735), (400, 800, None),
])
def test_shared_power_preserves_zero_gain_and_invalid_factor(temperature, irradiance, expected):
    assert estimated_power(5000, -0.0035, temperature, irradiance) == pytest.approx(expected)


def test_negative_temperature_factor_does_not_become_a_valid_monitoring_segment():
    result = calculate(settings(), samples(temp=400), 0, 60)
    assert result.valid_seconds == 0
    assert result.estimated_power is None
    assert result.quality == 'unavailable'


@pytest.mark.parametrize('started_at,at,quality', [(590, 600, 'warming_up'), (1200, 600, 'partial'),
                                                 (540, 600, 'partial'), (None, 600, 'partial')])
def test_realtime_warming_up_only_applies_inside_current_startup_window(started_at, at, quality):
    from pvyieldlens import engine

    result = engine.calculate_realtime(settings(power_max_age_seconds=30),
                                       samples(at=550) + samples(at=590), at, started_at=started_at)
    assert result.quality == quality
    assert result.valid_seconds == 40
    assert result.pr == pytest.approx(90)


@pytest.mark.parametrize('observations', [samples(), samples(at=590) + [Observation('sensor.sun', 600, None)]])
def test_realtime_invalidates_current_sources_without_erasing_valid_average(observations):
    from pvyieldlens import engine

    result = engine.calculate_realtime(settings(power_max_age_seconds=30), observations, 600)
    assert result.estimated_power is None
    assert result.actual_power is None
    assert result.pr is None
    assert result.optimizable_power is None
    assert result.quality == 'unavailable'
    assert result.reason == 'current_source_unavailable'


def test_realtime_valid_zero_irradiance_is_available():
    from pvyieldlens import engine

    result = engine.calculate_realtime(settings(), samples(power=0, sun=0), 60)
    assert result.estimated_power == result.actual_power == 0
    assert result.pr is None
    assert result.reason == 'zero_expected_power'
    assert result.quality == 'complete'


def test_realtime_does_not_use_an_observation_after_the_requested_endpoint():
    from pvyieldlens import engine

    result = engine.calculate_realtime(settings(), samples(power=None) + samples(at=600.00005), 600)
    assert result.estimated_power is None
    assert result.quality == 'unavailable'
    assert result.reason == 'current_source_unavailable'


@pytest.mark.parametrize('changes,observations,endpoints,started_at', [
    ({}, samples() + samples(at=7.25, power=1100, sun=500)
     + [Observation('sensor.sun', 25, None)] + samples(at=47.75), [10, 30, 60, 90], None),
    ({'power_max_age_seconds': 30}, samples() + samples(at=40), [20, 30, 35, 60, 70, 75], None),
    ({}, [], [0, 30, 60], None),
    ({}, samples(power=0, sun=0), [0, 5, 60, 90], 0),
    ({}, samples() + samples(at=10, temp=400) + samples(at=50), [5, 20, 50, 60, 90], None),
    ({'power_max_age_seconds': 30}, samples(at=550) + samples(at=590),
     [550, 590, 600, 649, 650, 660], 590),
    ({}, samples(power=None) + samples(at=600.00005), [600, 600.00005, 600.0001, 600.0002], None),
    ({'power_max_age_seconds': 1}, samples(at=600.00003),
     [600.00001, 600.00003, 601.00001, 601.00003, 601.00005], None),
    ({}, samples() + samples(at=60, power=0, sun=0), [60, 90, 120, 150], None),
])
def test_realtime_series_preserves_scalar_windows(changes, observations, endpoints, started_at):
    from pvyieldlens import engine

    config = settings(**changes)
    results = engine.calculate_realtime_series(config, observations, endpoints, started_at=started_at)
    assert len(results) == len(endpoints)
    for at, result in zip(endpoints, results):
        expected = engine.calculate_realtime(config, observations, at, started_at=started_at)
        assert result.quality == expected.quality
        assert result.reason == expected.reason
        for field in ('start', 'end', 'valid_seconds', 'estimated_energy_wh', 'actual_energy_wh',
                      'estimated_power', 'actual_power', 'pr', 'optimizable_power', 'coverage_percent'):
            assert getattr(result, field) == pytest.approx(getattr(expected, field), abs=1e-8)
        assert result.segments == expected.segments


def test_realtime_series_empty_endpoints_produce_no_windows():
    from pvyieldlens import engine

    assert engine.calculate_realtime_series(settings(), samples(), []) == []
