import sqlite3

import pytest

from pvyieldlens.engine import Observation, calculate
from pvyieldlens.generation import generation_view
from pvyieldlens.settings import AmbientSite
from pvyieldlens.storage import Store
from test_engine import samples, settings
from test_history import settle_cross_midnight, timestamp


@pytest.fixture
def store(tmp_path):
    instance = Store(tmp_path / 'data.sqlite')
    yield instance
    instance.close()


def commit_windows(store, config, observations, boundaries, origin=''):
    revision = store.save_monitoring_settings(config, boundaries[0], origin)
    store.add_observations(observations, origin)
    for start, end in zip(boundaries, boundaries[1:]):
        store.settle(calculate(config, observations, start, end), revision, config.home_timezone)


def test_input_averages_survive_missing_actual_power(store):
    observations = samples(power=None, temp=20, sun=100) + [
        Observation('sensor.temp', 30, 30), Observation('sensor.sun', 30, 300)]
    commit_windows(store, settings(), observations, [0, 60])

    view = generation_view(store, now=60, home_timezone='UTC')

    assert view.windows[0]['actual_power_w'] is None
    assert view.inputs[0].module_temperature_c == pytest.approx(25)
    assert view.inputs[0].irradiance_w_m2 == pytest.approx(200)
    assert view.requested_range.model_dump() == {'start': 0, 'end': 60}


def test_estimated_temperature_uses_joint_coverage_without_actual_power(store):
    site = AmbientSite(latitude=31.2, longitude=121.5)
    config = settings(module_temperature_entity=None, ambient_site=site)
    observations = [Observation(site.observation_entity_id, 0, 20),
                    Observation(site.observation_entity_id, 900, None), Observation('sensor.sun', 890, 800)]
    commit_windows(store, config, observations, [880, 920])

    view = generation_view(store, now=920, home_timezone='UTC')

    assert view.windows[0]['actual_power_w'] is None
    assert view.inputs[0].module_temperature_c == pytest.approx(45)
    assert view.inputs[0].irradiance_w_m2 == pytest.approx(800)


def test_estimated_temperature_weights_unequal_known_durations(store):
    site = AmbientSite(latitude=31.2, longitude=121.5)
    config = settings(module_temperature_entity=None, ambient_site=site)
    observations = [Observation(site.observation_entity_id, 0, 10),
                    Observation(site.observation_entity_id, 45, 30), Observation('sensor.sun', 0, 800)]
    commit_windows(store, config, observations, [0, 60])

    point = generation_view(store, now=60, home_timezone='UTC').inputs[0]

    assert point.module_temperature_c == pytest.approx(40)


def test_configured_unavailable_temperature_does_not_use_cached_ambient(store):
    site = AmbientSite(latitude=31.2, longitude=121.5)
    observations = samples(temp=None) + [Observation(site.observation_entity_id, 0, 20)]
    commit_windows(store, settings(ambient_site=site), observations, [0, 60])

    view = generation_view(store, now=60, home_timezone='UTC')

    assert view.windows[0]['estimated_power_w'] is None
    assert view.inputs[0].irradiance_w_m2 == pytest.approx(800)
    assert view.inputs[0].module_temperature_c is None


def test_independent_input_average_weights_unequal_durations_in_a_startup_window(store):
    observations = samples(power=None, at=20, temp=20, sun=100) + [Observation('sensor.temp', 30, 40)]
    commit_windows(store, settings(settlement_interval_minutes=1), observations, [20, 60])

    view = generation_view(store, now=60, home_timezone='UTC')

    assert len(view.windows) == len(view.inputs) == 1
    assert view.windows[0]['actual_power_w'] is None
    assert (view.inputs[0].start, view.inputs[0].end) == (20, 60)
    assert view.inputs[0].module_temperature_c == 35


def test_source_timeout_does_not_zero_fill_other_inputs(store):
    observations = samples(temp=20, sun=100) + [Observation('sensor.temp', 90, 40)]
    commit_windows(store, settings(irradiance_max_age_seconds=30), observations, [0, 60, 120])

    view = generation_view(store, now=150, home_timezone='UTC')

    assert view.inputs[0].irradiance_w_m2 == pytest.approx(100)
    expired_point = view.inputs[1]
    assert expired_point.irradiance_w_m2 is None
    assert expired_point.module_temperature_c == pytest.approx(30)
    assert view.windows[1]['actual_power_w'] is None
    assert view.requested_range.end == 120


