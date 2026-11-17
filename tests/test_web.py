import httpx
import pytest

from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from pvyieldlens.web import Runtime, create_app
from test_engine import settings


@pytest.fixture
def service(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    instance = Service(store)
    yield instance
    store.close()


async def test_standalone_requires_password_and_does_not_return_token(service):
    service.store.set_meta('connection', '{"url":"http://example.test:8123","token":"private-token"}')
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app') as client:
        assert (await client.get('/api/config')).status_code == 401
        response = await client.get('/api/config', auth=('admin', 'test-pass'))
        assert response.status_code == 200
        assert 'private-token' not in response.text
        assert response.json()['connection']['token_set'] is True


async def test_ingress_uses_real_peer_not_forwarded_header(service):
    app = create_app(service, Runtime(supervisor_token='super-secret'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('10.0.0.5', 123)), base_url='http://app') as client:
        assert (await client.get('/api/config', headers={'x-forwarded-for': '172.30.32.2'})).status_code == 403
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('172.30.32.2', 123)), base_url='http://app') as client:
        response = await client.get('/api/config')
        assert response.status_code == 200
        assert 'super-secret' not in response.text


async def test_configuration_validation_preserves_settings_and_secrets(service):
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin','test-pass')) as client:
        body = {'forecast_settings': {}, 'monitoring_settings': settings().model_dump(), 'connection': {'url':'http://ha.test:8123','token':'private-token'}}
        response = await client.put('/api/config', json=body)
        assert response.status_code == 200
        assert set(response.json()) == {'monitoring_settings', 'forecast_settings', 'location', 'mode', 'connection', 'monitoring_changed'}
        assert response.json()['monitoring_settings'] == body['monitoring_settings']
        assert (await client.get('/api/config')).json()['monitoring_settings'] == body['monitoring_settings']
        body['monitoring_settings']['total_max_power_at_stc_w'] = -1
        response = await client.put('/api/config', json=body)
        assert response.status_code == 422
        assert response.json()['fields'] == ['monitoring_settings.total_max_power_at_stc_w']
        assert 'private-token' not in response.text
        assert service.monitoring_settings.total_max_power_at_stc_w == 5000


async def test_csrf_and_empty_password_are_rejected(service):
    with pytest.raises(ValueError, match='web_password_required'):
        create_app(service, Runtime(), run_background=False)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin','test-pass')) as client:
        response = await client.put('/api/config', json={'forecast_settings': {}, 'monitoring_settings':settings().model_dump()}, headers={'Origin':'https://evil.test'})
        assert response.status_code == 403


async def test_health_exposes_no_configuration(service):
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app') as client:
        assert (await client.get('/health')).json()['status'] == 'ok'


async def test_large_history_gzip_preserves_response_authentication_and_ingress(service):
    import gzip
    import json
    from fastapi import FastAPI
    from pvyieldlens.engine import calculate
    from test_engine import samples

    await service.configure(settings(settlement_interval_minutes=1), now=0)
    for at in range(0, 6000, 60):
        service.store.settle(calculate(settings(), samples(at=at), at, at + 60), 1, 'UTC')
    app = create_app(service, Runtime(supervisor_token='private-token'), run_background=False)
    ingress = FastAPI()
    ingress.mount('/api/hassio_ingress/example', app)
    path = '/api/hassio_ingress/example/api/history?start=0&end=6000'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress, client=('172.30.32.2', 123)), base_url='http://app') as client:
        async with client.stream('GET', path, headers={'Accept-Encoding': 'gzip'}) as response:
            compressed = b''.join([part async for part in response.aiter_raw()])
            assert response.status_code == 200
            assert response.headers['content-encoding'] == 'gzip'
            assert 'Accept-Encoding' in response.headers['vary']
            assert response.headers['cache-control'] == 'no-store'
        plain = await client.get(path, headers={'Accept-Encoding': 'identity'})
    assert json.loads(gzip.decompress(compressed)) == plain.json()
    assert len(compressed) < len(plain.content)
    assert len(plain.json()['windows']) == 100
    assert all('segments' not in row for row in plain.json()['windows'])
    assert plain.json()['requested_range'] == {'start': 0, 'end': 6000}
    assert plain.json()['summary'] == pytest.approx({'start': 0, 'end': 6000, 'estimated_energy_kwh': 6.2,
                                                  'actual_energy_kwh': 5.58, 'pr': 90, 'data_completeness_percent': 100, 'valid_seconds': 6000})
    assert 'private-token' not in plain.text
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress, client=('10.0.0.5', 123)), base_url='http://app') as client:
        assert (await client.get(path, headers={'Accept-Encoding': 'gzip'})).status_code == 403


