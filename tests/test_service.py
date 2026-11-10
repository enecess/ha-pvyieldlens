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


async def test_timezone_reprojects_committed_midnight_segments_after_late_history_and_restart(tmp_path):
    from datetime import datetime, timezone

    start = datetime(2026, 11, 1, 18, 10, tzinfo=timezone.utc).timestamp()
    path = tmp_path / 'data.sqlite'
    store = Store(path)
    service = Service(store)
    await service.configure(settings(interval_minutes=10), now=start)
    store.add_observations(samples(at=start) + samples(at=start + 300, sun=400))
    await service.tick(start + 600)
    assert service.snapshot(start + 600)['energy']['total_kwh'] == pytest.approx(.465)
    # The mutable observations have the same total but a different midnight distribution.
    store.add_observations(samples(at=start, sun=400) + samples(at=start + 300))
    await service.configure(settings(interval_minutes=10, timezone='Asia/Kathmandu'), now=start + 600)
    energy = service.snapshot(start + 600)['energy']
    assert energy['daily_kwh'] == pytest.approx(.155)
    assert energy['daily_valid_seconds'] == 300
    assert energy['daily_complete'] is True
    assert energy['total_kwh'] == pytest.approx(.465)
    assert 'segments' not in store.history(start, start + 600)[0]
    await service.configure(settings(interval_minutes=10), now=start + 600)
    assert service.snapshot(start + 600)['energy']['daily_kwh'] == pytest.approx(.465)
    store.close()
    store = Store(path)
    service = Service(store)
    await service.configure(settings(interval_minutes=10, timezone='Asia/Kathmandu'), now=start + 600)
    assert service.snapshot(start + 600)['energy']['daily_kwh'] == pytest.approx(.155)
    store.close()


async def test_timezone_pending_periods_keep_their_calculation_and_origin_in_current_day(tmp_path):
    from datetime import datetime, timezone

    start = datetime(2026, 11, 1, 12, tzinfo=timezone.utc).timestamp()
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=1), now=start, origin='old')
    store.add_observations(samples(at=start), 'old')
    await service.tick(start + 60)
    await service.configure(settings(interval_minutes=1, timezone='Asia/Shanghai', rated_power_w=10000),
                            now=start + 90, origin='new')
    store.add_observations(samples(at=start + 90, sun=400), 'new')
    await service.tick(start + 120)
    energy = service.snapshot(start + 120)['energy']
    assert energy['daily_kwh'] == pytest.approx(.124)
    assert energy['total_kwh'] == pytest.approx(.124)
    assert energy['daily_valid_seconds'] == 120
    assert energy['daily_complete'] is True
    store.close()


async def test_timezone_empty_committed_detail_is_not_replaced_by_late_valid_observations(tmp_path):
    from datetime import datetime, timezone

    start = datetime(2026, 11, 1, 18, 10, tzinfo=timezone.utc).timestamp()
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=10), now=start)
    await service.tick(start + 600)
    store.add_observations(samples(at=start))
    await service.configure(settings(interval_minutes=10, timezone='Asia/Kathmandu'), now=start + 600)
    energy = service.snapshot(start + 600)['energy']
    assert energy['daily_kwh'] == energy['total_kwh'] == 0
    assert energy['daily_valid_seconds'] == 0
    assert energy['daily_complete'] is True
    store.close()


