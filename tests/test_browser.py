import asyncio
import os
import time

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1 after installing Playwright Chromium')


async def test_data_pages_and_gear_settings_preserve_context(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    history_requests = []
    page.on('request', lambda request: history_requests.append(request.url) if '/api/history?' in request.url else None)
    await expect(page.locator('#live-page')).to_be_visible()
    await expect(page.locator('#history-page')).to_be_hidden()
    await expect(page.locator('#forecast-page')).to_be_hidden()
    assert history_requests == []
    await page.locator('#history-tab').click()
    await page.locator('#history-range').select_option('7')
    await page.locator('#settings-button').click()
    await expect(page.locator('#configuration')).to_be_visible()
    await expect(page.locator('#data-navigation')).to_be_hidden()
    await expect(page.locator('#settings-back')).to_have_text('← Back to History')
    await page.locator('button[data-settings-category=panels]').click()
    await page.locator('[name=temperature_coefficient_pct_per_c]').fill('-0.4')
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[data-settings-section=panels]')).to_be_hidden()
    await expect(page.locator('[data-settings-section=forecast]')).to_be_visible()
    await page.locator('#settings-back').click()
    await expect(page.locator('#history-page')).to_be_visible()
    await expect(page.locator('#history-range')).to_have_value('7')
    await expect(page.locator('#draft-status')).to_have_text('Unsaved changes')
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#forecast-page')).to_be_visible()
    await expect(page.locator('#live-page')).to_be_hidden()
    await expect(page.locator('#history-page')).to_be_hidden()
    await page.locator('#settings-button').click()
    await expect(page.locator('#settings-back')).to_have_text('← Back to Forecast')
    await page.locator('button[data-settings-category=panels]').click()
    await expect(page.locator('[name=temperature_coefficient_pct_per_c]')).to_have_value('-0.4')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.config.temperature_coefficient_pct_per_c == -0.4
    await expect(page.locator('#ha-token')).to_have_value('')
    await expect(page.locator('#draft-status')).to_be_hidden()


@pytest.mark.parametrize('width', [700, 768])
async def test_french_tablet_settings_returns_to_selected_history_range(browser_workspace, width):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.locator('#language-select').select_option('fr')
    await page.locator('#history-tab').click()
    await page.locator('#history-range').select_option('7')
    await page.locator('#settings-button').click()
    await expect(page.locator('#configuration')).to_be_visible()
    await expect(page.locator('#data-navigation')).to_be_hidden()
    await expect(page.locator('#settings-back')).to_have_text('← Retour à Historique')
    await page.locator('button[data-settings-category=panels]').click()
    await page.locator('[name=rated_power_w]').fill('6000')
    await page.locator('#settings-back').click()
    await expect(page.locator('#history-page')).to_be_visible()
    await expect(page.locator('#history-range')).to_have_value('7')
    await expect(page.locator('#draft-status')).to_have_text('Modifications non enregistrées')
    assert await page.evaluate('scrollX') == 0


@pytest.mark.parametrize('browser_workspace', [False], indirect=True)
async def test_settings_reveals_first_invalid_category(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#open-settings').click()
    await page.locator('button[data-settings-category=panels]').click()
    await page.locator('[name=rated_power_w]').fill('5000')
    await page.locator('[name=temperature_coefficient_pct_per_c]').fill('-0.35')
    await page.locator('button[data-settings-category=forecast]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('button[data-settings-category=sources]')).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('[name=power_entity]')).to_be_focused()
    assert service.config is None
    await page.locator('[name=power_entity]').fill('sensor.power')
    await page.locator('[name=temperature_entity]').fill('sensor.temp')
    await page.locator('[name=irradiance_entity]').fill('sensor.sun')
    await page.locator('button[data-settings-category=forecast]').click()
    await page.locator('[name=forecast_enabled]').check()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_tilt_deg]')).to_be_focused()
    await expect(page.locator('[data-settings-section=forecast]')).to_be_visible()


async def test_forecast_settings_round_trip_and_server_error_category(browser_workspace):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('45')
    await page.locator('[name=forecast_enabled]').check()
    await page.locator('[name=forecast_tilt_deg]').fill('25')
    await page.locator('#forecast-direction').select_option('180')
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_have_value('180')
    await page.locator('#forecast-direction').select_option('custom')
    await page.locator('[name=forecast_azimuth_deg]').fill('360')
    await page.locator('button[data-settings-category=panels]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_be_focused()
    await expect(page.locator('#save-result')).to_be_empty()
    await page.locator('[name=forecast_azimuth_deg]').fill('123.5')
    await page.locator('[name=forecast_noct_c]').fill('20')
    await page.locator('button[data-settings-category=panels]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_be_focused()
    await expect(page.locator('#save-result')).to_be_empty()
    await page.locator('[name=forecast_noct_c]').fill('46')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.forecast.settings.model_dump() == {'enabled': True, 'tilt_deg': 25, 'azimuth_deg': 123.5, 'noct_c': 46}
    await page.reload()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('46')
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_have_value('123.5')
    await expect(page.locator('#forecast-direction')).to_have_value('custom')
    await page.locator('[name=forecast_enabled]').uncheck()
    await page.locator('[name=forecast_tilt_deg]').fill('')
    await page.locator('[name=forecast_azimuth_deg]').fill('')
    await page.locator('#save-button').click()
    await expect(page.locator('#save-result')).to_have_text('Configuration saved')
    assert service.forecast.settings.tilt_deg is None and service.forecast.settings.azimuth_deg is None
    await page.reload()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('46')
    await page.locator('#settings-button').click()
    await page.locator('button[data-settings-category=forecast]').click()
    await expect(page.locator('[name=forecast_enabled]')).not_to_be_checked()
    await expect(page.locator('[name=forecast_tilt_deg]')).to_have_value('')
    await expect(page.locator('[name=forecast_azimuth_deg]')).to_have_value('')
    await expect(page.locator('#forecast-direction')).to_have_value('')
    await page.route('**/api/config', lambda route: route.fulfill(status=422, json={
        'error': 'invalid_configuration', 'fields': ['settings.power_max_age_seconds']}))
    await page.locator('#save-button').click()
    await expect(page.locator('button[data-settings-category=monitoring]')).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('[name=power_max_age_seconds]')).to_be_focused()
    await expect(page.locator('#monitoring-advanced')).to_have_attribute('open', '')


async def test_locales_storage_fallback_and_ingress(browser_workspace):
    from playwright.async_api import expect
    from fastapi import FastAPI
    from test_integration import fake_server

    page, _, web = browser_workspace
    for locale, language in [('zh-CN', 'zh'), ('fr-CA', 'fr'), ('pl-PL', 'pl'), ('it-IT', 'it'), ('es-ES', 'en')]:
        await page.evaluate("locale => {Object.defineProperty(navigator, 'languages', {get: () => [locale], configurable: true}); window.dispatchEvent(new Event('languagechange'));}", locale)
        await expect(page.locator('html')).to_have_attribute('lang', language)
    await page.locator('#language-select').select_option('fr')
    await page.reload()
    await expect(page.locator('html')).to_have_attribute('lang', 'fr')
    await page.locator('#language-select').select_option('auto')
    blocked = await page.context.new_page()
    await blocked.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Blocked', 'SecurityError')}})")
    await blocked.goto(page.url)
    await expect(blocked.locator('[name=rated_power_w]')).to_have_value('5000')
    await blocked.locator('#language-select').select_option('zh')
    await expect(blocked.locator('html')).to_have_attribute('lang', 'zh')
    await blocked.close()
    ingress = FastAPI()
    # The running app is mounted through a relative Ingress prefix.
    ingress.mount('/api/hassio_ingress/test-prefix', web)
    async with fake_server(ingress) as url:
        await page.goto(url + '/api/hassio_ingress/test-prefix/')
        await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
        await page.locator('#history-tab').click()
        await expect(page.locator('#history-chart .chart-empty')).to_be_visible()
        await page.locator('#settings-button').click()
        await expect(page.locator('#power-options option')).to_have_attribute('value', 'sensor.power')


@pytest.fixture
async def browser_workspace(tmp_path, request):
    from playwright.async_api import async_playwright, expect
    from test_engine import settings
    from test_integration import fake_server
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    service = Service(Store(tmp_path / 'data.sqlite'))
    if getattr(request, 'param', True):
        await service.configure(settings(interval_minutes=1, update_seconds=1))
    async with fake_server() as ha_url:
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url, ha_token='simulation-token'), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            context = await browser.new_context(locale='en-US', http_credentials={'username': 'admin', 'password': 'browser-test'})
            page = await context.new_page()
            page.set_default_timeout(5000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(url)
            await expect(page.locator('#live-hint')).not_to_be_empty()
            yield page, service, web
            assert errors == []
            await browser.close()
    service.store.close()


async def test_rolling_history_refreshes_only_when_complete_window_membership_changes(tmp_path):
    from playwright.async_api import async_playwright, expect
    from test_engine import samples, settings
    from test_integration import fake_server
    from pvyieldlens.engine import calculate
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    service = Service(Store(tmp_path / 'data.sqlite'))
    now = int(time.time())
    start = now - 86400
    config = settings(interval_minutes=1, update_seconds=1)
    await service.configure(config, now=start)
    for offset, power in [(0, 1000), (60, 2000), (120, 3000)]:
        service.store.settle(calculate(config, samples(power=power, at=start+offset),
                                      start+offset, start+offset+60), 1, 'UTC')
    service._mark_offline()
    web = create_app(service, Runtime(web_password='browser-test'), run_background=False)
    async with fake_server(web) as url, async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=['--no-sandbox'])
        page = await browser.new_page(http_credentials={'username':'admin','password':'browser-test'})
        await page.add_init_script(f'window.testNow = {now * 1000}; Date.now = () => window.testNow;')
        history_requests = []
        errors = []
        page.on('request', lambda request: history_requests.append(request.url) if '/api/history?' in request.url else None)
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def advance_clock(seconds):
            await page.evaluate('now => { window.testNow = now; }', (now+seconds)*1000)
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass

        await page.goto(url)
        await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
        await page.locator('#history-tab').click()
        await expect(page.locator('#history-chart svg')).to_be_visible()
        charts = page.locator('#history-chart svg, #pr-chart svg')
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'initial')")
        actual_y = await page.locator('#history-chart path.series').nth(1).evaluate(
            "path => path.getAttribute('d').match(/[ML][\\d.]+,[\\d.]+/g).map(command => Number(command.split(',')[1]))")
        assert len(actual_y) == 3
        initial_requests = len(history_requests)
        await advance_clock(0)
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['initial', 'initial']
        assert len(history_requests) == initial_requests

        # A straddling window is excluded from both the summary and chart.
        await advance_clock(90)
        await expect(charts.first).not_to_have_attribute('data-original', 'initial')
        assert await page.locator('#history-chart path.series').nth(1).evaluate(
            "path => path.getAttribute('d').match(/[ML][\\d.]+,[\\d.]+/g).map(command => Number(command.split(',')[1]))") == actual_y[2:]
        assert await page.locator('#pr-chart path.series').evaluate(
            "path => path.getAttribute('d').match(/[ML]/g).length") == 1
        assert len(history_requests) == initial_requests + 1
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'remaining')")
        await advance_clock(100)
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['remaining', 'remaining']

        # A window ending exactly at the rolling start no longer overlaps the range.
        await advance_clock(180)
        await expect(charts).to_have_count(0)
        empty = page.locator('#history-chart .chart-empty, #pr-chart .chart-empty')
        await expect(empty).to_have_count(2)
        await empty.evaluate_all("nodes => nodes.forEach(node => node.dataset.original = 'empty')")
        await advance_clock(210)
        assert await empty.evaluate_all('nodes => nodes.map(node => node.dataset.original)') == ['empty', 'empty']
        assert len(history_requests) == initial_requests + 2

        async with page.expect_response(lambda response: '/api/history?' in response.url):
            await page.locator('#history-range').select_option('7')
        await expect(charts).to_have_count(2)
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'hidden')")
        await page.locator('#settings-button').click()
        await advance_clock(6*86400+180)
        assert len(history_requests) == initial_requests+3
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['hidden', 'hidden']
        async with page.expect_response(lambda response: '/api/history?' in response.url):
            await page.locator('#settings-back').click()
        await expect(charts).to_have_count(0)
        assert len(history_requests) == initial_requests+4
        assert errors == []
        await browser.close()
    service.store.close()

