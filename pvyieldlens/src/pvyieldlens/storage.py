import json
import sqlite3
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .engine import Observation, WindowResult
from .settings import Settings


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS configs (
                revision INTEGER PRIMARY KEY, effective_at REAL NOT NULL, settings TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations (
                entity_id TEXT NOT NULL, at REAL NOT NULL, value REAL, reported_at REAL,
                PRIMARY KEY(entity_id, at));
            CREATE INDEX IF NOT EXISTS observation_time ON observations(at);
            CREATE TABLE IF NOT EXISTS windows (
                revision INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL, result TEXT NOT NULL,
                PRIMARY KEY(revision, start, end));
            CREATE TABLE IF NOT EXISTS days (
                timezone TEXT NOT NULL, day TEXT NOT NULL, energy_wh REAL NOT NULL, valid_seconds REAL NOT NULL,
                PRIMARY KEY(timezone, day));
            INSERT OR IGNORE INTO metadata VALUES ('total_wh', '0');
            INSERT OR IGNORE INTO metadata VALUES ('valid_seconds', '0');
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

    def settings(self) -> Settings | None:
        row = self.db.execute("SELECT settings FROM configs ORDER BY revision DESC LIMIT 1").fetchone()
        return Settings.model_validate_json(row[0]) if row else None

    def save_settings(self, settings: Settings, effective_at: float) -> int:
        with self.db:
            result = self.db.execute("INSERT INTO configs(effective_at, settings) VALUES (?,?)",
                                     (effective_at, settings.model_dump_json()))
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('cursor', ?)", (str(effective_at),))
        return result.lastrowid

    def add_observations(self, items: list[Observation]):
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?)",
                                [(item.entity_id, item.at, item.value, item.reported_at) for item in items])

    def observations(self, start: float, end: float) -> list[Observation]:
        rows = self.db.execute("""
            SELECT * FROM observations WHERE at>=? AND at<=?
            UNION ALL
            SELECT * FROM observations WHERE (entity_id,at) IN
                (SELECT entity_id, MAX(at) FROM observations WHERE at<? GROUP BY entity_id)
            ORDER BY at
        """, (start, end, start))
        return [Observation(row['entity_id'], row['at'], row['value'], row['reported_at']) for row in rows]

    def settle(self, result: WindowResult, revision: int, timezone: str):
        if self.db.execute("SELECT 1 FROM windows WHERE revision=? AND start=? AND end=?",
                           (revision, result.start, result.end)).fetchone():
            return
        if self.cursor != result.start:
            raise ValueError("non_contiguous_settlement")
        zone = ZoneInfo(timezone)
        with self.db:
            self.db.execute("INSERT INTO windows VALUES (?,?,?,?)",
                            (revision, result.start, result.end, json.dumps(result.public())))
            for segment in result.segments:
                left = segment.start
                while left < segment.end:
                    day = datetime.fromtimestamp(left, zone).date()
                    midnight = datetime.combine(day + timedelta(days=1), time(), zone).timestamp()
                    right = min(segment.end, midnight)
                    self.db.execute("""INSERT INTO days VALUES (?,?,?,?)
                        ON CONFLICT(timezone,day) DO UPDATE SET
                        energy_wh=energy_wh+excluded.energy_wh, valid_seconds=valid_seconds+excluded.valid_seconds""",
                        (timezone, day.isoformat(), segment.estimated_power * (right-left) / 3600, right-left))
                    left = right
            self.db.execute("UPDATE metadata SET value=CAST(value AS REAL)+? WHERE key='total_wh'",
                            (result.estimated_energy_wh,))
            self.db.execute("UPDATE metadata SET value=CAST(value AS REAL)+? WHERE key='valid_seconds'",
                            (result.valid_seconds,))
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('cursor',?)", (str(result.end),))
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('latest_window',?)", (json.dumps(result.public()),))

    def totals(self, now: float, timezone: str):
        day = datetime.fromtimestamp(now, ZoneInfo(timezone)).date().isoformat()
        row = self.db.execute("SELECT energy_wh,valid_seconds FROM days WHERE timezone=? AND day=?", (timezone, day)).fetchone()
        return {"daily_kwh": row[0] / 1000 if row else 0, "total_kwh": float(self.get_meta("total_wh")) / 1000,
                "day": day, "timezone": timezone, "daily_valid_seconds": row[1] if row else 0,
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
