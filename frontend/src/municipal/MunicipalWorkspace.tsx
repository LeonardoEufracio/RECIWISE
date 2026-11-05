import { useEffect, useMemo, useState } from 'react'
import type { Api } from '../api'
import type { Report } from '../types'
import Reports from '../Reports'
import Dashboard from './Dashboard'
import Events from './Events'
import Groupings from './Groupings'
import Priorities from './Priorities'
import Planning from './Planning'
import Resources from './Resources'
import LiveEvents from './LiveEvents'
import LiveGroupings from './LiveGroupings'
import LiveProposals from './LiveProposals'
import RouteManagement from '../operations/RouteManagement'
import { createBackendService } from './backendService'
import type { DecisionIntent } from './backendTypes'
import { createMunicipalService, type MunicipalService } from './services'
import { decideDemo, initialDemo, proposeDemo } from './demo'
import type { DemoData, Section } from './model'
import { Icon, Modal } from './ui'
import './municipal.css'

const sections: [Section, string][] = [
  ['dashboard', 'Dashboard'], ['reports', 'Reportes ciudadanos'], ['events', 'Eventos o puntos de atención'],
  ['groupings', 'Revisión de agrupaciones'], ['priorities', 'Priorización'], ['planning', 'Planificación de rutas'], ['resources', 'Recursos operativos'],
]

function simulatedApi(data: DemoData): Api {
  return async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (init.method && init.method !== 'GET') throw new Error('Esta vista de demostración no envía escrituras.')
    const url = new URL(path, 'https://demo.invalid')
    if (url.pathname === '/municipal/reports') {
      const offset = Number(url.searchParams.get('offset') || 0)
      const limit = Number(url.searchParams.get('limit') || 50)
      const status = url.searchParams.get('status')
      return data.reports.filter((r) => !status || r.status === status).slice(offset, offset + limit) as T
    }
    if (/^\/reports\/[^/]+\/photos$/.test(url.pathname)) return [] as T
    throw new Error('Función no disponible en el adaptador de demostración.')
  }
}

