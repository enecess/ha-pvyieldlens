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
        payload = history_payload([window], summary, {'start': end-180, 'end': end}, selected,
                                  evaluated_at=datetime.now(timezone.utc).timestamp())
        if payload['days']:
            payload['days'][1]['summary'] = {**summary, 'estimated_energy_kwh': 0, 'actual_energy_kwh': 0, 'pr': None}
            payload['days'][2]['boundary_unavailable'] = True
            payload['days'][-1]['summary'] = summary
        await route.fulfill(json=payload)

    await page.route('**/api/history?*', history)
    await page.locator('#history-tab').click()
    await expect(page.locator('#history-range [data-value="today"]')).to_have_attribute('aria-pressed', 'true')
    await expect(page.locator('#history-actual-energy')).to_have_text('0.07')
    await expect(page.locator('#history-pr')).to_have_text('87.5')
    await expect(page.locator('#history-totals')).to_have_count(0)
    await page.locator(f'#history-range [data-value="{period}"]').click()
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
    await expect(chart.locator('.chart-tooltip')).not_to_contain_text('Data completeness')
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
    bars = chart.locator('.daily-column').last.locator('.daily-bar')
    last_bar = await bars.last.bounding_box()
    pointer_x = last_bar['x'] + last_bar['width'] / 2
    await page.keyboard.press('Home')
    await expect(hit).to_have_attribute('aria-valuenow', '0')
    await page.mouse.move(pointer_x, last_bar['y'] + 5)
    await expect(hit).to_have_attribute('aria-valuenow', str(count - 1))
    bounds = await tip.bounding_box()
    assert bounds['x'] + bounds['width'] <= min(pointer_x, (await bars.first.bounding_box())['x']) - 11
    # All dates retain independent hit columns despite sparse axis labels.
    box = await hit.bounding_box()
    await page.mouse.move(box['x'] + 2.5/count*box['width'], box['y']+5)
    await expect(hit).to_have_attribute('aria-valuenow', '2')
    await expect(tip).not_to_contain_text('cannot be allocated exactly')
    artifacts = Path(os.getenv('PVYL_HISTORY_ARTIFACTS', 'artifacts/task-3-history'))
    artifacts.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(artifacts / f'daily-{width}-{period}-{language}-{theme}.png'))
    await page.locator('#content-scroll').evaluate('node => node.scrollTo(0,0)')
    await page.screenshot(path=str(artifacts / f'cards-{width}-{period}-{language}-{theme}.png'))
    pr_chart = page.locator('#daily-pr-chart')
    await pr_chart.scroll_into_view_if_needed()
    pr_hit = pr_chart.locator('.chart-hit-area')
    box = await pr_hit.bounding_box()
    await page.mouse.move(box['x'] + (1 - 0.9 / count) * box['width'], box['y'] + 5)
    await expect(pr_hit).to_have_attribute('aria-valuenow', str(count - 1))
    await pr_hit.focus()
    await page.keyboard.press('End')
    pr_tip = pr_chart.locator('.chart-tooltip')
    await expect(pr_tip).to_be_visible()
    guide_x = (await pr_chart.locator('.chart-guide').bounding_box())['x']
    bounds = await pr_tip.bounding_box()
    # End reanchors at the guide even when the pointer had already selected the final date.
    assert guide_x - 13 <= bounds['x'] + bounds['width'] <= guide_x - 11
    await page.screenshot(path=str(artifacts / f'single-pr-{width}-{period}-{language}-{theme}.png'))


