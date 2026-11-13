import json
import math
import os
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
    await service.configure(settings(interval_minutes=1, update_seconds=1))
    async with fake_server() as ha_url:
        web = create_app(service, Runtime(web_password='browser-test', ha_url=ha_url,
                                         ha_token='simulation-token'), run_background=False)
        async with fake_server(web) as url, async_playwright() as playwright:
            browser = await playwright.chromium.launch(ignore_default_args=['--hide-scrollbars'], args=['--no-sandbox'])
            page = await browser.new_page(locale='en-US', viewport={'width': 1440, 'height': 600},
                                          http_credentials={'username': 'admin', 'password': 'browser-test'})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(url)
            await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
            await expect(page.locator('#setup-empty')).to_be_hidden()
            await expect(page.locator('#live-chart .chart-empty')).to_be_visible()
            yield page, service
            assert errors == []
            await browser.close()
    service.store.close()


@pytest.fixture
def layout_artifacts():
    path = Path(os.getenv('PVYL_LAYOUT_ARTIFACTS', 'artifacts/layout'))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.parametrize('width', [1440, 1100])
async def test_tab_switch_keeps_header_and_content_geometry(layout_page, layout_artifacts, width):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 600})
    overview_height = await page.evaluate('document.documentElement.scrollHeight')
    await page.locator('#settings-tab').click()
    await expect(page.locator('#connection-result')).to_have_text('Connection verified')
    settings_height = await page.evaluate('document.documentElement.scrollHeight')
    assert overview_height > settings_height + 40
    await page.set_viewport_size({'width': width, 'height': math.ceil((overview_height + settings_height) / 2)})

    measurements = []
    for tab in ['overview', 'settings', 'overview', 'settings', 'overview']:
        await page.locator(f'#{tab}-tab').click()
        await expect(page.locator('#dashboard' if tab == 'overview' else '#configuration')).to_be_visible()
        measurements.append(await page.evaluate('''tab => ({tab,
            viewport: innerWidth, height: innerHeight,
            scrollHeight: document.documentElement.scrollHeight,
            occupied: innerWidth - document.documentElement.clientWidth,
            boxes: Object.fromEntries(Object.entries({brand: '.brand', nav: 'nav', language: '.language-picker',
                content: 'main > section:not([hidden])'}).map(([name, selector]) => {
                const {x, right, width} = document.querySelector(selector).getBoundingClientRect();
                return [name, {x, right, width}];
            }))})''', tab))
        await page.screenshot(path=str(layout_artifacts / f'tabs-{width}-{len(measurements)}-{tab}.png'))
    (layout_artifacts / f'tabs-{width}.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
    print(json.dumps(measurements))

    for measurement in measurements:
        assert (measurement['scrollHeight'] > measurement['height']) == (measurement['tab'] == 'overview')
    assert measurements[0]['occupied'] > 0, 'Classic scrollbars must occupy real viewport width'
    for measurement in measurements[1:]:
        for name, box in measurement['boxes'].items():
            for edge, value in box.items():
                assert value == pytest.approx(measurements[0]['boxes'][name][edge], abs=1), (name, edge, measurements)
    for measurement in measurements:
        assert measurement['boxes']['brand']['x'] == pytest.approx(measurement['boxes']['content']['x'], abs=1)
    assert measurements[0]['boxes']['content']['width'] <= 1200
    if width == 1100:
        assert measurements[0]['boxes']['content']['width'] < 1200


@pytest.mark.parametrize(('width', 'language'), [(1440, 'en'), (390, 'de'), (320, 'fr')])
@pytest.mark.parametrize(('source', 'destination'), [('overview', 'settings'), ('settings', 'overview')])
async def test_scrolled_navigation_reveals_destination_and_preserves_same_section_scroll(layout_page, layout_artifacts, width, language, source, destination):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 700})
    await page.locator('#language-select').select_option(language)
    if source == 'settings':
        await page.locator('#settings-tab').click()
        await expect(page.locator('#power-options option')).to_have_attribute('value', 'sensor.power')
    initial = await page.locator('.topbar').bounding_box()
    if width < 600:
        assert initial['height'] > 90, 'Exercise a header whose controls wrap'
    await page.evaluate('window.scrollTo(0, 500)')
    await page.wait_for_function('scrollY >= 400')
    geometry = await page.evaluate('''() => {
        const header = document.querySelector('.topbar').getBoundingClientRect();
        return {scrollY, top: header.top, bottom: header.bottom, height: header.height,
            viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
            controls: [...document.querySelectorAll('.topbar button, .topbar select')].map(node => {
                const box = node.getBoundingClientRect();
                return {id: node.id, top: box.top, bottom: box.bottom, left: box.left, right: box.right};
            })};
    }''')
    (layout_artifacts / f'sticky-{width}-{language}-{source}.json').write_text(json.dumps(geometry, indent=2), encoding='utf-8')
    await page.screenshot(path=str(layout_artifacts / f'sticky-{width}-{language}-{source}.png'))
    print(json.dumps(geometry))
    assert geometry['scrollY'] > 200
    assert geometry['top'] == pytest.approx(0, abs=1)
    assert geometry['height'] == pytest.approx(initial['height'], abs=1)
    assert geometry['scrollWidth'] <= geometry['viewport']
    for control in geometry['controls']:
        assert control['top'] >= 0 and control['bottom'] <= geometry['bottom']
        assert control['left'] >= 0 and control['right'] <= geometry['viewport']
    await page.locator(f'#{source}-tab').click()
    assert await page.evaluate('scrollY') == pytest.approx(geometry['scrollY'], abs=1), 'The active section must keep its scroll position'

    await page.locator(f'#{destination}-tab').click()
    await expect(page.locator('#configuration' if destination == 'settings' else '#dashboard')).to_be_visible()
    if destination == 'settings':
        await expect(page.locator('#power-options option')).to_have_attribute('value', 'sensor.power')
    opening = await page.evaluate('''destination => {
        const header = document.querySelector('.topbar').getBoundingClientRect();
        const selectors = destination === 'settings'
            ? ['#configuration > .section-heading h1', '#ha-url', '#ha-token']
            : ['#dashboard > .section-heading h1', '#dashboard .live-metrics'];
        return {destination, scrollY, height: innerHeight, headerBottom: header.bottom,
            content: selectors.map(selector => {
                const {top, bottom} = document.querySelector(selector).getBoundingClientRect();
                return {selector, top, bottom};
            })};
    }''', destination)
    (layout_artifacts / f'opening-{width}-{language}-{destination}.json').write_text(json.dumps(opening, indent=2), encoding='utf-8')
    await page.screenshot(path=str(layout_artifacts / f'opening-{width}-{language}-{destination}.png'))
    print(json.dumps(opening))
    assert opening['scrollY'] == pytest.approx(0, abs=1), opening
    for content in opening['content']:
        assert content['top'] >= opening['headerBottom'] and content['bottom'] <= opening['height'], opening
    await page.locator('#language-select').select_option('zh')
    await expect(page.locator('html')).to_have_attribute('lang', 'zh')


