import pytest

from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from test_engine import samples, settings


async def test_live_does_not_increment_energy_and_statistic_settles_once(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.tick(30)
    assert service.snapshot(30)['live_window']['pr'] == pytest.approx(90)
    assert service.snapshot(30)['energy_totals']['estimated_energy_lifetime_kwh'] == 0
    await service.tick(60)
    await service.tick(60)
    assert service.snapshot(60)['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(0.062)
    store.close()


async def test_timezone_reprojects_committed_midnight_segments_after_late_history_and_restart(tmp_path):
    from datetime import datetime, timezone

    start = datetime(2026, 11, 1, 18, 10, tzinfo=timezone.utc).timestamp()
    path = tmp_path / 'data.sqlite'
    store = Store(path)
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=10), now=start)
    store.add_observations(samples(at=start) + samples(at=start + 300, sun=400))
    await service.tick(start + 600)
    assert service.snapshot(start + 600)['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(.465)
    # The mutable observations have the same total but a different midnight distribution.
    store.add_observations(samples(at=start, sun=400) + samples(at=start + 300))
    await service.configure(settings(settlement_interval_minutes=10, home_timezone='Asia/Kathmandu'), now=start + 600)
    energy = service.snapshot(start + 600)['energy_totals']
    assert energy['estimated_energy_today_kwh'] == pytest.approx(.155)
    assert energy['today_valid_seconds'] == 300
    assert energy['today_allocation_complete'] is True
    assert energy['estimated_energy_lifetime_kwh'] == pytest.approx(.465)
    assert 'segments' not in store.history(start, start + 600)[0]
    await service.configure(settings(settlement_interval_minutes=10), now=start + 600)
    assert service.snapshot(start + 600)['energy_totals']['estimated_energy_today_kwh'] == pytest.approx(.465)
    store.close()
    store = Store(path)
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=10, home_timezone='Asia/Kathmandu'), now=start + 600)
    assert service.snapshot(start + 600)['energy_totals']['estimated_energy_today_kwh'] == pytest.approx(.155)
    store.close()


async def test_timezone_pending_periods_keep_their_calculation_and_origin_in_current_day(tmp_path):
    from datetime import datetime, timezone

    start = datetime(2026, 11, 1, 12, tzinfo=timezone.utc).timestamp()
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=start, origin='old')
    store.add_observations(samples(at=start), 'old')
    await service.tick(start + 60)
    await service.configure(settings(settlement_interval_minutes=1, home_timezone='Asia/Shanghai', total_max_power_at_stc_w=10000),
                            now=start + 90, origin='new')
    store.add_observations(samples(at=start + 90, sun=400), 'new')
    await service.tick(start + 120)
    energy = service.snapshot(start + 120)['energy_totals']
    assert energy['estimated_energy_today_kwh'] == pytest.approx(.124)
    assert energy['estimated_energy_lifetime_kwh'] == pytest.approx(.124)
    assert energy['today_valid_seconds'] == 120
    assert energy['today_allocation_complete'] is True
    store.close()


async def test_timezone_empty_committed_detail_is_not_replaced_by_late_valid_observations(tmp_path):
    from datetime import datetime, timezone

    start = datetime(2026, 11, 1, 18, 10, tzinfo=timezone.utc).timestamp()
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=10), now=start)
    await service.tick(start + 600)
    store.add_observations(samples(at=start))
    await service.configure(settings(settlement_interval_minutes=10, home_timezone='Asia/Kathmandu'), now=start + 600)
    energy = service.snapshot(start + 600)['energy_totals']
    assert energy['estimated_energy_today_kwh'] == energy['estimated_energy_lifetime_kwh'] == 0
    assert energy['today_valid_seconds'] == 0
    assert energy['today_allocation_complete'] is True
    store.close()


