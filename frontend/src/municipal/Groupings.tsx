import { useState } from 'react'
import { datePeru, numberText, shortId } from '../format'
import type { DecisionKind, DemoData, SuggestionKind } from './model'
import { Badge, Empty, ErrorBox, Modal, Pending, useAction } from './ui'

const labels: Record<SuggestionKind, string> = { agrupar_candidato: 'Candidato a agrupar', requiere_revision: 'Requiere revisión', mantener_separado: 'Mantener separado' }
const decisions: Record<DecisionKind, string> = { agrupar: 'Confirmar agrupación', mantener_separado: 'Mantener separados', revisar: 'Enviar a revisión' }
export default function Groupings({ data, decide }: { data: DemoData | null; decide: (id: string, kind: DecisionKind, notes: string) => void }) {
  const [filter, setFilter] = useState('todos')
  const [pending, setPending] = useState<{ id: string; kind: DecisionKind } | null>(null)
  const [notes, setNotes] = useState('')
  const action = useAction()
  if (!data) return <Pending feature="Revisión de agrupaciones" />
  const suggestions = data.suggestions.filter((s) => filter === 'todos' || s.sugerencia === filter)
  return <>
    <div className="page-heading"><div><span className="eyebrow">Decisión municipal</span><h2>Revisión de agrupaciones</h2><p>Compara observaciones y decide si describen el mismo evento.</p></div></div>
    <div className="notice info">Valores ilustrativos de demostración, no resultados de IA. La similitud textual no es una probabilidad de coincidencia.</div>
    {action.error && <ErrorBox message={action.error} />}{action.message && <p className="notice success" role="status">{action.message}</p>}
    <label className="compact-field">Tipo de sugerencia<select value={filter} onChange={(e) => setFilter(e.target.value)}><option value="todos">Todas</option>{Object.entries(labels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    {!suggestions.length && <Empty title="No hay sugerencias con ese filtro" />}
    {suggestions.map((s) => {
      const report = data.reports.find((r) => r.id === s.reporte_nuevo_id)
      const event = data.events.find((e) => e.id === s.evento_candidato_id)
      const decision = data.decisions.find((d) => d.suggestion_id === s.id)
      return <article className="panel suggestion" key={s.id}>
        <div className="toolbar"><span className={'suggestion-tag kind-' + s.sugerencia}>{labels[s.sugerencia]}</span><span className="hint">Caso {shortId(s.id)}</span></div>
        <div className="comparison">
          <div><span className="eyebrow">Reporte nuevo</span><h3>{report?.description || 'Reporte no disponible'}</h3><p className="hint">{s.reporte_nuevo_id}<br />Observado: {datePeru(report?.observed_at)}</p></div>
          <div><span className="eyebrow">Evento candidato</span><h3>{event?.intervention_type || 'Intervención por definir'}</h3>{event && <Badge status={event.state} />}
            {event?.report_ids.map((rid) => <p key={rid}>{data.reports.find((r) => r.id === rid)?.description || 'Sin descripción'}</p>)}
          </div>
        </div>
        <dl className="metrics"><div><dt>Similitud textual</dt><dd>{numberText(s.similitud_texto)}</dd></div><div><dt>Distancia geográfica</dt><dd>{numberText(s.distancia_metros, ' m')}</dd></div><div><dt>Diferencia temporal</dt><dd>{numberText(s.diferencia_horas, ' h')}</dd></div></dl>
        <h4>Motivos de la sugerencia</h4><ul>{s.motivos.map((m) => <li key={m}>{m}</li>)}</ul>
        {s.factores.length > 0 && <dl className="detail-list">{s.factores.map((f) => <div key={f.label}><dt>{f.label}</dt><dd>{f.value}</dd></div>)}</dl>}
        <p className="hint">Configuración: {s.version_configuracion} · Confirmar una relación no significa atender el reporte.</p>
        {decision ? <p className="notice success">Decisión local registrada: {decisions[decision.decision]}</p> : <div className="actions">
          {(Object.keys(decisions) as DecisionKind[]).map((kind) => <button key={kind} type="button"
            disabled={action.busy || !event || !report || (kind === 'agrupar' && event.state === 'cerrado')}
            onClick={() => { setNotes(''); setPending({ id: s.id, kind }) }}>{decisions[kind]}</button>)}
        </div>}
        {event?.state === 'cerrado' && <p className="hint">Evento cerrado: no se permite confirmar una agrupación.</p>}
      </article>
    })}
    <section className="panel"><h3>Historial de decisiones de esta demostración</h3>
      {!data.decisions.length ? <Empty title="Todavía no hay decisiones locales" /> : <ol className="timeline">{[...data.decisions].reverse().map((d) => <li key={d.id}><strong>{decisions[d.decision]}</strong><p>Reporte {shortId(d.report_id)} · Evento {shortId(d.event_id)}</p><p className="hint">{datePeru(d.decided_at)} · Solo memoria de esta demostración</p>{d.notes && <p>{d.notes}</p>}</li>)}</ol>}
    </section>
    {pending && <Modal title={decisions[pending.kind] + ' — simulación'} close={() => !action.busy && setPending(null)}>
      <p>Esta acción cambia únicamente los ejemplos de la sesión. No se envía a la base de datos ni marca un reporte como atendido.</p>
      <label>Motivo de la decisión<textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={1000} rows={3} /></label>
      <div className="actions"><button disabled={action.busy} onClick={() => setPending(null)}>Cancelar</button><button className="primary" disabled={action.busy} onClick={() => void action.run(async () => { decide(pending.id, pending.kind, notes); setPending(null); return 'Decisión simulada registrada en memoria.' })}>Confirmar decisión simulada</button></div>
    </Modal>}
  </>
}
