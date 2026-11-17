from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .storage import DayAllocation, HistorySummary, HistoryWindow, Store, summarize_history


HistoryPeriod = Literal['today', '24h', '7d', '30d', 'custom']


class HistoryRange(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    start: float
    end: float


class HistoryDay(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    day: str
    start: float
    end: float
    summary: HistorySummary
    in_progress: bool
    boundary_unavailable: bool


class HistorySlice(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    windows: list[HistoryWindow]
    summary: HistorySummary
    requested_range: HistoryRange
    boundary_unavailable: bool
    days: list[HistoryDay]


class HistoryComparison(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    summary: HistorySummary
    requested_range: HistoryRange
    pr_change_pp: float | None


class HistoryView(HistorySlice):
    period: HistoryPeriod
    home_timezone: str
    today: str
    comparison: HistoryComparison | None = None


def _allocated_window(window: HistoryWindow, parts: list[DayAllocation]) -> HistoryWindow:
    """Derive a query-only record from exact, already settled calendar allocations."""
    start, end = parts[0]['start'], parts[-1]['end']
    valid = sum(part['valid_seconds'] for part in parts)
    estimated = sum(part['estimated_energy_wh'] for part in parts)
    actual = sum(part['actual_energy_wh'] for part in parts)
    return {**window, 'start': start, 'end': end, 'valid_seconds': valid,
            'estimated_energy_wh': estimated, 'actual_energy_wh': actual,
            'estimated_power_w': estimated * 3600 / valid if valid else None,
            'actual_power_w': actual * 3600 / valid if valid else None,
            'pr': actual / estimated * 100 if valid and estimated else None,
            'optimizable_power_w': (estimated - actual) * 3600 / valid if valid else None,
            'data_completeness_percent': valid / (end - start) * 100,
            'quality': 'complete' if valid and abs(valid - (end - start)) < 1e-6 else 'partial' if valid else 'unavailable',
            'reason': 'missing_data' if not valid else 'zero_estimated_power' if not estimated else None}


def _calendar_dates(start: float, end: float, zone: ZoneInfo) -> list[date]:
    """List household dates touched by a half-open timestamp range."""
    first = datetime.fromtimestamp(start, zone).date()
    last = datetime.fromtimestamp(end, zone).date()
    if end == datetime.combine(last, time(), zone).timestamp():
        last -= timedelta(days=1)
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def read_history_range(store: Store, start: float, end: float, home_timezone: str, *,
                       now: float, include_days: bool) -> HistorySlice:
    """Read committed calendar data without reconstructing or modifying settlements."""
    zone = ZoneInfo(home_timezone)
    rows = store.history(start, end, include_day_allocations=True)
    windows: list[HistoryWindow] = []
    excluded: list[HistoryWindow] = []
    for row in rows:
        if row['start'] >= start and row['end'] <= end:
            windows.append(row)
            continue
        allocations = row.get('day_allocations')
        parts = ([part for part in allocations['parts'] if part['start'] >= start and part['end'] <= end]
                 if allocations and allocations['home_timezone'] == home_timezone else [])
        # Only a stored calendar boundary can cut a settled source window exactly.
        if parts and parts[0]['start'] == max(start, row['start']) and parts[-1]['end'] == min(end, row['end']):
            windows.append({**_allocated_window(row, parts), 'source_start': row['start'], 'source_end': row['end']})
        else:
            excluded.append(row)

    days = []
    if include_days:
        dates = _calendar_dates(start, end, zone)
        daily: dict[date, list[HistoryWindow]] = {day: [] for day in dates}
        unavailable: set[date] = set()
        excluded_dates = {day for row in excluded
                          for day in _calendar_dates(max(start, row['start']), min(end, row['end']), zone)}
        for window in windows:
            covered = _calendar_dates(window['start'], window['end'], zone)
            if len(covered) == 1:
                daily[covered[0]].append(window)
                continue
            allocations = window.get('day_allocations')
            if allocations and allocations['home_timezone'] == home_timezone:
                for part in allocations['parts']:
                    if part['start'] >= window['start'] and part['end'] <= window['end']:
                        daily[datetime.fromtimestamp(part['start'], zone).date()].append(_allocated_window(window, [part]))
            else:
                unavailable.update(covered)

        today = datetime.fromtimestamp(now, zone).date()
        for day, settled in daily.items():
            left = datetime.combine(day, time(), zone).timestamp()
            right = datetime.combine(day + timedelta(days=1), time(), zone).timestamp()
            summary = summarize_history(settled, left, right)
            if day in unavailable:
                summary = summary.model_copy(update={'estimated_energy_kwh': None, 'actual_energy_kwh': None,
                                                     'pr': None, 'data_completeness_percent': None})
            days.append(HistoryDay(day=day.isoformat(), start=left, end=right, summary=summary,
                                   in_progress=day == today, boundary_unavailable=day in unavailable or day in excluded_dates))

    summary = summarize_history(windows, start, end)
    for window in windows:
        window.pop('day_allocations', None)
    return HistorySlice(windows=windows, summary=summary, requested_range=HistoryRange(start=start, end=end),
                        boundary_unavailable=bool(excluded), days=days)


def _read_rolling_range(store: Store, start: float, end: float) -> HistorySlice:
    windows = [row for row in store.history(start, end) if row['start'] >= start and row['end'] <= end]
    return HistorySlice(windows=windows, summary=summarize_history(windows, start, end),
                        requested_range=HistoryRange(start=start, end=end), boundary_unavailable=False, days=[])


def history_view(store: Store, period: HistoryPeriod, now: float, home_timezone: str, *,
                 start_date: date | None = None, end_date: date | None = None, compare: bool = False) -> HistoryView:
    """Read one settled history view while the caller holds the service lock."""
    zone = ZoneInfo(home_timezone)
    today = datetime.fromtimestamp(now, zone).date()
    count = 7 if period == '7d' else 30 if period == '30d' else 1
    if period == 'custom':
        assert start_date is not None and end_date is not None
        first_day = start_date
        end = min(now, datetime.combine(end_date + timedelta(days=1), time(), zone).timestamp())
    else:
        first_day = today - timedelta(days=count - 1)
        end = now
    start = now - 86400 if period == '24h' else datetime.combine(first_day, time(), zone).timestamp()
    current = (_read_rolling_range(store, start, end) if period == '24h'
               else read_history_range(store, start, end, home_timezone, now=now,
                                       include_days=period in ('7d', '30d', 'custom')))
    if (now == datetime.combine(today, time(), zone).timestamp()
            and (period in ('7d', '30d') or period == 'custom' and end_date == today)):
        current = current.model_copy(update={'days': [*current.days, HistoryDay(
            day=today.isoformat(), start=now, end=datetime.combine(today + timedelta(days=1), time(), zone).timestamp(),
            summary=summarize_history([], now, now), in_progress=True, boundary_unavailable=False)]})
    comparison = None
    if compare and period != 'custom' and current.summary.end is not None:
        previous_start = (start - 86400 if period == '24h'
                          else (datetime.fromtimestamp(start, zone) - timedelta(days=count)).timestamp())
        previous_end = (current.summary.end - 86400 if period == '24h'
                        else (datetime.fromtimestamp(current.summary.end, zone) - timedelta(days=count)).timestamp())
        previous = (_read_rolling_range(store, previous_start, previous_end) if period == '24h'
                    else read_history_range(store, previous_start, previous_end, home_timezone,
                                            now=now, include_days=False))
        comparison = HistoryComparison(
            summary=previous.summary, requested_range=previous.requested_range,
            pr_change_pp=current.summary.pr - previous.summary.pr
            if current.summary.pr is not None and previous.summary.pr is not None else None)
    return HistoryView(**current.model_dump(), period=period, home_timezone=home_timezone,
                       today=today.isoformat(), comparison=comparison)
