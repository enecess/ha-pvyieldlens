import os
import re
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1')


@pytest.fixture
async def timezone_page(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import pvyieldlens.web as web_module
    import pvyieldlens.service as service_module
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from playwright.async_api import async_playwright, expect
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app
    from pvyieldlens.engine import calculate
    from test_engine import samples, settings
    from test_forecast_browser import forecast_payload
    from test_integration import fake_server

    instant = datetime(2026, 11, 16, 5, tzinfo=timezone.utc)
    clock = SimpleNamespace(time=lambda: instant.timestamp())
    monkeypatch.setattr(web_module, 'time', clock)
    monkeypatch.setattr(service_module, 'time', clock)
    service = Service(Store(tmp_path / 'data.sqlite'))
    await service.configure(settings(home_timezone='Asia/Shanghai', update_interval_seconds=1), now=instant.timestamp() - 60)
    result = calculate(service.monitoring_settings, samples(at=instant.timestamp() - 60), instant.timestamp() - 60, instant.timestamp())
    service.store.settle(result, 1, 'Asia/Shanghai')
    service.live_window = result.public()
    view = forecast_payload('2026-11-16', 'Asia/Shanghai')
    view.update(fetched_at=instant.timestamp(), calculated_at=instant.timestamp())
    state = {'mode': 'app', 'forecast': 0, 'snapshots': 0, 'requests': []}
    web = create_app(service, Runtime(web_password='timezone-test'), run_background=False)
    parent = FastAPI()
    parent.mount('/api/hassio_ingress/timezone-test', web)
    async with fake_server(web) as standalone:
        @parent.get('/host')
        async def host():
            return HTMLResponse('''<!doctype html><html><body><home-assistant></home-assistant>
<script>document.querySelector('home-assistant').hass = {
locale: {language: 'en', number_format: 'language', time_format: '24', time_zone: 'local',
first_weekday: 'language', date_format: 'language'},
selectedTheme: {theme: 'default'}, themes: {darkMode: false}};</script>
<iframe id="app" src="/api/hassio_ingress/timezone-test/"></iframe></body></html>''')

        @parent.get('/unreadable')
        async def unreadable():
            return HTMLResponse(f'<!doctype html><html><body><iframe id="app" src="{standalone}/"></iframe></body></html>')

        async with fake_server(parent) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            context = await browser.new_context(locale='en-GB', timezone_id='America/Los_Angeles',
                                                http_credentials={'username': 'admin', 'password': 'timezone-test'})
            await context.add_init_script('''const Native = Intl.DateTimeFormat;
Intl.DateTimeFormat = function(locale, options) { return new Native(locale, {...options, hourCycle: 'h23'}); };
Intl.DateTimeFormat.prototype = Native.prototype;''')
            page = await context.new_page()
            page.set_default_timeout(5000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))

            async def config(route):
                response = await route.fetch()
                payload = await response.json()
                payload['mode'] = state['mode']
                await route.fulfill(response=response, json=payload)

            async def snapshot(route):
                state['snapshots'] += 1
                payload = service.snapshot(now=instant.timestamp())
                payload.update(calculated_at=instant.timestamp(),
                               forecast={key: value for key, value in view.items() if key not in ('days', 'intervals')})
                payload['energy_totals'].update(estimated_energy_today_kwh=3.25, estimated_energy_lifetime_kwh=123.5)
                await route.fulfill(json=payload)

            async def forecast(route):
                state['forecast'] += 1
                await route.fulfill(json=view)

            await context.route('**/api/config', config)
            await context.route('**/api/snapshot', snapshot)
            await context.route('**/api/forecast', forecast)
            page.on('request', lambda request: state['requests'].append(request.method + ' ' + request.url)
                    if '/api/' in request.url else None)
            await page.add_init_script(f'Date.now = () => {instant.timestamp() * 1000}')
            await page.goto(url + '/host')
            app = page.frame_locator('#app')
            await expect(app.locator('main')).to_have_attribute('data-snapshot-ready', 'true')
            yield page, app, state, url, standalone
            assert errors == []
            await browser.close()
    service.store.close()


