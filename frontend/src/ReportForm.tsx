import { useState, type FormEvent } from 'react'
import type { Api } from './api'
import type { Report } from './types'
import { localDateTime, reportPayload } from './reportPayload'
import MapView from './MapView'

export default function ReportForm({ api, onCreated }: { api: Api; onCreated: (report: Report) => void }) {
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const validLocation = latitude.trim() && longitude.trim() && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude))
    && Math.abs(Number(latitude)) <= 90 && Math.abs(Number(longitude)) <= 180

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    setError(''); setMessage('')
    setBusy(true)
    try {
      const payload = reportPayload(form)
      const report = await api<Report>('/reports', { method: 'POST', body: JSON.stringify(payload) })
      form.reset(); setLatitude(''); setLongitude('')
      setMessage(`Reporte registrado (${report.id}). Puedes añadir fotografías en el listado inferior.`)
      onCreated(report)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }

  return <section className="panel">
    <h2>Registrar acumulación de basura</h2>
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <label>Descripción<textarea name="description" required minLength={3} maxLength={2000} rows={3} /></label>
        <div className="fields">
          <label>Latitud<input name="latitude" type="number" step="any" min={-90} max={90} required value={latitude} onChange={(e) => setLatitude(e.target.value)} /></label>
          <label>Longitud<input name="longitude" type="number" step="any" min={-180} max={180} required value={longitude} onChange={(e) => setLongitude(e.target.value)} /></label>
        </div>
        <MapView location={validLocation ? { latitude: Number(latitude), longitude: Number(longitude) } : undefined}
          onPick={(point) => { if (!busy) { setLatitude(String(point.latitude)); setLongitude(String(point.longitude)) } }} />
        <div className="fields">
          <label>Fecha y hora de observación<input name="observed_at" type="datetime-local" defaultValue={localDateTime()} required /><span className="hint">Hora local del dispositivo; se envía con zona horaria.</span></label>
          <label>Tipo de residuo (opcional)<input name="waste_type" maxLength={80} /></label>
        </div>
        <button>{busy ? 'Registrando…' : 'Registrar reporte'}</button>
      </fieldset>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="success" role="status">{message}</p>}
  </section>
}
