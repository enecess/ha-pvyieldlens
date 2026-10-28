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


async def test_real_rest_websocket_collection_and_nine_outputs(tmp_path):
    published.clear()
    async with fake_server() as url:
        store = Store(tmp_path / 'data.sqlite')
        service = Service(store, HomeAssistantClient(url, 'simulation-token'))
        await service.configure(settings(interval_minutes=1, timezone='Asia/Shanghai', update_seconds=1), now=time.time()-65)
        await service.start()
        async with asyncio.timeout(15):
            while len(published) != 9 or published['sensor.pvyieldlens_realtime_pr']['state'] == 'unavailable':
                await asyncio.sleep(0.1)
        assert float(published['sensor.pvyieldlens_realtime_pr']['state']) == pytest.approx(90, abs=0.1)
        assert service.snapshot()['connected']
        assert service.snapshot()['energy']['total_kwh'] > 0
        total = service.snapshot()['energy']['total_kwh']
        await service.recover()
        assert service.snapshot()['energy']['total_kwh'] >= total
        await service.stop()
        assert published['sensor.pvyieldlens_realtime_pr']['state'] == 'unavailable'
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
