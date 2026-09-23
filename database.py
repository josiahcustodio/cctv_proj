"""
Thread-Safe SQLite Database Manager
Handles event logging for line crossings, zone dwell times, and sampled zone
occupancy, plus the aggregation queries backing the Analytics tab.
"""

import queue
import sqlite3
import threading
from typing import Dict, List, Tuple
from config import DB_FILE_PATH


class DatabaseManager:
    def __init__(self, db_path: str = DB_FILE_PATH):
        self.db_path = db_path
        self._init_db()

        # Single persistent writer thread + queue: avoids spawning an OS thread and
        # opening a fresh connection for every individual crossing/dwell event, and
        # keeps writes in the order they were queued.
        self._write_queue: "queue.Queue" = queue.Queue()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")  # Write-Ahead Logging for concurrency
        return conn

    def _init_db(self):
        """Creates necessary tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Line Crossing Events Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS line_crossings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    camera_id INTEGER NOT NULL,
                    direction TEXT CHECK(direction IN ('IN', 'OUT')),
                    track_id INTEGER NOT NULL
                )
            """)
            # Zone Dwell Events Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS zone_dwells (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    camera_id INTEGER NOT NULL,
                    track_id INTEGER NOT NULL,
                    dwell_time_seconds REAL NOT NULL
                )
            """)
            # Sampled Zone Occupancy Table.
            # The live "people present" count is otherwise discarded every frame, so
            # without this there is no way to chart how busy an area was over time.
            # Written on an interval (ZONE_OCCUPANCY_SAMPLE_SEC), never per frame.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS zone_occupancy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    camera_id INTEGER NOT NULL,
                    people_count INTEGER NOT NULL
                )
            """)
            # Date-range filtering drives every analytics query; without these the
            # charts do a full table scan on each redraw.
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cross_ts ON line_crossings(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dwell_ts ON zone_dwells(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_occ_ts ON zone_occupancy(timestamp)")
            conn.commit()

    def _writer_loop(self):
        """Runs on the dedicated writer thread; owns the only write connection."""
        conn = self._get_connection()
        while True:
            sql, params, label = self._write_queue.get()
            try:
                conn.execute(sql, params)
                conn.commit()
                if label:
                    print(label)
            except Exception as e:
                print(f"[DB ERROR] write failed: {e}")

    # ----------------------------------------------------------------- writes

    def log_line_crossing(self, camera_id: int, direction: str, track_id: int):
        """Queues an IN/OUT event for the writer thread."""
        camera_id = int(camera_id)
        track_id = int(track_id)
        self._write_queue.put((
            "INSERT INTO line_crossings (camera_id, direction, track_id) VALUES (?, ?, ?)",
            (camera_id, direction, track_id),
            f"[DB] Logged crossing: Cam {camera_id} | {direction} | ID {track_id}",
        ))

    def log_dwell_time(self, camera_id: int, track_id: int, dwell_seconds: float):
        """Queues a zone-dwell-duration event for the writer thread."""
        camera_id = int(camera_id)
        track_id = int(track_id)
        self._write_queue.put((
            "INSERT INTO zone_dwells (camera_id, track_id, dwell_time_seconds) VALUES (?, ?, ?)",
            (camera_id, track_id, round(dwell_seconds, 2)),
            None,
        ))

    def log_zone_occupancy(self, camera_id: int, people_count: int):
        """Queues a sampled 'how many people are in this zone right now' reading."""
        self._write_queue.put((
            "INSERT INTO zone_occupancy (camera_id, people_count) VALUES (?, ?)",
            (int(camera_id), int(people_count)),
            None,
        ))

    # ------------------------------------------------------------------ reads

    def _query(self, sql: str, params: tuple = ()) -> List[tuple]:
        """Runs a read-only query on its own connection; returns [] on failure."""
        try:
            with self._get_connection() as conn:
                return conn.execute(sql, params).fetchall()
        except Exception as e:
            print(f"[DB ERROR] query failed: {e}")
            return []

    def get_today_summary(self) -> Dict[str, float]:
        """Retrieves aggregated metrics for the current calendar day."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Convert UTC timestamps to local time before checking the date!
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN direction = 'IN' THEN 1 ELSE 0 END) as total_in,
                        SUM(CASE WHEN direction = 'OUT' THEN 1 ELSE 0 END) as total_out
                    FROM line_crossings
                    WHERE date(timestamp, 'localtime') = date('now', 'localtime')
                """)
                row = cursor.fetchone()
                total_in = row[0] if row and row[0] is not None else 0
                total_out = row[1] if row and row[1] is not None else 0

                cursor.execute("""
                    SELECT AVG(dwell_time_seconds)
                    FROM zone_dwells
                    WHERE date(timestamp, 'localtime') = date('now', 'localtime')
                """)
                avg_dwell_row = cursor.fetchone()
                avg_dwell = avg_dwell_row[0] if avg_dwell_row and avg_dwell_row[0] is not None else 0.0

                occupancy = max(0, total_in - total_out)

                return {
                    "total_in": total_in,
                    "total_out": total_out,
                    "occupancy": occupancy,
                    "avg_dwell": round(avg_dwell, 1)
                }
        except Exception as e:
            print(f"[DB ERROR] get_today_summary failed: {e}")
            return {"total_in": 0, "total_out": 0, "occupancy": 0, "avg_dwell": 0.0}

    # Every range query below takes inclusive local-date bounds as YYYY-MM-DD strings.

    def get_range_summary(self, start: str, end: str) -> Dict[str, float]:
        """KPI headline numbers for a date range."""
        rows = self._query("""
            SELECT
                SUM(CASE WHEN direction = 'IN' THEN 1 ELSE 0 END),
                SUM(CASE WHEN direction = 'OUT' THEN 1 ELSE 0 END),
                COUNT(DISTINCT date(timestamp, 'localtime'))
            FROM line_crossings
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
        """, (start, end))
        total_in = rows[0][0] if rows and rows[0][0] is not None else 0
        total_out = rows[0][1] if rows and rows[0][1] is not None else 0
        active_days = rows[0][2] if rows and rows[0][2] is not None else 0

        dwell = self._query("""
            SELECT AVG(dwell_time_seconds), COUNT(*), MAX(dwell_time_seconds)
            FROM zone_dwells
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
        """, (start, end))
        avg_dwell = dwell[0][0] if dwell and dwell[0][0] is not None else 0.0
        dwell_count = dwell[0][1] if dwell and dwell[0][1] is not None else 0
        max_dwell = dwell[0][2] if dwell and dwell[0][2] is not None else 0.0

        peak = self._query("""
            SELECT strftime('%H', timestamp, 'localtime') hr, COUNT(*) c
            FROM line_crossings
            WHERE direction = 'IN' AND date(timestamp, 'localtime') BETWEEN ? AND ?
            GROUP BY hr ORDER BY c DESC LIMIT 1
        """, (start, end))
        peak_hour = peak[0][0] if peak else None

        busiest = self._query("""
            SELECT camera_id, AVG(dwell_time_seconds) a
            FROM zone_dwells
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
            GROUP BY camera_id ORDER BY a DESC LIMIT 1
        """, (start, end))
        busiest_zone = busiest[0][0] if busiest else None

        return {
            "total_in": total_in,
            "total_out": total_out,
            "active_days": active_days,
            "avg_per_day": round(total_in / active_days, 1) if active_days else 0.0,
            "avg_dwell": round(avg_dwell, 1),
            "max_dwell": round(max_dwell, 1),
            "dwell_count": dwell_count,
            "peak_hour": peak_hour,
            "busiest_zone": busiest_zone,
        }

    def get_hourly_footfall(self, start: str, end: str) -> List[Tuple[int, int, int]]:
        """[(hour, in_count, out_count)] aggregated across the range."""
        rows = self._query("""
            SELECT CAST(strftime('%H', timestamp, 'localtime') AS INTEGER) hr,
                   SUM(CASE WHEN direction = 'IN' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN direction = 'OUT' THEN 1 ELSE 0 END)
            FROM line_crossings
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
            GROUP BY hr ORDER BY hr
        """, (start, end))
        return [(int(r[0]), int(r[1] or 0), int(r[2] or 0)) for r in rows]

    def get_daily_traffic(self, start: str, end: str) -> List[Tuple[str, int, int]]:
        """[(date, in_count, out_count)] one row per day that has activity."""
        rows = self._query("""
            SELECT date(timestamp, 'localtime') d,
                   SUM(CASE WHEN direction = 'IN' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN direction = 'OUT' THEN 1 ELSE 0 END)
            FROM line_crossings
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
            GROUP BY d ORDER BY d
        """, (start, end))
        return [(r[0], int(r[1] or 0), int(r[2] or 0)) for r in rows]

    def get_dwell_by_zone(self, start: str, end: str) -> List[Tuple[int, float, int]]:
        """[(camera_id, avg_dwell_seconds, visit_count)] per zone camera."""
        rows = self._query("""
            SELECT camera_id, AVG(dwell_time_seconds), COUNT(*)
            FROM zone_dwells
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
            GROUP BY camera_id ORDER BY camera_id
        """, (start, end))
        return [(int(r[0]), float(r[1] or 0.0), int(r[2] or 0)) for r in rows]

    def get_dwell_durations(self, start: str, end: str) -> List[float]:
        """Raw dwell durations, for the distribution histogram."""
        rows = self._query("""
            SELECT dwell_time_seconds FROM zone_dwells
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
        """, (start, end))
        return [float(r[0]) for r in rows]

    def get_zone_occupancy_series(self, start: str, end: str) -> Dict[int, List[Tuple[str, float]]]:
        """
        {camera_id: [(HH:MM bucket, avg_people)]} averaged into 15-minute buckets,
        so a multi-day range stays readable instead of plotting every raw sample.
        """
        rows = self._query("""
            SELECT camera_id,
                   strftime('%H', timestamp, 'localtime') hr,
                   (CAST(strftime('%M', timestamp, 'localtime') AS INTEGER) / 15) * 15 mins,
                   AVG(people_count)
            FROM zone_occupancy
            WHERE date(timestamp, 'localtime') BETWEEN ? AND ?
            GROUP BY camera_id, hr, mins
            ORDER BY camera_id, hr, mins
        """, (start, end))
        series: Dict[int, List[Tuple[str, float]]] = {}
        for cam_id, hr, mins, avg in rows:
            series.setdefault(int(cam_id), []).append((f"{hr}:{int(mins):02d}", float(avg or 0.0)))
        return series

    def get_dow_hour_matrix(self, start: str, end: str) -> List[List[int]]:
        """7x24 matrix of entry counts indexed [weekday][hour], Monday first."""
        rows = self._query("""
            SELECT CAST(strftime('%w', timestamp, 'localtime') AS INTEGER) dow,
                   CAST(strftime('%H', timestamp, 'localtime') AS INTEGER) hr,
                   COUNT(*)
            FROM line_crossings
            WHERE direction = 'IN' AND date(timestamp, 'localtime') BETWEEN ? AND ?
            GROUP BY dow, hr
        """, (start, end))
        matrix = [[0] * 24 for _ in range(7)]
        for dow, hr, count in rows:
            # SQLite's %w is Sunday=0; shift so the chart reads Monday-first.
            matrix[(int(dow) + 6) % 7][int(hr)] = int(count)
        return matrix

    def get_available_date_range(self) -> Tuple[str, str]:
        """(earliest, latest) local dates holding any data; ('', '') when empty."""
        rows = self._query("""
            SELECT MIN(d), MAX(d) FROM (
                SELECT date(timestamp, 'localtime') d FROM line_crossings
                UNION ALL
                SELECT date(timestamp, 'localtime') d FROM zone_dwells
                UNION ALL
                SELECT date(timestamp, 'localtime') d FROM zone_occupancy
            )
        """)
        if rows and rows[0][0]:
            return rows[0][0], rows[0][1]
        return "", ""
