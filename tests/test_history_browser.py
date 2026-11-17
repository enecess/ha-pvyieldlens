import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from history_fixtures import history_payload
from test_browser import browser_workspace

pytestmark = pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1')


@pytest.mark.parametrize('width,period,language,theme', [
    (1440, '7d', 'en', 'light'), (1440, '30d', 'de', 'dark'),
    (390, '7d', 'fr', 'dark'), (320, '30d', 'de', 'light'),
    (390, '30d', 'zh', 'dark'), (390, '7d', 'pl', 'light'), (390, '7d', 'it', 'dark'),
])
async def test_daily_slots_zero_gaps_cutoff_and_viewport(browser_workspace, width, period, language, theme):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.set_viewport_size({'width': width, 'height': 900})
    end = datetime(2026, 11, 11, 0, 3, tzinfo=timezone.utc).timestamp()
    summary = {'start': end-180, 'end': end, 'estimated_energy_kwh': 0.08,
               'actual_energy_kwh': 0.07, 'pr': 87.5, 'data_completeness_percent': 60, 'valid_seconds': 108}
    window = {'revision': 1, 'start': end-180, 'end': end, 'valid_seconds': 108,
              'estimated_energy_wh': 60, 'actual_energy_wh': 60, 'estimated_power_w': 2000,
              'actual_power_w': 2000, 'pr': 100, 'optimizable_power_w': 0, 'data_completeness_percent': 60,
              'quality': 'partial', 'reason': 'missing_data', 'source_start': end-300, 'source_end': end}

    async def history(route):
        selected = parse_qs(urlsplit(route.request.url).query)['period'][0]
        payload = history_payload([window], summary, {'start': end-180, 'end': end}, selected)
        if payload['days']:
            payload['days'][1]['summary'] = {**summary, 'estimated_energy_kwh': 0, 'actual_energy_kwh': 0, 'pr': None}
            payload['days'][2]['boundary_unavailable'] = True
            payload['days'][-1]['summary'] = summary
        await route.fulfill(json=payload)

    await page.route('**/api/history?*', history)
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-range')).to_have_value('today')
    await expect(page.locator('#history-actual-energy')).to_have_text('0.07')
    await expect(page.locator('#history-pr')).to_have_text('87.5')
    await expect(page.locator('#history-totals')).to_have_count(0)
    await page.locator('#history-range').select_option(period)
    count = 7 if period == '7d' else 30
    await expect(page.locator('#daily-energy-chart .daily-column')).to_have_count(count)
    await expect(page.locator('#daily-energy-chart .daily-bar')).to_have_count(4)
    await expect(page.locator('#daily-energy-chart .daily-bar[height="0"]')).to_have_count(2)
    await expect(page.locator('#daily-pr-chart .daily-pr-point')).to_have_count(1)
    chart = page.locator('#daily-energy-chart')
    await chart.scroll_into_view_if_needed()
    hit = chart.locator('.chart-hit-area')
    box = await hit.bounding_box()
    # The entire date column works even at a measured zero bar's baseline.
    await page.mouse.move(box['x'] + 1.5 / count * box['width'], box['y']+10)
    await expect(chart.locator('.chart-tooltip')).to_contain_text('0 kWh')
    await hit.focus()
    await page.keyboard.press('End')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('Through 12:03 AM')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('60 %')
    await page.keyboard.press('Escape')
    await expect(chart.locator('.chart-tooltip')).to_have_count(0)
    await page.locator('#language-select').select_option(language)
    await page.locator('#theme-select').select_option(theme)
    await chart.scroll_into_view_if_needed()
    labels = await chart.locator('.daily-column text').evaluate_all('''nodes => nodes.map(node => {
        const box = node.getBoundingClientRect(); return {left: box.left, right: box.right};
    })''')
    assert all(right['left'] - left['right'] >= 6 for left, right in zip(labels, labels[1:])), labels
    await hit.focus()
    await page.keyboard.press('End')
    tip = chart.locator('.chart-tooltip')
    await expect(tip).to_be_visible()
    bounds = await tip.bounding_box()
    viewport = await page.locator('#content-scroll').bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
    assert bounds['y'] >= viewport['y'] - 1 and bounds['y'] + bounds['height'] <= 901
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # All dates retain independent hit columns despite sparse axis labels.
    box = await hit.bounding_box()
    await page.mouse.move(box['x'] + 2.5/count*box['width'], box['y']+5)
    await expect(hit).to_have_attribute('aria-valuenow', '2')
    await expect(tip.locator('p').last).to_be_visible()
    artifacts = Path(os.getenv('PVYL_HISTORY_ARTIFACTS', 'artifacts/task-3-history'))
    artifacts.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(artifacts / f'daily-{width}-{period}-{language}-{theme}.png'))
    await page.locator('#content-scroll').evaluate('node => node.scrollTo(0,0)')
    await page.screenshot(path=str(artifacts / f'cards-{width}-{period}-{language}-{theme}.png'))
    await page.locator('#daily-pr-chart').scroll_into_view_if_needed()
    await page.locator('#daily-pr-chart .chart-hit-area').focus()
    await page.keyboard.press('End')
    await expect(page.locator('#daily-pr-chart .chart-tooltip')).to_be_visible()
    await page.screenshot(path=str(artifacts / f'single-pr-{width}-{period}-{language}-{theme}.png'))


