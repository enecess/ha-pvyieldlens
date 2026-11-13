import asyncio
import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1 after installing Playwright Chromium')


async def test_dashboard_configuration_locales_and_mobile(tmp_path):
    from playwright.async_api import async_playwright, expect
    from fake_ha import source_states
    from test_integration import fake_server
    from test_engine import settings
    from pvyieldlens.home_assistant import HAState, parse_state
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    async with fake_server() as ha_url:
        service = Service(Store(tmp_path / 'data.sqlite'))
        now = time.time()
        await service.configure(settings(interval_minutes=1, update_seconds=1, timezone='Asia/Shanghai'), now=now-1800)
        service.store.add_observations([point for at in range(int(now)-1800,int(now)+1,10)
            for raw,role in zip(source_states(at),('power','temperature','irradiance'))
            for point in parse_state(HAState.model_validate(raw),role)])
        await service.tick(now)
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url, ha_token='simulation-token'))
        async with fake_server(web, lifespan='on') as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(args=['--no-sandbox'])
            context = await browser.new_context(locale='en-US', viewport={'width':1440,'height':1080},
                                                 http_credentials={'username':'admin','password':'browser-test'})
            page = await context.new_page()
            errors = []
            history_requests = []
            page.on('request', lambda request: history_requests.append(request.url) if '/api/history?' in request.url else None)
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(url)
            await expect(page.locator('#live-pr')).to_have_text('90', timeout=15000)
            await expect(page.locator('#history-chart svg')).to_be_visible()
            stable_snapshot = service.snapshot(now)
            await page.route('**/api/snapshot', lambda route: route.fulfill(json=stable_snapshot))
            await page.locator('#history-chart svg').evaluate("svg => svg.dataset.original = 'yes'")
            initial_requests = len(history_requests)
            await page.evaluate('Date.now = (() => { const now = Date.now; return () => now() + 31000; })()')
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            await expect(page.locator('#history-chart svg')).to_have_attribute('data-original', 'yes')
            assert len(history_requests) == initial_requests
            stable_snapshot['energy']['daily_complete'] = False
            await expect(page.locator('#banner')).to_contain_text("Today's energy is incomplete")
            stable_snapshot['energy']['daily_complete'] = True
            await expect(page.locator('#banner')).to_be_hidden()
            artifacts = Path('artifacts')
            artifacts.mkdir(exist_ok=True)
            await page.screenshot(path=str(artifacts/'dashboard-desktop.png'), full_page=True)
            dashboard_width = (await page.locator('#dashboard').bounding_box())['width']
            assert dashboard_width <= 1200
            updated = await page.locator('#updated').inner_text()
            stable_snapshot['calculated_at'] += 1
            await page.get_by_role('button', name='Settings', exact=True).click()
            await expect(page.locator('#updated')).not_to_have_text(updated)
            await page.evaluate('Date.now = (() => { const now = Date.now; return () => now() + 31000; })()')
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            assert len(history_requests) == initial_requests
            await expect(page.locator('#history-chart svg')).to_have_attribute('data-original', 'yes')
            async with page.expect_response(lambda response: '/api/history?' in response.url):
                assert await page.locator('#overview-tab').evaluate(
                    "button => { button.click(); const charts = [...document.querySelectorAll('#dashboard svg')]; return charts.length === 3 && charts.every(chart => chart.viewBox.baseVal.width > 0 && chart.viewBox.baseVal.height > 0); }")
            await expect(page.locator('#history-chart svg')).not_to_have_attribute('data-original', 'yes')
            assert len(history_requests) == initial_requests + 1
            async with page.expect_response(lambda response: '/api/history?' in response.url):
                await page.locator('#history-range').select_option('7')
            assert len(history_requests) == initial_requests + 2
            stable_snapshot['statistics'] = {**stable_snapshot['statistics'], 'end': stable_snapshot['statistics']['end'] + 60}
            async with page.expect_response(lambda response: '/api/history?' in response.url):
                pass
            assert len(history_requests) == initial_requests + 3
            await page.locator('#history-chart svg').evaluate("svg => svg.dataset.original = 'language'")
            await page.locator('#language-select').select_option('fr')
            await expect(page.locator('#history-chart svg')).not_to_have_attribute('data-original', 'language')
            await page.locator('#language-select').select_option('auto')
            await page.locator('#history-chart svg').evaluate("svg => svg.dataset.original = 'size'")
            await page.set_viewport_size({'width':1200, 'height':900})
            await expect(page.locator('#history-chart svg')).not_to_have_attribute('data-original', 'size')
            await page.locator('#history-chart svg').evaluate("svg => svg.dataset.original = 'restore-size'")
            await page.set_viewport_size({'width':1440, 'height':1080})
            await expect(page.locator('#history-chart svg')).not_to_have_attribute('data-original', 'restore-size')
            await page.locator('#history-chart svg').evaluate("svg => svg.dataset.original = 'same-page'")
            await page.locator('#overview-tab').click()
            await expect(page.locator('#history-chart svg')).to_have_attribute('data-original', 'same-page')
            assert len(history_requests) == initial_requests + 3
            await page.unroute('**/api/snapshot')
            await page.locator('#settings-tab').click()
            assert (await page.locator('#configuration').bounding_box())['width'] == dashboard_width
            await page.screenshot(path=str(artifacts/'configuration-desktop.png'), full_page=True)
            coefficient = page.locator('[name=temperature_coefficient_pct_per_c]')
            await coefficient.fill('-0.4')
            await page.locator('#language-select').select_option('fr')
            await expect(page.locator('html')).to_have_attribute('lang','fr')
            await page.evaluate("Object.defineProperty(navigator,'languages',{get:()=>['de-DE'],configurable:true}); window.dispatchEvent(new Event('languagechange'))")
            await expect(page.locator('html')).to_have_attribute('lang','fr')
            await expect(coefficient).to_have_value('-0.4')
            await page.locator('#language-select').select_option('auto')
            await expect(coefficient).to_have_value('-0.4')
            await expect(coefficient.locator('..')).to_contain_text('%/°C')
            await page.locator('#load-entities').click()
            await expect(page.locator('#connection-result')).to_have_text('Verbindung geprüft')
            await coefficient.fill('-0.35')
            await page.locator('#save-button').click()
            await expect(page.locator('#save-result')).to_have_text('Konfiguration gespeichert')
            assert service.config.temperature_coefficient_pct_per_c == -0.35
            await expect(page.locator('#connection-state')).to_have_class('connection-badge online',timeout=10000)
            await page.locator('#language-select').select_option('fr')
            await expect(page.locator('#save-result')).to_have_text('Configuration enregistrée')
            await expect(page.locator('#connection-result')).to_have_text('Connexion vérifiée')
            await page.locator('#language-select').select_option('auto')
            await page.set_viewport_size({'width':390,'height':844})
            await page.screenshot(path=str(artifacts/'configuration-mobile.png'), full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            configuration_width = (await page.locator('#configuration').bounding_box())['width']
            await page.locator('#overview-tab').click()
            assert (await page.locator('#dashboard').bounding_box())['width'] == configuration_width
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(artifacts/'dashboard-mobile.png'), full_page=True)
            await page.locator('#settings-tab').click()
            for locale, language in [('zh-CN','zh'), ('fr-CA','fr'), ('pl-PL','pl'), ('it-IT','it'), ('es-ES','en')]:
                await page.evaluate("locale=>{Object.defineProperty(navigator,'languages',{get:()=>[locale],configurable:true});window.dispatchEvent(new Event('languagechange'))}", locale)
                await expect(page.locator('html')).to_have_attribute('lang', language)
                await expect(coefficient).to_have_value('-0.35')
                await page.locator('#overview-tab').click()
                await page.locator('.quality-panel').screenshot(path=str(artifacts/f'quality-{language}.png'))
                await page.locator('#settings-tab').click()
            await page.locator('#language-select').select_option('it')
            await page.reload()
            await expect(page.locator('html')).to_have_attribute('lang','it')
            await expect(page.locator('#language-select')).to_have_value('it')
            await page.locator('#language-select').select_option('auto')
            await expect(page.locator('html')).to_have_attribute('lang','en')
            blocked_page = await context.new_page()
            await blocked_page.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError')}})")
            await blocked_page.goto(url)
            await expect(blocked_page.locator('#live-pr')).to_have_text('90',timeout=15000)
            await blocked_page.locator('#language-select').select_option('zh')
            await expect(blocked_page.locator('html')).to_have_attribute('lang','zh')
            await blocked_page.close()
            chinese_context = await browser.new_context(locale='zh-CN', http_credentials={'username':'admin','password':'browser-test'})
            chinese_page = await chinese_context.new_page()
            await chinese_page.goto(url)
            await expect(chinese_page.locator('html')).to_have_attribute('lang','zh')
            await expect(chinese_page.locator('#language-select')).to_have_value('auto')
            await expect(chinese_page.locator('#live-pr')).to_have_text('90',timeout=15000)
            await chinese_page.screenshot(path=str(artifacts/'dashboard-chinese.png'),full_page=True)
            await chinese_context.close()
            from fastapi import FastAPI
            ingress = FastAPI()
            ingress.mount('/api/hassio_ingress/test-prefix', web)
            async with fake_server(ingress) as ingress_url:
                ingress_page = await context.new_page()
                ingress_page.on('pageerror', lambda error: errors.append(str(error)))
                await ingress_page.goto(ingress_url + '/api/hassio_ingress/test-prefix/')
                await expect(ingress_page.locator('#live-pr')).to_have_text('90', timeout=15000)
                await expect(ingress_page.locator('#history-chart svg')).to_be_visible()
                await ingress_page.locator('#settings-tab').click()
                await expect(ingress_page.locator('#power-options option')).to_have_attribute('value', 'sensor.power')
                await expect(ingress_page.locator('#temperature-options option')).to_have_attribute('value', 'sensor.temp')
                await expect(ingress_page.locator('#irradiance-options option')).to_have_attribute('value', 'sensor.sun')
                await ingress_page.close()
            assert errors == []
            await browser.close()


