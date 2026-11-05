import { useCallback, useRef, useState } from 'react'
import { ApiError } from '../api'
import { datePeru, shortId } from '../format'
import type { BackendService } from './backendService'
import type { DecisionCommand, DecisionDto, DecisionIntent, DecisionKindDto, GroupingDto } from './backendTypes'
import { editable, JsonDetails, Pager } from './backendUi'
import { Badge, Empty, ErrorBox, Loading, Modal, useData } from './ui'

const names: Record<DecisionKindDto, string> = { agrupar: 'Confirmar agrupación', separar: 'Separar reporte', mantener_separado: 'Mantener separados', revisar: 'Registrar revisión' }
const operations: Record<string, string> = { confirm: 'Confirmación', reassign: 'Corrección de asociación', separate: 'Separación', keep_separate: 'Mantener separados', review: 'Revisión pendiente' }

function DecisionDetails({ item, close }: { item: DecisionDto; close: () => void }) {
  return <Modal title="Detalle de decisión" close={close}>
    <p className="identifier">{item.id}</p><h3>{item.operation ? operations[item.operation] || item.operation : names[item.decision]}</h3>
    <p>Reporte: {item.report_id}</p><p>Evento candidato: {item.candidate_event_id || 'Sin candidato'}</p>
    <p>Evento anterior: {item.previous_event_known ? item.previous_event_id || 'Sin asociación' : 'No consta en este registro histórico'}</p>
    <p>Evento resultante: {item.resulting_event_id || 'Sin asociación'}</p>
    <p>Responsable: {item.decided_by || 'No registrado'}<br />Fecha: {datePeru(item.decided_at)}</p>
    {item.notes && <p>Observaciones: {item.notes}</p>}<p>Configuración: {item.config_version || 'Sin versión'}</p><JsonDetails value={item.factors} />
  </Modal>
}

