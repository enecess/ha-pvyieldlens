from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .storage import DayAllocation, HistorySummary, HistoryWindow, Store, summarize_history


HistoryPeriod = Literal['today', '24h', '7d', '30d']


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


class HistoryView(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    windows: list[HistoryWindow]
    summary: HistorySummary
    requested_range: HistoryRange
    period: HistoryPeriod
    home_timezone: str
    today: str
    boundary_unavailable: bool
    days: list[HistoryDay]


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


def history_view(store: Store, period: HistoryPeriod, now: float, home_timezone: str) -> HistoryView:
    """Read one settled history view while the caller holds the service lock."""
    zone = ZoneInfo(home_timezone)
    today = datetime.fromtimestamp(now, zone).date()
    count = 7 if period == '7d' else 30 if period == '30d' else 1
    first_day = today - timedelta(days=count - 1)
    start = now - 86400 if period == '24h' else datetime.combine(first_day, time(), zone).timestamp()
    rows = store.history(start, now, include_day_allocations=True)
    windows: list[HistoryWindow] = []
    excluded: list[HistoryWindow] = []
    for row in rows:
        if row['start'] >= start and row['end'] <= now:
            windows.append(row)
            continue
        if period == '24h':
            continue
        allocations = row.get('day_allocations')
        parts = ([part for part in allocations['parts'] if part['start'] >= start and part['end'] <= now]
                 if allocations and allocations['home_timezone'] == home_timezone else [])
        # Only a stored calendar boundary can cut a settled source window exactly.
        if parts and parts[0]['start'] == max(start, row['start']) and parts[-1]['end'] == min(now, row['end']):
            windows.append({**_allocated_window(row, parts), 'source_start': row['start'], 'source_end': row['end']})
        else:
            excluded.append(row)

    days = []
    if period in ('7d', '30d'):
        for offset in range(count):
            day = first_day + timedelta(days=offset)
            left = datetime.combine(day, time(), zone).timestamp()
            right = datetime.combine(day + timedelta(days=1), time(), zone).timestamp()
            daily: list[HistoryWindow] = []
            unavailable = False
            for window in windows:
                if window['end'] <= left or window['start'] >= right:
                    continue
                if window['start'] >= left and window['end'] <= right:
                    daily.append(window)
                    continue
                allocations = window.get('day_allocations')
                if allocations and allocations['home_timezone'] == home_timezone:
                    daily.extend(_allocated_window(window, [part]) for part in allocations['parts']
                                 if part['start'] >= left and part['end'] <= right)
                else:
                    unavailable = True
            summary = summarize_history(daily, left, right)
            if unavailable:
                summary = summary.model_copy(update={'estimated_energy_kwh': None, 'actual_energy_kwh': None,
                                                     'pr': None, 'data_completeness_percent': None})
            days.append(HistoryDay(day=day.isoformat(), start=left, end=right, summary=summary,
                                   in_progress=day == today,
                                   boundary_unavailable=unavailable or any(
                                       row['end'] > left and row['start'] < right for row in excluded)))

    summary = summarize_history(windows, start, now)
    for window in windows:
        window.pop('day_allocations', None)
    return HistoryView(windows=windows, summary=summary, requested_range=HistoryRange(start=start, end=now),
                       period=period, home_timezone=home_timezone, today=today.isoformat(),
                       boundary_unavailable=bool(excluded), days=days)
