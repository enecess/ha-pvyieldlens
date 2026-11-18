import base64
import binascii
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator
from starlette.middleware.gzip import GZipMiddleware

from .generation import generation_view
from .home_assistant import HomeAssistantClient, source_value
from .history import HistoryPeriod, history_view
from .service import NETWORK_ERRORS, Service
from .settings import DEFAULT_NOCT_C, AmbientSite, ForecastSettings, MonitoringSettings
from .storage import Store, summarize_history


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
    monitoring_settings: MonitoringSettings
    connection: Connection | None = None
    forecast_settings: ForecastSettings

    @field_validator('forecast_settings')
    @classmethod
    def require_geometry(cls, settings: ForecastSettings) -> ForecastSettings:
        if settings.geometry_sources is None:
            raise ValueError('forecast_geometry_required')
        return settings


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
        return {'monitoring_settings': service.monitoring_settings.public() if service.monitoring_settings else None,
                'forecast_settings': service.forecast.settings.model_dump(),
                'location': service.forecast.location.model_dump() if service.forecast.location else None,
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
        return {'status': 'ok', 'configured': service.monitoring_settings is not None}

    @app.get('/api/config')
    async def get_configuration():
        async with service.lock:
            return config_response()

    @app.put('/api/config')
    async def configure(update: ConfigurationUpdate):
        previous_connection = saved_connection()
        connection = previous_connection
        if not runtime.supervisor_token and update.connection:
            token = update.connection.token.get_secret_value()
            if not token and connection and update.connection.url == connection.url:
                token = connection.token.get_secret_value()
            connection = Connection(url=update.connection.url, token=token)
        if not connection or not connection.token.get_secret_value():
            return JSONResponse({'error': 'connection_required'}, status_code=422)
        monitoring_settings = update.monitoring_settings
        estimated = monitoring_settings.module_temperature_entity is None
        location = service.forecast.location
        site = (AmbientSite(latitude=location.latitude, longitude=location.longitude)
                if estimated and location is not None and location.origin == connection.url else None)
        monitoring_settings = monitoring_settings.model_copy(update={
            'module_temperature_noct_c': update.forecast_settings.noct_c if estimated else DEFAULT_NOCT_C,
            'ambient_site': site,
        })
        monitoring_changed = service.monitoring_settings != monitoring_settings or service.origin != connection.url or connection != previous_connection
        if monitoring_changed and run_background:
            await service.stop()
        if monitoring_changed:
            await service.configure(monitoring_settings, origin=connection.url)
            if not runtime.supervisor_token:
                service.store.set_meta('connection', json.dumps({'url': connection.url, 'token': connection.token.get_secret_value()}))
        async with service.lock:
            forecast = service.forecast
            forecast.configure(service.monitoring_settings, update.forecast_settings, service.origin, forecast.location)
        if monitoring_changed or service.client is None:
            service.client = HomeAssistantClient(connection.url, connection.token.get_secret_value())
        if monitoring_changed and run_background:
            await service.start()
        return {**config_response(), 'monitoring_changed': monitoring_changed}

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
            forecast_settings = service.forecast.settings
            selected = {entity for entity in (forecast_settings.tilt_entity, forecast_settings.azimuth_entity)
                        if entity is not None} if connection == saved else set()
            entities = {}
            for state in states:
                entity = state.entity_id
                unit = state.attributes.unit_of_measurement
                angle_candidate = entity in selected or (unit == '°' and entity.startswith(('sensor.', 'number.', 'input_number.')))
                if entity.startswith('sensor.pvyieldlens_') or not (angle_candidate or entity.startswith('sensor.')):
                    continue
                row = {'entity_id': entity, 'name': state.attributes.friendly_name or entity, 'unit': unit, 'state': state.state}
                if angle_candidate:
                    row['angle_deg'] = source_value(state.state, unit, 'azimuth')
                entities[entity] = row
            for entity in sorted(selected - entities.keys()):
                entities[entity] = {'entity_id': entity, 'name': entity, 'unit': None, 'state': 'unavailable', 'angle_deg': None}
            return {'home_timezone': config.time_zone, 'location': config.location.model_dump() if config.location else None,
                    'entities': list(entities.values())}
        except NETWORK_ERRORS:
            return JSONResponse({'error': 'ha_connection_failed'}, status_code=502)
        finally:
            await client.close()

    @app.get('/api/snapshot')
    async def snapshot():
        async with service.lock:
            return service.snapshot()

    @app.get('/api/source-diagnostics')
    async def source_diagnostics():
        async with service.lock:
            client = service.client
            monitoring_settings = service.monitoring_settings
        if monitoring_settings is None:
            return {'observed_at': None, 'sources': []}
        if client is None:
            return JSONResponse({'error': 'ha_connection_failed'}, status_code=502)
        try:
            sources = monitoring_settings.ha_sources
            return await client.source_diagnostics(tuple(entity for _, entity, _ in sources),
                                                   roles=tuple(role for role, _, _ in sources))
        except NETWORK_ERRORS:
            return JSONResponse({'error': 'ha_connection_failed'}, status_code=502)

    @app.get('/api/live-series')
    async def live_series():
        async with service.lock:
            return service.live_series()

    @app.get('/api/forecast')
    async def get_forecast():
        async with service.lock:
            forecast = service.forecast
            return forecast.view(time.time()).model_dump(mode='json')

    @app.post('/api/forecast/refresh')
    async def refresh_forecast():
        async with service.lock:
            forecast = service.forecast
            if forecast.context == 'configuration_required':
                return JSONResponse({'error': 'forecast_configuration_required'}, status_code=422)
            if forecast.context == 'location_unavailable':
                return JSONResponse({'error': 'forecast_location_required'}, status_code=422)
            scheduled = forecast.request_refresh()
            return JSONResponse({'scheduled': scheduled, 'status': forecast.view(time.time()).status}, status_code=202)

    @app.get('/api/generation-data')
    async def generation_data():
        async with service.lock:
            store = service.store
            home_timezone = service.monitoring_settings.home_timezone if service.monitoring_settings else 'UTC'
            return generation_view(store, time.time(), home_timezone).model_dump(mode='json')

    @app.get('/api/history')
    async def history(period: HistoryPeriod | None = None,
                      start: float | None = Query(default=None, ge=0, allow_inf_nan=False),
                      end: float | None = Query(default=None, ge=0, allow_inf_nan=False),
                      start_date: date | None = None, end_date: date | None = None,
                      compare: bool | None = None):
        if period is not None:
            if (start is not None or end is not None
                    or period != 'custom' and (start_date is not None or end_date is not None)
                    or period == 'custom' and (start_date is None or end_date is None or compare)):
                return JSONResponse({'error': 'invalid_time_range'}, status_code=422)
            async with service.lock:
                store = service.store
                home_timezone = service.monitoring_settings.home_timezone if service.monitoring_settings else 'UTC'
                now = time.time()
                if period == 'custom':
                    assert start_date is not None and end_date is not None
                    today = datetime.fromtimestamp(now, ZoneInfo(home_timezone)).date()
                    if end_date < start_date or (end_date - start_date).days >= 90 or end_date > today:
                        return JSONResponse({'error': 'invalid_time_range'}, status_code=422)
                return history_view(store, period, now, home_timezone, start_date=start_date,
                                    end_date=end_date, compare=bool(compare)).model_dump(mode='json')
        if (start_date is not None or end_date is not None or compare is not None
                or start is None or end is None or end <= start or end - start > 90 * 86400):
            return JSONResponse({'error': 'invalid_time_range'}, status_code=422)
        async with service.lock:
            store = service.store
            rows = store.history(start, end)
        # Preserve outages by returning complete windows; the browser aggregates for display.
        return {'windows': rows, 'summary': summarize_history(rows, start, end).model_dump(mode='json'),
                'requested_range': {'start': start, 'end': end}}

    static = Path(__file__).parent / 'static'

    @app.get('/')
    async def index():
        return FileResponse(static / 'dist' / 'index.html')

    app.mount('/assets', StaticFiles(directory=static / 'dist' / 'assets', check_dir=False), name='assets')
    return app


def app_from_environment():
    runtime = Runtime(supervisor_token=os.getenv('SUPERVISOR_TOKEN'), web_password=os.getenv('PVYL_WEB_PASSWORD'),
                      data_dir=Path(os.getenv('PVYL_DATA_DIR', '/data')), ha_url=os.getenv('PVYL_HA_URL', ''),
                      ha_token=os.getenv('PVYL_HA_TOKEN', ''))
    runtime.data_dir.mkdir(parents=True, exist_ok=True)
    runtime.data_dir.chmod(0o700)
    store = Store(runtime.data_dir / 'pvyieldlens.sqlite')
    return create_app(Service(store), runtime)