async def test_pruned_boundary_quality_persists_without_replaying_on_snapshot(tmp_path):
    import sqlite3
    from datetime import datetime, timezone
    from pvyieldlens.home_assistant import entity_payloads

    start = datetime(2026, 11, 1, 18, 10, tzinfo=timezone.utc).timestamp()
    path = tmp_path / 'data.sqlite'
    store = Store(path)
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=10), now=start)
    store.add_observations(samples(at=start) + samples(at=start + 600))
    await service.tick(start + 1200)
    store.prune(start + 4 * 86400)
    store.close()
    store = Store(path)
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=10, home_timezone='Asia/Kathmandu'), now=start + 1200)
    energy = service.snapshot(start + 1200)['energy_totals']
    assert energy['estimated_energy_today_kwh'] == pytest.approx(.620)
    assert energy['today_valid_seconds'] == 600
    assert energy['today_allocation_complete'] is False
    assert energy['estimated_energy_lifetime_kwh'] == pytest.approx(1.240)
    store.close()
    store = Store(path)
    service = Service(store)
    store.add_observations(samples(at=start + 1200))
    await service.tick(start + 1800)
    store.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_READ and table in ('windows', 'window_segments', 'observations')
                            else sqlite3.SQLITE_OK)
    snapshot = service.snapshot(start + 1800)
    assert snapshot['energy_totals']['estimated_energy_today_kwh'] == pytest.approx(1.240)
    assert snapshot['energy_totals']['today_allocation_complete'] is False
    payloads = entity_payloads(snapshot)
    assert payloads['sensor.pvyieldlens_estimated_energy_today']['attributes']['today_allocation_complete'] is False
    assert service.snapshot(start + 2 * 86400)['energy_totals']['today_allocation_complete'] is True
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
    await service.configure(settings(home_timezone='America/New_York'), now=last - 1)
    energy = service.snapshot(last - 1)['energy_totals']
    assert energy['estimated_energy_today_kwh'] == pytest.approx(hours * 3.72)
    assert energy['today_valid_seconds'] == hours * 3600
    assert energy['today_allocation_complete'] is True
    store.close()