async def test_legacy_boundary_quality_persists_without_replaying_on_snapshot(tmp_path):
    import sqlite3
    from datetime import datetime, timezone
    from pvyieldlens.home_assistant import entity_payloads

    start = datetime(2026, 11, 1, 18, 10, tzinfo=timezone.utc).timestamp()
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as old:
        old.execute('CREATE TABLE days (timezone TEXT, day TEXT, energy_wh REAL, valid_seconds REAL, PRIMARY KEY(timezone, day))')
    store = Store(path)
    service = Service(store)
    await service.configure(settings(interval_minutes=10), now=start)
    store.add_observations(samples(at=start) + samples(at=start + 600))
    await service.tick(start + 1200)
    store.db.execute('DROP TABLE IF EXISTS window_segments')
    store.close()
    store = Store(path)
    service = Service(store)
    await service.configure(settings(interval_minutes=10, timezone='Asia/Kathmandu'), now=start + 1200)
    energy = service.snapshot(start + 1200)['energy']
    assert energy['daily_kwh'] == pytest.approx(.620)
    assert energy['daily_valid_seconds'] == 600
    assert energy['daily_complete'] is False
    assert energy['total_kwh'] == pytest.approx(1.240)
    store.close()
    store = Store(path)
    service = Service(store)
    store.add_observations(samples(at=start + 1200))
    await service.tick(start + 1800)
    store.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_READ and table in ('windows', 'window_segments', 'observations')
                            else sqlite3.SQLITE_OK)
    snapshot = service.snapshot(start + 1800)
    assert snapshot['energy']['daily_kwh'] == pytest.approx(1.240)
    assert snapshot['energy']['daily_complete'] is False
    payloads = entity_payloads(snapshot)
    assert payloads['sensor.pvyieldlens_daily_estimated_energy']['attributes']['daily_complete'] is False
    assert service.snapshot(start + 2 * 86400)['energy']['daily_complete'] is True
    store.close()


@pytest.mark.parametrize('month,day,hours', [(3,8,23), (11,1,25)])
async def test_timezone_projection_uses_actual_eastern_day_boundaries(tmp_path, month, day, hours):
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    from pvyieldlens.engine import calculate

    local = datetime(2026, month, day, tzinfo=ZoneInfo('America/New_York'))
    first, last = local.timestamp(), (local + timedelta(days=1)).timestamp()
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(), now=first - 3600)
    # Include an earlier hour that the new local day must exclude.
    observations = [point for at in range(int(first - 3600), int(last), 300) for point in samples(at=at)]
    store.settle(calculate(settings(), observations, first - 3600, first), 1, 'UTC')
    store.settle(calculate(settings(), observations, first, last), 1, 'UTC')
    await service.configure(settings(timezone='America/New_York'), now=last - 1)
    energy = service.snapshot(last - 1)['energy']
    assert energy['daily_kwh'] == pytest.approx(hours * 3.72)
    assert energy['daily_valid_seconds'] == hours * 3600
    assert energy['daily_complete'] is True
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


async def test_config_change_during_outage_defers_settlement_until_recovery(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.tick(60)
    await service.configure(settings(interval_minutes=1, rated_power_w=10000), now=180)
    assert store.cursor == 60
    store.close()
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    store.add_observations(samples(at=60) + samples(at=180))
    await service.tick(240)
    assert service.snapshot(240)['energy']['total_kwh'] == pytest.approx(0.310)
    assert [row['revision'] for row in store.history(0,240)] == [1,1,1,2]
    store.close()


async def test_connection_change_separates_same_named_sources(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=1), now=0, origin='http://old-ha')
    store.add_observations(samples(), origin='http://old-ha')
    await service.configure(settings(interval_minutes=1), now=30, origin='http://new-ha')
    store.add_observations(samples(sun=400), origin='http://new-ha')
    await service.tick(60)
    assert service.snapshot(60)['energy']['total_kwh'] == pytest.approx(0.0465)
    assert len(store.history(0,60)) == 2
    store.close()


async def test_subscription_ready_before_history_and_settlement(tmp_path, monkeypatch):
    import asyncio
    from pvyieldlens.home_assistant import HAConfig, HAState
    from datetime import datetime, timezone
    ready = asyncio.Event()

    class DelayedClient:
        history_calls = 0

        async def events(self):
            await ready.wait()
            yield None
            await asyncio.Event().wait()

        async def configuration(self):
            return HAConfig(time_zone='UTC')

        async def history(self, entities, start, end):
            self.history_calls += 1
            return self._states(120) + [self._states(125, 400)[2], self._states(135)[2]]

        def _states(self, at, sun=800):
            stamp = datetime.fromtimestamp(at, timezone.utc)
            return [HAState(entity_id=entity,state=str(value),attributes={'unit_of_measurement':unit},
                            last_updated=stamp,last_changed=stamp)
                    for entity,value,unit in [('sensor.power',3348,'W'),('sensor.temp',45,'°C'),('sensor.sun',sun,'W/m²')]]

        async def states(self, entities):
            return self._states(180)

        async def publish(self, payloads):
            pass

        async def close(self):
            pass

    monkeypatch.setattr('pvyieldlens.service.time.time', lambda:180)
    client = DelayedClient()
    store = Store(tmp_path/'data.sqlite')
    service = Service(store, client)
    await service.configure(settings(interval_minutes=1), now=120)
    await service.start()
    try:
        await asyncio.sleep(0.05)
        assert client.history_calls == 0
        assert store.cursor == 120
        ready.set()
        async with asyncio.timeout(2):
            while store.cursor != 180:
                await asyncio.sleep(0.01)
        assert service.snapshot(180)['statistics']['estimated_power'] == pytest.approx(3410)
    finally:
        await service.stop()
        store.close()


