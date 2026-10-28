import pytest

from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from test_engine import samples, settings


async def test_realtime_does_not_increment_energy_and_statistic_settles_once(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.tick(30)
    assert service.snapshot(30)['realtime']['pr'] == pytest.approx(90)
    assert service.snapshot(30)['energy']['total_kwh'] == 0
    await service.tick(60)
    await service.tick(60)
    assert service.snapshot(60)['energy']['total_kwh'] == pytest.approx(0.062)
    store.close()


async def test_configuration_change_settles_old_parameters_without_overlap(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.configure(settings(interval_minutes=1, rated_power_w=10000), now=30)
    await service.tick(60)
    assert service.snapshot(60)['energy']['total_kwh'] == pytest.approx(0.093)
    store.close()


async def test_only_realtime_settings_do_not_split_statistic_window(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.configure(settings(interval_minutes=1, realtime_window_seconds=120), now=30)
    assert store.cursor == 0
    await service.tick(60)
    assert len(store.history(0, 60)) == 1
    store.close()


async def test_current_missing_source_immediately_invalidates_realtime(tmp_path):
    from pvyieldlens.engine import Observation
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(), now=0)
    store.add_observations(samples() + [Observation('sensor.sun', 40, None)])
    await service.tick(45)
    assert service.snapshot(45)['realtime']['pr'] is None
    assert service.snapshot(45)['realtime']['reason'] == 'current_source_unavailable'
    store.close()
