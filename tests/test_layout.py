import base64
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
    from pvyieldlens.settings import ForecastSettings
    from pvyieldlens.storage import Store
    from pvyieldlens.web import Runtime, create_app

    service = Service(Store(tmp_path / 'data.sqlite'))
    await service.configure(settings(settlement_interval_minutes=1, update_interval_seconds=1), now=int(time.time())-86430)
    service.forecast.configure(service.monitoring_settings, ForecastSettings(tilt_deg=25.0, azimuth_deg=180.0), service.origin, None)
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
            await expect(page.locator('#live-chart svg')).to_be_visible()
            await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', '')
            yield page, service
            assert errors == []
            await browser.close()
    service.store.close()


@pytest.fixture
def layout_artifacts():
    path = Path(os.getenv('PVYL_LAYOUT_ARTIFACTS', 'artifacts/task-6-layout'))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.parametrize('width', [1440, 1100, 1920, 2560])
@pytest.mark.parametrize('height', [600, 1000])
async def test_data_and_settings_keep_header_and_content_width(layout_page, layout_artifacts, width, height):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': height})
    await expect(page.locator('#content-scroll')).to_have_count(1)
    measurements = []
    for control, destination in [('live-tab', 'live-page'), ('history-tab', 'history-page'),
                                  ('live-tab', 'live-page'),
                                  ('forecast-tab', 'forecast-page'), ('settings-button', 'settings-page'),
                                  ('forecast-tab', 'forecast-page')]:
        await page.locator(f'#{control}').click()
        await expect(page.locator(f'#{destination}')).to_be_visible()
        measurements.append(await page.evaluate('''destination => ({destination,
            viewport: innerWidth,
            root: {clientHeight: document.documentElement.clientHeight,
                scrollHeight: document.documentElement.scrollHeight,
                overflows: document.documentElement.scrollHeight > document.documentElement.clientHeight},
            scrollWidth: document.documentElement.scrollWidth,
            content: (() => {
                const node = document.querySelector('#content-scroll'), style = getComputedStyle(node);
                return {clientWidth: node.clientWidth, scrollWidth: node.scrollWidth,
                    overflows: node.scrollHeight > node.clientHeight, gutter: style.scrollbarGutter};
            })(),
            boxes: Object.fromEntries(Object.entries({brand: '.brand', language: '.language-picker',
                header: '.app-header', main: 'main',
                settings: '#settings-button', status: '#connection-state', theme: '.theme-control',
                content: '#' + destination}).map(([name, selector]) => {
                const {x, right, width, top, bottom} = document.querySelector(selector).getBoundingClientRect();
                return [name, {x, right, width, top, bottom}];
            }))})''', destination))
        assert await page.locator('.app-header #connection-state').count() == 1
        assert await page.locator('#theme-mode, .context-bar').count() == 0
    (layout_artifacts / f'widths-{width}-{height}.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
    assert measurements[0]['content']['overflows']
    assert measurements[1]['content']['overflows']
    assert measurements[2]['content']['overflows']
    for measurement in measurements:
        assert not measurement['root']['overflows']
        assert measurement['scrollWidth'] <= width
        assert measurement['content']['scrollWidth'] <= measurement['content']['clientWidth']
        assert measurement['content']['gutter'] == 'stable'
        assert measurement['boxes']['header']['x'] == 0
        assert measurement['boxes']['header']['top'] == 0
        assert measurement['boxes']['header']['right'] == width
        assert measurement['boxes']['content']['width'] <= 1388
        header_inset = max(26, (width - 1440) / 2 + 26)
        assert measurement['boxes']['brand']['x'] == pytest.approx(header_inset, abs=1)
        assert measurement['boxes']['settings']['right'] == pytest.approx(width - header_inset, abs=1)
        assert measurement['boxes']['content']['x'] == pytest.approx(measurement['boxes']['main']['x'] + 26, abs=1)
        assert measurement['boxes']['content']['right'] == pytest.approx(measurement['boxes']['main']['right'] - 26, abs=1)
        assert measurement['boxes']['main']['right'] <= measurement['content']['clientWidth']
        status, theme = measurement['boxes']['status'], measurement['boxes']['theme']
        assert status['right'] < theme['x']
        assert (status['top'] + status['bottom']) / 2 == pytest.approx((theme['top'] + theme['bottom']) / 2, abs=1)
        assert measurement['boxes']['brand']['x'] == pytest.approx(measurements[0]['boxes']['brand']['x'], abs=1)
        assert measurement['boxes']['brand']['width'] == pytest.approx(measurements[0]['boxes']['brand']['width'], abs=1)
        assert measurement['boxes']['content']['x'] == pytest.approx(measurements[0]['boxes']['content']['x'], abs=1)
        assert measurement['boxes']['content']['width'] == pytest.approx(measurements[0]['boxes']['content']['width'], abs=1)
        assert measurement['boxes']['settings']['right'] == pytest.approx(measurements[0]['boxes']['settings']['right'], abs=1)
        assert measurement['boxes']['language']['right'] == pytest.approx(measurements[0]['boxes']['language']['right'], abs=1)
        assert measurement['boxes']['language']['width'] == pytest.approx(measurements[0]['boxes']['language']['width'], abs=1)


@pytest.mark.parametrize(('width', 'height'), [(1440, 1000), (390, 1600)])
@pytest.mark.parametrize(('theme', 'background'), [('light', [243, 245, 249, 255]), ('dark', [16, 23, 35, 255])])
async def test_content_empty_gutter_matches_background_and_scrolled_header_stays_visible(layout_page, layout_artifacts, width, height, theme, background):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': height})
    await page.locator('#theme-select').select_option(theme)
    await page.locator('#forecast-tab').click()
    await expect(page.locator('#content-scroll')).to_have_count(1)
    empty = await page.locator('#content-scroll').evaluate('''node => {
        const {top, right, bottom} = node.getBoundingClientRect(), style = getComputedStyle(node);
        return {top, right, bottom, clientWidth: node.clientWidth, width: node.offsetWidth,
            scrollHeight: node.scrollHeight, height: node.clientHeight, background: style.backgroundColor,
            scrollbarWidth: style.scrollbarWidth, scrollbarColor: style.scrollbarColor};
    }''')
    assert empty['scrollHeight'] <= empty['height'], empty
    assert empty['width'] > empty['clientWidth'], empty
    capture = await page.screenshot(path=str(layout_artifacts / f'empty-gutter-{width}-{theme}.png'))
    pixels = await page.evaluate('''async ({png, x, top, bottom}) => {
        const image = new Image(); image.src = 'data:image/png;base64,' + png; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
        return [top + 2, Math.floor((top + bottom) / 2), bottom - 2].map(y =>
            [...context.getImageData(x, y, 1, 1).data]);
    }''', {'png': base64.b64encode(capture).decode(), 'x': width - 2, 'top': empty['top'], 'bottom': empty['bottom']})
    assert pixels == [background] * 3, {'geometry': empty, 'pixels': pixels}
    await page.locator('#settings-button').click()
    settings_style = await page.locator('#settings-scroll').evaluate('''node => {
        const style = getComputedStyle(node); return {width: style.scrollbarWidth, color: style.scrollbarColor};
    }''')
    assert empty['scrollbarWidth'] == settings_style['width'] == 'thin'
    assert empty['scrollbarColor'] == settings_style['color']
    assert settings_style['color'].endswith('rgba(0, 0, 0, 0)')
    scrolled_height = min(height, 1000)
    await page.set_viewport_size({'width': width, 'height': scrolled_height})
    await page.locator('#live-tab').click()
    await expect(page.locator('#history-totals')).to_have_count(0)
    await page.locator('#content-scroll').evaluate('node => node.scrollTo(0, node.scrollHeight)')
    await page.wait_for_function("() => document.querySelector('#content-scroll').scrollTop > 0")
    scrolled = await page.evaluate('''() => {
        const header = document.querySelector('.app-header').getBoundingClientRect(), node = document.querySelector('#content-scroll');
        return {headerTop: header.top, headerRight: header.right, headerBottom: header.bottom,
            contentTop: node.getBoundingClientRect().top, scrollTop: node.scrollTop,
            rootTop: scrollY, rootHeight: document.documentElement.scrollHeight};
    }''')
    assert scrolled['headerTop'] == scrolled['rootTop'] == 0, scrolled
    assert scrolled['headerRight'] == width
    assert scrolled['contentTop'] == scrolled['headerBottom']
    assert scrolled['rootHeight'] == scrolled_height
    await page.screenshot(path=str(layout_artifacts / f'scrolled-header-{width}-{theme}.png'))
    (layout_artifacts / f'gutter-{width}-{theme}.json').write_text(json.dumps({'empty': empty, 'pixels': pixels,
        'settings_scrollbar': settings_style, 'scrolled': scrolled}, indent=2), encoding='utf-8')


@pytest.mark.parametrize('width', [601, 700, 768, 800, 801, 851, 900, 1024])
async def test_tablet_data_header_keeps_controls_inside_viewport(layout_page, layout_artifacts, width):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 844})
    await page.locator('#language-select').select_option('fr')
    async def unconfigured(route):
        response = await route.fetch()
        configuration = await response.json()
        configuration['monitoring_settings'] = None
        await route.fulfill(response=response, json=configuration)
    await page.route('**/api/config', unconfigured)
    await page.reload()
    await expect(page.locator('#connection-state')).to_contain_text('Configuration requise')
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
    await expect(page.locator('#content-scroll')).to_have_count(1)
    await page.locator('#content-scroll').evaluate('node => node.scrollTo(0, 500)')
    await page.wait_for_function("() => document.querySelector('#content-scroll').scrollTop > 50")
    before = await page.locator('#content-scroll').evaluate('node => node.scrollTop')
    await page.locator('#live-tab').evaluate('node => node.click()')
    assert await page.locator('#content-scroll').evaluate('node => node.scrollTop') == pytest.approx(before, abs=1)
    assert (await page.locator('.app-header').bounding_box())['y'] == 0
    await page.locator('#settings-button').evaluate('node => node.click()')
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('#load-entities')).to_be_enabled()
    if width > 600:
        assert await page.locator('#content-scroll').evaluate('node => node.scrollTop') == 0
    await page.locator('button[data-settings-category=monitoring]').click()
    await expect(page.locator('[name=actual_power_max_age_seconds]')).to_be_visible()
    await page.locator('[name=update_interval_seconds]').fill('2')
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
    assert await page.locator('#content-scroll').evaluate('node => node.scrollTop') == 0
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
        await page.locator('[name=forecast_pr_history_days]').fill('48')
        await expect(page.locator('[data-settings-category=forecast]')).to_have_attribute('aria-current', 'location')
        before = await page.locator('#settings-scroll').evaluate('node => node.scrollTop')
        section = await page.locator('#settings-categories [aria-current=location]').get_attribute('data-settings-category')
        await page.locator('#theme-select').select_option('dark' if theme == 'light' else 'light')
        assert await page.locator('#settings-scroll').evaluate('node => node.scrollTop') == pytest.approx(before, abs=1)
        await page.locator('#language-select').select_option('zh' if language != 'zh' else 'en')
        await expect(page.locator('[name=forecast_pr_history_days]')).to_have_value('48')
        await expect(page.locator(f'[data-settings-category={section}]')).to_have_attribute('aria-current', 'location')
        await page.locator('#language-select').select_option(language)
        await page.locator('#theme-select').select_option(theme)
        history_days = page.locator('[name=forecast_pr_history_days]')
        await history_days.focus()
        await expect(history_days).to_be_in_viewport(ratio=1)
        field = await history_days.bounding_box()
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
    header = await page.locator('.app-header').bounding_box()
    directory = await page.locator('#settings-categories').bounding_box()
    assert directory['y'] == pytest.approx(header['height'], abs=1)
    evidence = []
    for category in ['connection', 'modules', 'sources', 'forecast', 'monitoring']:
        await page.locator(f'[data-settings-category={category}]').click()
        await page.locator('#settings-categories').evaluate('node => node.scrollIntoView({block: "start"})')
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
        assert geometry['directory']['top'] >= header['height'] - 1, geometry
        assert (await page.locator('.app-header').bounding_box())['y'] == 0
        assert await page.evaluate('scrollY') == 0
        assert geometry['scrollWidth'] <= geometry['width'], geometry
        evidence.append({'category': category, **geometry})
    await page.locator('#settings-scroll').evaluate('node => node.scrollTo(0, node.scrollHeight)')
    await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
    field = await page.locator('[name=irradiance_max_age_seconds]').bounding_box()
    dock = await page.locator('#settings-actions').bounding_box()
    scroll = await page.locator('#settings-scroll').bounding_box()
    detail = await page.locator('#settings-scroll').evaluate("""node => ({
        top: node.scrollTop, height: node.clientHeight, extent: node.scrollHeight,
        bottomPadding: getComputedStyle(node).paddingBottom,
        lastField: node.querySelector('[name=irradiance_max_age_seconds]').getBoundingClientRect().toJSON()
    })""")
    (layout_artifacts / 'short-mobile-last-field.json').write_text(json.dumps({'field': field, 'dock': dock, 'scroll': scroll, 'detail': detail}, indent=2), encoding='utf-8')
    await page.screenshot(path=str(layout_artifacts / 'short-mobile-last-field.png'))
    assert scroll['y'] <= field['y'] and field['y'] + field['height'] < dock['y'], {'field': field, 'dock': dock, 'scroll': scroll, 'detail': detail}
    evidence.append({'last_field': field, 'dock': dock, 'scroll': scroll})
    await page.screenshot(path=str(layout_artifacts / 'settings-short-390-430-de.png'))
    for theme in ['light', 'dark']:
        await page.locator('#theme-select').select_option(theme)
        await page.screenshot(path=str(layout_artifacts / f'settings-390-430-{theme}.png'))
    (layout_artifacts / 'settings-short-390-430-de.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    await page.locator('[name=forecast_pr_history_days]').fill('48')
    await page.locator('#history-tab').click()
    await expect(page.locator('dialog')).to_be_visible()
    await page.locator('#keep-editing').click()
    await expect(page.locator('[name=forecast_pr_history_days]')).to_have_value('48')
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
    for category in ['connection', 'modules', 'sources', 'forecast', 'monitoring']:
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
    await page.locator('#monitoring-toggle').click()
    await page.locator('#monitoring-help-toggle').click()
    await expect(page.locator('#monitoring-fields')).to_be_hidden()
    help_panel = page.locator('#monitoring-help')
    await expect(help_panel).to_be_visible()
    assert await help_panel.evaluate('node => node.scrollWidth <= node.clientWidth')
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    await page.screenshot(path=str(layout_artifacts / f'monitoring-help-{width}-{language}.png'))
    await page.locator('#theme-select').select_option('dark')
    await page.screenshot(path=str(layout_artifacts / f'monitoring-help-{width}-{language}-dark.png'))
    await page.locator('#theme-select').select_option('auto')
    await page.locator('#live-tab').click()
    await page.screenshot(path=str(layout_artifacts / f'live-{width}-{language}.png'))
    await page.locator('#history-tab').click()
    await page.screenshot(path=str(layout_artifacts / f'history-{width}-{language}.png'))


async def test_history_summary_and_charts_share_range(layout_page, layout_artifacts, monkeypatch):
    from types import SimpleNamespace
    import pvyieldlens.web as web_module
    import pvyieldlens.service as service_module
    from playwright.async_api import expect
    from test_engine import samples
    from pvyieldlens.engine import calculate

    page, service = layout_page
    start = service.store.cursor
    now = int(start + 86430)
    for offset, power in [(0, 1000), (60, 2000), (120, 3000)]:
        service.store.settle(calculate(service.monitoring_settings, samples(power=power, at=start+offset),
                                      start+offset, start+offset+60), 1, 'UTC')
    clock = SimpleNamespace(time=lambda: now)
    monkeypatch.setattr(web_module, 'time', clock)
    monkeypatch.setattr(service_module, 'time', clock)
    await page.evaluate('now => Date.now = () => now', now * 1000)
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        pass
    async with page.expect_response(lambda response: '/api/history?period=24h' in response.url) as response:
        await page.locator('#history-tab').click()
        await page.locator('#history-range [data-value="24h"]').click()
    payload = await (await response.value).json()
    assert len(payload['windows']) == 2
    assert payload['summary']['estimated_energy_kwh'] == pytest.approx(0.124)
    await expect(page.locator('#history-energy')).to_have_text('0.124')
    await expect(page.locator('#history-pr')).to_have_text('67.2')
    await expect(page.locator('#history-data-completeness')).to_have_count(0)
    for selector in ['#history-chart', '#pr-chart']:
        await page.locator(selector + ' .chart-hit-area').focus()
        await page.keyboard.press('ArrowRight')
        await expect(page.locator(selector + ' .chart-tooltip')).to_contain_text('2,000 W')
        await page.keyboard.press('ArrowRight')
        await expect(page.locator(selector + ' .chart-tooltip')).to_contain_text('3,000 W')
    await expect(page.locator('#history-range-caption')).not_to_be_empty()
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
    await expect(page.locator('#history-totals')).to_have_count(0)
    total = service.snapshot(now=now)['energy_totals']['estimated_energy_lifetime_kwh']
    async with page.expect_response(lambda response: '/api/history?' in response.url):
        await page.locator('#history-range [data-value="7d"]').click()
    await expect(page.locator('#history-energy')).to_have_text('0.186')
    await expect(page.locator('#daily-energy-chart')).to_be_visible()
    await page.locator('#history-aggregation [data-value=settlement]').click()
    await page.locator('#history-chart .chart-hit-area').focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('#history-chart .chart-tooltip')).to_contain_text('1,000 W')
    assert await page.locator('#history-chart path.series').first.evaluate('path => path.getTotalLength()') > 0
    assert service.snapshot(now=now)['energy_totals']['estimated_energy_lifetime_kwh'] == total
    await page.screenshot(path=str(layout_artifacts / 'history-populated-desktop.png'), full_page=True)
    await page.locator('#live-tab').click()
    await expect(page.locator('#history-chart svg')).to_be_hidden()


