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
                                  ('forecast-tab', 'forecast-page'), ('settings-button', 'settings-page'),
                                  ('forecast-tab', 'forecast-page')]:
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
        assert measurement['boxes']['content']['width'] <= 1388
        assert measurement['boxes']['brand']['x'] == pytest.approx(measurement['boxes']['content']['x'], abs=1)
        scrollbar_change = measurements[0]['occupied'] - measurement['occupied']
        for edge, value in measurement['boxes']['brand'].items():
            assert value == pytest.approx(measurements[0]['boxes']['brand'][edge], abs=1)
        assert measurement['boxes']['content']['x'] == pytest.approx(measurements[0]['boxes']['content']['x'], abs=1)
        assert measurement['boxes']['content']['width'] == pytest.approx(measurements[0]['boxes']['content']['width'] + scrollbar_change, abs=1)
        assert measurement['boxes']['language']['right'] == pytest.approx(measurements[0]['boxes']['language']['right'] + scrollbar_change, abs=1)
        assert measurement['boxes']['language']['width'] == pytest.approx(measurements[0]['boxes']['language']['width'], abs=1)


@pytest.mark.parametrize('width', [601, 700, 768, 800, 801])
async def test_tablet_data_header_keeps_controls_inside_viewport(layout_page, layout_artifacts, width):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.locator('#language-select').select_option('fr')
    for control, destination in [('live-tab', 'live-page'), ('history-tab', 'history-page'),
                                  ('forecast-tab', 'forecast-page'), ('settings-button', 'settings-page'),
                                  ('forecast-tab', 'forecast-page')]:
        geometry = await page.evaluate('''() => ({
            viewport: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            controls: [...document.querySelectorAll('.app-header button, .app-header select')]
                .filter(node => node.checkVisibility()).map(node => {
                    const {left, right} = node.getBoundingClientRect();
                    return {id: node.id, left, right};
                })
        })''')
        assert geometry['scrollWidth'] <= geometry['viewport'], geometry
        assert all(box['left'] >= 0 and box['right'] <= geometry['viewport'] for box in geometry['controls']), geometry
        await page.locator(f'#{control}').click()
        await expect(page.locator(f'#{destination}')).to_be_visible()
    await page.screenshot(path=str(layout_artifacts / f'header-tablet-{width}-fr.png'))


@pytest.mark.parametrize(('width', 'language'), [(1440, 'en'), (768, 'fr'), (700, 'fr'), (390, 'de'), (320, 'fr')])
async def test_scrolled_navigation_reveals_destination_and_preserves_same_page_scroll(layout_page, layout_artifacts, width, language):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 430})
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#language-select').select_option(language)
    await page.locator('#source-diagnostics').evaluate('node => node.open = true')
    await page.evaluate('window.scrollTo(0, 500)')
    await page.wait_for_function('scrollY > 50')
    before = await page.evaluate('scrollY')
    await page.locator('#live-tab').evaluate('node => node.click()')
    assert await page.evaluate('scrollY') == pytest.approx(before, abs=1)
    await page.locator('#settings-button').evaluate('node => node.click()')
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('#load-entities')).to_be_enabled()
    if width > 600:
        assert await page.evaluate('scrollY') == 0
    await page.locator('button[data-settings-category=monitoring]').click()
    await expect(page.locator('[name=power_max_age_seconds]')).to_be_visible()
    await page.locator('[name=update_seconds]').fill('2')
    before = await page.locator('#settings-scroll').evaluate('node => node.scrollTop')
    await page.locator('#settings-button').click()
    assert await page.locator('#settings-scroll').evaluate('node => node.scrollTop') == pytest.approx(before, abs=1)
    await page.locator('#live-tab').click()
    await expect(page.locator('dialog')).to_be_visible()
    await page.locator('#keep-editing').click()
    assert await page.locator('#settings-scroll').evaluate('node => node.scrollTop') == pytest.approx(before, abs=1)
    await page.locator('#live-tab').click()
    await page.locator('#discard-changes').click()
    await expect(page.locator('#live-page')).to_be_visible()
    assert await page.evaluate('scrollY') == 0
    assert (await page.locator('#live-page h1').bounding_box())['y'] >= (await page.locator('.app-header').bounding_box())['height']
    await page.screenshot(path=str(layout_artifacts / f'navigation-{width}-{language}.png'))


