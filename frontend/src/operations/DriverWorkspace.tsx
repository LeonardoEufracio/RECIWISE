import { useCallback, useMemo, useState } from 'react'
import type { Api } from '../api'
import { datePeru, shortId } from '../format'
import { Pager } from '../municipal/backendUi'
import { Badge, Empty, ErrorBox, Loading, useData } from '../municipal/ui'
import OperationConfirm from './OperationConfirm'
import RouteDetails from './RouteDetails'
import { createOperationsService, type OperationsService } from './service'
import { actionNames, type Intent, type OperationAction, type RouteDetail } from './types'
import './driver.css'

function Assignment({ id, service, close, changed }: { id: string; service: OperationsService; close: () => void; changed: () => void }) {
  const load = useCallback((signal: AbortSignal) => service.detail(id, signal), [service, id])
  const data = useData(load)
  const [intent, setIntent] = useState<Intent | null>(null)
  const [notes, setNotes] = useState('')
  const [incidentType, setIncidentType] = useState('')
  const [error, setError] = useState('')
  function prepare(route: RouteDetail, action: OperationAction, stopId?: string) {
    if (intent) return
    setError('')
    if (['incident', 'not_attended'].includes(action) && notes.trim().length < 3) { setError('Escribe el motivo de la incidencia o de la no atención.'); return }
    if (action === 'incident' && incidentType.trim().length < 2) { setError('Escribe el tipo de incidencia.'); return }
    setIntent({ scope: 'driver', routeId: route.id, stopId, stage: 'prepared', error: '', notFound: false, command: { operation_id: crypto.randomUUID(), expected_status: route.status, expected_revision: route.revision, notes: notes.trim() || null, action: action as Intent['command']['action'], ...(action === 'incident' ? { incident_type: incidentType.trim() } : {}) } })
  }
  function refresh() { setIntent(null); setNotes(''); setIncidentType(''); data.retry(); changed() }
  const route = data.data
  const next = route?.stops.find((s) => s.status === 'pendiente')
  return <section className="driver-assignment">
    <button disabled={!!intent} onClick={close}>Volver a mis recorridos</button>
    {data.loading && <Loading />}{data.error && <ErrorBox message={data.error} retry={data.retry} />}
    {route && <><RouteDetails route={route} />
      {route.approval_verified && route.status === 'aprobada' && <section className="panel"><h3>Preparar salida</h3><p>Solo se permite iniciar durante el horario del turno y con los recursos disponibles.</p><button className="primary" onClick={() => prepare(route, 'start')}>Revisar inicio de recorrido</button></section>}
      {route.approval_verified && route.status === 'en_ejecucion' && <section className="panel driver-controls">
        <h3>{next ? 'Siguiente parada: ' + next.order : 'Todas las paradas registradas'}</h3>
        {error && <ErrorBox message={error} />}
        {next && <><p className="identifier">Evento {next.event_id}</p><label>Observación o motivo de no atención<textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} /></label><label>Tipo de incidencia (si corresponde)<input value={incidentType} maxLength={80} onChange={(e) => setIncidentType(e.target.value)} placeholder="Ej.: acceso bloqueado" /></label>
          <div className="driver-actions">{(['attend', 'incident', 'not_attended'] as const).map((a) => <button key={a} disabled={!!intent} className={a === 'attend' ? 'primary' : ''} onClick={() => prepare(route, a, next.id)}>{actionNames[a]}</button>)}</div><p className="hint">Los registros se guardan en orden. Una incidencia o no atención requiere un motivo.</p></>}
        {!next && <button className="primary" onClick={() => prepare(route, 'finish')}>Revisar fin de recorrido</button>}
      </section>}
      {route.status === 'finalizada' && <p className="notice success">Recorrido finalizado. Los registros permanecen disponibles para consulta.</p>}
    </>}
    {intent && <OperationConfirm key={intent.command.operation_id} service={service} initial={intent} close={() => { setIntent(null); data.retry() }} saved={refresh} />}
  </section>
}
export default function DriverWorkspace({ api }: { api: Api }) {
  const service = useMemo(() => createOperationsService(api, 'driver'), [api])
  const [selected, setSelected] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const load = useCallback((signal: AbortSignal) => service.routes(offset, undefined, signal), [service, offset])
  const data = useData(load)
  return <div className="driver-workspace">
    <div className="page-heading"><div><span className="eyebrow">RECIWISE · Chofer</span><h2>Mis recorridos</h2><p>Solo rutas asignadas a tu perfil y aprobadas con procedencia verificada.</p></div></div>
    {selected ? <Assignment key={selected} id={selected} service={service} close={() => setSelected(null)} changed={data.retry} /> : <>
      <button disabled={data.loading} onClick={data.retry}>Actualizar mis recorridos</button>
      {data.loading && <Loading />}{data.error && <ErrorBox message={data.error} retry={data.retry} />}
      {data.data && <>{!data.data.length && <Empty title="No tienes recorridos autorizados"><span>Las propuestas y los resultados de prueba no son rutas operativas. La aprobación depende de un proveedor verificado.</span></Empty>}
        <div className="card-grid">{data.data.map((r) => <article className="panel" key={r.id}><Badge status={r.status} /><h3>{r.vehicle_label}</h3><p>{datePeru(r.starts_at)}<br />hasta {datePeru(r.ends_at)}</p><button className="primary" onClick={() => setSelected(r.id)}>Abrir mi recorrido {shortId(r.id)}</button></article>)}</div><Pager label="mis recorridos" offset={offset} count={data.data.length} loading={data.loading} change={setOffset} /></>}
    </>}
  </div>
}