async def test_rolling_history_expires_cached_windows_without_refetch(tmp_path):
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
        await expect(page.locator('#history-chart svg')).to_be_visible()
        charts = page.locator('#history-chart svg, #pr-chart svg')
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'initial')")
        actual_y = await page.locator('#history-chart path.series').nth(1).evaluate(
            "path => path.getAttribute('d').match(/[ML][\\d.]+,[\\d.]+/g).map(command => Number(command.split(',')[1]))")
        assert len(actual_y) == 3
        initial_requests = len(history_requests)
        await advance_clock(30)
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['initial', 'initial']
        assert len(history_requests) == initial_requests

        # The middle window straddles the new start and must remain alongside the last window.
        await advance_clock(90)
        await expect(charts.first).not_to_have_attribute('data-original', 'initial')
        assert await page.locator('#history-chart path.series').nth(1).evaluate(
            "path => path.getAttribute('d').match(/[ML][\\d.]+,[\\d.]+/g).map(command => Number(command.split(',')[1]))") == actual_y[1:]
        assert await page.locator('#pr-chart path.series').evaluate(
            "path => path.getAttribute('d').match(/[ML]/g).length") == 2
        assert len(history_requests) == initial_requests
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
        assert len(history_requests) == initial_requests

        async with page.expect_response(lambda response: '/api/history?' in response.url):
            await page.locator('#history-range').select_option('7')
        await expect(charts).to_have_count(2)
        await charts.evaluate_all("charts => charts.forEach(chart => chart.dataset.original = 'hidden')")
        await page.locator('#settings-tab').click()
        await advance_clock(6*86400+180)
        assert len(history_requests) == initial_requests+1
        assert await charts.evaluate_all('charts => charts.map(chart => chart.dataset.original)') == ['hidden', 'hidden']
        async with page.expect_response(lambda response: '/api/history?' in response.url):
            await page.locator('#overview-tab').click()
        await expect(charts).to_have_count(0)
        assert len(history_requests) == initial_requests+2
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
            await page.locator('#settings-tab').click()
            await page.locator('[name=power_entity]').fill('sensor.typed_power')
            await page.locator('[name=temperature_coefficient_pct_per_c]').fill('-0.4')
            if edited_connection:
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
            await page.locator('#overview-tab').click()
            await page.locator('#settings-tab').click()
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
            await page.locator('#overview-tab').click()
            await page.locator('#settings-tab').click()
            await page.locator('#language-select').select_option('en')
            async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
                pass
            assert len(requests) == 1
            assert await page.locator('#settings-form').evaluate('form => [...new FormData(form)]') == unsaved
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
])
async def test_settings_pending_configuration_preserves_cleared_field(tmp_path, selector, typed_value):
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

            async def configuration(route):
                response = await route.fetch()
                config_requested.set()
                await config_ready.wait()
                await route.fulfill(response=response)

            await page.route('**/api/config', configuration)
            await page.goto(url, wait_until='domcontentloaded')
            await asyncio.wait_for(config_requested.wait(), 10)
            await page.locator('#settings-tab').click()
            await page.locator(selector).fill(typed_value)
            await page.locator(selector).fill('')
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
            await page.locator('#settings-tab').click()
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
                    await page.locator('#overview-tab').click()
                    await page.locator('#settings-tab').click()
                else:
                    await page.locator('#load-entities').click()
            await expect(page.locator('#power-options option')).to_have_attribute('value', 'sensor.power')
            assert requests == [{'url':ha_url, 'token':'' if saved_credentials else 'simulation-token'}] * 2
            await expect(page.locator('#ha-url')).to_have_value(ha_url)
            await expect(page.locator('#ha-token')).to_have_value('' if saved_credentials else 'simulation-token')
            await browser.close()
        service.store.close()
