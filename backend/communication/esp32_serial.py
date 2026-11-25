"""Comunicación serial persistente con el ESP32."""
import threading
import time

try:
    from .. import config
except ImportError:
    import config

try:
    import serial
except ImportError:
    serial = None

_lock = threading.Lock()
_port = None
_last_error = None


def conectar():
    global _port, _last_error
    with _lock:
        if _port is not None and getattr(_port, "is_open", False):
            return True
        if serial is None:
            _last_error = "pyserial no está instalado"
            return False
        if not config.ESP32_SERIAL_PORT:
            _last_error = "ESP32_SERIAL_PORT no está configurado"
            return False
        try:
            _port = serial.Serial(
                port=config.ESP32_SERIAL_PORT,
                baudrate=config.ESP32_BAUDRATE,
                timeout=config.ESP32_SERIAL_TIMEOUT,
                write_timeout=2,
            )
            # El ESP32 suele reiniciarse al abrir el puerto USB.
            time.sleep(2)
            _port.reset_input_buffer()
            _last_error = None
            print(f"ESP32 conectado en {config.ESP32_SERIAL_PORT} a {config.ESP32_BAUDRATE} baudios")
            return True
        except Exception as exc:
            _port = None
            _last_error = str(exc)
            print(f"No se pudo conectar al ESP32: {_last_error}")
            return False


def enviar_persona(persona_id):
    """Envía ID:n. ID 0 apaga todos los LED."""
    global _port, _last_error
    try:
        persona_id = int(persona_id)
    except (TypeError, ValueError):
        raise ValueError("El identificador de persona debe ser un entero")
    if persona_id not in (0, 1, 2, 3, 4):
        raise ValueError("Identificador no válido. Valores permitidos: 0, 1, 2, 3, 4")

    with _lock:
        if _port is None or not getattr(_port, "is_open", False):
            # Conexión bajo demanda si el ESP32 se conectó después de iniciar FastAPI.
            if serial is None:
                _last_error = "pyserial no está instalado"
                return {"sent": False, "message": _last_error}
            try:
                candidate = serial.Serial(
                    config.ESP32_SERIAL_PORT,
                    config.ESP32_BAUDRATE,
                    timeout=config.ESP32_SERIAL_TIMEOUT,
                    write_timeout=2,
                )
                time.sleep(2)
                candidate.reset_input_buffer()
                _port = candidate
                _last_error = None
            except Exception as exc:
                _last_error = str(exc)
                return {"sent": False, "message": _last_error}

        message = f"ID:{persona_id}\n"
        try:
            _port.write(message.encode("utf-8"))
            _port.flush()
            return {
                "sent": True,
                "person_id": persona_id,
                "message": message.strip(),
                "port": config.ESP32_SERIAL_PORT,
            }
        except Exception as exc:
            _last_error = str(exc)
            try:
                _port.close()
            except Exception:
                pass
            _port = None
            return {"sent": False, "message": _last_error}


def estado():
    connected = _port is not None and getattr(_port, "is_open", False)
    return {
        "connected": bool(connected),
        "port": config.ESP32_SERIAL_PORT,
        "baudrate": config.ESP32_BAUDRATE,
        "last_error": _last_error,
    }


def desconectar():
    global _port
    with _lock:
        if _port is not None:
            try:
                if _port.is_open:
                    _port.write(b"ID:0\n")
                    _port.flush()
                    _port.close()
            except Exception as exc:
                print(f"Error al cerrar el puerto ESP32: {exc}")
            finally:
                _port = None
