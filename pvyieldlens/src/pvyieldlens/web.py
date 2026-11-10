import base64
import binascii
import json
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator
from starlette.middleware.gzip import GZipMiddleware

from .home_assistant import HomeAssistantClient
from .service import NETWORK_ERRORS, Service
from .settings import Settings
from .storage import Store


@dataclass(frozen=True)
class Runtime:
    supervisor_token: str | None = field(default=None, repr=False)
    web_password: str | None = field(default=None, repr=False)
    data_dir: Path = Path('/data')
    ha_url: str = ''
    ha_token: str = field(default='', repr=False)


class Connection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str
    token: SecretStr = SecretStr('')

    @field_validator('url')
    @classmethod
    def valid_url(cls, value: str) -> str:
        try:
            parts = httpx.URL(value)
        except httpx.InvalidURL as error:
            raise ValueError('invalid_ha_url') from error
        if parts.scheme not in ('http', 'https') or not parts.host or parts.username or parts.password or parts.query or parts.fragment or (parts.port is not None and not 0 <= parts.port <= 65535):
            raise ValueError('invalid_ha_url')
        return value.rstrip('/')


class ConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    settings: Settings
    connection: Connection | None = None


def create_app(service: Service, runtime: Runtime, run_background=True) -> FastAPI:
    if not runtime.supervisor_token and not runtime.web_password:
        raise ValueError('web_password_required: set PVYL_WEB_PASSWORD')

    def saved_connection():
        if runtime.supervisor_token:
            return Connection(url='http://supervisor/core', token=runtime.supervisor_token)
        stored = service.store.get_meta('connection')
        if stored:
            try:
                return Connection.model_validate_json(stored)
            except ValidationError:
                return None
        return Connection(url=runtime.ha_url, token=runtime.ha_token) if runtime.ha_url else None

    def config_response():
        connection = saved_connection()
        return {'settings': service.config.model_dump() if service.config else None,
                'mode': 'app' if runtime.supervisor_token else 'docker',
                'connection': {'url': connection.url if connection else '',
                               'token_set': bool(connection and connection.token.get_secret_value())}}

    @asynccontextmanager
    async def lifespan(app):
        connection = saved_connection()
        if connection:
            service.client = HomeAssistantClient(connection.url, connection.token.get_secret_value())
            if run_background:
                await service.start()
        yield
        if run_background:
            await service.stop()
        service.store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware('http')
    async def authenticate(request: Request, call_next):
        if request.url.path == '/health':
            return await call_next(request)
        if runtime.supervisor_token:
            if not request.client or request.client.host != '172.30.32.2':
                return JSONResponse({'error': 'ingress_only'}, status_code=403)
        else:
            header = request.headers.get('authorization', '')
            decoded = ''
            if header.startswith('Basic '):
                try:
                    decoded = base64.b64decode(header[6:], validate=True).decode('utf-8')
                except (binascii.Error, UnicodeError):
                    pass
            if not secrets.compare_digest(decoded.encode(), ('admin:' + runtime.web_password).encode()):
                return JSONResponse({'error': 'authentication_required'}, status_code=401,
                                    headers={'WWW-Authenticate': 'Basic realm="PVYieldLens", charset="UTF-8"'})
            origin = request.headers.get('origin')
            if request.method not in ('GET', 'HEAD') and origin and urlsplit(origin).netloc != request.headers.get('host'):
                return JSONResponse({'error': 'origin_mismatch'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({'error': 'invalid_configuration',
            'fields': ['.'.join(str(part) for part in item['loc'][1:]) for item in error.errors()]}, status_code=422)

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'configured': service.config is not None}

    @app.get('/api/config')
    async def get_configuration():
        async with service.lock:
            return config_response()

    @app.put('/api/config')
    async def configure(update: ConfigurationUpdate):
        connection = saved_connection()
        if not runtime.supervisor_token and update.connection:
            token = update.connection.token.get_secret_value()
            if not token and connection and update.connection.url == connection.url:
                token = connection.token.get_secret_value()
            connection = Connection(url=update.connection.url, token=token)
        if not connection or not connection.token.get_secret_value():
            return JSONResponse({'error': 'connection_required'}, status_code=422)
        if run_background:
            await service.stop()
        await service.configure(update.settings, origin=connection.url)
        if not runtime.supervisor_token:
            service.store.set_meta('connection', json.dumps({'url': connection.url, 'token': connection.token.get_secret_value()}))
        service.client = HomeAssistantClient(connection.url, connection.token.get_secret_value())
        if run_background:
            await service.start()
        return config_response()

    @app.post('/api/connection')
    async def check_connection(connection: Connection | None = None):
        saved = saved_connection()
        if runtime.supervisor_token or connection is None:
            connection = saved
        elif not connection.token.get_secret_value() and saved and connection.url == saved.url:
            connection = Connection(url=connection.url, token=saved.token)
        if connection is None or not connection.token.get_secret_value():
            return JSONResponse({'error': 'connection_required'}, status_code=422)
        client = HomeAssistantClient(connection.url, connection.token.get_secret_value())
        try:
            config = await client.configuration()
            states = await client.states()
            return {'timezone': config.time_zone, 'entities': [
                {'entity_id': state.entity_id, 'name': state.attributes.friendly_name or state.entity_id,
                 'unit': state.attributes.unit_of_measurement, 'state': state.state}
                for state in states if state.entity_id.startswith('sensor.') and not state.entity_id.startswith('sensor.pvyieldlens_')]}
        except NETWORK_ERRORS:
            return JSONResponse({'error': 'ha_connection_failed'}, status_code=502)
        finally:
            await client.close()

    @app.get('/api/snapshot')
    async def snapshot():
        async with service.lock:
            return service.snapshot()

    @app.get('/api/history')
    async def history(start: float = Query(ge=0, allow_inf_nan=False), end: float = Query(ge=0, allow_inf_nan=False)):
        if end <= start or end - start > 90 * 86400:
            return JSONResponse({'error': 'invalid_time_range'}, status_code=422)
        async with service.lock:
            rows = service.store.history(start, end)
        # Preserve outages by returning complete windows; the browser aggregates for display.
        return {'windows': rows}

    static = Path(__file__).parent / 'static'

    @app.get('/')
    async def index():
        return FileResponse(static / 'index.html')

    app.mount('/static', StaticFiles(directory=static, check_dir=False), name='static')
    return app


def app_from_environment():
    runtime = Runtime(supervisor_token=os.getenv('SUPERVISOR_TOKEN'), web_password=os.getenv('PVYL_WEB_PASSWORD'),
                      data_dir=Path(os.getenv('PVYL_DATA_DIR', '/data')), ha_url=os.getenv('PVYL_HA_URL', ''),
                      ha_token=os.getenv('PVYL_HA_TOKEN', ''))
    runtime.data_dir.mkdir(parents=True, exist_ok=True)
    runtime.data_dir.chmod(0o700)
    store = Store(runtime.data_dir / 'pvyieldlens.sqlite')
    return create_app(Service(store), runtime)
