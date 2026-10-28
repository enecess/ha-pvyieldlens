import asyncio
import json
import math
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import AwareDatetime, BaseModel, Field, JsonValue, TypeAdapter
from websockets.asyncio.client import connect

from .engine import Observation


class StateAttributes(BaseModel):
    unit_of_measurement: str | None = None
    friendly_name: str | None = None


class HAState(BaseModel):
    entity_id: str
    state: str
    attributes: StateAttributes = Field(default_factory=StateAttributes)
    last_updated: AwareDatetime
    last_changed: AwareDatetime
    last_reported: AwareDatetime | None = None


class HAConfig(BaseModel):
    time_zone: str


class EventData(BaseModel):
    entity_id: str
    new_state: HAState | None = None


class Event(BaseModel):
    data: EventData
    time_fired: AwareDatetime


class WSMessage(BaseModel):
    type: str
    success: bool | None = None
    event: Event | None = None


def parse_state(state: HAState, role: Literal['power', 'temperature', 'irradiance'], historical=False) -> list[Observation]:
    value = None
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", state.state):
        number = float(state.state)
        unit = (state.attributes.unit_of_measurement or '').replace('²', '2').replace('^', '').replace(' ', '')
        if math.isfinite(number):
            if role == 'power' and unit in ('W', 'kW') and number >= 0:
                value = number * (1000 if unit == 'kW' else 1)
            elif role == 'irradiance' and unit in ('W/m2', 'kW/m2') and number >= 0:
                value = number * (1000 if unit == 'kW/m2' else 1)
            elif role == 'temperature' and unit in ('°C', '°F', 'K'):
                value = (number-32) * 5/9 if unit == '°F' else number-273.15 if unit == 'K' else number
    if value is not None and not math.isfinite(value):
        value = None
    at = state.last_updated.timestamp()
    points = [Observation(state.entity_id, at, value, at)]
    if not historical and state.last_reported and state.last_reported.timestamp() > at:
        points.append(Observation(state.entity_id, state.last_reported.timestamp(), value, state.last_reported.timestamp()))
    return points


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip('/')
        parts = urlsplit(self.base_url)
        self.websocket_url = urlunsplit(('wss' if parts.scheme == 'https' else 'ws', parts.netloc,
                                        parts.path + ('/websocket' if parts.hostname == 'supervisor' else '/api/websocket'), '', ''))
        self.token = token
        self.http = http or httpx.AsyncClient(timeout=20, trust_env=False)
        self._owns_http = http is None

    async def close(self):
        if self._owns_http:
            await self.http.aclose()

    async def request(self, method: str, path: str, **kwargs):
        response = await self.http.request(method, self.base_url + '/api/' + path,
                                           headers={'Authorization': 'Bearer ' + self.token}, **kwargs)
        response.raise_for_status()
        return response.json()

    async def configuration(self) -> HAConfig:
        return HAConfig.model_validate(await self.request('GET', 'config'))

    async def states(self, entities: tuple[str, ...] | None = None) -> list[HAState]:
        if entities is None:
            return TypeAdapter(list[HAState]).validate_python(await self.request('GET', 'states'))
        states = []
        for entity in entities:
            response = await self.http.get(self.base_url + '/api/states/' + entity,
                                          headers={'Authorization': 'Bearer ' + self.token})
            if response.status_code == 404:
                now = datetime.now(timezone.utc)
                states.append(HAState(entity_id=entity, state='unavailable', last_changed=now, last_updated=now))
            else:
                response.raise_for_status()
                states.append(HAState.model_validate(response.json()))
        return states

    async def history(self, entities: list[str], start: float, end: float) -> list[HAState]:
        stamp = datetime.fromtimestamp(start, timezone.utc).isoformat()
        result = TypeAdapter(list[list[HAState]]).validate_python(await self.request('GET', 'history/period/' + stamp, params={
            'filter_entity_id': ','.join(entities), 'end_time': datetime.fromtimestamp(end, timezone.utc).isoformat(),
            'significant_changes_only': '0',
        }))
        # Recorder may synthesize an initial state at the query boundary.
        return [state.model_copy(update={'last_updated': state.last_changed})
                if index == 0 and state.last_updated.timestamp() == start else state
                for group in result for index, state in enumerate(group)
                if not (index == 0 and state.last_updated.timestamp() == start and state.last_changed.timestamp() >= start)]

    async def events(self):
        async with connect(self.websocket_url, open_timeout=20, max_size=8_388_608, proxy=None) as socket:
            message = WSMessage.model_validate_json(await socket.recv())
            if message.type != 'auth_required':
                raise ValueError('ha_protocol_error')
            await socket.send(json.dumps({'type': 'auth', 'access_token': self.token}))
            message = WSMessage.model_validate_json(await socket.recv())
            if message.type != 'auth_ok':
                raise ValueError('ha_auth_failed')
            await socket.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
            message = WSMessage.model_validate_json(await socket.recv())
            if message.type != 'result' or not message.success:
                raise ValueError('ha_subscription_failed')
            yield None
            async for raw in socket:
                message = WSMessage.model_validate_json(raw)
                if message.type == 'event' and message.event:
                    event = message.event
                    yield event.data.new_state or HAState(entity_id=event.data.entity_id, state='unavailable',
                                                          last_updated=event.time_fired, last_changed=event.time_fired)

    async def publish(self, payloads: dict[str, dict[str, JsonValue]]):
        for entity, payload in payloads.items():
            await self.request('POST', 'states/' + entity, json=payload)


def entity_payloads(snapshot):
    definitions = (
        ('estimated_power', 'statistics', 'estimated_power', 'W', 'power'),
        ('actual_power', 'statistics', 'actual_power', 'W', 'power'),
        ('pr', 'statistics', 'pr', '%', None),
        ('daily_estimated_energy', 'energy', 'daily_kwh', 'kWh', 'energy'),
        ('total_estimated_energy', 'energy', 'total_kwh', 'kWh', 'energy'),
        ('realtime_estimated_power', 'realtime', 'estimated_power', 'W', 'power'),
        ('realtime_actual_power', 'realtime', 'actual_power', 'W', 'power'),
        ('realtime_pr', 'realtime', 'pr', '%', None),
        ('realtime_optimizable_power', 'realtime', 'optimizable_power', 'W', 'power'),
    )
    payloads = {}
    for name, channel, field, unit, device_class in definitions:
        data = snapshot.get(channel) or {}
        value = data.get(field)
        attributes = {
            'friendly_name': 'PVYieldLens ' + name.replace('_', ' ').title(),
            'unit_of_measurement': unit, 'state_class': 'total_increasing' if channel == 'energy' else 'measurement',
            'calculated_at': snapshot['calculated_at'], 'configuration_revision': snapshot['revision'],
            'sampling_method': 'state_hold',
            **{key: data[key] for key in ('start', 'end', 'valid_seconds', 'coverage_percent', 'quality', 'reason',
                                          'settled_until', 'day', 'timezone', 'daily_valid_seconds', 'total_valid_seconds') if key in data},
        }
        if device_class:
            attributes['device_class'] = device_class
        payloads['sensor.pvyieldlens_' + name] = {'state': 'unavailable' if value is None else str(round(value, 6)), 'attributes': attributes}
    return payloads
