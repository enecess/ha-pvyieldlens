import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from pvyieldlens.engine import calculate
from pvyieldlens.storage import Store, summarize_history
from test_engine import samples, settings


def timestamp(local, home_timezone='Asia/Shanghai'):
    return datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(home_timezone)).timestamp()


@pytest.fixture
def store(tmp_path):
    instance = Store(tmp_path / 'data.sqlite')
    yield instance
    instance.close()


def settle_cross_midnight(store, *, missing_after=False, home_timezone='Asia/Shanghai'):
    start = timestamp('2026-11-10T23:58:00')
    midnight = timestamp('2026-11-11T00:00:00')
    end = timestamp('2026-11-11T00:03:00')
    config = settings(total_max_power_at_stc_w=600, home_timezone=home_timezone)
    revision = store.save_monitoring_settings(config, start)
    observations = (samples(at=start, power=300, sun=1000, temp=25)
                    + samples(at=midnight, power=None if missing_after else 1200, sun=2000, temp=25))
    store.add_observations(observations)
    store.settle(calculate(config, observations, start, end), revision, home_timezone)
    return start, midnight, end


def test_cross_day_allocation_survives_reload_and_raw_pruning_with_exact_fragment(store, tmp_path):
    from pvyieldlens.history import history_view

    start, midnight, end = settle_cross_midnight(store)
    original = store.history(start, end, include_day_allocations=True)[0]
    assert original['day_allocations'] == {'home_timezone': 'Asia/Shanghai', 'parts': [
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
        'pr': 100, 'data_completeness_percent': 100, 'valid_seconds': 180,
    })
    fragment = view.windows[0]
    assert (fragment['start'], fragment['end'], fragment['source_start'], fragment['source_end']) == (
        midnight, end, start, end)
    assert (fragment['estimated_power_w'], fragment['actual_power_w'], fragment['pr']) == (1200, 1200, 100)
    assert fragment['optimizable_power_w'] == 0
    assert fragment['quality'] == 'complete'
    assert not view.boundary_unavailable
    assert view.days == []
    assert restored.history(start, end, include_day_allocations=True) == [original]
    assert 'source_start' not in restored.latest_settled_window()
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
    assert fragment['actual_power_w'] is None and fragment['pr'] is None
    assert view.summary.actual_energy_kwh is None
    assert view.summary.data_completeness_percent == 0
    assert not view.boundary_unavailable


def test_same_day_and_exact_midnight_end_do_not_store_allocations(store):
    start = timestamp('2026-11-10T23:58:00')
    end = timestamp('2026-11-11T00:00:00')
    revision = store.save_monitoring_settings(settings(), start)
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
    assert view.home_timezone == 'Asia/Shanghai'
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


def test_unknown_internal_split_preserves_range_but_marks_daily_values_unavailable(store):
    from pvyieldlens.history import history_view

    start, _, end = settle_cross_midnight(store, home_timezone='Asia/Taipei')
    original = store.history(start, end, include_day_allocations=True)[0]
    assert original['day_allocations']['home_timezone'] == 'Asia/Taipei'
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
        assert day.summary.data_completeness_percent is None


@pytest.mark.parametrize('period', ['today', '7d', '30d'])
@pytest.mark.parametrize('known_remaining', [True, False])
def test_unknown_outer_split_is_excluded_and_flagged(store, period, known_remaining):
    from pvyieldlens.history import history_view

    start, midnight, end = settle_cross_midnight(store, home_timezone='Asia/Taipei')
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
        config = settings(total_max_power_at_stc_w=rated)
        revision = store.save_monitoring_settings(config, start + offset)
        store.settle(calculate(config, samples(at=start + offset, power=actual, temp=25, sun=1000),
                               start + offset, start + offset + 600), revision, 'Asia/Shanghai')
    first_two = history_view(store, '7d', start + 1200, 'Asia/Shanghai')
    assert first_two.summary.actual_energy_kwh == pytest.approx(0.95)
    assert first_two.days[-1].summary.pr == pytest.approx(95)
    all_three = history_view(store, '7d', start + 1800, 'Asia/Shanghai')
    assert all_three.days[-1].summary.actual_energy_kwh == pytest.approx(0.95)
    assert all_three.days[-1].summary.pr == pytest.approx(950 / 1100 * 100)


def settle_history_windows(store, windows, home_timezone='Asia/Shanghai'):
    config = settings(total_max_power_at_stc_w=600, home_timezone=home_timezone)
    revision = store.save_monitoring_settings(config, timestamp(windows[0][0], home_timezone))
    for local, seconds, power, sun in windows:
        start = timestamp(local, home_timezone)
        if store.cursor < start:
            store.settle(calculate(config, [], store.cursor, start), revision, home_timezone)
        store.settle(calculate(config, samples(at=start, power=power, temp=25, sun=sun),
                               start, start + seconds), revision, home_timezone)


