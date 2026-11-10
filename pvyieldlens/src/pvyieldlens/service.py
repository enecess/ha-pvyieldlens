import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import replace

import httpx
from websockets.exceptions import WebSocketException

from .engine import calculate
from .home_assistant import HomeAssistantClient, entity_payloads, parse_state
from .settings import Settings
from .storage import Store

LOGGER = logging.getLogger(__name__)
NETWORK_ERRORS = (httpx.HTTPError, WebSocketException, OSError, ValueError)


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
        self.origin = store.latest_origin()
        self.subscribed = asyncio.Event()

    async def configure(self, config: Settings, now: float | None = None, origin: str | None = None):
        now = time.time() if now is None else now
        origin = self.origin if origin is None else origin
        async with self.lock:
            if self.config and self.config.timezone != config.timezone:
                self.store.rebuild_day(now, config.timezone)
            realtime_fields = {'realtime_window_seconds', 'update_seconds'}
            realtime_only = self.config and origin == self.origin and self.config.model_dump(exclude=realtime_fields) == config.model_dump(exclude=realtime_fields)
            if realtime_only:
                # Keep the settlement boundary; only the rolling view changes.
                self.store.update_realtime_settings(config)
            else:
                self.store.save_settings(config, now, origin)
            self.config = config
            self.origin = origin
            self.sources = []
            self.realtime = None
            self._recovery_needed = True

    async def _settle(self, now: float):
        cursor = self.store.cursor
        periods = self.store.configuration_history(cursor, now)
        for index, period in enumerate(periods):
            limit = periods[index+1].effective_at if index+1 < len(periods) else now
            step = period.settings.interval_minutes * 60
            while cursor < limit:
                boundary = (int(cursor // step) + 1) * step
                if boundary > limit and index == len(periods)-1:
                    break
                end = min(boundary, limit)
                result = calculate(period.settings, self.store.observations(cursor, end, period.settings.entities, period.origin), cursor, end)
                self.store.settle(result, period.revision, self.config.timezone)
                cursor = end
                await asyncio.sleep(0)

    async def tick(self, now: float | None = None):
        now = time.time() if now is None else now
        async with self.lock:
            if not self.config:
                return
            await self._settle(now)
            observations = self.store.observations(now - self.config.realtime_window_seconds, now, self.config.entities, self.origin)
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

    async def ingest(self, states, historical=False, config: Settings | None = None, origin: str | None = None):
        async with self.lock:
            if not self.config:
                return
            roles = dict(zip((config or self.config).entities, ('power', 'temperature', 'irradiance')))
            parsed = [(state, parse_state(state, roles[state.entity_id], historical)) for state in states if state.entity_id in roles]
            items = [item for _, points in parsed for item in points]
            self.store.add_observations(items, self.origin if origin is None else origin)
            if not historical:
                previous = {source['entity_id']: source for source in self.sources}
                for state, points in parsed:
                    previous[state.entity_id] = {'entity_id': state.entity_id, 'state': state.state,
                        'unit': state.attributes.unit_of_measurement, 'reported_at': points[-1].at,
                        'valid': points[-1].value is not None}
                self.sources = [previous[entity] for entity in self.config.entities if entity in previous]

    async def recover(self):
        if not self.client or not self.config:
            return
        now = time.time()
        self.history_available = True
        periods = self.store.configuration_history(self.store.cursor, now)
        for index, period in enumerate(periods):
            if period.origin != self.origin:
                continue
            limit = periods[index+1].effective_at if index+1 < len(periods) else now
            first = max(max(self.store.cursor, period.effective_at) - max(period.settings.max_ages), now - 7 * 86400)
            while first < limit:
                end = min(limit, first + 6 * 3600)
                try:
                    history = await self.client.history(list(period.settings.entities), first, end)
                except httpx.HTTPStatusError as error:
                    if error.response.status_code not in (400, 404):
                        raise
                    self.history_available = False
                    break
                await self.ingest(history, historical=True, config=period.settings, origin=period.origin)
                first = end
        await self.ingest(await self.client.states(self.config.entities))
        self._recovery_needed = False

    def _mark_offline(self):
        self.connected = False
        self.error = 'ha_connection_failed'
        self._recovery_needed = True
        self.realtime = None
        self.calculated_at = time.time()

    async def _events(self):
        while True:
            if not self.client:
                await asyncio.sleep(1)
                continue
            try:
                async for state in self.client.events():
                    if state is None:
                        self._recovery_needed = True
                        self.subscribed.set()
                    else:
                        await self.ingest([state])
            except NETWORK_ERRORS as error:
                LOGGER.warning('HA event stream unavailable (%s)', type(error).__name__)
                self._mark_offline()
                self.subscribed.clear()
                await asyncio.sleep(5)
            finally:
                if self.subscribed.is_set():
                    self._mark_offline()
                self.subscribed.clear()

    async def _run(self):
        last_prune = 0
        while True:
            started = time.time()
            try:
                if self.client and self.config:
                    await self.subscribed.wait()
                    ha_config = await self.client.configuration()
                    if self.config.timezone != ha_config.time_zone:
                        await self.configure(Settings.model_validate({**self.config.model_dump(), 'timezone': ha_config.time_zone}))
                    if self._recovery_needed:
                        await self.recover()
                    else:
                        await self.ingest(await self.client.states(self.config.entities))
                    if not self.subscribed.is_set():
                        continue
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
                # Do not settle during an outage before historical recovery has a chance.
                self._mark_offline()
                LOGGER.warning('HA update unavailable (%s)', type(error).__name__)
            interval = self.config.update_seconds if self.config else 5
            await asyncio.sleep(max(0.1, interval - (time.time() - started)))

    async def start(self):
        self.subscribed.clear()
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