@pytest.mark.parametrize('method,path', [('POST', '/api/connection'), ('PUT', '/api/config')])
@pytest.mark.parametrize('url', ['http://ha.test:abc', 'http://ha.test:-1', 'http://ha.test:65536'])
async def test_invalid_connection_ports_preserve_configuration_and_credentials(service, method, path, url):
    await service.configure(settings(), now=0, origin='http://old-ha.test:8123')
    saved = '{"url":"http://old-ha.test:8123","token":"private-token"}'
    service.store.set_meta('connection', saved)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url='http://app', auth=('admin', 'test-pass')) as client:
        connection = {'url': url, 'token': 'replacement-token'}
        body = connection if method == 'POST' else {'forecast_settings': {}, 'monitoring_settings': settings(total_max_power_at_stc_w=10000).model_dump(), 'connection': connection}
        response = await client.request(method, path, json=body)
    assert response.status_code == 422
    assert response.json() == {'error': 'invalid_configuration', 'fields': ['url' if method == 'POST' else 'connection.url']}
    assert service.monitoring_settings.total_max_power_at_stc_w == 5000
    assert service.store.revision == 1
    assert service.origin == 'http://old-ha.test:8123'
    assert service.store.get_meta('connection') == saved
    assert service.client is None


@pytest.mark.parametrize('url', ['http://ha.test:8123', 'https://ha.test', 'http://[::1]:8123/core/', 'http://ha.test:+8123/core/'])
async def test_valid_connection_urls_remain_supported(service, url):
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        response = await client.put('/api/config', json={'forecast_settings': {}, 'monitoring_settings': settings().model_dump(), 'connection': {'url': url, 'token': 'private-token'}})
    assert response.status_code == 200
    assert response.json()['connection'] == {'url': url.rstrip('/'), 'token_set': True}
    await service.client.close()


@pytest.mark.parametrize('method,path', [('POST', '/api/connection'), ('PUT', '/api/config')])
async def test_changed_connection_requires_token_without_changing_saved_state(service, method, path):
    from test_integration import fake_server

    await service.configure(settings(), now=0, origin='http://old-ha.test:8123')
    saved = '{"url":"http://old-ha.test:8123","token":"simulation-token"}'
    service.store.set_meta('connection', saved)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with fake_server() as url, httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
            base_url='http://app', auth=('admin', 'test-pass')) as client:
        connection = {'url': url, 'token': ''}
        body = connection if method == 'POST' else {'forecast_settings': {}, 'monitoring_settings': settings(total_max_power_at_stc_w=10000).model_dump(), 'connection': connection}
        response = await client.request(method, path, json=body)
    assert response.status_code == 422
    assert response.json() == {'error': 'connection_required'}
    assert service.monitoring_settings.total_max_power_at_stc_w == 5000
    assert service.store.revision == 1
    assert service.origin == 'http://old-ha.test:8123'
    assert service.store.get_meta('connection') == saved
    assert service.client is None


@pytest.mark.parametrize('method,path', [('POST', '/api/connection'), ('PUT', '/api/config')])
async def test_same_normalized_connection_reuses_saved_token(service, method, path):
    from test_integration import fake_server

    async with fake_server() as url:
        await service.configure(settings(), now=0, origin=url)
        service.store.set_meta('connection', '{"url":"' + url + '","token":"simulation-token"}')
        app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
            connection = {'url': url + '/', 'token': ''}
            body = connection if method == 'POST' else {'forecast_settings': {}, 'monitoring_settings': settings().model_dump(), 'connection': connection}
            response = await client.request(method, path, json=body)
        assert response.status_code == 200
        assert service.origin == url
        if method == 'POST':
            assert response.json()['home_timezone'] == 'Asia/Shanghai'
        else:
            assert response.json()['connection'] == {'url': url, 'token_set': True}
            await service.client.close()