def test_custom_range_counts_calendar_days_across_fall_dst(store):
    from pvyieldlens.history import history_view

    view = history_view(store, 'custom', timestamp('2026-11-18T12:00:00', 'America/New_York'),
                        'America/New_York', start_date=date(2026, 8, 20), end_date=date(2026, 11, 17))
    assert len(view.days) == 90
    assert view.requested_range.start == timestamp('2026-08-20T00:00:00', 'America/New_York')
    assert view.requested_range.end == timestamp('2026-11-18T00:00:00', 'America/New_York')
    assert view.requested_range.end - view.requested_range.start == 90 * 86400 + 3600
    assert view.days[0].summary.actual_energy_kwh is None
    assert not any(day.in_progress for day in view.days)


def test_custom_range_preserves_exact_allocations_and_zero(store):
    from pvyieldlens.history import history_view, read_history_range

    start, midnight, end = settle_cross_midnight(store)
    store.settle(calculate(settings(), samples(at=end, power=0), end, end + 60), store.revision, 'Asia/Shanghai')
    before = store.history(start, end + 60, include_day_allocations=True)
    zero_start = timestamp('2026-11-12T00:00:00')
    store.settle(calculate(settings(), [], end + 60, zero_start), store.revision, 'Asia/Shanghai')
    store.settle(calculate(settings(), samples(at=zero_start, power=0), zero_start, zero_start + 60),
                 store.revision, 'Asia/Shanghai')
    view = history_view(store, 'custom', timestamp('2026-11-14T00:00:00'), 'Asia/Shanghai',
                        start_date=date(2026, 11, 10), end_date=date(2026, 11, 13))
    zero_day = view.days[2]
    missing_day = view.days[3]
    assert sum(day.summary.actual_energy_kwh or 0 for day in view.days) == pytest.approx(view.summary.actual_energy_kwh)
    assert [day.summary.actual_energy_kwh for day in view.days[:2]] == pytest.approx([0.01, 0.06])
    assert zero_day.summary.actual_energy_kwh == 0
    assert missing_day.summary.actual_energy_kwh is None
    assert view.comparison is None
    fragment = read_history_range(store, midnight, end, 'Asia/Shanghai', now=end, include_days=False)
    assert fragment.summary.actual_energy_kwh == pytest.approx(0.06)
    assert fragment.windows[0]['source_start'] == start
    assert fragment.days == []
    assert store.history(start, end + 60, include_day_allocations=True) == before


def test_custom_range_including_today_stops_at_now(store):
    from pvyieldlens.history import history_view

    now = timestamp('2026-11-17T12:07:00')
    view = history_view(store, 'custom', now, 'Asia/Shanghai',
                        start_date=date(2026, 11, 16), end_date=date(2026, 11, 17))
    assert view.requested_range.end == now
    assert [day.in_progress for day in view.days] == [False, True]
    assert view.days[-1].end == timestamp('2026-11-18T00:00:00')


def test_custom_range_marks_stored_timezone_allocation_mismatch(store):
    from pvyieldlens.history import history_view

    _, midnight, end = settle_cross_midnight(store, home_timezone='Asia/Taipei')
    view = history_view(store, 'custom', end, 'Asia/Shanghai',
                        start_date=date(2026, 11, 11), end_date=date(2026, 11, 11))
    assert view.requested_range.start == midnight
    assert view.boundary_unavailable
    assert view.days[0].boundary_unavailable
    assert view.summary.actual_energy_kwh is None
    assert view.windows == []


def test_custom_range_never_splits_settlement_at_arbitrary_cutoff(store):
    from pvyieldlens.history import read_history_range

    start, midnight, end = settle_cross_midnight(store)
    view = read_history_range(store, midnight, end - 60, 'Asia/Shanghai', now=end, include_days=True)
    assert view.windows == []
    assert view.summary.actual_energy_kwh is None
    assert view.boundary_unavailable
    assert view.days[0].boundary_unavailable
    assert store.history(start, end)[0]['actual_energy_wh'] == pytest.approx(70)


@pytest.mark.parametrize('period,previous_start,current_start', [
    ('today', '2026-11-16T00:00:00', '2026-11-17T00:00:00'),
    ('7d', '2026-11-04T00:00:00', '2026-11-11T00:00:00'),
    ('30d', '2026-09-19T00:00:00', '2026-10-19T00:00:00'),
])
def test_previous_period_stops_at_comparable_settlement(store, period, previous_start, current_start):
    from pvyieldlens.history import history_view

    previous_day = '2026-11-16' if period == 'today' else '2026-11-10' if period == '7d' else '2026-10-18'
    settle_history_windows(store, [
        (previous_day + 'T12:00:00', 300, 540, 1000),
        (previous_day + 'T12:05:00', 300, 0, 1000),
        ('2026-11-17T12:00:00', 300, 480, 1000),
    ])
    view = history_view(store, period, timestamp('2026-11-17T12:07:00'), 'Asia/Shanghai', compare=True)
    assert view.requested_range.start == timestamp(current_start)
    assert view.summary.pr == pytest.approx(80)
    assert view.comparison.summary.pr == pytest.approx(90)
    assert view.comparison.pr_change_pp == pytest.approx(-10)
    assert view.comparison.requested_range.start == timestamp(previous_start)
    assert view.comparison.requested_range.end == timestamp(previous_day + 'T12:05:00')
    assert view.comparison.summary.end == timestamp(previous_day + 'T12:05:00')


