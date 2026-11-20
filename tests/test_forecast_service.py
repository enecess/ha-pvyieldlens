import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from forecast_fixtures import forecast_payload
from pvyieldlens.home_assistant import HomeAssistantClient
from pvyieldlens.open_meteo import OpenMeteoClient
from pvyieldlens.settings import ForecastSettings, HALocation
from pvyieldlens.storage import Store
from test_engine import samples, settings


ORIGIN = 'http://ha.test'
PREDICTION = ForecastSettings(tilt_deg=25.0, azimuth_deg=180.0)
LOCATION = HALocation(origin=ORIGIN, latitude=0.0, longitude=0.0, home_timezone='UTC')


def angle_state(entity_id, value, unit='°'):
    return {'entity_id': entity_id, 'state': value,
        'attributes': {'unit_of_measurement': unit},
        'last_updated': '1970-01-01T00:00:00+00:00', 'last_changed': '1970-01-01T00:00:00+00:00',
        'last_reported': '1970-01-01T00:00:00+00:00'}


def controller(store, http, *, prediction=PREDICTION, ha_client=None):
    from pvyieldlens.forecast_service import ForecastController

    forecast = ForecastController(store, OpenMeteoClient(http), ha_client=ha_client)
    forecast.configure(settings(), prediction, ORIGIN, LOCATION)
    return forecast


async def test_cache_restart_preserves_fetched_at(tmp_path):
    from pvyieldlens.forecast_service import ForecastController
    from pvyieldlens.engine import calculate

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    store.save_monitoring_settings(settings(), 0, ORIGIN)
    store.settle(calculate(settings(), samples(), 0, 60), store.revision, 'UTC')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=forecast_payload(0, weather_code=61)),
    )) as http:
        forecast = controller(store, http)
        store.set_meta('forecast_cache', '{}')
        await forecast.refresh(now=120)
        assert forecast.view(180).fetched_at == 120
        assert store.get_meta('forecast_cache') == '{}'
        assert store.get_meta('forecast_cache_v2') is not None
        store.close()
        store = Store(path)
        restored = ForecastController(store)
        assert restored.view(180).fetched_at == 120
        assert restored.view(180).today.forecast_energy_kwh == pytest.approx(89.28)
        assert restored.view(180).days[0].weather.weather_code == 61
        assert len(restored.batch.weather_samples) == 217
        assert len(restored.batch.intervals) == 864
        assert store.revision == 1
        assert store.cursor == 60
        assert store.monitoring_settings() == settings()
        assert store.totals(180, 'UTC')['estimated_energy_lifetime_kwh'] == pytest.approx(0.062)
        assert set(restored.batch.model_dump()['inputs']) == {'location', 'total_max_power_at_stc_w',
            'pmax_temperature_coefficient_pct_per_c', 'tilt_deg', 'azimuth_deg', 'noct_c'}
        await restored.stop()
    store.close()


