import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .engine import Observation, WindowResult
from .settings import Settings


@dataclass(frozen=True)
class ConfigurationRevision:
    revision: int
    effective_at: float
    settings: Settings
    origin: str


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS configs (
                revision INTEGER PRIMARY KEY, effective_at REAL NOT NULL, settings TEXT NOT NULL, origin TEXT NOT NULL);
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
                timezone TEXT NOT NULL, day TEXT NOT NULL, energy_wh REAL NOT NULL, valid_seconds REAL NOT NULL,
                complete INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(timezone, day));
            INSERT OR IGNORE INTO metadata VALUES ('total_wh', '0');
            INSERT OR IGNORE INTO metadata VALUES ('valid_seconds', '0');
        """)
        if 'complete' not in {row['name'] for row in self.db.execute('PRAGMA table_info(days)')}:
            self.db.execute('ALTER TABLE days ADD COLUMN complete INTEGER NOT NULL DEFAULT 1')

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

    def settings(self) -> Settings | None:
        row = self.db.execute("SELECT settings FROM configs ORDER BY revision DESC LIMIT 1").fetchone()
        return Settings.model_validate_json(row[0]) if row else None

    def save_settings(self, settings: Settings, effective_at: float, origin='') -> int:
        with self.db:
            result = self.db.execute("INSERT INTO configs(effective_at, settings, origin) VALUES (?,?,?)",
                                     (effective_at, settings.model_dump_json(), origin))
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('cursor', ?)", (str(effective_at),))
        return result.lastrowid

    def update_realtime_settings(self, settings: Settings):
        with self.db:
            self.db.execute('UPDATE configs SET settings=? WHERE revision=?', (settings.model_dump_json(), self.revision))

    def configuration_history(self, start: float, end: float) -> list[ConfigurationRevision]:
        rows = self.db.execute("""SELECT * FROM configs WHERE
            revision=(SELECT revision FROM configs WHERE effective_at<=? ORDER BY effective_at DESC,revision DESC LIMIT 1)
            OR (effective_at>? AND effective_at<=?) ORDER BY effective_at,revision""", (start, start, end))
        return [ConfigurationRevision(row['revision'], row['effective_at'], Settings.model_validate_json(row['settings']), row['origin']) for row in rows]

    def latest_origin(self) -> str:
        row = self.db.execute('SELECT origin FROM configs ORDER BY revision DESC LIMIT 1').fetchone()
        return row[0] if row else ''

    def add_observations(self, items: list[Observation], origin=''):
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?)",
                                [(origin, item.entity_id, item.at, item.value, item.reported_at) for item in items])

    def observations(self, start: float, end: float, entities: tuple[str, str, str], origin='') -> list[Observation]:
        rows = self.db.execute("""
            WITH sources(entity_id) AS (VALUES (?),(?),(?))
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

    def settle(self, result: WindowResult, revision: int, timezone: str):
        if self.db.execute("SELECT 1 FROM windows WHERE revision=? AND start=? AND end=?",
                           (revision, result.start, result.end)).fetchone():
            return
        if self.cursor != result.start:
            raise ValueError("non_contiguous_settlement")
        zone = ZoneInfo(timezone)
        public = {**result.public(), 'revision': revision}
        detail = []
        for segment in result.segments:
            if detail and detail[-1][1] == segment.start and detail[-1][2] == segment.estimated_power:
                detail[-1][1] = segment.end
            else:
                detail.append([segment.start, segment.end, segment.estimated_power])
        with self.db:
            self.db.execute("INSERT INTO windows VALUES (?,?,?,?)",
                            (revision, result.start, result.end, json.dumps(public)))
            self.db.execute('INSERT INTO window_segments VALUES (?,?,?,?)',
                            (revision, result.start, result.end, json.dumps(detail, separators=(',', ':'))))
            for left, end, power in detail:
                while left < end:
                    day = datetime.fromtimestamp(left, zone).date()
                    midnight = datetime.combine(day + timedelta(days=1), time(), zone).timestamp()
                    right = min(end, midnight)
                    self.db.execute("""INSERT INTO days(timezone,day,energy_wh,valid_seconds) VALUES (?,?,?,?)
                        ON CONFLICT(timezone,day) DO UPDATE SET
                        energy_wh=energy_wh+excluded.energy_wh, valid_seconds=valid_seconds+excluded.valid_seconds""",
                        (timezone, day.isoformat(), power * (right-left) / 3600, right-left))
                    left = right
            self.db.execute("UPDATE metadata SET value=CAST(value AS REAL)+? WHERE key='total_wh'",
                            (result.estimated_energy_wh,))
            self.db.execute("UPDATE metadata SET value=CAST(value AS REAL)+? WHERE key='valid_seconds'",
                            (result.valid_seconds,))
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('cursor',?)", (str(result.end),))
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('latest_window',?)", (json.dumps(public),))

    def rebuild_day(self, now: float, timezone: str):
        zone = ZoneInfo(timezone)
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
                # Legacy boundary windows do not retain their midnight distribution.
                complete = False
            else:
                for left, right, power in json.loads(row['segments']):
                    duration = max(0, min(right, end) - max(left, start))
                    energy += power * duration / 3600
                    valid += duration
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO days VALUES (?,?,?,?,?)',
                            (timezone, day.isoformat(), energy, valid, complete))

    def totals(self, now: float, timezone: str):
        day = datetime.fromtimestamp(now, ZoneInfo(timezone)).date().isoformat()
        row = self.db.execute("SELECT energy_wh,valid_seconds,complete FROM days WHERE timezone=? AND day=?", (timezone, day)).fetchone()
        return {"daily_kwh": row[0] / 1000 if row else 0, "total_kwh": float(self.get_meta("total_wh")) / 1000,
                "day": day, "timezone": timezone, "daily_valid_seconds": row[1] if row else 0,
                "daily_complete": bool(row[2]) if row else True,
                "total_valid_seconds": float(self.get_meta("valid_seconds")), "settled_until": self.cursor}

    def latest_window(self):
        value = self.get_meta("latest_window")
        return json.loads(value) if value else None

    def history(self, start: float, end: float):
        return [{**json.loads(row['result']), 'revision': row['revision']}
                for row in self.db.execute("SELECT revision,result FROM windows WHERE end>? AND start<? ORDER BY start", (start, end))]

    def prune(self, now: float):
        with self.db:
            self.db.execute("DELETE FROM observations WHERE at<?", (now - 7 * 86400,))
            self.db.execute("DELETE FROM windows WHERE end<?", (now - 90 * 86400,))
            self.db.execute("DELETE FROM window_segments WHERE end<?", (now - 3 * 86400,))
