import asyncio
import time
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .correction import ForecastCorrection, correction_view, physical_context
from .forecast import ForecastBatch, ForecastInput, ForecastView, forecast_view
from .open_meteo import OpenMeteoClient
from .settings import ForecastSettings, HALocation, MonitoringSettings
from .storage import Store


class ForecastController:
    def __init__(self, store: Store, client: OpenMeteoClient | None = None):
        self.store = store
        self.client = client
        self._owns_client = client is None
        self.settings = store.forecast_settings()
        location = store.get_meta('ha_location')
        self.location = HALocation.model_validate_json(location) if location and location != 'null' else None
        cache = store.get_meta('forecast_cache')
        self.batch = ForecastBatch.model_validate_json(cache) if cache else None
        self.inputs: ForecastInput | None = None
        self.monitoring_settings: MonitoringSettings | None = None
        self.origin = ''
        self._correction: ForecastCorrection | None = None
        self._correction_key = None
        self.last_error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._request_task: asyncio.Task[None] | None = None
        self._inflight: asyncio.Future[None] | None = None
        self._request_scope: asyncio.Timeout | None = None
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
        inputs = ForecastInput(
            location=location.model_copy(update={'location_name': None}),
            total_max_power_at_stc_w=monitoring_settings.total_max_power_at_stc_w,
            pmax_temperature_coefficient_pct_per_c=monitoring_settings.pmax_temperature_coefficient_pct_per_c,
            tilt_deg=settings.tilt_deg, azimuth_deg=settings.azimuth_deg, noct_c=settings.noct_c,
        ) if monitoring_settings and location and settings.tilt_deg is not None and settings.azimuth_deg is not None else None
        changed = inputs != self.inputs or settings.enabled != self.settings.enabled
        if (monitoring_settings != self.monitoring_settings or origin != self.origin
                or settings.pr_history_days != self.settings.pr_history_days):
            self.invalidate_correction()
        self.monitoring_settings = monitoring_settings
        self.origin = origin
        self.settings = settings
        if not settings.enabled and self._request_scope is not None and self._request_scope.when() is None:
            self._request_scope.reschedule(asyncio.get_running_loop().time())
        self.location = location
        self.inputs = inputs
        if self.batch and self.batch.inputs != inputs:
            self.batch = None
        if changed:
            self.last_error = None
            self._next_refresh = 0.0
            self._wake.set()

    def invalidate_correction(self) -> None:
        self._correction_key = None

    def view(self, now: float) -> ForecastView:
        correction = None
        if self.settings.enabled and self.monitoring_settings is not None:
            config = self.monitoring_settings
            key = (datetime.fromtimestamp(now, ZoneInfo(config.home_timezone)).date(), config.home_timezone,
                   self.settings.pr_history_days, physical_context(config, self.origin))
            if key != self._correction_key:
                self._correction = correction_view(self.store, config, self.origin, now, self.settings.pr_history_days)
                self._correction_key = key
            correction = self._correction
        return forecast_view(self.batch, self.inputs, self.settings, now,
                             correction=correction, refreshing=self.settings.enabled and self._inflight is not None, last_error=self.last_error)

    def request_refresh(self) -> bool:
        if not self.settings.enabled or self.inputs is None:
            return False
        if self._inflight is None:
            self._next_refresh = 0.0
            self._wake.set()
            if self._task is None:
                self._task = asyncio.create_task(self._run())
        return True

    async def refresh(self, now: float | None = None) -> None:
        if not self.settings.enabled or self.inputs is None:
            return
        if self._inflight is not None:
            await asyncio.shield(self._inflight)
            return
        inputs = self.inputs
        self._inflight = asyncio.get_running_loop().create_future()
        self._request_task = asyncio.current_task()
        self._request_scope = asyncio.timeout(None)
        try:
            if self.client is None:
                self.client = OpenMeteoClient()
            try:
                async with self._request_scope:
                    data = await self.client.fetch(inputs)
            except (httpx.HTTPError, OSError, ValueError):
                if self._request_scope.when() is None and self.settings.enabled and self.inputs == inputs:
                    self.last_error = 'forecast_fetch_failed'
                    self._next_refresh = asyncio.get_running_loop().time() + 900
            else:
                if self._request_scope.when() is None and self.settings.enabled and self.inputs == inputs:
                    self.batch = ForecastBatch(inputs=inputs, fetched_at=time.time() if now is None else now,
                                               intervals=data.intervals, weather_samples=data.weather_samples)
                    self.store.set_meta('forecast_cache', self.batch.model_dump_json())
                    self.last_error = None
                    self._next_refresh = asyncio.get_running_loop().time() + 3600
        finally:
            self._inflight.set_result(None)
            self._inflight = None
            self._request_task = None
            self._request_scope = None
            self._wake.set()

    async def _run(self) -> None:
        while True:
            delay = max(0.0, self._next_refresh - asyncio.get_running_loop().time()) if (
                self.settings.enabled and self.inputs is not None
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