def test_true_zero_inputs_remain_zero_without_actual_power(store):
    commit_windows(store, settings(), samples(power=None, temp=0, sun=0), [0, 60])

    point = generation_view(store, now=60, home_timezone='UTC').inputs[0]

    assert point.module_temperature_c == 0
    assert point.irradiance_w_m2 == 0


def test_partial_inputs_average_only_their_own_known_portions(store):
    observations = [Observation('sensor.temp', 0, 20), Observation('sensor.temp', 10, None),
                    Observation('sensor.temp', 50, 40), Observation('sensor.sun', 20, 100),
                    Observation('sensor.sun', 40, None), Observation('sensor.sun', 60, 900)]
    commit_windows(store, settings(), observations, [0, 60])

    point = generation_view(store, now=60, home_timezone='UTC').inputs[0]

    assert point.module_temperature_c == pytest.approx(30)
    assert point.irradiance_w_m2 == pytest.approx(100)


@pytest.mark.parametrize('sun_at,expected_sun', [(-20, 100), (-30, None)])
def test_predecessors_are_held_only_until_each_source_timeout(store, sun_at, expected_sun):
    observations = [Observation('sensor.temp', -20, 10), Observation('sensor.sun', sun_at, 100)]
    commit_windows(store, settings(module_temperature_max_age_seconds=60,
                                   irradiance_max_age_seconds=30), observations, [0, 60, 120])

    view = generation_view(store, now=120, home_timezone='UTC')

    assert view.inputs[0].module_temperature_c == pytest.approx(10)
    assert view.inputs[0].irradiance_w_m2 == expected_sun
    assert view.inputs[1].module_temperature_c is None
    assert view.inputs[1].irradiance_w_m2 is None


def test_each_revision_uses_its_original_entities_origin_and_timeouts(store):
    first = settings(module_temperature_max_age_seconds=60, irradiance_max_age_seconds=60)
    second = settings(module_temperature_entity='sensor.temp_new', irradiance_entity='sensor.sun_new',
                      module_temperature_max_age_seconds=30, irradiance_max_age_seconds=30)
    third = settings(module_temperature_entity='sensor.temp_new', irradiance_entity='sensor.sun_new',
                     module_temperature_max_age_seconds=120, irradiance_max_age_seconds=120)
    commit_windows(store, first, samples(temp=10, sun=100), [0, 60], 'old-origin')
    commit_windows(store, second, [Observation('sensor.temp_new', 60, 20),
                                  Observation('sensor.sun_new', 60, 200)], [60, 120], 'old-origin')
    commit_windows(store, third, [Observation('sensor.temp_new', 120, 30),
                                 Observation('sensor.sun_new', 120, 300)], [120, 180, 240], 'new-origin')
    store.add_observations(samples(at=60, temp=90, sun=900), 'old-origin')
    store.add_observations([Observation('sensor.temp_new', 120, 80),
                            Observation('sensor.sun_new', 120, 800)], 'old-origin')
    store.add_observations([Observation('sensor.temp_new', 60, 70),
                            Observation('sensor.sun_new', 60, 700)], 'new-origin')

    view = generation_view(store, now=240, home_timezone='UTC')

    assert [point.module_temperature_c for point in view.inputs] == pytest.approx([10, 20, 30, 30])
    assert [point.irradiance_w_m2 for point in view.inputs] == pytest.approx([100, 200, 300, 300])
    assert [window['revision'] for window in view.windows] == [1, 2, 3, 3]


