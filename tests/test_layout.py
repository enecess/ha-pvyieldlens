import json
import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1 after installing Playwright Chromium')


@pytest.fixture
async def layout_page(tmp_path):
    from playwright.async_api import async_playwright, expect
    from test_engine import settings
    from test_integration import fake_server
    from pvyieldlens.service import Service
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    service = Service(Store(tmp_path / 'data.sqlite'))
    await service.configure(settings(interval_minutes=1, update_seconds=1), now=int(time.time())-86430)
    async with fake_server() as ha_url:
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url,
                                         ha_token='simulation-token'), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(ignore_default_args=['--hide-scrollbars'], args=['--no-sandbox'])
            page = await browser.new_page(locale='en-US', viewport={'width': 1440, 'height': 700},
                                          http_credentials={'username': 'admin', 'password': 'browser-test'})
            page.set_default_timeout(5000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            await page.goto(url)
            await expect(page.locator('main')).to_have_attribute('data-configuration-ready', 'true')
            await expect(page.locator('main')).to_have_attribute('data-snapshot-ready', 'true')
            await expect(page.locator('#setup-empty')).to_be_hidden()
            await expect(page.locator('#live-chart .chart-empty')).to_be_visible()
            yield page, service
            assert errors == []
            await browser.close()
    service.store.close()


@pytest.fixture
def layout_artifacts():
    path = Path(os.getenv('PVYL_LAYOUT_ARTIFACTS', 'artifacts/task-6-layout'))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.parametrize('width', [1440, 1100])
async def test_data_and_settings_keep_header_and_content_width(layout_page, layout_artifacts, width):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 600})
    measurements = []
    for control, destination in [('live-tab', 'live-page'), ('history-tab', 'history-page'),
                                  ('forecast-tab', 'forecast-page'), ('settings-button', 'configuration'),
                                  ('settings-back', 'forecast-page')]:
        await page.locator(f'#{control}').click()
        await expect(page.locator(f'#{destination}')).to_be_visible()
        measurements.append(await page.evaluate('''destination => ({destination,
            viewport: innerWidth, occupied: innerWidth - document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            boxes: Object.fromEntries(Object.entries({brand: '.brand', language: '.language-picker',
                content: '#' + destination}).map(([name, selector]) => {
                const {x, right, width} = document.querySelector(selector).getBoundingClientRect();
                return [name, {x, right, width}];
            }))})''', destination))
    (layout_artifacts / f'widths-{width}.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
    assert measurements[0]['occupied'] > 0
    for measurement in measurements:
        assert measurement['scrollWidth'] <= width
        assert measurement['boxes']['content']['width'] <= 1200
        assert measurement['boxes']['brand']['x'] == pytest.approx(measurement['boxes']['content']['x'], abs=1)
        for name, box in measurement['boxes'].items():
            for edge, value in box.items():
                assert value == pytest.approx(measurements[0]['boxes'][name][edge], abs=1)


@pytest.mark.parametrize('width', [601, 700, 768, 800, 801])
async def test_tablet_data_header_keeps_controls_inside_viewport(layout_page, layout_artifacts, width):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.locator('#language-select').select_option('fr')
    for control, destination in [('live-tab', 'live-page'), ('history-tab', 'history-page'),
                                  ('forecast-tab', 'forecast-page'), ('settings-button', 'configuration'),
                                  ('settings-back', 'forecast-page')]:
        geometry = await page.evaluate('''() => ({
            viewport: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            controls: [...document.querySelectorAll('.topbar button, .topbar select')]
                .filter(node => node.checkVisibility()).map(node => {
                    const {left, right} = node.getBoundingClientRect();
                    return {id: node.id, left, right};
                })
        })''')
        assert geometry['scrollWidth'] <= geometry['viewport'], geometry
        assert all(box['left'] >= 0 and box['right'] <= geometry['viewport'] for box in geometry['controls']), geometry
        await page.locator(f'#{control}').click()
        await expect(page.locator(f'#{destination}')).to_be_visible()
    await page.screenshot(path=str(layout_artifacts / f'header-tablet-{width}-fr.png'), full_page=True)


@pytest.mark.parametrize(('width', 'language'), [(1440, 'en'), (768, 'fr'), (700, 'fr'), (390, 'de'), (320, 'fr')])
async def test_scrolled_navigation_reveals_destination_and_preserves_same_page_scroll(layout_page, layout_artifacts, width, language):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 430})
    await page.locator('#language-select').select_option(language)
    await page.locator('#source-diagnostics').evaluate('node => node.open = true')
    for source, destination, opening in [('live-tab', 'settings-button', 'configuration'),
                                         ('settings-button', 'settings-back', 'live-page')]:
        if source == 'settings-button':
            await page.locator('button[data-settings-category=monitoring]').click()
            await page.locator('#monitoring-advanced').evaluate('node => node.open = true')
        await page.evaluate('window.scrollTo(0, 500)')
        await page.wait_for_function('scrollY > 50')
        geometry = await page.evaluate('''() => {
            const header = document.querySelector('.topbar').getBoundingClientRect();
            return {scrollY, top: header.top, bottom: header.bottom, viewport: innerWidth,
                scrollWidth: document.documentElement.scrollWidth,
                controls: [...document.querySelectorAll('.topbar button, .topbar select')].filter(node => node.checkVisibility()).map(node => {
                    const box = node.getBoundingClientRect();
                    return {top: box.top, bottom: box.bottom, left: box.left, right: box.right};
                })};
        }''')
        assert geometry['top'] == pytest.approx(0, abs=1)
        assert geometry['scrollWidth'] <= width
        assert all(control['top'] >= 0 and control['bottom'] <= geometry['bottom'] and
                   control['left'] >= 0 and control['right'] <= width for control in geometry['controls'])
        await page.locator(f'#{source}').click()
        assert await page.evaluate('scrollY') == pytest.approx(geometry['scrollY'], abs=1)
        await page.locator(f'#{destination}').click()
        await expect(page.locator(f'#{opening}')).to_be_visible()
        assert await page.evaluate('scrollY') == 0
        header_bottom = (await page.locator('.topbar').bounding_box())['height']
        assert (await page.locator(f'#{opening} h1:visible').bounding_box())['y'] >= header_bottom
    await page.screenshot(path=str(layout_artifacts / f'navigation-{width}-{language}.png'), full_page=True)


