import asyncio
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .correction import ForecastCorrection, correction_view, physical_context
from .forecast import (
    FORECAST_MODEL_VERSION, ForecastAngleIssue, ForecastAxis, ForecastBatch, ForecastInput,
    ForecastPrerequisite, ForecastView, forecast_view,
)
from .home_assistant import HomeAssistantClient, source_value
from .open_meteo import OpenMeteoClient
from .settings import ForecastSettings, HALocation, MonitoringSettings
from .storage import Store


@dataclass(frozen=True)
class ForecastContext:
    location: HALocation
    total_max_power_at_stc_w: float
    pmax_temperature_coefficient_pct_per_c: float
    noct_c: float
    tilt: float | str
    azimuth: float | str
    model_version: int = FORECAST_MODEL_VERSION


class ForecastController:
    def __init__(self, store: Store, client: OpenMeteoClient | None = None, *,
                 ha_client: Callable[[], HomeAssistantClient | None] | None = None):
        self.store = store
        self.client = client
        self.ha_client = ha_client
        self._owns_client = client is None
        self.settings = store.forecast_settings()
        location = store.get_meta('ha_location')
        self.location = HALocation.model_validate_json(location) if location and location != 'null' else None
        cache = store.get_meta('forecast_cache')
        self.batch = ForecastBatch.model_validate_json(cache) if cache else None
        self.context: ForecastContext | ForecastPrerequisite = 'configuration_required'
        self.monitoring_settings: MonitoringSettings | None = None
        self.origin = ''
        self._correction: ForecastCorrection | None = None
        self._correction_key = None
        self.last_error: str | None = None
        self.unavailable_angles: tuple[ForecastAngleIssue, ...] = ()
        self._task: asyncio.Task[None] | None = None
        self._request_task: asyncio.Task[None] | None = None
        self._inflight: asyncio.Future[None] | None = None
        self._wake = asyncio.Event()
        self._next_refresh = 0.0
        self.configure(store.monitoring_settings(), self.settings, store.latest_origin(), self.location)

    def configure(self, monitoring_settings: MonitoringSettings | None, settings: ForecastSettings,
                  origin: str, location: HALocation | None) -> None:
        location = location if location and location.origin == origin else None
        if settings != self.settings:
            self.store.save_forecast_settings(settings)
        if location != self.location:
            self.store.set_meta('ha_location', location.model_dump_json() if location else 'null')
        geometry = settings.geometry_sources
        context: ForecastContext | ForecastPrerequisite
        if monitoring_settings is None or geometry is None:
            context = 'configuration_required'
        elif location is None:
            context = 'location_unavailable'
        else:
            tilt, azimuth = geometry
            context = ForecastContext(
                location=location.model_copy(update={'location_name': None}),
                total_max_power_at_stc_w=monitoring_settings.total_max_power_at_stc_w,
                pmax_temperature_coefficient_pct_per_c=monitoring_settings.pmax_temperature_coefficient_pct_per_c,
                noct_c=settings.noct_c, tilt=tilt, azimuth=azimuth,
            )
        changed = context != self.context
        if (monitoring_settings != self.monitoring_settings or origin != self.origin
                or settings.pr_history_days != self.settings.pr_history_days):
            self.invalidate_correction()
        self.monitoring_settings = monitoring_settings
        self.origin = origin
        self.settings = settings
        self.location = location
        self.context = context
        if self.batch is not None:
            cached = self.batch.inputs
            if ForecastContext(
                location=cached.location,
                total_max_power_at_stc_w=cached.total_max_power_at_stc_w,
                pmax_temperature_coefficient_pct_per_c=cached.pmax_temperature_coefficient_pct_per_c,
                noct_c=cached.noct_c,
                tilt=self.batch.tilt_entity or cached.tilt_deg,
                azimuth=self.batch.azimuth_entity or cached.azimuth_deg,
                model_version=cached.model_version,
            ) != context:
                self.batch = None
        if changed:
            self.last_error = None
            self.unavailable_angles = ()
            self._next_refresh = 0.0
            self._wake.set()

    def invalidate_correction(self) -> None:
        self._correction_key = None

    def view(self, now: float) -> ForecastView:
        correction = None
        context = self.context
        config = self.monitoring_settings
        if context != 'configuration_required' and config is not None:
            key = (datetime.fromtimestamp(now, ZoneInfo(config.home_timezone)).date(), config.home_timezone,
                   self.settings.pr_history_days, physical_context(config, self.origin))
            if key != self._correction_key:
                self._correction = correction_view(self.store, config, self.origin, now, self.settings.pr_history_days)
                self._correction_key = key
            correction = self._correction
        return forecast_view(self.batch, context.location if isinstance(context, ForecastContext) else context, now,
                             correction=correction, refreshing=self._inflight is not None,
                             last_error=self.last_error, unavailable_angles=self.unavailable_angles)

    def request_refresh(self) -> bool:
        if isinstance(self.context, str):
            return False
        if self._inflight is None:
            self._next_refresh = 0.0
            self._wake.set()
            if self._task is None:
                self._task = asyncio.create_task(self._run())
        return True

    async def refresh(self, now: float | None = None) -> None:
        context = self.context
        if isinstance(context, str):
            return
        if self._inflight is not None:
            await asyncio.shield(self._inflight)
            return
        axes: tuple[tuple[ForecastAxis, float | str], ...] = (('tilt', context.tilt), ('azimuth', context.azimuth))
        entities = tuple(dict.fromkeys(source for _, source in axes if isinstance(source, str)))
        self._inflight = asyncio.get_running_loop().create_future()
        self._request_task = asyncio.current_task()
        try:
            batch = error = read_at = None
            issues = []
            try:
                states_by_id = {}
                if entities:
                    ha = self.ha_client() if self.ha_client is not None else None
                    if ha is not None and ha.base_url == context.location.origin:
                        try:
                            states = await ha.states(entities)
                        except (httpx.HTTPError, OSError, ValueError):
                            pass
                        else:
                            read_at = time.time() if now is None else now
                            states_by_id = {state.entity_id: state for state in states}
                angles = {}
                for axis, source in axes:
                    if isinstance(source, str):
                        state = states_by_id.get(source)
                        angle = source_value(state.state, state.attributes.unit_of_measurement, axis) if state else None
                        if angle is None:
                            issues.append(ForecastAngleIssue(axis=axis, entity_id=source))
                            continue
                        angles[axis] = angle
                    else:
                        angles[axis] = source
                if issues:
                    error = 'forecast_angle_unavailable'
                else:
                    inputs = ForecastInput(location=context.location,
                        total_max_power_at_stc_w=context.total_max_power_at_stc_w,
                        pmax_temperature_coefficient_pct_per_c=context.pmax_temperature_coefficient_pct_per_c,
                        tilt_deg=angles['tilt'], azimuth_deg=angles['azimuth'], noct_c=context.noct_c)
                    if self.client is None:
                        self.client = OpenMeteoClient()
                    data = await self.client.fetch(inputs)
                    batch = ForecastBatch(inputs=inputs, fetched_at=time.time() if now is None else now,
                        tilt_entity=context.tilt if isinstance(context.tilt, str) else None,
                        azimuth_entity=context.azimuth if isinstance(context.azimuth, str) else None,
                        angles_read_at=read_at, intervals=data.intervals, weather_samples=data.weather_samples)
            except (httpx.HTTPError, OSError, ValueError):
                error = 'forecast_fetch_failed'
            if self.context == context:
                if batch is not None:
                    self.batch = batch
                    self.store.set_meta('forecast_cache', batch.model_dump_json())
                self.last_error = error
                self.unavailable_angles = tuple(issues)
                self._next_refresh = asyncio.get_running_loop().time() + (900 if error else 3600)
        finally:
            self._inflight.set_result(None)
            self._inflight = None
            self._request_task = None
            self._wake.set()

    async def _run(self) -> None:
        while True:
            delay = max(0.0, self._next_refresh - asyncio.get_running_loop().time()) if (
                isinstance(self.context, ForecastContext)
            ) else None
            if delay == 0:
                self._wake.clear()
                await self.refresh()
                continue
            try:
                async with asyncio.timeout(delay):
                    await self._wake.wait()
            except TimeoutError:
                pass
            self._wake.clear()

    async def start(self) -> None:
        if self._task is None:
            self._next_refresh = 0.0
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        tasks = {task for task in (self._task, self._request_task) if task is not None}
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._task = None
        self._wake.clear()
        if self._owns_client and self.client is not None:
            await self.client.close()
            self.client = None
