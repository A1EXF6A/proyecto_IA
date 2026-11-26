import base64
import time
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from . import config, db, face_engine, focus
    from .communication import esp32_serial
except ImportError:
    import config
    import db
    import face_engine
    import focus
    from communication import esp32_serial


class RecognizePayload(BaseModel):
    image_base64: str | None = None


class OwnerPayload(BaseModel):
    owner_id: int


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    # Si el ESP32 no está conectado, el backend sigue funcionando.
    esp32_serial.conectar()
    try:
        yield
    finally:
        esp32_serial.desconectar()


app = FastAPI(title="Reconocimiento de dueños de vehículos", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _decode_base64(value: str) -> bytes:
    if value.startswith("data:"):
        value = value.split(",", 1)[-1]
    try:
        return base64.b64decode(value, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="Base64 de imagen inválido")


def _camera_bytes():
    if not config.CAMERA_URL:
        raise HTTPException(
            status_code=400,
            detail="Cámara no configurada. Defina IPWEBCAM_URL en el backend.",
        )
    try:
        return face_engine.fetch_camera_image(config.CAMERA_URL)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="No se pudo capturar de la cámara configurada.",
        )


def _mjpeg_iter():
    """Genera cuadros MJPEG leyendo la cámara configurada."""
    interval = 1.0 / max(1, config.CAMERA_STREAM_FPS)
    failures = 0
    while True:
        started = time.monotonic()
        try:
            frame = face_engine.fetch_camera_image(config.CAMERA_URL)
            failures = 0
        except Exception:
            failures += 1
            # Se reintenta brevemente; si la cámara sigue caída se cierra el
            # stream para que el frontend muestre el aviso y pueda reconectar.
            if failures > 5:
                break
            time.sleep(0.4)
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode("ascii") + b"\r\n\r\n"
            + frame
            + b"\r\n"
        )
        remaining = interval - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)


def _native_mjpeg_iter(upstream):
    """Reenvía tal cual el stream MJPEG nativo de IP Webcam (una sola conexión)."""
    try:
        while True:
            try:
                chunk = upstream.read(8192)
            except Exception:
                break
            if not chunk:
                break
            yield chunk
    finally:
        try:
            upstream.close()
        except Exception:
            pass


def _source_bytes(file: UploadFile | None, image_base64: str | None):
    if file is not None:
        return file.file.read()
    if image_base64:
        return _decode_base64(image_base64)
    return _camera_bytes()


def _recognize_bytes(image_bytes: bytes):
    try:
        result = face_engine.recognize(image_bytes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if result["recognized"]:
        person_id = int(result["person"]["id"])
        result["focus"] = focus.activate_for(person_id)
        result["esp32"] = esp32_serial.enviar_persona(person_id)
    else:
        result["focus"] = focus.turn_off_all()
        result["esp32"] = esp32_serial.enviar_persona(5)
    return result


# Estado del reconocimiento automático.
# La identidad se aplica con el primer fotograma reconocido (sin confirmación).
# Solo el apagado exige varios fotogramas sin identidad para evitar parpadeos.
_live_lock = threading.Lock()
_live_candidate_id = None
_live_candidate_frames = 0
_live_last_sent_id = 0
_live_last_applied_id = 0
_LIVE_UNKNOWN_FRAMES = 3


def _reset_live_state() -> None:
    """Olvida la última identificación aplicada para forzar una nueva evaluación."""
    global _live_candidate_id, _live_candidate_frames, _live_last_sent_id, _live_last_applied_id
    with _live_lock:
        _live_candidate_id = None
        _live_candidate_frames = 0
        _live_last_sent_id = 0
        _live_last_applied_id = 0


def _recognize_live_frame(image_bytes: bytes):
    global _live_candidate_id, _live_candidate_frames, _live_last_sent_id, _live_last_applied_id
    try:
        result = face_engine.recognize(image_bytes)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    candidate_id = (
        int(result["person"]["id"])
        if result.get("recognized") and result.get("person")
        else None
    )

    with _live_lock:
        if candidate_id == _live_candidate_id:
            _live_candidate_frames += 1
        else:
            _live_candidate_id = candidate_id
            _live_candidate_frames = 1

        # Un rostro reconocido se aplica de inmediato (1 fotograma).
        required = 1 if candidate_id is not None else _LIVE_UNKNOWN_FRAMES
        stable = _live_candidate_frames >= required
        result["stable"] = stable
        result["pending_frames"] = _live_candidate_frames
        result["required_frames"] = required

        if not stable:
            result["focus"] = focus.get_state()
            result["esp32"] = {
                "sent": False,
                "message": "Esperando a confirmar que no hay una persona reconocida",
            }
            result["message"] = (
                f"Buscando un rostro reconocido "
                f"({_live_candidate_frames}/{required})..."
            )
            return result

        # ID 5 representa rostro no reconocido; ID 0 se reserva para apagar
        # explícitamente todos los LED (por ejemplo, al detener el sistema).
        target_id = candidate_id if candidate_id is not None else 5
        if target_id != _live_last_applied_id:
            if candidate_id is not None:
                result["focus"] = focus.activate_for(target_id)
            else:
                result["focus"] = focus.turn_off_all()
            _live_last_applied_id = target_id
        else:
            # Aunque no se repita la activación, se devuelve el vehículo de la
            # persona reconocida para que la interfaz no muestre "sin vehículo"
            # en los fotogramas posteriores a la confirmación.
            result["focus"] = focus.get_state(candidate_id)

        # Si el ESP32 estaba desconectado, se vuelve a intentar en los siguientes
        # fotogramas hasta confirmar el envío, sin repetir eventos de foco.
        serial_state = esp32_serial.estado()
        if target_id != _live_last_sent_id or not serial_state["connected"]:
            result["esp32"] = esp32_serial.enviar_persona(target_id)
            if result["esp32"].get("sent"):
                _live_last_sent_id = target_id
        else:
            result["esp32"] = {
                "sent": False,
                "person_id": target_id,
                "message": "Sin cambios: la salida ya corresponde a esta identificación",
            }

        result["message"] = (
            f"Persona reconocida: {result['person']['name']}"
            if candidate_id is not None
            else "Persona desconocida o sin rostro reconocido"
        )
        return result


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model_trained": face_engine.is_trained(),
        "model_provider": config.FACE_MODEL_PROVIDER,
        "camera_configured": bool(config.CAMERA_URL),
    }