function Review({ service, reportId, intent, setIntent, changed }: {
  service: BackendService; reportId: string; intent: DecisionIntent | null
  setIntent: (value: DecisionIntent | null) => void; changed: () => void
}) {
  const [revision, setRevision] = useState(0)
  const [candidateOffset, setCandidateOffset] = useState(0)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [candidateId, setCandidateId] = useState('')
  const [notes, setNotes] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const [decision, setDecision] = useState<DecisionDto | null>(null)
  const lock = useRef(false)
  const load = useCallback(async (signal: AbortSignal) => {
    const [relation, candidates, history] = await Promise.all([
      service.relation(reportId, signal), service.candidates(reportId, { offset: candidateOffset }, signal),
      service.decisions({ report_id: reportId, offset: historyOffset }, signal),
    ])
    return { relation, candidates, history }
  }, [service, reportId, candidateOffset, historyOffset, revision])
  const { data, loading, error: readError, retry } = useData(load)
  const ownIntent = intent?.command.report_id === reportId ? intent : null
  function refresh() { setRevision((v) => v + 1); changed() }
  function prepare(kind: DecisionKindDto) {
    if (!data || intent) return
    const relation = data.relation
    const command: DecisionCommand = { operation_id: crypto.randomUUID(), report_id: reportId, decision: kind,
      candidate_event_id: kind === 'separar' ? null : candidateId,
      expected_event_id: relation.event_id, expected_decision_id: relation.last_decision_id, notes: notes.trim() || null }
    setError(''); setMessage('')
    setIntent({ command, stage: 'prepared', error: '', notFound: false })
  }
  async function send() {
    if (!ownIntent || lock.current || !['prepared', 'uncertain'].includes(ownIntent.stage)) return
    if (ownIntent.stage === 'uncertain' && !ownIntent.notFound) return
    lock.current = true
    const command = ownIntent.command
    setIntent({ command, stage: 'sending', error: '', notFound: false })
    try {
      const result = await service.decide(command)
      setIntent(null); setDecision(result.decision); setCandidateId(''); setNotes('')
      setMessage(result.replayed ? 'La operación ya estaba registrada. Se recuperó sin repetir la escritura.' : 'Decisión guardada. El reporte original conserva su estado.')
      refresh()
    } catch (err) {
      const status = err instanceof ApiError ? err.status : null
      const stage = status === 409 ? 'conflict' : status === null || status >= 500 ? 'uncertain' : 'rejected'
      setIntent({ command, stage, error: err instanceof Error ? err.message : 'No se pudo completar la petición.', notFound: false })
    } finally { lock.current = false }
  }
  async function checkOperation() {
    if (!ownIntent || lock.current) return
    lock.current = true; setChecking(true)
    try {
      const item = await service.decision(ownIntent.command.operation_id)
      if (item.report_id !== reportId) throw new Error('El identificador pertenece a otro reporte. Revisa el historial antes de continuar.')
      setIntent(null); setDecision(item); setMessage('Operación encontrada en el historial. No se reenviará la escritura.'); refresh()
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setIntent({ ...ownIntent, notFound: true, error: 'La operación todavía no aparece. Puedes volver a consultar o reenviar exactamente el mismo comando.' })
      else setIntent({ ...ownIntent, error: err instanceof Error ? err.message : 'No se pudo comprobar la operación.' })
    } finally { lock.current = false; setChecking(false) }
  }
  async function viewDecision(id: string) {
    if (lock.current) return
    lock.current = true; setError('')
    try { setDecision(await service.decision(id)) }
    catch (err) { setError(err instanceof Error ? err.message : 'No se pudo consultar la decisión.') }
    finally { lock.current = false }
  }
  return <section className="panel grouping-review" aria-label="Revisión del reporte seleccionado">
    <div className="toolbar"><h3>Revisar relación</h3><button disabled={loading || Boolean(intent)} onClick={retry}>Actualizar relación</button></div>
    {loading && <Loading />}{readError && <ErrorBox message={readError} retry={retry} />}{error && <ErrorBox message={error} />}{message && <p className="notice success" role="status">{message}</p>}
    {data && <>
      <div className="comparison"><div><span className="eyebrow">Reporte original</span><h3>{data.relation.report.description}</h3><Badge status={data.relation.report.status} /><p className="hint">{reportId}<br />Observado: {datePeru(data.relation.report.observed_at)}</p></div>
        <div><span className="eyebrow">Relación actual</span><h3>{data.relation.event ? data.relation.event.intervention_type || 'Evento ' + shortId(data.relation.event.id) : 'Sin asociación'}</h3>
          {data.relation.event && <><Badge status={data.relation.event.state} /><p className="hint">{data.relation.event.id}</p></>}
          <p>{data.relation.pending_review ? 'Última decisión: requiere revisión' : 'Sin revisión pendiente en la última decisión'}</p>
        </div></div>
      <p className="notice">Candidatos de selección manual. FastAPI no ha generado sugerencias de IA ni puntuaciones para esta revisión.</p>
      <label>Evento candidato<select value={candidateId} disabled={Boolean(intent)} onChange={(e) => setCandidateId(e.target.value)}>
        <option value="">Selecciona un evento</option>
        {data.relation.event && <option value={data.relation.event.id}>Evento actual · {shortId(data.relation.event.id)} (para revisión)</option>}
        {data.candidates.candidates.map((e) => <option key={e.id} value={e.id}>{e.intervention_type || 'Evento'} · {shortId(e.id)} · {e.state}</option>)}
      </select></label>
      {!data.candidates.candidates.length && <p className="hint">No hay candidatos disponibles en esta página.</p>}
      <Pager label="candidatos" offset={candidateOffset} count={data.candidates.candidates.length} loading={loading || Boolean(intent)} change={(offset) => { setCandidateOffset(offset); setCandidateId('') }} />
      <label>Observaciones de la decisión<textarea value={notes} maxLength={2000} rows={3} disabled={Boolean(intent)} onChange={(e) => setNotes(e.target.value)} /></label>
      {!editable(data.relation.event) && <p className="notice warning">La asociación pertenece a un evento no editable. Puedes registrar una revisión, pero no cambiar el vínculo.</p>}
      <div className="actions">
        <button disabled={Boolean(intent) || !candidateId || candidateId === data.relation.event_id || !editable(data.relation.event)} onClick={() => prepare('agrupar')}>{data.relation.event_id ? 'Corregir asociación' : 'Confirmar agrupación'}</button>
        <button disabled={Boolean(intent) || !data.relation.event_id || !editable(data.relation.event)} onClick={() => prepare('separar')}>Separar reporte</button>
        <button disabled={Boolean(intent) || !candidateId || candidateId === data.relation.event_id} onClick={() => prepare('mantener_separado')}>Mantener separados</button>
        <button disabled={Boolean(intent) || !candidateId} onClick={() => prepare('revisar')}>Registrar revisión</button>
      </div>
      <h3>Historial de decisiones</h3>
      {!data.history.length ? <Empty title="Todavía no hay decisiones para este reporte" /> : <ol className="timeline">{data.history.map((item) => <li key={item.id}>
        <strong>{item.operation ? operations[item.operation] || item.operation : names[item.decision]}</strong>
        <p>Responsable: {item.decided_by || 'No registrado'} · {datePeru(item.decided_at)}</p>
        {item.notes && <p>{item.notes}</p>}<button onClick={() => void viewDecision(item.id)}>Ver decisión {shortId(item.id)}</button>
      </li>)}</ol>}
      <Pager label="decisiones" offset={historyOffset} count={data.history.length} loading={loading || Boolean(intent)} change={setHistoryOffset} />
    </>}
    {ownIntent && <Modal title="Confirmar decisión municipal" close={() => { if (['prepared', 'rejected'].includes(ownIntent.stage)) setIntent(null) }}>
      <h3>{ownIntent.command.decision === 'agrupar' && ownIntent.command.expected_event_id ? 'Corregir asociación' : names[ownIntent.command.decision]}</h3>
      <p>Reporte: {ownIntent.command.report_id}<br />Evento anterior: {ownIntent.command.expected_event_id || 'Sin asociación'}<br />Candidato: {ownIntent.command.candidate_event_id || 'Sin candidato'}</p>
      {ownIntent.command.notes && <p>Observaciones: {ownIntent.command.notes}</p>}
      <p className="hint">Operación: <span className="identifier">{ownIntent.command.operation_id}</span></p>
      {ownIntent.error && <ErrorBox message={ownIntent.error} />}
      {ownIntent.stage === 'conflict' && <p>La relación o su revisión cambiaron. Debes descartar este comando, consultar el estado actual y preparar otra decisión.</p>}
      {ownIntent.stage === 'uncertain' && <p>El resultado puede haberse guardado. Comprueba el identificador antes de reenviar. Se conserva el cuerpo y no se genera otra operación.</p>}
      <div className="actions">
        {['prepared', 'rejected'].includes(ownIntent.stage) && <button onClick={() => setIntent(null)}>Cancelar</button>}
        {ownIntent.stage === 'prepared' && <button className="primary" onClick={() => void send()}>Confirmar decisión</button>}
        {ownIntent.stage === 'sending' && <button disabled>Guardando decisión…</button>}
        {ownIntent.stage === 'conflict' && <button onClick={() => { setIntent(null); setCandidateId(''); refresh() }}>Descartar y actualizar relación</button>}
        {ownIntent.stage === 'uncertain' && <>
          <button disabled={checking} onClick={() => void checkOperation()}>Comprobar operación</button>
          {ownIntent.notFound && <button className="primary" disabled={checking} onClick={() => void send()}>Reintentar el mismo comando</button>}
        </>}
      </div>
    </Modal>}
    {decision && <DecisionDetails item={decision} close={() => setDecision(null)} />}
  </section>
}

