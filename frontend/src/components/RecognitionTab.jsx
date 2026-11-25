import { useEffect, useRef, useState } from 'react'
import { api, cameraStreamUrl, postForm, postJson } from '../api.js'

export default function RecognitionTab({ focusState, refreshFocus }) {
  const [streamKey, setStreamKey] = useState(0)
  const [previewLoaded, setPreviewLoaded] = useState(false)
  const [previewFailed, setPreviewFailed] = useState(false)
  const [flash, setFlash] = useState(false)
  const [cameraStatus, setCameraStatus] = useState({ configured: false })
  const [esp32Status, setEsp32Status] = useState({ connected: false, port: 'COM3' })
  const [result, setResult] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [faceStatus, setFaceStatus] = useState({
    trained: false,
    provider: 'lbph',
    people: [],
    total_samples: 0
  })
  const [trainingPerson, setTrainingPerson] = useState('')
  const [sampleFile, setSampleFile] = useState(null)
  const [trainingBusy, setTrainingBusy] = useState(false)
  const uploadRef = useRef(null)
  const flashTimer = useRef(null)

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

  useEffect(() => () => {
    if (flashTimer.current) window.clearTimeout(flashTimer.current)
  }, [])

  function reconnectPreview() {
    setPreviewFailed(false)
    setPreviewLoaded(false)
    setStreamKey(Date.now())
  }

  async function recognize(payload, isForm = false) {
    setBusy(true)
    setMessage(null)
    setResult(null)
    try {
      const data = isForm
        ? await postForm('/api/recognize', payload)
        : await postJson('/api/recognize/json', payload)
      setResult(data)
      await refreshFocus()
      await loadEsp32Status()
    } catch (error) {
      setMessage({ type: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  function handleCapture() {
    if (!cameraStatus.configured) {
      setMessage({ type: 'error', text: 'Configure IPWEBCAM_URL en el backend' })
      return
    }
    // Pequeño destello para indicar que se tomó el fotograma actual.
    setFlash(true)
    if (flashTimer.current) window.clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlash(false), 320)
    recognize({})
  }

  function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    recognize(form, true)
    event.target.value = ''
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

  const vehicle = result?.focus?.vehicle
  const activeVehicle = focusState.vehicles.find((item) => item.focus_active)
  const modelLabel = externalModel ? `Modelo ${faceStatus.provider}` : faceStatus.trained ? 'Modelo entrenado' : 'Modelo sin entrenar'

  return (
    <div className="content-grid">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Cámara en vivo (IP Web Cam)</h2>
            <p className="muted">Lo que ves es la transmisión actual del celular; toma la foto cuando el rostro esté en cuadro.</p>
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
                <span className={`capture-flash ${flash ? 'active' : ''}`} />
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
            <button
              className="button primary"
              type="button"
              onClick={handleCapture}
              disabled={busy || !cameraStatus.configured}
            >
              {busy ? 'Procesando...' : 'Tomar foto y reconocer'}
            </button>
            <button
              className="button secondary"
              type="button"
              onClick={() => uploadRef.current?.click()}
              disabled={busy}
            >
              Subir foto desde la PC
            </button>
            <input
              ref={uploadRef}
              className="hidden-input"
              type="file"
              accept="image/*"
              onChange={handleUpload}
            />
            <p className="muted small">
              Al tomar la foto se analiza el fotograma actual, se compara con el modelo KNN y se activa el foco del vehículo.
            </p>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Resultado</h2>
            <p className="muted">Dueño, vehículo y foco activado</p>
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
            <p>Toma una foto para ver el resultado del reconocimiento.</p>
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