@app.get("/api/esp32/status")
def esp32_status():
    return esp32_serial.estado()


@app.get("/api/people")
def people():
    return db.get_people()


@app.get("/api/vehicles")
def vehicles():
    return db.get_vehicles()


@app.put("/api/vehicles/{vehicle_id}/owner")
def change_owner(vehicle_id: int, payload: OwnerPayload):
    try:
        vehicle = db.set_vehicle_owner(vehicle_id, payload.owner_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado")
    focus.turn_off_all()
    esp32_serial.enviar_persona(0)
    # La asignación cambió: se debe volver a evaluar y enviar en el próximo
    # reconocimiento, aunque sea la misma persona que antes.
    _reset_live_state()
    return {"message": "Dueño actualizado", "vehicle": vehicle}


@app.get("/api/focus")
def focus_state():
    return focus.get_state()


@app.post("/api/focus/off")
def focus_off():
    result = focus.turn_off_all()
    result["esp32"] = esp32_serial.enviar_persona(0)
    _reset_live_state()
    return result


@app.get("/api/camera/status")
def camera_status():
    return {"configured": bool(config.CAMERA_URL)}


@app.get("/api/camera/snapshot")
def camera_snapshot():
    return Response(
        content=_camera_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/camera/stream")
def camera_stream():
    """Vista en vivo en formato MJPEG (multipart/x-mixed-replace).

    Primero intenta reenviar el stream nativo de IP Webcam (/video), que
    entrega muchos más cuadros por segundo. Si no está disponible, cae al
    sondeo de IPWEBCAM_URL (shot.jpg).
    """
    if not config.CAMERA_URL:
        raise HTTPException(
            status_code=400,
            detail="Cámara no configurada. Defina IPWEBCAM_URL en el backend.",
        )
    headers = {
        "Cache-Control": "no-store, max-age=0",
        "Pragma": "no-cache",
        "X-Accel-Buffering": "no",
    }
    _, upstream = face_engine.open_camera_stream()
    if upstream is not None:
        media_type = (
            upstream.headers.get("Content-Type")
            or "multipart/x-mixed-replace; boundary=frame"
        )
        return StreamingResponse(
            _native_mjpeg_iter(upstream), media_type=media_type, headers=headers
        )
    return StreamingResponse(
        _mjpeg_iter(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers=headers,
    )


@app.post("/api/recognize")
async def recognize_upload(file: UploadFile | None = File(None)):
    return _recognize_bytes(_source_bytes(file, None))


@app.post("/api/recognize/json")
def recognize_json(payload: RecognizePayload):
    return _recognize_bytes(_source_bytes(None, payload.image_base64))


@app.post("/api/recognize/live")
def recognize_live():
    """Analiza automáticamente el fotograma actual de IP Webcam."""
    return _recognize_live_frame(_camera_bytes())


@app.get("/api/faces/status")
def face_status():
    status = db.get_face_status()
    return {
        "trained": face_engine.is_trained(),
        "provider": config.FACE_MODEL_PROVIDER,
        "people": status,
        "total_samples": sum(item["sample_count"] for item in status),
    }


@app.post("/api/faces/enroll")
async def enroll(
    person_id: int = Form(...),
    file: UploadFile | None = File(None),
):
    image_bytes = _source_bytes(file, None)
    try:
        sample = face_engine.enroll_face(image_bytes, person_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"message": "Muestra registrada", "sample": sample}


@app.post("/api/faces/train")
def train():
    try:
        return face_engine.train()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "frontend" / "dist"

if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

if (DIST_DIR / "index.html").exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        return FileResponse(DIST_DIR / "index.html")
