import pytest
from pydantic import ValidationError

from pvyieldlens import engine
from pvyieldlens.settings import AmbientSite, MonitoringSettings
from pvyieldlens.engine import Observation, calculate, estimated_power


def settings(**changes):
    return MonitoringSettings.model_validate({
        'total_max_power_at_stc_w': 5000, 'pmax_temperature_coefficient_pct_per_c': -0.35,
        'actual_power_entity': 'sensor.power', 'module_temperature_entity': 'sensor.temp',
        'irradiance_entity': 'sensor.sun', 'actual_power_max_age_seconds': 900,
        'irradiance_max_age_seconds': 900, **changes,
    })


def samples(power=3348, temp=45, sun=800, at=0):
    return [Observation('sensor.power', at, power), Observation('sensor.temp', at, temp),
            Observation('sensor.sun', at, sun)]


def test_datasheet_percent_and_roundtrip():
    config = MonitoringSettings.model_validate_json(settings().model_dump_json())
    result = calculate(config, samples(), 0, 60)
    assert config.pmax_temperature_coefficient_pct_per_c == -0.35
    assert result.estimated_power_w == pytest.approx(3720)
    assert result.actual_power_w == pytest.approx(3348)
    assert set(result.public()) == {'start', 'end', 'valid_seconds', 'estimated_energy_wh', 'actual_energy_wh', 'estimated_power_w', 'actual_power_w', 'pr', 'optimizable_power_w', 'data_completeness_percent', 'quality', 'reason'}
    assert result.pr == pytest.approx(90)
    assert result.optimizable_power_w == pytest.approx(372)
    assert result.estimated_energy_wh == pytest.approx(62)


def test_optional_temperature_source_preserves_ha_roles():
    assert settings().ha_sources == (
        ('power', 'sensor.power', 900), ('temperature', 'sensor.temp', 900), ('irradiance', 'sensor.sun', 900),
    )

    config = settings(module_temperature_entity=None)
    assert config.module_temperature_noct_c == 45.0
    assert config.ambient_site is None
    assert config.ha_sources == (('power', 'sensor.power', 900), ('irradiance', 'sensor.sun', 900))
    assert config.entities == ('sensor.power', 'sensor.sun')
    assert config.max_ages == (900, 900)
    raw = config.model_dump(exclude={'module_temperature_entity'})
    assert MonitoringSettings.model_validate(raw) == config


@pytest.mark.parametrize('changes', [
    {'module_temperature_entity': ''},
    {'module_temperature_entity': None, 'irradiance_entity': 'sensor.power'},
    {'module_temperature_entity': 'sensor.sun'},
    {'module_temperature_entity': 'sensor.pvyieldlens_live_pr'},
    {'module_temperature_entity': None, 'irradiance_entity': 'sensor.pvyieldlens_live_pr'},
])
def test_rejects_invalid_configured_sources_with_optional_temperature(changes):
    with pytest.raises(ValidationError):
        settings(**changes)


def test_monitoring_without_measured_temperature_is_unavailable():
    from pvyieldlens.engine import calculate_live, calculate_live_series

    config = settings(module_temperature_entity=None)
    result = calculate(config, samples(), 0, 60)
    assert result.quality == 'unavailable'
    assert result.estimated_power_w is None
    assert result.valid_seconds == 0
    live = calculate_live(config, samples(), 60)
    assert live.reason == 'current_source_unavailable'
    assert calculate_live_series(config, samples(), [60]) == [live]


@pytest.mark.parametrize('irradiance,temperature,power', [(800, 45, 3720), (0, 20, 0)])
def test_noct_temperature_drives_live_and_settled_power(irradiance, temperature, power):
    site = AmbientSite(latitude=31.2, longitude=121.5)
    config = settings(module_temperature_entity=None, module_temperature_noct_c=45, ambient_site=site)
    observations = samples(sun=irradiance) + [Observation(site.observation_entity_id, 0, 20)]

    settled = calculate(config, observations, 0, 60)
    live = engine.calculate_live(config, observations, 60)
    [series] = engine.calculate_live_series(config, observations, [60])

    for result in (settled, live, series):
        assert result.estimated_power_w == pytest.approx(power)
        assert result.valid_seconds == 60
    assert engine.noct_temperature(20, irradiance, 45) == temperature


@pytest.mark.parametrize('next_sample', [[], [Observation('weather:ambient:31.2:121.5', 900, None)]])
def test_ambient_sample_expires_at_fifteen_minutes(next_sample):
    site = AmbientSite(latitude=31.2, longitude=121.5)
    config = settings(module_temperature_entity=None, module_temperature_max_age_seconds=30, ambient_site=site)
    observations = samples(at=860) + [Observation(site.observation_entity_id, 0, 20)] + next_sample

    assert calculate(config, observations, 880, 920).valid_seconds == 20
    endpoints = [899, 900, 910]
    results = engine.calculate_live_series(config, observations, endpoints)
    assert [result.estimated_power_w for result in results] == [pytest.approx(3720), None, None]
    for at in endpoints[1:]:
        assert engine.calculate_live(config, observations, at).reason == 'current_source_unavailable'


def test_weights_duration_not_record_count():
    result = calculate(settings(), samples(power=1000) + [Observation('sensor.power', 540, 0)], 0, 600)
    assert result.actual_power_w == pytest.approx(900)
    assert result.actual_energy_wh == pytest.approx(150)


def test_calculates_before_averaging_inputs():
    observations = samples(power=1000, temp=25, sun=1000) + [
        Observation('sensor.temp', 30, 65), Observation('sensor.sun', 30, 500)]
    result = calculate(settings(), observations, 0, 60)
    assert result.estimated_power_w == pytest.approx(3575)


