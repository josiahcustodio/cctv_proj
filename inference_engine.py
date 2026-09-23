import time
import cv2
import numpy as np
from typing import Dict, List, Tuple
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import IterableSimpleNamespace, YAML
from ultralytics.utils.checks import check_yaml

from config import (
    CUDA_DEVICE, TARGET_FPS, INFERENCE_FPS,
    CAMERA_CONFIGS, MODEL_WIDTH, MODEL_HEIGHT,
    ZONE_OCCUPANCY_SAMPLE_SEC
)
from engine_builder import get_model_path
from analytics_engine import LineCrossingTracker, ZoneDwellTracker
from database import DatabaseManager
from rtsp_capture import RTSPCaptureThread

ACCENT = (0, 168, 232)  # BGR, matches the UI's cyan


class BatchedInferenceThread(QThread):
    """
    Centralized Inference Engine using TensorRT and Batched YOLO Inference.

    Each camera owns its own ByteTrack instance. Ultralytics' model.track() cannot
    provide this: it allocates one tracker per batch slot only when the source is a
    "stream", and a list of arrays is "image" mode, so every camera would share
    trackers[0] (see ultralytics/trackers/track.py). Sharing makes camera N's frame
    look like the frame immediately after camera N-1's, so tracks from every camera
    but the first almost never survive long enough to be confirmed.
    """
    frame_processed = Signal(int, QImage, dict)

    def __init__(self, capture_threads: List[RTSPCaptureThread], db_manager: DatabaseManager):
        super().__init__()
        self.capture_threads = capture_threads
        self.db = db_manager
        self.running = True

        # Initialize Analytics Trackers per camera
        self.trackers = {}
        for thread in self.capture_threads:
            cam_id = thread.camera_id
            cfg = CAMERA_CONFIGS.get(cam_id)
            if not cfg:
                continue

            mode = cfg["mode"]
            if mode == "ENTRANCE_EXIT":
                self.trackers[cam_id] = {
                    "mode": mode,
                    "tracker": LineCrossingTracker(cfg["line_vector"]),
                    "config": cfg
                }
            elif mode == "AREA_DWELL":
                self.trackers[cam_id] = {
                    "mode": mode,
                    "tracker": ZoneDwellTracker(cfg["zone_polygon"]),
                    "config": cfg
                }
            elif mode == "OCCUPANCY":
                self.trackers[cam_id] = {
                    "mode": mode,
                    "config": cfg
                }

        # Temporal smoothing buffers (Exponential Moving Average / count history)
        self.occupancy_history = {thread.camera_id: [] for thread in self.capture_threads}
        self.smooth_window = 5 # frames

        # Last time each camera persisted its zone occupancy, so the sampled write
        # fires on an interval instead of once per processed frame.
        self.last_occupancy_log = {thread.camera_id: 0.0 for thread in self.capture_threads}

        # Per-camera state carried between ticks. Rendering runs faster than
        # inference, so display-only ticks reuse the most recent boxes and metrics.
        self.last_seq: Dict[int, int] = {t.camera_id: -1 for t in self.capture_threads}
        self.cached_boxes: Dict[int, List[Tuple[int, Tuple[int, int, int, int]]]] = {
            t.camera_id: [] for t in self.capture_threads
        }
        self.last_metrics: Dict[int, dict] = {t.camera_id: {} for t in self.capture_threads}

    def run(self):
        # get_model_path() returns the TensorRT engine when one was built, and the
        # .pt weights otherwise, so a missing/failed engine degrades to PyTorch
        # inference instead of crashing the worker thread.
        model_path = get_model_path()
        print(f"[INFO] Initializing inference on {CUDA_DEVICE} with {model_path}...")
        model = YOLO(model_path, task='detect')

        tracker_cfg = IterableSimpleNamespace(**YAML.load(check_yaml("bytetrack.yaml")))
        byte_trackers = {
            t.camera_id: BYTETracker(args=tracker_cfg) for t in self.capture_threads
        }

        display_interval = 1.0 / TARGET_FPS
        inference_interval = 1.0 / INFERENCE_FPS
        last_inference = 0.0

        while self.running:
            start_time = time.time()

            # 1. Collect only cameras that produced a frame we have not handled yet.
            # Offline cameras contribute nothing rather than a blank placeholder, so
            # the dynamic-batch engine only ever runs over real pixels.
            batch: List[np.ndarray] = []
            batch_ids: List[int] = []
            for thread in self.capture_threads:
                fetched = thread.get_frame_if_newer(self.last_seq.get(thread.camera_id, -1))
                if fetched is None:
                    continue
                frame, seq = fetched
                self.last_seq[thread.camera_id] = seq
                batch.append(frame)
                batch_ids.append(thread.camera_id)

            if not batch:
                time.sleep(0.005)
                continue

            # 2. Detection + tracking, on the slower inference cadence.
            now = time.time()
            ran_inference = (now - last_inference) >= inference_interval
            if ran_inference:
                last_inference = now
                results = model.predict(
                    source=batch,
                    device=CUDA_DEVICE,
                    classes=[0], # Person class only
                    verbose=False,
                    imgsz=(MODEL_HEIGHT, MODEL_WIDTH),
                )

                for result, frame, cam_id in zip(results, batch, batch_ids):
                    # ByteTrack rows are [x1, y1, x2, y2, track_id, conf, cls, idx].
                    tracks = byte_trackers[cam_id].update(result.boxes.cpu().numpy(), frame)
                    self.cached_boxes[cam_id] = [
                        (int(t[4]), (int(t[0]), int(t[1]), int(t[2]), int(t[3])))
                        for t in tracks
                    ]

            # 3. Analytics (inference ticks only) and rendering (every tick).
            for frame, cam_id in zip(batch, batch_ids):
                h, w = frame.shape[:2]
                boxes = self.cached_boxes.get(cam_id, [])
                detections = [
                    (track_id, ((x1 + x2) // 2, (y1 + y2) // 2))
                    for track_id, (x1, y1, x2, y2) in boxes
                ]

                if ran_inference:
                    metrics = self._process_analytics(cam_id, (h, w), detections)
                    self.last_metrics[cam_id] = metrics

                    if "people_present" in metrics:
                        if (now - self.last_occupancy_log.get(cam_id, 0.0)) >= ZONE_OCCUPANCY_SAMPLE_SEC:
                            self.last_occupancy_log[cam_id] = now
                            self.db.log_zone_occupancy(cam_id, metrics["people_present"])
                else:
                    metrics = self.last_metrics.get(cam_id, {})

                self._render(cam_id, frame, boxes, detections, metrics)

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                qimg = QImage(
                    rgb_frame.data, w, h, w * 3, QImage.Format_RGB888
                ).copy()

                self.frame_processed.emit(cam_id, qimg, metrics)

            # Throttling
            elapsed = time.time() - start_time
            sleep_time = max(0.0, display_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _process_analytics(self, cam_id: int, shape: Tuple[int, int], detections) -> dict:
        """Advances per-camera analytics state and writes events. Does no drawing."""
        h, w = shape
        metrics: dict = {}
        tracker_info = self.trackers.get(cam_id)
        if not tracker_info:
            return metrics

        mode = tracker_info["mode"]
        if mode == "ENTRANCE_EXIT":
            events = tracker_info["tracker"].process_frame((h, w), detections)
            for direction, track_id in events:
                self.db.log_line_crossing(cam_id, direction, track_id)

        elif mode == "AREA_DWELL":
            active_dwells, completed = tracker_info["tracker"].process_frame((h, w), detections)
            for track_id, duration in completed:
                self.db.log_dwell_time(cam_id, track_id, duration)
            metrics["people_present"] = len(active_dwells)

        elif mode == "OCCUPANCY":
            # Temporal smoothing (Median Filter)
            hist = self.occupancy_history[cam_id]
            hist.append(len(detections))
            if len(hist) > self.smooth_window:
                hist.pop(0)
            metrics["people_present"] = int(np.median(hist))

        return metrics

    def _render(self, cam_id: int, frame: np.ndarray, boxes, detections, metrics: dict):
        """Draws boxes, zone/line geometry and counters onto the frame, in place."""
        h, w = frame.shape[:2]

        for track_id, (x1, y1, x2, y2) in boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), ACCENT, 2, cv2.LINE_AA)
            cv2.putText(
                frame, f"#{track_id}", (x1, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, ACCENT, 1, cv2.LINE_AA
            )

        tracker_info = self.trackers.get(cam_id)
        if not tracker_info:
            return

        mode = tracker_info["mode"]
        cfg = tracker_info["config"]

        if mode == "ENTRANCE_EXIT":
            p1 = (int(cfg["line_vector"][0][0] * w), int(cfg["line_vector"][0][1] * h))
            p2 = (int(cfg["line_vector"][1][0] * w), int(cfg["line_vector"][1][1] * h))
            cv2.line(frame, p1, p2, (0, 255, 255), 3, cv2.LINE_AA)
            for _track_id, (cx, cy) in detections:
                cv2.circle(frame, (cx, cy), 5, (0, 255, 100), -1, cv2.LINE_AA)

        elif mode == "AREA_DWELL":
            poly_pts = np.array(
                [[int(x * w), int(y * h)] for x, y in cfg["zone_polygon"]],
                dtype=np.int32,
            )
            overlay = frame.copy()
            cv2.fillPoly(overlay, [poly_pts], ACCENT)
            cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
            cv2.polylines(frame, [poly_pts], True, ACCENT, 2, cv2.LINE_AA)

        if "people_present" in metrics:
            cv2.putText(
                frame, f"PEOPLE PRESENT: {metrics['people_present']}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3, cv2.LINE_AA
            )

    def stop(self):
        self.running = False
        self.wait()
