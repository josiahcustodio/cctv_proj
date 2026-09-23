import os, cv2
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv()

u = os.environ['CCTV_RTSP_USER']
p = os.environ['CCTV_RTSP_PASS']
host = "192.168.1.113:554"
path = "/cam/realmonitor?channel=1&subtype=1"
url = f"rtsp://{quote(u, safe='')}:{quote(p, safe='')}@{host}{path}"

print(f"Testing cam4 RTSP at {host}...")
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport|tcp|stimeout|5000000"
cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000)
opened = cap.isOpened()
print(f"Stream opened: {opened}")
if opened:
    ret, frame = cap.read()
    print(f"Frame received: {ret}, shape: {frame.shape if ret and frame is not None else None}")
else:
    print("FAILED - check credentials or RTSP path")
cap.release()
