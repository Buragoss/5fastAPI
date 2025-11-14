import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List

class TelemetryLogger:

    def __init__(self, db_path: str = "robot_telemetry.db") -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.row_factory = sqlite3.Row  # Для dict-результатов

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:

        assert self._conn is not None
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
              id         INTEGER PRIMARY KEY,
              variant_id INTEGER NOT NULL,
              started_at TEXT NOT NULL,
              ended_at   TEXT,
              status     TEXT NOT NULL CHECK(status IN ('running','completed','error'))
            );

            CREATE TABLE IF NOT EXISTS sensor_readings (
              id          INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              sensor_type TEXT NOT NULL,
              timestamp   TEXT NOT NULL,
              value       REAL NOT NULL,
              unit        TEXT
            );

            CREATE TABLE IF NOT EXISTS actuator_commands (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              actuator_type TEXT NOT NULL,
              timestamp     TEXT NOT NULL,
              command       REAL NOT NULL,
              status        TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
              id         INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              timestamp  TEXT NOT NULL,
              event_type TEXT NOT NULL,
              severity   TEXT NOT NULL CHECK(severity IN ('info','warning','error')),
              message    TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sensor_time ON sensor_readings(session_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_actuator_time ON actuator_commands(session_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_time ON events(session_id, timestamp);
            """
        )
        self._conn.commit()

    # --- Методы для API ---
    def create_session(self, variant_id: int) -> int:

        assert self._conn is not None
        ts = datetime.utcnow().isoformat()
        cur = self._conn.execute(
            "INSERT INTO sessions(variant_id, started_at, status) VALUES (?,?,?)",
            (variant_id, ts, "running"),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:

        cur = self._conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:

        cur = self._conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cur.fetchall()]

    def end_session(self, session_id: int, status: str = "completed") -> None:

        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "UPDATE sessions SET ended_at=?, status=? WHERE id=?",
            (ts, status, session_id),
        )
        self._conn.commit()

    def log_sensor(self, session_id: int, sensor_type: str, value: float, unit: str = "") -> None:

        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO sensor_readings(session_id, sensor_type, timestamp, value, unit) VALUES (?,?,?,?,?)",
            (session_id, sensor_type, ts, value, unit),
        )
        self._conn.commit()

    def log_command(self, session_id: int, actuator_type: str, command: float, status: str = "sent") -> None:

        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO actuator_commands(session_id, actuator_type, timestamp, command, status) VALUES (?,?,?,?,?)",
            (session_id, actuator_type, ts, command, status),
        )
        self._conn.commit()

    def log_event(self, session_id: int, event_type: str, severity: str, message: str) -> None:

        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO events(session_id, timestamp, event_type, severity, message) VALUES (?,?,?,?,?)",
            (session_id, ts, event_type, severity, message),
        )
        self._conn.commit()

    def sensor_stats(self, session_id: int, sensor_type: str) -> Optional[Dict[str, Any]]:

        cur = self._conn.execute(
            "SELECT COUNT(*) AS count, AVG(value) AS avg, MIN(value) AS min, MAX(value) AS max "
            "FROM sensor_readings WHERE session_id=? AND sensor_type=?",
            (session_id, sensor_type),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_events(self, session_id: int, severity: Optional[str] = None) -> List[Dict[str, Any]]:

        if severity:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE session_id=? AND severity=? ORDER BY timestamp",
                (session_id, severity),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY timestamp",
                (session_id,),
            )
        return [dict(row) for row in cur.fetchall()]

    def list_sensor_readings(self, session_id: int, sensor_type: Optional[str] = None) -> List[Dict[str, Any]]:

        if sensor_type:
            cur = self._conn.execute(
                "SELECT id, sensor_type, timestamp, value, unit FROM sensor_readings "
                "WHERE session_id=? AND sensor_type=? ORDER BY timestamp",
                (session_id, sensor_type)
            )
        else:
            cur = self._conn.execute(
                "SELECT id, sensor_type, timestamp, value, unit FROM sensor_readings "
                "WHERE session_id=? ORDER BY timestamp",
                (session_id,)
            )
        return [dict(row) for row in cur.fetchall()]

    def list_actuator_commands(self, session_id: int, actuator_type: Optional[str] = None) -> List[Dict[str, Any]]:

        if actuator_type:
            cur = self._conn.execute(
                "SELECT id, actuator_type, timestamp, command, status FROM actuator_commands "
                "WHERE session_id=? AND actuator_type=? ORDER BY timestamp",
                (session_id, actuator_type)
            )
        else:
            cur = self._conn.execute(
                "SELECT id, actuator_type, timestamp, command, status FROM actuator_commands "
                "WHERE session_id=? ORDER BY timestamp",
                (session_id,)
            )
        return [dict(row) for row in cur.fetchall()]


db = TelemetryLogger()