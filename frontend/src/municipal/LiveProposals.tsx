import { useCallback, useMemo, useState } from 'react'
import { datePeru, numberText, shortId } from '../format'
import type { BackendService } from './backendService'
import type { OriginDto, ProposalSummaryDto } from './backendTypes'
import { JsonDetails, Pager, snapshotEvents } from './backendUi'
import type { MunicipalService } from './services'
import RouteMap from './RouteMap'
import { Empty, ErrorBox, Loading, Modal, useData } from './ui'

const origins: Record<OriginDto, string> = { pending: 'Pendiente de cálculo', test_fixture: 'Datos de prueba', municipal_unverified: 'Municipal sin verificar', d3: 'Proveedor D3', legacy_unknown: 'Origen histórico desconocido' }
const calculations = { pending: 'Pendiente', completed: 'Calculada', unknown: 'Desconocido' }
function Metrics({ item }: { item: ProposalSummaryDto }) {
  return <dl className="proposal-metrics"><div><dt>Distancia estimada</dt><dd>{item.distance_m === null ? 'No disponible' : numberText(item.distance_m) + ' m'}</dd></div>
    <div><dt>Duración estimada</dt><dd>{item.estimated_duration_seconds === null ? 'No disponible' : numberText(item.estimated_duration_seconds / 60) + ' min'}</dd></div>
    <div><dt>Algoritmo / versión</dt><dd>{item.algorithm_version || 'No disponible'}</dd></div><div><dt>Fuente de matriz</dt><dd>{item.matrix_source || 'No disponible'}</dd></div></dl>
}
function ProposalDetail({ service, id, close }: { service: BackendService; id: string; close: () => void }) {
  const [stopOffset, setStopOffset] = useState(0)
  const [excludedOffset, setExcludedOffset] = useState(0)
  const load = useCallback(async (signal: AbortSignal) => {
    const [detail, stops, excluded] = await Promise.all([service.proposal(id, signal), service.stops(id, { offset: stopOffset }, signal), service.exclusions(id, { offset: excludedOffset }, signal)])
    return { detail, stops, excluded }
  }, [service, id, stopOffset, excludedOffset])
  const { data, loading, error, retry } = useData(load)
  const mapEvents = useMemo(() => data ? snapshotEvents(data.detail) : [], [data])
  const mapProposal = useMemo(() => ({ geometry: data?.detail.geometry_geojson || null, stops: data?.detail.stops || [] }), [data])
  return <Modal title={'Detalle de propuesta ' + shortId(id)} close={close}>
    {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}
    {data && <>
      <p className="identifier">{data.detail.id}</p><p>Estado: {data.detail.status} · Cálculo: {calculations[data.detail.calculation_status]}</p>
      <p className="notice warning"><strong>{origins[data.detail.result_origin]} · NO OPERATIVA.</strong> Esta consulta no aprueba, asigna ni ejecuta una ruta.</p>
      <p>Turno: {data.detail.shift_id}<br />Creada: {datePeru(data.detail.created_at)}</p><Metrics item={data.detail} />
      <h3>Limitaciones</h3>{data.detail.limitations.length ? <ul>{data.detail.limitations.map((value, i) => <li key={i}>{value}</li>)}</ul> : <p>Sin limitaciones declaradas por el proveedor; no implica validación operativa.</p>}
      {!!data.detail.unknowns.length && <><h3>Información desconocida</h3><ul>{data.detail.unknowns.map((value, i) => <li key={i}>{value}</li>)}</ul></>}
      <RouteMap proposal={mapProposal} events={mapEvents} simulated={false} />
      {data.detail.stops.some((stop) => !mapEvents.some((event) => event.id === stop.event_id)) && <p className="notice">Hay paradas sin coordenadas verificables en la instantánea. Se conservan en el listado y no se inventa su ubicación.</p>}
      <h3>Paradas ordenadas ({data.detail.stop_count})</h3>
      {!data.stops.length && <Empty title="No hay paradas en esta página" />}
      <ol className="timeline">{data.stops.map((stop) => <li key={stop.id} value={stop.order}><strong>Parada {stop.order}</strong><p>Evento: {stop.event_id}</p><p>Estado: {stop.status} · Servicio estimado: {stop.estimated_service_minutes === null ? 'No disponible' : numberText(stop.estimated_service_minutes) + ' min'}</p></li>)}</ol>
      <Pager label="paradas" offset={stopOffset} count={data.stops.length} loading={loading} change={setStopOffset} />
      <h3>Eventos excluidos ({data.detail.excluded_count})</h3>
      {!data.excluded.length && <Empty title="No hay exclusiones en esta página" />}
      <ul>{data.excluded.map((item) => <li key={item.event_id}><strong>{item.event_id}</strong><p>Motivo: {item.reason}</p></li>)}</ul>
      <Pager label="exclusiones" offset={excludedOffset} count={data.excluded.length} loading={loading} change={setExcludedOffset} />
      <JsonDetails label="Configuración recibida" value={data.detail.configuration} />
    </>}
  </Modal>
}

