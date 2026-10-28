import pytest
from pydantic import ValidationError

from pvyieldlens.settings import Settings
from pvyieldlens.engine import Observation, calculate


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