async def test_configuration_change_settles_old_parameters_without_overlap(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.configure(settings(settlement_interval_minutes=1, total_max_power_at_stc_w=10000), now=30)
    await service.tick(60)
    assert service.snapshot(60)['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(0.093)
    store.close()


async def test_only_live_settings_do_not_split_statistic_window(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.configure(settings(settlement_interval_minutes=1, live_window_seconds=120), now=30)
    assert store.cursor == 0
    await service.tick(60)
    assert len(store.history(0, 60)) == 1
    store.close()


async def test_current_missing_source_immediately_invalidates_live(tmp_path):
    from pvyieldlens.engine import Observation
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(), now=0)
    store.add_observations(samples() + [Observation('sensor.sun', 40, None)])
    await service.tick(45)
    assert service.snapshot(45)['live_window']['pr'] is None
    assert service.snapshot(45)['live_window']['reason'] == 'current_source_unavailable'
    store.close()


async def test_config_change_during_outage_defers_settlement_until_recovery(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.tick(60)
    await service.configure(settings(settlement_interval_minutes=1, total_max_power_at_stc_w=10000), now=180)
    assert store.cursor == 60
    store.close()
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    store.add_observations(samples(at=60) + samples(at=180))
    await service.tick(240)
    assert service.snapshot(240)['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(0.310)
    assert [row['revision'] for row in store.history(0,240)] == [1,1,1,2]
    store.close()


async def test_connection_change_separates_same_named_sources(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=0, origin='http://old-ha')
    store.add_observations(samples(), origin='http://old-ha')
    await service.configure(settings(settlement_interval_minutes=1), now=30, origin='http://new-ha')
    store.add_observations(samples(sun=400), origin='http://new-ha')
    await service.tick(60)
    assert service.snapshot(60)['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(0.0465)
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
    await service.configure(settings(settlement_interval_minutes=1), now=120)
    await service.start()
    try:
        await asyncio.sleep(0.05)
        assert client.history_calls == 0
        assert store.cursor == 120
        ready.set()
        async with asyncio.timeout(2):
            while store.cursor != 180:
                await asyncio.sleep(0.01)
        assert service.snapshot(180)['latest_settled_window']['estimated_power_w'] == pytest.approx(3410)
    finally:
        await service.stop()
        store.close()


@pytest.mark.parametrize('minutes,energy', [(1,0.062),(5,0.310),(10,0.620)])
async def test_selected_grid_interval_settles_at_its_boundary(tmp_path, minutes, energy):
    store = Store(tmp_path/'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=minutes), now=0)
    store.add_observations(samples())
    await service.tick(minutes*60-1)
    assert store.latest_settled_window() is None
    await service.tick(minutes*60)
    assert service.snapshot(minutes*60)['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(energy)
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
        assert service.snapshot(180)['live_window'] is None
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
        await service.configure(settings(settlement_interval_minutes=1), now=120)
        try:
            await service.recover()
            assert service.snapshot(180)['history_available'] is False
            available = True
            await service.recover()
            assert service.snapshot(180)['history_available'] is True
            await service.tick(180)
            assert service.snapshot(180)['latest_settled_window']['pr'] == pytest.approx(90)
            assert service.snapshot(180)['latest_settled_window']['data_completeness_percent'] == pytest.approx(100)
        finally:
            await client.close()
            store.close()


async def test_http_location_bootstraps_forecast_before_websocket_ready(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from forecast_fixtures import forecast_payload
    from pvyieldlens.forecast_service import ForecastController
    from pvyieldlens.home_assistant import HomeAssistantClient
    from pvyieldlens.open_meteo import OpenMeteoClient
    from pvyieldlens.settings import ForecastSettings

    received, ready = asyncio.Event(), asyncio.Event()
    requests = []

    def ha_response(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={'time_zone': 'UTC', 'latitude': 31.23, 'longitude': 121.47,
                                       'location_name': 'Home'})

    async def events():
        await ready.wait()
        yield None
        await asyncio.Event().wait()

    def weather_response(request):
        received.set()
        return httpx.Response(200, json=forecast_payload(0))

    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    store = Store(tmp_path / 'data.sqlite')
    store.save_monitoring_settings(settings(settlement_interval_minutes=1), 120, 'http://ha.test')
    store.save_forecast_settings(ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0))
    async with httpx.AsyncClient(transport=httpx.MockTransport(ha_response)) as ha_http, \
            httpx.AsyncClient(transport=httpx.MockTransport(weather_response)) as weather_http:
        ha_client = HomeAssistantClient('http://ha.test', 'secret', ha_http)
        monkeypatch.setattr(ha_client, 'events', events)
        service = Service(store, ha_client)
        service.forecast = ForecastController(store, OpenMeteoClient(weather_http))
        await service.start()
        try:
            await asyncio.wait_for(received.wait(), 1)
            assert service.forecast.view(180).fetched_at == 180
            assert service.forecast.location.latitude == 31.23
            assert requests == ['/api/config']
            assert store.cursor == 120
            assert service.subscribed.is_set() is False
        finally:
            await service.stop()
    store.close()


async def test_om_timeout_does_not_stop_monitoring(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from datetime import datetime, timezone
    from pvyieldlens.forecast_service import ForecastController
    from pvyieldlens.home_assistant import HAConfig, HAState
    from pvyieldlens.open_meteo import OpenMeteoClient
    from pvyieldlens.settings import ForecastSettings, HALocation

    received = asyncio.Event()
    location = HALocation(origin='http://ha.test', latitude=0.0, longitude=0.0, home_timezone='UTC')

    class LiveClient:
        async def events(self):
            yield None
            await asyncio.Event().wait()

        async def configuration(self):
            return HAConfig(time_zone='UTC', location=location)

        async def history(self, entities, start, end):
            return self._states(120)

        def _states(self, at):
            stamp = datetime.fromtimestamp(at, timezone.utc)
            return [HAState(entity_id=entity, state=str(value), attributes={'unit_of_measurement': unit},
                            last_updated=stamp, last_changed=stamp)
                    for entity, value, unit in [('sensor.power', 3348, 'W'), ('sensor.temp', 45, '°C'),
                                                 ('sensor.sun', 800, 'W/m²')]]

        async def states(self, entities):
            return self._states(180)

        async def publish(self, payloads):
            pass

        async def close(self):
            pass

    def timeout(request):
        received.set()
        raise httpx.ReadTimeout('timeout', request=request)

    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    store = Store(tmp_path / 'data.sqlite')
    store.save_monitoring_settings(settings(settlement_interval_minutes=1), 120, location.origin)
    store.save_forecast_settings(ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0))
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http:
        service = Service(store, LiveClient())
        service.forecast = ForecastController(store, OpenMeteoClient(http))
        await service.start()
        try:
            await asyncio.wait_for(received.wait(), 1)
            async with asyncio.timeout(1):
                while store.cursor != 180:
                    await asyncio.sleep(0)
            assert service.snapshot(180)['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(.062)
            assert service.snapshot(180)['connected'] is True
            assert service.snapshot(180)['error'] is None
            assert service.forecast.view(180).status == 'unavailable'
        finally:
            await service.stop()
    store.close()


async def test_ha_outage_uses_cached_location(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from forecast_fixtures import forecast_payload
    from pvyieldlens.forecast_service import ForecastController
    from pvyieldlens.open_meteo import OpenMeteoClient
    from pvyieldlens.settings import ForecastSettings, HALocation

    received = asyncio.Event()
    path = tmp_path / 'data.sqlite'
    store = Store(path)
    store.save_monitoring_settings(settings(), 120, 'http://ha.test')
    forecast = ForecastController(store)
    forecast.configure(settings(), ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0),
                       'http://ha.test', HALocation(origin='http://ha.test', latitude=0.0, longitude=0.0,
                                                  home_timezone='UTC'))
    store.close()
    store = Store(path)

    class OfflineClient:
        async def events(self):
            raise OSError('offline')
            yield None

        async def configuration(self):
            raise OSError('offline')

        async def publish(self, payloads):
            pass

        async def close(self):
            pass

    def respond(request):
        received.set()
        return httpx.Response(200, json=forecast_payload(0))

    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        service = Service(store, OfflineClient())
        service.forecast = ForecastController(store, OpenMeteoClient(http))
        await service.start()
        try:
            await asyncio.wait_for(received.wait(), 1)
            assert service.forecast.view(180).today.forecast_energy_kwh == pytest.approx(89.28)
            assert service.forecast.location.origin == 'http://ha.test'
            assert service.snapshot(180)['connected'] is False
            assert store.cursor == 120
        finally:
            await service.stop()
    store.close()


async def test_unchanged_monitoring_configuration_keeps_live_and_sources(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=0)
    store.add_observations(samples())
    await service.tick(60)
    service.sources = [{'entity_id': 'sensor.sun', 'valid': True}]
    before = service.snapshot(60)
    changes = store.db.total_changes
    await service.configure(settings(settlement_interval_minutes=1), now=61)
    assert service.snapshot(60) == before
    assert store.db.total_changes == changes
    store.close()


async def test_service_restart_recreates_separate_owned_weather_client(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from forecast_fixtures import forecast_payload
    from pvyieldlens.settings import ForecastSettings, HALocation

    received = asyncio.Event()
    clients, requests = [], []
    original_client = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        received.set()
        return httpx.Response(200, json=forecast_payload(0))

    def weather_client(**kwargs):
        client = original_client(transport=httpx.MockTransport(respond), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr('pvyieldlens.open_meteo.httpx.AsyncClient', weather_client)
    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=120, origin='http://ha.test')
    service.forecast.configure(service.monitoring_settings, ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0),
                               service.origin, HALocation(origin=service.origin, latitude=0.0, longitude=0.0,
                                                          home_timezone='UTC'))
    for _ in range(2):
        received.clear()
        await service.start()
        await asyncio.wait_for(received.wait(), 1)
        await service.stop()
        assert clients[-1].is_closed is True
    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert all('authorization' not in request.headers and 'cookie' not in request.headers for request in requests)
    assert all(request.url.host == 'api.open-meteo.com' for request in requests)
    store.close()


async def test_successful_invalid_ha_location_clears_cached_site(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from forecast_fixtures import forecast_payload
    from pvyieldlens.forecast_service import ForecastController
    from pvyieldlens.home_assistant import HomeAssistantClient
    from pvyieldlens.open_meteo import OpenMeteoClient
    from pvyieldlens.settings import ForecastSettings, HALocation

    async def events():
        await asyncio.Event().wait()
        yield None

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    service = Service(store)
    await service.configure(settings(), now=120, origin='http://ha.test')
    service.forecast.configure(service.monitoring_settings, ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0),
                               service.origin, HALocation(origin=service.origin, latitude=0.0, longitude=0.0,
                                                          home_timezone='UTC'))
    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'time_zone': 'UTC', 'latitude': 95.0, 'longitude': 0.0},
    ))) as ha_http, httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json=forecast_payload(0),
    ))) as weather_http:
        client = HomeAssistantClient(service.origin, 'secret', ha_http)
        monkeypatch.setattr(client, 'events', events)
        service.client = client
        service.forecast = ForecastController(store, OpenMeteoClient(weather_http))
        await service.start()
        try:
            async with asyncio.timeout(1):
                while service.forecast.location is not None:
                    await asyncio.sleep(0)
            assert service.forecast.view(180).status == 'location_unavailable'
            assert store.cursor == 120
        finally:
            await service.stop()
    store.close()
    store = Store(path)
    restored = ForecastController(store)
    assert restored.location is None
    assert restored.view(180).status == 'location_unavailable'
    store.close()


async def test_shared_monitoring_inputs_update_forecast_and_new_origin_drops_site(tmp_path):
    from pvyieldlens.settings import ForecastSettings, HALocation

    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(), now=0, origin='http://ha.test')
    service.forecast.configure(service.monitoring_settings, ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0),
                               service.origin, HALocation(origin=service.origin, latitude=0.0, longitude=0.0,
                                                          home_timezone='UTC'))
    await service.configure(settings(total_max_power_at_stc_w=6000, pmax_temperature_coefficient_pct_per_c=-0.4), now=30)
    assert service.forecast.inputs.total_max_power_at_stc_w == 6000
    assert service.forecast.inputs.pmax_temperature_coefficient_pct_per_c == -0.4
    await service.configure(service.monitoring_settings, now=60, origin='http://new-ha.test')
    assert service.forecast.location is None
    assert service.forecast.view(60).status == 'location_unavailable'
    store.close()