@pytest.mark.parametrize(('width', 'language'), [(320, 'fr'), (390, 'de'), (1100, 'zh'), (1440, 'fr')])
async def test_settings_mobile_categories_and_long_locale_fit(layout_page, layout_artifacts, width, language):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.locator('#language-select').select_option(language)
    await page.locator('#settings-button').click()
    selected_language = await page.locator('#language-select').evaluate('''select => {
        const style = getComputedStyle(select);
        const context = document.createElement('canvas').getContext('2d');
        context.font = style.font;
        return {text: context.measureText(select.selectedOptions[0].textContent).width,
            available: select.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) - 20};
    }''')
    assert selected_language['text'] <= selected_language['available'], selected_language
    await expect(page.locator('#connection-result')).not_to_be_empty()
    assert await page.locator('#settings-form').count() == 1
    for category in ['connection', 'panels', 'sources', 'monitoring', 'forecast']:
        await page.locator(f'button[data-settings-category={category}]').click()
        await expect(page.locator(f'[data-settings-section={category}]')).to_be_visible()
        await expect(page.locator('[data-settings-section]:visible')).to_have_count(1)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        section = await page.locator(f'[data-settings-section={category}]').bounding_box()
        nav = await page.locator('#settings-categories').bounding_box()
        if width < 600:
            assert section['y'] >= nav['y'] + nav['height']
            assert await page.locator(f'[data-settings-section={category}] label').evaluate_all('nodes => nodes.filter(node => node.checkVisibility()).every(node => getComputedStyle(node).gridTemplateColumns.split(" ").length === 1)')
        else:
            assert section['x'] > nav['x'] + nav['width']
        await page.screenshot(path=str(layout_artifacts / f'settings-{width}-{language}-{category}.png'), full_page=True)
    await page.locator('#settings-back').click()
    await page.screenshot(path=str(layout_artifacts / f'live-{width}-{language}.png'), full_page=True)
    await page.locator('#history-tab').click()
    await page.screenshot(path=str(layout_artifacts / f'history-{width}-{language}.png'), full_page=True)


