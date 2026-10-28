from bisect import bisect_right
from dataclasses import asdict, dataclass

from .settings import Settings


@dataclass(frozen=True)
class Observation:
    entity_id: str
    at: float
    value: float | None
    reported_at: float | None = None


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    estimated_power: float
    actual_power: float


@dataclass(frozen=True)
class WindowResult:
    start: float
    end: float
    valid_seconds: float
    estimated_energy_wh: float
    actual_energy_wh: float
    estimated_power: float | None
    actual_power: float | None
    pr: float | None
    optimizable_power: float | None
    coverage_percent: float
    quality: str
    reason: str | None
    segments: tuple[Segment, ...]

    def public(self):
        return {key: value for key, value in asdict(self).items() if key != "segments"}


def calculate(settings: Settings, observations: list[Observation], start: float, end: float) -> WindowResult:
    """Integrate the intersection of valid, piecewise constant source intervals."""
    sources = [sorted({item.at: item for item in observations if item.entity_id == entity and item.at < end}.values(),
                      key=lambda item: item.at) for entity in settings.entities]
    points = sorted({start, end} | {
        point for source, age in zip(sources, settings.max_ages)
        for item in source for point in (item.at, item.at + age) if start < point < end
    })
    segments = []
    coefficient = settings.coefficient_per_c
    for left, right in zip(points, points[1:]):
        values = []
        for source, age in zip(sources, settings.max_ages):
            index = bisect_right(source, left, key=lambda item: item.at) - 1
            item = source[index] if index >= 0 else None
            values.append(item.value if item and left < item.at + age else None)
        power, temperature, irradiance = values
        if power is None or temperature is None or irradiance is None:
            continue
        factor = 1 + coefficient * (temperature - 25)
        if factor < 0:
            continue
        segments.append(Segment(left, right, settings.rated_power_w * factor * irradiance / 1000, power))
    duration = sum(part.end - part.start for part in segments)
    estimated = sum(part.estimated_power * (part.end - part.start) / 3600 for part in segments)
    actual = sum(part.actual_power * (part.end - part.start) / 3600 for part in segments)
    expected_power = estimated * 3600 / duration if duration else None
    actual_power = actual * 3600 / duration if duration else None
    return WindowResult(
        start, end, duration, estimated, actual, expected_power, actual_power,
        actual / estimated * 100 if estimated else None,
        expected_power - actual_power if duration else None,
        duration / (end - start) * 100 if end > start else 0,
        "complete" if duration and abs(duration - (end - start)) < 1e-6 else "partial" if duration else "unavailable",
        "missing_data" if not duration else "zero_expected_power" if not estimated else None,
        tuple(segments),
    )
