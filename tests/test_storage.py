from datetime import datetime, timezone

import pytest

from pvyieldlens.engine import calculate
from pvyieldlens.storage import Store
from test_engine import samples, settings


def test_restart_and_duplicate_settlement_are_idempotent(tmp_path):
    path = tmp_path / 'data.sqlite'
    store = Store(path)
    revision = store.save_monitoring_settings(settings(), 0)
    result = calculate(settings(), samples(), 0, 60)
    store.settle(result, revision, 'UTC')
    store.settle(result, revision, 'UTC')
    store.close()
    restored = Store(path)
    assert restored.totals(60, 'UTC')['estimated_energy_lifetime_kwh'] == pytest.approx(0.062)
    assert restored.cursor == 60
    assert restored.monitoring_settings().pmax_temperature_coefficient_pct_per_c == -0.35
    assert set(restored.db.execute('SELECT * FROM configs').fetchone().keys()) == {
        'revision', 'effective_at', 'monitoring_settings', 'origin'}
    assert set(restored.db.execute('SELECT * FROM days').fetchone().keys()) == {
        'home_timezone', 'day', 'estimated_energy_wh', 'valid_seconds', 'allocation_complete'}
    assert {row['key'] for row in restored.db.execute('SELECT key FROM metadata')} == {
        'estimated_energy_lifetime_wh', 'lifetime_valid_seconds', 'cursor', 'latest_settled_window'}
    assert restored.latest_settled_window()['estimated_power_w'] == pytest.approx(3720)
    restored.close()


def test_midnight_splits_energy_and_empty_new_day_is_zero(tmp_path):
    start = datetime(2026, 10, 28, 15, 59, 30, tzinfo=timezone.utc).timestamp()
    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_monitoring_settings(settings(), start)
    store.settle(calculate(settings(), samples(at=start), start, start + 60), revision, 'Asia/Shanghai')
    assert store.totals(start, 'Asia/Shanghai')['estimated_energy_today_kwh'] == pytest.approx(0.031)
    assert store.totals(start + 60, 'Asia/Shanghai')['estimated_energy_today_kwh'] == pytest.approx(0.031)
    assert store.totals(start + 86460, 'Asia/Shanghai')['estimated_energy_today_kwh'] == 0
    store.close()


