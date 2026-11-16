import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from forecast_fixtures import hourly_payload
from pvyieldlens.open_meteo import OpenMeteoClient
from pvyieldlens.settings import ForecastSettings, HALocation
from pvyieldlens.storage import Store
from test_engine import samples, settings


ORIGIN = 'http://ha.test'
ENABLED = ForecastSettings(enabled=True, tilt_deg=25.0, azimuth_deg=180.0)
LOCATION = HALocation(origin=ORIGIN, latitude=0.0, longitude=0.0, timezone='UTC')


def controller(store, http):
    from pvyieldlens.forecast_service import ForecastController

    forecast = ForecastController(store, OpenMeteoClient(http))
    forecast.configure(settings(), ENABLED, ORIGIN, LOCATION)
    return forecast


async def test_cache_restart_preserves_fetched_at(tmp_path):
    from pvyieldlens.forecast_service import ForecastController

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    store.save_settings(settings(), 0, ORIGIN)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=hourly_payload(0, weather_code=61)),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=120)
        assert forecast.view(180).fetched_at == 120
        store.close()
        store = Store(path)
        restored = ForecastController(store)
        assert restored.view(180).fetched_at == 120
        assert restored.view(180).today.kwh == pytest.approx(89.28)
        assert restored.view(180).days[0].weather.weather_code == 61
        assert len(restored.batch.weather_samples) == 217
        assert store.revision == 1
        assert store.cursor == 0
        await restored.stop()
    store.close()


async def test_forecast_only_change_keeps_monitoring_revision_cursor_and_totals(tmp_path):
    from pvyieldlens.service import Service

    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(interval_minutes=1), now=0, origin=ORIGIN)
    store.add_observations(samples(), ORIGIN)
    await service.tick(60)
    service.sources = [{'entity_id': 'sensor.sun', 'valid': True}]
    before_revision, before_cursor = store.revision, store.cursor
    before_totals = store.totals(60, 'UTC')
    before_realtime, before_sources = service.realtime, service.sources.copy()
    before_days = list(map(tuple, store.db.execute('SELECT * FROM days')))
    before_observations = store.observations(0, 60, settings().entities, ORIGIN)
    service.forecast.configure(service.config, ENABLED, ORIGIN, LOCATION)
    service.forecast.configure(service.config, ENABLED.model_copy(update={'noct_c': 47.0}), ORIGIN, LOCATION)
    assert store.revision == before_revision
    assert store.cursor == before_cursor
    assert store.totals(60, 'UTC') == before_totals
    assert service.sources == before_sources
    assert service.realtime == before_realtime
    assert list(map(tuple, store.db.execute('SELECT * FROM days'))) == before_days
    assert store.observations(0, 60, settings().entities, ORIGIN) == before_observations
    store.close()