@pytest.mark.parametrize(('mode', 'pending_configuration', 'edited_connection'), [
    ('docker', False, False), ('app', False, False), ('docker', True, False),
    ('app', True, False), ('docker', True, True),
])
async def test_settings_discovers_once_and_preserves_edits(tmp_path, mode, pending_configuration, edited_connection):
    from playwright.async_api import async_playwright, expect
    from test_engine import settings
    from test_integration import fake_server
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    async with fake_server() as ha_url:
        service = Service(Store(tmp_path / 'data.sqlite'))
        await service.configure(settings(interval_minutes=1, update_seconds=1))
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url,
                                         ha_token='simulation-token'), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(locale='en-US',
                                          http_credentials={'username':'admin', 'password':'browser-test'})
            config_requested = asyncio.Event()
            config_ready = asyncio.Event()
            discovery_ready = asyncio.Event()
            requests = []
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))

            async def configuration(route):
                response = await route.fetch()
                body = await response.json()
                body['mode'] = mode
                config_requested.set()
                if pending_configuration:
                    await config_ready.wait()
                await route.fulfill(response=response, json=body)

            async def discovery(route):
                requests.append(route.request.post_data_json)
                await discovery_ready.wait()
                await route.continue_()

            await page.route('**/api/config', configuration)
            await page.route('**/api/connection', discovery)
            await page.goto(url, wait_until='domcontentloaded')
            await asyncio.wait_for(config_requested.wait(), 10)
            if not pending_configuration:
                await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
                async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                    pass
            assert requests == []
            await expect(page.locator('#power-options option')).to_have_count(0)
            await page.locator('#settings-button').click()
            await page.locator('button[data-settings-category=sources]').click()
            await page.locator('[name=power_entity]').fill('sensor.typed_power')
            await page.locator('button[data-settings-category=panels]').click()
            await page.locator('[name=temperature_coefficient_pct_per_c]').fill('-0.4')
            if edited_connection:
                await page.locator('button[data-settings-category=connection]').click()
                await page.locator('#ha-url').fill(ha_url + '/')
                await page.locator('#ha-token').fill('simulation-token')
            config_ready.set()
            await expect(page.locator('#load-entities')).to_be_disabled()
            await expect(page.locator('[name=power_entity]')).to_have_value('sensor.typed_power')
            await expect(page.locator('[name=temperature_coefficient_pct_per_c]')).to_have_value('-0.4')
            await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
            await expect(page.locator('[name=temperature_entity]')).to_have_value('sensor.temp')
            await expect(page.locator('[name=irradiance_entity]')).to_have_value('sensor.sun')
            await expect(page.locator('[name=interval_minutes]')).to_have_value('1')
            unsaved = await page.locator('#settings-form').evaluate('form => [...new FormData(form)]')
            await page.locator('#settings-back').click()
            await page.locator('#settings-button').click()
            await page.locator('#language-select').select_option('fr')
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            assert requests == [None if mode == 'app' else {
                'url':ha_url + '/' if edited_connection else ha_url,
                'token':'simulation-token' if edited_connection else '',
            }]
            await expect(page.locator('#ha-url')).to_have_value(ha_url + '/' if edited_connection else ha_url)
            await expect(page.locator('#ha-token')).to_have_value('simulation-token' if edited_connection else '')
            assert await page.locator('#settings-form').evaluate('form => [...new FormData(form)]') == unsaved
            discovery_ready.set()
            await expect(page.locator('#load-entities')).to_be_enabled()
            for role, entity in [('power', 'sensor.power'), ('temperature', 'sensor.temp'), ('irradiance', 'sensor.sun')]:
                await expect(page.locator(f'#{role}-options option')).to_have_attribute('value', entity)
            await page.locator('#settings-back').click()
            await page.locator('#settings-button').click()
            await page.locator('#language-select').select_option('en')
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            assert len(requests) == 1
            assert await page.locator('#settings-form').evaluate('form => [...new FormData(form)]') == unsaved
            await page.locator('button[data-settings-category=connection]').click()
            if mode == 'docker':
                await page.locator('#ha-url').fill(ha_url + '/')
                await page.locator('#ha-token').fill('simulation-token')
            async with page.expect_response(lambda response: response.url.endswith('/api/connection')):
                await page.locator('#load-entities').click()
            await expect(page.locator('#load-entities')).to_be_enabled()
            assert requests == [
                None if mode == 'app' else {
                    'url':ha_url + '/' if edited_connection else ha_url,
                    'token':'simulation-token' if edited_connection else '',
                },
                None if mode == 'app' else {'url':ha_url + '/', 'token':'simulation-token'},
            ]
            assert await page.locator('#settings-form').evaluate(
                "form => [...new FormData(form)].filter(([key]) => key.endsWith('_entity') || key === 'temperature_coefficient_pct_per_c')"
            ) == [entry for entry in unsaved if entry[0].endswith('_entity') or entry[0] == 'temperature_coefficient_pct_per_c']
            assert errors == []
            await browser.close()
        service.store.close()


