import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import replace

import httpx
from pydantic import ValidationError
from websockets.exceptions import WebSocketException

from .engine import calculate
from .home_assistant import HomeAssistantClient, entity_payloads, parse_state
from .settings import Settings
from .storage import Store

LOGGER = logging.getLogger(__name__)
NETWORK_ERRORS = (httpx.HTTPError, WebSocketException, OSError, TimeoutError, ValidationError, ValueError)


class Service:
    def __init__(self, store: Store, client: HomeAssistantClient | None = None):
        self.store = store
        self.client = client
        self.config = store.settings()
        self.lock = asyncio.Lock()
        self.realtime = None
        self.connected = False
        self.error = None
        self.sources = []
        self.tasks = []
        self.calculated_at = None
        self.history_available = True
        self._recovery_needed = True

    async def configure(self, config: Settings, now: float | None = None):
        now = time.time() if now is None else now
        async with self.lock:
            realtime_fields = {'realtime_window_seconds', 'update_seconds'}
            realtime_only = self.config and self.config.model_dump(exclude=realtime_fields) == config.model_dump(exclude=realtime_fields)
            if realtime_only:
                # Keep the settlement boundary; only the rolling view changes.
                self.store.db.execute('UPDATE configs SET settings=? WHERE revision=?', (config.model_dump_json(), self.store.revision))
                self.store.db.commit()
            else:
                if self.config:
                    await self._settle(now, partial=True)
                self.store.save_settings(config, now)
            self.config = config
            self.realtime = None
            self._recovery_needed = True

    async def _settle(self, now: float, partial=False):
        step = self.config.interval_minutes * 60
        cursor = self.store.cursor
        while cursor < now:
            end = (int(cursor // step) + 1) * step
            if end > now:
                if not partial:
                    break
                end = now
            result = calculate(self.config, self.store.observations(cursor, end), cursor, end)
            self.store.settle(result, self.store.revision, self.config.timezone)
            cursor = end
            await asyncio.sleep(0)

    async def tick(self, now: float | None = None):
        now = time.time() if now is None else now
        async with self.lock:
            if not self.config:
                return
            await self._settle(now)
            observations = self.store.observations(now - self.config.realtime_window_seconds, now)
            result = calculate(self.config, observations, now - self.config.realtime_window_seconds, now)
            current = calculate(self.config, observations, now, now + 0.0001)
            if not current.valid_seconds:
                result = replace(result, estimated_power=None, actual_power=None, pr=None, optimizable_power=None,
                                 quality='unavailable', reason='current_source_unavailable')
            elif result.quality == 'partial' and self.store.get_meta('started_at'):
                if now - float(self.store.get_meta('started_at')) < self.config.realtime_window_seconds:
                    result = replace(result, quality='warming_up')
            self.realtime = result.public()
            self.calculated_at = now

    def snapshot(self, now: float | None = None):
        now = time.time() if now is None else now
        return {'configured': self.config is not None, 'connected': self.connected, 'error': self.error,
                'history_available': self.history_available, 'calculated_at': self.calculated_at,
                'revision': self.store.revision, 'statistics': self.store.latest_window(), 'realtime': self.realtime,
                'energy': self.store.totals(now, self.config.timezone if self.config else 'UTC'),
                'sources': self.sources, 'timezone': self.config.timezone if self.config else 'UTC'}

    async def ingest(self, states, historical=False):
        async with self.lock:
            if not self.config:
                return
            roles = dict(zip(self.config.entities, ('power', 'temperature', 'irradiance')))
            items = [item for state in states if state.entity_id in roles
                     for item in parse_state(state, roles[state.entity_id], historical)]
            self.store.add_observations(items)
            if not historical:
                previous = {source['entity_id']: source for source in self.sources}
                for state in states:
                    if state.entity_id in roles:
                        points = parse_state(state, roles[state.entity_id])
                        previous[state.entity_id] = {'entity_id': state.entity_id, 'state': state.state,
                            'unit': state.attributes.unit_of_measurement, 'reported_at': points[-1].at,
                            'valid': points[-1].value is not None}
                self.sources = [previous[entity] for entity in self.config.entities if entity in previous]

    async def recover(self):
        if not self.client or not self.config:
            return
        now = time.time()
        first = max(self.store.cursor - max(self.config.max_ages), now - 7 * 86400)
        while first < now:
            end = min(now, first + 6 * 3600)
            try:
                history = await self.client.history(list(self.config.entities), first, end)
            except httpx.HTTPStatusError as error:
                if error.response.status_code not in (400, 404):
                    raise
                self.history_available = False
                break
            await self.ingest(history, historical=True)
            first = end
        await self.ingest(await self.client.states(self.config.entities))
        self._recovery_needed = False

    async def _events(self):
        while True:
            if not self.client:
                await asyncio.sleep(1)
                continue
            try:
                async for state in self.client.events():
                    if state is None:
                        self._recovery_needed = True
                    else:
                        await self.ingest([state])
            except NETWORK_ERRORS as error:
                LOGGER.warning('HA event stream unavailable (%s)', type(error).__name__)
                self._recovery_needed = True
                await asyncio.sleep(5)

    async def _run(self):
        last_prune = 0
        while True:
            started = time.time()
            try:
                if self.client and self.config:
                    ha_config = await self.client.configuration()
                    if self.config.timezone != ha_config.time_zone:
                        await self.configure(Settings.model_validate({**self.config.model_dump(), 'timezone': ha_config.time_zone}))
                    if self._recovery_needed:
                        await self.recover()
                    else:
                        await self.ingest(await self.client.states(self.config.entities))
                    self.connected = True
                    self.error = None
                await self.tick()
                if self.client and self.config:
                    await self.client.publish(entity_payloads(self.snapshot()))
                if started - last_prune >= 3600:
                    async with self.lock:
                        self.store.prune(started)
                    last_prune = started
            except NETWORK_ERRORS as error:
                self.connected = False
                self.error = 'ha_connection_failed'
                self._recovery_needed = True
                # Do not settle during an outage before historical recovery has a chance.
                self.realtime = None
                LOGGER.warning('HA update unavailable (%s)', type(error).__name__)
            interval = self.config.update_seconds if self.config else 5
            await asyncio.sleep(max(0.1, interval - (time.time() - started)))

    async def start(self):
        self.store.set_meta('started_at', str(time.time()))
        self.tasks = [asyncio.create_task(self._events()), asyncio.create_task(self._run())]

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with suppress(asyncio.CancelledError):
                await task
        self.tasks = []
        if self.client:
            with suppress(httpx.HTTPError, OSError):
                payloads = entity_payloads(self.snapshot())
                for payload in payloads.values():
                    payload['state'] = 'unavailable'
                await self.client.publish(payloads)
            await self.client.close()