async def test_manual_refresh_coalesces_with_running_request(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def respond(request):
        requests.append(request)
        entered.set()
        await release.wait()
        return httpx.Response(200, json=hourly_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert forecast.request_refresh() is True
            refresh = asyncio.create_task(forecast.refresh(now=120))
            await asyncio.sleep(0)
            assert forecast.view(120).refreshing is True
            release.set()
            await refresh
            await asyncio.sleep(0)
            assert len(requests) == 1
            assert forecast.view(120).refreshing is False
        finally:
            await forecast.stop()
    store.close()


@pytest.mark.parametrize('field,value', [
    ('origin', 'http://new-ha.test'), ('latitude', 1.0), ('longitude', 1.0),
    ('timezone', 'Asia/Shanghai'), ('rated_power_w', 6000.0),
    ('temperature_coefficient_pct_per_c', -0.4), ('tilt_deg', 26.0),
    ('azimuth_deg', 181.0), ('noct_c', 46.0),
])
async def test_changed_inputs_discard_old_inflight_result(tmp_path, field, value):
    entered, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json=hourly_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        refresh = asyncio.create_task(forecast.refresh(now=120))
        await asyncio.wait_for(entered.wait(), 1)
        location = LOCATION.model_copy(update={field: value}) if field in {
            'origin', 'latitude', 'longitude', 'timezone',
        } else LOCATION
        config = settings(**{field: value}) if field in {
            'rated_power_w', 'temperature_coefficient_pct_per_c',
        } else settings()
        prediction = ENABLED.model_copy(update={field: value}) if field in {
            'tilt_deg', 'azimuth_deg', 'noct_c',
        } else ENABLED
        forecast.configure(config, prediction, location.origin, location)
        release.set()
        await refresh
        assert forecast.view(180).fetched_at is None
        assert store.get_meta('forecast_cache') is None
    store.close()


async def test_unchanged_configuration_does_not_restart_or_refetch(tmp_path):
    requests = []
    received = asyncio.Event()

    def respond(request):
        requests.append(request)
        received.set()
        return httpx.Response(200, json=hourly_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(received.wait(), 1)
            await asyncio.sleep(0)
            before_changes = store.db.total_changes
            task = forecast._task
            forecast.configure(settings(), ENABLED, ORIGIN, LOCATION)
            await forecast.start()
            await asyncio.sleep(0)
            assert forecast._task is task
            assert len(requests) == 1
            assert store.db.total_changes == before_changes
            assert forecast.view(120).fetched_at is not None
        finally:
            await forecast.stop()
    store.close()


async def test_success_failure_and_stale_deadlines(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from pvyieldlens import forecast_service

    clock = [0.0]
    delays = []
    scheduled = asyncio.Event()
    real_timeout = asyncio.timeout

    def timeout(delay):
        if delay is not None:
            delays.append(delay)
            scheduled.set()
        return real_timeout(None)

    def respond(request):
        if clock[0] >= 3600:
            raise httpx.ReadTimeout('weather timeout', request=request)
        clock[0] = 10.0
        return httpx.Response(200, json=hourly_payload(0))

    monkeypatch.setattr(forecast_service, 'time', SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(forecast_service.asyncio, 'timeout', timeout)
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(scheduled.wait(), 1)
            assert delays[-1] == pytest.approx(3600, abs=0.1)
            assert forecast.view(7199).status == 'ready'
            assert forecast.view(7210).status == 'stale'
            assert forecast.view(20).fetched_at == 10
            scheduled.clear()
            clock[0] = 3610
            assert forecast.request_refresh()
            await asyncio.wait_for(scheduled.wait(), 1)
            assert delays[-1] == pytest.approx(900, abs=0.1)
            assert forecast.view(3610).status == 'stale'
            assert forecast.view(3610).fetched_at == 10
            assert forecast.view(3610).last_error == 'forecast_fetch_failed'
        finally:
            await forecast.stop()
    store.close()


async def test_disabled_has_no_requests_and_keeps_parameters(tmp_path):
    requests = []
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=hourly_payload(0)),
    )) as http:
        forecast = controller(store, http)
        disabled = ENABLED.model_copy(update={'enabled': False})
        forecast.configure(settings(), disabled, ORIGIN, LOCATION)
        await forecast.start()
        await forecast.refresh(now=120)
        assert not forecast.request_refresh()
        await asyncio.sleep(0)
        assert requests == []
        assert store.forecast_settings() == disabled
        assert forecast.view(120).status == 'disabled'
        await forecast.stop()
    store.close()


async def test_midnight_reclips_cache_without_network_or_new_fetched_at(tmp_path):
    requests = []
    start = datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp()
    payload = hourly_payload(start, weather_code=0)
    payload['hourly']['weather_code'][24:48] = [61] * 24
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=payload),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=start + 86300)
        before = forecast.view(start + 86300)
        after = forecast.view(start + 86400 + 100)
        assert before.days[0].day == '2026-11-13'
        assert after.days[0].day == '2026-11-14'
        assert after.today.kwh == pytest.approx(89.28)
        assert after.remaining_today.kwh < after.today.kwh
        assert after.fetched_at == before.fetched_at == start + 86300
        assert before.days[0].weather.weather_code == 0
        assert after.days[0].weather.weather_code == 61
        assert len(requests) == 1
    store.close()


async def test_location_name_updates_do_not_invalidate_physical_cache(tmp_path):
    requests = []
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=hourly_payload(0)),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=120)
        forecast.configure(settings(), ENABLED, ORIGIN, LOCATION.model_copy(update={'location_name': 'New name'}))
        assert forecast.view(180).fetched_at == 120
        assert forecast.view(180).today.kwh == pytest.approx(89.28)
        assert HALocation.model_validate_json(store.get_meta('ha_location')).location_name == 'New name'
        assert len(requests) == 1
    store.close()


async def test_changed_inputs_hide_persisted_cache_after_restart(tmp_path):
    from pvyieldlens.forecast_service import ForecastController

    path = tmp_path / 'data.sqlite'
    store = Store(path)
    store.save_settings(settings(), 0, ORIGIN)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=hourly_payload(0)),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=120)
    store.save_settings(settings(rated_power_w=6000), 180, ORIGIN)
    store.close()
    store = Store(path)
    forecast = ForecastController(store)
    assert forecast.view(180).status == 'loading'
    assert forecast.view(180).fetched_at is None
    assert forecast.view(180).intervals == ()
    assert all(day.weather is None for day in forecast.view(180).days)
    assert store.cursor == 0
    store.close()