async def test_dashboard_single_day_energy_tooltip_clears_focus(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    context = await page.context.browser.new_context(has_touch=True, is_mobile=True,
        viewport={'width': 320, 'height': 900}, http_credentials={'username': 'admin', 'password': 'browser-test'})
    async with context:
        touch = await context.new_page()

        async def history(route):
            response = await route.fetch()
            payload = await response.json()
            payload['days'][-1]['summary'].update(estimated_energy_kwh=12.345, actual_energy_kwh=10.543, pr=85.4)
            await route.fulfill(response=response, json=payload)

        await touch.route('**/api/history?*', history)
        await touch.goto(page.url)
        chart = touch.locator('#dashboard-energy-chart')
        tip = chart.locator('.chart-tooltip')
        days = chart.locator('.daily-column')
        await expect(days).to_have_count(7)
        await chart.scroll_into_view_if_needed()
        bars = days.last.locator('.daily-bar')
        last_bar = await bars.last.bounding_box()
        pointer_x = last_bar['x'] + last_bar['width'] / 2
        await touch.mouse.move(pointer_x, last_bar['y'] + 5)
        await expect(tip).to_contain_text('10.543 kWh')
        seven_day_tip = await tip.bounding_box()
        seven_day_left = min(pointer_x, (await bars.first.bounding_box())['x'])

        await touch.locator('#dashboard-energy-range [data-value=custom]').click()
        await touch.locator('#dashboard-energy-range-apply').click()
        await expect(days).to_have_count(1)
        await chart.scroll_into_view_if_needed()
        hit = await chart.locator('.chart-hit-area').bounding_box()
        pointer_x = round(hit['x'] + hit['width'] / 2 + 10)
        await touch.touchscreen.tap(pointer_x, hit['y'] + 20)
        await expect(tip).to_contain_text('12.345 kWh')
        await expect(tip).to_contain_text('10.543 kWh')
        bounds = await tip.bounding_box()
        chart_bounds = await chart.bounding_box()
        guide_x = (await chart.locator('.chart-guide').bounding_box())['x']
        assert chart_bounds['x'] <= bounds['x']
        assert bounds['x'] + bounds['width'] <= chart_bounds['x'] + chart_bounds['width']
        assert chart_bounds['y'] <= bounds['y']
        assert bounds['y'] + bounds['height'] <= chart_bounds['y'] + chart_bounds['height']
        assert (bounds['x'] + bounds['width'] <= min(pointer_x, guide_x) - 11
                or bounds['x'] >= max(pointer_x, guide_x) + 11)
        assert bounds['width'] < seven_day_tip['width']
        assert await tip.evaluate('node => node.scrollWidth <= node.clientWidth')
        assert seven_day_tip['x'] + seven_day_tip['width'] <= seven_day_left - 11

        # Shrink only the viewport, leaving the chart and touch selection in place.
        reduced_height = int(chart_bounds['y']) + 65
        assert reduced_height < 900
        await touch.set_viewport_size({'width': 320, 'height': reduced_height})
        await touch.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
        assert await chart.bounding_box() == chart_bounds
        bounds = await tip.bounding_box()
        assert bounds['y'] >= chart_bounds['y'] - 1 and bounds['y'] + bounds['height'] <= reduced_height + 1
        assert await tip.evaluate("node => getComputedStyle(node).pointerEvents === 'auto'")
        assert await tip.evaluate('node => node.scrollHeight > node.clientHeight')
        values = tip.locator('div > span:last-child')
        for value in ['12.345 kWh', '10.543 kWh']:
            reading = values.get_by_text(value, exact=True)
            assert await reading.evaluate('''node => {
                const tip = node.closest('.chart-tooltip');
                const view = tip.getBoundingClientRect();
                tip.scrollTop += node.getBoundingClientRect().bottom - view.top - tip.clientHeight;
                const box = node.getBoundingClientRect();
                return box.top >= view.top && box.bottom <= view.bottom;
            }'''), value
        assert await tip.evaluate('node => node.scrollTop > 0')


async def test_dashboard_short_viewport_wheel_keeps_selected_date(browser_workspace):
    from playwright.async_api import expect

    page, _, _ = browser_workspace
    await page.set_viewport_size({'width': 320, 'height': 600})
    await page.locator('#language-select').select_option('fr')
    chart = page.locator('#dashboard-energy-chart')
    await expect(chart.locator('.daily-column')).to_have_count(7)
    await chart.scroll_into_view_if_needed()
    await chart.evaluate('''host => {
        const scroll = host.closest('#content-scroll');
        scroll.scrollTop += host.getBoundingClientRect().top - innerHeight + 90;
    }''')
    await page.wait_for_function("""() => Math.abs(
        document.querySelector('#dashboard-energy-chart').getBoundingClientRect().top - innerHeight + 90
    ) < 1""")
    hit = chart.locator('.chart-hit-area')
    box = await hit.bounding_box()
    await page.mouse.move(box['x'] + box['width'] - 4, box['y'] + 15)
    await expect(hit).to_have_attribute('aria-valuenow', '6')
    tip = chart.locator('.chart-tooltip')
    await expect(tip).to_be_visible()
    assert await tip.evaluate('node => node.scrollHeight > node.clientHeight')

    scroll = page.locator('#content-scroll')
    scroll_top = await scroll.evaluate('node => node.scrollTop')
    await page.mouse.wheel(0, 200)
    await page.wait_for_function("""() => {
        const tip = document.querySelector('#dashboard-energy-chart .chart-tooltip');
        return tip.scrollTop > 0 && tip.scrollTop + tip.clientHeight >= tip.scrollHeight - 1;
    }""", timeout=2000)
    await expect(hit).to_have_attribute('aria-valuenow', '6')
    assert await scroll.evaluate('node => node.scrollTop') == scroll_top
    await page.mouse.wheel(0, 60)
    await page.wait_for_function("before => document.querySelector('#content-scroll').scrollTop > before", arg=scroll_top)


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
    async with page.expect_response('**/api/history?period=today&compare=true') as pending:
        await page.locator('#history-tab').click()
    before = await (await pending.value).json()
    assert before['today'] == '2026-11-10'
    clock.time = lambda: now+2
    async with page.expect_response('**/api/history?period=today&compare=true') as pending:
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
        {'start': 1793740800, 'end': 1794326580}, '7d', evaluated_at=datetime.now(timezone.utc).timestamp())
    context = await page.context.browser.new_context(has_touch=True, is_mobile=True,
        viewport={'width': 390, 'height': 600}, http_credentials={'username': 'admin', 'password': 'browser-test'})
    touch = await context.new_page()
    await touch.route('**/api/history?*', lambda route: route.fulfill(json=payload))
    await touch.goto(page.url)
    await touch.locator('#history-tab').click()
    await touch.locator('#history-range [data-value="7d"]').click()
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