def test_previous_period_excludes_window_crossing_non_calendar_cutoff(store):
    from pvyieldlens.history import history_view

    settle_history_windows(store, [
        ('2026-11-16T12:00:00', 600, 540, 1000),
        ('2026-11-17T12:00:00', 300, 480, 1000),
    ])
    view = history_view(store, 'today', timestamp('2026-11-17T12:07:00'), 'Asia/Shanghai', compare=True)
    assert view.comparison.requested_range.end == timestamp('2026-11-16T12:05:00')
    assert view.comparison.summary.actual_energy_kwh is None
    assert view.comparison.pr_change_pp is None


@pytest.mark.parametrize('prior_sun', [0, 1000])
def test_previous_period_empty_or_zero_denominator_pr_is_unavailable(store, prior_sun):
    from pvyieldlens.history import history_view

    if prior_sun == 0:
        settle_history_windows(store, [
            ('2026-11-16T12:00:00', 300, 0, 0),
            ('2026-11-17T12:00:00', 300, 480, 1000),
        ])
    else:
        settle_history_windows(store, [('2026-11-17T12:00:00', 300, 480, 1000)])
    view = history_view(store, 'today', timestamp('2026-11-17T12:07:00'), 'Asia/Shanghai', compare=True)
    assert view.comparison.summary.pr is None
    assert view.comparison.pr_change_pp is None


def test_previous_period_is_absent_without_current_settlement(store):
    from pvyieldlens.history import history_view

    view = history_view(store, 'today', timestamp('2026-11-17T12:07:00'), 'Asia/Shanghai', compare=True)
    assert view.comparison is None


def test_previous_period_uses_household_dates_across_dst(store):
    from pvyieldlens.history import history_view

    zone = 'America/New_York'
    settle_history_windows(store, [
        ('2026-10-31T12:00:00', 300, 540, 1000),
        ('2026-11-01T12:00:00', 300, 480, 1000),
    ], zone)
    view = history_view(store, 'today', timestamp('2026-11-01T12:07:00', zone), zone, compare=True)
    assert view.comparison.requested_range.start == timestamp('2026-10-31T00:00:00', zone)
    assert view.comparison.requested_range.end == timestamp('2026-10-31T12:05:00', zone)
    assert view.summary.end - view.comparison.requested_range.end == 25 * 3600
    assert view.comparison.pr_change_pp == pytest.approx(-10)


def test_previous_period_rolling_24h_preserves_seconds_and_whole_windows(store):
    from pvyieldlens.history import history_view

    settle_history_windows(store, [
        ('2026-11-15T12:06:00', 300, 540, 1000),
        ('2026-11-16T12:06:00', 300, 0, 1000),
        ('2026-11-17T12:00:00', 300, 480, 1000),
    ])
    now = timestamp('2026-11-17T12:07:00')
    view = history_view(store, '24h', now, 'Asia/Shanghai', compare=True)
    assert view.requested_range.start == now - 86400
    assert view.summary.pr == pytest.approx(80)
    assert view.comparison.requested_range.start == now - 2 * 86400
    assert view.comparison.requested_range.end == timestamp('2026-11-16T12:05:00')
    assert view.comparison.summary.pr is None
    assert view.comparison.pr_change_pp is None
    assert not view.boundary_unavailable
    assert view.days == []


@pytest.mark.parametrize('first', [date(2026, 11, 16), date(2026, 11, 17)])
def test_custom_range_at_midnight_keeps_inclusive_today_slot(store, first):
    from pvyieldlens.history import history_view

    now = timestamp('2026-11-17T00:00:00')
    view = history_view(store, 'custom', now, 'Asia/Shanghai',
                        start_date=first, end_date=date(2026, 11, 17))
    assert len(view.days) == (date(2026, 11, 17) - first).days + 1
    assert view.days[-1].day == '2026-11-17'
    assert view.days[-1].in_progress
    assert view.days[-1].summary.actual_energy_kwh is None
    assert view.days[-1].start == now
    assert view.days[-1].end == timestamp('2026-11-18T00:00:00')
    assert view.requested_range.end == now


def test_custom_range_ending_yesterday_at_midnight_excludes_today(store):
    from pvyieldlens.history import history_view

    now = timestamp('2026-11-17T00:00:00')
    view = history_view(store, 'custom', now, 'Asia/Shanghai',
                        start_date=date(2026, 11, 16), end_date=date(2026, 11, 16))
    assert [day.day for day in view.days] == ['2026-11-16']
    assert not view.days[0].in_progress
