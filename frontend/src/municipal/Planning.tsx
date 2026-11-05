import { useCallback, useState, type FormEvent } from 'react'
import type { DemoData, PlanningInput, RouteProposal } from './model'
import type { MunicipalService } from './services'
import { validatePlanning } from './demo'
import { datePeru, numberText, shortId } from '../format'
import { Badge, Empty, ErrorBox, Loading, Modal, useAction, useData } from './ui'
import RouteMap from './RouteMap'

const blank: PlanningInput = { shift_id: '', vehicle_id: '', driver_id: '', departure_site_id: '', disposal_site_id: '', event_ids: [] }
export default function Planning({ service, demo, generate, approve }: {
  service: MunicipalService; demo: DemoData | null; generate: (input: PlanningInput) => void; approve: (id: string) => void
}) {
  const load = useCallback(async (signal: AbortSignal) => {
    if (demo) return demo
    const [vehicles, sites, shifts] = await Promise.all([service.vehicles(signal), service.sites(signal), service.shifts(signal)])
    return { vehicles, sites, shifts, events: [], proposals: [] }
  }, [service, demo])
  const { data, loading, error, retry } = useData(load)
  const [input, setInput] = useState<PlanningInput>(blank)
  const [confirm, setConfirm] = useState<'generate' | RouteProposal | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const action = useAction()
  const proposal = data?.proposals.find((p) => p.id === selected) || data?.proposals[0]
  const drivers = [...new Set(data?.shifts.map((s) => s.driver_id) || [])]
  function selectShift(id: string) {
    const shift = data?.shifts.find((s) => s.id === id)
    setInput(shift ? { shift_id: shift.id, vehicle_id: shift.vehicle_id, driver_id: shift.driver_id, departure_site_id: shift.departure_site_id, disposal_site_id: shift.disposal_site_id, event_ids: input.event_ids } : blank)
  }
  function requestProposal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void action.run(async () => {
      if (!data || !demo) throw new Error('La generación de propuestas aún no está habilitada.')
      validatePlanning(data, input); setConfirm('generate')
    })
  }
  return <>
    <div className="page-heading"><div><span className="eyebrow">Preparación operativa</span><h2>Planificación de rutas</h2><p>Elige un turno y revisa sus recursos antes de solicitar una propuesta.</p></div></div>
    {!demo && <div className="notice info">Puedes consultar y preparar recursos reales. Los eventos, la generación y la aprobación de propuestas aún no están habilitados. Ninguna solicitud de ruta se enviará.</div>}
    {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}{action.error && <ErrorBox message={action.error} />}{action.message && <p role="status" className="notice success">{action.message}</p>}
    {data && <>
      <form className="panel" onSubmit={requestProposal}><h3>Preparar solicitud</h3>
        <fieldset disabled={action.busy}>
          <label>Jornada o turno<select required value={input.shift_id} onChange={(e) => selectShift(e.target.value)}><option value="">Selecciona un turno</option>{data.shifts.map((s) => <option key={s.id} value={s.id} disabled={s.status !== 'programado'}>{datePeru(s.starts_at)} · {shortId(s.id)} · {s.status}</option>)}</select></label>
          {!data.shifts.length && <p className="hint">No hay turnos disponibles. La creación de jornadas se realiza por separado en Recursos operativos.</p>}
          <div className="fields"><label>Vehículo<select required value={input.vehicle_id} onChange={(e) => setInput({ ...input, vehicle_id: e.target.value })}><option value="">Selecciona un vehículo</option>{data.vehicles.map((v) => <option key={v.id} value={v.id} disabled={!v.available}>{v.label}{!v.available ? ' — No disponible' : ''}</option>)}</select></label>
            <label>Chofer del turno<select required value={input.driver_id} onChange={(e) => setInput({ ...input, driver_id: e.target.value })}><option value="">Selecciona un chofer conocido</option>{drivers.map((id) => <option key={id} value={id}>Chofer · {shortId(id)}</option>)}</select></label></div>
          <p className="hint">Capacidad registrada: {data.vehicles.find((v) => v.id === input.vehicle_id)?.capacity_kg == null ? 'No especificada' : numberText(data.vehicles.find((v) => v.id === input.vehicle_id)?.capacity_kg, ' kg')}. No se infiere carga desde la descripción.</p>
          <div className="fields"><label>Punto de salida<select required value={input.departure_site_id} onChange={(e) => setInput({ ...input, departure_site_id: e.target.value })}><option value="">Selecciona la salida</option>{data.sites.filter((s) => s.active && ['salida', 'ambos'].includes(s.site_type)).map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label>
            <label>Punto de descarga<select required value={input.disposal_site_id} onChange={(e) => setInput({ ...input, disposal_site_id: e.target.value })}><option value="">Selecciona la descarga</option>{data.sites.filter((s) => s.active && ['descarga', 'ambos'].includes(s.site_type)).map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label></div>
          <p className="hint">Los recursos deben coincidir con el turno. El listado de choferes se limita a los identificadores de turnos disponibles; no se inventan nombres ni perfiles.</p>
          <fieldset className="choice-list"><legend>Eventos candidatos de atención</legend>
            {!data.events.length && <p className="hint">{demo ? 'Sin eventos candidatos.' : 'La consulta de eventos espera integración con el servicio.'}</p>}
            {data.events.map((e) => <label key={e.id} className="check-row"><input type="checkbox" checked={input.event_ids.includes(e.id)} disabled={['cerrado', 'descartado', 'atendido'].includes(e.state)} onChange={(v) => setInput({ ...input, event_ids: v.target.checked ? [...input.event_ids, e.id] : input.event_ids.filter((id) => id !== e.id) })} /><span>Evento {shortId(e.id)} · {e.intervention_type || 'Intervención por definir'} <Badge status={e.state} /></span></label>)}
          </fieldset>
          <button className="primary" disabled={!demo || action.busy || !data.events.length}>{demo ? 'Generar propuesta simulada' : 'Solicitar propuesta (pendiente)'}</button>
          {!demo && <p className="hint">La acción se habilitará cuando exista un servicio autorizado de propuestas.</p>}
        </fieldset>
      </form>
      <section className="panel"><div className="toolbar"><h3>Propuestas para revisar</h3>{data.proposals.length > 1 && <label className="compact-field">Propuesta<select value={proposal?.id || ''} onChange={(e) => setSelected(e.target.value)}>{data.proposals.map((p) => <option key={p.id} value={p.id}>{shortId(p.id)}</option>)}</select></label>}</div>
        {!proposal ? <Empty title="Aún no hay propuestas">{demo ? 'Elige un turno y eventos abiertos para explorar una propuesta ficticia.' : 'Las propuestas aparecerán cuando se integre el servicio de planificación.'}</Empty> : <>
          <div className="toolbar"><span className="identifier">{proposal.id}</span><Badge status={proposal.status} /></div>
          <div className="notice warning">PROPUESTA SIMULADA — NO OPERATIVA. No asigna trabajo a un chofer ni representa optimización vial.</div>
          <dl className="metrics"><div><dt>Distancia estimada</dt><dd>{numberText(proposal.distance_m, ' m')}</dd></div><div><dt>Tiempo estimado</dt><dd>{numberText(proposal.duration_seconds == null ? null : proposal.duration_seconds / 60, ' min')}</dd></div><div><dt>Fuente de matriz</dt><dd>{proposal.matrix_source || 'Sin matriz vial real'}</dd></div></dl>
          <p className="hint">Algoritmo/adaptador: {proposal.algorithm_version} · Turno {shortId(proposal.shift_id)}</p>
          <RouteMap proposal={proposal} events={data.events} />
          <div className="comparison"><div><h4>Orden de paradas</h4><ol>{proposal.stops.map((s) => <li key={s.event_id}>Evento {shortId(s.event_id)} · {data.events.find((e) => e.id === s.event_id)?.intervention_type || 'Por definir'}</li>)}</ol></div><div><h4>Eventos excluidos y motivos</h4>{proposal.excluded.length ? <ul>{proposal.excluded.map((e) => <li key={e.event_id}>{shortId(e.event_id)}: {e.reason}</li>)}</ul> : <p>No hay exclusiones en este ejemplo.</p>}</div></div>
          <h4>Limitaciones</h4><ul>{proposal.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          <button type="button" disabled={!demo || proposal.status === 'aprobada' || action.busy} onClick={() => setConfirm(proposal)}>Aprobar solo en demostración</button>
          {proposal.status === 'aprobada' && <p className="hint">Revisión simulada aprobada, sin asignación operativa ni persistencia.</p>}
        </>}
      </section>
    </>}
    {confirm && <Modal title={confirm === 'generate' ? 'Confirmar propuesta de demostración' : 'Confirmar aprobación simulada'} close={() => !action.busy && setConfirm(null)}>
      <p>La operación existe únicamente en memoria de esta demostración y no se envía al backend. No se generan cálculos de IA ni se asigna una ruta real.</p>
      <div className="actions"><button disabled={action.busy} onClick={() => setConfirm(null)}>Cancelar</button><button className="primary" disabled={action.busy} onClick={() => void action.run(async () => { if (confirm === 'generate') { generate(input); setSelected(null) } else approve(confirm.id); setConfirm(null); return 'Simulación actualizada. No se ha modificado la base de datos.' })}>Confirmar simulación</button></div>
    </Modal>}
  </>
}
