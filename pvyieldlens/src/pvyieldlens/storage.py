import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import NotRequired, TypedDict
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .engine import Observation, WindowResult
from .settings import AMBIENT_OBSERVATION_PREFIX, AMBIENT_SAMPLE_SECONDS, ForecastSettings, MonitoringSettings


class DayAllocation(TypedDict):
    start: float
    end: float
    valid_seconds: float
    estimated_energy_wh: float
    actual_energy_wh: float


class DayAllocations(TypedDict):
    home_timezone: str
    parts: list[DayAllocation]


class HistoryWindow(TypedDict):
    revision: int
    start: float
    end: float
    valid_seconds: float
    estimated_energy_wh: float
    actual_energy_wh: float
    estimated_power_w: float | None
    actual_power_w: float | None
    pr: float | None
    optimizable_power_w: float | None
    data_completeness_percent: float
    quality: str
    reason: str | None
    source_start: NotRequired[float]
    source_end: NotRequired[float]
    day_allocations: NotRequired[DayAllocations]


class HistorySummary(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True, frozen=True)

    start: float | None
    end: float | None
    estimated_energy_kwh: float | None
    actual_energy_kwh: float | None
    pr: float | None
    data_completeness_percent: float | None
    valid_seconds: float


def summarize_history(windows: list[HistoryWindow], start: float, end: float) -> HistorySummary:
    included = [row for row in windows if row['start'] >= start and row['end'] <= end]
    if not included:
        return HistorySummary(start=None, end=None, estimated_energy_kwh=None, actual_energy_kwh=None, pr=None,
                              data_completeness_percent=None, valid_seconds=0)
    first = min(row['start'] for row in included)
    last = max(row['end'] for row in included)
    valid = sum(row['valid_seconds'] for row in included)
    estimated = sum(row['estimated_energy_wh'] for row in included)
    return HistorySummary(
        start=first, end=last, estimated_energy_kwh=estimated / 1000 if valid else None,
        actual_energy_kwh=sum(row['actual_energy_wh'] for row in included) / 1000 if valid else None,
        pr=sum(row['actual_energy_wh'] for row in included) / estimated * 100 if valid and estimated else None,
        data_completeness_percent=valid / (last - first) * 100, valid_seconds=valid,
    )


