from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def history_payload(windows, summary, requested_range, period='today', home_timezone='UTC', *, evaluated_at=None):
    """Keep chart-only doubles faithful to the complete preset response contract."""
    today = datetime.fromtimestamp(requested_range['end'] if evaluated_at is None else evaluated_at,
                                   ZoneInfo(home_timezone)).date()
    empty = {'start': None, 'end': None, 'estimated_energy_kwh': None,
             'actual_energy_kwh': None, 'pr': None, 'data_completeness_percent': None, 'valid_seconds': 0}
    dates = [today - timedelta(days=offset) for offset in reversed(range({'7d': 7, '30d': 30}.get(period, 0)))]
    return {'windows': windows, 'summary': summary, 'requested_range': requested_range,
            'comparison': None, 'period': period, 'home_timezone': home_timezone, 'today': today.isoformat(), 'boundary_unavailable': False,
            'days': [{'day': day.isoformat(),
                      'start': datetime.combine(day, datetime.min.time(), ZoneInfo(home_timezone)).timestamp(),
                      'end': datetime.combine(day + timedelta(days=1), datetime.min.time(), ZoneInfo(home_timezone)).timestamp(),
                      'summary': dict(empty), 'in_progress': day == today, 'boundary_unavailable': False}
                     for day in dates]}