@pytest.mark.parametrize('port', ['abc', '65536'])
async def test_invalid_legacy_connection_keeps_app_reachable_until_correction(service, monkeypatch, port):
    import asyncio
    import json
    from pvyieldlens.home_assistant import HomeAssistantClient
    from test_engine import samples
    from test_integration import fake_server

    legacy_url = 'http://legacy-ha.test:' + port
    saved = json.dumps({'url': legacy_url, 'token': 'private-legacy-token'})
    await service.configure(settings(settlement_interval_minutes=1, update_interval_seconds=1), now=120, origin=legacy_url)
    service.store.add_observations(samples(at=120), origin=legacy_url)
    service.store.set_meta('connection', saved)
    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    remote_requests = []
    request = HomeAssistantClient.request

    async def record_request(client, method, path, **kwargs):
        remote_requests.append(client.base_url)
        return await request(client, method, path, **kwargs)

    monkeypatch.setattr(HomeAssistantClient, 'request', record_request)
    app = create_app(service, Runtime(web_password='test-pass'))
    async with fake_server() as url, app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        assert (await client.get('/')).status_code == 200
        response = await client.get('/api/config')
        assert response.status_code == 200
        assert response.json()['monitoring_settings']['total_max_power_at_stc_w'] == 5000
        assert response.json()['connection'] == {'url': '', 'token_set': False}
        assert 'private-legacy-token' not in response.text
        assert (await client.post('/api/connection', json=None)).json() == {'error': 'connection_required'}
        assert (await client.put('/api/config', json={'forecast_settings': {}, 'monitoring_settings': settings(total_max_power_at_stc_w=10000).model_dump()})).status_code == 422
        await asyncio.sleep(0.05)
        assert service.store.cursor == 120
        assert service.store.history(120, 180) == []
        assert service.store.get_meta('connection') == saved
        assert service.monitoring_settings.total_max_power_at_stc_w == 5000
        assert service.client is None
        assert remote_requests == []
        connection = {'url': url, 'token': 'simulation-token'}
        assert (await client.post('/api/connection', json=connection)).status_code == 200
        assert remote_requests == [url, url]
        assert service.store.get_meta('connection') == saved
        response = await client.put('/api/config', json={'forecast_settings': {}, 'monitoring_settings': settings().model_dump(), 'connection': connection})
        assert response.status_code == 200
        assert response.json()['connection'] == {'url': url, 'token_set': True}
        assert json.loads(service.store.get_meta('connection')) == connection
        assert service.client.base_url == url


async def test_invalid_forecast_preserves_all_configuration_and_secrets(service):
    from pvyieldlens.settings import ForecastSettings, HALocation

    await service.configure(settings(), now=0, origin='http://ha.test')
    before_forecast_settings = ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0)
    location = HALocation(origin=service.origin, latitude=31.23, longitude=121.47, home_timezone='UTC')
    service.forecast.configure(service.monitoring_settings, before_forecast_settings, service.origin, location)
    saved_connection = '{"url":"http://ha.test","token":"private-token"}'
    service.store.set_meta('connection', saved_connection)
    before_monitor_config = service.monitoring_settings
    before_changes = service.store.db.total_changes
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        invalid_response = await client.put('/api/config', json={
            'monitoring_settings': settings(total_max_power_at_stc_w=6000).model_dump(),
            'connection': {'url': 'http://new-ha.test', 'token': 'private-token'},
            'forecast_settings': {'enabled': True, 'tilt_deg': None, 'azimuth_deg': 360},
        })
    assert invalid_response.status_code == 422
    assert service.monitoring_settings == before_monitor_config
    assert service.store.forecast_settings() == before_forecast_settings
    assert 'private-token' not in invalid_response.text
    assert service.store.get_meta('connection') == saved_connection
    assert service.forecast.location == location
    assert service.store.revision == 1
    assert service.store.db.total_changes == before_changes
    assert service.client is None


async def test_forecast_update_requires_effective_credentials_before_writes(service):
    await service.configure(settings(), now=0, origin='http://ha.test')
    before = service.store.db.total_changes
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        response = await client.put('/api/config', json={
            'monitoring_settings': settings(total_max_power_at_stc_w=6000).model_dump(),
            'forecast_settings': {'enabled': True, 'tilt_deg': 25.0, 'azimuth_deg': 180.0},
        })
    assert response.status_code == 422
    assert response.json() == {'error': 'connection_required'}
    assert service.monitoring_settings.total_max_power_at_stc_w == 5000
    assert service.store.forecast_settings().enabled is False
    assert service.store.db.total_changes == before


