import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pvyieldlens.engine import calculate
from pvyieldlens.storage import Store, summarize_history
from test_engine import samples, settings


def timestamp(local, timezone='Asia/Shanghai'):
    return datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(timezone)).timestamp()


@pytest.fixture
def store(tmp_path):
    instance = Store(tmp_path / 'data.sqlite')
    yield instance
    instance.close()


def settle_cross_midnight(store, *, missing_after=False):
    start = timestamp('2026-11-10T23:58:00')
    midnight = timestamp('2026-11-11T00:00:00')
    end = timestamp('2026-11-11T00:03:00')
    config = settings(rated_power_w=600)
    revision = store.save_settings(config, start)
    observations = (samples(at=start, power=300, sun=1000, temp=25)
                    + samples(at=midnight, power=None if missing_after else 1200, sun=2000, temp=25))
    store.add_observations(observations)
    store.settle(calculate(config, observations, start, end), revision, 'Asia/Shanghai')
    return start, midnight, end


def test_cross_day_allocation_survives_reload_and_raw_pruning_with_exact_fragment(store, tmp_path):
    from pvyieldlens.history import history_view

    start, midnight, end = settle_cross_midnight(store)
    original = store.history(start, end, include_day_allocations=True)[0]
    assert original['day_allocations'] == {'timezone': 'Asia/Shanghai', 'parts': [
        {'start': start, 'end': midnight, 'valid_seconds': 120, 'estimated_energy_wh': 20, 'actual_energy_wh': 10},
        {'start': midnight, 'end': end, 'valid_seconds': 180, 'estimated_energy_wh': 60, 'actual_energy_wh': 60},
    ]}
    before_totals = store.totals(end, 'Asia/Shanghai')
    before_meta = list(store.db.execute('SELECT * FROM metadata ORDER BY key'))
    store.prune(end + 8 * 86400)
    assert store.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == 0
    assert store.db.execute('SELECT COUNT(*) FROM window_segments').fetchone()[0] == 0
    restored = Store(tmp_path / 'data.sqlite')
    restored.db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                              if action == sqlite3.SQLITE_READ and table in ('observations', 'window_segments')
                              else sqlite3.SQLITE_OK)
    view = history_view(restored, 'today', end, 'Asia/Shanghai')
    assert view.requested_range.model_dump() == {'start': midnight, 'end': end}
    assert view.summary.model_dump() == pytest.approx({
        'start': midnight, 'end': end, 'estimated_energy_kwh': 0.06, 'actual_energy_kwh': 0.06,
        'pr': 100, 'coverage_percent': 100, 'valid_seconds': 180,
    })
    fragment = view.windows[0]
    assert (fragment['start'], fragment['end'], fragment['source_start'], fragment['source_end']) == (
        midnight, end, start, end)
    assert (fragment['estimated_power'], fragment['actual_power'], fragment['pr']) == (1200, 1200, 100)
    assert fragment['optimizable_power'] == 0
    assert fragment['quality'] == 'complete'
    assert not view.boundary_unavailable
    assert view.days == []
    assert restored.history(start, end, include_day_allocations=True) == [original]
    assert 'source_start' not in restored.latest_window()
    assert restored.totals(end, 'Asia/Shanghai') == before_totals
    assert [tuple(row) for row in restored.db.execute('SELECT * FROM metadata ORDER BY key')] == [tuple(row) for row in before_meta]
    restored.close()


def test_cross_day_allocation_keeps_unavailable_portion_and_fragment(store):
    from pvyieldlens.history import history_view

    start, midnight, end = settle_cross_midnight(store, missing_after=True)
    original = store.history(start, end, include_day_allocations=True)[0]
    assert original['day_allocations']['parts'][1] == {
        'start': midnight, 'end': end, 'valid_seconds': 0, 'estimated_energy_wh': 0, 'actual_energy_wh': 0,
    }
    view = history_view(store, 'today', end, 'Asia/Shanghai')
    fragment = view.windows[0]
    assert fragment['start'] == midnight
    assert fragment['quality'] == 'unavailable'
    assert fragment['reason'] == 'missing_data'
    assert fragment['actual_power'] is None and fragment['pr'] is None
    assert view.summary.actual_energy_kwh is None
    assert view.summary.coverage_percent == 0
    assert not view.boundary_unavailable


