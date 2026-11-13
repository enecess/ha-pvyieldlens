import asyncio
import socket
import time
from contextlib import asynccontextmanager

import pytest
import uvicorn

from fake_ha import app, published
from pvyieldlens.home_assistant import HomeAssistantClient
from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from test_engine import settings


@asynccontextmanager
async def fake_server(application=app, lifespan='off'):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, log_level='critical', ws='websockets-sansio', lifespan=lifespan))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    async with asyncio.timeout(10):
        while not server.started:
            await asyncio.sleep(0.01)
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)


async def test_real_rest_websocket_collection_and_thirteen_outputs(tmp_path):
    published.clear()
    async with fake_server() as url:
        store = Store(tmp_path / 'data.sqlite')
        service = Service(store, HomeAssistantClient(url, 'simulation-token'))
        await service.configure(settings(interval_minutes=1, timezone='Asia/Shanghai', update_seconds=1), now=time.time()-65)
        await service.start()
        async with asyncio.timeout(15):
            while len(published) != 13 or published['sensor.pvyieldlens_realtime_pr']['state'] == 'unavailable':
                await asyncio.sleep(0.1)
        assert float(published['sensor.pvyieldlens_realtime_pr']['state']) == pytest.approx(90, abs=0.1)
        assert all(payload['state'] == 'unavailable' for entity, payload in published.items() if entity.startswith('sensor.pvyieldlens_forecast_'))
        assert service.snapshot()['connected']
        assert service.snapshot()['energy']['total_kwh'] > 0
        await service.stop()
        assert all(payload['state'] == 'unavailable' for payload in published.values())
        store.close()


async def test_websocket_handshake_has_a_bounded_timeout():
    from fastapi import FastAPI, WebSocket
    stalled = FastAPI()

    @stalled.websocket('/api/websocket')
    async def socket_handler(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json({'type':'auth_required'})
        await websocket.receive_json()
        await websocket.receive()

    async with fake_server(stalled) as url:
        client = HomeAssistantClient(url, 'simulation-token')
        client.handshake_timeout = 0.05
        started = time.monotonic()
        async with asyncio.timeout(2):
            with pytest.raises(TimeoutError):
                await anext(client.events())
        assert time.monotonic() - started < 1
        await client.close()


async def test_debug_logging_does_not_include_websocket_access_token(monkeypatch, caplog):
    import logging
    from pvyieldlens.__main__ import main
    monkeypatch.setenv('PVYL_LOG_LEVEL','debug')
    monkeypatch.setattr('pvyieldlens.__main__.uvicorn.run', lambda *args, **kwargs: None)
    caplog.set_level(logging.DEBUG)
    main()
    async with fake_server() as url:
        client = HomeAssistantClient(url, 'simulation-token')
        stream = client.events()
        await anext(stream)
        await stream.aclose()
        await client.close()
    transport_logs = '\n'.join(record.getMessage() for record in caplog.records if record.name.startswith('websockets'))
    assert 'simulation-token' not in transport_logs


async def test_forecast_outputs_republish_after_ha_reconnect_and_shutdown(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import httpx
    from fastapi import FastAPI, WebSocket
    from forecast_fixtures import hourly_payload
    from pvyieldlens.forecast_service import ForecastController
    from pvyieldlens.open_meteo import OpenMeteoClient
    from pvyieldlens.settings import ForecastSettings, HALocation

    disconnect, reconnected = asyncio.Event(), asyncio.Event()
    reconnecting_ha = FastAPI()
    connections = 0

    @reconnecting_ha.websocket('/api/websocket')
    async def events(websocket: WebSocket):
        nonlocal connections
        await websocket.accept()
        await websocket.send_json({'type': 'auth_required'})
        assert (await websocket.receive_json())['access_token'] == 'simulation-token'
        await websocket.send_json({'type': 'auth_ok'})
        command = await websocket.receive_json()
        await websocket.send_json({'type': 'result', 'id': command['id'], 'success': True, 'result': None})
        connections += 1
        if connections == 1:
            await disconnect.wait()
            await websocket.close()
        else:
            reconnected.set()
            await websocket.receive()

    reconnecting_ha.include_router(app.router)
    published.clear()
    requests = []
    today = datetime.now(ZoneInfo('Asia/Shanghai')).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    async with fake_server(reconnecting_ha) as url, httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=hourly_payload(today)),
    )) as weather_http:
        store = Store(tmp_path / 'data.sqlite')
        service = Service(store, HomeAssistantClient(url, 'simulation-token'))
        await service.configure(settings(interval_minutes=1, timezone='Asia/Shanghai', update_seconds=1),
            now=time.time() - 65, origin=url)
        service.forecast = ForecastController(store, OpenMeteoClient(weather_http))
        service.forecast.configure(service.config, ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0),
            url, HALocation(origin=url, latitude=31.23, longitude=121.47, location_name='Home', timezone='Asia/Shanghai'))
        await service.start()
        try:
            async with asyncio.timeout(5):
                while len(published) != 13 or published['sensor.pvyieldlens_forecast_energy_today']['state'] == 'unavailable':
                    await asyncio.sleep(0.01)
            fetched_at = published['sensor.pvyieldlens_forecast_energy_today']['attributes']['fetched_at']
            assert float(published['sensor.pvyieldlens_forecast_energy_today']['state']) == pytest.approx(89.28)
            assert float(published['sensor.pvyieldlens_realtime_pr']['state']) == pytest.approx(90, abs=0.1)
            published.clear()
            disconnect.set()
            await asyncio.wait_for(reconnected.wait(), 2)
            async with asyncio.timeout(5):
                while len(published) != 13:
                    await asyncio.sleep(0.01)
            assert connections == 2
            assert service.snapshot()['connected'] is True
            assert float(published['sensor.pvyieldlens_forecast_energy_today']['state']) == pytest.approx(89.28)
            assert published['sensor.pvyieldlens_forecast_energy_today']['attributes']['fetched_at'] == fetched_at
            assert len(requests) == 1
        finally:
            await service.stop()
        assert len(published) == 13
        assert all(payload['state'] == 'unavailable' for payload in published.values())
        assert service.tasks == []
        assert service.forecast._task is None
        store.close()