@dataclass(frozen=True)
class ConfigurationRevision:
    revision: int
    effective_at: float
    monitoring_settings: MonitoringSettings
    origin: str

    @property
    def temperature_context(self):
        config = self.monitoring_settings
        return self.origin, config.module_temperature_entity or (config.ambient_site, config.module_temperature_noct_c)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS configs (
                revision INTEGER PRIMARY KEY, effective_at REAL NOT NULL, monitoring_settings TEXT NOT NULL, origin TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations (
                origin TEXT NOT NULL, entity_id TEXT NOT NULL, at REAL NOT NULL, value REAL, reported_at REAL,
                PRIMARY KEY(origin, entity_id, at));
            CREATE INDEX IF NOT EXISTS observation_time ON observations(at);
            CREATE TABLE IF NOT EXISTS windows (
                revision INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL, result TEXT NOT NULL,
                PRIMARY KEY(revision, start, end));
            CREATE TABLE IF NOT EXISTS window_segments (
                revision INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL, segments TEXT NOT NULL,
                PRIMARY KEY(revision, start, end));
            CREATE TABLE IF NOT EXISTS days (
                home_timezone TEXT NOT NULL, day TEXT NOT NULL, estimated_energy_wh REAL NOT NULL, valid_seconds REAL NOT NULL,
                allocation_complete INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(home_timezone, day));
            INSERT OR IGNORE INTO metadata VALUES ('estimated_energy_lifetime_wh', '0');
            INSERT OR IGNORE INTO metadata VALUES ('lifetime_valid_seconds', '0');
        """)

    def close(self):
        self.db.close()

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES (?, ?)", (key, value))

    @property
    def cursor(self) -> float | None:
        value = self.get_meta("cursor")
        return float(value) if value is not None else None

    @property
    def revision(self) -> int:
        return self.db.execute("SELECT COALESCE(MAX(revision),0) FROM configs").fetchone()[0]

    def monitoring_settings(self) -> MonitoringSettings | None:
        row = self.db.execute("SELECT monitoring_settings FROM configs ORDER BY revision DESC LIMIT 1").fetchone()
        return MonitoringSettings.model_validate_json(row[0]) if row else None

    def forecast_settings(self) -> ForecastSettings:
        value = self.get_meta('forecast_settings')
        return ForecastSettings.model_validate_json(value) if value else ForecastSettings()

    def save_forecast_settings(self, settings: ForecastSettings) -> None:
        self.set_meta('forecast_settings', settings.model_dump_json())

    def save_monitoring_settings(self, monitoring_settings: MonitoringSettings, effective_at: float, origin='') -> int:
        with self.db:
            result = self.db.execute("INSERT INTO configs(effective_at, monitoring_settings, origin) VALUES (?,?,?)",
                                     (effective_at, monitoring_settings.model_dump_json(), origin))
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('cursor', ?)", (str(effective_at),))
        return result.lastrowid

    def update_live_settings(self, monitoring_settings: MonitoringSettings):
        with self.db:
            self.db.execute('UPDATE configs SET monitoring_settings=? WHERE revision=?', (monitoring_settings.model_dump_json(), self.revision))

    def configuration_history(self, start: float, end: float) -> list[ConfigurationRevision]:
        rows = self.db.execute("""SELECT * FROM configs WHERE
            revision=(SELECT revision FROM configs WHERE effective_at<=? ORDER BY effective_at DESC,revision DESC LIMIT 1)
            OR (effective_at>? AND effective_at<=?) ORDER BY effective_at,revision""", (start, start, end))
        return [ConfigurationRevision(row['revision'], row['effective_at'], MonitoringSettings.model_validate_json(row['monitoring_settings']), row['origin']) for row in rows]

    def latest_origin(self) -> str:
        row = self.db.execute('SELECT origin FROM configs ORDER BY revision DESC LIMIT 1').fetchone()
        return row[0] if row else ''

    def add_observations(self, items: list[Observation], origin=''):
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?)",
                                [(origin, item.entity_id, item.at, item.value, item.reported_at) for item in items])

    def cache_ambient_temperature(self, items: tuple[Observation, ...], origin: str) -> None:
        cursor = self.cursor
        with self.db:
            # Late weather can fill input chart gaps. Preserve existing readings before the cursor.
            self.db.executemany("""
                INSERT INTO observations VALUES (?,?,?,?,?)
                ON CONFLICT(origin, entity_id, at) DO UPDATE SET value=excluded.value, reported_at=excluded.reported_at
                WHERE observations.at>=COALESCE(?, observations.at)
            """, ((origin, item.entity_id, item.at, item.value, item.reported_at, cursor) for item in items))

    def observations(self, start: float, end: float, entities: tuple[str, ...], origin='') -> list[Observation]:
        if not entities:
            return []
        placeholders = ','.join(['(?)'] * len(entities))
        rows = self.db.execute(f"""
            WITH sources(entity_id) AS (VALUES {placeholders})
            SELECT * FROM observations WHERE origin=? AND entity_id IN (SELECT entity_id FROM sources)
                AND at>=? AND at<=?
            UNION ALL
            SELECT observation.* FROM sources JOIN observations AS observation
                ON observation.origin=? AND observation.entity_id=sources.entity_id
                AND observation.at=(SELECT MAX(previous.at) FROM observations AS previous
                    WHERE previous.origin=? AND previous.entity_id=sources.entity_id AND previous.at<?)
            ORDER BY at,entity_id
        """, (*entities, origin, start, end, origin, origin, start))
        return [Observation(row['entity_id'], row['at'], row['value'], row['reported_at']) for row in rows]

    def settle(self, result: WindowResult, revision: int, home_timezone: str):
        if self.db.execute("SELECT 1 FROM windows WHERE revision=? AND start=? AND end=?",
                           (revision, result.start, result.end)).fetchone():
            return
        if self.cursor != result.start:
            raise ValueError("non_contiguous_settlement")
        zone = ZoneInfo(home_timezone)
        public = {**result.public(), 'revision': revision}
        stored = public.copy()
        midnight = datetime.combine(datetime.fromtimestamp(result.start, zone).date() + timedelta(days=1),
                                    time(), zone).timestamp()
        if midnight < result.end:
            parts: list[DayAllocation] = []
            left = result.start
            while left < result.end:
                right = min(result.end, midnight)
                intersections = [(segment, max(0, min(segment.end, right) - max(segment.start, left)))
                                 for segment in result.segments]
                parts.append({'start': left, 'end': right,
                              'valid_seconds': sum(duration for _, duration in intersections),
                              'estimated_energy_wh': sum(segment.estimated_power_w * duration / 3600
                                                         for segment, duration in intersections),
                              'actual_energy_wh': sum(segment.actual_power_w * duration / 3600
                                                      for segment, duration in intersections)})
                left = right
                midnight = datetime.combine(datetime.fromtimestamp(left, zone).date() + timedelta(days=1),
                                            time(), zone).timestamp()
            stored['day_allocations'] = {'home_timezone': home_timezone, 'parts': parts}
        detail = []
        for segment in result.segments:
            if detail and detail[-1][1] == segment.start and detail[-1][2] == segment.estimated_power_w:
                detail[-1][1] = segment.end
            else:
                detail.append([segment.start, segment.end, segment.estimated_power_w])
        with self.db:
            self.db.execute("INSERT INTO windows VALUES (?,?,?,?)",
                            (revision, result.start, result.end, json.dumps(stored)))
            self.db.execute('INSERT INTO window_segments VALUES (?,?,?,?)',
                            (revision, result.start, result.end, json.dumps(detail, separators=(',', ':'))))
            for left, end, power in detail:
                while left < end:
                    day = datetime.fromtimestamp(left, zone).date()
                    midnight = datetime.combine(day + timedelta(days=1), time(), zone).timestamp()
                    right = min(end, midnight)
                    self.db.execute("""INSERT INTO days(home_timezone,day,estimated_energy_wh,valid_seconds) VALUES (?,?,?,?)
                        ON CONFLICT(home_timezone,day) DO UPDATE SET
                        estimated_energy_wh=estimated_energy_wh+excluded.estimated_energy_wh, valid_seconds=valid_seconds+excluded.valid_seconds""",
                        (home_timezone, day.isoformat(), power * (right-left) / 3600, right-left))
                    left = right
            self.db.execute("UPDATE metadata SET value=CAST(value AS REAL)+? WHERE key='estimated_energy_lifetime_wh'",
                            (result.estimated_energy_wh,))
            self.db.execute("UPDATE metadata SET value=CAST(value AS REAL)+? WHERE key='lifetime_valid_seconds'",
                            (result.valid_seconds,))
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('cursor',?)", (str(result.end),))
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('latest_settled_window',?)", (json.dumps(public),))

    def rebuild_day(self, now: float, home_timezone: str):
        zone = ZoneInfo(home_timezone)
        day = datetime.fromtimestamp(now, zone).date()
        start = datetime.combine(day, time(), zone).timestamp()
        end = datetime.combine(day + timedelta(days=1), time(), zone).timestamp()
        energy, valid = self.db.execute('''SELECT
            COALESCE(SUM(json_extract(result,'$.estimated_energy_wh')),0),
            COALESCE(SUM(json_extract(result,'$.valid_seconds')),0)
            FROM windows WHERE start>=? AND end<=?''', (start, end)).fetchone()
        complete = True
        rows = self.db.execute('''SELECT segments FROM windows LEFT JOIN window_segments USING(revision,start,end)
            WHERE windows.end>? AND windows.start<? AND (windows.start<? OR windows.end>?)''', (start, end, start, end))
        for row in rows:
            if row['segments'] is None:
                # Retained boundary windows may no longer have their exact segment distribution.
                complete = False
            else:
                for left, right, power in json.loads(row['segments']):
                    duration = max(0, min(right, end) - max(left, start))
                    energy += power * duration / 3600
                    valid += duration
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO days VALUES (?,?,?,?,?)',
                            (home_timezone, day.isoformat(), energy, valid, complete))

    def totals(self, now: float, home_timezone: str):
        day = datetime.fromtimestamp(now, ZoneInfo(home_timezone)).date().isoformat()
        row = self.db.execute("SELECT estimated_energy_wh,valid_seconds,allocation_complete FROM days WHERE home_timezone=? AND day=?", (home_timezone, day)).fetchone()
        return {"estimated_energy_today_kwh": row[0] / 1000 if row else 0, "estimated_energy_lifetime_kwh": float(self.get_meta("estimated_energy_lifetime_wh")) / 1000,
                "day": day, "home_timezone": home_timezone, "today_valid_seconds": row[1] if row else 0,
                "today_allocation_complete": bool(row[2]) if row else True,
                "lifetime_valid_seconds": float(self.get_meta("lifetime_valid_seconds")), "settled_until": self.cursor}

    def latest_settled_window(self) -> HistoryWindow | None:
        value = self.get_meta("latest_settled_window")
        return json.loads(value) if value else None

    def history(self, start: float, end: float, *, include_day_allocations=False) -> list[HistoryWindow]:
        windows = [{**json.loads(row['result']), 'revision': row['revision']}
                   for row in self.db.execute("SELECT revision,result FROM windows WHERE end>? AND start<? ORDER BY start", (start, end))]
        if not include_day_allocations:
            for window in windows:
                window.pop('day_allocations', None)
        return windows

    def prune(self, now: float):
        cutoff = now - 7 * 86400
        with self.db:
            self.db.execute("""
                DELETE FROM observations WHERE at<? AND (at<=? OR entity_id NOT GLOB ?)
            """, (cutoff, cutoff - AMBIENT_SAMPLE_SECONDS, f'{AMBIENT_OBSERVATION_PREFIX}*'))
            self.db.execute("DELETE FROM windows WHERE end<?", (now - 90 * 86400,))
            self.db.execute("DELETE FROM window_segments WHERE end<?", (now - 3 * 86400,))