def test_same_day_and_exact_midnight_end_do_not_store_allocations(store):
    start = timestamp('2026-11-10T23:58:00')
    end = timestamp('2026-11-11T00:00:00')
    revision = store.save_settings(settings(), start)
    store.settle(calculate(settings(), samples(at=start), start, end), revision, 'Asia/Shanghai')
    store.settle(calculate(settings(), samples(at=end), end, end + 60), revision, 'Asia/Shanghai')
    assert all('day_allocations' not in row for row in store.history(start, end + 60, include_day_allocations=True))


@pytest.mark.parametrize('period,count,first', [('7d', 7, '2026-11-05'), ('30d', 30, '2026-10-13')])
def test_calendar_daily_energy_sums_match_range_and_keep_empty_slots(store, period, count, first):
    from pvyieldlens.history import history_view

    _, _, end = settle_cross_midnight(store)
    view = history_view(store, period, end, 'Asia/Shanghai')
    assert len(view.days) == count
    assert view.days[0].day == first
    assert view.days[-1].day == '2026-11-11'
    assert sum(day.in_progress for day in view.days) == 1
    assert view.days[0].summary.actual_energy_kwh is None
    assert view.days[0].summary.valid_seconds == 0
    assert not view.days[0].boundary_unavailable
    assert view.summary.estimated_energy_kwh == pytest.approx(0.08)
    assert view.summary.actual_energy_kwh == pytest.approx(0.07)
    assert view.summary.pr == pytest.approx(87.5)
    assert [day.summary.actual_energy_kwh for day in view.days[-2:]] == pytest.approx([0.01, 0.06])
    assert [day.summary.pr for day in view.days[-2:]] == pytest.approx([50, 100])
    assert sum(day.summary.actual_energy_kwh or 0 for day in view.days) == pytest.approx(view.summary.actual_energy_kwh)
    assert sum(day.summary.estimated_energy_kwh or 0 for day in view.days) == pytest.approx(view.summary.estimated_energy_kwh)
    assert len(view.windows) == 1 and 'source_start' not in view.windows[0]


@pytest.mark.parametrize('period,count,start', [
    ('today', 0, '2026-11-11T00:00:00'), ('7d', 7, '2026-11-05T00:00:00'),
    ('30d', 30, '2026-10-13T00:00:00'), ('24h', 0, '2026-11-10T00:00:00'),
])
def test_calendar_midnight_updates_today_without_new_settlement(store, period, count, start):
    from pvyieldlens.history import history_view

    now = timestamp('2026-11-11T00:00:00')
    view = history_view(store, period, now, 'Asia/Shanghai')
    assert view.today == '2026-11-11'
    assert view.timezone == 'Asia/Shanghai'
    assert view.requested_range.start == timestamp(start)
    assert view.requested_range.end == now
    assert len(view.days) == count
    assert view.summary.start is None and view.summary.actual_energy_kwh is None
    assert view.windows == []
    if view.days:
        assert view.days[-1].in_progress
        assert view.days[-1].end - view.days[-1].start == 86400


@pytest.mark.parametrize('now,day,hours', [
    ('2026-03-09T12:00:00', '2026-03-08', 23), ('2026-11-02T12:00:00', '2026-11-01', 25),
])
@pytest.mark.parametrize('period,count', [('7d', 7), ('30d', 30)])
def test_calendar_dst_days_use_local_midnights(store, now, day, hours, period, count):
    from pvyieldlens.history import history_view

    zone = 'America/New_York'
    view = history_view(store, period, timestamp(now, zone), zone)
    assert len(view.days) == count
    transition = next(item for item in view.days if item.day == day)
    assert transition.end - transition.start == hours * 3600
    assert all(left.end == right.start for left, right in zip(view.days, view.days[1:]))
    assert view.days[-1].day == now[:10]


