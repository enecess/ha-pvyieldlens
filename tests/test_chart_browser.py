import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from urllib.parse import parse_qs, urlsplit
from history_fixtures import history_payload
from test_browser import browser_workspace
from test_forecast_browser import forecast_page

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1')


@pytest.mark.parametrize('scenario,chart_id,zero', [
    ('history-single', 'history-chart', False), ('history-single', 'pr-chart', True),
    ('history-isolated', 'history-chart', True), ('history-isolated', 'pr-chart', False),
    ('live-single', 'live-chart', False), ('live-isolated', 'live-chart', True),
])
@pytest.mark.parametrize('touch', [False, True], ids=['mouse', 'touch'])
async def test_singleton_glyph_pixel_picking(browser_workspace, scenario, chart_id, zero, touch):
    from playwright.async_api import expect

    page, service, _ = browser_workspace
    await page.set_viewport_size({'width': 1440, 'height': 1000})
    now = int(time.time())
    endpoint = now - 180
    await service.configure(service.monitoring_settings.model_copy(update={'update_interval_seconds': 60}))
    record = {'start': endpoint - 60, 'end': endpoint, 'valid_seconds': 60,
              'estimated_power_w': 4400, 'actual_power_w': 0 if zero else 3885.2,
              'pr': 0 if zero else 88.3, 'optimizable_power_w': 4400 if zero else 514.8,
              'data_completeness_percent': 100, 'estimated_energy_wh': 4400 / 60,
              'actual_energy_wh': 0 if zero else 3885.2 / 60,
              'quality': 'complete', 'reason': None, 'revision': service.store.revision}
    records = [record]
    if scenario.endswith('isolated'):
        records = [{**record, 'start': endpoint - 420, 'end': endpoint - 360},
                   {**record, 'start': endpoint - 360, 'end': endpoint - 300}, record,
                   {**record, 'start': endpoint + 120, 'end': endpoint + 180}]

    async def snapshot(route):
        result = service.snapshot(now=now)
        result.update(connected=True, calculated_at=endpoint, live_window=record, latest_settled_window=record)
        await route.fulfill(json=result)

    async def history(route):
        await route.fulfill(json=history_payload(records, {'start': records[0]['start'], 'end': records[-1]['end'],
                        'actual_energy_kwh': record['actual_energy_wh'] / 1000,
                        'estimated_energy_kwh': record['estimated_energy_wh'] / 1000,
                        'pr': record['pr'], 'data_completeness_percent': 100, 'valid_seconds': 60},
            {'start': records[0]['start'], 'end': records[-1]['end']}, parse_qs(urlsplit(route.request.url).query).get('period', ['today'])[0]))

    async def live(route):
        await route.fulfill(json={
            'configured': True, 'recovering': False, 'range': {'start': now - 600, 'end': now},
            'step_seconds': 60, 'context': {'revision': service.store.revision,
                                          'monitoring_settings': service.monitoring_settings.public()},
            'points': [{'at': point['end'], **point} for point in records],
        })

    url = page.url
    touch_context = None
    if touch:
        touch_context = await page.context.browser.new_context(has_touch=True, viewport={'width': 1440, 'height': 1000},
            http_credentials={'username': 'admin', 'password': 'browser-test'})
        page = await touch_context.new_page()
    await page.route('**/api/snapshot', snapshot)
    await page.route('**/api/history?*', history)
    await page.route('**/api/live-series', live)
    await page.clock.set_fixed_time(datetime.fromtimestamp(now, timezone.utc))
    await page.goto(url)
    if chart_id != 'live-chart':
        await page.locator('#history-tab').click()
    chart = page.locator(f'#{chart_id}')
    hit = chart.locator('.chart-hit-area')
    await expect(chart.locator('.series-point').first).to_be_visible()
    await chart.scroll_into_view_if_needed()
    box = await hit.bounding_box()
    start = float(await hit.get_attribute('aria-valuemin'))
    end = float(await hit.get_attribute('aria-valuemax'))
    target = box['x'] + (endpoint - start) / (end - start) * box['width']
    dots = await chart.locator('.series-point').evaluate_all('''nodes => nodes.map(node => {
        const box = node.getBoundingClientRect();
        return {x: box.x + box.width / 2, y: box.y + box.height / 2};
    })''')
    dot = min(dots, key=lambda point: abs(point['x'] - target))
    reads = []
    tip = chart.locator('.chart-tooltip')
    pointer_y = min(box['y'] + box['height'] - 1, max(box['y'] + 1, dot['y']))

    async def inspect(offset):
        if touch:
            await page.touchscreen.tap(target + offset, pointer_y)
        else:
            await page.mouse.move(0, 0)
            await page.mouse.move(target + offset, pointer_y)
        await expect(tip).to_be_visible()
        reads.append({'offset_css_px': offset, 'text': await tip.inner_text(),
                      'at': float(await hit.get_attribute('aria-valuenow')),
                      'markers': await chart.locator('.active-series-marker[visibility=visible]').count()})

    # The explicit settlement range puts a single History point on the right edge.
    edge_single = scenario == 'history-single'
    offsets = ([-1, -11] if touch else [-1, -5]) if edge_single else ([1, 11] if touch else [1, 5])
    if not edge_single and target - 1 > box['x']:
        offsets.insert(0, -1)
    if not edge_single:
        offsets.append(13 if touch else 7)
    assert all(box['x'] <= target + offset <= box['x'] + box['width'] for offset in offsets), {
        'target': target, 'plot': box, 'offsets': offsets}
    for offset in offsets:
        await inspect(offset)
    await hit.focus()
    await page.keyboard.press('ArrowLeft')
    keyboard = await tip.inner_text()
    keyboard_at = float(await hit.get_attribute('aria-valuenow'))
    await page.keyboard.press('ArrowLeft')
    evidence = Path('artifacts/history-daily-singleton')
    evidence.mkdir(parents=True, exist_ok=True)
    stem = f'{scenario}-{chart_id}-{"touch" if touch else "mouse"}'
    report = {'target': dot, 'axis': [start, end], 'reads': reads, 'keyboard': keyboard, 'keyboard_at': keyboard_at,
              'previous_keyboard_at': float(await hit.get_attribute('aria-valuenow'))}
    (evidence / f'{stem}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    await page.screenshot(path=str(evidence / f'{stem}.png'))
    print(stem, json.dumps(report))
    if touch_context:
        await touch_context.close()
    for read in (reads if edge_single else reads[:-1]):
        assert read['at'] == endpoint, read
        assert read['markers'] == (1 if chart_id == 'pr-chart' else 2), read
        assert ('0 W' if zero else '3,885.2 W') in read['text'], read
        assert ('0 %' if zero else '88.3 %') in read['text'], read
    if not edge_single:
        assert reads[-1]['markers'] == 0, reads[-1]
        assert reads[-1]['text'].count('— %' if chart_id == 'pr-chart' else '— W') == (1 if chart_id == 'pr-chart' else 2), reads[-1]
        assert 'Unavailable' not in reads[-1]['text'], reads[-1]
    assert ('0 W' if zero else '3,885.2 W') in keyboard
    assert keyboard_at == (endpoint if len(records) == 1 else endpoint + 180)
    assert report['previous_keyboard_at'] == endpoint


async def test_single_forecast_row_keeps_quarter_hour_interval_selection(forecast_page):
    from playwright.async_api import expect

    page, state, _ = forecast_page
    row = state['view']['intervals'][12]
    state['view']['intervals'] = [row]
    state['view']['days'] = state['view']['days'][:1]
    await page.locator('#forecast-tab').click()
    chart = page.locator('#forecast-chart')
    hit = chart.locator('.chart-hit-area')
    await expect(hit).to_be_visible()
    await chart.scroll_into_view_if_needed()
    box = await hit.bounding_box()
    start = float(await hit.get_attribute('aria-valuemin'))
    end = float(await hit.get_attribute('aria-valuemax'))
    reads = []
    for at in [row['start'] + 60, row['end'] - 60, row['end'] + 60]:
        pointer_x = box['x'] + (at - start) / (end - start) * box['width']
        await page.mouse.move(pointer_x, box['y'] + 3)
        tooltip = chart.locator('.chart-tooltip')
        reads.append({'at': at, 'text': await tooltip.inner_text(),
                      'markers': await chart.locator('.active-series-marker[visibility=visible]').count()})
        if at < row['end']:
            guide_x = await chart.locator('.chart-guide[visibility=visible]').evaluate('node => node.getBoundingClientRect().x')
            tip = await tooltip.bounding_box()
            assert abs(guide_x - pointer_x) > 2
            assert tip['x'] >= max(pointer_x, guide_x) + 11 or tip['x'] + tip['width'] <= min(pointer_x, guide_x) - 11
    print('forecast-single-interval', json.dumps(reads))
    assert all(read['markers'] == 2 and '3,720 W' in read['text'] and '3,348 W' in read['text'] for read in reads[:2])
    assert reads[-1]['markers'] == 0 and reads[-1]['text'].count('— W') == 2


@pytest.fixture
async def chart_page(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    state = {'values': [0, 80, 100, 20, 0], 'ends': [60, 180, 360, 660, 900]}

    async def history(route):
        ends = state['ends']
        starts = state.get('starts', [0, *ends])
        windows = [{'start': starts[index], 'end': end, 'estimated_power_w': value,
                    'actual_power_w': value, 'pr': 125 if value is not None else None,
                    'optimizable_power_w': 0 if value is not None else None,
                    'estimated_energy_wh': 1, 'actual_energy_wh': 1, 'valid_seconds': end - starts[index],
                    'data_completeness_percent': 100 if value is not None else 0,
                    'quality': 'complete' if value is not None else 'unavailable', 'reason': None, 'revision': 1}
                   for index, (end, value) in enumerate(zip(ends, state['values']))]
        await route.fulfill(json=history_payload(windows,
            {'start': 0, 'end': ends[-1], 'estimated_energy_kwh': 0.005, 'actual_energy_kwh': 0.005,
             'pr': 125, 'data_completeness_percent': 100, 'valid_seconds': 900},
            {'start': 0, 'end': ends[-1]}, parse_qs(urlsplit(route.request.url).query).get('period', ['today'])[0]))

    await page.route('**/api/history?*', history)
    # Keep the fixture's early-epoch windows inside the rolling query range.
    await page.clock.set_fixed_time(datetime.fromtimestamp(2000, timezone.utc))
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-chart svg')).to_be_visible()
    await page.locator('#history-chart').scroll_into_view_if_needed()
    return page, state


@pytest.mark.parametrize('touch', [False, True], ids=['mouse', 'touch'])
async def test_covered_continuous_run_precedes_overlapping_singleton(chart_page, touch):
    from playwright.async_api import expect

    page, state = chart_page
    await page.set_viewport_size({'width': 1200, 'height': 1000})
    state.update(ends=[40, 45, 46, 1040], starts=[0, 44, 45, 1000], values=[10, 20, 30, None])
    await page.locator('#history-range [data-value="24h"]').click()
    await page.locator('#history-chart').scroll_into_view_if_needed()
    await expect(page.locator('#history-chart .chart-hit-area')).to_have_attribute('aria-valuemax', '1040')
    touch_context = None
    if touch:
        payload = await page.evaluate("fetch('api/history?start=0&end=2000').then(response => response.json())")
        touch_context = await page.context.browser.new_context(has_touch=True, viewport={'width': 1200, 'height': 1000},
            http_credentials={'username': 'admin', 'password': 'browser-test'})
        viewer = await touch_context.new_page()
        await viewer.route('**/api/history?*', lambda route: route.fulfill(json=payload))
        await viewer.goto(page.url)
        page = viewer
        await page.locator('#history-tab').click()
    chart = page.locator('#history-chart')
    hit = chart.locator('.chart-hit-area')
    await expect(hit).to_have_attribute('aria-valuemax', '1040')
    await chart.scroll_into_view_if_needed()
    box = await hit.bounding_box()
    pointer_x = box['x'] + 45.1 / 1040 * box['width']
    if touch:
        await page.touchscreen.tap(pointer_x, box['y'] + 3)
    else:
        await page.mouse.move(pointer_x, box['y'] + 3)
    tip = chart.locator('.chart-tooltip')
    await expect(tip).to_be_visible()
    result = {'singleton_distance_css_px': pointer_x - (box['x'] + 40 / 1040 * box['width']),
              'at': float(await hit.get_attribute('aria-valuenow')), 'text': await tip.inner_text()}
    print('covered-run-overlap', 'touch' if touch else 'mouse', json.dumps(result))
    if touch_context:
        await touch_context.close()
    assert result['singleton_distance_css_px'] < 6
    assert result['at'] == 45, result
    assert '20 W' in result['text'], result


async def test_curve_is_bounded_between_samples(chart_page):
    from playwright.async_api import expect

    page, state = chart_page
    geometry = await page.locator('#history-chart').evaluate('''host => {
        const path = host.querySelector('path.series');
        const points = [0, 80, 100, 20, 0].map((value, index) => ({
            x: 48 + [60,180,360,660,900][index] / 900 * (host.clientWidth - 60),
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
    await page.locator('#history-range [data-value="24h"]').click()
    await page.locator('#history-chart').scroll_into_view_if_needed()
    await expect(page.locator('#history-chart path.series').first).not_to_have_attribute('d', geometry['curve'])
    gap = await page.locator('#history-chart').evaluate('''host => {
        const path = host.querySelector('path.series');
        const x = at => 48 + at / 900 * (host.clientWidth - 60);
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
    await page.mouse.move(box['x'] + box['width'] * 180 / 900, box['y'] + 3)
    tooltip = chart.locator('.chart-tooltip')
    await expect(tooltip).to_contain_text('80 W')
    await expect(tooltip).to_contain_text('125 %')
    await expect(chart.locator('.active-series-marker')).to_have_count(2)
    svg = await chart.locator('svg').evaluate("node => node.dataset.original = 'inspect'")
    state['values'][2] = None
    await page.locator('#history-range [data-value="24h"]').click()
    await page.locator('#history-chart').scroll_into_view_if_needed()
    await expect(chart.locator('svg')).not_to_have_attribute('data-original', svg)
    box = await area.bounding_box()
    await page.mouse.move(box['x'] + box['width'] * 360 / 900, box['y'] + box['height'] - 3)
    await expect(tooltip).not_to_contain_text('Unavailable')
    await expect(tooltip).to_contain_text('— W')
    assert await chart.locator('.active-series-marker:visible').count() == 0
    await page.mouse.move(box['x'], box['y'] + 3)
    await expect(tooltip).to_contain_text('0 W')
    await page.mouse.move(0, 0)
    await expect(tooltip).to_be_hidden()


async def test_tooltip_clears_pointer_and_guide_at_both_edges(chart_page):
    from playwright.async_api import expect

    page, _ = chart_page
    chart = page.locator('#history-chart')
    hit = chart.locator('.chart-hit-area')
    tooltip = chart.locator('.chart-tooltip')
    guide = chart.locator('.chart-guide[visibility=visible]')
    box = await hit.bounding_box()

    pointer_x = box['x'] + 1
    await page.mouse.move(pointer_x, box['y'] + 3)
    await expect(hit).to_have_attribute('aria-valuenow', '60')
    await expect(tooltip).to_contain_text('0 W')
    await expect(tooltip).to_contain_text('125 %')
    guide_x = await guide.evaluate('node => node.getBoundingClientRect().x')
    assert (await tooltip.bounding_box())['x'] >= max(pointer_x, guide_x) + 11

    pointer_x = box['x'] + box['width'] - 1
    await page.mouse.move(pointer_x, box['y'] + 3)
    await expect(hit).to_have_attribute('aria-valuenow', '900')
    await expect(tooltip).to_contain_text('0 W')
    await expect(tooltip).to_contain_text('125 %')
    guide_x = await guide.evaluate('node => node.getBoundingClientRect().x')
    tip = await tooltip.bounding_box()
    assert tip['x'] + tip['width'] <= min(pointer_x, guide_x) - 11


async def test_missing_settlement_gap_is_unavailable_but_valid_edges_remain_inspectable(chart_page):
    from playwright.async_api import expect

    page, state = chart_page
    state['starts'] = [0, 60, 300, 600, 660]
    await page.locator('#history-range [data-value="24h"]').click()
    await page.locator('#history-chart').scroll_into_view_if_needed()
    chart = page.locator('#history-chart')
    await expect(chart.locator('path.series').first).to_have_attribute('d', re.compile(r'^M[^M]+M[^M]+M[^M]+$'))
    hit = chart.locator('.chart-hit-area')
    box = await hit.bounding_box()
    tooltip = chart.locator('.chart-tooltip')
    gap = (box['x'] + 240 / 900 * box['width'], box['y'] + 3)
    await page.mouse.move(*gap)
    await expect(tooltip).not_to_contain_text('Unavailable')
    await expect(tooltip).to_contain_text('— W')
    await page.mouse.click(*gap)
    await expect(hit).to_have_css('outline-style', 'none')
    await expect(tooltip).to_contain_text('— W')
    assert await chart.locator('.active-series-marker[visibility=visible]').count() == 0
    # Mouse coordinates round to subpixels; exact interval boundaries are unit-tested.
    for at, value in [(179.9, '80 W'), (300.1, '100 W'), (359.9, '100 W'), (600.1, '20 W')]:
        await page.mouse.move(box['x'] + at / 900 * box['width'], box['y'] + 3)
        await expect(tooltip).to_contain_text(value)
        await expect(tooltip).to_contain_text('125 %')
        assert await chart.locator('.active-series-marker[visibility=visible]').count() == 2
        await expect(tooltip).not_to_contain_text('Data complete')


async def test_inspection_reads_original_thinned_record(chart_page):
    from playwright.async_api import expect

    page, state = chart_page
    state['ends'] = list(range(1, 1202))
    state['values'] = [index if index != 502 else 0 for index in range(1201)]
    await page.locator('#history-range [data-value="24h"]').click()
    await page.locator('#history-chart').scroll_into_view_if_needed()
    chart = page.locator('#history-chart')
    await expect(chart.locator('.chart-hit-area')).to_be_visible()
    # The zero at index 502 is omitted from the displayed sample. Geometry there
    # follows its neighboring retained values, while inspection must still return zero.
    await page.wait_for_function("() => document.querySelector('#history-chart .chart-hit-area').getAttribute('aria-valuemax') === '1201'")
    displayed_power = await chart.evaluate('''host => {
        const path = host.querySelector('path.series'), target = 48 + 503 / 1201 * (host.clientWidth - 60);
        const samples = Array.from({length: 10001}, (_, index) => path.getPointAtLength(path.getTotalLength() * index / 10000));
        const point = samples.reduce((nearest, point) => Math.abs(point.x - target) < Math.abs(nearest.x - target) ? point : nearest);
        return 1320 - (point.y - 16) / (host.clientHeight - 50) * 1320;
    }''')
    assert displayed_power > 400
    box = await chart.locator('.chart-hit-area').bounding_box()
    await page.mouse.move(box['x'] + 503 / 1201 * box['width'], box['y'] + 3)
    await expect(chart.locator('.chart-tooltip')).to_contain_text('0 W')


async def test_keyboard_and_touch_inspection(chart_page):
    from playwright.async_api import expect

    page, _ = chart_page
    chart = page.locator('#history-chart')
    hit = chart.locator('.chart-hit-area')
    await expect(hit).to_be_visible()
    await page.locator('#pr-chart .chart-hit-area').focus()
    await page.keyboard.press('Tab')
    await expect(chart.locator('.chart-hit-area:focus-visible')).to_be_focused()
    await expect(hit).to_have_css('outline-style', 'solid')
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
    header = await touch.locator('.app-header').bounding_box()
    await touch.touchscreen.tap(10, header['height'] + 5)
    await expect(touch_chart.locator('.chart-tooltip')).to_be_hidden()
    assert await touch_chart.locator('.chart-hit-area').evaluate("node => getComputedStyle(node).touchAction") == 'pan-y'
    session = await context.new_cdp_session(touch)
    before = await touch.locator('#content-scroll').evaluate('node => node.scrollTop')
    # The comparison chart is last, so pan back toward the content above it.
    assert before > 0
    await session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': box['x'] + 20, 'y': box['y'] + 20}]})
    for distance in [20, 40, 70, 100]:
        await session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': box['x'] + 20, 'y': box['y'] + 20 + distance}]})
    await session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    await touch.wait_for_function("before => document.querySelector('#content-scroll').scrollTop < before", arg=before)
    assert await touch.evaluate('scrollY') == 0
    assert (await touch.locator('.app-header').bounding_box())['y'] == 0
    await context.close()


@pytest.mark.parametrize('language', ['fr', 'de'])
async def test_tooltip_stays_inside_narrow_chart(chart_page, language):
    from playwright.async_api import expect

    page, state = chart_page
    await page.locator('#language-select').select_option(language)
    await page.locator('#theme-select').select_option('dark')
    # Inspect the same first record near the center and near the left edge.
    state.update(ends=[60, 920], values=[123456.7, 20])
    await page.locator('#history-range [data-value="24h"]').click()
    chart = page.locator('#history-chart')
    hit = chart.locator('.chart-hit-area')
    tooltip = chart.locator('.chart-tooltip')
    await expect(hit).to_have_attribute('aria-valuemax', '920')
    await chart.scroll_into_view_if_needed()
    box = await hit.bounding_box()
    await page.mouse.move(box['x'] + 1, box['y'] + 10)
    await expect(hit).to_have_attribute('aria-valuenow', '60')
    natural_width = (await tooltip.bounding_box())['width']
    natural_content = await tooltip.inner_text()

    await page.set_viewport_size({'width': 320, 'height': 844})
    await chart.scroll_into_view_if_needed()
    box = await hit.bounding_box()
    widths = []
    contents = []
    for index, pointer_x in enumerate([box['x'] + 1, box['x'] + box['width'] * 0.5, box['x'] + 1]):
        await page.mouse.move(pointer_x, box['y'] + 10)
        await expect(hit).to_have_attribute('aria-valuenow', '60')
        await expect(tooltip).to_contain_text('125 %')
        bounds = await chart.evaluate('''host => {
            const chart = host.getBoundingClientRect(), tooltip = host.querySelector('.chart-tooltip');
            const tip = tooltip.getBoundingClientRect();
            const guide = host.querySelector('.chart-guide[visibility=visible]').getBoundingClientRect();
            return {left: chart.left, right: chart.right, top: chart.top, bottom: chart.bottom,
                tipLeft: tip.left, tipRight: tip.right, tipTop: tip.top, tipBottom: tip.bottom,
                tipWidth: tip.width, guideX: guide.x,
                scrollWidth: tooltip.scrollWidth, clientWidth: tooltip.clientWidth,
                scrollHeight: tooltip.scrollHeight, clientHeight: tooltip.clientHeight};
        }''')
        assert bounds['tipLeft'] >= bounds['left'] and bounds['tipRight'] <= bounds['right'] + 1
        assert bounds['tipTop'] >= bounds['top'] and bounds['tipBottom'] <= bounds['bottom'] + 1
        assert bounds['tipLeft'] >= max(pointer_x, bounds['guideX']) + 11
        assert bounds['scrollWidth'] <= bounds['clientWidth']
        if index != 1:
            assert bounds['scrollHeight'] <= bounds['clientHeight']
        widths.append(bounds['tipWidth'])
        contents.append(await tooltip.inner_text())
    assert contents[0] == contents[1] == contents[2] == natural_content
    assert widths[1] < widths[0] <= natural_width
    assert widths[2] == widths[0]
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    Path('artifacts').mkdir(exist_ok=True)
    await page.screenshot(path=f'artifacts/chart-inspection-{language}-320-dark.png')


async def scroll_and_measure_tooltip(chart, distance):
    return await chart.evaluate('''async (host, distance) => {
        const scroll = document.querySelector('#content-scroll');
        scroll.scrollBy(0, distance);
        await new Promise(resolve => requestAnimationFrame(resolve));
        const chart = host.getBoundingClientRect(), content = scroll.getBoundingClientRect();
        const tip = host.querySelector('.chart-tooltip').getBoundingClientRect();
        const contentTop = content.top + scroll.clientTop;
        return {visibleTop: Math.max(chart.top, contentTop, 0),
            visibleBottom: Math.min(chart.bottom, contentTop + scroll.clientHeight, innerHeight),
            tipTop: tip.top, tipBottom: tip.bottom};
    }''', distance)


async def test_partially_visible_tooltip_keeps_all_rows_reachable(chart_page):
    from playwright.async_api import expect

    page, _ = chart_page
    await page.set_viewport_size({'width': 320, 'height': 600})
    await page.locator('#language-select').select_option('fr')
    chart = page.locator('#history-chart')
    await chart.scroll_into_view_if_needed()
    await chart.evaluate('''host => {
        const scroll = document.querySelector('#content-scroll');
        scroll.scrollTo(0, host.getBoundingClientRect().top + scroll.scrollTop - innerHeight + 90);
    }''')
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
    await page.mouse.move(0, 0)
    await expect(tooltip).to_be_hidden()
    await hit.evaluate('node => node.focus({preventScroll: true})')
    await page.keyboard.press('ArrowLeft')
    await page.keyboard.press('Tab')
    await expect(tooltip).to_be_focused()
    await page.keyboard.press('Home')
    await expect(tooltip).to_be_visible()
    await page.keyboard.press('End')
    await page.wait_for_function("() => { const tip = document.querySelector('#history-chart .chart-tooltip'); return tip.scrollTop + tip.clientHeight >= tip.scrollHeight - 1; }")
    bounds = await scroll_and_measure_tooltip(chart, -30)
    await expect(tooltip).to_be_visible()
    assert bounds['tipTop'] >= bounds['visibleTop'] - 1 and bounds['tipBottom'] <= bounds['visibleBottom'] + 1, bounds
    await page.keyboard.press('Escape')
    await expect(tooltip).to_be_hidden()
    await expect(hit).to_be_focused()


async def test_tooltip_on_top_clipped_chart_stays_below_header(chart_page):
    from playwright.async_api import expect

    page, _ = chart_page
    await page.set_viewport_size({'width': 390, 'height': 600})
    # PR is the first chart area, with enough content below it to test top clipping.
    chart = page.locator('#pr-chart')
    await expect(page.locator('#content-scroll')).to_have_count(1)
    await chart.evaluate('''host => {
        const scroll = document.querySelector('#content-scroll');
        scroll.scrollTo(0, scroll.scrollTop + host.getBoundingClientRect().top - scroll.getBoundingClientRect().top + 70);
    }''')
    await page.wait_for_function("() => document.querySelector('#pr-chart').getBoundingClientRect().top < document.querySelector('.app-header').getBoundingClientRect().bottom")
    hit = await chart.locator('.chart-hit-area').bounding_box()
    header = await page.locator('.app-header').bounding_box()
    await page.mouse.move(hit['x'] + hit['width'] / 2, header['height'] + 10)
    tooltip = chart.locator('.chart-tooltip')
    await expect(tooltip).to_be_visible()
    box = await tooltip.bounding_box()
    assert box['y'] >= header['height'], {'tooltip': box, 'header': header}
    assert box['y'] + box['height'] <= 600
    await page.mouse.move(0, 0)
    await expect(tooltip).to_be_hidden()
    await chart.locator('.chart-hit-area').evaluate('node => node.focus({preventScroll: true})')
    await page.keyboard.press('ArrowRight')
    bounds = await scroll_and_measure_tooltip(chart, 35)
    await expect(tooltip).to_be_visible()
    assert bounds['tipTop'] >= bounds['visibleTop'] - 1 and bounds['tipBottom'] <= bounds['visibleBottom'] + 1, bounds
    evidence = Path(os.getenv('PVYL_LAYOUT_ARTIFACTS', 'artifacts/task-6-layout'))
    evidence.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(evidence / 'tooltip-top-clipped-390.png'))
