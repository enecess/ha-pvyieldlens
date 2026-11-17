import asyncio
import json
import math
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import AwareDatetime, BaseModel, Field, JsonValue, TypeAdapter, ValidationError
from websockets.asyncio.client import connect

from .engine import Observation
from .settings import HALocation


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
    location: HALocation | None = None


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
    handshake_timeout = 20

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
        response = await self.request('GET', 'config')
        config = HAConfig.model_validate(response)
        try:
            location = HALocation.model_validate({
                'origin': self.base_url, 'latitude': response.get('latitude'),
                'longitude': response.get('longitude'), 'location_name': response.get('location_name'),
                'home_timezone': config.time_zone,
            })
        except ValidationError:
            location = None
        return config.model_copy(update={'location': location})

    async def states(self, entities: tuple[str, ...] | None = None) -> list[HAState]:
        if entities is None:
            return TypeAdapter(list[HAState]).validate_python(await self.request('GET', 'states'))
        # State.as_dict JSON is cached across unchanged reports; read live fields atomically.
        result = TypeAdapter(list[HAState | None]).validate_python(await self.request('POST', 'template', json={
            'template': '''[{% for entity in entities %}{% set s = states[entity] %}
                {% if s is not none %}{{ dict(entity_id=s.entity_id, state=s.state, attributes=dict(s.attributes),
                    last_changed=s.last_changed.isoformat(), last_updated=s.last_updated.isoformat(),
                    last_reported=s.last_reported.isoformat()) | to_json }}{% else %}null{% endif %}
                {% if not loop.last %},{% endif %}{% endfor %}]''',
            'variables': {'entities': entities},
        }))
        now = datetime.now(timezone.utc)
        return [state or HAState(entity_id=entity, state='unavailable', last_changed=now, last_updated=now)
                for entity, state in zip(entities, result, strict=True)]

    async def history(self, entities: list[str], start: float, end: float) -> list[HAState]:
        stamp = datetime.fromtimestamp(start, timezone.utc).isoformat()
        result = TypeAdapter(list[list[HAState]]).validate_python(await self.request('GET', 'history/period/' + stamp, params={
            'filter_entity_id': ','.join(entities), 'end_time': datetime.fromtimestamp(end, timezone.utc).isoformat(),
            'significant_changes_only': '0', 'skip_initial_state': '1',
        }))
        return [state for group in result for state in group]

    async def events(self):
        async with connect(self.websocket_url, open_timeout=20, max_size=8_388_608, proxy=None) as socket:
            async with asyncio.timeout(self.handshake_timeout):
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
        ('settled_estimated_power', 'latest_settled_window', 'estimated_power_w', 'W', 'power'),
        ('settled_actual_power', 'latest_settled_window', 'actual_power_w', 'W', 'power'),
        ('settled_pr', 'latest_settled_window', 'pr', '%', None),
        ('estimated_energy_today', 'energy_totals', 'estimated_energy_today_kwh', 'kWh', 'energy'),
        ('estimated_energy_lifetime', 'energy_totals', 'estimated_energy_lifetime_kwh', 'kWh', 'energy'),
        ('live_estimated_power', 'live_window', 'estimated_power_w', 'W', 'power'),
        ('live_actual_power', 'live_window', 'actual_power_w', 'W', 'power'),
        ('live_pr', 'live_window', 'pr', '%', None),
        ('live_optimizable_power', 'live_window', 'optimizable_power_w', 'W', 'power'),
    )
    payloads = {}
    for name, channel, field, unit, device_class in definitions:
        data = snapshot.get(channel) or {}
        value = data.get(field)
        attributes = {
            'friendly_name': name,
            'unit_of_measurement': unit, 'state_class': 'total_increasing' if channel == 'energy_totals' else 'measurement',
            'calculated_at': snapshot['calculated_at'], 'configuration_revision': data.get('revision', snapshot['revision']),
            'sampling_method': 'state_hold',
            **{key: data[key] for key in ('start', 'end', 'valid_seconds', 'data_completeness_percent', 'quality', 'reason',
                                          'settled_until', 'day', 'home_timezone', 'today_valid_seconds', 'lifetime_valid_seconds',
                                          'today_allocation_complete') if key in data},
        }
        if device_class:
            attributes['device_class'] = device_class
        payloads['sensor.pvyieldlens_' + name] = {'state': 'unavailable' if value is None else str(round(value, 6)), 'attributes': attributes}
    forecast = snapshot.get('forecast') or {}
    for name, target in (
        ('forecast_energy_today', 'today'),
        ('forecast_energy_remaining_today', 'remaining_today'),
        ('forecast_energy_tomorrow', 'tomorrow'),
        ('forecast_energy_7d', 'seven_days'),
    ):
        data = forecast.get(target) or {}
        value = data.get('forecast_energy_kwh')
        payloads['sensor.pvyieldlens_' + name] = {
            'state': 'unavailable' if value is None else str(round(value, 6)),
            'attributes': {
                'friendly_name': name,
                'unit_of_measurement': 'kWh', 'device_class': 'energy',
                'start': data.get('start'), 'end': data.get('end'),
                'home_timezone': forecast.get('home_timezone'), 'fetched_at': forecast.get('fetched_at'),
                'calculated_at': forecast.get('calculated_at'),
                'data_completeness_percent': data.get('data_completeness_percent', 0), 'quality': data.get('quality', 'unavailable'),
                'status': forecast.get('status', 'disabled'), 'refreshing': forecast.get('refreshing', False),
                'last_error': forecast.get('last_error'),
            },
        }
    return payloads
