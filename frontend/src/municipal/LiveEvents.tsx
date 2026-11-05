import { useCallback, useState } from 'react'
import type { Api } from '../api'
import MapView from '../MapView'
import Photos from '../Photos'
import { datePeru, numberText, shortId, stateLabel } from '../format'
import type { BackendService } from './backendService'
import type { EventState } from './backendTypes'
import { eventStates, JsonDetails, Pager } from './backendUi'
import { Badge, Empty, ErrorBox, Loading, Modal, useData } from './ui'
import CreateEvent from './CreateEvent'

function EventDetail({ api, service, id, close }: { api: Api; service: BackendService; id: string; close: () => void }) {
  const [offset, setOffset] = useState(0)
  const [photoId, setPhotoId] = useState<string | null>(null)
  const load = useCallback(async (signal: AbortSignal) => {
    const [event, reports] = await Promise.all([service.event(id, signal), service.eventReports(id, { offset }, signal)])
    return { event, reports }
  }, [service, id, offset])
  const { data, loading, error, retry } = useData(load)
  return <Modal title={'Detalle de evento ' + shortId(id)} close={close}>
    {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}
    {data && <>
      <div className="toolbar"><span className="identifier">{data.event.id}</span><Badge status={data.event.state} /></div>
      <p>{data.event.intervention_type || 'Intervención por definir'}</p>
      <p>Ubicación: {data.event.latitude}, {data.event.longitude}</p>
      <p>Creado: {datePeru(data.event.created_at)} · Cierre: {datePeru(data.event.closed_at)}</p>
      <p>Prioridad: {numberText(data.event.priority?.score)} · Versión: {data.event.priority?.version || 'No disponible'}</p>
      {data.event.priority && <JsonDetails value={data.event.priority.factors} />}
      <p className="hint">Sin información de restricciones; no implica acceso verificado.</p>
      <MapView events={[data.event]} reports={data.reports} onReportSelect={setPhotoId} />
      <div className="map-legend"><span>◆ Evento</span><span>● Observación ciudadana</span></div>
      <h3>Reportes asociados ({data.event.report_count})</h3>
      {!data.reports.length && <Empty title="No hay reportes asociados en esta página" />}
      {data.reports.map((report) => <article className="report" key={report.id}>
        <strong>{report.description}</strong><p><Badge status={report.status} /></p>
        <p className="hint">Reporte: {report.id}<br />Observado: {datePeru(report.observed_at)} · Registrado: {datePeru(report.created_at)}</p>
        {report.waste_type && <p>Residuo: {report.waste_type}</p>}
        <button aria-expanded={photoId === report.id} onClick={() => setPhotoId(photoId === report.id ? null : report.id)}>Ver fotografías del reporte</button>
        {photoId === report.id && <Photos api={api} reportId={report.id} canUpload={false} />}
      </article>)}
      <Pager label="reportes asociados" offset={offset} count={data.reports.length} loading={loading} change={(page) => { setOffset(page); setPhotoId(null) }} />
    </>}
  </Modal>
}

export default function LiveEvents({ api, service }: { api: Api; service: BackendService }) {
  const [state, setState] = useState<EventState | ''>('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const load = useCallback((signal: AbortSignal) => service.events({ offset, state: state || undefined }, signal), [service, state, offset])
  const { data, loading, error, retry } = useData(load)
  return <>
    <div className="page-heading"><div><span className="eyebrow">Eventos de FastAPI</span><h2>Eventos o puntos de atención</h2><p>Consulta las acumulaciones registradas y sus observaciones asociadas.</p></div><div className="actions"><button className="primary" onClick={() => setCreating(true)}>Crear evento manual</button><button disabled={loading} onClick={retry}>Actualizar eventos</button></div></div>
    <section className="panel">
      <label className="compact-field">Estado de eventos<select value={state} onChange={(e) => { setState(e.target.value as EventState | ''); setOffset(0) }}><option value="">Todos</option>{eventStates.map((value) => <option value={value} key={value}>{stateLabel(value)}</option>)}</select></label>
      {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}
      {data && <><MapView events={data} onEventSelect={setSelected} /><p className="hint">El mapa muestra esta página. La cercanía no crea agrupaciones.</p></>}
    </section>
    {data && <>
      {!data.length && <Empty title="No hay eventos con ese filtro" />}
      <div className="card-grid">{data.map((event) => <article className={'panel event-card ' + (event.state === 'cerrado' ? 'closed' : '')} key={event.id}>
        <div className="toolbar"><span className="eyebrow">Evento {shortId(event.id)}</span><Badge status={event.state} /></div>
        <h3>{event.intervention_type || 'Intervención por definir'}</h3>
        <p>{event.report_count} {event.report_count === 1 ? 'reporte asociado' : 'reportes asociados'}</p>
        <p className="hint">{event.latitude}, {event.longitude}<br />Creado: {datePeru(event.created_at)}</p>
        <p>Prioridad: {numberText(event.priority?.score)}</p>
        {event.closed_at && <p>Cierre: {datePeru(event.closed_at)}</p>}
        <button onClick={() => setSelected(event.id)}>Abrir evento {shortId(event.id)}</button>
      </article>)}</div>
      <Pager label="eventos" offset={offset} count={data.length} loading={loading} change={setOffset} />
    </>}
    {selected && <EventDetail key={selected} api={api} service={service} id={selected} close={() => setSelected(null)} />}
    {creating && <CreateEvent service={service} close={() => { setCreating(false); retry() }} saved={(id) => { setCreating(false); retry(); setSelected(id) }} />}
  </>
}