async def test_dashboard_midnight_uses_household_day_with_fixed_offline_measurement(browser_workspace, monkeypatch):
    import pvyieldlens.web as web_module
    import pvyieldlens.service as service_module

    page, service, _ = browser_workspace
    dashboard_url = page.url
    # Retire the fixture's dashboard requests before watching the fresh navigation.
    await page.goto('about:blank')
    await service.configure(service.monitoring_settings.model_copy(update={'home_timezone': 'Asia/Shanghai'}))
    now = datetime(2026, 11, 10, 15, 59, 59, tzinfo=timezone.utc).timestamp()
    clock = SimpleNamespace(time=lambda: now)
    monkeypatch.setattr(web_module, 'time', clock)
    monkeypatch.setattr(service_module, 'time', clock)
    service._mark_offline()
    calculated = service.snapshot(now=now)['calculated_at']
    daily_history_url = '**/api/history?period=7d&include_windows=false'
    async with page.expect_response('**/api/generation-data') as first_generation, page.expect_response(daily_history_url) as first_history:
        await page.goto(dashboard_url)
    before_generation = await (await first_generation.value).json()
    before_history = await (await first_history.value).json()
    async with page.expect_response('**/api/generation-data') as next_generation, page.expect_response(daily_history_url) as next_history:
        clock.time = lambda: now + 2
    after_generation = await (await next_generation.value).json()
    after_history = await (await next_history.value).json()
    assert service.snapshot(now=now+2)['calculated_at'] == calculated
    assert before_history['today'] == '2026-11-10'
    assert after_history['today'] == '2026-11-11'
    assert before_history['windows'] == after_history['windows'] == []
    assert after_history['days'][-1]['day'] == '2026-11-11'
    assert after_history['days'][-1]['summary']['estimated_energy_kwh'] is None
    assert after_generation['requested_range']['start'] == now + 1
    assert before_generation['requested_range']['start'] < after_generation['requested_range']['start']
