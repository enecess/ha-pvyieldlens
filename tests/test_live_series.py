import json
from pathlib import Path

import httpx
import pytest

from pvyieldlens.engine import Observation
from pvyieldlens.service import Service
from pvyieldlens.storage import Store
from pvyieldlens.web import Runtime, create_app
from test_engine import samples, settings


@pytest.fixture
def service(tmp_path):
    store = Store(tmp_path / 'data.sqlite')
    instance = Service(store)
    yield instance
    store.close()


async def test_live_series_replays_without_settlement(service, monkeypatch):
    await service.configure(settings(), now=0)
    store = service.store
    store.add_observations(samples() + samples(at=600))
    await service.tick(1200)
    calls = []
    observations = store.observations

    def read(*args):
        calls.append(args)
        return observations(*args)

    monkeypatch.setattr(store, 'observations', read)

    class NoHAReads:
        def __getattr__(self, name):
            pytest.fail(f'Live reconstruction accessed HA: {name}')

    service.client = NoHAReads()
    before = (store.cursor, store.get_meta('estimated_energy_lifetime_wh'), store.get_meta('lifetime_valid_seconds'))
    changes = store.db.total_changes
    result = service.live_series(now=1200)
    assert result['range'] == {'start': 600, 'end': 1200}
    assert len(result['points']) == 121
    assert [point['at'] for point in result['points']] == list(range(600, 1201, 5))
    assert result['points'][0]['estimated_power_w'] == pytest.approx(3720)
    assert result['points'][-1]['estimated_power_w'] == pytest.approx(3720)
    assert result['points'][-1]['pr'] == pytest.approx(90)
    assert result['context'] == {'revision': 1, 'monitoring_settings': settings().model_dump()}
    assert result['configured'] is True
    assert result['recovering'] is True
    service._recovery_needed = False
    assert service.live_series(now=1200)['recovering'] is False
    assert calls == [(540, 1200, settings().entities, '')] * 2
    assert before == (store.cursor, store.get_meta('estimated_energy_lifetime_wh'), store.get_meta('lifetime_valid_seconds'))
    assert store.db.total_changes == changes


@pytest.mark.parametrize('step,count,first', [(1, 598, 603), (7, 86, 605)])
async def test_live_series_grid_uses_recent_snapshot_anchor(service, step, count, first):
    await service.configure(settings(update_interval_seconds=step), now=0)
    service.store.add_observations(samples() + samples(at=600))
    await service.tick(1200)
    result = service.live_series(now=1203)
    assert result['range'] == {'start': 603, 'end': 1203}
    # The grid is anchored at 1200, even when the request arrives later.
    assert result['step_seconds'] == step
    assert result['points'][0]['at'] == first
    assert result['points'][-1]['at'] == 1200
    assert len(result['points']) == count
    assert all(right['at'] - left['at'] == step
               for left, right in zip(result['points'], result['points'][1:]))


async def test_live_series_one_second_grid_keeps_all_601_endpoints(service):
    await service.configure(settings(update_interval_seconds=1), now=0)
    service.store.add_observations(samples() + samples(at=600))
    await service.tick(1200)
    assert len(service.live_series(now=1200)['points']) == 601


async def test_live_series_preserves_partial_expired_and_zero_sources(service):
    await service.configure(settings(actual_power_max_age_seconds=30), now=0)
    service.store.add_observations(samples(at=550) + samples(at=590, power=0, sun=0))
    await service.tick(600)
    result = service.live_series(now=600)
    point = next(point for point in result['points'] if point['at'] == 600)
    assert point['valid_seconds'] == 40
    assert point['data_completeness_percent'] == pytest.approx(100 * 40 / 60)
    assert point['quality'] == 'partial'
    later = service.live_series(now=1300)['points'][-1]
    assert later['estimated_power_w'] is None
    assert later['reason'] == 'current_source_unavailable'
    service.store.add_observations(samples(at=610, power=0, sun=0) + samples(at=630, power=0, sun=0))
    await service.tick(650)
    zero = service.live_series(now=650)['points'][-1]
    assert zero['estimated_power_w'] == 0
    assert zero['actual_power_w'] == 0
    assert zero['pr'] is None
    assert zero['reason'] == 'zero_estimated_power'


@pytest.mark.parametrize('changes', [{'total_max_power_at_stc_w': 10000}, {'actual_power_entity': 'sensor.new_power'}])
async def test_live_series_starts_at_physical_or_source_configuration_boundary(service, changes):
    await service.configure(settings(), now=0)
    service.store.add_observations(samples() + samples(at=600))
    await service.configure(settings(**changes), now=1002)
    service.store.add_observations([Observation('sensor.new_power', 1002, 3348)])
    await service.tick(1200)
    result = service.live_series(now=1200)
    assert result['range'] == {'start': 600, 'end': 1200}
    assert result['points'][0]['at'] == 1005
    assert result['context']['revision'] == 2
    assert result['points'][-1]['estimated_power_w'] == pytest.approx(7440 if 'total_max_power_at_stc_w' in changes else 3720)


async def test_live_series_live_only_settings_replay_without_revision_split(service):
    await service.configure(settings(), now=0)
    service.store.add_observations(samples() + samples(at=600) + samples(at=1170, sun=400))
    await service.tick(1200)
    await service.configure(settings(update_interval_seconds=7, live_window_seconds=120), now=1200)
    result = service.live_series(now=1200)
    assert result['context']['revision'] == 1
    assert result['step_seconds'] == 7
    assert result['points'][0]['at'] == 605
    prior = result['points'][-2]
    assert prior['start'] == 1073
    assert prior['estimated_power_w'] == pytest.approx(3363.5)