async def test_refresh_resolves_entity_angles_and_restores_last_batch(tmp_path, monkeypatch):
    from pvyieldlens import forecast_service

    clock = [120]
    monkeypatch.setattr(forecast_service, 'time', SimpleNamespace(time=lambda: clock[0]))
    ha_requests, weather_angles = [], []
    values = {'sensor.tilt': '0', 'input_number.azimuth': '90'}

    def respond(request):
        if request.url.host == 'ha.test':
            assert request.method == 'POST' and request.url.path == '/api/template'
            assert request.headers['Authorization'] == 'Bearer saved-token'
            ids = json.loads(request.content)['variables']['entities']
            ha_requests.append(ids)
            return httpx.Response(200, json=[angle_state(entity, values[entity]) for entity in ids])
        weather_angles.append((float(request.url.params['tilt']), float(request.url.params['azimuth'])))
        clock[0] += 5
        return httpx.Response(200, json=forecast_payload(0))

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    store.save_monitoring_settings(settings(), 0, ORIGIN)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        ha = HomeAssistantClient(ORIGIN, 'saved-token', http)
        forecast = controller(store, http, prediction=ForecastSettings(
            tilt_entity='sensor.tilt', azimuth_deg=180), ha_client=lambda: ha)
        await forecast.refresh()
        view = forecast.view(180)
        assert ha_requests == [['sensor.tilt']]
        assert weather_angles == [(0, 0)]
        assert view.geometry.model_dump() == {'tilt_deg': 0, 'azimuth_deg': 180, 'read_at': 120}
        assert view.fetched_at == 125

        clock[0] = 240
        values['sensor.tilt'] = '25'
        await forecast.refresh()
        view = forecast.view(250)
        assert weather_angles[-1] == (25, 0)
        assert view.geometry.model_dump() == {'tilt_deg': 25, 'azimuth_deg': 180, 'read_at': 240}
        assert view.fetched_at == 245

        clock[0] = 360
        forecast.configure(settings(), ForecastSettings(tilt_entity='sensor.tilt',
            azimuth_entity='input_number.azimuth'), ORIGIN, LOCATION)
        await forecast.refresh()
        assert ha_requests == [['sensor.tilt'], ['sensor.tilt'], ['sensor.tilt', 'input_number.azimuth']]
        assert weather_angles == [(0, 0), (25, 0), (25, -90)]
        assert forecast.view(370).geometry.model_dump() == {'tilt_deg': 25, 'azimuth_deg': 90, 'read_at': 360}
        assert forecast.view(370).fetched_at == 365

    store.close()
    store = Store(path)
    restored = forecast_service.ForecastController(store)
    view = restored.view(370)
    assert view.geometry.model_dump() == {'tilt_deg': 25, 'azimuth_deg': 90, 'read_at': 360}
    assert view.fetched_at == 365
    assert view.today.forecast_energy_kwh == pytest.approx(89.28)
    store.close()


