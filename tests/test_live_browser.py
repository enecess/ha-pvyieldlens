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
async def live_page(browser_workspace, monkeypatch):
    from playwright.async_api import expect
    from test_engine import samples, settings
    from types import SimpleNamespace
    import pvyieldlens.web as web_module

    page, service, _ = browser_workspace
    now = 1794805200
    await service.configure(settings(settlement_interval_minutes=1, update_interval_seconds=60), now=now-900)
    service.store.add_observations(samples(at=now-660) + samples(power=None, at=now-300) + samples(at=now-180), origin=service.origin)
    await service.tick(now)
    service.connected = True
    service._recovery_needed = False
    state = {'now': now, 'seeds': 0, 'snapshots': 0, 'fail_seed': False,
             'diagnostics': 0, 'reported_at': now - 10}
    monkeypatch.setattr(web_module, 'time', SimpleNamespace(time=lambda: state['now']))

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

    async def diagnostics(route):
        state['diagnostics'] += 1
        await route.fulfill(json={'observed_at': state['now'], 'sources': [
            {'entity_id': 'sensor.power', 'state': '3.348', 'unit': 'kW',
             'reported_at': state['reported_at'], 'valid': True},
            {'entity_id': 'sensor.temp', 'state': '40', 'unit': '°C',
             'reported_at': state['reported_at'], 'valid': True},
            {'entity_id': 'sensor.sun', 'state': 'unavailable', 'unit': None,
             'reported_at': None, 'valid': False},
        ]})

    await page.route('**/api/live-series', seed)
    await page.route('**/api/snapshot', snapshot)
    await page.route('**/api/source-diagnostics', diagnostics)
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
    await expect(page.locator('#live-chart .chart-tooltip')).to_contain_text('— W')
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
        await expect(chart.locator('.chart-tooltip')).to_contain_text('— W')
        await expect(chart.locator('.chart-tooltip')).to_contain_text('— W')
        assert await chart.locator('.active-series-marker[visibility=visible]').count() == 0


async def test_dashboard_does_not_request_source_diagnostics(live_page):
    from playwright.async_api import expect

    page, _, state = live_page
    await expect(page.locator('#source-diagnostics')).to_have_count(0)
    await page.clock.fast_forward(3000)
    assert state['diagnostics'] == 0
    await expect(page.locator('#generation-power-chart')).to_have_count(1)
    await expect(page.locator('#generation-irradiance-chart')).to_have_count(1)
    await expect(page.locator('#generation-temperature-chart')).to_have_count(1)
    await page.locator('#settings-button').click()
    await page.locator('[data-settings-category=modules]').click()
    await page.locator('[name=total_max_power_at_stc_w]').fill('6100')
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        await page.clock.fast_forward(60000)
    assert state['diagnostics'] == 0
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
    await expect(chart.locator('.chart-tooltip')).to_contain_text('— W')
    await expect(chart.locator('.chart-tooltip')).to_contain_text('— W')
    async with page.expect_response(lambda response: response.url.endswith('/api/snapshot')):
        await page.clock.fast_forward(60000)
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile(r'^M[^M]+M[^M]+$'))
    async with page.expect_response(lambda response: response.url.endswith('/api/live-series')):
        release_seed.set()
    await expect(page.locator('#live-chart path.series').first).to_have_attribute('d', re.compile(r'^M[^M]+$'))

@pytest.mark.parametrize('width,theme', [(1440, 'light'), (1440, 'dark'), (390, 'light'), (390, 'dark')])
async def test_dashboard_generation_ranges_legends_and_visuals(live_page, width, theme):
    from playwright.async_api import expect

    page, _, state = live_page
    await page.set_viewport_size({'width': width, 'height': 1000 if width == 1440 else 844})
    await page.locator('#language-select').select_option('zh')
    await page.locator('#theme-select').select_option(theme)
    await expect(page.locator('#live-heading')).to_have_text('看板')
    for identifier in ['generation-power-chart', 'generation-irradiance-chart', 'generation-temperature-chart']:
        await expect(page.locator('#' + identifier + ' svg')).to_be_attached()
    await expect(page.locator('#generation-data')).not_to_contain_text('已结算功率')
    await expect(page.locator('#generation-data')).not_to_contain_text('今天')
    await expect(page.locator('#dashboard-energy-range [data-value="7d"]')).to_have_attribute('aria-pressed', 'true')
    assert state['diagnostics'] == 0
    artifacts = Path('artifacts/task-5-dashboard')
    artifacts.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(artifacts / f'dashboard-{width}-{theme}-top.png'))
    await page.locator('#generation-data').scroll_into_view_if_needed()
    await page.screenshot(path=str(artifacts / f'dashboard-{width}-{theme}-generation.png'))
    legends = await page.locator('#live-page .legend').evaluate_all('''nodes => nodes.map(node => ({
        alignment: getComputedStyle(node).justifyContent,
        labels: [...node.querySelectorAll('span')].map(span => span.textContent)
    }))''')
    assert all(legend['alignment'] == 'flex-end' and all(legend['labels']) for legend in legends)
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    await page.locator('#dashboard-energy-range [data-value=custom]').click()
    today = await page.locator('#dashboard-energy-range-end').get_attribute('max')
    await page.locator('#dashboard-energy-range-start').fill(today)
    await page.locator('#dashboard-energy-range-end').fill(today)
    await page.screenshot(path=str(artifacts / f'dashboard-{width}-{theme}-custom.png'))
    panel = await page.locator('#dashboard-energy-range-panel').bounding_box()
    assert panel['x'] >= 0 and panel['x'] + panel['width'] <= width
    async with page.expect_response(lambda response: '/api/history?period=custom&' in response.url) as pending:
        await page.locator('#dashboard-energy-range-apply').click()
    payload = await (await pending.value).json()
    assert len(payload['days']) == 1
    assert payload['days'][0]['day'] == today
    await expect(page.locator('#dashboard-energy-range [data-value=custom]')).to_contain_text(today)
    await page.locator('#history-tab').click()
    await page.locator('#history-range [data-value="7d"]').click()
    await expect(page.locator('#history-page .history-grid > article')).to_have_count(2)
    await expect(page.locator('#daily-pr-chart svg')).to_be_visible()
    assert await page.locator('#daily-pr-chart .reference-line').evaluate("""line =>
        Number(line.getAttribute('x2')) > Number(line.getAttribute('x1')) &&
        Number(line.getAttribute('y1')) > 0 && getComputedStyle(line).strokeDasharray !== 'none'""")
    summary_gap = await page.locator('#history-page .energy-summary').evaluate("""node => {
        const label = document.createRange(); label.selectNodeContents(node.firstChild);
        return node.querySelector('strong').getBoundingClientRect().left - label.getBoundingClientRect().right;
    }""")
    assert summary_gap <= 8
    await page.screenshot(path=str(artifacts / f'efficiency-{width}-{theme}-daily.png'))
    await page.locator('#history-aggregation [data-value=settlement]').click()
    await expect(page.locator('#pr-chart svg')).to_be_visible()
    assert await page.locator('#pr-chart .reference-line').evaluate("""line =>
        Number(line.getAttribute('x2')) > Number(line.getAttribute('x1')) &&
        Number(line.getAttribute('y1')) > 0 && getComputedStyle(line).strokeDasharray !== 'none'""")
    await expect(page.locator('#history-chart svg')).to_contain_text('W')
    await page.screenshot(path=str(artifacts / f'efficiency-{width}-{theme}-settlement.png'))