def test_observations_deduplicate_and_keep_predecessor(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    store.add_observations(samples())
    store.add_observations(samples())
    assert len(store.observations(30, 60, settings().entities)) == 3
    store.close()


def test_observation_sources_origin_and_inclusive_bounds_keep_strict_predecessors(tmp_path):
    from pvyieldlens.engine import Observation

    store = Store(tmp_path / 'data.sqlite')
    store.add_observations(samples(at=5) + samples(at=10) + samples(at=20) + samples(at=30)
                           + [Observation('sensor.retired', 15, 999), Observation('sensor.retired', 0, 999)], 'old')
    store.add_observations(samples(at=10, sun=100), 'new')
    store.add_observations([Observation('sensor.sun', 20, None)], 'old')
    records = store.observations(10, 20, settings().entities, 'old')
    assert [(item.at, item.entity_id, item.value) for item in records] == [
        (5, 'sensor.power', 3348), (5, 'sensor.sun', 800), (5, 'sensor.temp', 45),
        (10, 'sensor.power', 3348), (10, 'sensor.sun', 800), (10, 'sensor.temp', 45),
        (20, 'sensor.power', 3348), (20, 'sensor.sun', None), (20, 'sensor.temp', 45),
    ]
    assert [(item.entity_id, item.value) for item in store.observations(10, 10, settings().entities, 'new')] == [
        ('sensor.power', 3348), ('sensor.sun', 100), ('sensor.temp', 45),
    ]
    assert store.observations(0, 4, settings().entities, 'old') == []
    store.close()


def test_observations_with_two_sources_keep_only_their_strict_predecessors(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    store.add_observations(samples(at=1) + samples(at=5) + samples(at=10) + samples(at=20) + samples(at=30), 'active')
    store.add_observations(samples(at=8), 'other')
    records = store.observations(10, 20, ('sensor.power', 'sensor.sun'), 'active')
    assert [(item.at, item.entity_id) for item in records] == [
        (5, 'sensor.power'), (5, 'sensor.sun'),
        (10, 'sensor.power'), (10, 'sensor.sun'),
        (20, 'sensor.power'), (20, 'sensor.sun'),
    ]
    store.close()


def test_retention_keeps_totals_and_latest_settled_window(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_monitoring_settings(settings(), 0)
    store.settle(calculate(settings(), samples(), 0, 60), revision, 'UTC')
    store.prune(100 * 86400)
    assert store.totals(100 * 86400, 'UTC')['estimated_energy_lifetime_kwh'] == pytest.approx(0.062)
    assert store.latest_settled_window()['end'] == 60
    store.close()


def test_detail_retention_preserves_three_days_and_committed_history(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_monitoring_settings(settings(), 0)
    for start in range(0, 4 * 86400, 86400):
        store.settle(calculate(settings(), samples(at=start), start, start + 86400), revision, 'UTC')
    before = store.totals(4 * 86400, 'UTC')['estimated_energy_lifetime_kwh']
    store.prune(5 * 86400)
    assert len(store.history(0, 4 * 86400)) == 4
    assert [row[0] for row in store.db.execute('SELECT end FROM window_segments ORDER BY end')] == [
        2 * 86400, 3 * 86400, 4 * 86400,
    ]
    assert store.totals(5 * 86400, 'UTC')['estimated_energy_lifetime_kwh'] == before
    store.close()


def test_fresh_store_defaults_forecast_disabled(tmp_path):
    from pvyieldlens.settings import ForecastSettings

    path = tmp_path / 'fresh.sqlite'
    store = Store(path)
    store.save_monitoring_settings(settings(), 0)
    store.close()
    store = Store(path)
    assert store.forecast_settings() == ForecastSettings()
    assert store.get_meta('forecast_settings') is None
    assert store.revision == 1
    store.close()


def test_forecast_settings_round_trip_keeps_monitoring_metadata(tmp_path):
    from pvyieldlens.settings import ForecastSettings

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    store.save_monitoring_settings(settings(), 0)
    forecast = ForecastSettings(enabled=False, tilt_deg=25.0, azimuth_deg=180.0, noct_c=47.0)
    store.save_forecast_settings(forecast)
    store.close()
    store = Store(path)
    assert store.forecast_settings() == forecast
    assert store.revision == 1
    assert store.cursor == 0
    store.close()


def test_history_summary_uses_energy_ratio_not_mean_pr(tmp_path):
    from pvyieldlens.storage import summarize_history

    store = Store(tmp_path / 'data.sqlite')
    first = settings(total_max_power_at_stc_w=600)
    second = settings(total_max_power_at_stc_w=5400)
    store.settle(calculate(first, samples(power=300, temp=25, sun=1000), 0, 600),
                 store.save_monitoring_settings(first, 0), 'UTC')
    store.settle(calculate(second, samples(power=5400, temp=25, sun=1000, at=600), 600, 1200),
                 store.save_monitoring_settings(second, 600), 'UTC')
    windows = store.history(0, 1200)
    assert [(row['estimated_energy_wh'], row['actual_energy_wh']) for row in windows] == [(100, 50), (900, 900)]
    assert [row['revision'] for row in windows] == [1, 2]
    summary = summarize_history(windows, 0, 1200)
    assert summary.estimated_energy_kwh == pytest.approx(1.0)
    assert summary.actual_energy_kwh == pytest.approx(0.95)
    assert summary.pr == pytest.approx(95.0)
    assert summary.data_completeness_percent == pytest.approx(100.0)
    assert summary.valid_seconds == 1200
    assert (summary.start, summary.end) == (0, 1200)
    assert store.history(0, 1200) == windows
    store.close()


def test_partial_boundary_windows_are_excluded_without_proration(tmp_path):
    import sqlite3
    from pvyieldlens.storage import summarize_history

    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_monitoring_settings(settings(), 0.25)
    for at in (0.25, 600.25, 1200.25):
        store.settle(calculate(settings(), samples(at=at), at, at + 600), revision, 'UTC')
    store.add_observations(samples(at=600.25, sun=100))
    store.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_READ and table in ('window_segments', 'observations')
                            else sqlite3.SQLITE_OK)
    windows = store.history(30.5, 1500.5)
    assert len(windows) == 3
    summary = summarize_history(windows, 30.5, 1500.5)
    assert (summary.start, summary.end) == (600.25, 1200.25)
    assert summary.estimated_energy_kwh == pytest.approx(0.62)
    assert summary.pr == pytest.approx(90)
    assert summary.valid_seconds == 600
    assert summary.data_completeness_percent == 100
    assert all('segments' not in row for row in windows)
    store.close()


@pytest.mark.parametrize('windows,start,end,expected', [
    pytest.param([], 0, 86400, (None, None, None, None, None, None, 0), id='no-windows'),
    pytest.param([{**calculate(settings(), samples(), 0, 60).public(), 'revision': 1}],
                 30, 45, (None, None, None, None, None, None, 0), id='no-full-window'),
    pytest.param([{**calculate(settings(), [], 0, 60).public(), 'revision': 1}],
                 0, 86400, (0, 60, None, None, None, 0, 0), id='missing'),
    pytest.param([{**calculate(settings(), samples(power=0, sun=0), 0, 60).public(), 'revision': 1}],
                 0, 86400, (0, 60, 0, 0, None, 100, 60), id='valid-night'),
    pytest.param([{**calculate(settings(), samples(at=3600), 3600, 3660).public(), 'revision': 1}],
                 0, 86400, (3600, 3660, 0.062, 0.0558, 90, 100, 60), id='short-installation'),
    pytest.param([{**calculate(settings(actual_power_max_age_seconds=30), samples(), 0, 60).public(), 'revision': 1},
                  {**calculate(settings(), [], 60, 120).public(), 'revision': 1},
                  {**calculate(settings(), samples(at=120), 120, 180).public(), 'revision': 2}],
                 0, 86400, (0, 180, 0.093, 0.0837, 90, 50, 90), id='partial-and-missing'),
])
def test_history_summary_no_windows_missing_night_and_short_installation(windows, start, end, expected):
    from pvyieldlens.storage import summarize_history

    summary = summarize_history(windows, start, end)
    assert summary.model_dump() == pytest.approx(dict(zip(
        ('start', 'end', 'estimated_energy_kwh', 'actual_energy_kwh', 'pr', 'data_completeness_percent', 'valid_seconds'), expected)))


@pytest.mark.parametrize('changes', [
    {'valid_seconds': '60'}, {'estimated_energy_kwh': float('nan')},
    {'pr': float('inf')}, {'actual_energy_kwh': float('inf')}, {'extra': 1},
])
def test_history_summary_rejects_non_strict_or_non_finite_values(changes):
    from pydantic import ValidationError
    from pvyieldlens.storage import HistorySummary

    with pytest.raises(ValidationError):
        HistorySummary(**{'start': 0.0, 'end': 60.0, 'estimated_energy_kwh': 0.062, 'actual_energy_kwh': 0.0558,
                          'pr': 90.0, 'data_completeness_percent': 100.0, 'valid_seconds': 60.0, **changes})


def test_ambient_cache_preserves_settled_inputs_and_accepts_pending_predecessor(tmp_path):
    from pvyieldlens.engine import Observation
    from pvyieldlens.settings import AmbientSite

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    site = AmbientSite(latitude=31.2, longitude=121.5)
    entity = site.observation_entity_id
    origin = 'http://ha.test'
    config = settings(module_temperature_entity=None, ambient_site=site)
    revision = store.save_monitoring_settings(config, 60, origin)

    store.cache_ambient_temperature((Observation(entity, 0, 20),), origin)
    original = store.observations(60, 120, (entity,), origin)
    assert original == [Observation(entity, 0, 20)]
    result = calculate(config, samples() + original, 60, 120)
    assert result.estimated_power_w == pytest.approx(3720)
    store.settle(result, revision, 'UTC')

    store.cache_ambient_temperature((Observation(entity, 0, None), Observation(entity, 900, 21)), origin)
    store.cache_ambient_temperature((Observation(entity, 900, 22), Observation(entity, 1800, None)), origin)
    store.close()

    store = Store(path)
    try:
        assert store.observations(60, 120, (entity,), origin) == original
        assert store.observations(900, 1800, (entity,), origin) == [
            Observation(entity, 0, 20), Observation(entity, 900, 22), Observation(entity, 1800, None),
        ]
        assert store.observations(60, 120, (entity,), 'http://other-ha.test') == []
        assert store.history(60, 120)[0]['estimated_power_w'] == pytest.approx(3720)
    finally:
        store.close()