export default function MunicipalWorkspace({ api, demoAvailable }: { api: Api; demoAvailable: boolean }) {
  const [section, setSection] = useState<Section>('dashboard')
  const [menuOpen, setMenuOpen] = useState(false)
  const [demo, setDemo] = useState<DemoData | null>(null)
  const [switchMode, setSwitchMode] = useState<'enter' | 'leave' | 'reset' | null>(null)
  const [mutations, setMutations] = useState(0)
  const [intent, setIntent] = useState<DecisionIntent | null>(null)
  const [routePending, setRoutePending] = useState(false)
  const [planningView, setPlanningView] = useState<'proposals' | 'decisions'>('proposals')
  useEffect(() => {
    if (!intent || ['prepared', 'rejected'].includes(intent.stage)) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [intent])
  const trackedApi = useMemo<Api>(() => async function request<T>(path: string, init: RequestInit = {}, authenticated = true) {
    const write = init.method && init.method !== 'GET'
    if (write) setMutations((n) => n + 1)
    try { return await api<T>(path, init, authenticated) }
    finally { if (write) setMutations((n) => n - 1) }
  }, [api])
  const backend = useMemo(() => createBackendService(trackedApi), [trackedApi])
  const displayApi = useMemo(() => demo ? simulatedApi(demo) : trackedApi, [demo, trackedApi])
  const service = useMemo<MunicipalService>(() => {
    const real = createMunicipalService(trackedApi)
    if (!demo) return real
    const update = (next: DemoData) => { setDemo(next) }
    return {
      reports: (limit = 50, offset = 0, status = '') => Promise.resolve(demo.reports.filter((r) => !status || r.status === status).slice(offset, offset + limit)),
      photos: async () => [], vehicles: async () => demo.vehicles, sites: async () => demo.sites, shifts: async () => demo.shifts,
      drivers: async () => [...new Set(demo.shifts.map((s) => s.driver_id))].map((id) => ({ id, role: 'chofer' as const })),
      updateSite: async (id, changes) => { const site = demo.sites.find((s) => s.id === id); if (!site) throw new Error('Sitio no disponible.'); const value = { ...site, ...changes }; update({ ...demo, sites: demo.sites.map((s) => s.id === id ? value : s) }); return value },
      createVehicle: async (input) => {
        if (demo.vehicles.some((v) => v.label === input.label)) throw new Error('El nombre de la unidad ya existe en la demostración.')
        const value = { ...input, id: crypto.randomUUID() }; update({ ...demo, vehicles: [...demo.vehicles, value] }); return value
      },
      availability: async (id, available) => {
        const vehicle = demo.vehicles.find((v) => v.id === id)
        if (!vehicle) throw new Error('Vehículo no disponible.')
        const value = { ...vehicle, available }; update({ ...demo, vehicles: demo.vehicles.map((v) => v.id === id ? value : v) }); return value
      },
      createSite: async (input) => { const value = { ...input, id: crypto.randomUUID(), active: true }; update({ ...demo, sites: [...demo.sites, value] }); return value },
      createShift: async (input) => {
        if (!demo.shifts.some((s) => s.driver_id === input.driver_id)) throw new Error('El chofer no está incluido en los ejemplos.')
        if (demo.shifts.some((s) => s.status === 'programado' && (s.vehicle_id === input.vehicle_id || s.driver_id === input.driver_id) && s.starts_at < input.ends_at && s.ends_at > input.starts_at)) throw new Error('Vehículo o chofer ya reservado en ese horario de demostración.')
        const value = { ...input, id: crypto.randomUUID(), status: 'programado', created_by: 'demo-manager' }; update({ ...demo, shifts: [...demo.shifts, value] }); return value
      },
    }
  }, [trackedApi, demo])
  function navigate(next: Section) { setSection(next); setMenuOpen(false) }
  return <div className="municipal-shell">
    <aside className="municipal-sidebar"><div className="sidebar-brand"><Icon name="leaf" size={26} /><div><strong>RECIWISE</strong><small>Gestión municipal</small></div></div>
      <button className="mobile-menu" aria-expanded={menuOpen} aria-controls="municipal-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? 'Cerrar navegación' : 'Abrir navegación'}</button>
      <nav id="municipal-navigation" aria-label="Navegación municipal" className={menuOpen ? 'menu-open' : ''}>
        {sections.map(([id, title]) => <button key={id} disabled={mutations > 0 || routePending} aria-current={section === id ? 'page' : undefined} onClick={() => navigate(id)}><Icon name={id} /><span>{title}</span></button>)}
      </nav><div className="sidebar-note"><span className="live-dot" /> {demo ? 'Ejemplos de desarrollo' : 'Información de FastAPI'}<p>La revisión municipal convierte observaciones en decisiones de atención.</p></div>
    </aside>
    <div className="municipal-content">
      <div className="workspace-bar"><span>{sections.find(([id]) => id === section)?.[1]}</span><div className="actions">
        <span className={'source-pill ' + (demo ? 'demo-pill' : '')}>{demo ? 'Demostración local' : 'Modo real'}</span>
        {demoAvailable && <button disabled={mutations > 0 || Boolean(intent) || routePending} onClick={() => setSwitchMode(demo ? 'leave' : 'enter')}>{demo ? 'Volver al modo real' : 'Explorar demostración'}</button>}
        {demo && <button onClick={() => setSwitchMode('reset')}>Reiniciar demostración</button>}
      </div></div>
      {demo && <div className="demo-banner" role="status"><strong>DATOS SIMULADOS — DEMOSTRACIÓN</strong><span>Ejemplos ficticios, no estadísticas oficiales de El Tambo. Las acciones permanecen en memoria y se descartan al salir o recargar.</span></div>}
      <div className="municipal-page" key={demo ? 'demo' : 'real'}>
        {intent && section !== 'groupings' && <div className="notice warning" role="status">Hay una decisión pendiente de resolver: {intent.command.operation_id}.<button onClick={() => navigate('groupings')}>Volver a la decisión</button></div>}
        {section === 'dashboard' && <Dashboard service={service} demo={demo} navigate={navigate} />}
        {section === 'reports' && <Reports api={displayApi} municipal />}
        {section === 'events' && (demo ? <Events data={demo} /> : <LiveEvents api={trackedApi} service={backend} />)}
        {section === 'groupings' && (demo ? <Groupings data={demo} decide={(id, kind, notes) => { setDemo(decideDemo(demo, id, kind, notes)) }} /> : <LiveGroupings service={backend} intent={intent} setIntent={setIntent} />)}
        {section === 'priorities' && <Priorities data={demo} />}
        {section === 'planning' && (demo ? <Planning service={service} demo={demo} generate={(input) => { setDemo(proposeDemo(demo, input)) }} approve={(id) => { setDemo({ ...demo, proposals: demo.proposals.map((p) => p.id === id ? { ...p, status: 'aprobada' } : p) }) }} /> : <><nav className="subnav" aria-label="Vistas de planificación"><button disabled={routePending} aria-current={planningView === 'proposals' ? 'page' : undefined} onClick={() => setPlanningView('proposals')}>Propuestas recibidas</button><button disabled={routePending} aria-current={planningView === 'decisions' ? 'page' : undefined} onClick={() => setPlanningView('decisions')}>Decisiones e historial</button></nav>{planningView === 'proposals' ? <LiveProposals service={backend} resources={service} /> : <RouteManagement api={trackedApi} onPending={setRoutePending} />}</>)}
        {section === 'resources' && <Resources service={service} simulated={Boolean(demo)} />}
      </div>
    </div>
    {switchMode && <Modal title={switchMode === 'enter' ? 'Explorar datos de demostración' : 'Descartar la demostración'} close={() => setSwitchMode(null)}>
      <p>{switchMode === 'enter' ? 'Cambiarás a un conjunto ficticio separado. No se combinarán los datos de FastAPI ni se enviarán acciones de demostración al servidor.' : 'Se descartarán las decisiones, recursos y propuestas locales de esta demostración. La base de datos no cambia.'}</p>
      <div className="actions"><button onClick={() => setSwitchMode(null)}>Cancelar</button><button className="primary" onClick={() => { setDemo(switchMode === 'leave' ? null : initialDemo()); setSection('dashboard'); setSwitchMode(null); setMenuOpen(false) }}>Confirmar cambio de modo</button></div>
    </Modal>}
  </div>
}
