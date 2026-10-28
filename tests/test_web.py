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
