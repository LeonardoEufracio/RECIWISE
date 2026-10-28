import { useEffect, useRef, useState } from 'react'
import type { Coordinates, ReportLocation } from './types'
import LocationMap from './LocationMap'

const gpsErrors: Record<number, string> = {
  1: 'Se denegó el permiso de ubicación. Puedes habilitarlo en tu navegador o elegir el lugar en el mapa.',
  2: 'No se pudo determinar tu ubicación. Revisa la señal del dispositivo o elige el lugar en el mapa.',
  3: 'La ubicación tardó demasiado en responder. Inténtalo de nuevo o elige el lugar en el mapa.',
}

function validPoint(point: Coordinates) {
  return Number.isFinite(point.latitude) && Math.abs(point.latitude) <= 90
    && Number.isFinite(point.longitude) && Math.abs(point.longitude) <= 180
}

export default function LocationPicker({ location, onChange, disabled }: {
  location: ReportLocation | null; onChange: (location: ReportLocation) => void; disabled: boolean
}) {
  const [mode, setMode] = useState<'device' | 'map' | null>(null)
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState('')
  // getCurrentPosition no se puede cancelar; ignorar respuestas tardías al
  // elegir en el mapa, desmontar el formulario o cerrar sesión.
  const requestId = useRef(0)
  useEffect(() => () => { requestId.current += 1 }, [])

  function chooseOnMap() {
    requestId.current += 1
    setLocating(false); setError(''); setMode('map')
    if (location) onChange({ ...location, confirmed: false })
  }

  function pick(point: Coordinates) {
    if (disabled || locating || location?.confirmed || !validPoint(point)) return
    requestId.current += 1
    setMode('map'); setError('')
    // Al mover el punto, la precisión del GPS ya no describe la selección.
    onChange({ ...point, source: 'map', confirmed: false })
  }

  function useDeviceLocation() {
    const currentRequest = ++requestId.current
    setError(''); setMode('device')
    if (location) onChange({ ...location, confirmed: false })
    if (!window.isSecureContext) {
      setError('Para usar tu ubicación abre el aplicativo mediante HTTPS en móvil o localhost en desarrollo. También puedes elegir el lugar en el mapa.')
      return
    }
    if (!navigator.geolocation?.getCurrentPosition) {
      setError('Este navegador no ofrece geolocalización. Elige el lugar en el mapa.')
      return
    }
    setLocating(true)
    try {
      navigator.geolocation.getCurrentPosition((position) => {
        if (currentRequest !== requestId.current) return
        setLocating(false)
        const { latitude, longitude, accuracy } = position.coords
        if (!validPoint({ latitude, longitude })) {
          setError('El dispositivo devolvió una ubicación inválida. Inténtalo de nuevo o elige el lugar en el mapa.')
          return
        }
        onChange({ latitude, longitude, source: 'device', confirmed: false,
          ...(Number.isFinite(accuracy) && accuracy >= 0 ? { accuracy } : {}) })
      }, (failure) => {
        if (currentRequest !== requestId.current) return
        setLocating(false)
        setError(gpsErrors[failure.code] ?? 'No se pudo obtener tu ubicación. Inténtalo de nuevo o elige el lugar en el mapa.')
      }, { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 })
    } catch {
      setLocating(false)
      setError('No se pudo solicitar tu ubicación. Revisa los permisos del navegador o elige el lugar en el mapa.')
    }
  }

  return <section className="location-picker" aria-label="Ubicación del reporte">
    <h3>¿Dónde está la acumulación?</h3>
    <div className="actions location-options">
      <button type="button" disabled={disabled || locating} aria-pressed={mode === 'device'} onClick={useDeviceLocation}>
        {locating ? 'Obteniendo ubicación…' : 'Usar mi ubicación'}
      </button>
      <button type="button" disabled={disabled} aria-pressed={mode === 'map'} onClick={chooseOnMap}>Elegir en el mapa</button>
    </div>
    <p className="hint">El GPS solo se solicita al pulsar «Usar mi ubicación». La selección permanece en esta pantalla hasta confirmar y enviar el reporte.</p>
    {locating && <p role="status">Buscando tu ubicación. Si aparece una solicitud del navegador, puedes aceptar o elegir en el mapa.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {mode && <>
      <LocationMap location={location} editable={!disabled && !locating && !location?.confirmed} onPick={pick} />
      {!location && !locating && <p>Toca o haz clic en el mapa para seleccionar el lugar. El centro inicial es solo una referencia.</p>}
    </>}
    {location && <div className="location-summary" aria-live="polite">
      <p><strong>Punto seleccionado:</strong> {location.latitude.toFixed(6)}, {location.longitude.toFixed(6)}</p>
      {location.source === 'device' && location.accuracy !== undefined && <p>Precisión estimada: ±{Math.round(location.accuracy)} m.</p>}
      {location.confirmed
        ? <><p className="success">Ubicación confirmada. Se incluirá al pulsar «Registrar reporte».</p>
          <button type="button" disabled={disabled} onClick={chooseOnMap}>Corregir ubicación</button></>
        : <><p>Revisa el punto. Puedes tocar otro lugar o arrastrar el marcador para corregirlo y después confirmar.</p>
          <button type="button" disabled={disabled || locating} onClick={() => onChange({ ...location, confirmed: true })}>Confirmar ubicación</button></>}
    </div>}
  </section>
}