async def test_live_series_isolates_origin_and_reuses_predecessors(service):
    await service.configure(settings(), now=0, origin='old-ha')
    service.store.add_observations(samples() + samples(at=600), origin='old-ha')
    await service.configure(settings(), now=900, origin='new-ha')
    service.store.add_observations(samples(at=850, sun=400), origin='new-ha')
    await service.tick(1200)
    result = service.live_series(now=1200)
    assert result['points'][0]['at'] == 900
    assert result['points'][-1]['estimated_power_w'] == pytest.approx(1860)
    assert result['points'][-1]['pr'] == pytest.approx(180)


async def test_live_series_restart_does_not_warm_up_historical_partial_points(service):
    await service.configure(settings(actual_power_max_age_seconds=30), now=0)
    service.store.add_observations(samples(at=550) + samples(at=590))
    service.store.set_meta('started_at', '1200')
    restarted = Service(service.store)
    result = restarted.live_series(now=1200)
    assert result['points'][0]['at'] == 600
    assert result['points'][0]['quality'] == 'partial'
    assert result['points'][0]['valid_seconds'] == 40


async def test_live_series_anchor_preserves_published_values(service):
    await service.configure(settings(), now=0)
    service.store.add_observations(samples() + samples(at=600))
    await service.tick(1200)
    service.store.add_observations(samples(at=1170, sun=400))
    result = service.live_series(now=1202)
    assert result['points'][-1] == {'at': 1200, **service.live_window}
    assert result['points'][-2]['estimated_power_w'] < 3720


async def test_live_series_preserves_current_offline_endpoint(service, monkeypatch):
    await service.configure(settings(), now=0)
    service.store.add_observations(samples() + samples(at=600))
    await service.tick(1200)
    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 1205)
    service._mark_offline()
    result = service.live_series()
    assert result['points'][-1]['at'] == 1205
    assert result['points'][-1]['estimated_power_w'] is None
    assert result['points'][-1]['actual_power_w'] is None
    assert result['points'][-1]['pr'] is None
    assert result['points'][-1]['quality'] == 'unavailable'
    assert result['points'][-1]['reason'] == 'current_source_unavailable'
    assert result['points'][-2]['pr'] == pytest.approx(90)


async def test_live_series_keeps_unavailable_observation_gaps(service):
    await service.configure(settings(), now=0)
    service.store.add_observations(samples() + samples(at=600)
                                   + [Observation('sensor.sun', 900, None)] + samples(at=1000))
    await service.tick(1200)
    result = service.live_series(now=1200)
    invalid = next(point for point in result['points'] if point['at'] == 900)
    assert invalid['estimated_power_w'] is None
    assert invalid['reason'] == 'current_source_unavailable'
    assert invalid['valid_seconds'] == 60
    assert result['points'][-1]['pr'] == pytest.approx(90)


async def test_live_series_short_uptime_keeps_the_empty_average_window(service):
    await service.configure(settings(), now=0)
    result = service.live_series(now=10)
    assert result['range'] == {'start': 0, 'end': 10}
    assert [point['at'] for point in result['points']] == [0, 5, 10]
    assert all(point['estimated_power_w'] is None and point['actual_power_w'] is None for point in result['points'])


async def test_live_series_route_authentication_and_origin(service, monkeypatch):
    monkeypatch.setattr('pvyieldlens.service.time.time', lambda: 1200)
    app = create_app(service, Runtime(web_password='test-pass'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app') as client:
        assert (await client.get('/api/live-series')).status_code == 401
        empty = await client.get('/api/live-series', auth=('admin', 'test-pass'))
        assert empty.status_code == 200
        assert (await client.get('/api/live-history', auth=('admin', 'test-pass'))).status_code == 404
        assert empty.json() == {'configured': False, 'recovering': False,
                                'range': {'start': 600, 'end': 1200}, 'step_seconds': None,
                                'context': None, 'points': []}
        await service.configure(settings(), now=0, origin='http://ha.test')
        service.store.set_meta('connection', '{"url":"http://ha.test","token":"private-token"}')
        service.store.add_observations(samples() + samples(at=600), origin='http://ha.test')
        await service.tick(1200)
        before = (service.store.cursor, service.store.totals(1200, 'UTC'), service.store.history(0, 1200))
        changes = service.store.db.total_changes
        response = await client.get('/api/live-series', auth=('admin', 'test-pass'))
        repeated = await client.get('/api/live-series', auth=('admin', 'test-pass'))
        assert response.status_code == 200
        assert response.json() == repeated.json()
        assert response.headers['cache-control'] == 'no-store'
        assert 'segments' not in response.text
        assert 'private-token' not in response.text
        assert 'test-pass' not in response.text
        assert before == (service.store.cursor, service.store.totals(1200, 'UTC'), service.store.history(0, 1200))
        assert service.store.db.total_changes == changes
        path = service.store.db.execute('PRAGMA database_list').fetchone()['file']
        reopened = Store(Path(path))
        try:
            replay = Service(reopened).live_series(now=1200)
            assert replay['points'][:-1] == response.json()['points'][:-1]
            assert replay['points'][0]['pr'] == pytest.approx(90)
        finally:
            reopened.close()
    ingress = create_app(service, Runtime(supervisor_token='super-secret'), run_background=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress, client=('10.0.0.5', 123)), base_url='http://app') as client:
        assert (await client.get('/api/live-series', headers={'x-forwarded-for': '172.30.32.2'})).status_code == 403
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ingress, client=('172.30.32.2', 123)), base_url='http://app') as client:
        response = await client.get('/api/live-series')
        assert response.status_code == 200
        assert response.json()['configured'] is True
        assert 'super-secret' not in json.dumps(response.json())
