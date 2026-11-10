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
        body = {'settings': settings().model_dump(), 'connection': {'url':'http://ha.test:8123','token':'private-token'}}
        assert (await client.put('/api/config', json=body)).status_code == 200
        body['settings']['rated_power_w'] = -1
        response = await client.put('/api/config', json=body)
        assert response.status_code == 422
        assert 'private-token' not in response.text
        assert service.config.rated_power_w == 5000


async def test_csrf_and_empty_password_are_rejected(service):
    with pytest.raises(ValueError, match='web_password_required'):
        create_app(service, Runtime(), run_background=False)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin','test-pass')) as client:
        response = await client.put('/api/config', json={'settings':settings().model_dump()}, headers={'Origin':'https://evil.test'})
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

    await service.configure(settings(interval_minutes=1), now=0)
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
        body = connection if method == 'POST' else {'settings': settings(rated_power_w=10000).model_dump(), 'connection': connection}
        response = await client.request(method, path, json=body)
    assert response.status_code == 422
    assert response.json() == {'error': 'invalid_configuration', 'fields': ['url' if method == 'POST' else 'connection.url']}
    assert service.config.rated_power_w == 5000
    assert service.store.revision == 1
    assert service.origin == 'http://old-ha.test:8123'
    assert service.store.get_meta('connection') == saved
    assert service.client is None


@pytest.mark.parametrize('url', ['http://ha.test:8123', 'https://ha.test', 'http://[::1]:8123/core/', 'http://ha.test:+8123/core/'])
async def test_valid_connection_urls_remain_supported(service, url):
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app', auth=('admin', 'test-pass')) as client:
        response = await client.put('/api/config', json={'settings': settings().model_dump(), 'connection': {'url': url, 'token': 'private-token'}})
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
        body = connection if method == 'POST' else {'settings': settings(rated_power_w=10000).model_dump(), 'connection': connection}
        response = await client.request(method, path, json=body)
    assert response.status_code == 422
    assert response.json() == {'error': 'connection_required'}
    assert service.config.rated_power_w == 5000
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
            body = connection if method == 'POST' else {'settings': settings().model_dump(), 'connection': connection}
            response = await client.request(method, path, json=body)
        assert response.status_code == 200
        assert service.origin == url
        if method == 'POST':
            assert response.json()['timezone'] == 'Asia/Shanghai'
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
    await service.configure(settings(interval_minutes=1, update_seconds=1), now=120, origin=legacy_url)
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
        assert response.json()['settings']['rated_power_w'] == 5000
        assert response.json()['connection'] == {'url': '', 'token_set': False}
        assert 'private-legacy-token' not in response.text
        assert (await client.post('/api/connection', json=None)).json() == {'error': 'connection_required'}
        assert (await client.put('/api/config', json={'settings': settings(rated_power_w=10000).model_dump()})).status_code == 422
        await asyncio.sleep(0.05)
        assert service.store.cursor == 120
        assert service.store.history(120, 180) == []
        assert service.store.get_meta('connection') == saved
        assert service.config.rated_power_w == 5000
        assert service.client is None
        assert remote_requests == []
        connection = {'url': url, 'token': 'simulation-token'}
        assert (await client.post('/api/connection', json=connection)).status_code == 200
        assert remote_requests == [url, url]
        assert service.store.get_meta('connection') == saved
        response = await client.put('/api/config', json={'settings': settings().model_dump(), 'connection': connection})
        assert response.status_code == 200
        assert response.json()['connection'] == {'url': url, 'token_set': True}
        assert json.loads(service.store.get_meta('connection')) == connection
        assert service.client.base_url == url