def test_input_boundaries_follow_changed_settlement_intervals(store):
    commit_windows(store, settings(settlement_interval_minutes=1), samples(temp=10, sun=100), [0, 60])
    commit_windows(store, settings(settlement_interval_minutes=5), samples(at=60, temp=20, sun=200), [60, 300])
    commit_windows(store, settings(settlement_interval_minutes=10), samples(at=300, temp=30, sun=300), [300, 600])

    view = generation_view(store, now=620, home_timezone='UTC')

    assert [(point.start, point.end) for point in view.inputs] == [(0, 60), (60, 300), (300, 600)]
    assert [(window['start'], window['end']) for window in view.windows] == [(0, 60), (60, 300), (300, 600)]
    assert [point.irradiance_w_m2 for point in view.inputs] == pytest.approx([100, 200, 300])
    assert view.requested_range.end == 600


def test_midnight_fragment_uses_exact_calendar_and_original_revision(store):
    start, midnight, end = settle_cross_midnight(store)
    store.save_monitoring_settings(settings(module_temperature_entity='sensor.other_temp',
                                            irradiance_entity='sensor.other_sun'), end, 'new-origin')
    store.add_observations([Observation('sensor.temp', start, 5), Observation('sensor.temp', midnight, 35)])

    view = generation_view(store, now=end + 30, home_timezone='Asia/Shanghai')

    assert len(view.windows) == len(view.inputs) == 1
    window, point = view.windows[0], view.inputs[0]
    assert (window['source_start'], window['source_end']) == (start, end)
    assert (point.start, point.end) == (midnight, end)
    assert point.irradiance_w_m2 == pytest.approx(2000)
    assert point.module_temperature_c == pytest.approx(35)
    assert window['actual_power_w'] == pytest.approx(1200)
    assert view.requested_range.model_dump() == {'start': midnight, 'end': end}


def test_estimated_spans_are_clipped_to_the_midnight_fragment_and_next_window(store):
    midnight = timestamp('2026-11-11T00:00:00')
    start, end = midnight - 120, midnight + 180
    site = AmbientSite(latitude=31.2, longitude=121.5)
    config = settings(module_temperature_entity=None, ambient_site=site, home_timezone='Asia/Shanghai')
    observations = samples(at=start) + [Observation(site.observation_entity_id, start, 10),
                                       Observation(site.observation_entity_id, midnight + 45, 30)]
    commit_windows(store, config, observations, [start, end, end + 60])

    view = generation_view(store, now=end + 60, home_timezone=config.home_timezone)

    assert [(point.start, point.end) for point in view.inputs] == [(midnight, end), (end, end + 60)]
    assert [point.module_temperature_c for point in view.inputs] == pytest.approx([50, 55])
    assert [point.irradiance_w_m2 for point in view.inputs] == pytest.approx([800, 800])


def test_unallocated_midnight_boundary_window_is_excluded(store):
    _, midnight, end = settle_cross_midnight(store, home_timezone='Asia/Taipei')

    view = generation_view(store, now=end, home_timezone='Asia/Shanghai')

    assert view.windows == []
    assert view.inputs == []
    assert view.requested_range.model_dump() == {'start': midnight, 'end': end}


def test_unconfigured_store_returns_household_today_to_now(store):
    now = timestamp('2026-11-17T12:07:00')

    view = generation_view(store, now=now, home_timezone='Asia/Shanghai')

    assert view.windows == []
    assert view.inputs == []
    assert view.home_timezone == 'Asia/Shanghai'
    assert view.requested_range.model_dump() == {'start': timestamp('2026-11-17T00:00:00'), 'end': now}


def test_generation_is_read_only_and_reads_observations_once_per_revision(store):
    commit_windows(store, settings(), samples(), [0, 60, 120, 180])
    tables = ('metadata', 'configs', 'observations', 'windows', 'window_segments', 'days')
    before = {table: [tuple(row) for row in store.db.execute(f'SELECT * FROM {table}')] for table in tables}
    changes = store.db.total_changes
    statements = []
    store.db.set_trace_callback(statements.append)
    store.db.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY
                            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)
                            else sqlite3.SQLITE_OK)

    view = generation_view(store, now=200, home_timezone='UTC')

    store.db.set_trace_callback(None)
    assert len(view.inputs) == 3
    assert sum('WITH sources' in statement for statement in statements) == 1
    assert store.db.total_changes == changes
    assert {table: [tuple(row) for row in store.db.execute(f'SELECT * FROM {table}')] for table in tables} == before
