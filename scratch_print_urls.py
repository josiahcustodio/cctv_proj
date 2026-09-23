from config import CAMERA_CONFIGS
import re

for k, v in CAMERA_CONFIGS.items():
    url = v["rtsp_url"]
    fb = v["fallback_url"]
    safe_url = re.sub(r'://[^:]+:[^@]+@', '://***:***@', url) if '@' in url else url
    safe_fb = re.sub(r'://[^:]+:[^@]+@', '://***:***@', fb) if '@' in fb else fb
    print(f"Cam {k}: {safe_url}")
    print(f"   fb : {safe_fb}")
    print()
