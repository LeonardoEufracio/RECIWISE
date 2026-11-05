import { useMemo } from 'react'
import { datePeru, numberText, shortId } from '../format'
import RouteMap from '../municipal/RouteMap'
import { Badge } from '../municipal/ui'
import { actionNames, type RouteDetail } from './types'

export default function RouteDetails({ route }: { route: RouteDetail }) {
  const points = useMemo(() => route.stops.flatMap((s) => s.latitude !== null && s.longitude !== null ? [{ id: s.event_id, latitude: s.latitude, longitude: s.longitude }] : []), [route.stops])
  const map = useMemo(() => ({ geometry: route.geometry_geojson, stops: route.stops }), [route.geometry_geojson, route.stops])
  return <>
    <div className="toolbar"><h3>{route.vehicle_label}</h3><Badge status={route.status} /></div>
    <p className="identifier">Ruta {route.id}</p>
    <p className={'notice ' + (route.approval_verified ? 'success' : 'warning')}>{route.approval_verified ? 'Aprobación verificada por el backend.' : 'NO OPERATIVA. La aprobación requiere un proveedor verificado; una etiqueta D3 no la autoriza.'}</p>
    <dl className="proposal-metrics">
      <div><dt>Horario del turno (Perú)</dt><dd>{datePeru(route.starts_at)} — {datePeru(route.ends_at)}</dd></div>
      <div><dt>Chofer asignado</dt><dd className="identifier">{route.driver_id}</dd></div>
      <div><dt>Unidad</dt><dd>{route.vehicle_available ? 'Disponible' : 'No disponible'}</dd></div>
      <div><dt>Turno</dt><dd>{route.shift_status}</dd></div>
      <div><dt>Salida</dt><dd>{route.departure.name}{!route.departure.active && ' · Inactiva'}</dd></div>
      <div><dt>Descarga</dt><dd>{route.disposal.name}{!route.disposal.active && ' · Inactiva'}</dd></div>
      <div><dt>Distancia estimada</dt><dd>{numberText(route.distance_m, ' m')}</dd></div>
      <div><dt>Duración estimada</dt><dd>{route.estimated_duration_seconds === null ? 'No disponible' : numberText(route.estimated_duration_seconds / 60, ' min')}</dd></div>
      <div><dt>Aprobación</dt><dd>{route.approved_by ? shortId(route.approved_by) + ' · ' + datePeru(route.approved_at) : 'Sin aprobación'}</dd></div>
    </dl>
    <RouteMap proposal={map} events={points} simulated={false} execution={route.approval_verified} />
    {route.stops.some((s) => s.latitude === null || s.longitude === null) && <p className="notice warning">Hay paradas sin ubicación en la instantánea. No se inventan coordenadas.</p>}
    <h3>Paradas del recorrido</h3>
    {!route.stops.length && <p>Sin paradas registradas.</p>}
    <ol className="timeline">{route.stops.map((s) => <li value={s.order} key={s.id}><strong>Parada {s.order}</strong> <Badge status={s.status} /><p className="identifier">Evento: {s.event_id}</p><p>{s.latitude !== null ? s.latitude + ', ' + s.longitude : 'Ubicación no disponible'}</p>{s.visited_at && <p>Registrada: {datePeru(s.visited_at)} · {shortId(s.recorded_by || '')}</p>}{s.incidents.map((i) => <div className="notice warning" key={i.id}><strong>{i.incident_type}</strong><p>{i.description}</p></div>)}</li>)}</ol>
    {!!route.excluded_events.length && <><h3>Exclusiones</h3><ul>{route.excluded_events.map((e) => <li key={e.event_id}>{shortId(e.event_id)}: {e.reason}</li>)}</ul></>}
    {!!route.limitations.length && <details><summary>Limitaciones del resultado</summary><ul>{route.limitations.map((s, i) => <li key={i}>{s}</li>)}</ul></details>}
    <details className="panel"><summary>Historial de decisiones y ejecución ({route.history.length})</summary>{!route.history.length && <p>Sin operaciones registradas.</p>}{[...route.history].reverse().map((h) => <article key={h.operation_id} className="report"><strong>{actionNames[h.action]}</strong><p>{datePeru(h.at)} · Responsable {shortId(h.actor_id)}</p><p>{h.previous_status} → {h.resulting_status}</p><p>{h.notes}</p><span className="identifier">{h.operation_id}</span></article>)}</details>
  </>
}
