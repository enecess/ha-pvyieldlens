from datetime import datetime, timezone

import pytest

from pvyieldlens.engine import calculate
from pvyieldlens.storage import Store
from test_engine import samples, settings


def test_restart_and_duplicate_settlement_are_idempotent(tmp_path):
    path = tmp_path / 'data.sqlite'
    store = Store(path)
    revision = store.save_settings(settings(), 0)
    result = calculate(settings(), samples(), 0, 60)
    store.settle(result, revision, 'UTC')
    store.settle(result, revision, 'UTC')
    store.close()
    restored = Store(path)
    assert restored.totals(60, 'UTC')['total_kwh'] == pytest.approx(0.062)
    assert restored.cursor == 60
    assert restored.settings().temperature_coefficient_pct_per_c == -0.35
    restored.close()


def test_midnight_splits_energy_and_empty_new_day_is_zero(tmp_path):
    start = datetime(2026, 10, 28, 15, 59, 30, tzinfo=timezone.utc).timestamp()
    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_settings(settings(), start)
    store.settle(calculate(settings(), samples(at=start), start, start + 60), revision, 'Asia/Shanghai')
    assert store.totals(start, 'Asia/Shanghai')['daily_kwh'] == pytest.approx(0.031)
    assert store.totals(start + 60, 'Asia/Shanghai')['daily_kwh'] == pytest.approx(0.031)
    assert store.totals(start + 86460, 'Asia/Shanghai')['daily_kwh'] == 0
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


def test_retention_keeps_totals_and_latest_window(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_settings(settings(), 0)
    store.settle(calculate(settings(), samples(), 0, 60), revision, 'UTC')
    store.prune(100 * 86400)
    assert store.totals(100 * 86400, 'UTC')['total_kwh'] == pytest.approx(0.062)
    assert store.latest_window()['end'] == 60
    store.close()


def test_detail_retention_preserves_three_days_and_committed_history(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_settings(settings(), 0)
    for start in range(0, 4 * 86400, 86400):
        store.settle(calculate(settings(), samples(at=start), start, start + 86400), revision, 'UTC')
    before = store.totals(4 * 86400, 'UTC')['total_kwh']
    store.prune(5 * 86400)
    assert len(store.history(0, 4 * 86400)) == 4
    assert [row[0] for row in store.db.execute('SELECT end FROM window_segments ORDER BY end')] == [
        2 * 86400, 3 * 86400, 4 * 86400,
    ]
    assert store.totals(5 * 86400, 'UTC')['total_kwh'] == before
    store.close()
