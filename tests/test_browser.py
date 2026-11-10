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
            for locale, language in [('zh-CN','zh'), ('fr-CA','fr'), ('pl-PL','pl'), ('it-IT','it'), ('es-ES','en')]:
                await page.evaluate("locale=>{Object.defineProperty(navigator,'languages',{get:()=>[locale],configurable:true});window.dispatchEvent(new Event('languagechange'))}", locale)
                await expect(page.locator('html')).to_have_attribute('lang', language)
                await expect(coefficient).to_have_value('-0.35')
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