@pytest.mark.parametrize(('selector', 'typed_value'), [
    ('[name=power_entity]', 'sensor.cleared_power'), ('#ha-url', 'http://edited.invalid:8123'),
    ('[name=forecast_tilt_deg]', '12.5'), ('[name=forecast_azimuth_deg]', '123.5'), ('[name=forecast_noct_c]', '50'),
])
async def test_settings_pending_configuration_preserves_cleared_field(tmp_path, selector, typed_value):
    from pvyieldlens.settings import ForecastSettings
    from playwright.async_api import async_playwright, expect
    from test_engine import settings
    from test_integration import fake_server
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    async with fake_server() as ha_url:
        service = Service(Store(tmp_path / 'data.sqlite'))
        await service.configure(settings(interval_minutes=1, update_seconds=1))
        service.forecast.configure(service.config, ForecastSettings(enabled=True, tilt_deg=25, azimuth_deg=180), service.origin, None)
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url,
                                         ha_token='simulation-token'), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(locale='en-US',
                                          http_credentials={'username':'admin', 'password':'browser-test'})
            config_requested = asyncio.Event()
            config_ready = asyncio.Event()

            async def configuration(route):
                response = await route.fetch()
                config_requested.set()
                await config_ready.wait()
                await route.fulfill(response=response)

            await page.route('**/api/config', configuration)
            await page.goto(url, wait_until='domcontentloaded')
            await asyncio.wait_for(config_requested.wait(), 10)
            await page.locator('#settings-button').click()
            await page.locator('button[data-settings-category=forecast]' if 'forecast_' in selector else 'button[data-settings-category=sources]' if selector.startswith('[name=') else 'button[data-settings-category=connection]').click()
            if 'azimuth' in selector:
                await page.locator('#forecast-direction').select_option('custom')
            await page.locator(selector).fill(typed_value)
            await page.locator(selector).fill('')
            await page.locator('button[data-settings-category=forecast]').click()
            await page.locator('#settings-back').click()
            await page.locator('#history-tab').click()
            await page.locator('#settings-button').click()
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                config_ready.set()
            await expect(page.locator(selector)).to_have_value('')
            await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
            await expect(page.locator('[name=temperature_entity]')).to_have_value('sensor.temp')
            await expect(page.locator('[name=irradiance_entity]')).to_have_value('sensor.sun')
            await expect(page.locator('[name=interval_minutes]')).to_have_value('1')
            await expect(page.locator('[name=temperature_coefficient_pct_per_c]')).to_have_value('-0.35')
            if selector == '[name=power_entity]':
                await expect(page.locator('#ha-url')).to_have_value(ha_url)
            else:
                await expect(page.locator('[name=power_entity]')).to_have_value('sensor.power')
            await browser.close()
        service.store.close()


