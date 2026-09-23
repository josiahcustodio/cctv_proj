"""
Standalone RTSP Credential Tester for Dahua Cameras
----------------------------------------------------
Run this BEFORE the main application to verify the stream is reachable.

Usage:
    python test_rtsp.py

It will try the primary substream, the mainstream fallback, and optionally
a custom URL you type in — using both TCP and UDP transports.
"""

import os
import sys
import time
import cv2
from urllib.parse import quote, urlparse, urlunparse, ParseResult
from dotenv import load_dotenv

load_dotenv()

# ── Credentials & camera host (mirrors config.py) ─────────────────────────────
USER = os.environ["CCTV_RTSP_USER"]
PASS = os.environ["CCTV_RTSP_PASS"]
HOST = "192.168.1.108:554"


def build_url(user: str, password: str, host: str, path: str) -> str:
    """Return a properly URL-encoded RTSP URL."""
    return f"rtsp://{quote(user, safe='')}:{quote(password, safe='')}@{host}{path}"


URLS = {
    "Primary   (substream ch1)": build_url(USER, PASS, HOST, "/cam/realmonitor?channel=1&subtype=1"),
    "Fallback  (mainstream ch1)": build_url(USER, PASS, HOST, "/cam/realmonitor?channel=1&subtype=0"),
}

SEPARATOR = "-" * 65


def _safe_url(url: str) -> str:
    """Redact password from URL for display."""
    parsed = urlparse(url)
    redacted = parsed._replace(netloc=f"{parsed.username}:***@{parsed.hostname}:{parsed.port}")
    return urlunparse(redacted)


def test_url(label: str, url: str, transport: str = "tcp", timeout_ms: int = 6000) -> bool:
    """
    Try to open an RTSP URL and grab a single frame.

    Returns True on success, False otherwise.
    """
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport|{transport}|stimeout|{timeout_ms * 1000}"
    )

    print(f"\n  [{transport.upper()}] {label}")
    print(f"  URL : {_safe_url(url)}")

    t0 = time.time()
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)

    opened = cap.isOpened()
    elapsed_open = time.time() - t0

    if not opened:
        print(f"  x  Could not open stream  ({elapsed_open:.1f}s)")
        cap.release()
        return False

    # Attempt to grab exactly one frame to confirm auth succeeded
    t1 = time.time()
    ret, frame = cap.read()
    elapsed_frame = time.time() - t1
    cap.release()

    if ret and frame is not None:
        h, w = frame.shape[:2]
        print(f"  OK  Frame received  {w}x{h}  "
              f"(open {elapsed_open:.1f}s, read {elapsed_frame:.1f}s)")
        return True
    else:
        print(f"  x  Stream opened but no frame returned  (read {elapsed_frame:.1f}s)")
        return False


def main() -> None:
    print(SEPARATOR)
    print("  Dahua RTSP Connection Tester")
    print(SEPARATOR)
    print(f"  Camera : {HOST}")
    print(f"  User   : {USER}")
    print(f"  Pass   : {'*' * len(PASS)}")
    print(SEPARATOR)

    results = {}

    for label, url in URLS.items():
        print(f"\n  {label}")
        # Always try TCP first (Dahua Digest-Auth works more reliably over TCP)
        ok_tcp = test_url(label, url, transport="tcp")
        results[f"{label} [TCP]"] = ok_tcp

        if not ok_tcp:
            # Fall back to UDP only if TCP fails
            ok_udp = test_url(label, url, transport="udp")
            results[f"{label} [UDP]"] = ok_udp

    # -- Optional custom URL ---------------------------------------------------
    print(f"\n{SEPARATOR}")
    try:
        custom = input("  Enter a custom RTSP URL to test (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        custom = ""

    if custom:
        results["Custom URL [TCP]"] = test_url("Custom", custom, transport="tcp")

    # -- Summary ---------------------------------------------------------------
    print(f"\n{SEPARATOR}")
    print("  Summary")
    print(SEPARATOR)
    all_pass = True
    for name, passed in results.items():
        icon = "OK" if passed else "FAIL"
        print(f"  [{icon}]  {name}")
        if not passed:
            all_pass = False

    print(SEPARATOR)
    if all_pass:
        print("  All tests passed — safe to launch the main application.\n")
        sys.exit(0)
    else:
        print("  One or more streams failed. Check credentials, network, or camera settings.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