async def test_forecast_only_put_keeps_running_monitoring(service, monkeypatch):
    import asyncio
    from pvyieldlens.settings import ForecastSettings, HALocation
    from test_integration import fake_server

    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    async with fake_server() as url:
        config = settings(settlement_interval_minutes=1, update_interval_seconds=60, home_timezone='Asia/Shanghai')
        await service.configure(config, now=120, origin=url)
        location = HALocation(origin=url, latitude=31.23, longitude=121.47, location_name='Home', home_timezone='Asia/Shanghai')
        service.forecast.configure(config, ForecastSettings(tilt_deg=25.0, azimuth_deg=180.0), url, location)
        service.store.set_meta('connection', '{"url":"' + url + '","token":"simulation-token"}')
        app = create_app(service, Runtime(web_password='test-pass'))
        async with app.router.lifespan_context(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                base_url='http://app', auth=('admin', 'test-pass')) as client:
            async with asyncio.timeout(2):
                while not service.connected:
                    await asyncio.sleep(0.01)
            tasks, ha_client = tuple(service.tasks), service.client
            before = service.snapshot(180)
            cursor, started_at = service.store.cursor, service.store.get_meta('started_at')
            observations = service.store.observations(120, 180, config.entities, url)
            days = list(map(tuple, service.store.db.execute('SELECT * FROM days')))
            response = await client.put('/api/config', json={'monitoring_settings': config.model_dump(),
                'connection': {'url': url + '/', 'token': ''},
                'forecast_settings': {'enabled': False, 'tilt_deg': 25.0, 'azimuth_deg': 180.0, 'noct_c': 47.0}})
            assert response.status_code == 200
            assert tuple(service.tasks) == tasks
            assert all(not task.done() for task in tasks)
            assert service.client is ha_client
            assert service._recovery_needed is False
            after = service.snapshot(180)
            for key in ('revision', 'energy_totals', 'live_window', 'sources', 'latest_settled_window', 'connected', 'calculated_at'):
                assert after[key] == before[key]
            assert service.store.cursor == cursor
            assert service.store.get_meta('started_at') == started_at
            assert list(map(tuple, service.store.db.execute('SELECT * FROM days'))) == days
            assert service.store.observations(120, 180, config.entities, url) == observations
            assert response.json()['location'] == location.model_dump()
            assert response.json()['forecast_settings']['noct_c'] == 47.0


async def test_connection_preview_does_not_replace_active_forecast_location(service):
    from pvyieldlens.settings import ForecastSettings, HALocation
    from test_integration import fake_server

    await service.configure(settings(), now=0, origin='http://active-ha.test')
    location = HALocation(origin=service.origin, latitude=0.0, longitude=0.0, location_name='Active', home_timezone='UTC')
    service.forecast.configure(service.monitoring_settings, ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0), service.origin, location)
    saved = '{"url":"http://active-ha.test","token":"private-token"}'
    service.store.set_meta('connection', saved)
    changes = service.store.db.total_changes
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with fake_server() as url, httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
            base_url='http://app', auth=('admin', 'test-pass')) as client:
        response = await client.post('/api/connection', json={'url': url, 'token': 'simulation-token'})
        assert response.status_code == 200
        assert response.json()['location'] == {'origin': url, 'latitude': 31.23, 'longitude': 121.47,
                                              'location_name': 'Home', 'home_timezone': 'Asia/Shanghai'}
        assert len(response.json()['entities']) == 3
        assert service.forecast.location == location
        assert service.store.get_meta('ha_location') == location.model_dump_json()
        assert service.store.get_meta('connection') == saved
        assert service.store.db.total_changes == changes
        assert (await client.get('/api/config')).json()['location'] == location.model_dump()