async def test_viewer_timezone_keeps_household_forecast_day(timezone_page):
    from playwright.async_api import expect

    page, app, state, _, _ = timezone_page
    await page.set_viewport_size({'width': 1440, 'height': 1100})
    await page.locator('#app').evaluate("node => { node.style.width = 'calc(100vw - 32px)'; node.style.height = '1800px'; }")
    monitoring_clock = re.search(r'\d{2}:\d{2}', await app.locator('#updated').inner_text()).group()
    assert monitoring_clock == '21:00'

    await app.locator('#history-tab').click()
    await app.locator('#history-range').select_option('7d')
    await expect(app.locator('#history-boundaries')).to_contain_text('Nov 15, 2026, 21:00')
    await expect(app.locator('#last-settled')).to_contain_text('21:00')
    await expect(app.locator('#history-home-timezone')).to_contain_text('Asia/Shanghai')
    await expect(app.locator('#daily-energy-chart [aria-current=date]')).to_have_attribute('data-day', '2026-11-16')
    totals_before = [await app.locator(selector).inner_text() for selector in ('#history-actual-energy', '#history-energy')]
    await app.locator('#forecast-tab').click()
    await expect(app.locator('#forecast-days button')).to_have_count(7)
    forecast_selected_day = await app.locator('#forecast-days [aria-pressed=true]').get_attribute('data-day')
    assert forecast_selected_day == '2026-11-16'
    await app.locator('#forecast-details summary').click()
    forecast_hour_clock = await app.locator('#forecast-rows tr').nth(13).locator('time').first.inner_text()
    assert forecast_hour_clock == '13:00'
    fetched = re.search(r'[A-Z][a-z]{2} \d{1,2}, \d{4}', await app.locator('#forecast-fetched').inner_text()).group()
    fetched_date = datetime.strptime(fetched, '%b %d, %Y').date().isoformat()
    assert fetched_date == '2026-11-15'
    await expect(app.locator('#forecast-home-time-note')).to_contain_text('Asia/Shanghai')
    await expect(app.locator('#forecast-days [aria-current=date]')).to_have_attribute('data-day', '2026-11-16')
    await expect(app.locator('#forecast-days [aria-current=date] .day-label')).to_have_text('Today')
    from pathlib import Path
    evidence = Path('artifacts/task-5-weather')
    evidence.mkdir(parents=True, exist_ok=True)
    await app.locator('#forecast-details summary').click()
    await app.locator('#forecast-page').screenshot(path=str(evidence / 'timezone-shanghai-los-angeles.png'))
    await expect(app.locator('#forecast-timezone, #timezone-note')).to_have_count(0)
    assert 'GMT' not in await app.locator('#forecast-rows').inner_text()
    assert 'Asia/Shanghai' not in await app.locator('#live-page').inner_text()
    await app.locator('[data-day="2026-11-18"]').click()
    await app.locator('#settings-button').click()
    await app.locator('[data-settings-category=modules]').click()
    await app.locator('[name=total_max_power_at_stc_w]').fill('6100')
    await expect(app.locator('#home-timezone')).to_contain_text('Home time zone')
    forecast_fetch_count_before = state['forecast']
    requests_before = len(state['requests'])
    snapshot_count_before = state['snapshots']
    await page.evaluate("document.querySelector('home-assistant').hass.locale.time_zone = 'server'")
    async with page.expect_response('**/api/snapshot'):
        pass
    await expect(app.locator('#updated')).to_contain_text('13:00')
    await expect(app.locator('#history-boundaries')).to_contain_text('Nov 16, 2026, 13:00')
    await expect(app.locator('#last-settled')).to_contain_text('13:00')
    await expect(app.locator('#forecast-home-time-note')).to_have_count(0)
    await expect(app.locator('[name=total_max_power_at_stc_w]')).to_have_value('6100')
    await expect(app.locator('#history-range')).to_have_value('7d')
    await expect(app.locator('[data-day="2026-11-18"]')).to_have_attribute('aria-pressed', 'true')
    totals_after = [await app.locator(selector).inner_text() for selector in ('#history-actual-energy', '#history-energy')]
    forecast_fetch_count_after = state['forecast']
    assert totals_after == totals_before
    assert forecast_fetch_count_after == forecast_fetch_count_before
    assert len(state['requests']) - requests_before == state['snapshots'] - snapshot_count_before
    assert not any(request.startswith(('PUT ', 'POST ')) for request in state['requests'][requests_before:])


@pytest.mark.parametrize(('destination', 'mode', 'clock'), [('standalone', 'docker', '21:00'), ('unreadable', 'app', '13:00')])
async def test_timezone_fallback_keeps_household_context(timezone_page, destination, mode, clock):
    from playwright.async_api import expect

    page, _, state, url, standalone = timezone_page
    state['mode'] = mode
    await page.goto(standalone if destination == 'standalone' else url + '/unreadable')
    app = page if destination == 'standalone' else page.frame_locator('#app')
    await expect(app.locator('#updated')).to_contain_text(clock)
    await app.locator('#forecast-tab').click()
    await expect(app.locator('#forecast-days [aria-pressed=true]')).to_have_attribute('data-day', '2026-11-16')
    await app.locator('#forecast-details summary').click()
    await expect(app.locator('#forecast-rows tr').nth(13).locator('time').first).to_have_text('13:00')
