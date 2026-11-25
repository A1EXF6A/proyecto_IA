"""Carga y predicción con el único modelo seleccionado: KNN."""
import json
from functools import lru_cache

import joblib
import numpy as np

try:
    from . import config, db
except ImportError:
    import config
    import db


@lru_cache(maxsize=1)
def _load_model():
    if not config.BEST_MODEL_PATH.exists():
        raise RuntimeError(f"No se encuentra el modelo KNN: {config.BEST_MODEL_PATH}")
    return joblib.load(config.BEST_MODEL_PATH)


@lru_cache(maxsize=1)
def _load_labels():
    if not config.BEST_MODEL_LABELS_PATH.exists():
        raise RuntimeError(f"No se encuentra el archivo de etiquetas: {config.BEST_MODEL_LABELS_PATH}")
    payload = json.loads(config.BEST_MODEL_LABELS_PATH.read_text(encoding="utf-8"))
    return payload.get("labels", {})


def is_configured():
    return config.BEST_MODEL_PATH.is_file() and config.BEST_MODEL_LABELS_PATH.is_file()


def _resolve_person(label):
    normalized = str(label).strip().lower()
    if normalized == "desconocido":
        return None
    mapped_name = _load_labels().get(normalized, normalized)
    wanted = str(mapped_name).strip().casefold()
    for person in db.get_people():
        if person["name"].strip().casefold() == wanted:
            return person
    return None


def predict(features):
    """Predice una etiqueta KNN y devuelve la persona si es una identidad autorizada."""
    model = _load_model()
    values = np.asarray(features, dtype=np.float64)
    predicted_label = str(model.predict(values)[0])
    confidence = 0.0
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(values)[0]
        confidence = float(np.max(probabilities)) * 100.0
    if predicted_label == "desconocido":
        return {
            "person": None,
            "label": predicted_label,
            "confidence": round(confidence, 2),
        }
    if confidence < config.FACE_MODEL_THRESHOLD * 100:
        return {
            "person": None,
            "label": "desconocido",
            "confidence": round(confidence, 2),
        }
    person = _resolve_person(predicted_label)
    if not person:
        return {
            "person": None,
            "label": "desconocido",
            "confidence": round(confidence, 2),
        }
    return {
        "person": person,
        "label": predicted_label,
        "confidence": round(confidence, 2),
    }
