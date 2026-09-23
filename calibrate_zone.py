"""
Interactive calibration tool for line_vector / zone_polygon coordinates.

Grabs a single frame from a configured camera (by ID) or an arbitrary source
(RTSP URL / video file), lets you click points on it, and prints normalized
(x, y) coordinates ready to paste into CAMERA_CONFIGS in config.py.

Usage:
    python calibrate_zone.py --cam 1 --mode line        # 2 points, for ENTRANCE_EXIT
    python calibrate_zone.py --cam 2 --mode polygon      # 3+ points, for AREA_DWELL
    python calibrate_zone.py --source path/to/video.mp4 --mode polygon

Controls:
    Left click   - add a point
    Right click  - undo last point
    Enter / S    - print normalized coordinates + save a snapshot PNG next to this script
    Q / Esc      - quit without saving
"""
import argparse
import sys

import cv2
import numpy as np

from config import CAMERA_CONFIGS

WINDOW_NAME = "Calibration - click points, Enter to save, Q to quit"


def grab_frame(source: str, fallback: str = None) -> np.ndarray:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened() and fallback:
        cap.release()
        cap = cv2.VideoCapture(fallback)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source: {source}")
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise RuntimeError("Opened source but failed to read a frame")
    return frame


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cam", type=int, help="Camera ID from config.py CAMERA_CONFIGS")
    parser.add_argument("--source", type=str, help="Raw RTSP URL or video file path")
    parser.add_argument("--mode", choices=["line", "polygon"], required=True)
    args = parser.parse_args()

    if args.cam is not None:
        cfg = CAMERA_CONFIGS.get(args.cam)
        if not cfg:
            sys.exit(f"No camera {args.cam} in CAMERA_CONFIGS")
        frame = grab_frame(cfg["rtsp_url"], cfg.get("fallback_url"))
        label = f"Cam {args.cam}: {cfg['name']}"
    elif args.source:
        frame = grab_frame(args.source)
        label = args.source
    else:
        sys.exit("Pass --cam <id> or --source <url/path>")

    h, w = frame.shape[:2]
    max_points = 2 if args.mode == "line" else None
    points = []

    def on_mouse(event, x, y, flags, userdata):
        if event == cv2.EVENT_LBUTTONDOWN:
            if max_points is None or len(points) < max_points:
                points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN and points:
            points.pop()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse)

    print(f"Calibrating {label} ({w}x{h}) in '{args.mode}' mode.")
    print("Left click to add points, right click to undo, Enter/S to save, Q/Esc to quit.")

    while True:
        display = frame.copy()
        for i, (px, py) in enumerate(points):
            cv2.circle(display, (px, py), 6, (0, 255, 100), -1, cv2.LINE_AA)
            cv2.putText(
                display, str(i), (px + 8, py - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 100), 2, cv2.LINE_AA
            )
        if args.mode == "line" and len(points) == 2:
            cv2.line(display, points[0], points[1], (0, 255, 255), 2, cv2.LINE_AA)
        elif args.mode == "polygon" and len(points) >= 2:
            closed = len(points) >= 3
            cv2.polylines(
                display, [np.array(points, dtype=np.int32)], closed,
                (0, 168, 232), 2, cv2.LINE_AA
            )

        cv2.imshow(WINDOW_NAME, display)
        key = cv2.waitKey(20) & 0xFF

        if key in (ord('q'), 27):  # Q or Esc
            print("Cancelled, nothing printed.")
            break

        if key in (ord('s'), 13):  # S or Enter
            if (args.mode == "line" and len(points) != 2) or (
                args.mode == "polygon" and len(points) < 3
            ):
                print("Not enough points yet.")
                continue

            normalized = [(round(px / w, 4), round(py / h, 4)) for px, py in points]
            key_name = "line_vector" if args.mode == "line" else "zone_polygon"
            print(f'"{key_name}": {normalized},')

            snapshot_path = f"calibration_snapshot_{label.split(':')[0].replace(' ', '')}.png"
            cv2.imwrite(snapshot_path, display)
            print(f"Saved snapshot: {snapshot_path}")
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
