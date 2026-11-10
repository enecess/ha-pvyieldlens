"""Local-only HA protocol simulator for integration and browser checks."""
import asyncio
import math
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse

app = FastAPI()
published = {}


def source_states(at=None):
    at = time.time() if at is None else at
    stamp = datetime.fromtimestamp(at, timezone.utc).isoformat()
    sun = 800 + 50 * math.sin(at / 45)
    return [{'entity_id': entity, 'state': str(value),
        'attributes': {'unit_of_measurement': unit, 'friendly_name': name},
        'last_changed': stamp, 'last_updated': stamp, 'last_reported': stamp}
        for entity, value, unit, name in (
            ('sensor.power', 5000 * 0.93 * sun / 1000 * 0.9, 'W', 'Solar power'),
            ('sensor.temp', 45, '°C', 'Module temperature'),
            ('sensor.sun', sun, 'W/m²', 'Plane-of-array irradiance'))]


@app.middleware('http')
async def authenticate(request: Request, call_next):
    if request.headers.get('authorization') != 'Bearer simulation-token':
        return JSONResponse({'message': 'Unauthorized'}, status_code=401)
    return await call_next(request)


@app.get('/api/config')
async def config():
    return {'time_zone': 'Asia/Shanghai'}


@app.get('/api/states')
async def states():
    return source_states()


@app.get('/api/states/{entity}')
async def state(entity: str):
    found = next((state for state in source_states() if state['entity_id'] == entity), None)
    return found if found else JSONResponse({'message':'not found'}, status_code=404)


@app.post('/api/template')
async def selected_states(request: Request):
    entities = (await request.json())['variables']['entities']
    available = {item['entity_id']: item for item in source_states()}
    return [available.get(entity) for entity in entities]


@app.get('/api/history/period/{start}')
async def history(start: str, request: Request):
    first = datetime.fromisoformat(start).timestamp()
    end = datetime.fromisoformat(request.query_params['end_time']).timestamp()
    entities = request.query_params['filter_entity_id'].split(',')
    points = [source_states(at) for at in range(int(first), int(end)+1, 10)]
    return [[state for group in points for state in group if state['entity_id']==entity] for entity in entities]


@app.post('/api/states/{entity}')
async def publish(entity: str, request: Request):
    published[entity] = await request.json()
    return {'entity_id':entity, **published[entity]}


@app.websocket('/api/websocket')
async def events(socket: WebSocket):
    await socket.accept()
    await socket.send_json({'type':'auth_required'})
    auth = await socket.receive_json()
    if auth.get('access_token') != 'simulation-token':
        await socket.send_json({'type':'auth_invalid'})
        await socket.close()
        return
    await socket.send_json({'type':'auth_ok'})
    command = await socket.receive_json()
    await socket.send_json({'type':'result','id':command['id'],'success':True,'result':None})
    while True:
        await asyncio.sleep(0.5)
        for state in source_states():
            await socket.send_json({'type':'event','id':command['id'],'event':{
                'data':{'entity_id':state['entity_id'],'new_state':state},'time_fired':state['last_updated']}})
