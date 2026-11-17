import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pvyieldlens.engine import calculate
from pvyieldlens.storage import Store
from test_engine import samples, settings


ORIGIN = 'http://ha.test'
NOW = datetime(2026, 11, 17, 12, tzinfo=ZoneInfo('UTC')).timestamp()
TODAY = NOW - 12 * 3600


@pytest.fixture
def store(tmp_path):
    instance = Store(tmp_path / 'data.sqlite')
    yield instance
    instance.close()


def committed_days(store, energies, *, config=None, first_age=None):
    config = config or settings(total_max_power_at_stc_w=1000)
    oldest = first_age if first_age is not None else len(energies)
    start = TODAY - oldest * 86400
    revision = store.save_monitoring_settings(config, start, ORIGIN)
    for index, (estimated, actual) in enumerate(energies):
        left = start + index * 86400
        points = samples(at=left, power=actual * 12, sun=estimated * 12, temp=25)
        result = calculate(config, points, left, left + 86400)
        store.settle(result, revision, config.home_timezone)
    return config


def test_correction_weights_energy_and_recency_by_calendar_age(store):
    from pvyieldlens.correction import correction_view

    config = committed_days(store, [(2000, 1000), *[(0, 0)] * 5, (3000, 2400), (1000, 900)])
    expected = (900 + 2400 * 2 ** (-1 / 7) + 1000 * 0.5) / (1000 + 3000 * 2 ** (-1 / 7) + 2000 * 0.5)
    correction = correction_view(store, config, ORIGIN, NOW, 14)
    assert correction.pr == pytest.approx(expected * 100)
    assert (correction.history_days, correction.start, correction.end) == (14, TODAY - 14 * 86400, TODAY)
    assert correction_view(store, config, ORIGIN, NOW, 3).pr is None


@pytest.mark.parametrize('energies,expected', [
    ([(1000, 900)] * 2, None), ([(0, 0)] * 3, None),
    ([(1000, 0)] * 3, 0), ([(1000, 1100)] * 3, 110),
])
def test_correction_requires_three_positive_estimated_dates_and_keeps_zero_or_above_100(store, energies, expected):
    from pvyieldlens.correction import correction_view

    config = committed_days(store, energies)
    assert correction_view(store, config, ORIGIN, NOW, 14).pr == (pytest.approx(expected) if expected is not None else None)


def test_correction_excludes_today(store):
    from pvyieldlens.correction import correction_view

    config = committed_days(store, [(1000, 900)] * 2)
    store.settle(calculate(config, samples(at=TODAY), TODAY, TODAY + 300), store.revision, 'UTC')
    assert correction_view(store, config, ORIGIN, NOW, 14).pr is None


@pytest.mark.parametrize('changes', [
    {'total_max_power_at_stc_w': 2000}, {'pmax_temperature_coefficient_pct_per_c': -0.4},
    {'actual_power_entity': 'sensor.changed'}, {'irradiance_entity': 'sensor.changed'},
    {'module_temperature_entity': 'sensor.changed'},
])
def test_correction_starts_latest_contiguous_physical_epoch(store, changes):
    from pvyieldlens.correction import correction_view

    config = committed_days(store, [(1000, 900)] * 3)
    changed = config.model_copy(update=changes)
    store.save_monitoring_settings(changed, TODAY - 3600, ORIGIN)
    assert correction_view(store, changed, ORIGIN, NOW, 14).pr is None
    store.save_monitoring_settings(config, TODAY, ORIGIN)
    assert correction_view(store, config, ORIGIN, NOW, 14).pr is None


def test_correction_source_change_excludes_prior_source(store):
    from pvyieldlens.correction import correction_view

    config = committed_days(store, [(1000, 900)] * 3)
    store.save_monitoring_settings(config, TODAY, 'http://other.test')
    assert correction_view(store, config, 'http://other.test', NOW, 14).pr is None


@pytest.mark.parametrize('changes', [
    {'live_window_seconds': 120}, {'update_interval_seconds': 10},
    {'settlement_interval_minutes': 10}, {'actual_power_max_age_seconds': 600},
])
def test_correction_retains_committed_history_for_nonphysical_changes(store, changes):
    from pvyieldlens.correction import correction_view

    config = committed_days(store, [(1000, 900)] * 3)
    changed = config.model_copy(update=changes)
    store.save_monitoring_settings(changed, TODAY, ORIGIN)
    assert correction_view(store, changed, ORIGIN, NOW, 14).pr == pytest.approx(90)


def test_correction_rejects_day_with_inexact_allocation_even_if_partial_summary_is_numeric(store):
    from pvyieldlens.correction import correction_view

    config = committed_days(store, [(1000, 900)] * 3)
    # A legacy source window overlaps an otherwise usable day without exact calendar allocation.
    row = json.loads(store.db.execute('SELECT result FROM windows ORDER BY start LIMIT 1').fetchone()[0])
    left = TODAY - 3 * 86400 - 60
    row.update(start=left, end=left + 120)
    with store.db:
        store.db.execute('INSERT INTO windows VALUES (?,?,?,?)', (store.revision, left, left + 120, json.dumps(row)))
    assert correction_view(store, config, ORIGIN, NOW, 14).pr is None


def test_correction_uses_household_calendar_days_across_dst(store):
    from pvyieldlens.correction import correction_view

    zone = ZoneInfo('Europe/Berlin')
    now = datetime(2026, 10, 27, 12, tzinfo=zone).timestamp()
    config = settings(home_timezone='Europe/Berlin')
    result = correction_view(store, config, ORIGIN, now, 3)
    assert result.start == datetime(2026, 10, 24, tzinfo=zone).timestamp()
    assert result.end == datetime(2026, 10, 27, tzinfo=zone).timestamp()
    assert result.end - result.start == 73 * 3600