async def test_unavailable_entity_angle_keeps_only_usable_forecast(tmp_path):
    value = 'unavailable'
    weather_times = []
    loop = asyncio.get_running_loop()

    def respond(request):
        if request.url.host == 'ha.test':
            ids = json.loads(request.content)['variables']['entities']
            assert ids == ['sensor.tilt']
            if value is None:
                raise httpx.ConnectError('Home Assistant offline', request=request)
            return httpx.Response(200, json=[angle_state('sensor.tilt', value)])
        weather_times.append(now)
        return httpx.Response(200, json=forecast_payload(now // 86400 * 86400))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        ha = HomeAssistantClient(ORIGIN, 'saved-token', http)
        forecast = controller(store, http, prediction=ForecastSettings(
            tilt_entity='sensor.tilt', azimuth_deg=180), ha_client=lambda: ha)
        now = 120
        await forecast.refresh(now=now)
        failed = forecast.view(now)
        assert failed.status == 'unavailable'
        assert failed.fetched_at is failed.geometry is None
        assert failed.last_error == 'forecast_angle_unavailable'
        assert [issue.model_dump() for issue in failed.unavailable_angles] == [{'axis': 'tilt', 'entity_id': 'sensor.tilt'}]
        assert weather_times == []

        value, now = '25', 180
        await forecast.refresh(now=now)
        prior = forecast.view(now)
        assert prior.status == 'ready'

        value, now = None, 240
        await forecast.refresh(now=now)
        stale = forecast.view(now)
        assert forecast._next_refresh - loop.time() == pytest.approx(900, abs=0.5)
        assert stale.status == 'stale'
        assert stale.last_error == 'forecast_angle_unavailable'
        assert stale.unavailable_angles == failed.unavailable_angles
        assert stale.fetched_at == prior.fetched_at == 180
        assert stale.geometry == prior.geometry
        assert stale.today.forecast_energy_kwh == prior.today.forecast_energy_kwh == pytest.approx(89.28)
        assert weather_times == [180]

        now = 10 * 86400
        expired = forecast.view(now)
        assert expired.status == 'unavailable'
        assert expired.today.forecast_energy_kwh is None
        assert expired.intervals == ()
        assert expired.geometry is None

        value = '0'
        await forecast.refresh(now=now)
        recovered = forecast.view(now)
        assert recovered.status == 'ready'
        assert recovered.last_error is None and recovered.unavailable_angles == ()
        assert recovered.geometry.tilt_deg == 0
        assert weather_times == [180, now]
    store.close()


async def test_forecast_only_change_keeps_monitoring_revision_cursor_and_totals(tmp_path):
    from pvyieldlens.service import Service

    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(settlement_interval_minutes=1), now=0, origin=ORIGIN)
    store.add_observations(samples(), ORIGIN)
    await service.tick(60)
    before_revision, before_cursor = store.revision, store.cursor
    before_totals = store.totals(60, 'UTC')
    before_live = service.live_window
    before_days = list(map(tuple, store.db.execute('SELECT * FROM days')))
    before_observations = store.observations(0, 60, settings().entities, ORIGIN)
    service.forecast.configure(service.monitoring_settings, PREDICTION, ORIGIN, LOCATION)
    service.forecast.configure(service.monitoring_settings, PREDICTION.model_copy(update={'noct_c': 47.0}), ORIGIN, LOCATION)
    assert store.revision == before_revision
    assert store.cursor == before_cursor
    assert store.totals(60, 'UTC') == before_totals
    assert service.live_window == before_live
    assert list(map(tuple, store.db.execute('SELECT * FROM days'))) == before_days
    assert store.observations(0, 60, settings().entities, ORIGIN) == before_observations
    store.close()


@pytest.mark.parametrize('dynamic', [False, True])
async def test_manual_refresh_coalesces_with_running_request(tmp_path, dynamic):
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def respond(request):
        requests.append(request)
        if request.url.host == 'ha.test' or not dynamic:
            entered.set()
            await release.wait()
        if request.url.host == 'ha.test':
            assert json.loads(request.content)['variables']['entities'] == ['sensor.angle']
            return httpx.Response(200, json=[angle_state('sensor.angle', '25')])
        return httpx.Response(200, json=forecast_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        if dynamic:
            ha = HomeAssistantClient(ORIGIN, 'saved-token', http)
            forecast = controller(store, http, prediction=ForecastSettings(
                tilt_entity='sensor.angle', azimuth_entity='sensor.angle'), ha_client=lambda: ha)
        else:
            forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert forecast.request_refresh() is True
            refresh = asyncio.create_task(forecast.refresh(now=120))
            await asyncio.sleep(0)
            assert forecast.view(120).refreshing is True
            release.set()
            await refresh
            await asyncio.sleep(0)
            assert [request.url.path for request in requests] == (['/api/template'] if dynamic else []) + ['/v1/forecast']
            assert forecast.view(120).refreshing is False
        finally:
            await forecast.stop()
    store.close()


@pytest.mark.parametrize('field,value', [
    ('origin', 'http://new-ha.test'), ('latitude', 1.0), ('longitude', 1.0),
    ('home_timezone', 'Asia/Shanghai'), ('total_max_power_at_stc_w', 6000.0),
    ('pmax_temperature_coefficient_pct_per_c', -0.4), ('tilt_deg', 26.0),
    ('azimuth_deg', 181.0), ('noct_c', 46.0), ('tilt_entity', 'sensor.new_tilt'),
])
async def test_changed_inputs_discard_old_inflight_result(tmp_path, field, value):
    entered, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        if request.url.host == 'ha.test':
            assert json.loads(request.content)['variables']['entities'] == ['sensor.old_tilt']
            return httpx.Response(200, json=[angle_state('sensor.old_tilt', '25')])
        entered.set()
        await release.wait()
        return httpx.Response(200, json=forecast_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        if field == 'tilt_entity':
            ha = HomeAssistantClient(ORIGIN, 'saved-token', http)
            forecast = controller(store, http, prediction=ForecastSettings(
                tilt_entity='sensor.old_tilt', azimuth_deg=180), ha_client=lambda: ha)
        else:
            forecast = controller(store, http)
        refresh = asyncio.create_task(forecast.refresh(now=120))
        await asyncio.wait_for(entered.wait(), 1)
        location = LOCATION.model_copy(update={field: value}) if field in {
            'origin', 'latitude', 'longitude', 'home_timezone',
        } else LOCATION
        config = settings(**{field: value}) if field in {
            'total_max_power_at_stc_w', 'pmax_temperature_coefficient_pct_per_c',
        } else settings()
        prediction = forecast.settings.model_copy(update={field: value}) if field in {
            'tilt_deg', 'azimuth_deg', 'noct_c', 'tilt_entity',
        } else forecast.settings
        forecast.configure(config, prediction, location.origin, location)
        release.set()
        await refresh
        assert forecast.view(180).fetched_at is None
        assert store.get_meta('forecast_cache_v2') is None
    store.close()


async def test_unchanged_configuration_does_not_restart_or_refetch(tmp_path):
    requests = []
    received = asyncio.Event()

    def respond(request):
        requests.append(request)
        received.set()
        return httpx.Response(200, json=forecast_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(received.wait(), 1)
            await asyncio.sleep(0)
            before_changes = store.db.total_changes
            task = forecast._task
            forecast.configure(settings(), PREDICTION, ORIGIN, LOCATION)
            await forecast.start()
            await asyncio.sleep(0)
            assert forecast._task is task
            assert len(requests) == 1
            assert store.db.total_changes == before_changes
            assert forecast.view(120).fetched_at is not None
        finally:
            await forecast.stop()
    store.close()


async def test_success_failure_and_stale_deadlines(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from pvyieldlens import forecast_service

    clock = [0.0]
    delays = []
    scheduled = asyncio.Event()
    real_timeout = asyncio.timeout

    def timeout(delay):
        if delay is not None:
            delays.append(delay)
            scheduled.set()
        return real_timeout(None)

    def respond(request):
        if clock[0] >= 3600:
            raise httpx.ReadTimeout('weather timeout', request=request)
        clock[0] = 10.0
        return httpx.Response(200, json=forecast_payload(0))

    monkeypatch.setattr(forecast_service, 'time', SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(forecast_service.asyncio, 'timeout', timeout)
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(scheduled.wait(), 1)
            assert delays[-1] == pytest.approx(3600, abs=0.1)
            assert forecast.view(7199).status == 'ready'
            assert forecast.view(7210).status == 'stale'
            assert forecast.view(20).fetched_at == 10
            scheduled.clear()
            clock[0] = 3610
            assert forecast.request_refresh()
            await asyncio.wait_for(scheduled.wait(), 1)
            assert delays[-1] == pytest.approx(900, abs=0.1)
            assert forecast.view(3610).status == 'stale'
            assert forecast.view(3610).fetched_at == 10
            assert forecast.view(3610).last_error == 'forecast_fetch_failed'
        finally:
            await forecast.stop()
    store.close()


async def test_complete_saved_settings_fetch_forecast_automatically(tmp_path):
    from pvyieldlens.forecast_service import ForecastController

    store = Store(tmp_path / 'data.sqlite')
    store.save_monitoring_settings(settings(), 0, ORIGIN)
    store.set_meta('ha_location', LOCATION.model_dump_json())
    store.save_forecast_settings(ForecastSettings(tilt_deg=0.0, azimuth_deg=180.0))

    fetched = asyncio.Event()

    def respond(request):
        assert float(request.url.params['tilt']) == 0.0
        assert float(request.url.params['azimuth']) == 0.0
        fetched.set()
        return httpx.Response(200, json=forecast_payload(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = ForecastController(store, OpenMeteoClient(http))
        await forecast.start()
        try:
            await asyncio.wait_for(fetched.wait(), 1)
            assert forecast.view(120).fetched_at is not None
            assert forecast.batch.inputs.tilt_deg == 0.0
            assert forecast.batch.inputs.azimuth_deg == 180.0
        finally:
            await forecast.stop()
    store.close()


async def test_partial_saved_settings_wait_for_geometry_without_fetching(tmp_path):
    from pvyieldlens.forecast_service import ForecastController

    store = Store(tmp_path / 'data.sqlite')
    store.save_monitoring_settings(settings(), 0, ORIGIN)
    store.set_meta('ha_location', LOCATION.model_dump_json())
    store.save_forecast_settings(ForecastSettings(tilt_deg=0.0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: pytest.fail('Incomplete geometry should not request weather'),
    )) as http:
        forecast = ForecastController(store, OpenMeteoClient(http))
        await forecast.start()
        try:
            await forecast.refresh(now=120)
            assert not forecast.request_refresh()
            await asyncio.sleep(0)
            assert forecast.settings.tilt_deg == 0.0
            assert forecast.settings.azimuth_deg is None
            assert forecast.view(120).status == 'configuration_required'
        finally:
            await forecast.stop()
    store.close()


async def test_midnight_reclips_cache_without_network_or_new_fetched_at(tmp_path):
    requests = []
    start = datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp()
    payload = forecast_payload(start, weather_code=0)
    payload['hourly']['weather_code'][24:48] = [61] * 24
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=payload),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=start + 86300)
        before = forecast.view(start + 86300)
        after = forecast.view(start + 86400 + 100)
        assert before.days[0].day == '2026-11-13'
        assert after.days[0].day == '2026-11-14'
        assert after.today.forecast_energy_kwh == pytest.approx(89.28)
        assert after.remaining_today.forecast_energy_kwh < after.today.forecast_energy_kwh
        assert after.fetched_at == before.fetched_at == start + 86300
        assert before.days[0].weather.weather_code == 0
        assert after.days[0].weather.weather_code == 61
        assert len(requests) == 1
    store.close()


async def test_location_name_updates_do_not_invalidate_physical_cache(tmp_path):
    requests = []
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=forecast_payload(0)),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=120)
        forecast.configure(settings(), PREDICTION, ORIGIN, LOCATION.model_copy(update={'location_name': 'New name'}))
        assert forecast.view(180).fetched_at == 120
        assert forecast.view(180).today.forecast_energy_kwh == pytest.approx(89.28)
        assert HALocation.model_validate_json(store.get_meta('ha_location')).location_name == 'New name'
        assert len(requests) == 1
    store.close()


@pytest.mark.parametrize('changes', [
    {'total_max_power_at_stc_w': 6000}, {'pmax_temperature_coefficient_pct_per_c': -0.4},
    {'origin': 'http://other.test'}, {'tilt_entity': 'sensor.new_tilt'},
])
async def test_changed_inputs_hide_persisted_cache_after_restart(tmp_path, changes):
    from pvyieldlens.forecast_service import ForecastController

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    store.save_monitoring_settings(settings(), 0, ORIGIN)
    def respond(request):
        if request.url.host == 'ha.test':
            assert json.loads(request.content)['variables']['entities'] == ['sensor.old_tilt']
            return httpx.Response(200, json=[angle_state('sensor.old_tilt', '25')])
        return httpx.Response(200, json=forecast_payload(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        if 'tilt_entity' in changes:
            ha = HomeAssistantClient(ORIGIN, 'saved-token', http)
            forecast = controller(store, http, prediction=ForecastSettings(
                tilt_entity='sensor.old_tilt', azimuth_deg=180), ha_client=lambda: ha)
        else:
            forecast = controller(store, http)
        await forecast.refresh(now=120)
        assert forecast.view(180).status == 'ready'
    if 'tilt_entity' in changes:
        store.save_forecast_settings(ForecastSettings(azimuth_deg=180, **changes))
    elif 'origin' in changes:
        store.save_monitoring_settings(settings(), 180, changes['origin'])
        store.set_meta('ha_location', LOCATION.model_copy(update=changes).model_dump_json())
    else:
        store.save_monitoring_settings(settings(**changes), 180, ORIGIN)
    store.close()
    store = Store(path)
    forecast = ForecastController(store)
    assert forecast.view(180).status == 'loading'
    assert forecast.view(180).fetched_at is None
    assert forecast.view(180).intervals == ()
    assert all(day.weather is None for day in forecast.view(180).days)
    assert store.cursor == 0
    store.close()


async def test_changed_running_inputs_refresh_after_old_result_is_discarded(tmp_path):
    entered, release, received = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests = []

    async def respond(request):
        requests.append(request)
        if len(requests) == 1:
            entered.set()
            await release.wait()
        else:
            received.set()
        return httpx.Response(200, json=forecast_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(entered.wait(), 1)
            forecast.configure(settings(total_max_power_at_stc_w=6000), PREDICTION, ORIGIN, LOCATION)
            assert forecast.request_refresh()
            release.set()
            await asyncio.wait_for(received.wait(), 1)
            assert len(requests) == 2
            assert forecast.view(120).today.forecast_energy_kwh == pytest.approx(107.136)
            assert forecast.batch.inputs.total_max_power_at_stc_w == 6000
        finally:
            await forecast.stop()
    store.close()


async def test_stop_cancels_running_fetch_and_keeps_injected_client_open(tmp_path):
    entered = asyncio.Event()

    async def respond(request):
        entered.set()
        await asyncio.Event().wait()

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        await asyncio.wait_for(entered.wait(), 1)
        await forecast.stop()
        assert forecast.view(120).refreshing is False
        assert forecast.view(120).fetched_at is None
        assert store.get_meta('forecast_cache_v2') is None
        assert not http.is_closed
    store.close()


async def test_direct_refresh_failure_reschedules_sleeping_worker(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from pvyieldlens import forecast_service

    failed = False
    sleeping = asyncio.Event()
    delays = []
    real_timeout = asyncio.timeout

    def timeout(delay):
        if delay is not None:
            delays.append(delay)
            sleeping.set()
        return real_timeout(None)

    def respond(request):
        if failed:
            raise httpx.ReadTimeout('weather timeout', request=request)
        return httpx.Response(200, json=forecast_payload(0))

    monkeypatch.setattr(forecast_service, 'asyncio', SimpleNamespace(
        Event=asyncio.Event, get_running_loop=asyncio.get_running_loop,
        create_task=asyncio.create_task, current_task=asyncio.current_task,
        shield=asyncio.shield, timeout=timeout, CancelledError=asyncio.CancelledError,
    ))
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(sleeping.wait(), 1)
            assert delays[-1] == pytest.approx(3600, abs=0.1)
            sleeping.clear()
            failed = True
            await forecast.refresh(now=120)
            await asyncio.wait_for(sleeping.wait(), 1)
            assert delays[-1] == pytest.approx(900, abs=0.1)
            assert forecast.view(120).status == 'stale'
        finally:
            await forecast.stop()
    store.close()


async def test_forecast_remaining_updates_without_new_weather(tmp_path):
    from pvyieldlens.home_assistant import entity_payloads
    from pvyieldlens.service import Service

    requests = []
    payload = forecast_payload(0)
    payload['minutely_15']['global_tilted_irradiance'] = [800.0] * 57 + [0.0] * 808
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(), now=0, origin=ORIGIN)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=payload),
    )) as http:
        service.forecast = controller(store, http)
        await service.forecast.refresh(now=48000)
        before = service.snapshot(48000)
        after = service.snapshot(49200)
        assert before['forecast']['remaining_today']['forecast_energy_kwh'] == pytest.approx(2.48)
        assert after['forecast']['remaining_today']['forecast_energy_kwh'] == pytest.approx(1.24)
        assert 'days' not in before['forecast']
        assert 'intervals' not in before['forecast']
        before_payload = entity_payloads(before)['sensor.pvyieldlens_forecast_energy_remaining_today']
        after_payload = entity_payloads(after)['sensor.pvyieldlens_forecast_energy_remaining_today']
        assert before_payload['state'] == '2.48'
        assert after_payload['state'] == '1.24'
        assert before_payload['attributes']['fetched_at'] == after_payload['attributes']['fetched_at'] == 48000
        assert before_payload['attributes']['calculated_at'] == 48000
        assert after_payload['attributes']['calculated_at'] == 49200
        assert after['forecast']['today']['forecast_energy_kwh'] == before['forecast']['today']['forecast_energy_kwh'] == pytest.approx(52.08)
        assert len(requests) == 1
    store.close()


async def test_missing_minutely_interval_keeps_hourly_weather_summary(tmp_path):
    payload = forecast_payload(0, weather_code=61)
    payload['minutely_15']['global_tilted_irradiance'][49] = None
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=120)
        view = forecast.view(180)
        assert view.today.forecast_energy_kwh is None
        assert view.today.data_completeness_percent == pytest.approx(95 / 96 * 100)
        assert (view.intervals[48].start, view.intervals[48].end) == (43200, 44100)
        assert view.intervals[48].forecast_power_w is None
        assert view.days[0].weather.model_dump() == {
            'weather_code': 61, 'air_temperature_min_c': 20, 'air_temperature_max_c': 20,
            'quality': 'complete',
        }
        assert view.tomorrow.forecast_energy_kwh == pytest.approx(89.28)
        await forecast.stop()
    store.close()


async def test_correction_cache_reuses_snapshots_and_refreshes_date_context_and_n(tmp_path, monkeypatch):
    from pvyieldlens import forecast_service
    from pvyieldlens.service import Service
    from test_correction import NOW, TODAY, committed_days

    calls = []
    real_correction = forecast_service.correction_view

    def counted(*args):
        calls.append(args)
        return real_correction(*args)

    monkeypatch.setattr(forecast_service, 'correction_view', counted)
    store = Store(tmp_path / 'data.sqlite')
    config = committed_days(store, [(1000, 500), *[(0, 0)] * 5, (1000, 800), (1000, 900)])
    service = Service(store)
    requests = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=forecast_payload(TODAY)),
    )) as http:
        forecast = forecast_service.ForecastController(store, OpenMeteoClient(http))
        service.forecast = forecast
        forecast.configure(config, PREDICTION, ORIGIN, LOCATION)
        await forecast.refresh(now=NOW)
        before = service.snapshot(NOW)
        service.snapshot(NOW + 10)
        assert len(calls) == 1
        raw_batch = forecast.batch.model_dump_json()
        revision, live = store.revision, service.live_window
        forecast.configure(config, PREDICTION.model_copy(update={'pr_history_days': 30}), ORIGIN, LOCATION)
        after = service.snapshot(NOW + 20)
        assert len(calls) == 2
        assert before['forecast']['correction']['pr'] != after['forecast']['correction']['pr']
        assert after['forecast']['fetched_at'] == before['forecast']['fetched_at'] == NOW
        assert forecast.batch.model_dump_json() == raw_batch
        assert (store.revision, service.live_window) == (revision, live)
        assert len(requests) == 1
        assert forecast._next_refresh > asyncio.get_running_loop().time()
        forecast.view(TODAY + 86400 + 1)
        assert len(calls) == 3
        forecast.invalidate_correction()
        forecast.view(TODAY + 86400 + 2)
        assert len(calls) == 4
        changed = config.model_copy(update={'actual_power_entity': 'sensor.changed'})
        store.save_monitoring_settings(changed, NOW + 30, ORIGIN)
        forecast.configure(changed, forecast.settings, ORIGIN, LOCATION)
        assert forecast.view(TODAY + 86400 + 3).correction.pr is None
        assert len(calls) == 5
    store.close()


def test_correction_cache_discards_old_epoch_after_context_changes_back_without_a_view(tmp_path):
    from pvyieldlens.forecast_service import ForecastController
    from test_correction import NOW, ORIGIN, committed_days

    store = Store(tmp_path / 'data.sqlite')
    config = committed_days(store, [(1000, 900)] * 3)
    forecast = ForecastController(store)
    forecast.configure(config, PREDICTION, ORIGIN, LOCATION)
    assert forecast.view(NOW).correction.pr == pytest.approx(90)
    changed = config.model_copy(update={'actual_power_entity': 'sensor.changed'})
    store.save_monitoring_settings(changed, NOW + 1, ORIGIN)
    forecast.configure(changed, PREDICTION, ORIGIN, LOCATION)
    store.save_monitoring_settings(config, NOW + 2, ORIGIN)
    forecast.configure(config, PREDICTION, ORIGIN, LOCATION)
    assert forecast.view(NOW + 3).correction.pr is None
    store.close()
