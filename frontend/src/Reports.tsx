import { useEffect, useState } from 'react'
import type { Api } from './api'
import type { Report } from './types'
import MapView from './MapView'
import Photos from './Photos'
import { datePeru } from './format'
import { Badge } from './municipal/ui'

const PAGE_SIZE = 50

export default function Reports({ api, municipal, revision = 0, createdReportId }: {
  api: Api; municipal: boolean; revision?: number; createdReportId?: string
}) {
  const [reports, setReports] = useState<Report[]>([])
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [statusInput, setStatusInput] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => { setOffset(0); setOpenId(createdReportId ?? null) }, [revision, createdReportId])

  useEffect(() => {
    const controller = new AbortController()
    let current = true
    setLoading(true); setError(''); setReports([])
    const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
    if (municipal && status) query.set('status', status)
    void api<Report[]>(`${municipal ? '/municipal/reports' : '/reports/mine'}?${query}`, { signal: controller.signal })
      .then((data) => { if (current) setReports(data) })
      .catch((err: Error) => { if (current) setError(err.message) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false; controller.abort() }
  }, [api, municipal, offset, status, refresh, revision])

  const visible = reports.filter((r) => r.description.toLocaleLowerCase('es-PE').includes(search.trim().toLocaleLowerCase('es-PE')))
  function selectReport(id: string) { setSelectedId(id); setOpenId(id) }
  return <section className="panel">
    <div className="toolbar">
      <h2>{municipal ? 'Reportes municipales' : 'Mis reportes'}</h2>
      <button type="button" disabled={loading} onClick={() => setRefresh((value) => value + 1)}>Actualizar listado</button>
    </div>
    {municipal && <>
      <form className="toolbar" onSubmit={(event) => { event.preventDefault(); setOffset(0); setStatus(statusInput.trim()); setRefresh((value) => value + 1) }}>
        <label>Filtrar por estado (vacío = todos)<input value={statusInput} maxLength={30} placeholder="Por ejemplo: recibido" onChange={(e) => setStatusInput(e.target.value)} /></label>
        <button disabled={loading}>Aplicar filtro</button>
      </form>
      <label>Buscar por descripción en esta página<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar una observación…" /></label>
      <MapView reports={visible} selectedReportId={selectedId} onReportSelect={selectReport} />
      <p className="hint">El mapa y la búsqueda muestran esta página, con el filtro aplicado. Fechas en hora de Perú (UTC−5).</p>
      <div className="map-legend"><span>● Reporte individual</span><span>La cercanía no implica agrupación.</span></div>
    </>}
    {loading && <p role="status">Consultando reportes…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {!loading && !error && !reports.length && <p>No hay reportes en esta página.</p>}
    {!loading && !error && reports.length > 0 && !visible.length && <p>No hay coincidencias en esta página.</p>}
    <div className="report-list">{visible.map((report) => <article className={'report ' + (selectedId === report.id ? 'selected-report' : '')} key={report.id}>
      <div className="toolbar"><strong>{report.description}</strong><Badge status={report.status} /></div>
      <p className="hint">{report.latitude}, {report.longitude} · Observado: {datePeru(report.observed_at)} · Registrado: {datePeru(report.created_at)}</p>
      {report.waste_type && <p>Tipo de residuo: {report.waste_type}</p>}
      <p className="hint">ID: {report.id}</p>
      <div className="actions">{municipal && <button type="button" onClick={() => { setSelectedId(report.id); document.querySelector('.municipal-page .map')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}>Centrar en el mapa</button>}
      <button type="button" aria-expanded={openId === report.id} onClick={() => setOpenId(openId === report.id ? null : report.id)}>
        {openId === report.id ? 'Ocultar fotografías' : 'Ver fotografías'}
      </button>
      </div>
      {openId === report.id && <Photos api={api} reportId={report.id} canUpload={!municipal} />}
    </article>)}</div>
    <div className="toolbar pagination">
      <button type="button" disabled={loading || offset === 0} onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); setOpenId(null) }}>Anterior</button>
      <span>Página {offset / PAGE_SIZE + 1} · {reports.length} reportes</span>
      <button type="button" disabled={loading || !!error || reports.length < PAGE_SIZE} onClick={() => { setOffset(offset + PAGE_SIZE); setOpenId(null) }}>Siguiente</button>
    </div>
  </section>
}
