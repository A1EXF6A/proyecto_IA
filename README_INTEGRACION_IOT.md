# Integración de reconocimiento facial + ESP32

## Qué quedó integrado

- Frontend React existente: conserva captura, vista previa y resultado.
- Backend FastAPI: obtiene la imagen desde IP Webcam, procesa el rostro y ejecuta el modelo KNN.
- Modelo: `backend/models/knn_best.joblib` (único clasificador usado).
- Etiquetas: `backend/models/labels.json`.
- Preprocesamiento: YuNet + alineación de ojos + escala de grises 64x64 + estadísticas regionales 4x4 + HOG. Se replica el procedimiento del notebook.
- Serial: `backend/communication/esp32_serial.py`, protocolo `ID:n\n`.
- Firmware: `esp32/firmware_leds/firmware_leds.ino`.

## Modelo seleccionado

Se seleccionó KNN porque en `salidas/metricas_fotos_nuevas.csv` obtuvo los mejores resultados de la evaluación independiente:
- Accuracy: 0.7321 (73.21 %)
- F1 macro: 0.6852 (68.52 %)

La CNN tuvo mejor resultado en la comparación original, pero menor rendimiento en las fotografías independientes. El sistema utiliza únicamente KNN.

## Correspondencia de identidades y LED

La base de datos del proyecto contiene estos identificadores:

| ID enviado | Etiqueta del modelo | Persona de la base | LED |
|---:|---|---|---|
| 1 | alexander | Alexander Luisa | Rojo (GPIO 25) |
| 2 | alex | Alex Guachi | Verde (GPIO 26) |
| 3 | heidi | Heidi Villavicenicio | Azul (GPIO 27) |
| 4 | steven | Steven Toala | Amarillo (GPIO 32) |
| 0 | desconocido / sin rostro | Ninguna | Todos apagados |

El ID enviado corresponde al `id` de la persona en la base SQLite, por eso se conserva el mapeo actual.

## Instalación en Windows

Abre PowerShell en `ProyectoFinal_IA`:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si Windows bloquea la activación del entorno, ejecuta:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

YuNet se descarga automáticamente la primera vez y se guarda en:
`backend/models/face_detection_yunet_2023mar.onnx`.
Para esa primera descarga se necesita conexión a Internet.

## Configuración

Edita `backend/.env`:

```env
IPWEBCAM_URL=http://IP_DEL_TELEFONO:8080/shot.jpg
ESP32_SERIAL_PORT=COM3
ESP32_BAUDRATE=115200
ESP32_SERIAL_TIMEOUT=1
FACE_MODEL_PROVIDER=joblib
FACE_MODEL_THRESHOLD=0.0
BEST_MODEL_PATH=models/knn_best.joblib
BEST_MODEL_LABELS_PATH=models/labels.json
YUNET_PATH=models/face_detection_yunet_2023mar.onnx
```

- En IP Webcam activa el servidor e introduce la URL de captura que corresponda a tu teléfono. Según la versión, la ruta puede ser `/shot.jpg`.
- Comprueba el puerto del ESP32 en Administrador de dispositivos > Puertos (COM y LPT).
- Cambia `COM3` por el puerto real.
- Cierra el Monitor Serial del Arduino IDE antes de ejecutar el backend: un puerto COM no puede estar abierto simultáneamente por dos programas.

## Cargar el firmware

1. Abre `esp32/firmware_leds/firmware_leds.ino` en Arduino IDE.
2. Selecciona la placa ESP32 y el puerto correcto.
3. Conecta los LED con sus resistencias a GPIO 25, 26, 27 y 32, respectivamente; conecta sus cátodos a GND.
4. Sube el firmware.
5. Cierra el Monitor Serial del IDE.

Ambos extremos utilizan 115200 baudios.

## Ejecutar el sistema

Terminal 1 (backend):
```powershell
cd ProyectoFinal_IA\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2 (frontend):
```powershell
cd ProyectoFinal_IA\frontend
npm install
npm run dev
```

Abre la URL que muestre Vite. El backend estará en `http://localhost:8000`.

## Secuencia de funcionamiento

1. El usuario pulsa **Tomar foto y reconocer**.
2. React solicita al backend la captura de IP Webcam.
3. FastAPI descarga la fotografía.
4. YuNet localiza el rostro, lo recorta, alinea y normaliza.
5. El backend genera el mismo vector de 356 características usado al entrenar KNN.
6. KNN devuelve una etiqueta.
7. Si es una persona conocida, se busca su ID en SQLite y se envía `ID:<id>`.
8. Si es desconocida, no hay rostro o no se puede identificar, se envía `ID:0`.
9. El ESP32 apaga todos los LED y enciende solamente el LED asociado al ID recibido.

## Verificación

- `GET http://localhost:8000/api/health`: estado general y disponibilidad del modelo.
- `GET http://localhost:8000/api/esp32/status`: estado del puerto serial.
- `GET http://localhost:8000/api/faces/status`: personas y muestras registradas.
- En la interfaz se muestra el estado de conexión del ESP32 y el comando enviado en cada reconocimiento.

## Notas importantes

- El endpoint de entrenamiento interno LBPH se conserva por compatibilidad, pero no se utiliza: el reconocimiento de producción carga el KNN ya entrenado.
- No vuelvas a entrenar KNN con las fotos capturadas en vivo desde esta interfaz; el artefacto seleccionado se mantiene como modelo fijo.
- Si KNN reconoce una etiqueta pero la persona no existe en SQLite con el mismo nombre, se tratará como desconocida y se enviará `ID:0`.
- Para un uso de control de acceso real, valida el modelo con fotografías de prueba representativas del entorno final; el resultado independiente actual aún presenta errores de clasificación.