@pytest.mark.parametrize('width', [320, 390, 700, 768, 1024, 1440])
@pytest.mark.parametrize('language', ['en', 'zh', 'fr', 'de', 'pl', 'it'])
async def test_shell_language_width_theme_matrix(layout_page, layout_artifacts, width, language):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#language-select').select_option(language)
    evidence = []
    for theme in ['light', 'dark']:
        await page.locator('#theme-select').select_option(theme)
        for destination in ['live', 'history', 'forecast', 'settings']:
            await page.locator('#settings-button' if destination == 'settings' else f'#{destination}-tab').click()
            await expect(page.locator(f'#{destination}-page')).to_be_visible()
            await expect(page.locator('#data-navigation button')).to_have_count(3)
            assert await page.locator('#data-navigation #settings-button').count() == 0
            await expect(page.locator('#settings-button svg')).to_be_visible()
            for selector in ['#theme-select', '#language-select']:
                assert await page.locator(selector).get_attribute('aria-label')
            await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            geometry = await page.evaluate('''() => ({
                viewport: document.documentElement.clientWidth,
                scrollWidth: document.documentElement.scrollWidth,
                controls: [...document.querySelectorAll('.app-header a, .app-header button, .app-header select')].map(node => {
                    const {left, right, top, bottom} = node.getBoundingClientRect();
                    return {id: node.id || node.className, left, right, top, bottom};
                }),
                settingsText: (() => {
                    const button = document.querySelector('#settings-button');
                    const range = document.createRange();
                    range.selectNodeContents([...button.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim()));
                    const {left, right, width} = range.getBoundingClientRect();
                    return {left, right, width};
                })()
            })''')
            assert geometry['scrollWidth'] <= geometry['viewport'], geometry
            assert all(box['left'] >= 0 and box['right'] <= geometry['viewport'] for box in geometry['controls']), geometry
            assert geometry['settingsText']['width'] > 0 and geometry['settingsText']['right'] <= geometry['viewport'], geometry
            evidence.append({'page': destination, 'theme': theme, **geometry})
            if language == 'en' and width in [390, 1440]:
                capture = await page.screenshot(path=str(layout_artifacts / f'matrix-{width}-{theme}-{destination}.png'))
                dimensions = {'width': int.from_bytes(capture[16:20], 'big'), 'height': int.from_bytes(capture[20:24], 'big')}
                assert dimensions == {'width': width, 'height': 844}
                evidence[-1]['png'] = dimensions
        await expect(page.locator('#load-entities')).to_be_enabled()
        await page.locator('button[data-settings-category=forecast]').click()
        await page.locator('[name=forecast_noct_c]').fill('48')
        await expect(page.locator('[data-settings-category=forecast]')).to_have_attribute('aria-current', 'location')
        before = await page.locator('#settings-scroll').evaluate('node => node.scrollTop')
        section = await page.locator('#settings-categories [aria-current=location]').get_attribute('data-settings-category')
        await page.locator('#theme-select').select_option('dark' if theme == 'light' else 'light')
        assert await page.locator('#settings-scroll').evaluate('node => node.scrollTop') == pytest.approx(before, abs=1)
        await page.locator('#language-select').select_option('zh' if language != 'zh' else 'en')
        await expect(page.locator('[name=forecast_noct_c]')).to_have_value('48')
        await expect(page.locator(f'[data-settings-category={section}]')).to_have_attribute('aria-current', 'location')
        await page.locator('#language-select').select_option(language)
        await page.locator('#theme-select').select_option(theme)
        await page.locator('#settings-scroll').evaluate('node => node.scrollTo(0, node.scrollHeight)')
        await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        field = await page.locator('[name=forecast_noct_c]').bounding_box()
        dock = await page.locator('#settings-actions').bounding_box()
        assert field['y'] + field['height'] <= dock['y'], {'field': field, 'dock': dock}
        await page.locator('#history-tab').click()
        await expect(page.locator('#keep-editing')).to_be_focused()
        for selector in ['#keep-editing', '#discard-changes']:
            box = await page.locator(selector).bounding_box()
            assert 0 <= box['x'] and box['x'] + box['width'] <= width
            assert 0 <= box['y'] and box['y'] + box['height'] <= 844
        if language == 'en' and width in [390, 1440]:
            await page.screenshot(path=str(layout_artifacts / f'matrix-{width}-{theme}-dialog.png'))
        await page.keyboard.press('Tab')
        await expect(page.locator('#discard-changes')).to_be_focused()
        await page.keyboard.press('Enter')
        await expect(page.locator('#history-page')).to_be_visible()
    (layout_artifacts / f'matrix-{width}-{language}.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')


