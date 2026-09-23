"""Test RTSP connectivity for ALL cameras on the network."""
import os, cv2, time
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv()

USER = os.environ["CCTV_RTSP_USER"]
PASS = os.environ["CCTV_RTSP_PASS"]

# All Dahua cameras found via ARP
CAMERAS = {
    "Cam1": "192.168.1.109:554",
    "Cam2": "192.168.1.111:554",
    "Cam3": "192.168.1.112:554",
    "Cam4": "192.168.1.113:554",
}

# Different Dahua RTSP path variants to try
PATHS = [
    "/cam/realmonitor?channel=1&subtype=1",      # Dahua substream
    "/cam/realmonitor?channel=1&subtype=0",      # Dahua mainstream
    "/live",                                      # Some Dahua models
    "/Streaming/Channels/101",                    # Hikvision-style (some rebrands)
    "/h264Preview_01_sub",                        # Older Dahua
]

def try_connect(host, path, timeout_ms=6000):
    url = f"rtsp://{quote(USER, safe='')}:{quote(PASS, safe='')}@{host}{path}"
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport|tcp|stimeout|5000000"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
    t0 = time.time()
    opened = cap.isOpened()
    elapsed = time.time() - t0
    ret, frame = (False, None)
    if opened:
        ret, frame = cap.read()
    cap.release()
    return opened, ret, frame, elapsed

print("=" * 60)
print("RTSP Connectivity Test - All Cameras")
print(f"Credentials: {USER} / {'*' * len(PASS)}")
print("=" * 60)

for name, host in CAMERAS.items():
    print(f"\n--- {name} ({host}) ---")
    
    # First check if port 554 is even open
    import socket
    ip = host.split(":")[0]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    port_open = sock.connect_ex((ip, 554)) == 0
    sock.close()
    print(f"  Port 554 open: {port_open}")
    
    if not port_open:
        print(f"  SKIPPING - port closed")
        continue
    
    for path in PATHS:
        opened, ret, frame, elapsed = try_connect(host, path)
        shape = frame.shape if ret and frame is not None else None
        status = "OK" if ret else ("OPENED-NO-FRAME" if opened else "FAILED")
        print(f"  [{status:20s}] {path:<45s} ({elapsed:.1f}s) {shape or ''}")
        if ret:
            break  # Found working path, no need to try more

print("\n" + "=" * 60)
print("Done!")
