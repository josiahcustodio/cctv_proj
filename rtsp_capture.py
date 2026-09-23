import os
import re
import time
import cv2
import threading
from typing import Optional, Tuple
import numpy as np
from PySide6.QtCore import QThread, Signal

# Set RTSP transport options ONCE at module level, before any threads start.
# Setting this inside threads causes race conditions since os.environ is shared.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport|tcp|stimeout|5000000"
)


def open_rtsp_stream(url: str) -> cv2.VideoCapture:
    """Open an RTSP stream. Call from the MAIN thread to avoid FFMPEG/QThread deadlocks."""
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
    return cap


def pre_connect_camera(camera_id: int, rtsp_url: str, fallback_url: str) -> Optional[cv2.VideoCapture]:
    """
    Try to open the primary and fallback RTSP URLs sequentially.
    Must be called from the main thread before spawning QThreads.
    Returns an opened VideoCapture or None.
    """
    if "0.0.0.0" in rtsp_url or "offline" in rtsp_url:
        print(f"[CAM {camera_id}] Skipping — marked offline")
        return None

    safe = re.sub(r'://[^:]+:[^@]+@', '://***:***@', rtsp_url)
    print(f"[CAM {camera_id}] Trying primary: {safe}")

    cap = open_rtsp_stream(rtsp_url)
    if cap and cap.isOpened():
        print(f"[CAM {camera_id}] PRIMARY connected OK")
        return cap
    if cap:
        cap.release()
    print(f"[CAM {camera_id}] Primary FAILED, trying fallback...")

    if "0.0.0.0" in fallback_url or "offline" in fallback_url:
        print(f"[CAM {camera_id}] No fallback (offline)")
        return None

    safe_fb = re.sub(r'://[^:]+:[^@]+@', '://***:***@', fallback_url)
    print(f"[CAM {camera_id}] Trying fallback: {safe_fb}")
    cap = open_rtsp_stream(fallback_url)
    if cap and cap.isOpened():
        print(f"[CAM {camera_id}] FALLBACK connected OK")
        return cap
    else:
        print(f"[CAM {camera_id}] Fallback FAILED too")
        if cap:
            cap.release()
        return None


class RTSPCaptureThread(QThread):
    """
    Dedicated thread for high-throughput RTSP ingestion.
    Reads frames as fast as possible and only retains the MOST RECENT frame,
    dropping any stale frames to ensure zero latency.

    The initial VideoCapture connection must be opened on the main thread
    (via pre_connect_camera) and passed in, because OpenCV's FFMPEG backend
    deadlocks when cv2.VideoCapture() is called from multiple QThreads.
    Reconnection attempts within the thread use a class-level lock to
    serialize and avoid the same issue.
    """
    # Signal emitted if stream drops or reconnects
    status_changed = Signal(int, bool)

    # Serialize reconnection attempts across all camera threads.
    _connect_lock = threading.Lock()

    def __init__(self, camera_id: int, rtsp_url: str, fallback_url: str,
                 initial_cap: Optional[cv2.VideoCapture] = None):
        super().__init__()
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.fallback_url = fallback_url
        self._initial_cap = initial_cap

        self.running = True
        self._latest_frame = None
        self._frame_seq = 0  # bumped on every decoded frame; lets consumers skip re-work
        self._lock = threading.Lock()
        self.is_connected = False

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Thread-safe getter for the most recently captured frame."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def get_frame_if_newer(self, last_seq: int) -> Optional[Tuple[np.ndarray, int]]:
        """
        Returns (frame, seq) only when a frame newer than last_seq has arrived,
        else None. A camera pushing fewer FPS than the inference loop would
        otherwise have the same frame detected and drawn over and over.
        """
        with self._lock:
            if self._latest_frame is None or self._frame_seq == last_seq:
                return None
            return self._latest_frame.copy(), self._frame_seq

    def run(self):
        """Continuous read loop."""
        # Use the pre-connected capture if available
        cap = self._initial_cap
        self._initial_cap = None  # don't hold reference

        if cap and cap.isOpened():
            self.is_connected = True
            self.status_changed.emit(self.camera_id, True)

        while self.running:
            if not cap or not cap.isOpened():
                if self.is_connected:
                    self.is_connected = False
                    self.status_changed.emit(self.camera_id, False)
                if cap:
                    cap.release()

                cap = self._reconnect_stream()
                if cap and cap.isOpened():
                    self.is_connected = True
                    self.status_changed.emit(self.camera_id, True)
                else:
                    time.sleep(2.0)
                    continue

            ret, frame = cap.read()

            if not ret or frame is None:
                if self.is_connected:
                    self.is_connected = False
                    self.status_changed.emit(self.camera_id, False)
                cap.release()
                cap = None
                time.sleep(2.0)
                continue

            # Update latest frame
            with self._lock:
                self._latest_frame = frame
                self._frame_seq += 1

        if cap:
            cap.release()

    def stop(self):
        self.running = False
        self.wait()

    def _reconnect_stream(self) -> Optional[cv2.VideoCapture]:
        """
        Attempt to reconnect. Serialized with a class-level lock to prevent
        FFMPEG deadlocks when multiple camera threads try to reconnect at once.
        """
        if "0.0.0.0" in self.rtsp_url or "offline" in self.rtsp_url:
            return None

        with RTSPCaptureThread._connect_lock:
            print(f"[CAM {self.camera_id}] Reconnecting...")
            cap = open_rtsp_stream(self.rtsp_url)
            if cap and cap.isOpened():
                print(f"[CAM {self.camera_id}] Reconnected OK (primary)")
                return cap
            if cap:
                cap.release()

            if "0.0.0.0" in self.fallback_url or "offline" in self.fallback_url:
                return None

            cap = open_rtsp_stream(self.fallback_url)
            if cap and cap.isOpened():
                print(f"[CAM {self.camera_id}] Reconnected OK (fallback)")
                return cap
            if cap:
                cap.release()
            print(f"[CAM {self.camera_id}] Reconnect FAILED")
            return None