async def test_correction_invalidates_once_for_recovered_closed_day_settlement_batch(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from pvyieldlens.engine import calculate
    from pvyieldlens.home_assistant import HAState
    from pvyieldlens.settings import ForecastSettings, HALocation
    from test_correction import ORIGIN, TODAY, committed_days

    stamp = datetime.fromtimestamp(TODAY - 180, timezone.utc)
    recovered = [HAState(entity_id=entity, state=str(value), attributes={'unit_of_measurement': unit},
                         last_updated=stamp, last_changed=stamp)
                 for entity, value, unit in [('sensor.power', 10800, 'W'), ('sensor.temp', 25, '°C'),
                                             ('sensor.sun', 12000, 'W/m²')]]

    class HistoryClient:
        async def history(self, entities, start, end):
            return recovered

        async def states(self, entities):
            return []

    store = Store(tmp_path / 'data.sqlite')
    config = committed_days(store, [(1000, 900)] * 2, first_age=3,
                            config=settings(total_max_power_at_stc_w=1000, settlement_interval_minutes=1))
    store.settle(calculate(config, [], store.cursor, TODAY - 180), store.revision, 'UTC')
    service = Service(store, HistoryClient())
    service.forecast.configure(config, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180),
        ORIGIN, HALocation(origin=ORIGIN, latitude=0, longitude=0, home_timezone='UTC'))
    calls = []
    invalidate = service.forecast.invalidate_correction

    def counted():
        calls.append(store.cursor)
        invalidate()

    monkeypatch.setattr(service.forecast, 'invalidate_correction', counted)
    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: TODAY + 60)
    before = service.forecast.view(TODAY + 60).correction
    assert before.pr is None
    await service.recover()
    assert calls == []
    await service.tick(TODAY + 60)
    assert calls == [TODAY + 60]
    after = service.forecast.view(TODAY + 60).correction
    assert after.pr == pytest.approx(90)
    await service.tick(TODAY + 120)
    assert calls == [TODAY + 60]
    assert service.forecast.view(TODAY + 120).correction is after
    store.close()