async def test_history_summary_and_charts_share_range(layout_page, layout_artifacts):
    from playwright.async_api import expect
    from test_engine import samples
    from pvyieldlens.engine import calculate

    page, service = layout_page
    start = service.store.cursor
    now = int(start + 86430)
    for offset, power in [(0, 1000), (60, 2000), (120, 3000)]:
        service.store.settle(calculate(service.config, samples(power=power, at=start+offset),
                                      start+offset, start+offset+60), 1, 'UTC')
    await page.evaluate('now => Date.now = () => now', now * 1000)
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        pass
    async with page.expect_response(lambda response: '/api/history?' in response.url) as response:
        await page.locator('#history-tab').click()
    payload = await (await response.value).json()
    assert len(payload['windows']) == 3
    assert payload['summary']['estimated_energy_kwh'] == pytest.approx(0.124)
    await expect(page.locator('#history-energy')).to_have_text('0.124')
    await expect(page.locator('#history-pr')).to_have_text('67.2')
    await expect(page.locator('#stat-coverage')).to_contain_text('100%')
    for selector in ['#history-chart path.series', '#pr-chart path.series']:
        assert await page.locator(selector).first.evaluate("path => path.getAttribute('d').match(/[ML]/g).length") == 2
    await expect(page.locator('#history-boundaries')).to_contain_text('Settled periods')
    requests = []
    page.on('request', lambda request: requests.append(request.url) if '/api/history?' in request.url else None)
    await page.locator('#history-chart svg').evaluate("node => node.dataset.original = 'steady'")
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        pass
    await expect(page.locator('#history-chart svg')).to_have_attribute('data-original', 'steady')
    assert requests == []
    await page.locator('#language-select').select_option('de')
    await expect(page.locator('#history-chart svg')).not_to_have_attribute('data-original', 'steady')
    await page.locator('#language-select').select_option('en')
    await page.locator('#history-chart svg').evaluate("node => node.dataset.original = 'resize'")
    await page.set_viewport_size({'width': 1100, 'height': 700})
    await expect(page.locator('#history-chart svg')).not_to_have_attribute('data-original', 'resize')
    await page.set_viewport_size({'width': 1440, 'height': 900})
    await page.locator('#settings-button').click()
    await page.locator('#history-chart svg').evaluate("node => node.dataset.original = 'hidden'")
    await page.locator('#language-select').select_option('fr')
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        pass
    await expect(page.locator('#history-chart svg')).to_have_attribute('data-original', 'hidden')
    assert requests == []
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-chart svg')).not_to_have_attribute('data-original', 'hidden')
    await page.locator('#language-select').select_option('en')
    await page.locator('#history-totals').evaluate('node => node.open = true')
    total = await page.locator('#total-energy').inner_text()
    async with page.expect_response(lambda response: '/api/history?' in response.url):
        await page.locator('#history-range').select_option('7')
    await expect(page.locator('#history-energy')).to_have_text('0.186')
    assert await page.locator('#history-chart path.series').first.evaluate("path => path.getAttribute('d').match(/[ML]/g).length") == 3
    await expect(page.locator('#total-energy')).to_have_text(total)
    await page.screenshot(path=str(layout_artifacts / 'history-populated-desktop.png'), full_page=True)
    await page.locator('#live-tab').click()
    await expect(page.locator('#history-chart svg')).to_be_hidden()


async def test_completeness_hints_follow_language(layout_page):
    from playwright.async_api import expect

    page, _ = layout_page
    hints = []
    for language in ['en', 'zh']:
        await page.locator('#language-select').select_option(language)
        metric_hints = await page.locator('#live-coverage, #stat-coverage').evaluate_all('nodes => nodes.map(node => node.title)')
        assert len(metric_hints) == 2 and all(metric_hints)
        assert metric_hints[0] == metric_hints[1]
        assert metric_hints[0] not in await page.locator('.quality-panel').inner_text()
        hints.append(metric_hints[0])
    assert hints[0] != hints[1]