@pytest.mark.parametrize('metadata', ['legacy', 'different_timezone'])
def test_unknown_internal_split_preserves_range_but_marks_daily_values_unavailable(store, metadata):
    from pvyieldlens.history import history_view

    start, _, end = settle_cross_midnight(store)
    original = store.history(start, end, include_day_allocations=True)[0]
    if metadata == 'legacy':
        original.pop('day_allocations', None)
    else:
        original['day_allocations'] = {'timezone': 'UTC', 'parts': []}
    with store.db:
        store.db.execute('UPDATE windows SET result=?', (json.dumps(original),))
    view = history_view(store, '7d', end, 'Asia/Shanghai')
    assert view.summary.actual_energy_kwh == pytest.approx(0.07)
    assert view.summary.pr == pytest.approx(87.5)
    assert view.windows == [{key: value for key, value in original.items() if key != 'day_allocations'}]
    assert not view.boundary_unavailable
    for day in view.days[-2:]:
        assert day.boundary_unavailable
        assert day.summary.actual_energy_kwh is None
        assert day.summary.estimated_energy_kwh is None
        assert day.summary.pr is None
        assert day.summary.coverage_percent is None


@pytest.mark.parametrize('period', ['today', '7d', '30d'])
@pytest.mark.parametrize('metadata', ['legacy', 'different_timezone'])
@pytest.mark.parametrize('known_remaining', [True, False])
def test_unknown_outer_split_is_excluded_and_flagged(store, period, metadata, known_remaining):
    from pvyieldlens.history import history_view

    start, midnight, end = settle_cross_midnight(store)
    with store.db:
        original = store.history(start, end, include_day_allocations=True)[0]
        if metadata == 'legacy':
            original.pop('day_allocations', None)
        else:
            original['day_allocations']['timezone'] = 'UTC'
        store.db.execute('UPDATE windows SET result=?', (json.dumps(original),))
    if known_remaining:
        store.settle(calculate(settings(), samples(at=end, power=0), end, end + 60), store.revision, 'Asia/Shanghai')
    now = end + (0 if period == 'today' else 6 if period == '7d' else 29) * 86400 + 60
    view = history_view(store, period, now, 'Asia/Shanghai')
    assert view.requested_range.start == midnight
    assert view.boundary_unavailable
    assert len(view.windows) == (1 if known_remaining else 0)
    assert view.summary.start == (end if known_remaining else None)
    assert view.summary.actual_energy_kwh == (0 if known_remaining else None)
    assert view.summary.estimated_energy_kwh == (pytest.approx(0.062) if known_remaining else None)
    if view.days:
        assert view.days[0].boundary_unavailable
        assert view.days[0].summary.actual_energy_kwh == (0 if known_remaining else None)


def test_rolling_and_numeric_queries_never_prorate_even_with_exact_allocation(store):
    from pvyieldlens.history import history_view

    start, midnight, end = settle_cross_midnight(store)
    view = history_view(store, '24h', midnight + 86400, 'Asia/Shanghai')
    assert view.windows == []
    assert view.summary.actual_energy_kwh is None
    assert not view.boundary_unavailable
    assert summarize_history(store.history(midnight, end), midnight, end).actual_energy_kwh is None


def test_daily_pr_is_energy_weighted_and_valid_zero_actual_is_not_missing(store):
    from pvyieldlens.history import history_view

    start = timestamp('2026-11-11T00:00:00')
    for offset, rated, actual in [(0, 600, 300), (600, 5400, 5400), (1200, 600, 0)]:
        config = settings(rated_power_w=rated)
        revision = store.save_settings(config, start + offset)
        store.settle(calculate(config, samples(at=start + offset, power=actual, temp=25, sun=1000),
                               start + offset, start + offset + 600), revision, 'Asia/Shanghai')
    first_two = history_view(store, '7d', start + 1200, 'Asia/Shanghai')
    assert first_two.summary.actual_energy_kwh == pytest.approx(0.95)
    assert first_two.days[-1].summary.pr == pytest.approx(95)
    all_three = history_view(store, '7d', start + 1800, 'Asia/Shanghai')
    assert all_three.days[-1].summary.actual_energy_kwh == pytest.approx(0.95)
    assert all_three.days[-1].summary.pr == pytest.approx(950 / 1100 * 100)
