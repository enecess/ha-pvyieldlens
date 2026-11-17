import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_browser import browser_workspace

pytestmark = [pytest.mark.skipif(os.getenv('PVYL_BROWSER_TESTS') != '1', reason='Set PVYL_BROWSER_TESTS=1'),
              pytest.mark.parametrize('browser_workspace', [False], indirect=True)]


@pytest.fixture
async def live_page(browser_workspace):
    from playwright.async_api import expect
    from test_engine import samples, settings

    page, service, _ = browser_workspace
    now = 1794805200
    await service.configure(settings(settlement_interval_minutes=1, update_interval_seconds=60), now=now-900)
    service.store.add_observations(samples(at=now-660) + samples(power=None, at=now-300) + samples(at=now-180), origin=service.origin)
    await service.tick(now)
    service.connected = True
    service._recovery_needed = False
    state = {'now': now, 'seeds': 0, 'snapshots': 0, 'fail_seed': False}

    async def seed(route):
        state['seeds'] += 1
        if state['fail_seed']:
            await route.fulfill(status=503, json={'error': 'error'})
        else:
            await route.fulfill(json=service.live_series(now=state['now']))

    async def snapshot(route):
        state['snapshots'] += 1
        payload = service.snapshot(now=state['now'])
        payload['sources'] = [{'entity_id': 'sensor.power', 'state': '3348', 'unit': 'W',
                               'reported_at': now, 'valid': True}]
        await route.fulfill(json=payload)

    await page.route('**/api/live-series', seed)
    await page.route('**/api/snapshot', snapshot)
    await page.clock.install(time=datetime.fromtimestamp(now, timezone.utc))
    await page.reload()
    await expect(page.locator('#live-actual')).to_have_text('3,348')
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile('C'))
    Path('artifacts/task-4-live').mkdir(parents=True, exist_ok=True)
    return page, service, state


async def test_reload_restores_ten_minutes_and_rolls_left_boundary(live_page):
    from playwright.async_api import expect

    page, service, state = live_page
    hit = page.locator('#live-chart .chart-hit-area')
    await hit.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('#live-chart .chart-tooltip')).to_contain_text('3,348 W')
    first = await page.locator('#live-chart .chart-tooltip strong').text_content()
    await page.reload()
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile('C'))
    await page.locator('#live-chart .chart-hit-area').focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('#live-chart .chart-tooltip')).to_contain_text(first)
    await page.screenshot(path='artifacts/task-4-live/reload-ten-minutes.png')
    state['now'] += 60
    await service.tick(state['now'])
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        await page.clock.fast_forward(60000)
    await page.locator('#live-chart .chart-hit-area').focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.locator('#live-chart .chart-tooltip')).not_to_contain_text(first)
    assert state['seeds'] == 2


async def test_unavailable_interval_remains_a_break_and_inspects_raw_values(live_page):
    from playwright.async_api import expect

    page, _, _ = live_page
    path = await page.locator('#live-chart path.series').first.get_attribute('d')
    assert path.count('M') == 2
    await page.locator('#live-chart .chart-hit-area').focus()
    await page.keyboard.press('ArrowRight')
    for _ in range(6):
        await page.keyboard.press('ArrowRight')
    await expect(page.locator('#live-chart .chart-tooltip')).to_contain_text('Unavailable')
    await expect(page.locator('#live-chart .chart-tooltip')).to_contain_text('— W')
    await page.screenshot(path='artifacts/task-4-live/tooltip-gap.png')


async def test_uncovered_live_range_inspects_unavailable_instead_of_distant_samples(live_page):
    from playwright.async_api import expect

    page, service, state = live_page
    payload = service.live_series(now=state['now'])
    payload['points'] = [point for point in payload['points'] if state['now'] - 420 <= point['at'] <= state['now'] - 360]
    snapshot = service.snapshot(now=state['now'])
    snapshot['calculated_at'] = state['now'] - 300
    await page.route('**/api/live-series', lambda route: route.fulfill(json=payload))
    await page.route('**/api/snapshot', lambda route: route.fulfill(json=snapshot))
    await page.reload()
    chart = page.locator('#live-chart')
    await expect(chart.locator('.chart-hit-area')).to_be_visible()
    box = await chart.locator('.chart-hit-area').bounding_box()
    for fraction in [0.1, 0.9]:
        await page.mouse.move(box['x'] + fraction * box['width'], box['y'] + 3)
        await expect(chart.locator('.chart-tooltip')).to_contain_text('Unavailable')
        await expect(chart.locator('.chart-tooltip')).to_contain_text('— W')
        assert await chart.locator('.active-series-marker[visibility=visible]').count() == 0


async def test_source_ages_tick_without_replacing_svg_and_settings_keeps_polling(live_page):
    from playwright.async_api import expect

    page, _, state = live_page
    await page.locator('#source-diagnostics').evaluate('node => node.open = true')
    await page.locator('#live-chart svg').evaluate("node => node.dataset.original = 'age-clock'")
    age = page.locator('#source-rows td').nth(2)
    await expect(age).to_have_text('Just now')
    requests = state['snapshots']
    await page.clock.fast_forward(2000)
    await expect(age).to_have_text('2 s')
    await expect(page.locator('#live-chart svg')).to_have_attribute('data-original', 'age-clock')
    assert state['snapshots'] == requests
    await page.screenshot(path='artifacts/task-4-live/source-age.png', full_page=True)
    await page.locator('#settings-button').click()
    await page.locator('[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        await page.clock.fast_forward(60000)
    assert state['snapshots'] > requests
    await expect(page.locator('[name=total_max_power_at_stc_w]')).to_have_value('6100')


async def test_seed_failure_is_chart_local_and_keeps_live_metrics(live_page):
    from playwright.async_api import expect

    page, _, state = live_page
    state['fail_seed'] = True
    await page.reload()
    await expect(page.locator('#live-actual')).to_have_text('3,348')
    await expect(page.locator('#live-series-error')).to_have_text('Recent data could not be loaded. Showing new live readings.')


async def test_resume_gap_survives_duplicate_snapshots_until_seed_fills_it(live_page):
    from playwright.async_api import expect

    page, service, state = live_page
    release_seed = asyncio.Event()

    async def seed(route):
        await release_seed.wait()
        await route.fulfill(json=service.live_series(now=state['now']))

    await page.route('**/api/live-series', seed)
    state['now'] += 240
    await service.tick(state['now'])
    await page.clock.set_system_time(datetime.fromtimestamp(state['now'], timezone.utc))
    await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        await page.clock.fast_forward(60000)
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile(r'^M[^M]+M[^M]+$'))
    chart = page.locator('#live-chart')
    box = await chart.locator('.chart-hit-area').bounding_box()
    await page.mouse.move(box['x'] + 0.7 * box['width'], box['y'] + 3)
    await expect(chart.locator('.chart-tooltip')).to_contain_text('Unavailable')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('— W')
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        await page.clock.fast_forward(60000)
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile(r'^M[^M]+M[^M]+$'))
    async with page.expect_response(lambda response: response.url.endswith('/api/live-series')):
        release_seed.set()
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile(r'^M[^M]+$'))