async def test_forecast_read_and_refresh_are_authenticated_and_nonblocking(service, monkeypatch):
    import asyncio
    from forecast_fixtures import hourly_payload
    from pvyieldlens.forecast_service import ForecastController
    from pvyieldlens.open_meteo import OpenMeteoClient
    from pvyieldlens.settings import ForecastSettings, HALocation

    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 180)
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def weather_response(request):
        requests.append(request)
        entered.set()
        await release.wait()
        return httpx.Response(200, json=hourly_payload(0, weather_code=61))

    await service.configure(settings(), now=0, origin='http://ha.test')
    async with httpx.AsyncClient(transport=httpx.MockTransport(weather_response)) as weather_http:
        service.forecast = ForecastController(service.store, OpenMeteoClient(weather_http))
        service.forecast.configure(service.monitoring_settings, ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0),
            service.origin, HALocation(origin=service.origin, latitude=0.0, longitude=0.0, home_timezone='UTC'))
        app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app') as client:
            try:
                assert (await client.get('/api/forecast')).status_code == 401
                assert (await client.post('/api/forecast/refresh')).status_code == 401
                assert requests == []
                auth = ('admin', 'test-pass')
                trigger = await asyncio.wait_for(client.post('/api/forecast/refresh', auth=auth), 0.5)
                assert trigger.status_code == 202
                assert trigger.json() == {'scheduled': True, 'status': 'loading'}
                await asyncio.wait_for(entered.wait(), 1)
                async with service.lock:
                    forecast = await asyncio.wait_for(client.get('/api/forecast', auth=auth), 0.5)
                    repeated = await asyncio.wait_for(client.post('/api/forecast/refresh', auth=auth), 0.5)
                assert forecast.status_code == 200
                assert forecast.json()['status'] == 'loading'
                assert forecast.json()['refreshing'] is True
                assert len(forecast.json()['days']) == 7
                assert forecast.json()['intervals'] == []
                assert repeated.status_code == 202
                assert repeated.json() == {'scheduled': True, 'status': 'loading'}
                snapshot = await asyncio.wait_for(client.get('/api/snapshot', auth=auth), 0.5)
                assert snapshot.json()['forecast']['refreshing'] is True
                assert 'days' not in snapshot.json()['forecast']
                assert 'intervals' not in snapshot.json()['forecast']
                assert 'weather_samples' not in snapshot.json()['forecast']
                assert len(requests) == 1
                assert (await client.post('/api/forecast/refresh', auth=auth, headers={'Origin': 'http://evil.test'})).status_code == 403
                release.set()
                async with asyncio.timeout(1):
                    while service.forecast.view(180).refreshing:
                        await asyncio.sleep(0)
                ready = await client.get('/api/forecast', auth=auth)
                assert ready.json()['today']['forecast_energy_kwh'] == pytest.approx(89.28)
                assert ready.json()['remaining_today']['forecast_energy_kwh'] == pytest.approx(89.094)
                assert ready.json()['fetched_at'] == 180
                assert ready.json()['calculated_at'] == 180
                assert len(ready.json()['intervals']) == 168
                assert ready.json()['days'][0]['weather'] == {
                    'weather_code': 61, 'air_temperature_min_c': 20, 'air_temperature_max_c': 20, 'quality': 'complete',
                }
                assert 'weather_samples' not in ready.json()
                assert 'weather' not in ready.json()['today']
                assert 'private-token' not in ready.text
            finally:
                await service.forecast.stop()


async def test_forecast_refresh_reports_disabled_and_location_required(service):
    from pvyieldlens.settings import ForecastSettings

    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        config = await client.get('/api/config')
        assert config.json()['forecast_settings'] == {'enabled': False, 'tilt_deg': None, 'azimuth_deg': None, 'noct_c': 45.0}
        assert config.json()['location'] is None
        disabled = await client.post('/api/forecast/refresh')
        assert disabled.status_code == 409
        assert disabled.json() == {'error': 'forecast_disabled'}
        service.forecast.configure(None, ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0), '', None)
        missing = await client.post('/api/forecast/refresh')
        assert missing.status_code == 422
        assert missing.json() == {'error': 'forecast_location_required'}
        forecast = await client.get('/api/forecast')
        assert forecast.json()['status'] == 'location_unavailable'
        assert forecast.json()['today'] is None


