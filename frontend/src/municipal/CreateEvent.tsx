import { useCallback, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../api'
import LocationPicker from '../LocationPicker'
import type { ReportLocation } from '../types'
import type { BackendService } from './backendService'
import type { EventCreateCommand } from './backendTypes'
import { Pager } from './backendUi'
import { Empty, ErrorBox, Loading, Modal, useData } from './ui'

export default function CreateEvent({ service, close, saved }: { service: BackendService; close: () => void; saved: (id: string) => void }) {
  const [location, setLocation] = useState<ReportLocation | null>(null)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string[]>([])
  const [command, setCommand] = useState<EventCreateCommand | null>(null)
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const [error, setError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const load = useCallback((signal: AbortSignal) => service.groupings({ linked: false, offset }, signal), [service, offset])
  const reports = useData(load)
  function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!location?.confirmed || lock.current || uncertain) return
    const fields = new FormData(event.currentTarget)
    setError('')
    setCommand({ latitude: location.latitude, longitude: location.longitude, intervention_type: String(fields.get('intervention') || '').trim() || null, report_ids: [...selected] })
  }
  async function submit() {
    if (!command || lock.current || uncertain) return
    lock.current = true; setBusy(true); setError('')
    try { const result = await service.createEvent(command); saved(result.id) }
    catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo registrar el evento.')
      if (!(err instanceof ApiError) || err.status === null || err.status >= 500) setUncertain(true)
      else { setCommand(null); reports.retry() }
    } finally { lock.current = false; setBusy(false) }
  }
  return <Modal title="Crear evento municipal" close={() => !lock.current && close()}>
    <p>Registro manual. Los reportes conservan su estado; asociarlos no significa atenderlos.</p>
    {error && <ErrorBox message={error} />}
    {uncertain && <div className="notice warning"><p>El resultado no está confirmado. Consulta los eventos antes de crear otro; no se repetirá el envío.</p><button onClick={close}>Volver a consultar eventos</button></div>}
    <form onSubmit={review}><fieldset disabled={busy || !!command || uncertain}>
      <label>Intervención manual (opcional)<input name="intervention" maxLength={120} /></label>
      <LocationPicker purpose="event" location={location} onChange={setLocation} disabled={busy || !!command || uncertain} />
      <h3>Reportes sin asociación</h3>
      <p className="hint">Solo se pueden asociar aquí reportes sin historial. Para corregir decisiones anteriores utiliza Revisión de agrupaciones.</p>
      {reports.loading && <Loading />}{reports.error && <ErrorBox message={reports.error} retry={reports.retry} />}
      {reports.data && !reports.data.length && <Empty title="Sin reportes en esta página" />}
      {reports.data?.map((item) => <label className="check-row report-choice" key={item.report.id}><input type="checkbox" disabled={!!item.last_decision_id || (!selected.includes(item.report.id) && selected.length >= 100)} checked={selected.includes(item.report.id)} onChange={(e) => setSelected((value) => e.target.checked ? [...value, item.report.id] : value.filter((id) => id !== item.report.id))} /><span>{item.report.description}<small className="identifier">{item.report.id}{item.last_decision_id && ' · Requiere revisión de historial'}</small></span></label>)}
      <Pager label="reportes sin asociación" offset={offset} count={reports.data?.length || 0} loading={reports.loading} change={setOffset} />
      <p>{selected.length} reportes seleccionados. Se permite un evento manual sin reportes.</p>
      <button className="primary" disabled={!location?.confirmed}>Revisar evento manual</button>
    </fieldset></form>
    {command && !uncertain && <section className="notice"><h3>Confirmar evento</h3><p>Ubicación: {command.latitude}, {command.longitude}. Reportes: {command.report_ids.length}. Intervención: {command.intervention_type || 'Por definir'}.</p><div className="actions"><button disabled={busy} onClick={() => setCommand(null)}>Corregir evento</button><button className="primary" disabled={busy} onClick={() => void submit()}>{busy ? 'Guardando evento…' : 'Confirmar creación de evento'}</button></div></section>}
  </Modal>
}