export default function LiveGroupings({ service, intent, setIntent }: {
  service: BackendService; intent: DecisionIntent | null; setIntent: (value: DecisionIntent | null) => void
}) {
  const [offset, setOffset] = useState(0)
  const [linked, setLinked] = useState('all')
  const [pending, setPending] = useState(false)
  const [selected, setSelected] = useState<string | null>(intent?.command.report_id || null)
  const [revision, setRevision] = useState(0)
  const load = useCallback((signal: AbortSignal) => service.groupings({ offset, linked: linked === 'all' ? undefined : linked === 'yes', pending_review: pending ? true : undefined }, signal), [service, offset, linked, pending, revision])
  const { data, loading, error, retry } = useData(load)
  return <>
    <div className="page-heading"><div><span className="eyebrow">Revisión municipal de FastAPI</span><h2>Revisión de agrupaciones</h2><p>Confirma, corrige o separa relaciones con trazabilidad. Agrupar no significa atender un reporte.</p></div><button disabled={loading || Boolean(intent)} onClick={retry}>Actualizar agrupaciones</button></div>
    <section className="panel"><div className="fields"><label>Relaciones<select value={linked} disabled={Boolean(intent)} onChange={(e) => { setLinked(e.target.value); setOffset(0) }}><option value="all">Todos los reportes</option><option value="yes">Con asociación</option><option value="no">Sin asociación</option></select></label>
      <label className="check-row"><input type="checkbox" checked={pending} disabled={Boolean(intent)} onChange={(e) => { setPending(e.target.checked); setOffset(0) }} />Última decisión pendiente de revisión</label></div>
      {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}
      {data && <>
        {!data.length && <Empty title="No hay reportes para revisar con este filtro" />}
        <div className="report-list grouping-list">{data.map((item: GroupingDto) => <article className="report" key={item.report.id}>
          <strong>{item.report.description}</strong><p><Badge status={item.report.status} /> · {item.event_id ? 'Evento ' + shortId(item.event_id) : 'Sin asociación'}</p>
          <p className="hint">Reporte: {item.report.id}</p>
          <button disabled={Boolean(intent) && intent?.command.report_id !== item.report.id} onClick={() => setSelected(item.report.id)}>Revisar relación {shortId(item.report.id)}</button>
        </article>)}</div><Pager label="relaciones" offset={offset} count={data.length} loading={loading || Boolean(intent)} change={setOffset} />
      </>}
    </section>
    {selected && <Review key={selected} service={service} reportId={selected} intent={intent} setIntent={setIntent} changed={() => setRevision((v) => v + 1)} />}
  </>
}
