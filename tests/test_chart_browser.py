import os
import re
from pathlib import Path

import pytest
from test_browser import browser_workspace

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1')


@pytest.fixture
async def chart_page(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    state = {'values': [0, 80, 100, 20, 0], 'ends': [60, 180, 360, 660, 900]}

    async def history(route):
        ends = state['ends']
        starts = state.get('starts', [0, *ends])
        windows = [{'start': starts[index], 'end': end, 'estimated_power': value,
                    'actual_power': value, 'pr': 125 if value is not None else None,
                    'optimizable_power': 0 if value is not None else None,
                    'estimated_energy_wh': 1, 'actual_energy_wh': 1, 'valid_seconds': end - starts[index],
                    'coverage_percent': 100 if value is not None else 0,
                    'quality': 'complete' if value is not None else 'unavailable', 'reason': None, 'revision': 1}
                   for index, (end, value) in enumerate(zip(ends, state['values']))]
        await route.fulfill(json={'windows': windows, 'requested_range': {'start': 0, 'end': ends[-1]},
                                 'summary': {'start': 0, 'end': ends[-1], 'estimated_energy_kwh': 0.005,
                                             'pr': 125, 'coverage_percent': 100, 'valid_seconds': 900}})

    await page.route('**/api/history?*', history)
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-chart svg')).to_be_visible()
    return page, state


async def test_curve_is_bounded_between_samples(chart_page):
    from playwright.async_api import expect

    page, state = chart_page
    geometry = await page.locator('#history-chart').evaluate('''host => {
        const path = host.querySelector('path.series');
        const points = [0, 80, 100, 20, 0].map((value, index) => ({
            x: 48 + ([60,180,360,660,900][index] - 60) / 840 * (host.clientWidth - 60),
            y: 16 + (110 - value) / 110 * (host.clientHeight - 50)
        }));
        const samples = Array.from({length: 2001}, (_, index) => {
            const point = path.getPointAtLength(path.getTotalLength() * index / 2000);
            return {x: point.x, y: point.y};
        });
        return {points, samples, curve: path.getAttribute('d')};
    }''')
    assert 'C' in geometry['curve']
    for sample in geometry['samples']:
        pairs = [(left, right) for left, right in zip(geometry['points'], geometry['points'][1:])
                 if left['x'] - 0.05 <= sample['x'] <= right['x'] + 0.05]
        assert pairs, sample
        assert any(min(left['y'], right['y']) - 0.05 <= sample['y'] <= max(left['y'], right['y']) + 0.05
                   for left, right in pairs), sample
    state['values'][2] = None
    await page.locator('#history-range').select_option('7')
    await expect(page.locator('#history-chart path.series').first).not_to_have_attribute('d', geometry['curve'])
    gap = await page.locator('#history-chart').evaluate('''host => {
        const path = host.querySelector('path.series');
        const x = at => 48 + (at - 60) / 840 * (host.clientWidth - 60);
        return {start: x(180), end: x(660), samples: Array.from({length: 1001}, (_, i) =>
            path.getPointAtLength(path.getTotalLength() * i / 1000).x)};
    }''')
    assert all(x <= gap['start'] + 0.05 or x >= gap['end'] - 0.05 for x in gap['samples'])


async def test_tooltip_works_away_from_the_line(chart_page):
    from playwright.async_api import expect

    page, state = chart_page
    chart = page.locator('#history-chart')
    area = chart.locator('.chart-hit-area')
    await expect(area).to_be_visible()
    box = await area.bounding_box()
    await page.mouse.move(box['x'] + box['width'] * 120 / 840, box['y'] + 3)
    tooltip = chart.locator('.chart-tooltip')
    await expect(tooltip).to_contain_text('80 W')
    await expect(tooltip).to_contain_text('125 %')
    await expect(chart.locator('.active-series-marker')).to_have_count(2)
    svg = await chart.locator('svg').evaluate("node => node.dataset.original = 'inspect'")
    state['values'][2] = None
    await page.locator('#history-range').select_option('7')
    await expect(chart.locator('svg')).not_to_have_attribute('data-original', svg)
    box = await area.bounding_box()
    await page.mouse.move(box['x'] + box['width'] * 300 / 840, box['y'] + box['height'] - 3)
    await expect(tooltip).to_contain_text('Unavailable')
    await expect(tooltip).to_contain_text('— W')
    assert await chart.locator('.active-series-marker:visible').count() == 0
    await page.mouse.move(box['x'], box['y'] + 3)
    await expect(tooltip).to_contain_text('0 W')
    await page.mouse.move(0, 0)
    await expect(tooltip).to_be_hidden()


async def test_missing_settlement_gap_is_unavailable_but_valid_edges_remain_inspectable(chart_page):
    from playwright.async_api import expect

    page, state = chart_page
    state['starts'] = [0, 60, 300, 600, 660]
    await page.locator('#history-range').select_option('7')
    chart = page.locator('#history-chart')
    await expect(chart.locator('path.series').first).to_have_attribute('d', re.compile(r'^M[^M]+M[^M]+M[^M]+$'))
    box = await chart.locator('.chart-hit-area').bounding_box()
    tooltip = chart.locator('.chart-tooltip')
    await page.mouse.move(box['x'] + (240 - 60) / 840 * box['width'], box['y'] + 3)
    await expect(tooltip).to_contain_text('Unavailable')
    await expect(tooltip).to_contain_text('— W')
    assert await chart.locator('.active-series-marker[visibility=visible]').count() == 0
    # Mouse coordinates round to subpixels; exact interval boundaries are unit-tested.
    for at, value in [(179.9, '80 W'), (300.1, '100 W'), (359.9, '100 W'), (600.1, '20 W')]:
        await page.mouse.move(box['x'] + (at - 60) / 840 * box['width'], box['y'] + 3)
        await expect(tooltip).to_contain_text(value)
        await expect(tooltip).to_contain_text('Data complete')


async def test_inspection_reads_original_thinned_record(chart_page):
    from playwright.async_api import expect

    page, state = chart_page
    state['ends'] = list(range(1, 1202))
    state['values'] = [index if index != 502 else 0 for index in range(1201)]
    await page.locator('#history-range').select_option('7')
    chart = page.locator('#history-chart')
    await expect(chart.locator('.chart-hit-area')).to_be_visible()
    # The zero at index 502 is omitted from the displayed sample. Geometry there
    # follows its neighboring retained values, while inspection must still return zero.
    await page.wait_for_function("document.querySelector('#history-chart .chart-hit-area').getAttribute('aria-valuemax') === '1201'")
    displayed_power = await chart.evaluate('''host => {
        const path = host.querySelector('path.series'), target = 48 + 502 / 1200 * (host.clientWidth - 60);
        const samples = Array.from({length: 10001}, (_, index) => path.getPointAtLength(path.getTotalLength() * index / 10000));
        const point = samples.reduce((nearest, point) => Math.abs(point.x - target) < Math.abs(nearest.x - target) ? point : nearest);
        return 1320 - (point.y - 16) / (host.clientHeight - 50) * 1320;
    }''')
    assert displayed_power > 400
    box = await chart.locator('.chart-hit-area').bounding_box()
    await page.mouse.move(box['x'] + 502 / 1200 * box['width'], box['y'] + 3)
    await expect(chart.locator('.chart-tooltip')).to_contain_text('0 W')


async def test_keyboard_and_touch_inspection(chart_page):
    from playwright.async_api import expect

    page, _ = chart_page
    chart = page.locator('#history-chart')
    hit = chart.locator('.chart-hit-area')
    await expect(hit).to_be_visible()
    await hit.focus()
    await page.keyboard.press('ArrowRight')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('0 W')
    await page.keyboard.press('ArrowRight')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('80 W')
    await page.keyboard.press('ArrowLeft')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('0 W')
    await page.keyboard.press('Escape')
    await expect(chart.locator('.chart-tooltip')).to_be_hidden()
    context = await page.context.browser.new_context(has_touch=True, is_mobile=True,
        viewport={'width': 390, 'height': 600},
        http_credentials={'username': 'admin', 'password': 'browser-test'})
    touch = await context.new_page()
    await touch.goto(page.url)
    # Reuse the fixture's real API response for the second, touch-capable viewer.
    # API routes belong to the first page, so read its response through fetch.
    payload = await page.evaluate("fetch('api/history?start=0&end=1000').then(response => response.json())")
    await touch.route('**/api/history?*', lambda route: route.fulfill(json=payload))
    await touch.locator('#history-tab').click()
    touch_chart = touch.locator('#history-chart')
    await expect(touch_chart.locator('.chart-hit-area')).to_be_visible()
    await touch_chart.scroll_into_view_if_needed()
    box = await touch_chart.locator('.chart-hit-area').bounding_box()
    await touch.touchscreen.tap(box['x'] + box['width'] / 2, box['y'] + 20)
    await expect(touch_chart.locator('.chart-tooltip')).to_be_visible()
    await touch.touchscreen.tap(10, 10)
    await expect(touch_chart.locator('.chart-tooltip')).to_be_hidden()
    assert await touch_chart.locator('.chart-hit-area').evaluate("node => getComputedStyle(node).touchAction") == 'pan-y'
    session = await context.new_cdp_session(touch)
    before = await touch.evaluate('scrollY')
    await session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': box['x'] + 20, 'y': box['y'] + 100}]})
    for distance in [20, 40, 70, 100]:
        await session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': box['x'] + 20, 'y': box['y'] + 100 - distance}]})
    await session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    await touch.wait_for_function('before => scrollY > before', arg=before)
    await context.close()


@pytest.mark.parametrize('language', ['fr', 'de'])
async def test_tooltip_stays_inside_narrow_chart(chart_page, language):
    from playwright.async_api import expect

    page, _ = chart_page
    await page.set_viewport_size({'width': 320, 'height': 844})
    await page.locator('#language-select').select_option(language)
    await page.locator('#theme-select').select_option('dark')
    chart = page.locator('#history-chart')
    hit = chart.locator('.chart-hit-area')
    await expect(hit).to_be_visible()
    await chart.scroll_into_view_if_needed()
    box = await hit.bounding_box()
    await page.mouse.move(box['x'] + box['width'] - 1, box['y'] + 10)
    await expect(chart.locator('.chart-tooltip')).to_be_visible()
    bounds = await chart.evaluate('''host => {
        const chart = host.getBoundingClientRect(), tip = host.querySelector('.chart-tooltip').getBoundingClientRect();
        return {left: chart.left, right: chart.right, top: chart.top, bottom: chart.bottom,
            tipLeft: tip.left, tipRight: tip.right, tipTop: tip.top, tipBottom: tip.bottom,
            tipScroll: host.querySelector('.chart-tooltip').scrollHeight, tipHeight: host.querySelector('.chart-tooltip').clientHeight};
    }''')
    assert bounds['tipLeft'] >= bounds['left'] and bounds['tipRight'] <= bounds['right'] + 1
    assert bounds['tipTop'] >= bounds['top'] and bounds['tipBottom'] <= bounds['bottom'] + 1
    assert bounds['tipScroll'] <= bounds['tipHeight']
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    Path('artifacts').mkdir(exist_ok=True)
    await page.screenshot(path=f'artifacts/chart-inspection-{language}-320-dark.png')


async def test_partially_visible_tooltip_keeps_all_rows_reachable(chart_page):
    from playwright.async_api import expect

    page, _ = chart_page
    await page.set_viewport_size({'width': 320, 'height': 600})
    await page.locator('#language-select').select_option('fr')
    chart = page.locator('#history-chart')
    await chart.scroll_into_view_if_needed()
    await chart.evaluate('host => scrollTo(0, host.getBoundingClientRect().top + scrollY - innerHeight + 90)')
    await page.wait_for_function("() => Math.abs(document.querySelector('#history-chart').getBoundingClientRect().top - innerHeight + 90) < 1")
    hit = chart.locator('.chart-hit-area')
    box = await hit.bounding_box()
    await page.mouse.move(box['x'] + box['width'] - 1, box['y'] + 4)
    tooltip = chart.locator('.chart-tooltip')
    await expect(tooltip).to_be_visible()
    assert await tooltip.evaluate('node => node.scrollHeight > node.clientHeight')
    await tooltip.hover()
    await page.mouse.wheel(0, 200)
    await page.wait_for_function("() => document.querySelector('#history-chart .chart-tooltip').scrollTop > 0")
    assert await tooltip.evaluate('node => node.scrollTop + node.clientHeight >= node.scrollHeight - 1')
    await hit.focus()
    await page.keyboard.press('Tab')
    await expect(tooltip).to_be_focused()
    await page.keyboard.press('Home')
    await expect(tooltip).to_be_visible()
    await page.keyboard.press('End')
    await page.wait_for_function("() => { const tip = document.querySelector('#history-chart .chart-tooltip'); return tip.scrollTop + tip.clientHeight >= tip.scrollHeight - 1; }")
    await page.keyboard.press('Escape')
    await expect(tooltip).to_be_hidden()
    await expect(hit).to_be_focused()