async def test_short_mobile_settings_keeps_directory_and_actions_usable(layout_page, layout_artifacts):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': 390, 'height': 430})
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#language-select').select_option('de')
    await page.locator('#settings-button').click()
    await expect(page.locator('#load-entities')).to_be_enabled()
    evidence = []
    for category in ['connection', 'panels', 'sources', 'monitoring', 'forecast']:
        await page.locator(f'[data-settings-category={category}]').click()
        await page.locator('#settings-heading').evaluate('node => node.scrollIntoView({block: "start"})')
        geometry = await page.evaluate('''() => {
            const box = selector => {
                const {top, bottom, left, right} = document.querySelector(selector).getBoundingClientRect();
                return {top, bottom, left, right};
            };
            return {dock: box('#settings-actions'), directory: box('#settings-categories'),
                viewport: innerHeight, width: document.documentElement.clientWidth,
                scrollWidth: document.documentElement.scrollWidth};
        }''')
        assert 0 <= geometry['dock']['top'] < geometry['dock']['bottom'] <= 430, geometry
        assert geometry['directory']['bottom'] < geometry['dock']['top'], geometry
        assert geometry['scrollWidth'] <= geometry['width'], geometry
        evidence.append({'category': category, **geometry})
    await page.locator('#settings-scroll').evaluate('node => node.scrollTo(0, node.scrollHeight)')
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    field = await page.locator('[name=forecast_noct_c]').bounding_box()
    dock = await page.locator('#settings-actions').bounding_box()
    scroll = await page.locator('#settings-scroll').bounding_box()
    assert scroll['y'] <= field['y'] and field['y'] + field['height'] < dock['y']
    evidence.append({'last_field': field, 'dock': dock, 'scroll': scroll})
    await page.screenshot(path=str(layout_artifacts / 'settings-short-390-430-de.png'))
    (layout_artifacts / 'settings-short-390-430-de.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    await page.locator('[name=forecast_noct_c]').fill('48')
    await page.locator('#history-tab').click()
    await expect(page.locator('dialog')).to_be_visible()
    await page.locator('#keep-editing').click()
    await expect(page.locator('[name=forecast_noct_c]')).to_have_value('48')
    await page.locator('#history-tab').click()
    await page.locator('#discard-changes').click()
    await expect(page.locator('#history-page')).to_be_visible()


@pytest.mark.parametrize('width', [390, 1440])
async def test_connection_error_light_dark_captures(layout_page, layout_artifacts, width):
    from playwright.async_api import expect

    page, service = layout_page
    await page.set_viewport_size({'width': width, 'height': 844})
    service.error = 'ha_connection_failed'
    await expect(page.locator('#banner')).to_contain_text('Cannot reach Home Assistant')
    for theme in ['light', 'dark']:
        await page.locator('#theme-select').select_option(theme)
        for destination in ['live', 'history', 'forecast', 'settings']:
            await page.locator('#settings-button' if destination == 'settings' else f'#{destination}-tab').click()
            await expect(page.locator(f'#{destination}-page')).to_be_visible()
            assert await page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
            capture = await page.screenshot(path=str(layout_artifacts / f'error-{width}-{theme}-{destination}.png'))
            assert int.from_bytes(capture[16:20], 'big') == width
            assert int.from_bytes(capture[20:24], 'big') == 844


@pytest.mark.parametrize(('width', 'language'), [(320, 'fr'), (390, 'de'), (1100, 'zh'), (1440, 'fr')])
async def test_settings_mobile_categories_and_long_locale_fit(layout_page, layout_artifacts, width, language):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.emulate_media(reduced_motion='reduce')
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
        await expect(page.locator('[data-settings-section]:visible')).to_have_count(5)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        section = await page.locator(f'[data-settings-section={category}] h2').bounding_box()
        nav = await page.locator('#settings-categories').bounding_box()
        if width < 600:
            assert section['y'] >= nav['y'] + nav['height']
            assert await page.locator(f'[data-settings-section={category}] label').evaluate_all('nodes => nodes.filter(node => node.checkVisibility()).every(node => getComputedStyle(node).gridTemplateColumns.split(" ").length === 1)')
        else:
            assert section['x'] > nav['x'] + nav['width']
        await page.screenshot(path=str(layout_artifacts / f'settings-{width}-{language}-{category}.png'))
    await page.locator('#live-tab').click()
    await page.screenshot(path=str(layout_artifacts / f'live-{width}-{language}.png'))
    await page.locator('#history-tab').click()
    await page.screenshot(path=str(layout_artifacts / f'history-{width}-{language}.png'))


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
    geometry = await page.evaluate('''() => {
        const bounds = node => {
            const {left, top, right, bottom, width, height} = node.getBoundingClientRect();
            return {left, top, right, bottom, width, height, clientWidth: node.clientWidth,
                scrollWidth: node.scrollWidth};
        };
        return {viewport: {width: innerWidth, height: innerHeight, devicePixelRatio},
            document: bounds(document.documentElement), body: bounds(document.body),
            main: bounds(document.querySelector('main')), header: bounds(document.querySelector('.app-header')),
            controls: [...document.querySelectorAll('.app-header button, .app-header select, .metric, #updated, #theme-mode')]
                .filter(node => node.checkVisibility()).map(node => ({id: node.id, ...bounds(node)}))};
    }''')
    assert geometry['viewport']['width'] == 390
    assert geometry['document']['scrollWidth'] <= geometry['document']['clientWidth']
    for box in [geometry['body'], geometry['main'], geometry['header'], *geometry['controls']]:
        assert box['left'] >= 0 and box['right'] <= geometry['document']['clientWidth'], geometry
    original = await page.screenshot(path=str(layout_artifacts / 'live-mobile-original-full-page.png'), full_page=True)
    geometry['original_full_page_png'] = {'width': int.from_bytes(original[16:20], 'big'),
                                          'height': int.from_bytes(original[20:24], 'big')}
    geometry['after_full_page_capture'] = await page.evaluate('''() => ({viewportWidth: innerWidth,
        documentWidth: document.documentElement.clientWidth, documentScrollWidth: document.documentElement.scrollWidth,
        bodyRight: document.body.getBoundingClientRect().right,
        mainRight: document.querySelector('main').getBoundingClientRect().right,
        headerRight: document.querySelector('.app-header').getBoundingClientRect().right,
        settingsRight: document.querySelector('#settings-button').getBoundingClientRect().right})''')
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    geometry['after_capture_render'] = await page.evaluate('''() => ({viewportWidth: innerWidth,
        documentWidth: document.documentElement.clientWidth, documentScrollWidth: document.documentElement.scrollWidth,
        bodyRight: document.body.getBoundingClientRect().right, mainRight: document.querySelector('main').getBoundingClientRect().right,
        headerRight: document.querySelector('.app-header').getBoundingClientRect().right})''')
    assert geometry['after_capture_render']['documentScrollWidth'] <= geometry['after_capture_render']['documentWidth'], geometry
    viewport = await page.screenshot(path=str(layout_artifacts / 'live-populated-mobile.png'))
    geometry['viewport_png'] = {'width': int.from_bytes(viewport[16:20], 'big'),
                               'height': int.from_bytes(viewport[20:24], 'big')}
    assert geometry['viewport_png'] == {'width': 390, 'height': 844}
    await page.set_viewport_size({'width': 390, 'height': 1040})
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    expanded = await page.screenshot(path=str(layout_artifacts / 'live-mobile-390-full-height.png'))
    geometry['expanded_viewport_png'] = {'width': int.from_bytes(expanded[16:20], 'big'),
                                        'height': int.from_bytes(expanded[20:24], 'big')}
    assert geometry['expanded_viewport_png'] == {'width': 390, 'height': 1040}
    await page.set_viewport_size({'width': 390, 'height': 844})
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    (layout_artifacts / 'live-mobile-390-geometry.json').write_text(json.dumps(geometry, indent=2), encoding='utf-8')
    await page.locator('#live-chart svg').evaluate("node => node.dataset.original = 'hidden'")
    await page.locator('#settings-button').click()
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
    await page.locator('[name=rated_power_w]').fill('6100')
    service.store.add_observations(samples(power=3000, at=now))
    await service.tick(now+60)
    await expect(page.locator('#live-actual')).to_have_text('3,000')
    await expect(page.locator('#live-chart svg')).to_have_attribute('data-original', 'hidden')
    await expect(page.locator('[name=rated_power_w]')).to_have_value('6100')
    await page.locator('#cancel-settings').click()
    await expect(page.locator('[name=rated_power_w]')).to_have_value('5000')
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


@pytest.mark.parametrize('width', [1440, 390])
async def test_settings_scrollspy_and_bottom_actions(layout_page, width):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 700 if width > 600 else 844})
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=rated_power_w]')).to_be_enabled()
    await expect(page.locator('[data-settings-section]')).to_have_count(5)
    for category in ['connection', 'panels', 'sources', 'monitoring', 'forecast']:
        await page.locator(f'[data-settings-category={category}]').click()
        await expect(page.locator(f'[data-settings-category={category}]')).to_have_attribute('aria-pressed', 'true')
        position = await page.locator('#settings-scroll').evaluate('node => node.scrollTop')
        assert 0 <= position <= 24 if category == 'connection' else position > 24
    await page.locator('#settings-scroll').evaluate('node => node.scrollTop = 0')
    await expect(page.locator('[data-settings-category=connection]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#settings-scroll').evaluate('''node => {
        node.scrollTop += node.querySelector('[data-settings-section=sources] h2').getBoundingClientRect().top
            - node.getBoundingClientRect().top - 20;
    }''')
    await expect(page.locator('[data-settings-category=sources]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#settings-scroll').evaluate('node => node.scrollTop = node.scrollHeight')
    await expect(page.locator('[data-settings-category=forecast]')).to_have_attribute('aria-pressed', 'true')
    boxes = await page.evaluate('''() => {
        const box = selector => {
            const {left, right, top, bottom} = document.querySelector(selector).getBoundingClientRect();
            return {left, right, top, bottom};
        };
        return {actions: box('#settings-actions'), last: box('[name=forecast_noct_c]'),
            scroll: box('#settings-scroll'), width: innerWidth, height: innerHeight,
            documentWidth: document.documentElement.scrollWidth};
    }''')
    assert boxes['actions']['bottom'] <= boxes['height']
    assert boxes['actions']['left'] >= 0 and boxes['actions']['right'] <= boxes['width']
    assert boxes['last']['top'] >= boxes['scroll']['top']
    assert boxes['last']['bottom'] < boxes['actions']['top']
    assert boxes['documentWidth'] <= boxes['width']
    await page.locator('[data-settings-category=panels]').click()
    await page.locator('[name=rated_power_w]').fill('')
    await page.locator('[data-settings-category=forecast]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=rated_power_w]')).to_be_focused()
    await expect(page.locator('[data-settings-category=panels]')).to_have_attribute('aria-pressed', 'true')
    focused = await page.locator('[name=rated_power_w]').bounding_box()
    assert focused['y'] >= boxes['scroll']['top']
    assert focused['y'] + focused['height'] < boxes['actions']['top']
