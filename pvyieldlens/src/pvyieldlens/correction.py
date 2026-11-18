from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .history import read_history_range
from .settings import MonitoringSettings
from .storage import Store


class ForecastCorrection(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    pr: float | None
    history_days: int
    start: float
    end: float


def physical_context(settings: MonitoringSettings, origin: str):
    temperature_model = ((settings.module_temperature_noct_c, settings.ambient_site)
                         if settings.module_temperature_entity is None else None)
    return (origin, settings.entities, settings.total_max_power_at_stc_w,
            settings.pmax_temperature_coefficient_pct_per_c, temperature_model)


def correction_view(store: Store, monitoring_settings: MonitoringSettings, origin: str,
                    now: float, history_days: int) -> ForecastCorrection:
    """Aggregate exact committed daily energy from the current physical epoch."""
    zone = ZoneInfo(monitoring_settings.home_timezone)
    today = datetime.fromtimestamp(now, zone).date()
    start = datetime.combine(today - timedelta(days=history_days), time(), zone).timestamp()
    end = datetime.combine(today, time(), zone).timestamp()
    context = physical_context(monitoring_settings, origin)
    epoch_start = end
    for period in reversed(store.configuration_history(start, now)):
        if physical_context(period.monitoring_settings, period.origin) != context:
            break
        epoch_start = period.effective_at
    days = read_history_range(store, max(start, epoch_start), end, monitoring_settings.home_timezone,
                              now=now, include_days=True).days if epoch_start < end else []
    eligible = [(day.summary.estimated_energy_kwh, day.summary.actual_energy_kwh,
                 2 ** (-((today - date.fromisoformat(day.day)).days - 1) / (history_days / 2)))
                for day in days if not day.boundary_unavailable
                and day.summary.estimated_energy_kwh is not None and day.summary.estimated_energy_kwh > 0
                and day.summary.actual_energy_kwh is not None]
    return ForecastCorrection(
        pr=sum(actual * weight for _, actual, weight in eligible)
        / sum(estimated * weight for estimated, _, weight in eligible) * 100 if len(eligible) >= 3 else None,
        history_days=history_days, start=start, end=end,
    )