async def test_completeness_hints_belong_to_metrics_and_follow_language(layout_page):
    from playwright.async_api import expect

    page, _ = layout_page
    hints = []
    for language in ['en', 'zh']:
        await page.locator('#language-select').select_option(language)
        await expect(page.locator('html')).to_have_attribute('lang', language)
        metric_hints = await page.locator('#live-coverage, #stat-coverage').evaluate_all('nodes => nodes.map(node => node.title)')
        assert len(metric_hints) == 2 and all(metric_hints), 'Both completeness indicators need a native hint'
        assert metric_hints[0] == metric_hints[1]
        assert metric_hints[0] not in await page.locator('.quality-panel').inner_text(), 'The sensor table has no completeness metric'
        hints.append(metric_hints[0])
    assert hints[0] != hints[1], 'Completeness hints must follow the selected language'


async def test_sensors_empty_data_empty_and_language_changes(layout_page, layout_artifacts):
    from playwright.async_api import expect
    from fake_ha import source_states
    from pvyieldlens.home_assistant import HAState

    page, service = layout_page
    table = page.locator('.quality-panel table')
    empty = table.locator('tbody td[colspan="3"]')
    await expect(empty).to_have_text('No sensor data yet')
    await empty.scroll_into_view_if_needed()
    await expect(empty).to_be_visible()
    assert (await empty.bounding_box())['width'] == pytest.approx((await table.bounding_box())['width'], abs=1)
    assert (await empty.bounding_box())['height'] >= 56
    assert await empty.evaluate('cell => getComputedStyle(cell).textAlign') == 'center'
    assert await empty.evaluate('cell => getComputedStyle(cell).color') == await page.locator('.quality-panel .muted').first.evaluate('node => getComputedStyle(node).color')
    await page.screenshot(path=str(layout_artifacts / 'sensors-empty-en.png'))
    await page.locator('#language-select').select_option('zh')
    await expect(empty).to_have_text('暂无传感器数据')
    await empty.scroll_into_view_if_needed()
    await page.screenshot(path=str(layout_artifacts / 'sensors-empty-zh.png'))

    await service.ingest([HAState.model_validate(state) for state in source_states()])
    await expect(table.locator('tbody tr:visible')).to_have_count(3)
    await expect(empty).to_be_hidden()
    assert await table.locator('tbody tr:visible').evaluate_all('rows => rows.every(row => row.cells.length === 3)')
    await expect(table.locator('tbody tr:visible').first.locator('td').first).to_have_text('sensor.power')
    await expect(table.locator('tbody tr:visible').nth(1).locator('td').nth(1)).to_contain_text('45 °C')
    await table.scroll_into_view_if_needed()
    await page.screenshot(path=str(layout_artifacts / 'sensors-populated-zh.png'))
    await page.locator('#language-select').select_option('en')
    await expect(table.locator('tbody tr:visible')).to_have_count(3)

    await service.configure(service.config)
    await expect(empty).to_have_text('No sensor data yet')
    await expect(table.locator('tbody tr:visible')).to_have_count(1)
    await page.locator('#language-select').select_option('zh')
    await expect(empty).to_have_text('暂无传感器数据')
    await expect(table.locator('thead th')).to_have_count(3)
    await empty.scroll_into_view_if_needed()
    await page.screenshot(path=str(layout_artifacts / 'sensors-reset-zh.png'))
