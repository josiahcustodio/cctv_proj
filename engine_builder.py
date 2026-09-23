import importlib.util
import os
from ultralytics import YOLO
from config import YOLO_MODEL_PATH, TRT_ENGINE_PATH, BATCH_SIZE, MODEL_WIDTH, MODEL_HEIGHT


def _tensorrt_available() -> bool:
    """True if the `tensorrt` python bindings are importable (required to export an engine)."""
    return importlib.util.find_spec("tensorrt") is not None


def get_model_path() -> str:
    """
    Path the inference engine should load: the TensorRT engine when it exists,
    otherwise the original PyTorch weights (slower, but keeps the app usable).
    """
    return TRT_ENGINE_PATH if os.path.exists(TRT_ENGINE_PATH) else YOLO_MODEL_PATH


def ensure_tensorrt_engine() -> str:
    """
    Ensures the TensorRT engine exists, building it if needed.

    Returns the model path to run inference with. A failed build is not fatal:
    we fall back to the .pt weights so the app still starts on machines without
    a working TensorRT install.
    """
    if os.path.exists(TRT_ENGINE_PATH):
        print(f"[INFO] TensorRT engine already exists at {TRT_ENGINE_PATH}")
        return TRT_ENGINE_PATH

    if not _tensorrt_available():
        print("[WARN] TensorRT bindings not installed - skipping engine build.")
        print('[WARN] Install with: pip install "tensorrt-cu12==10.13.3.9"  '
              "(use the -cu12 variant to match this torch cu121 build)")
        print(f"[WARN] Falling back to PyTorch inference with {YOLO_MODEL_PATH}")
        return YOLO_MODEL_PATH

    print(f"[INFO] TensorRT engine not found. Building from {YOLO_MODEL_PATH}...")
    print(f"[INFO] This will take a few minutes. Batch size: {BATCH_SIZE}, Half: True")

    try:
        model = YOLO(YOLO_MODEL_PATH)
        # dynamic=True builds a variable-batch profile (1..BATCH_SIZE) so the number of
        # active cameras can change (offline/reconnecting/added) without needing a
        # fixed-size batch on every inference call.
        model.export(
            format="engine",
            device=0, # Assuming CUDA_DEVICE is cuda:0
            half=True, # FP16 precision
            batch=BATCH_SIZE,  # max batch size profiled for
            imgsz=(MODEL_HEIGHT, MODEL_WIDTH),
            dynamic=True,
            simplify=True
        )
        print(f"[INFO] Successfully built TensorRT engine at {TRT_ENGINE_PATH}")
        return TRT_ENGINE_PATH
    except Exception as e:
        print(f"[ERROR] Failed to build TensorRT engine: {e}")
        print(f"[WARN] Falling back to PyTorch inference with {YOLO_MODEL_PATH}")
        return YOLO_MODEL_PATH


if __name__ == "__main__":
    ensure_tensorrt_engine()
