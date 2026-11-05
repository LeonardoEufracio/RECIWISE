import { useState } from 'react'
import type { DemoData } from './model'
import { datePeru, numberText, shortId } from '../format'
import { Badge, Empty, Pending } from './ui'

export default function Priorities({ data }: { data: DemoData | null }) {
  const [sort, setSort] = useState('date')
  if (!data) return <Pending feature="Priorización de eventos" />
  const available = data.events.some((e) => e.priority?.score != null)
  const events = [...data.events].filter((e) => !['cerrado', 'descartado', 'atendido'].includes(e.state))
    .sort((a, b) => sort === 'priority' ? (b.priority?.score ?? -Infinity) - (a.priority?.score ?? -Infinity) : Date.parse(a.created_at) - Date.parse(b.created_at))
  return <>
    <div className="page-heading"><div><span className="eyebrow">Resultados para revisar</span><h2>Priorización</h2><p>La interfaz muestra los resultados entregados; no calcula puntuaciones.</p></div></div>
    {!available && <div className="notice info">D3 todavía no ha entregado un cálculo de prioridad para estos ejemplos. Se muestran sin puntuación y ordenados por fecha.</div>}
    <label className="compact-field">Ordenar eventos<select value={sort} onChange={(e) => setSort(e.target.value)}><option value="date">Fecha de creación, más antiguos primero</option><option value="priority" disabled={!available}>Prioridad entregada por el servicio</option></select></label>
    {!events.length && <Empty title="No hay eventos abiertos para priorizar" />}
    <div className="priority-list">{events.map((e) => <article className="panel" key={e.id}><div className="toolbar"><h3>Evento {shortId(e.id)}</h3><Badge status={e.state} /></div>
      <dl className="detail-list"><div><dt>Prioridad</dt><dd>{e.priority?.score == null ? 'Sin cálculo' : numberText(e.priority.score)}</dd></div><div><dt>Intervención</dt><dd>{e.intervention_type || 'Por definir'}</dd></div><div><dt>Ubicación</dt><dd>{e.latitude}, {e.longitude}</dd></div><div><dt>Fecha</dt><dd>{datePeru(e.created_at)}</dd></div></dl>
      <h4>Factores entregados</h4>{e.priority?.factors.length ? <ul>{e.priority.factors.map((f) => <li key={f.label}>{f.label}: {f.value}</li>)}</ul> : <p className="hint">Sin factores calculados disponibles.</p>}
      <h4>Restricciones operativas</h4>{e.restrictions.length ? <ul>{e.restrictions.map((r) => <li key={r}>{r}</li>)}</ul> : <p className="hint">Sin información adicional; no implica acceso verificado.</p>}
      {e.priority?.version && <p className="hint">Versión: {e.priority.version}</p>}
    </article>)}</div>
  </>
}
