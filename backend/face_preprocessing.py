"""Preprocesamiento compatible con el notebook de entrenamiento.

YuNet detecta el rostro, se alinea usando los ojos y genera una imagen
en escala de grises de 64x64. Después se extraen estadísticas regionales
y HOG, exactamente como en la etapa de entrenamiento.
"""
from pathlib import Path
import urllib.request
import threading

import cv2
import numpy as np
from skimage.feature import hog

try:
    from . import config
except ImportError:
    import config

DETECTOR_SCORE = 0.6
DETECTOR_NMS = 0.3
DETECTOR_TOP_K = 5000
CARA_AMPLIADA = 256
MARGEN_CARA = 1.20
FRACCION_ALINEADA = 0.85
RESOLUCION = 64

REGION_ROWS = 4
REGION_COLS = 4
HOG_ORIENTATIONS = 9
HOG_PIXELS_PER_CELL = (16, 16)
HOG_CELLS_PER_BLOCK = (2, 2)
HOG_BLOCK_NORM = "L2-Hys"

_detector = None
_detector_lock = threading.Lock()


def _ensure_yunet():
    config.YUNET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not config.YUNET_PATH.exists():
        try:
            urllib.request.urlretrieve(config.YUNET_URL, str(config.YUNET_PATH))
        except Exception as exc:
            raise RuntimeError(
                "No se pudo descargar YuNet. Descarga face_detection_yunet_2023mar.onnx "
                f"y colócalo en {config.YUNET_PATH}. Detalle: {exc}"
            ) from exc
    if config.YUNET_PATH.stat().st_size < 100_000:
        raise RuntimeError(f"El archivo YuNet parece incompleto: {config.YUNET_PATH}")


def get_detector():
    global _detector
    with _detector_lock:
        if _detector is None:
            _ensure_yunet()
            _detector = cv2.FaceDetectorYN_create(
                str(config.YUNET_PATH), "", (CARA_AMPLIADA, CARA_AMPLIADA),
                DETECTOR_SCORE, DETECTOR_NMS, DETECTOR_TOP_K
            )
        return _detector


def _detect_face(detector, image):
    height, width = image.shape[:2]
    detector.setInputSize((width, height))
    _, faces = detector.detect(image)
    if faces is None or len(faces) == 0:
        return None
    # YuNet: x,y,w,h, cinco landmarks (10 valores), score.
    face = max(faces, key=lambda row: float(row[14]))
    box = face[:4].astype(np.float64)
    landmarks = face[4:14].reshape(5, 2).astype(np.float64)
    x, y, w, h = box
    if w <= 0 or h <= 0 or not np.isfinite(face).all():
        return None
    if not (0 <= landmarks[:, 0]).all() or not (landmarks[:, 0] <= width).all():
        return None
    if not (0 <= landmarks[:, 1]).all() or not (landmarks[:, 1] <= height).all():
        return None
    return box, landmarks


def _eye_angle(points):
    first, second = points[0], points[1]
    if second[0] < first[0]:
        first, second = second, first
    return float(np.degrees(np.arctan2(second[1]-first[1], second[0]-first[0])))


def _crop_face(image, box):
    height, width = image.shape[:2]
    x, y, w, h = box
    side = max(w, h) * MARGEN_CARA
    cx, cy = x + w/2.0, y + h/2.0
    x1 = int(round(cx-side/2.0))
    y1 = int(round(cy-side/2.0))
    side_i = max(1, int(round(side)))
    x1 = min(max(0, x1), max(0, width-side_i))
    y1 = min(max(0, y1), max(0, height-side_i))
    x2, y2 = min(width, x1+side_i), min(height, y1+side_i)
    return image[y1:y2, x1:x2]


def _align_crop(crop, angle):
    height, width = crop.shape[:2]
    center = (width/2.0, height/2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        crop, matrix, (width, height), flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE
    )
    side = int(round(min(width, height) * FRACCION_ALINEADA))
    x1, y1 = (width-side)//2, (height-side)//2
    return rotated[y1:y1+side, x1:x1+side]


def process_face(image, detector=None):
    """Devuelve (rostro_64x64_gris, bounding_box) o (None, None)."""
    if image is None or image.size == 0:
        return None, None
    detector = detector or get_detector()
    detected = _detect_face(detector, image)
    if detected is None:
        return None, None
    box, points = detected
    angle = _eye_angle(points)
    crop = _crop_face(image, box)
    if crop.size == 0 or min(crop.shape[:2]) < 8:
        return None, None
    enlarged = cv2.resize(crop, (CARA_AMPLIADA, CARA_AMPLIADA), interpolation=cv2.INTER_CUBIC)
    second = _detect_face(detector, enlarged)
    if second is not None:
        angle = _eye_angle(second[1])
    aligned = _align_crop(enlarged, angle)
    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    face64 = cv2.resize(gray, (RESOLUCION, RESOLUCION), interpolation=cv2.INTER_AREA)
    return face64, [int(round(v)) for v in box]


def regional_statistics(image):
    image = np.asarray(image, dtype=np.float32)
    height, width = image.shape
    cell_h, cell_w = height // REGION_ROWS, width // REGION_COLS
    values = []
    for row in range(REGION_ROWS):
        for col in range(REGION_COLS):
            region = image[row*cell_h:(row+1)*cell_h, col*cell_w:(col+1)*cell_w]
            values.extend((float(region.mean()), float(region.std())))
    return np.asarray(values, dtype=np.float64)


def hog_descriptor(image):
    return np.asarray(hog(
        np.asarray(image, dtype=np.float32),
        orientations=HOG_ORIENTATIONS,
        pixels_per_cell=HOG_PIXELS_PER_CELL,
        cells_per_block=HOG_CELLS_PER_BLOCK,
        block_norm=HOG_BLOCK_NORM,
        feature_vector=True,
    ), dtype=np.float64)


def extract_features(face64):
    """Mismo vector concatenado del notebook: estadísticas regionales + HOG."""
    normalized = np.asarray(face64, dtype=np.float32) / 255.0
    return np.concatenate([regional_statistics(normalized), hog_descriptor(normalized)]).reshape(1, -1)
