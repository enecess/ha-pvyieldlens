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
    assert len(store.observations(30, 60)) == 3
    store.close()


def test_retention_keeps_totals_and_latest_window(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    revision = store.save_settings(settings(), 0)
    store.settle(calculate(settings(), samples(), 0, 60), revision, 'UTC')
    store.prune(100 * 86400)
    assert store.totals(100 * 86400, 'UTC')['total_kwh'] == pytest.approx(0.062)
    assert store.latest_window()['end'] == 60
    store.close()
