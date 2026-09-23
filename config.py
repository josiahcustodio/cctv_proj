"""
Centralized Configuration Module
Contains RTSP streams, YOLO model paths, geometry coordinates, and performance caps.
"""

import os
from urllib.parse import quote
from typing import Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()


def _rtsp_url(user: str, password: str, host: str, path: str) -> str:
    """Build a properly URL-encoded RTSP URL so special chars in credentials are safe."""
    return f"rtsp://{quote(user, safe='')}:{quote(password, safe='')}@{host}{path}"

# System Hardware & Model Settings
CUDA_DEVICE: str = "cuda:0"
YOLO_MODEL_PATH: str = os.path.join(os.getcwd(), "yolov8n.pt")
TRT_ENGINE_PATH: str = os.path.join(os.getcwd(), "yolov8n.engine")
BATCH_SIZE: int = 4  # max simultaneous cameras the TensorRT engine is profiled for (see engine_builder.py)
TARGET_FPS: int = 15  # display/render cadence

# Inference runs on its own, slower cadence than the display. People counting stays
# accurate well below the display rate, and detection is by far the most expensive
# step, so decoupling the two is the cheapest large saving available.
# Raising this improves line-crossing precision for fast walkers; lowering it saves GPU.
INFERENCE_FPS: int = 10
MODEL_WIDTH: int = 640
MODEL_HEIGHT: int = 640

# RTSP Stream Endpoints
# Credentials come from .env (see .env.example) and are URL-encoded via _rtsp_url()
# so special chars (@, #, %, spaces, etc.) are safe. Never hardcode real credentials here.
_RTSP_USER: str = os.environ["CCTV_RTSP_USER"]
_RTSP_PASS: str = os.environ["CCTV_RTSP_PASS"]


def _cam_urls(host: str) -> Tuple[str, str]:
    """Return (substream_url, mainstream_url) for a standalone IP camera."""
    sub = _rtsp_url(_RTSP_USER, _RTSP_PASS, host, "/cam/realmonitor?channel=1&subtype=1")
    main = _rtsp_url(_RTSP_USER, _RTSP_PASS, host, "/cam/realmonitor?channel=1&subtype=0")
    return sub, main


# Placeholder for cameras that have no physical device yet.
# VideoWorkerThread will fail to open this URL and emit status_changed(False) cleanly.
_OFFLINE_URL: str = "rtsp://0.0.0.0:1/offline"

# Camera Assignments & Geometry Configurations
# All 4 cameras confirmed alive via RTSP test (ICMP/ping disabled on cameras)
_cam1_sub, _cam1_main = _cam_urls("192.168.1.109:554")
_cam2_sub, _cam2_main = _cam_urls("192.168.1.111:554")
_cam3_sub, _cam3_main = _cam_urls("192.168.1.112:554")
_cam4_sub, _cam4_main = _cam_urls("192.168.1.113:554")

# Default zone covering the central ~80% of frame. This is a placeholder —
# recalibrate per camera to match the actual display/shelf area in view.
_DEFAULT_ZONE_POLYGON: List[Tuple[float, float]] = [
    (0.1, 0.1), (0.9, 0.1), (0.9, 0.95), (0.1, 0.95)
]

CAMERA_CONFIGS: Dict[int, dict] = {
    1: {
        "name": "Main Entrance",
        "mode": "ENTRANCE_EXIT",
        "rtsp_url": _cam1_sub,
        "fallback_url": _cam1_main,
        "line_vector": [(0.1, 0.5), (0.9, 0.5)],
    },
    2: {
        "name": "Display Zone A",
        "mode": "AREA_DWELL",
        "rtsp_url": _cam2_sub,
        "fallback_url": _cam2_main,
        "zone_polygon": _DEFAULT_ZONE_POLYGON,
    },
    3: {
        "name": "Display Zone B",
        "mode": "AREA_DWELL",
        "rtsp_url": _cam3_sub,
        "fallback_url": _cam3_main,
        "zone_polygon": _DEFAULT_ZONE_POLYGON,
    },
    4: {
        "name": "Display Zone C",
        "mode": "AREA_DWELL",
        "rtsp_url": _cam4_sub,
        "fallback_url": _cam4_main,
        "zone_polygon": _DEFAULT_ZONE_POLYGON,
    },
}

# Analytics Thresholds
MIN_DWELL_THRESHOLD_SEC: float = 2.0  # Ignore transients under 2 seconds

# How often each zone camera persists its live "people present" count.
# Writing per frame would be ~15 rows/sec/camera of near-duplicate noise; sampling
# on an interval keeps the occupancy history chartable without bloating the DB.
ZONE_OCCUPANCY_SAMPLE_SEC: float = 15.0

# Dwell longer than this counts as genuine engagement rather than passing through.
ENGAGED_DWELL_SEC: float = 15.0
DB_FILE_PATH: str = os.path.join(os.getcwd(), "analytics.db")