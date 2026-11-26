import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
FACE_DIR = DATA_DIR / "faces"
DB_PATH = DATA_DIR / "app.db"
MODEL_PATH = DATA_DIR / "lbph_model.yml"
LABELS_PATH = DATA_DIR / "labels.json"

def env_path(name: str, default: str = "") -> Path:
    value = os.getenv(name, default).strip()
    if not value:
        return Path()
    path = Path(value).expanduser()
    return path if path.is_absolute() else BACKEND_DIR / path


CAMERA_URL = os.getenv("IPWEBCAM_URL", os.getenv("CAMERA_URL", "")).strip()
# Stream MJPEG nativo (por defecto se deduce IPWEBCAM_URL; ej. http://IP:8080/video).
CAMERA_STREAM_URL = os.getenv("CAMERA_STREAM_URL", "").strip()
CAMERA_TIMEOUT_SECONDS = float(os.getenv("CAMERA_TIMEOUT_SECONDS", "5"))
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
# Cuadros por segundo del modo de respaldo (sondeo de shot.jpg).
try:
    CAMERA_STREAM_FPS = int(os.getenv("CAMERA_STREAM_FPS", "10"))
except ValueError:
    CAMERA_STREAM_FPS = 10
CAMERA_STREAM_FPS = max(1, min(30, CAMERA_STREAM_FPS))
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "70"))
FACE_MODEL_PROVIDER = os.getenv("FACE_MODEL_PROVIDER", "lbph").strip().lower()
FACE_MODEL_PATH = env_path("FACE_MODEL_PATH")
FACE_MODEL_LABELS_PATH = env_path("FACE_MODEL_LABELS_PATH")
FACE_MODEL_THRESHOLD = float(os.getenv("FACE_MODEL_THRESHOLD", "0.55"))

_size = os.getenv("FACE_MODEL_INPUT_SIZE", "224x224").lower().replace("x", " ").replace(",", " ").split()
try:
    FACE_MODEL_INPUT_SIZE = (int(_size[0]), int(_size[1]))
except (IndexError, ValueError):
    FACE_MODEL_INPUT_SIZE = (224, 224)

FOCUS_WEBHOOK_URL = os.getenv("FOCUS_WEBHOOK_URL", "")
FOCUS_SERIAL_PORT = os.getenv("FOCUS_SERIAL_PORT", "")
FOCUS_SERIAL_BAUDRATE = int(os.getenv("FOCUS_SERIAL_BAUDRATE", "9600"))
FOCUS_SERIAL_TEMPLATE = os.getenv("FOCUS_SERIAL_TEMPLATE", "ON {plate} {owner}\n")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FACE_DIR.mkdir(parents=True, exist_ok=True)


# Modelo KNN entrenado en el notebook (único modelo utilizado en producción).
MODEL_DIR = BACKEND_DIR / "models"
BEST_MODEL_PATH = env_path("BEST_MODEL_PATH", "models/modelos.joblib")
BEST_MODEL_KEY = os.getenv("BEST_MODEL_KEY", "KNN").strip()
BEST_MODEL_LABELS_PATH = env_path("BEST_MODEL_LABELS_PATH", "models/labels.json")
FACE_MODEL_THRESHOLD = float(os.getenv("FACE_MODEL_THRESHOLD", "0.0"))

# Detector YuNet: se descarga automáticamente si no existe localmente.
YUNET_PATH = env_path("YUNET_PATH", "models/face_detection_yunet_2023mar.onnx")
YUNET_URL = os.getenv(
    "YUNET_URL",
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
)

# ESP32 por USB/serial. En Windows normalmente COM3, COM4, etc.
ESP32_SERIAL_PORT = os.getenv("ESP32_SERIAL_PORT", "COM3").strip()
ESP32_BAUDRATE = int(os.getenv("ESP32_BAUDRATE", "115200"))
ESP32_SERIAL_TIMEOUT = float(os.getenv("ESP32_SERIAL_TIMEOUT", "1"))