async def test_ha_midnight_refreshes_without_settlement(browser_workspace, monkeypatch):
    from playwright.async_api import expect
    import pvyieldlens.web as web_module
    import pvyieldlens.service as service_module

    page, service, _ = browser_workspace
    await service.configure(service.monitoring_settings.model_copy(update={'home_timezone': 'Asia/Shanghai'}))
    now = datetime(2026, 11, 10, 15, 59, 59, tzinfo=timezone.utc).timestamp()
    clock = SimpleNamespace(time=lambda: now)
    monkeypatch.setattr(web_module, 'time', clock)
    monkeypatch.setattr(service_module, 'time', clock)
    await page.clock.set_fixed_time(datetime.fromtimestamp(now, timezone.utc))
    await page.reload()
    await expect(page.locator('main')).to_have_attribute('data-snapshot-ready', 'true')
    async with page.expect_response('**/api/history?period=today') as pending:
        await page.locator('#history-tab').click()
    before = await (await pending.value).json()
    assert before['today'] == '2026-11-10'
    clock.time = lambda: now+2
    async with page.expect_response('**/api/history?period=today') as pending:
        pass
    after = await (await pending.value).json()
    assert after['today'] == '2026-11-11'
    assert before['windows'] == after['windows'] == []
    assert after['requested_range']['start'] == now+1
    await expect(page.locator('#history-actual-energy')).to_have_text('—')
    await expect(page.locator('#history-chart .chart-empty')).to_be_visible()


async def test_daily_touch_columns_preserve_vertical_scroll(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    payload = history_payload([], {'start': None, 'end': None, 'estimated_energy_kwh': None,
        'actual_energy_kwh': None, 'pr': None, 'data_completeness_percent': None, 'valid_seconds': 0},
        {'start': 1793740800, 'end': 1794326580}, '7d')
    context = await page.context.browser.new_context(has_touch=True, is_mobile=True,
        viewport={'width': 390, 'height': 600}, http_credentials={'username': 'admin', 'password': 'browser-test'})
    touch = await context.new_page()
    await touch.route('**/api/history?*', lambda route: route.fulfill(json=payload))
    await touch.goto(page.url)
    await touch.locator('#history-tab').click()
    await touch.locator('#history-range').select_option('7d')
    chart = touch.locator('#daily-energy-chart')
    await chart.scroll_into_view_if_needed()
    hit = chart.locator('.chart-hit-area')
    box = await hit.bounding_box()
    await touch.touchscreen.tap(box['x'] + 2.5/7 * box['width'], box['y'] + 20)
    await expect(hit).to_have_attribute('aria-valuenow', '2')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('— kWh')
    assert await hit.evaluate('node => getComputedStyle(node).touchAction') == 'pan-y'
    await hit.dispatch_event('pointercancel', {'pointerType': 'touch'})
    await expect(chart.locator('.chart-tooltip')).to_have_count(0)
    await touch.touchscreen.tap(box['x'] + 2.5/7 * box['width'], box['y'] + 20)
    await expect(chart.locator('.chart-tooltip')).to_be_visible()
    await touch.touchscreen.tap(10, 10)
    await expect(chart.locator('.chart-tooltip')).to_have_count(0)
    session = await context.new_cdp_session(touch)
    before = await touch.locator('#content-scroll').evaluate('node => node.scrollTop')
    await session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': box['x']+20, 'y': box['y']+100}]})
    for offset in [20, 40, 70, 100]:
        await session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': box['x']+20, 'y': box['y']+100-offset}]})
    await session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    await touch.wait_for_function('before => document.querySelector("#content-scroll").scrollTop > before', arg=before)
    await expect(chart.locator('.chart-tooltip')).to_have_count(0)
    await context.close()
