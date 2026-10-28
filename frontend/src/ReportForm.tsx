import { useState, type FormEvent } from 'react'
import type { Api } from './api'
import type { Report, ReportLocation } from './types'
import { localDateTime, reportPayload } from './reportPayload'
import LocationPicker from './LocationPicker'

export default function ReportForm({ api, onCreated }: { api: Api; onCreated: (report: Report) => void }) {
  const [location, setLocation] = useState<ReportLocation | null>(null)
  const [locationVersion, setLocationVersion] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    setError(''); setMessage('')
    setBusy(true)
    try {
      const payload = reportPayload(form, location)
      const report = await api<Report>('/reports', { method: 'POST', body: JSON.stringify(payload) })
      form.reset(); setLocation(null); setLocationVersion((value) => value + 1)
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
        <LocationPicker key={locationVersion} location={location} disabled={busy} onChange={(point) => { setLocation(point); setError('') }} />
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
