
import sqlite3
from datetime import datetime
import random
from typing import Optional
import requests

class TelemetryLogger:
    def __init__(self, db_path: str = "robot_telemetry.db") -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self.session_id: Optional[int] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON;")

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

            CREATE TABLE IF NOT EXISTS sensor_readings  (
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
            """
        )
        self._conn.commit()

    def start_session(self, variant_id: int) -> int:
        assert self._conn is not None
        ts = datetime.utcnow().isoformat()
        cur = self._conn.execute(
            "INSERT INTO sessions(variant_id, started_at, status) VALUES (?,?,?)",
            (variant_id, ts, "running"),
        )
        self._conn.commit()
        self.session_id = cur.lastrowid
        return self.session_id

    def end_session(self, status: str = "completed") -> None:
        assert self._conn is not None and self.session_id is not None
        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "UPDATE sessions SET ended_at=?, status=? WHERE id=?",
            (ts, status, self.session_id),
        )
        self._conn.commit()

    def log_sensor(self, sensor_type: str, value: float, unit: str = "v") -> None:
        assert self._conn is not None and self.session_id is not None
        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO sensor_readings(session_id, sensor_type, timestamp, value, unit) VALUES (?,?,?,?,?)",
            (self.session_id, sensor_type, ts, value, unit),
        )
        self._conn.commit()

    def log_command(self, actuator_type: str, command: float, status: str = "sent") -> None:
        assert self._conn is not None and self.session_id is not None
        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO actuator_commands(session_id, actuator_type, timestamp, command, status) VALUES (?,?,?,?,?)",
            (self.session_id, actuator_type, ts, command, status),
        )
        self._conn.commit()

    def log_event(self, event_type: str, severity: str, message: str) -> None:
        assert self._conn is not None and self.session_id is not None
        ts = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO events(session_id, timestamp, event_type, severity, message) VALUES (?,?,?,?,?)",
            (self.session_id, ts, event_type, severity, message),
        )
        self._conn.commit()

VARIANT_ID: int = 1

BASE = "http://127.0.0.1:8000" 
HTTP_TIMEOUT = 0.8

telemetry = TelemetryLogger("robot_telemetry.db")
telemetry.connect()
telemetry.init_schema()

class PIDController:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.prev_error = 0
        self.integral = 0

    def update(self, error, dt=0.1):
        self.integral += error * dt
        derivative = (error - self.prev_error) / dt
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        self.prev_error = error
        return max(-1, min(1, output))

class IRLineSensor:
    def __init__(self, n_sensors):
        self.n = n_sensors
        self.white = [1.0] * n_sensors
        self.black = [0.0] * n_sensors

    def calibrate(self, white_levels, black_levels):
        print("\nКалибровка")
        for i in range(self.n):
            noise_w = random.uniform(-0.05, 0)
            noise_b = random.uniform(0, 0.05)
            self.white[i] = min(1.0, max(0.0, white_levels[i] + noise_w))
            self.black[i] = min(1.0, max(0.0, black_levels[i] + noise_b))
            print(f"  Датчик {i+1}: белый={self.white[i]:.2f}, чёрный={self.black[i]:.2f}")

    def read_normalized(self, raw_values):
        result = []
        for i in range(self.n):
            w, b = self.white[i], self.black[i]
            value = (raw_values[i] - b) / (w - b + 1e-6)
            result.append(max(0.0, min(1.0, value)))
        return result

class MotorPair:
    def drive(self, base_speed, diff):
        left = max(-1, min(1, base_speed - diff))
        right = max(-1, min(1, base_speed + diff))
        print(f"   Моторы: L = {left:+.2f}, R = {right:+.2f}")
        telemetry.log_command("Motor_L", left)
        telemetry.log_command("Motor_R", right)
        return left, right

class TrackState:
    def update(self, normalized_values):
        avg = sum(normalized_values) / len(normalized_values)
        return 0.2 <= avg <= 0.8

def http_create_session():
    try:
        r = requests.post(f"{BASE}/sessions", json={"variant_id": VARIANT_ID}, timeout=HTTP_TIMEOUT)
        if r.ok:
            return r.json()["id"]
    except Exception as e:
        return None

def http_log_sensor(sid, sensor_type, value, unit=""):
    if sid is None:
        return
    try:
        requests.post(f"{BASE}/sessions/{sid}/sensors",
                      json={"sensor_type": sensor_type, "value": float(value), "unit": unit},
                      timeout=HTTP_TIMEOUT)
    except Exception:
        pass

def http_log_actuator(sid, actuator_type, command, status="sent"):
    if sid is None:
        return
    try:
        requests.post(f"{BASE}/sessions/{sid}/actuators",
                      json={"actuator_type": actuator_type, "command": float(command), "status": status},
                      timeout=HTTP_TIMEOUT)
    except Exception:
        pass

def http_log_event(sid, event_type, severity, message):
    if sid is None:
        return
    try:
        requests.post(f"{BASE}/sessions/{sid}/events",
                      json={"event_type": event_type, "severity": severity, "message": message},
                      timeout=HTTP_TIMEOUT)
    except Exception:
        pass

def http_end_session(sid, status="completed"):
    if sid is None:
        return
    try:
        requests.post(f"{BASE}/sessions/{sid}/end", json={"status": status}, timeout=HTTP_TIMEOUT)
    except Exception:
        pass

class LineFollowerRobot:
    def __init__(self, n_sensors=5):
        self.sensor = IRLineSensor(n_sensors)
        self.pid = PIDController(0.8, 0.0, 0.2)
        self.motors = MotorPair()
        self.track = TrackState()

    def calibrate(self):
        telemetry.start_session(VARIANT_ID)
        white = [1.0] * self.sensor.n
        black = [0.0] * self.sensor.n
        self.sensor.calibrate(white, black)
        telemetry.log_event("calibration", "info", "Калибровка завершена")
        telemetry.end_session("completed")

    def follow_line(self, measurements, label):
        session_id = telemetry.start_session(VARIANT_ID)
        remote_session_id = http_create_session()
        if remote_session_id is None:
            telemetry.log_event("server", "warning", "Не удалось подключиться к серверу телеметрии; записи будут только локально")
        else:
            http_log_event(remote_session_id, "scenario_start", "info", f"Начало сценария: {label}")

        telemetry.log_event("scenario_start_local", "info", f"Начало сценария локально: {label}")

        on_track_count = 0
        off_track_count = 0

        try:
            for step, raw in enumerate(measurements, 1):
                noisy = [max(0, min(1, v + random.uniform(-0.05, 0.05))) for v in raw]
                norm = self.sensor.read_normalized(noisy)

                for i, val in enumerate(norm):
                    name = f"IR_{i+1}"
                    telemetry.log_sensor(name, val, unit='норм')
                    http_log_sensor(remote_session_id, name, val, unit='норм')

                position = sum((i - (self.sensor.n - 1)/2) * (1 - norm[i]) for i in range(self.sensor.n))
                error = position / ((self.sensor.n - 1)/2) if (self.sensor.n - 1) != 0 else 0.0
                pid_out = self.pid.update(error)

                on_track = self.track.update(norm)
                state = "на линии" if on_track else "убежал"
                if on_track:
                    on_track_count += 1
                else:
                    off_track_count += 1
                    telemetry.log_event("line_tracking", "warning", f"Сошёл с линии на шаге {step}")
                    http_log_event(remote_session_id, "line_tracking", "warning", f"Сошёл с линии на шаге {step}")

                line = self._make_line(error)
                print(f"\nШаг {step}: {state}")
                print(f"  Сенсоры: {[f'{v:.2f}' for v in norm]}")
                print(f"  Ошибка={error:+.2f}, PID={pid_out:+.2f}")
                print(f"  Линия:  {line}")

                left, right = self.motors.drive(0.5, pid_out)

                http_log_actuator(remote_session_id, "Motor_L", left)
                http_log_actuator(remote_session_id, "Motor_R", right)

            print("\nИТОГ СЦЕНАРИЯ:")
            print(f"  На линии: {on_track_count} шагов")
            print(f"  Сошёл:    {off_track_count} шагов")

            telemetry.log_event("scenario_end", "info", f"Сценарий завершён. Сошёл {off_track_count} раз(а).")
            http_log_event(remote_session_id, "scenario_end", "info", f"Сценарий завершён. Сошёл {off_track_count} раз(а).")

            telemetry.end_session("completed")
            http_end_session(remote_session_id, "completed")
        except Exception as e:
            telemetry.log_event("exception", "error", f"Ошибка сценария: {e}")
            http_log_event(remote_session_id, "exception", "error", f"Ошибка сценария: {e}")
            telemetry.end_session("error")
            http_end_session(remote_session_id, "error")

    def _make_line(self, error):
        scale = 9
        center = scale // 2
        offset = int(center + error * center)
        offset = max(0, min(scale - 1, offset))
        line = [" "] * scale
        line[offset] = "|"
        return "".join(line)



if __name__ == "__main__":
    robot = LineFollowerRobot(n_sensors=5)

    # SCN-1A — калибровка
    robot.calibrate()

    # SCN-1B — удержание (нормальное)
    measurements_normal = [
        [0.9, 0.6, 0.2, 0.6, 0.9],
        [0.85, 0.55, 0.25, 0.55, 0.85],
        [0.8, 0.5, 0.3, 0.5, 0.8],
        [0.9, 0.5, 0.25, 0.5, 0.9],
        [0.85, 0.55, 0.3, 0.55, 0.85],
        [0.8, 0.5, 0.25, 0.5, 0.8],
        [0.85, 0.55, 0.25, 0.55, 0.85],
        [0.9, 0.6, 0.2, 0.6, 0.9],
        [0.9, 0.55, 0.25, 0.55, 0.9],
        [0.85, 0.5, 0.3, 0.5, 0.85],
    ]
    robot.follow_line(measurements_normal, "Робот идёт по линии")

    # SCN-1B — сход с линии
    measurements_offline = [
        [0.9, 0.6, 0.2, 0.6, 0.9],
        [0.85, 0.55, 0.25, 0.55, 0.85],
        [0.8, 0.5, 0.3, 0.5, 0.8],
        [0.9, 0.5, 0.25, 0.5, 0.9],
        [0.6, 0.3, 0.2, 0.7, 0.9],
        [0.5, 0.25, 0.2, 0.8, 0.95],
        [0.4, 0.2, 0.2, 0.9, 1.0],
        [0.3, 0.15, 0.25, 0.95, 1.0],
        [0.9, 0.9, 0.9, 0.9, 0.9],
        [0.95, 0.95, 0.95, 0.95, 0.95],
    ]
    robot.follow_line(measurements_offline, "Робот сходит с линии")

    telemetry.close()