async def test_dashboard_and_efficiency_remove_quality_copy_in_both_languages(layout_page):
    from playwright.async_api import expect

    page, _ = layout_page
    for language in ['en', 'zh']:
        await page.locator('#language-select').select_option(language)
        for destination in ['live', 'history']:
            await page.locator(f'#{destination}-tab').click()
            await expect(page.locator('#live-data-completeness, #history-data-completeness, #source-diagnostics')).to_have_count(0)
            text = await page.locator(f'#{destination}-page').inner_text()
            assert not any(term in text for term in ['Data completeness', 'Data quality', 'Included settled', '完整率', '数据质量', '纳入时段'])


async def test_empty_generation_charts_and_language_changes(layout_page, layout_artifacts):
    from playwright.async_api import expect

    page, _ = layout_page
    await expect(page.locator('#source-diagnostics')).to_have_count(0)
    for selector in ['#generation-power-chart', '#generation-irradiance-chart', '#generation-temperature-chart']:
        await expect(page.locator(selector + ' .chart-empty')).to_be_visible()
    await page.locator('#language-select').select_option('zh')
    await expect(page.locator('#generation-data h2')).to_have_text('发电数据')
    await page.locator('#generation-data').scroll_into_view_if_needed()
    await page.screenshot(path=str(layout_artifacts / 'generation-empty-zh.png'))

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
    await expect(page.locator('#live-optimizable-power')).to_have_text('372')
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
            controls: [...document.querySelectorAll('.app-header button, .app-header select, .metric, #updated, #connection-state')]
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
    await page.locator('#settings-button').click()
    await expect(page.locator('#settings-page')).to_be_visible()
    await expect(page.locator('#live-page')).not_to_be_visible()
    await page.locator('#live-chart svg').evaluate("node => node.dataset.original = 'hidden'")
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    service.store.add_observations(samples(power=3000, at=now))
    await service.tick(now+60)
    await expect(page.locator('#live-actual')).to_have_text('3,000')
    await expect(page.locator('#live-chart svg')).to_have_attribute('data-original', 'hidden')
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('6100')
    await page.locator('#discard-settings-changes').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('5000')
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
    await page.locator('#history-range [data-value="7d"]').click()
    await page.locator('#theme-select').select_option('light')
    await expect(page.locator('#history-range [data-value="7d"]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#settings-button').click()
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-range [data-value="7d"]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#live-tab').click()
    await expect(page.locator('#live-chart path.series').nth(1)).to_have_attribute('d', curve)


@pytest.mark.parametrize(('width', 'height'), [(1440, 700), (1920, 1080), (2560, 1440), (390, 844)])
async def test_settings_scrollspy_and_bottom_actions(layout_page, layout_artifacts, width, height):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': height})
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#settings-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_be_enabled()
    await expect(page.locator('[data-settings-section]')).to_have_count(5)
    assert await page.locator('#settings-categories button').evaluate_all(
        'buttons => buttons.map(button => button.dataset.settingsCategory)'
    ) == ['connection', 'modules', 'sources', 'forecast', 'monitoring']
    await expect(page.locator('#monitoring-fields')).to_be_hidden()
    for category in ['connection', 'modules', 'sources', 'forecast', 'monitoring']:
        await page.locator(f'[data-settings-category={category}]').click()
        await expect(page.locator(f'[data-settings-category={category}]')).to_have_attribute('aria-pressed', 'true')
        position = await page.locator('#settings-scroll').evaluate('node => node.scrollTop')
        assert 0 <= position <= 24 if category == 'connection' else position > 24
        heading_top = await page.locator('#settings-scroll').evaluate('''(node, category) =>
            node.querySelector(`[data-settings-section=${category}] h2`).getBoundingClientRect().top
                - node.getBoundingClientRect().top''', category)
        assert 0 <= heading_top <= 24 if category == 'connection' else heading_top == pytest.approx(20, abs=1), {'category': category, 'heading_top': heading_top}
    await page.locator('[data-settings-category=forecast]').click()
    for theme in ['light', 'dark']:
        await page.locator('#theme-select').select_option(theme)
        await page.screenshot(path=str(layout_artifacts / f'settings-{width}-{height}-{theme}.png'))
    await page.locator('#settings-scroll').evaluate('node => node.scrollTop = 0')
    await expect(page.locator('[data-settings-category=connection]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#settings-scroll').evaluate('''node => {
        node.scrollTop += node.querySelector('[data-settings-section=sources] h2').getBoundingClientRect().top
            - node.getBoundingClientRect().top - 20;
    }''')
    await expect(page.locator('[data-settings-category=sources]')).to_have_attribute('aria-pressed', 'true')
    await page.locator('#settings-scroll').evaluate('node => node.scrollTop = node.scrollHeight')
    await expect(page.locator('[data-settings-category=monitoring]')).to_have_attribute('aria-pressed', 'true')
    boxes = await page.evaluate('''() => {
        const box = selector => {
            const {left, right, top, bottom} = document.querySelector(selector).getBoundingClientRect();
            return {left, right, top, bottom};
        };
        return {actions: box('#settings-actions'), last: box('[name=irradiance_max_age_seconds]'),
            scroll: box('#settings-scroll'), width: innerWidth, height: innerHeight,
            documentWidth: document.documentElement.scrollWidth};
    }''')
    assert boxes['actions']['bottom'] <= boxes['height']
    assert boxes['actions']['left'] >= 0 and boxes['actions']['right'] <= boxes['width']
    assert boxes['last']['top'] >= boxes['scroll']['top']
    assert boxes['last']['bottom'] < boxes['actions']['top']
    assert boxes['documentWidth'] <= boxes['width']
    await page.locator('[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('')
    await page.locator('[data-settings-category=forecast]').click()
    await page.locator('#save-button').click()
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_be_focused()
    await expect(page.locator('[data-settings-category=modules]')).to_have_attribute('aria-pressed', 'true')
    focused = await page.locator('[name=total_max_power_at_stc_w]').bounding_box()
    assert focused['y'] >= boxes['scroll']['top']
    assert focused['y'] + focused['height'] < boxes['actions']['top']


async def test_settings_sections_remeasure_when_visible_resized_and_expanded(layout_page):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.emulate_media(reduced_motion='reduce')
    await page.set_viewport_size({'width': 2560, 'height': 1440})
    for mode in ['docker', 'app']:
        if mode == 'app':
            async def app_configuration(route):
                response = await route.fetch()
                configuration = await response.json()
                configuration['mode'] = 'app'
                await route.fulfill(response=response, json=configuration)
            await page.route('**/api/config', app_configuration)
            await page.reload()
        await page.locator('#settings-button').click()
        await expect(page.locator('[name=total_max_power_at_stc_w]')).to_be_enabled()
        await page.set_viewport_size({'width': 1440, 'height': 700})
        await page.locator('[data-settings-category=monitoring]').click()
        await page.locator('#settings-scroll').evaluate('node => node.scrollTop -= 3')
        await page.locator('[name=update_interval_seconds]').focus()
        await expect(page.locator('[data-settings-category=monitoring]')).to_have_attribute('aria-current', 'location')
        reading_top = await page.locator('#settings-scroll').evaluate('''node =>
            node.querySelector('[data-settings-section=monitoring] h2').getBoundingClientRect().top - node.getBoundingClientRect().top''')
        await page.set_viewport_size({'width': 2560, 'height': 1440})
        await expect(page.locator('[data-settings-category=monitoring]')).to_have_attribute('aria-current', 'location')
        await page.wait_for_function('''top => {
            const container = document.querySelector('#settings-scroll');
            return Math.abs(container.querySelector('[data-settings-section=monitoring] h2').getBoundingClientRect().top
                - container.getBoundingClientRect().top - top) <= 1;
        }''', arg=reading_top)
        await expect(page.locator('[name=update_interval_seconds]')).to_be_focused()
        for width, height in [(2560, 1440), (1920, 1080), (1440, 700), (390, 844), (390, 430), (2560, 1440)]:
            await page.set_viewport_size({'width': width, 'height': height})
            for category in ['monitoring', 'forecast']:
                await page.locator(f'[data-settings-category={category}]').click()
                await expect(page.locator(f'[data-settings-category={category}]')).to_have_attribute('aria-current', 'location')
                await page.wait_for_function('''category => {
                    const container = document.querySelector('#settings-scroll');
                    const heading = container.querySelector(`[data-settings-section=${category}] h2`);
                    return Math.abs(heading.getBoundingClientRect().top - container.getBoundingClientRect().top - 20) <= 1;
                }''', arg=category)
        for direction in ['custom', '180']:
            await page.locator('#forecast-direction').select_option(direction)
            await page.locator('[data-settings-category=monitoring]').click()
            await page.locator('#monitoring-toggle').click()
            await expect(page.locator('#monitoring-fields')).to_be_hidden()
            await page.locator('#settings-scroll').evaluate('node => node.scrollTo(0, node.scrollHeight)')
            await expect(page.locator('[data-settings-category=monitoring]')).to_have_attribute('aria-current', 'location')
            await page.wait_for_function('''() => {
                const container = document.querySelector('#settings-scroll');
                const heading = container.querySelector('[data-settings-section=monitoring] h2');
                return Math.abs(heading.getBoundingClientRect().top - container.getBoundingClientRect().top - 20) <= 1;
            }''')
        await page.locator('#discard-settings-changes').click()
        await page.locator('#live-tab').click()
        await page.locator('#settings-button').click()
        await expect(page.locator('[name=total_max_power_at_stc_w]')).to_be_enabled()
        await expect(page.locator('[data-settings-category=connection]')).to_have_attribute('aria-current', 'location')
        await page.locator('[data-settings-category=monitoring]').click()
        await expect(page.locator('[data-settings-category=monitoring]')).to_have_attribute('aria-current', 'location')
        await page.locator('#live-tab').click()


@pytest.mark.parametrize('width', [320, 390])
@pytest.mark.parametrize('theme', ['light', 'dark'])
async def test_sensor_labels_and_clear_buttons_fit_narrow_settings(layout_page, layout_artifacts, width, theme):
    from playwright.async_api import expect

    page, _ = layout_page
    await page.set_viewport_size({'width': width, 'height': 840})
    await page.emulate_media(reduced_motion='reduce')
    await page.locator('#theme-select').select_option(theme)
    await page.locator('#language-select').select_option('de')
    await page.locator('#settings-button').click()
    await page.locator('[data-settings-category=sources]').click()
    section = page.locator('[data-settings-section=sources]')
    await expect(section.get_by_role('button')).to_have_count(3)
    for field in await section.locator('input[role=combobox]').all():
        bounds = await field.evaluate('''field => {
            const box = node => node.getBoundingClientRect().toJSON();
            const label = field.labels[0];
            const text = new Range();
            text.selectNodeContents(label);
            return {input: box(field), button: box(field.parentElement.querySelector('button')),
                text: box(text), section: box(field.closest('[data-settings-section]'))};
        }''')
        control, clear, text, panel = (bounds[key] for key in ('input', 'button', 'text', 'section'))
        assert panel['left'] <= text['left'] < text['right'] <= panel['right']
        assert control['left'] < clear['left'] < clear['right'] <= control['right'] <= width
        assert control['top'] <= clear['top'] < clear['bottom'] <= control['bottom']
        assert clear['width'] >= 24 and clear['height'] >= 24
    await page.screenshot(path=str(layout_artifacts / f'settings-pickers-{width}-{theme}.png'))


@pytest.mark.parametrize('width', [390, 1440])
async def test_settings_location_and_angle_layout(layout_page, layout_artifacts, width):
    from playwright.async_api import expect
    from pvyieldlens.settings import ForecastSettings, HALocation

    page, service = layout_page
    origin = (await (await page.request.get(page.url + 'api/config')).json())['connection']['url']
    await service.configure(service.monitoring_settings, origin=origin)
    service.forecast.configure(service.monitoring_settings,
        ForecastSettings(tilt_entity='number.tracker_tilt', azimuth_deg=123.5), origin,
        HALocation(origin=origin, latitude=52.51739, longitude=13.39513,
                   location_name='West terrace · Community solar array', home_timezone='America/Argentina/Buenos_Aires'))
    await page.set_viewport_size({'width': width, 'height': 1050 if width == 390 else 930})
    await page.emulate_media(reduced_motion='reduce')
    await page.reload()
    await page.locator('#settings-button').click()

    for theme in ('light', 'dark'):
        await page.locator('#theme-select').select_option(theme)
        await page.locator('[data-settings-category=modules]').click()
        tilt = page.get_by_role('group', name='Module tilt', exact=True)
        direction = page.get_by_role('group', name='Module direction', exact=True)
        await expect(tilt.locator('.angle-reading')).to_have_text('number.tracker_tilt · Temporarily unreadable')
        await expect(direction.locator('[name=forecast_azimuth_deg]')).to_have_value('123.5')
        tilt_box, direction_box = await tilt.bounding_box(), await direction.bounding_box()
        if width == 390:
            assert direction_box['y'] > tilt_box['y'] + tilt_box['height']
            await tilt.evaluate('''group => {
                const scroll = group.closest('#settings-scroll');
                scroll.scrollTop += group.getBoundingClientRect().top - scroll.getBoundingClientRect().top - 10;
            }''')
        else:
            assert direction_box['y'] == pytest.approx(tilt_box['y'], abs=1)
            assert direction_box['x'] > tilt_box['x'] + tilt_box['width']
        await page.screenshot(path=str(layout_artifacts / f'settings-angles-{width}-{theme}.png'))
        await page.locator('[data-settings-category=forecast]').click()
        summary = page.locator('#forecast-location')
        await expect(summary.locator('dd')).to_have_text([
            'West terrace · Community solar array', '52.51739, 13.39513', 'America/Argentina/Buenos_Aires'])
        assert await summary.evaluate('node => node.scrollWidth <= node.clientWidth')
        assert await page.evaluate('document.documentElement.scrollWidth === innerWidth')
        await page.screenshot(path=str(layout_artifacts / f'settings-location-{width}-{theme}.png'))