async def test_history_summary_uses_committed_revisions_without_changing_monitoring(service):
    import sqlite3
    from pvyieldlens.home_assistant import entity_payloads
    from test_engine import samples

    await service.configure(settings(settlement_interval_minutes=1), now=0)
    service.store.add_observations(samples())
    await service.tick(60)
    await service.configure(settings(settlement_interval_minutes=1, total_max_power_at_stc_w=10000), now=60)
    service.store.add_observations(samples(at=60))
    await service.tick(120)
    service.store.add_observations(samples(at=120))
    await service.tick(180.25)
    before = service.snapshot(180.25)
    payloads = entity_payloads(before)
    original_ids = ('settled_estimated_power', 'settled_actual_power', 'settled_pr', 'estimated_energy_today', 'estimated_energy_lifetime',
                    'live_estimated_power', 'live_actual_power', 'live_pr', 'live_optimizable_power')
    original_payloads = {name: payloads['sensor.pvyieldlens_' + name] for name in original_ids}
    assert len(original_payloads) == 9
    assert original_payloads['settled_estimated_power']['state'] == '7440.0'
    assert original_payloads['settled_pr']['state'] == '45.0'
    service.store.add_observations(samples(at=60, sun=100))
    service.store.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                                   if action == sqlite3.SQLITE_READ and table in ('window_segments', 'observations')
                                   else sqlite3.SQLITE_OK)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app') as client:
        assert (await client.get('/api/history?start=0&end=180.25')).status_code == 401
        auth = ('admin', 'test-pass')
        complete = await client.get('/api/history?start=0&end=180.25', auth=auth)
        assert complete.status_code == 200
        complete_body = complete.json()
        assert complete_body['requested_range'] == {'start': 0, 'end': 180.25}
        assert complete_body['summary'] == pytest.approx({'start': 0, 'end': 180,
            'estimated_energy_kwh': 0.31, 'actual_energy_kwh': 0.1674, 'pr': 54, 'data_completeness_percent': 100, 'valid_seconds': 180})
        assert [row['revision'] for row in complete_body['windows']] == [1, 2, 2]
        assert [row['estimated_energy_wh'] for row in complete_body['windows']] == pytest.approx([62, 124, 124])
        partial = await client.get('/api/history?start=30.5&end=150.5', auth=auth)
        assert partial.status_code == 200
        partial_body = partial.json()
        assert partial_body['requested_range'] == {'start': 30.5, 'end': 150.5}
        assert partial_body['windows'] == complete_body['windows']
        assert partial_body['summary'] == pytest.approx({'start': 60, 'end': 120,
            'estimated_energy_kwh': 0.124, 'actual_energy_kwh': 0.0558, 'pr': 45, 'data_completeness_percent': 100, 'valid_seconds': 60})
        empty = await client.get('/api/history?start=30.5&end=50.5', auth=auth)
        assert len(empty.json()['windows']) == 1
        assert empty.json()['summary'] == {'start': None, 'end': None, 'estimated_energy_kwh': None,
                                         'actual_energy_kwh': None, 'pr': None, 'data_completeness_percent': None, 'valid_seconds': 0}
        assert (await client.get('/api/history?start=60&end=60', auth=auth)).status_code == 422
        assert (await client.get('/api/history?start=nan&end=180', auth=auth)).status_code == 422
        assert (await client.get('/api/history?start=0&end=inf', auth=auth)).status_code == 422
    after = service.snapshot(180.25)
    for channel in ('energy_totals', 'latest_settled_window', 'live_window', 'revision'):
        assert after[channel] == before[channel]
    after_payloads = entity_payloads(after)
    assert {name: after_payloads['sensor.pvyieldlens_' + name] for name in original_ids} == original_payloads
    assert after['energy_totals']['estimated_energy_lifetime_kwh'] == pytest.approx(0.31)
    assert after['latest_settled_window']['pr'] == pytest.approx(45)


@pytest.mark.parametrize('period,count', [('today', 0), ('24h', 0), ('7d', 7), ('30d', 30)])
async def test_history_presets_use_service_timezone_and_consistent_settlement(service, monkeypatch, period, count):
    from test_history import settle_cross_midnight

    start, midnight, end = settle_cross_midnight(service.store)
    service.monitoring_settings = settings(home_timezone='Asia/Shanghai')
    monkeypatch.setattr('pvyieldlens.web.time.time', lambda: end)
    before = service.snapshot(end)
    original = service.store.history(start, end)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app') as client:
        assert (await client.get('/api/history?period=' + period)).status_code == 401
        response = await client.get('/api/history?period=' + period, auth=('admin', 'test-pass'))
        assert response.status_code == 200
        body = response.json()
        assert body['period'] == period
        assert body['home_timezone'] == 'Asia/Shanghai'
        assert body['today'] == '2026-11-11'
        assert body['requested_range']['end'] == end
        assert body['boundary_unavailable'] is False
        assert len(body['days']) == count
        assert body['summary']['actual_energy_kwh'] == pytest.approx(0.06 if period == 'today' else 0.07)
        if period == 'today':
            assert body['requested_range']['start'] == midnight
            assert body['windows'][0]['source_start'] == start
    assert service.store.history(start, end) == original
    assert service.snapshot(end) == before


@pytest.mark.parametrize('query', [
    '', 'period=week', 'period=', 'period=today&start=0&end=60', 'period=7d&start=0', 'period=30d&end=60',
    'start=0', 'end=60', 'start=-1&end=60', 'start=60&end=60', 'start=70&end=60',
    'start=nan&end=60', 'start=0&end=inf', 'start=0&end=7776001', 'start=oops&end=60',
])
async def test_history_rejects_mixed_missing_or_invalid_parameters(service, query):
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app',
                                 auth=('admin', 'test-pass')) as client:
        assert (await client.get('/api/history?' + query)).status_code == 422