@pytest.mark.parametrize('minutes,energy', [(1,0.062),(5,0.310),(10,0.620)])
async def test_selected_grid_interval_settles_at_its_boundary(tmp_path, minutes, energy):
    store = Store(tmp_path/'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=minutes), now=0)
    store.add_observations(samples())
    await service.tick(minutes*60-1)
    assert store.latest_window() is None
    await service.tick(minutes*60)
    assert service.snapshot(minutes*60)['energy']['total_kwh'] == pytest.approx(energy)
    store.close()


async def test_outage_publishes_a_new_unavailable_snapshot_for_chart_break(tmp_path, monkeypatch):
    import asyncio

    class OfflineClient:
        async def events(self):
            raise OSError('offline')
            yield None

        async def configuration(self):
            raise OSError('offline')

        async def publish(self, payloads):
            raise OSError('offline')

        async def close(self):
            pass

    store = Store(tmp_path/'data.sqlite')
    service = Service(store, OfflineClient())
    await service.configure(settings(), now=0)
    store.add_observations(samples())
    await service.tick(100)
    monkeypatch.setattr('pvyieldlens.service.time.time', lambda:180)
    await service.start()
    try:
        await asyncio.sleep(0.05)
        assert service.snapshot(180)['calculated_at'] == 180
        assert service.snapshot(180)['realtime'] is None
    finally:
        await service.stop()
        store.close()


async def test_clean_event_stream_close_marks_connection_unavailable(tmp_path):
    import asyncio
    from contextlib import suppress
    close = asyncio.Event()

    class ClosingClient:
        calls = 0

        async def events(self):
            self.calls += 1
            if self.calls > 1:
                await asyncio.Event().wait()
            yield None
            await close.wait()

    store = Store(tmp_path/'data.sqlite')
    service = Service(store, ClosingClient())
    task = asyncio.create_task(service._events())
    try:
        await asyncio.wait_for(service.subscribed.wait(), 1)
        service.connected = True
        close.set()
        await asyncio.sleep(0.02)
        assert not service.snapshot()['connected']
        assert service.snapshot()['error'] == 'ha_connection_failed'
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        store.close()


async def test_history_unavailable_warning_clears_after_successful_recovery(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fake_ha import source_states
    from pvyieldlens.home_assistant import HomeAssistantClient
    from test_integration import fake_server

    available = False
    ha = FastAPI()

    @ha.get('/api/history/period/{start}')
    async def history(start: str):
        if not available:
            return JSONResponse({'message': 'History unavailable'}, status_code=404)
        return [[state] for state in source_states(120)]

    @ha.post('/api/template')
    async def selected_states():
        return source_states(180)

    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    async with fake_server(ha) as url:
        store = Store(tmp_path / 'data.sqlite')
        client = HomeAssistantClient(url, 'simulation-token')
        service = Service(store, client)
        await service.configure(settings(interval_minutes=1), now=120)
        try:
            await service.recover()
            assert service.snapshot(180)['history_available'] is False
            available = True
            await service.recover()
            assert service.snapshot(180)['history_available'] is True
            await service.tick(180)
            assert service.snapshot(180)['statistics']['pr'] == pytest.approx(90)
            assert service.snapshot(180)['statistics']['coverage_percent'] == pytest.approx(100)
        finally:
            await client.close()
            store.close()