@pytest.mark.parametrize('saved_credentials', [False, True])
async def test_settings_first_connection_failure_keeps_polling_and_allows_retry(tmp_path, saved_credentials):
    from playwright.async_api import async_playwright, expect
    from test_engine import settings
    from test_integration import fake_server
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    async with fake_server() as ha_url:
        service = Service(Store(tmp_path / 'data.sqlite'))
        await service.configure(settings(update_seconds=1))
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url,
                                         ha_token='simulation-token' if saved_credentials else ''), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(locale='en-US',
                                          http_credentials={'username':'admin', 'password':'browser-test'})
            fail_ready = asyncio.Event()
            requests = []

            async def discovery(route):
                requests.append(route.request.post_data_json)
                if len(requests) == 1:
                    await fail_ready.wait()
                    await route.fulfill(status=502, json={'error':'ha_connection_failed'})
                else:
                    await route.continue_()

            await page.route('**/api/connection', discovery)
            await page.goto(url)
            await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
            await page.locator('#settings-button').click()
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            if not saved_credentials:
                assert requests == []
                await expect(page.locator('#power-options option')).to_have_count(0)
                await page.locator('#ha-url').fill(ha_url)
                await page.locator('#ha-token').fill('simulation-token')
                await page.locator('#load-entities').click()
            await expect(page.locator('#load-entities')).to_be_disabled()
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            assert requests == [{'url':ha_url, 'token':'' if saved_credentials else 'simulation-token'}]
            fail_ready.set()
            await expect(page.locator('#connection-result')).to_contain_text('Cannot reach Home Assistant')
            await expect(page.locator('#load-entities')).to_be_enabled()
            await expect(page.locator('#power-options option')).to_have_count(0)
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            async with page.expect_response(lambda response: response.url.endswith('/api/connection')):
                if saved_credentials:
                    await page.locator('#settings-back').click()
                    await page.locator('#settings-button').click()
                else:
                    await page.locator('#load-entities').click()
            await expect(page.locator('#power-options option')).to_have_attribute('value', 'sensor.power')
            assert requests == [{'url':ha_url, 'token':'' if saved_credentials else 'simulation-token'}] * 2
            await expect(page.locator('#ha-url')).to_have_value(ha_url)
            await expect(page.locator('#ha-token')).to_have_value('' if saved_credentials else 'simulation-token')
            await browser.close()
        service.store.close()