async def test_numeric_history_and_snapshot_hide_internal_cross_day_allocations(service):
    from test_history import settle_cross_midnight

    start, midnight, end = settle_cross_midnight(service.store)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app',
                                 auth=('admin', 'test-pass')) as client:
        response = await client.get(f'/api/history?start={midnight}&end={end}')
        body = response.json()
        assert set(body) == {'windows', 'summary', 'requested_range'}
        assert body['windows'][0]['start'] == start
        assert body['summary']['actual_energy_kwh'] is None
        assert 'day_allocations' not in response.text
        assert 'source_start' not in response.text
        assert 'day_allocations' not in service.snapshot(end)['latest_settled_window']
        assert service.store.latest_settled_window() == body['windows'][0]


async def test_snapshot_refreshes_active_location_with_forecast_disabled(service):
    from pvyieldlens.settings import HALocation
    from test_integration import fake_server

    await service.configure(settings(), now=0, origin='http://active-ha.test')
    service.store.set_meta('connection', '{"url":"http://active-ha.test","token":"private-token"}')
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        assert (await client.get('/api/snapshot')).json()['location'] is None
        location = HALocation(origin=service.origin, latitude=0.0, longitude=0.0, location_name='Active', home_timezone='UTC')
        for current in (location, location.model_copy(update={'location_name': 'Renamed'}),
                        location.model_copy(update={'latitude': -33.86, 'longitude': 151.21, 'home_timezone': 'Australia/Sydney'}), None):
            service.forecast.configure(service.monitoring_settings, service.forecast.settings, service.origin, current)
            response = await client.get('/api/snapshot')
            assert response.status_code == 200
            assert response.json()['location'] == (current.model_dump() if current else None)
            assert response.json()['forecast']['status'] == 'disabled'
            assert 'days' not in response.json()['forecast'] and 'intervals' not in response.json()['forecast']
            assert 'private-token' not in response.text
        service.forecast.configure(service.monitoring_settings, service.forecast.settings, service.origin, location)
        async with fake_server() as url:
            preview = await client.post('/api/connection', json={'url': url, 'token': 'simulation-token'})
            assert preview.status_code == 200 and preview.json()['location']['origin'] == url
        assert (await client.get('/api/snapshot')).json()['location'] == location.model_dump()
        await service.configure(service.monitoring_settings, origin='http://new-active-ha.test')
        assert (await client.get('/api/snapshot')).json()['location'] is None


@pytest.mark.parametrize(('change', 'monitoring_changed'), [
    ('forecast', False), ('same_token', False), ('monitoring_settings', True), ('url', True), ('token', True),
])
async def test_save_reports_effective_monitoring_change(service, change, monitoring_changed):
    await service.configure(settings(), now=0, origin='http://active-ha.test')
    service.store.set_meta('connection', '{"url":"http://active-ha.test","token":"private-token"}')
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    update = {'monitoring_settings': service.monitoring_settings.model_dump(),
              'connection': {'url': service.origin + '/', 'token': ''},
              'forecast_settings': {'enabled': False, 'noct_c': 47}}
    if change == 'same_token':
        update['connection']['token'] = 'private-token'
    elif change == 'monitoring_settings':
        update['monitoring_settings']['update_interval_seconds'] = 2
    elif change == 'url':
        update['connection'] = {'url': 'http://new-ha.test', 'token': 'replacement-token'}
    elif change == 'token':
        update['connection']['token'] = 'replacement-token'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        response = await client.put('/api/config', json=update)
        assert response.status_code == 200
        assert response.json()['monitoring_changed'] is monitoring_changed
        assert 'private-token' not in response.text and 'replacement-token' not in response.text
    await service.client.close()


async def test_full_configuration_requires_forecast_settings_without_partial_writes(service):
    await service.configure(settings(), now=0)
    before = service.store.db.total_changes
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        response = await client.put('/api/config', json={'monitoring_settings': settings(total_max_power_at_stc_w=6000).model_dump()})
    assert response.status_code == 422
    assert response.json() == {'error': 'invalid_configuration', 'fields': ['forecast_settings']}
    assert service.monitoring_settings.total_max_power_at_stc_w == 5000
    assert service.store.db.total_changes == before


