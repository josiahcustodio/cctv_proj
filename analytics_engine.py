import time
import numpy as np
from typing import Dict, List, Tuple
import cv2

# Per-track cooldown: prevents the SAME person's detection jitter near the line from
# double-firing, without suppressing a second, different person crossing moments later.
CROSSING_COOLDOWN_SEC = 1.5

# Track ids not seen for this long are assumed gone; drop their bookkeeping so the
# per-camera dicts don't grow unbounded over a long-running session.
STALE_TRACK_TIMEOUT_SEC = 300.0


def _signed_side(point: np.ndarray, p1: np.ndarray, line_vec: np.ndarray) -> float:
    # Manual 2D cross product: (line_vec.x * diff.y) - (line_vec.y * diff.x)
    # np.cross on 2D vectors was deprecated/broken in newer NumPy versions.
    diff = point - p1
    return float(line_vec[0] * diff[1] - line_vec[1] * diff[0])


class LineCrossingTracker:
    """
    Tracks IN/OUT line crossings using persistent tracker IDs (from YOLO's
    built-in tracker) instead of frame-to-frame nearest-neighbor matching.
    Each track's side-of-line is remembered independently, so simultaneous
    crossings by different people are never suppressed by one another.
    """

    def __init__(self, line_normalized: List[Tuple[float, float]]):
        self.line_norm = line_normalized
        self.track_sides: Dict[int, int] = {}
        self.last_crossing_time: Dict[int, float] = {}
        self.last_seen: Dict[int, float] = {}

    def process_frame(
        self, frame_shape: Tuple[int, int], detections: List[Tuple[int, Tuple[int, int]]]
    ) -> List[Tuple[str, int]]:
        """detections: list of (track_id, centroid). Returns list of (direction, track_id)."""
        h, w = frame_shape[:2]
        p1 = np.array([self.line_norm[0][0] * w, self.line_norm[0][1] * h], dtype=float)
        p2 = np.array([self.line_norm[1][0] * w, self.line_norm[1][1] * h], dtype=float)
        line_vec = p2 - p1

        events: List[Tuple[str, int]] = []
        now = time.time()
        seen_ids = set()

        for track_id, centroid in detections:
            seen_ids.add(track_id)
            pos = np.array(centroid, dtype=float)
            side = 1 if _signed_side(pos, p1, line_vec) > 0 else -1

            prev_side = self.track_sides.get(track_id)
            crossed = prev_side is not None and side != prev_side
            suppressed = False

            if crossed:
                last_cross = self.last_crossing_time.get(track_id, 0.0)
                if (now - last_cross) > CROSSING_COOLDOWN_SEC:
                    self.last_crossing_time[track_id] = now
                    direction = "IN" if side > 0 else "OUT"
                    events.append((direction, track_id))
                else:
                    suppressed = True

            # A cooldown-suppressed crossing must NOT advance the remembered side.
            # Advancing it would "accept" a crossing we never logged, so the next
            # genuine flip back reports the same direction twice in a row (IN, IN)
            # and the running IN/OUT totals drift permanently out of balance.
            if not suppressed:
                self.track_sides[track_id] = side
            self.last_seen[track_id] = now

        stale_ids = [
            tid for tid, ts in self.last_seen.items()
            if tid not in seen_ids and (now - ts) > STALE_TRACK_TIMEOUT_SEC
        ]
        for tid in stale_ids:
            self.track_sides.pop(tid, None)
            self.last_crossing_time.pop(tid, None)
            self.last_seen.pop(tid, None)

        return events


class ZoneDwellTracker:
    """
    Tracks how long each persistent track ID stays inside a zone polygon.
    Keyed by track ID rather than nearest-neighbor position matching, so a
    brief occlusion doesn't fragment one visit into several short ones.
    """

    def __init__(self, polygon_normalized: List[Tuple[float, float]], min_dwell_sec: float = 2.0):
        self.poly_norm = polygon_normalized
        self.min_dwell_sec = min_dwell_sec
        self.active_dwells: Dict[int, float] = {}  # track_id -> entry_timestamp

    def process_frame(
        self, frame_shape: Tuple[int, int], detections: List[Tuple[int, Tuple[int, int]]]
    ) -> Tuple[List[float], List[Tuple[int, float]]]:
        """
        detections: list of (track_id, centroid).
        Returns (current_durations_for_people_still_inside, completed_events as (track_id, duration)).
        """
        h, w = frame_shape[:2]
        poly_pts = np.array(
            [[int(x * w), int(y * h)] for x, y in self.poly_norm], dtype=np.int32
        )

        now = time.time()
        inside_ids = set()

        for track_id, centroid in detections:
            if cv2.pointPolygonTest(poly_pts, (float(centroid[0]), float(centroid[1])), False) >= 0:
                inside_ids.add(track_id)
                if track_id not in self.active_dwells:
                    self.active_dwells[track_id] = now

        completed_events: List[Tuple[int, float]] = []
        for track_id in list(self.active_dwells.keys()):
            if track_id not in inside_ids:
                entry_time = self.active_dwells.pop(track_id)
                duration = now - entry_time
                if duration >= self.min_dwell_sec:
                    completed_events.append((track_id, duration))

        current_durations = [now - t for t in self.active_dwells.values()]
        return current_durations, completed_events