async def test_sensors_empty_data_empty_and_language_changes(layout_page, layout_artifacts):
    from playwright.async_api import expect
    from fake_ha import source_states
    from pvyieldlens.home_assistant import HAState

    page, service = layout_page
    await page.locator('#source-diagnostics').evaluate('node => node.open = true')
    table = page.locator('.quality-panel table')
    empty = table.locator('tbody td[colspan="3"]')
    await expect(empty).to_have_text('No sensor data yet')
    await expect(empty).to_be_visible()
    assert (await empty.bounding_box())['width'] == pytest.approx((await table.bounding_box())['width'], abs=1)
    assert (await empty.bounding_box())['height'] >= 56
    assert await empty.evaluate('cell => getComputedStyle(cell).textAlign') == 'center'
    await page.locator('#language-select').select_option('zh')
    await expect(empty).to_have_text('暂无传感器数据')
    await service.ingest([HAState.model_validate(state) for state in source_states()])
    await expect(table.locator('tbody tr:visible')).to_have_count(3)
    await expect(empty).to_be_hidden()
    await expect(table.locator('tbody tr:visible').first.locator('td').first).to_have_text('sensor.power')
    await expect(table.locator('tbody tr:visible').nth(1).locator('td').nth(1)).to_contain_text('45 °C')
    await page.screenshot(path=str(layout_artifacts / 'sources-populated-zh.png'), full_page=True)
    await service.configure(service.config.model_copy(update={'rated_power_w': 6000}))
    await expect(empty).to_have_text('暂无传感器数据')
    await expect(table.locator('tbody tr:visible')).to_have_count(1)


async def test_live_readings_keep_polling_while_configuring(layout_page, layout_artifacts):
    from playwright.async_api import expect
    from test_engine import samples

    page, service = layout_page
    now = time.time()
    service.store.add_observations(samples(at=now-60))
    await service.tick(now)
    await expect(page.locator('#live-pr')).to_have_text('90')
    await expect(page.locator('#live-actual')).to_have_text('3,348')
    await expect(page.locator('#live-estimated')).to_have_text('3,720')
    await expect(page.locator('#live-opportunity')).to_have_text('372')
    await page.screenshot(path=str(layout_artifacts / 'live-populated-desktop.png'), full_page=True)
    await page.set_viewport_size({'width': 390, 'height': 844})
    assert await page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
    await page.screenshot(path=str(layout_artifacts / 'live-populated-mobile.png'), full_page=True)
    await page.locator('#live-chart svg').evaluate("node => node.dataset.original = 'hidden'")
    await page.locator('#settings-button').click()
    await expect(page.locator('#settings-page')).to_be_visible()
    service.store.add_observations(samples(power=3000, at=now))
    await service.tick(now+60)
    await expect(page.locator('#live-actual')).to_have_text('3,000')
    await expect(page.locator('#live-chart svg')).to_have_attribute('data-original', 'hidden')
    await page.locator('#live-tab').click()
    await expect(page.locator('#live-chart svg')).not_to_have_attribute('data-original', 'hidden')
    curve = await page.locator('#live-chart path.series').nth(1).get_attribute('d')
    light_colors = await page.locator('#live-chart svg').evaluate('''svg => ({
        label: getComputedStyle(svg.querySelector('text')).fill,
        grid: getComputedStyle(svg.querySelector('.grid')).stroke
    })''')
    await page.locator('#theme-select').select_option('dark')
    await expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    dark_colors = await page.locator('#live-chart svg').evaluate('''svg => ({
        label: getComputedStyle(svg.querySelector('text')).fill,
        grid: getComputedStyle(svg.querySelector('.grid')).stroke
    })''')
    assert light_colors['label'] != dark_colors['label']
    assert light_colors['grid'] != dark_colors['grid']
    await expect(page.locator('#live-chart path.series').nth(1)).to_have_attribute('d', curve)
    await page.locator('#history-tab').click()
    await page.locator('#history-range').select_option('7')
    await page.locator('#theme-select').select_option('light')
    await expect(page.locator('#history-range')).to_have_value('7')
    await page.locator('#settings-button').click()
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-range')).to_have_value('7')
    await page.locator('#live-tab').click()
    await expect(page.locator('#live-chart path.series').nth(1)).to_have_attribute('d', curve)