async def test_source_diagnostics_requires_authentication_and_returns_unconfigured_empty(service):
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app') as client:
        assert (await client.get('/api/source-diagnostics')).status_code == 401
        response = await client.get('/api/source-diagnostics', auth=('admin', 'test-pass'))
    assert response.status_code == 200
    assert response.json() == {'observed_at': None, 'sources': []}
    assert response.headers['Cache-Control'] == 'no-store'


async def test_source_diagnostics_reads_leave_service_store_and_outputs_unchanged(service):
    from pvyieldlens.home_assistant import HomeAssistantClient
    from test_engine import samples
    from test_home_assistant import state

    await service.configure(settings(settlement_interval_minutes=1), now=0, origin='http://ha.test')
    service.store.add_observations(samples(at=0), origin=service.origin)
    await service.ingest([state(changed='1970-01-01T00:01:00+00:00', reported='1970-01-01T00:01:10+00:00')])
    await service.tick(now=120)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'observed_at': 121.25, 'sources': [
            {'state': '2.5', 'unit': 'kW', 'reported_at': 121.0}, None, None,
        ]})

    observation_count = service.store.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
    cursor = service.store.cursor
    metadata = list(service.store.db.execute('SELECT * FROM metadata ORDER BY key'))
    changes = service.store.db.total_changes
    snapshot = service.snapshot(now=120)
    live_series = service.live_series(now=120)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as ha_http:
        service.client = HomeAssistantClient('http://ha.test', 'secret', http=ha_http)
        app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app',
                                     auth=('admin', 'test-pass')) as client:
            for _ in range(2):
                response = await client.get('/api/source-diagnostics')
                assert response.status_code == 200
                assert response.json() == {'observed_at': 121.25, 'sources': [
                    {'entity_id': 'sensor.power', 'state': '2.5', 'unit': 'kW', 'reported_at': 121, 'valid': True},
                    {'entity_id': 'sensor.temp', 'state': 'unavailable', 'unit': None, 'reported_at': None, 'valid': False},
                    {'entity_id': 'sensor.sun', 'state': 'unavailable', 'unit': None, 'reported_at': None, 'valid': False},
                ]}
    assert service.store.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == observation_count
    assert service.store.cursor == cursor
    assert list(service.store.db.execute('SELECT * FROM metadata ORDER BY key')) == metadata
    assert service.store.db.total_changes == changes
    assert service.snapshot(now=120) == snapshot
    assert service.live_series(now=120) == live_series
    assert len(requests) == 2
    assert all(request.method == 'POST' and request.url.path == '/api/template' for request in requests)
    assert not any(request.method == 'POST' and '/states/' in request.url.path for request in requests)


async def test_source_diagnostics_uses_captured_configuration_without_locking_network_io(service):
    import json
    from pvyieldlens.home_assistant import HomeAssistantClient

    await service.configure(settings(), now=0, origin='http://ha.test')
    requests = []

    async def respond(request):
        assert not service.lock.locked()
        async with service.lock:
            service.client = None
            service.monitoring_settings = settings(actual_power_entity='sensor.replacement')
        requests.append(request)
        return httpx.Response(200, json={'observed_at': 110.0, 'sources': [None, None, None]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as ha_http:
        service.client = HomeAssistantClient('http://ha.test', 'secret', http=ha_http)
        app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app',
                                     auth=('admin', 'test-pass')) as client:
            response = await client.get('/api/source-diagnostics')
    assert response.status_code == 200
    assert [row['entity_id'] for row in response.json()['sources']] == ['sensor.power', 'sensor.temp', 'sensor.sun']
    assert len(requests) == 1
    assert json.loads(requests[0].content)['variables']['entities'] == ['sensor.power', 'sensor.temp', 'sensor.sun']


@pytest.mark.parametrize('failure', ['unavailable_client', 'network', 'http', 'validation'])
async def test_source_diagnostics_ha_failures_return_bad_gateway(service, failure):
    from pvyieldlens.home_assistant import HomeAssistantClient

    await service.configure(settings(), now=0, origin='http://ha.test')

    def respond(request):
        if failure == 'network':
            raise httpx.ConnectError('offline', request=request)
        if failure == 'http':
            return httpx.Response(503)
        return httpx.Response(200, json={'observed_at': None, 'sources': [None, None, None]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as ha_http:
        if failure != 'unavailable_client':
            service.client = HomeAssistantClient('http://ha.test', 'secret', http=ha_http)
        app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app',
                                     auth=('admin', 'test-pass')) as client:
            response = await client.get('/api/source-diagnostics')
    assert response.status_code == 502
    assert response.json() == {'error': 'ha_connection_failed'}