def test_partial_coverage_is_not_zero_filled():
    result = calculate(settings(actual_power_max_age_seconds=30), samples(), 0, 60)
    assert result.data_completeness_percent == 50
    assert result.estimated_power_w == pytest.approx(3720)
    assert result.estimated_energy_wh == pytest.approx(31)
    assert result.quality == 'partial'


def test_repeated_report_does_not_fill_expired_gap():
    observations = samples() + [Observation('sensor.power', 40, 3348)]
    result = calculate(settings(actual_power_max_age_seconds=30), observations, 0, 60)
    assert result.valid_seconds == 50


def test_invalid_event_ends_hold_and_no_future_data_used():
    observations = samples() + [Observation('sensor.sun', 20, None), Observation('sensor.sun', 70, 800)]
    assert calculate(settings(), observations, 0, 60).valid_seconds == 20


def test_zero_denominator_and_negative_optimizable_power():
    night = calculate(settings(), samples(power=0, sun=0), 0, 60)
    assert night.estimated_power_w == 0
    assert night.pr is None
    assert night.reason == 'zero_estimated_power'
    bright = calculate(settings(), samples(power=4000), 0, 60)
    assert bright.pr > 100
    assert bright.optimizable_power_w == pytest.approx(-280)


@pytest.mark.parametrize('changes', [
    {'total_max_power_at_stc_w': float('nan')}, {'total_max_power_at_stc_w': True},
    {'settlement_interval_minutes': 3}, {'live_window_seconds': 10, 'update_interval_seconds': 20},
    {'actual_power_entity': 'sensor.pvyieldlens_settled_pr'}, {'actual_power_entity': 'light.power'},
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
    assert result.estimated_power_w is None
    assert result.quality == 'unavailable'


@pytest.mark.parametrize('started_at,at,quality', [(590, 600, 'warming_up'), (1200, 600, 'partial'),
                                                 (540, 600, 'partial'), (None, 600, 'partial')])
def test_live_warming_up_only_applies_inside_current_startup_window(started_at, at, quality):
    from pvyieldlens import engine

    result = engine.calculate_live(settings(actual_power_max_age_seconds=30),
                                       samples(at=550) + samples(at=590), at, started_at=started_at)
    assert result.quality == quality
    assert result.valid_seconds == 40
    assert result.pr == pytest.approx(90)


@pytest.mark.parametrize('observations', [samples(), samples(at=590) + [Observation('sensor.sun', 600, None)]])
def test_live_invalidates_current_sources_without_erasing_valid_average(observations):
    from pvyieldlens import engine

    result = engine.calculate_live(settings(actual_power_max_age_seconds=30), observations, 600)
    assert result.estimated_power_w is None
    assert result.actual_power_w is None
    assert result.pr is None
    assert result.optimizable_power_w is None
    assert result.quality == 'unavailable'
    assert result.reason == 'current_source_unavailable'


def test_live_valid_zero_irradiance_is_available():
    from pvyieldlens import engine

    result = engine.calculate_live(settings(), samples(power=0, sun=0), 60)
    assert result.estimated_power_w == result.actual_power_w == 0
    assert result.pr is None
    assert result.reason == 'zero_estimated_power'
    assert result.quality == 'complete'


def test_live_does_not_use_an_observation_after_the_requested_endpoint():
    from pvyieldlens import engine

    result = engine.calculate_live(settings(), samples(power=None) + samples(at=600.00005), 600)
    assert result.estimated_power_w is None
    assert result.quality == 'unavailable'
    assert result.reason == 'current_source_unavailable'


@pytest.mark.parametrize('changes,observations,endpoints,started_at', [
    ({}, samples() + samples(at=7.25, power=1100, sun=500)
     + [Observation('sensor.sun', 25, None)] + samples(at=47.75), [10, 30, 60, 90], None),
    ({'actual_power_max_age_seconds': 30}, samples() + samples(at=40), [20, 30, 35, 60, 70, 75], None),
    ({}, [], [0, 30, 60], None),
    ({}, samples(power=0, sun=0), [0, 5, 60, 90], 0),
    ({}, samples() + samples(at=10, temp=400) + samples(at=50), [5, 20, 50, 60, 90], None),
    ({'actual_power_max_age_seconds': 30}, samples(at=550) + samples(at=590),
     [550, 590, 600, 649, 650, 660], 590),
    ({}, samples(power=None) + samples(at=600.00005), [600, 600.00005, 600.0001, 600.0002], None),
    ({'actual_power_max_age_seconds': 1}, samples(at=600.00003),
     [600.00001, 600.00003, 601.00001, 601.00003, 601.00005], None),
    ({}, samples() + samples(at=60, power=0, sun=0), [60, 90, 120, 150], None),
])
def test_live_series_preserves_scalar_windows(changes, observations, endpoints, started_at):
    from pvyieldlens import engine

    config = settings(**changes)
    results = engine.calculate_live_series(config, observations, endpoints, started_at=started_at)
    assert len(results) == len(endpoints)
    for at, result in zip(endpoints, results):
        expected = engine.calculate_live(config, observations, at, started_at=started_at)
        assert result.quality == expected.quality
        assert result.reason == expected.reason
        for field in ('start', 'end', 'valid_seconds', 'estimated_energy_wh', 'actual_energy_wh',
                      'estimated_power_w', 'actual_power_w', 'pr', 'optimizable_power_w', 'data_completeness_percent'):
            assert getattr(result, field) == pytest.approx(getattr(expected, field), abs=1e-8)
        assert result.segments == expected.segments


def test_live_series_empty_endpoints_produce_no_windows():
    from pvyieldlens import engine

    assert engine.calculate_live_series(settings(), samples(), []) == []
