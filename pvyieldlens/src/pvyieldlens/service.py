import asyncio
import logging
import time
from contextlib import suppress
from datetime import datetime, time as day_time
from zoneinfo import ZoneInfo

import httpx
from websockets.exceptions import WebSocketException

from .engine import calculate, calculate_live, calculate_live_series, input_spans
from .forecast_service import ForecastController
from .home_assistant import HomeAssistantClient, entity_payloads, parse_state
from .open_meteo import OPEN_METEO_TIMEOUT_SECONDS, OpenMeteoClient
from .settings import AmbientSite, HALocation, MonitoringSettings
from .storage import Store

LOGGER = logging.getLogger(__name__)
NETWORK_ERRORS = (httpx.HTTPError, WebSocketException, OSError, ValueError)


class Service:
    def __init__(self, store: Store, client: HomeAssistantClient | None = None, *,
                 ambient_client: OpenMeteoClient | None = None):
        self.store = store
        self.client = client
        self.ambient_client = ambient_client
        self._owns_ambient_client = ambient_client is None
        self._ambient_wake = asyncio.Event()
        self._ambient_request_scope: asyncio.Timeout | None = None
        self._ambient_attempted: tuple[str, AmbientSite] | None = None
        self.monitoring_settings = store.monitoring_settings()
        self.lock = asyncio.Lock()
        self.live_window = None
        self.connected = False
        self.error = None
        self.sources = []
        self.tasks = []
        self.calculated_at = None
        self.history_available = True
        self._recovery_needed = True
        self.origin = store.latest_origin()
        self.subscribed = asyncio.Event()
        self.forecast = ForecastController(store, ha_client=lambda: self.client)

    async def configure(self, monitoring_settings: MonitoringSettings, now: float | None = None, origin: str | None = None):
        now = time.time() if now is None else now
        async with self.lock:
            self._configure(monitoring_settings, now, self.origin if origin is None else origin, self.forecast.location)

    def _configure(self, monitoring_settings: MonitoringSettings, now: float, origin: str, location: HALocation | None):
        if self.monitoring_settings != monitoring_settings or self.origin != origin:
            previous_target = self._ambient_target()
            if self.monitoring_settings and self.monitoring_settings.home_timezone != monitoring_settings.home_timezone:
                self.store.rebuild_day(now, monitoring_settings.home_timezone)
            live_fields = {'live_window_seconds', 'update_interval_seconds'}
            live_only = (self.monitoring_settings and origin == self.origin
                         and self.monitoring_settings.model_dump(exclude=live_fields) == monitoring_settings.model_dump(exclude=live_fields))
            if live_only:
                # Keep the settlement boundary; only the rolling view changes.
                self.store.update_live_settings(monitoring_settings)
            else:
                self.store.save_monitoring_settings(monitoring_settings, now, origin)
            self.monitoring_settings = monitoring_settings
            self.origin = origin
            self.sources = []
            self.live_window = None
            self._recovery_needed = True
            if previous_target != self._ambient_target():
                self._ambient_attempted = None
                self._ambient_wake.set()
                if self._ambient_request_scope is not None:
                    self._ambient_request_scope.reschedule(asyncio.get_running_loop().time())
        self.forecast.configure(monitoring_settings, self.forecast.settings, origin, location)

    def _ambient_target(self) -> tuple[str, AmbientSite] | None:
        config = self.monitoring_settings
        if config and config.module_temperature_entity is None and config.ambient_site is not None:
            return self.origin, config.ambient_site
        return None

    async def _run_ambient(self) -> None:
        while True:
            self._ambient_wake.clear()
            target = self._ambient_target()
            delay = None
            if target is not None:
                origin, site = target
                if self.ambient_client is None:
                    self.ambient_client = OpenMeteoClient()
                self._ambient_request_scope = asyncio.timeout(OPEN_METEO_TIMEOUT_SECONDS)
                try:
                    async with self._ambient_request_scope:
                        observations = await self.ambient_client.fetch_ambient_temperature(site)
                except (httpx.HTTPError, OSError, ValueError) as error:
                    if target == self._ambient_target():
                        LOGGER.warning('Open-Meteo air temperature unavailable (%s)', type(error).__name__)
                    observations = None
                finally:
                    self._ambient_request_scope = None
                async with self.lock:
                    if target != self._ambient_target():
                        continue
                    if observations is not None:
                        self.store.cache_ambient_temperature(observations, origin)
                    self._ambient_attempted = target
                delay = 900 if observations is None else 3600
            try:
                async with asyncio.timeout(delay):
                    await self._ambient_wake.wait()
            except TimeoutError:
                pass

    async def _settle(self, now: float):
        cursor = self.store.cursor
        first = cursor
        ambient_pending = self._ambient_target() if self.tasks else None
        if ambient_pending == self._ambient_attempted:
            ambient_pending = None
        periods = self.store.configuration_history(cursor, now)
        for index, period in enumerate(periods):
            limit = periods[index+1].effective_at if index+1 < len(periods) else now
            config = period.monitoring_settings
            pending_temperature = config.temperature_input if (
                config.module_temperature_entity is None and ambient_pending == (period.origin, config.ambient_site)
            ) else None
            step = config.settlement_interval_minutes * 60
            while cursor < limit:
                boundary = (int(cursor // step) + 1) * step
                if boundary > limit and index == len(periods)-1:
                    break
                end = min(boundary, limit)
                observations = self.store.observations(cursor, end, config.observation_entities, period.origin)
                # Give the active site's first fetch a chance to fill gaps before committing this window.
                if pending_temperature and any(value is None for _, _, (value,) in input_spans(
                    observations, (pending_temperature,), cursor, end,
                )):
                    break
                result = calculate(config, observations, cursor, end)
                self.store.settle(result, period.revision, self.monitoring_settings.home_timezone)
                cursor = end
                await asyncio.sleep(0)
            if cursor < limit:
                break
        zone = ZoneInfo(self.monitoring_settings.home_timezone)
        midnight = datetime.combine(datetime.fromtimestamp(now, zone).date(), day_time(), zone).timestamp()
        if cursor > first and first < midnight:
            self.forecast.invalidate_correction()

    async def tick(self, now: float | None = None):
        now = time.time() if now is None else now
        async with self.lock:
            if not self.monitoring_settings:
                return
            await self._settle(now)
            observations = self.store.observations(now - self.monitoring_settings.live_window_seconds, now,
                                                   self.monitoring_settings.observation_entities, self.origin)
            started_at = self.store.get_meta('started_at')
            result = calculate_live(self.monitoring_settings, observations, now,
                                        started_at=float(started_at) if started_at is not None else None)
            self.live_window = result.public()
            self.calculated_at = now

    def live_series(self, now: float | None = None):
        now = time.time() if now is None else now
        start = max(0, now - 600)
        monitoring_settings = self.monitoring_settings
        if monitoring_settings is None:
            return {'configured': False, 'recovering': False, 'range': {'start': start, 'end': now},
                    'step_seconds': None, 'context': None, 'points': []}
        revision = self.store.revision
        period = self.store.configuration_history(now, now)[-1]
        observations = self.store.observations(start - monitoring_settings.live_window_seconds, now,
                                               monitoring_settings.observation_entities, self.origin)
        anchor = self.calculated_at if self.calculated_at is not None and start <= self.calculated_at <= now else now
        first = max(start, period.effective_at)
        started_at = self.store.get_meta('started_at')
        started_at = float(started_at) if started_at is not None else None
        endpoints = [anchor - index * monitoring_settings.update_interval_seconds
                     for index in reversed(range(max(0, int((anchor - first) // monitoring_settings.update_interval_seconds) + 1)))]
        points = [{'at': at, **result.public()} for at, result in zip(
            endpoints, calculate_live_series(monitoring_settings, observations, endpoints, started_at=started_at))]
        if points:
            if self.live_window is not None and anchor == self.calculated_at:
                points[-1] = {'at': anchor, **self.live_window}
            elif self.live_window is None:
                points[-1].update(estimated_power_w=None, actual_power_w=None, pr=None, optimizable_power_w=None,
                                  quality='unavailable', reason='current_source_unavailable')
        return {'configured': True, 'recovering': self._recovery_needed, 'range': {'start': start, 'end': now},
                'step_seconds': monitoring_settings.update_interval_seconds, 'context': {'revision': revision, 'monitoring_settings': monitoring_settings.public()},
                'points': points}

    def snapshot(self, now: float | None = None):
        now = time.time() if now is None else now
        return {'configured': self.monitoring_settings is not None, 'connected': self.connected, 'error': self.error,
                'history_available': self.history_available, 'calculated_at': self.calculated_at,
                'revision': self.store.revision, 'latest_settled_window': self.store.latest_settled_window(), 'live_window': self.live_window,
                'energy_totals': self.store.totals(now, self.monitoring_settings.home_timezone if self.monitoring_settings else 'UTC'),
                'sources': self.sources, 'home_timezone': self.monitoring_settings.home_timezone if self.monitoring_settings else 'UTC',
                'location': self.forecast.location.model_dump() if self.forecast.location else None,
                'forecast': self.forecast.view(now).model_dump(mode='json', exclude={'days', 'intervals'})}

    async def ingest(self, states, historical=False, monitoring_settings: MonitoringSettings | None = None, origin: str | None = None):
        async with self.lock:
            if not self.monitoring_settings:
                return
            roles = {entity: role for role, entity, _ in (monitoring_settings or self.monitoring_settings).ha_sources}
            parsed = [(state, parse_state(state, roles[state.entity_id], historical)) for state in states if state.entity_id in roles]
            items = [item for _, points in parsed for item in points]
            self.store.add_observations(items, self.origin if origin is None else origin)
            if not historical:
                previous = {source['entity_id']: source for source in self.sources}
                for state, points in parsed:
                    previous[state.entity_id] = {'entity_id': state.entity_id, 'state': state.state,
                        'unit': state.attributes.unit_of_measurement, 'reported_at': points[-1].at,
                        'valid': points[-1].value is not None}
                self.sources = [previous[entity] for entity in self.monitoring_settings.entities if entity in previous]

    async def recover(self):
        if not self.client or not self.monitoring_settings:
            return
        now = time.time()
        self.history_available = True
        periods = self.store.configuration_history(self.store.cursor, now)
        for index, period in enumerate(periods):
            if period.origin != self.origin:
                continue
            limit = periods[index+1].effective_at if index+1 < len(periods) else now
            first = max(max(self.store.cursor, period.effective_at) - max(period.monitoring_settings.max_ages), now - 7 * 86400)
            while first < limit:
                end = min(limit, first + 6 * 3600)
                try:
                    history = await self.client.history(list(period.monitoring_settings.entities), first, end)
                except httpx.HTTPStatusError as error:
                    if error.response.status_code not in (400, 404):
                        raise
                    self.history_available = False
                    break
                await self.ingest(history, historical=True, monitoring_settings=period.monitoring_settings, origin=period.origin)
                first = end
        await self.ingest(await self.client.states(self.monitoring_settings.entities))
        self._recovery_needed = False

    def _mark_offline(self):
        self.connected = False
        self.error = 'ha_connection_failed'
        self._recovery_needed = True
        self.live_window = None
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
                if self.client and self.monitoring_settings:
                    client = self.client
                    origin = self.origin
                    ha_config = await client.configuration()
                    async with self.lock:
                        if client is not self.client or origin != self.origin:
                            continue
                        config = self.monitoring_settings
                        location = ha_config.location
                        site = AmbientSite(latitude=location.latitude, longitude=location.longitude) if (
                            config.module_temperature_entity is None and location is not None and location.origin == origin
                        ) else None
                        if config.home_timezone != ha_config.time_zone or config.ambient_site != site:
                            config = MonitoringSettings.model_validate({
                                **config.model_dump(), 'home_timezone': ha_config.time_zone, 'ambient_site': site,
                            })
                        self._configure(config, time.time(), origin, location)
                    await self.subscribed.wait()
                    if self._recovery_needed:
                        await self.recover()
                    else:
                        await self.ingest(await self.client.states(self.monitoring_settings.entities))
                    if not self.subscribed.is_set():
                        continue
                    self.connected = True
                    self.error = None
                await self.tick()
                if self.client and self.monitoring_settings:
                    async with self.lock:
                        payloads = entity_payloads(self.snapshot())
                    await self.client.publish(payloads)
                if started - last_prune >= 3600:
                    async with self.lock:
                        self.store.prune(started)
                    last_prune = started
            except NETWORK_ERRORS as error:
                # Do not settle during an outage before historical recovery has a chance.
                self._mark_offline()
                LOGGER.warning('HA update unavailable (%s)', type(error).__name__)
            interval = self.monitoring_settings.update_interval_seconds if self.monitoring_settings else 5
            await asyncio.sleep(max(0.1, interval - (time.time() - started)))

    async def start(self):
        if self.tasks:
            return
        await self.forecast.start()
        self.subscribed.clear()
        self.store.set_meta('started_at', str(time.time()))
        self._ambient_attempted = None
        self.tasks = [asyncio.create_task(run()) for run in (self._events, self._run, self._run_ambient)]

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with suppress(asyncio.CancelledError):
                await task
        self.tasks = []
        await self.forecast.stop()
        if self._owns_ambient_client and self.ambient_client is not None:
            await self.ambient_client.close()
            self.ambient_client = None
        if self.client:
            with suppress(httpx.HTTPError, OSError):
                async with self.lock:
                    payloads = entity_payloads(self.snapshot())
                for payload in payloads.values():
                    payload['state'] = 'unavailable'
                await self.client.publish(payloads)
            await self.client.close()