async def test_changed_running_inputs_refresh_after_old_result_is_discarded(tmp_path):
    entered, release, received = asyncio.Event(), asyncio.Event(), asyncio.Event()
    requests = []

    async def respond(request):
        requests.append(request)
        if len(requests) == 1:
            entered.set()
            await release.wait()
        else:
            received.set()
        return httpx.Response(200, json=hourly_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(entered.wait(), 1)
            forecast.configure(settings(rated_power_w=6000), ENABLED, ORIGIN, LOCATION)
            assert forecast.request_refresh()
            release.set()
            await asyncio.wait_for(received.wait(), 1)
            assert len(requests) == 2
            assert forecast.view(120).today.kwh == pytest.approx(107.136)
            assert forecast.batch.inputs.rated_power_w == 6000
        finally:
            await forecast.stop()
    store.close()


async def test_stop_cancels_running_fetch_and_keeps_injected_client_open(tmp_path):
    entered = asyncio.Event()

    async def respond(request):
        entered.set()
        await asyncio.Event().wait()

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        await asyncio.wait_for(entered.wait(), 1)
        await forecast.stop()
        assert forecast.view(120).refreshing is False
        assert forecast.view(120).fetched_at is None
        assert store.get_meta('forecast_cache') is None
        assert not http.is_closed
    store.close()


async def test_direct_refresh_failure_reschedules_sleeping_worker(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from pvyieldlens import forecast_service

    failed = False
    sleeping = asyncio.Event()
    delays = []
    real_timeout = asyncio.timeout

    def timeout(delay):
        if delay is not None:
            delays.append(delay)
            sleeping.set()
        return real_timeout(None)

    def respond(request):
        if failed:
            raise httpx.ReadTimeout('weather timeout', request=request)
        return httpx.Response(200, json=hourly_payload(0))

    monkeypatch.setattr(forecast_service, 'asyncio', SimpleNamespace(
        Event=asyncio.Event, get_running_loop=asyncio.get_running_loop,
        create_task=asyncio.create_task, current_task=asyncio.current_task,
        shield=asyncio.shield, timeout=timeout, CancelledError=asyncio.CancelledError,
    ))
    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(sleeping.wait(), 1)
            assert delays[-1] == pytest.approx(3600, abs=0.1)
            sleeping.clear()
            failed = True
            await forecast.refresh(now=120)
            await asyncio.wait_for(sleeping.wait(), 1)
            assert delays[-1] == pytest.approx(900, abs=0.1)
            assert forecast.view(120).status == 'stale'
        finally:
            await forecast.stop()
    store.close()


@pytest.mark.parametrize('background', [True, False])
async def test_disabling_cancels_inflight_weather_and_retains_parameters(tmp_path, background):
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    second_received = asyncio.Event()
    requests = []

    async def respond(request):
        requests.append(request)
        if len(requests) > 1:
            second_received.set()
            return httpx.Response(200, json=hourly_payload(0, poa_w_m2=400.0))
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(200, json=hourly_payload(0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        refresh = None
        if background:
            await forecast.start()
        else:
            refresh = asyncio.create_task(forecast.refresh(now=120))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            disabled = ENABLED.model_copy(update={'enabled': False})
            forecast.configure(settings(), disabled, ORIGIN, LOCATION)
            assert forecast.view(120).status == 'disabled'
            assert forecast.view(120).refreshing is False
            assert not forecast.request_refresh()
            await asyncio.wait_for(cancelled.wait(), 1)
            if refresh is not None:
                await refresh
            assert store.get_meta('forecast_cache') is None
            assert store.forecast_settings() == disabled
            assert not http.is_closed
            forecast.configure(settings(), ENABLED, ORIGIN, LOCATION)
            if background:
                await asyncio.wait_for(second_received.wait(), 1)
            else:
                await forecast.refresh(now=180)
            assert len(requests) == 2
            assert forecast.view(180).today.kwh == pytest.approx(46.74)
            assert forecast.view(180).refreshing is False
        finally:
            await forecast.stop()
    store.close()


async def test_reenabling_before_cancelled_fetch_unwinds_requests_new_weather(tmp_path):
    entered, second_entered = asyncio.Event(), asyncio.Event()
    release, second_release = asyncio.Event(), asyncio.Event()
    requests = []

    async def respond(request):
        requests.append(request)
        if len(requests) == 1:
            entered.set()
            await release.wait()
            return httpx.Response(200, json=hourly_payload(0))
        second_entered.set()
        await second_release.wait()
        return httpx.Response(200, json=hourly_payload(0, poa_w_m2=400.0))

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(entered.wait(), 1)
            forecast.configure(settings(), ENABLED.model_copy(update={'enabled': False}), ORIGIN, LOCATION)
            forecast.configure(settings(), ENABLED, ORIGIN, LOCATION)
            release.set()
            await asyncio.wait_for(second_entered.wait(), 1)
            assert forecast.view(120).fetched_at is None
            assert store.get_meta('forecast_cache') is None
            second_release.set()
            await forecast.refresh(now=180)
            assert len(requests) == 2
            assert forecast.view(180).today.kwh == pytest.approx(46.74)
            assert forecast.view(180).refreshing is False
        finally:
            await forecast.stop()
    store.close()


async def test_repeated_disabled_configuration_is_idempotent_during_cancellation_cleanup(tmp_path):
    entered, cancelling, release_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cleaned_up, second_received = asyncio.Event(), asyncio.Event()
    requests = []

    async def respond(request):
        requests.append(request)
        if len(requests) > 1:
            second_received.set()
            return httpx.Response(200, json=hourly_payload(0, poa_w_m2=400.0))
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelling.set()
            await release_cleanup.wait()
            cleaned_up.set()

    store = Store(tmp_path / 'data.sqlite')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        forecast = controller(store, http)
        await forecast.start()
        try:
            await asyncio.wait_for(entered.wait(), 1)
            disabled = ENABLED.model_copy(update={'enabled': False})
            forecast.configure(settings(), disabled, ORIGIN, LOCATION)
            await asyncio.wait_for(cancelling.wait(), 1)
            changes = store.db.total_changes
            forecast.configure(settings(), disabled, ORIGIN, LOCATION)
            forecast.configure(settings(), disabled, ORIGIN, LOCATION)
            assert store.db.total_changes == changes
            assert forecast.view(120).status == 'disabled'
            assert forecast.view(120).refreshing is False
            assert not cleaned_up.is_set()
            release_cleanup.set()
            await asyncio.wait_for(cleaned_up.wait(), 1)
            forecast.configure(settings(), ENABLED, ORIGIN, LOCATION)
            await asyncio.wait_for(second_received.wait(), 1)
            assert len(requests) == 2
            assert forecast.view(180).today.kwh == pytest.approx(46.74)
        finally:
            release_cleanup.set()
            await forecast.stop()
    store.close()


async def test_forecast_remaining_updates_without_new_weather(tmp_path):
    from pvyieldlens.home_assistant import entity_payloads
    from pvyieldlens.service import Service

    requests = []
    payload = hourly_payload(0)
    payload['hourly']['global_tilted_irradiance'] = [800.0] * 15 + [0.0] * 202
    store = Store(tmp_path / 'data.sqlite')
    service = Service(store)
    await service.configure(settings(), now=0, origin=ORIGIN)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json=payload),
    )) as http:
        service.forecast = controller(store, http)
        await service.forecast.refresh(now=48000)
        before = service.snapshot(48000)
        after = service.snapshot(49200)
        assert before['forecast']['remaining_today']['kwh'] == pytest.approx(2.48)
        assert after['forecast']['remaining_today']['kwh'] == pytest.approx(1.24)
        assert 'days' not in before['forecast']
        assert 'intervals' not in before['forecast']
        before_payload = entity_payloads(before)['sensor.pvyieldlens_forecast_energy_remaining_today']
        after_payload = entity_payloads(after)['sensor.pvyieldlens_forecast_energy_remaining_today']
        assert before_payload['state'] == '2.48'
        assert after_payload['state'] == '1.24'
        assert before_payload['attributes']['fetched_at'] == after_payload['attributes']['fetched_at'] == 48000
        assert before_payload['attributes']['calculated_at'] == 48000
        assert after_payload['attributes']['calculated_at'] == 49200
        assert after['forecast']['today']['kwh'] == before['forecast']['today']['kwh'] == pytest.approx(52.08)
        assert len(requests) == 1
    store.close()


async def test_legacy_forecast_cache_has_no_weather_until_refresh(tmp_path):
    from pvyieldlens.forecast_service import ForecastController
    store = Store(tmp_path / 'data.sqlite')
    store.save_settings(settings(), 0, ORIGIN)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=hourly_payload(0, weather_code=61)),
    )) as http:
        forecast = controller(store, http)
        await forecast.refresh(now=120)
        original_fetched_at = forecast.view(180).fetched_at
        original_today_kwh = forecast.view(180).today.kwh
        legacy = forecast.batch.model_dump_json(exclude={'weather_samples'})
        store.set_meta('forecast_cache', legacy)
        restored = ForecastController(store, OpenMeteoClient(http))
        legacy_view = restored.view(180)
        assert legacy_view.days[0].weather is None
        assert legacy_view.fetched_at == original_fetched_at
        assert legacy_view.today.kwh == original_today_kwh
        assert store.get_meta('forecast_cache') == legacy
        await restored.refresh(now=300)
        assert restored.view(360).days[0].weather.weather_code == 61
        assert restored.view(360).fetched_at == 300
        assert restored.view(360).today.kwh == original_today_kwh
    store.close()