export default function LiveProposals({ service, resources }: { service: BackendService; resources: MunicipalService }) {
  const [offset, setOffset] = useState(0)
  const [shift, setShift] = useState('')
  const [calculation, setCalculation] = useState<ProposalSummaryDto['calculation_status'] | ''>('')
  const [origin, setOrigin] = useState<OriginDto | ''>('')
  const [selected, setSelected] = useState<string | null>(null)
  const load = useCallback((signal: AbortSignal) => service.proposals({ offset, shift_id: shift || undefined, calculation_status: calculation || undefined, result_origin: origin || undefined }, signal), [service, offset, shift, calculation, origin])
  const loadResources = useCallback(async (signal: AbortSignal) => {
    const [shifts, vehicles, sites] = await Promise.all([resources.shifts(signal), resources.vehicles(signal), resources.sites(signal)])
    return { shifts, vehicles, sites }
  }, [resources])
  const { data, loading, error, retry } = useData(load)
  const reference = useData(loadResources)
  return <>
    <div className="page-heading"><div><span className="eyebrow">Propuestas de FastAPI · Solo consulta</span><h2>Planificación de rutas</h2><p>Revisa resultados e instantáneas persistidas. No se generan rutas desde el navegador.</p></div><button disabled={loading} onClick={retry}>Actualizar propuestas</button></div>
    <section className="panel"><div className="fields">
      <label>Jornada o turno<select value={shift} onChange={(e) => { setShift(e.target.value); setOffset(0) }}><option value="">Todos los turnos</option>{reference.data?.shifts.map((item) => <option key={item.id} value={item.id}>{datePeru(item.starts_at)} · {reference.data?.vehicles.find((v) => v.id === item.vehicle_id)?.label || shortId(item.vehicle_id)} · {shortId(item.id)}</option>)}</select></label>
      <label>Estado del cálculo<select value={calculation} onChange={(e) => { setCalculation(e.target.value as typeof calculation); setOffset(0) }}><option value="">Todos</option>{Object.entries(calculations).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <label>Procedencia<select value={origin} onChange={(e) => { setOrigin(e.target.value as typeof origin); setOffset(0) }}><option value="">Todas</option>{Object.entries(origins).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
    </div>
      {reference.error && <ErrorBox message={reference.error} retry={reference.retry} />}
      {reference.data && <p className="hint">Recursos consultados: {reference.data.vehicles.length} vehículos, {reference.data.sites.length} sitios y {reference.data.shifts.length} turnos. Una capacidad desconocida no equivale a capacidad ilimitada.</p>}
      <button disabled>Solicitar propuesta (pendiente)</button><p className="hint">La generación requiere un contrato y proveedor D3 verificados. Las propuestas siguen sin autorización operativa.</p>
    </section>
    {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}
    {data && <>
      {!data.length && <Empty title="No hay propuestas con estos filtros" />}
      <div className="card-grid">{data.map((item) => <article className="panel" key={item.id}>
        <span className="eyebrow">Propuesta {shortId(item.id)}</span><h3>{origins[item.result_origin]}</h3>
        <p>Estado: {item.status} · Cálculo: {calculations[item.calculation_status]}</p><p className="notice warning">NO OPERATIVA</p>
        <p>{item.stop_count} paradas · {item.excluded_count} exclusiones<br />Creada: {datePeru(item.created_at)}</p><Metrics item={item} />
        <button onClick={() => setSelected(item.id)}>Abrir propuesta {shortId(item.id)}</button>
      </article>)}</div><Pager label="propuestas" offset={offset} count={data.length} loading={loading} change={setOffset} />
    </>}
    {selected && <ProposalDetail key={selected} service={service} id={selected} close={() => setSelected(null)} />}
  </>
}
