import { useCallback } from 'react'
import type { DemoData, Section } from './model'
import type { MunicipalService } from './services'
import { reportSnapshot } from './services'
import { datePeru, stateLabel } from '../format'
import { Badge, Empty, ErrorBox, Icon, Loading, useData } from './ui'

export default function Dashboard({ service, demo, navigate }: { service: MunicipalService; demo: DemoData | null; navigate: (section: Section) => void }) {
  const load = useCallback((signal: AbortSignal) => demo
    ? Promise.resolve({ reports: demo.reports, complete: true, fetchedAt: new Date().toISOString() })
    : reportSnapshot(service, signal), [service, demo])
  const { data, loading, error, retry } = useData(load)
  const statuses = ['recibido', 'en_revision', 'programado', 'atendido']
  return <>
    <div className="page-heading"><div><span className="eyebrow">Gestión municipal</span><h2>Dashboard</h2><p>Una vista de los reportes y del trabajo por revisar.</p></div><button onClick={retry} disabled={loading}>Actualizar resumen</button></div>
    {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}
    {data && <>
      <div className="stat-grid">
        <article className="stat-card primary-stat"><span>{data.complete ? 'Total de reportes consultados' : 'Reportes consultados (muestra limitada)'}</span><strong>{data.reports.length}</strong><small>{demo ? 'Ejemplos de demostración' : data.complete ? 'Consulta paginada completa' : 'Hasta 1 000 registros; no es el total global'}</small></article>
        {statuses.map((status) => <article className="stat-card" key={status}><span>{stateLabel(status)}</span><strong>{data.reports.filter((r) => r.status === status).length}</strong><small>{data.complete ? 'En esta consulta' : 'En la muestra consultada'}</small></article>)}
      </div>
      <p className="hint">Consulta: {datePeru(data.fetchedAt)} · Los cambios posteriores requieren actualizar. Las categorías cuentan reportes, no eventos ni ahorro de recursos.</p>
      <div className="dashboard-columns">
        <section className="panel"><div className="toolbar"><h3>Reportes recientes</h3><button onClick={() => navigate('reports')}>Ver reportes y mapa</button></div>
          {!data.reports.length ? <Empty title="Aún no hay reportes" /> : <div className="recent-list">{[...data.reports].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 5).map((r) => <article key={r.id}><div><strong>{r.description}</strong><p className="hint">Registrado: {datePeru(r.created_at)}</p></div><Badge status={r.status} /></article>)}</div>}
        </section>
        <section className="panel quick-actions"><span className="eyebrow">Continuar el trabajo</span><h3>De la observación a la atención</h3>
          <button onClick={() => navigate('reports')}><Icon name="events" /><span>Explorar el mapa de reportes<small>Ubicación, estado y fotografías</small></span><span aria-hidden="true">→</span></button>
          <button onClick={() => navigate('groupings')}><Icon name="groupings" /><span>Revisar agrupaciones<small>{demo ? 'Explorar sugerencias ficticias' : 'Interfaz preparada; servicio pendiente'}</small></span><span aria-hidden="true">→</span></button>
          <button onClick={() => navigate('planning')}><Icon name="planning" /><span>Preparar planificación<small>Turnos, recursos y propuestas</small></span><span aria-hidden="true">→</span></button>
        </section>
      </div>
    </>}
  </>
}
