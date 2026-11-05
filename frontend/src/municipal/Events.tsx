import { useState } from 'react'
import type { DemoData } from './model'
import { datePeru, numberText, shortId } from '../format'
import { Badge, Empty, Modal, Pending } from './ui'
import MapView from '../MapView'

export default function Events({ data }: { data: DemoData | null }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [filter, setFilter] = useState('todos')
  if (!data) return <Pending feature="Eventos o puntos de atención" />
  const events = data.events.filter((e) => filter === 'todos' || (filter === 'cerrados' ? e.state === 'cerrado' : e.state !== 'cerrado'))
  const event = data.events.find((e) => e.id === selected)
  return <>
    <div className="page-heading"><div><span className="eyebrow">Observaciones y acumulaciones</span><h2>Eventos o puntos de atención</h2><p>Un evento puede reunir reportes revisados; la cercanía no los agrupa por sí sola.</p></div></div>
    <section className="panel"><label className="compact-field">Estado de eventos<select value={filter} onChange={(e) => setFilter(e.target.value)}><option value="todos">Todos</option><option value="abiertos">No cerrados</option><option value="cerrados">Cerrados</option></select></label>
      <MapView reports={data.reports} events={events} onEventSelect={setSelected} />
      <div className="map-legend"><span>● Reporte individual</span><span>◆ Evento revisado</span><span>Gris: evento cerrado</span></div>
    </section>
    {!events.length && <Empty title="No hay eventos con ese filtro" />}
    <div className="card-grid">{events.map((e) => <article className={'panel event-card ' + (e.state === 'cerrado' ? 'closed' : '')} key={e.id}>
      <div className="toolbar"><span className="eyebrow">Evento {shortId(e.id)}</span><Badge status={e.state} /></div>
      <h3>{e.intervention_type || 'Intervención por definir'}</h3><p>{e.report_ids.length} {e.report_ids.length === 1 ? 'reporte asociado' : 'reportes asociados'}</p>
      <p className="hint">{e.latitude}, {e.longitude}<br />Creado: {datePeru(e.created_at)}</p>
      <p>Prioridad: {e.priority?.score == null ? 'Sin cálculo de D3' : numberText(e.priority.score)}</p>
      {e.closed_at && <p className="hint">Cerrado: {datePeru(e.closed_at)}</p>}
      <button onClick={() => setSelected(e.id)}>Abrir evento {shortId(e.id)}</button>
    </article>)}</div>
    {event && <Modal title={'Detalle de evento ' + shortId(event.id)} close={() => setSelected(null)}>
      <Badge status={event.state} /><p className="identifier">{event.id}</p><p>{event.intervention_type || 'Sin tipo de intervención'}</p>
      <p>Ubicación: {event.latitude}, {event.longitude}</p><p>Creado: {datePeru(event.created_at)} · Cierre: {datePeru(event.closed_at)}</p>
      <h3>Reportes asociados ({event.report_ids.length})</h3>
      {event.report_ids.map((id) => { const report = data.reports.find((r) => r.id === id); return <article key={id} className="mini-card"><strong>{report?.description || 'Descripción no disponible'}</strong><p className="hint">Reporte: {id}<br />Observado: {datePeru(report?.observed_at)}</p></article> })}
      {!event.report_ids.length && <p>Este ejemplo aún no tiene reportes vinculados.</p>}
    </Modal>}
  </>
}
