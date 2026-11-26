import { useEffect, useState } from 'react'
import { api, cameraStreamUrl, postForm } from '../api.js'

export default function RecognitionTab({ focusState, refreshFocus }) {
  const [streamKey, setStreamKey] = useState(0)
  const [previewLoaded, setPreviewLoaded] = useState(false)
  const [previewFailed, setPreviewFailed] = useState(false)
  const [cameraStatus, setCameraStatus] = useState({ configured: false })
  const [esp32Status, setEsp32Status] = useState({ connected: false, port: 'COM3' })
  const [result, setResult] = useState(null)
  const [message, setMessage] = useState(null)
  const [faceStatus, setFaceStatus] = useState({
    trained: false,
    provider: 'lbph',
    people: [],
    total_samples: 0
  })
  const [trainingPerson, setTrainingPerson] = useState('')
  const [sampleFile, setSampleFile] = useState(null)
  const [trainingBusy, setTrainingBusy] = useState(false)
  const [recognitionFile, setRecognitionFile] = useState(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)

  const externalModel = faceStatus.provider && faceStatus.provider !== 'lbph'

  async function loadFaceStatus() {
    try {
      const status = await api('/api/faces/status')
      setFaceStatus(status)
      setTrainingPerson((current) => {
        if (current || !status.people.length) return current
        return String(status.people[0].id)
      })
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    }
  }

  async function loadCameraStatus() {
    try {
      const status = await api('/api/camera/status')
      setCameraStatus(status)
      if (!status.configured) setPreviewFailed(true)
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    }
  }

  async function loadEsp32Status() {
    try {
      const status = await api('/api/esp32/status')
      setEsp32Status(status)
    } catch {
      setEsp32Status({ connected: false, port: 'No disponible' })
    }
  }

  useEffect(() => {
    loadFaceStatus()
    loadCameraStatus()
    loadEsp32Status()
  }, [])

  // Reconocimiento automático: consulta un fotograma de IP Webcam cada segundo.
  // El ciclo se programa después de terminar cada petición para evitar solapamientos.
  useEffect(() => {
    if (!cameraStatus.configured) return undefined
    let active = true
    let timerId

    const analyzeNextFrame = async () => {
      try {
        const data = await api('/api/recognize/live', { method: 'POST' })
        if (!active) return
        setResult(data)
        // Se actualiza el estado de los focos cuando la identificación queda
        // confirmada, aunque el ESP32 no esté conectado, para que el vehículo
        // asignado aparezca también en los fotogramas siguientes.
        if (data.stable) {
          await refreshFocus()
        }
        if (data.esp32?.sent) {
          await loadEsp32Status()
        }
        setMessage(null)
      } catch (error) {
        if (active) {
          setMessage({ type: 'error', text: `Reconocimiento automático: ${error.message}` })
        }
      } finally {
        if (active) {
          timerId = window.setTimeout(analyzeNextFrame, 1000)
        }
      }
    }

    analyzeNextFrame()
    return () => {
      active = false
      window.clearTimeout(timerId)
    }
  }, [cameraStatus.configured, refreshFocus])

  // Si el stream en vivo se corta (cámara apagada, cambio de red, etc.),
  // se reintenta automáticamente cada pocos segundos.
  useEffect(() => {
    if (!previewFailed || !cameraStatus.configured) return undefined
    const timer = window.setTimeout(() => {
      setPreviewFailed(false)
      setPreviewLoaded(false)
      setStreamKey(Date.now())
    }, 2500)
    return () => window.clearTimeout(timer)
  }, [previewFailed, cameraStatus.configured])

  function reconnectPreview() {
    setPreviewFailed(false)
    setPreviewLoaded(false)
    setStreamKey(Date.now())
  }

  // Reconocimiento puntual mediante una imagen seleccionada desde el ordenador.
  // Esta opción es independiente de la cámara en vivo y utiliza el mismo modelo.
  async function handleUploadRecognition() {
    if (!recognitionFile) {
      setMessage({ type: 'error', text: 'Selecciona una imagen desde el ordenador.' })
      return
    }
    setUploadBusy(true)
    try {
      const form = new FormData()
      form.append('file', recognitionFile)
      const data = await postForm('/api/recognize', form)
      setUploadResult(data)
      setMessage({
        type: data.recognized ? 'success' : 'warning',
        text: data.recognized
          ? `Imagen reconocida: ${data.person.name}. Se envió la identificación al ESP32.`
          : 'No se pudo identificar a la persona en la imagen.'
      })
      await refreshFocus()
      await loadEsp32Status()
    } catch (error) {
      setMessage({ type: 'error', text: `No se pudo analizar la imagen: ${error.message}` })
    } finally {
      setUploadBusy(false)
    }
  }

  async function handleSample(source) {
    if (!trainingPerson) {
      setMessage({ type: 'error', text: 'Selecciona una persona' })
      return
    }
    if (source === 'file' && !sampleFile) {
      setMessage({ type: 'error', text: 'Selecciona una imagen' })
      return
    }
    if (source === 'camera' && !cameraStatus.configured) {
      setMessage({ type: 'error', text: 'Configure IPWEBCAM_URL en el backend' })
      return
    }
    setTrainingBusy(true)
    try {
      const form = new FormData()
      form.append('person_id', trainingPerson)
      if (source === 'file') form.append('file', sampleFile)
      const data = await postForm('/api/faces/enroll', form)
      setMessage({
        type: 'success',
        text: `Muestra agregada a ${data.sample.person_name}.`
      })
      setSampleFile(null)
      await loadFaceStatus()
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setTrainingBusy(false)
    }
  }

  async function handleTrain() {
    setTrainingBusy(true)
    try {
      const data = await api('/api/faces/train', { method: 'POST' })
      setMessage({
        type: 'success',
        text: `Modelo entrenado con ${data.sample_count} muestras de ${data.person_count} personas.`
      })
      await loadFaceStatus()
      await refreshFocus()
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setTrainingBusy(false)
    }
  }

  async function turnOff() {
    await api('/api/focus/off', { method: 'POST' })
    setResult(null)
    await refreshFocus()
    await loadEsp32Status()
  }

  const activeVehicle = focusState.vehicles.find((item) => item.focus_active)
  const vehicle = result?.focus?.vehicle || activeVehicle
  const modelLabel = externalModel ? `Modelo ${faceStatus.provider}` : faceStatus.trained ? 'Modelo entrenado' : 'Modelo sin entrenar'

  return (
    <div className="content-grid">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Cámara en vivo (IP Web Cam)</h2>
            <p className="muted">Transmisión continua desde el teléfono con reconocimiento facial automático.</p>
          </div>
          <div className="chip-row">
            <span className={faceStatus.trained ? 'chip success' : 'chip warning'}>{modelLabel}</span>
            <span className={cameraStatus.configured ? 'chip success' : 'chip warning'}>
              {cameraStatus.configured ? 'Cámara configurada' : 'Cámara sin configurar'}
            </span>
            <span className={esp32Status.connected ? 'chip success' : 'chip warning'}>
              {esp32Status.connected ? `ESP32 conectado (${esp32Status.port})` : `ESP32 desconectado (${esp32Status.port})`}
            </span>
          </div>
        </div>

        <div className="camera-layout">
          <div className="preview-frame">
            {!cameraStatus.configured ? (
              <div className="preview-empty">Configure IPWEBCAM_URL en el backend</div>
            ) : (
              <>
                <img
                  key={streamKey}
                  src={cameraStreamUrl(streamKey)}
                  alt="Vista en vivo de IP Web Cam"
                  onLoad={() => {
                    setPreviewLoaded(true)
                    setPreviewFailed(false)
                  }}
                  onError={() => {
                    setPreviewLoaded(false)
                    setPreviewFailed(true)
                  }}
                />
                <span className={`live-badge ${previewLoaded && !previewFailed ? 'active' : ''}`}>
                  <span className="live-dot" />
                  {previewLoaded && !previewFailed ? 'EN VIVO' : 'SIN SEÑAL'}
                </span>
                {!previewLoaded && !previewFailed && (
                  <div className="preview-overlay">Conectando con la cámara…</div>
                )}
                {previewFailed && (
                  <div className="preview-overlay">
                    No se pudo cargar la vista en vivo. Reconectando…
                  </div>
                )}
              </>
            )}
          </div>
          <div className="action-column">
            <button
              className="button ghost"
              type="button"
              disabled={!cameraStatus.configured}
              onClick={reconnectPreview}
            >
              Reconectar cámara
            </button>
            <div className="alert success">
              Reconocimiento automático activo. El sistema analiza fotogramas continuamente y no necesita que presiones un botón.
            </div>
            <p className="muted small">
              Cuando una persona aparece frente a la cámara, el modelo KNN verifica su identidad en fotogramas consecutivos y envía el identificador al ESP32.
            </p>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Resultado</h2>
            <p className="muted">Identidad detectada y estado de activación del ESP32</p>
          </div>
          {activeVehicle && <span className="chip live">Foco encendido</span>}
        </div>

        {message && <div className={`alert ${message.type}`}>{message.text}</div>}

        {result ? (
          <div className="result-layout">
            <img className="result-image" src={result.annotated_image} alt="Foto analizada" />
            <div className="result-details">
              <h3 className={result.recognized ? 'name-success' : 'name-unknown'}>
                {result.recognized ? result.person.name : 'Persona no identificada'}
              </h3>
              <p className="muted">{result.message}</p>
              {!result.stable && result.required_frames && (
                <p className="muted small">Confirmación: {result.pending_frames}/{result.required_frames} fotogramas</p>
              )}
              <p className="muted small">
                ESP32: {result.esp32?.sent
                  ? `comando ${result.esp32.message} enviado`
                  : `sin envío: ${result.esp32?.message || 'puerto no disponible'}`}
              </p>
              <div className="metrics">
                <div>
                  <span>Confianza</span>
                  <strong>{result.confidence != null ? `${result.confidence}%` : 'N/A'}</strong>
                </div>
                <div>
                  <span>Distancia</span>
                  <strong>{result.distance != null ? result.distance : 'N/A'}</strong>
                </div>
              </div>
              <div className="result-vehicle">
                <span className="muted">Vehículo asignado</span>
                {vehicle ? (
                  <>
                    <strong>{vehicle.plate}</strong>
                    <p>{vehicle.brand} {vehicle.model} · {vehicle.color}</p>
                    <p className="muted">Dueño actual: {vehicle.owner_name}</p>
                  </>
                ) : (
                  <p className="muted">Esta persona no tiene vehículo asignado</p>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-state">
            <p>Esperando fotogramas de la cámara para detectar una persona automáticamente.</p>
          </div>
        )}

        <div className="focus-section">
          <div className="focus-heading">
            <h3>Focos de vehículos</h3>
            <button className="button ghost small-button" type="button" onClick={turnOff}>
              Apagar todos
            </button>
          </div>
          <div className="focus-grid">
            {focusState.vehicles.map((item) => (
              <div
                key={item.id}
                className={`focus-card ${item.focus_active ? 'active' : ''}`}
              >
                <span className={`bulb ${item.focus_active ? 'on' : ''}`} />
                <div>
                  <strong>{item.plate}</strong>
                  <p className="muted small">{item.owner_name}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel full-width">
        <div className="panel-header">
          <div>
            <h2>Reconocer imagen desde el ordenador</h2>
            <p className="muted">También puedes seleccionar una fotografía guardada en tu equipo. Se analizará con el mismo modelo KNN y, si se reconoce a una persona, se enviará su identificador al ESP32.</p>
          </div>
          <span className="chip">Reconocimiento manual</span>
        </div>
        <div className="training-layout">
          <label className="field">
            <span>Seleccionar fotografía</span>
            <input
              type="file"
              accept="image/*"
              onChange={(event) => {
                setRecognitionFile(event.target.files?.[0] || null)
                setUploadResult(null)
              }}
            />
          </label>
          <div className="training-actions">
            <button
              className="button primary"
              type="button"
              disabled={uploadBusy || !recognitionFile}
              onClick={handleUploadRecognition}
            >
              {uploadBusy ? 'Analizando imagen…' : 'Analizar imagen'}
            </button>
          </div>
        </div>
        {uploadResult && (
          <div className="result-layout upload-result">
            <img className="result-image" src={uploadResult.annotated_image} alt="Imagen subida y analizada" />
            <div className="result-details">
              <h3 className={uploadResult.recognized ? 'name-success' : 'name-unknown'}>
                {uploadResult.recognized ? uploadResult.person.name : 'Persona no identificada'}
              </h3>
              <p className="muted">{uploadResult.message}</p>
              <p className="muted small">
                ESP32: {uploadResult.esp32?.sent
                  ? `comando ${uploadResult.esp32.message} enviado`
                  : `sin envío: ${uploadResult.esp32?.message || 'puerto no disponible'}`}
              </p>
              <div className="metrics">
                <div><span>Confianza</span><strong>{uploadResult.confidence != null ? `${uploadResult.confidence}%` : 'N/A'}</strong></div>
                <div><span>Distancia</span><strong>{uploadResult.distance != null ? uploadResult.distance : 'N/A'}</strong></div>
              </div>
            </div>
          </div>
        )}
      </section>

      <section className="panel full-width">
        <div className="panel-header">
          <div>
            <h2>Registro de rostros</h2>
            <p className="muted">
              Captura muestras desde la cámara configurada en el backend o sube imágenes.
            </p>
          </div>
          <span className="chip">{faceStatus.total_samples} muestras</span>
        </div>

        <div className="training-layout">
          <label className="field">
            <span>Persona</span>
            <select
              value={trainingPerson}
              onChange={(event) => setTrainingPerson(event.target.value)}
            >
              {faceStatus.people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name} ({person.sample_count})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Muestra desde archivo</span>
            <input
              type="file"
              accept="image/*"
              onChange={(event) => setSampleFile(event.target.files?.[0] || null)}
            />
          </label>
          <div className="training-actions">
            <button
              className="button secondary"
              type="button"
              disabled={trainingBusy || !cameraStatus.configured}
              onClick={() => handleSample('camera')}
            >
              Capturar muestra
            </button>
            <button
              className="button secondary"
              type="button"
              disabled={trainingBusy}
              onClick={() => handleSample('file')}
            >
              Subir muestra
            </button>
            {!externalModel && (
              <button
                className="button primary"
                type="button"
                disabled={trainingBusy}
                onClick={handleTrain}
              >
                Entrenar modelo
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
