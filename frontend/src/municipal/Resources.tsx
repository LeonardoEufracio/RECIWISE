import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../api'
import type { MunicipalService } from './services'
import type { ReportLocation } from '../types'
import type { ShiftInput, Site, SiteInput, VehicleInput } from './model'
import { datePeru, isUuid, numberText, shortId } from '../format'
import LocationPicker from '../LocationPicker'
import { Badge, Empty, ErrorBox, Loading, Modal, useAction, useData } from './ui'

type Change = { title: string; execute: () => Promise<unknown>; reset?: () => void }
export default function Resources({ service, simulated }: { service: MunicipalService; simulated: boolean }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const [vehicles, sites, shifts, drivers] = await Promise.all([service.vehicles(signal), service.sites(signal), service.shifts(signal), service.drivers(signal)])
    return { vehicles, sites, shifts, drivers }
  }, [service])
  const { data, loading, error, retry } = useData(load)
  const [tab, setTab] = useState<'vehicles' | 'sites' | 'shifts'>('vehicles')
  const [location, setLocation] = useState<ReportLocation | null>(null)
  const [locationVersion, setLocationVersion] = useState(0)
  const [pending, setPending] = useState<Change | null>(null)
  const [uncertain, setUncertain] = useState(false)
  useEffect(() => setUncertain(false), [pending])
  const [editing, setEditing] = useState<Site | null>(null)
  const action = useAction()
  function vehicle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget; const fields = new FormData(form)
    void action.run(async () => {
      const capacity = String(fields.get('capacity_kg') || '')
      const input: VehicleInput = { label: String(fields.get('label')).trim(), vehicle_type: String(fields.get('vehicle_type')),
        plate: String(fields.get('plate') || '').trim() || null, capacity_kg: capacity === '' ? null : Number(capacity), available: fields.get('available') === 'on' }
      if (input.label.length < 2 || input.label.length > 100 || (input.capacity_kg !== null && (!Number.isFinite(input.capacity_kg) || input.capacity_kg <= 0))) throw new Error('Revisa el nombre y la capacidad positiva, o deja la capacidad vacía.')
      setPending({ title: 'Crear vehículo ' + input.label, execute: () => service.createVehicle(input), reset: () => form.reset() })
    })
  }
  function site(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget; const fields = new FormData(form)
    void action.run(async () => {
      if (!location?.confirmed) throw new Error('Selecciona y confirma la ubicación del sitio.')
      const input: SiteInput = { name: String(fields.get('name')).trim(), site_type: String(fields.get('site_type')) as SiteInput['site_type'], latitude: location.latitude, longitude: location.longitude }
      if (input.name.length < 2 || input.name.length > 120) throw new Error('El nombre debe tener entre 2 y 120 caracteres.')
      setPending({ title: 'Crear sitio ' + input.name, execute: () => service.createSite(input), reset: () => { form.reset(); setLocation(null); setLocationVersion((v) => v + 1) } })
    })
  }
  function shift(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget; const f = new FormData(form)
    void action.run(async () => {
      const from = new Date(String(f.get('starts_at'))); const to = new Date(String(f.get('ends_at')))
      const driver = String(f.get('driver_id')).trim()
      if (!isUuid(driver) || !data?.drivers.some((d) => d.id === driver)) throw new Error('Selecciona un perfil de chofer autorizado.')
      if (!Number.isFinite(from.getTime()) || !Number.isFinite(to.getTime()) || to <= from) throw new Error('El fin del turno debe ser posterior al inicio.')
      const input: ShiftInput = { vehicle_id: String(f.get('vehicle_id')), driver_id: driver, departure_site_id: String(f.get('departure_site_id')), disposal_site_id: String(f.get('disposal_site_id')), starts_at: from.toISOString(), ends_at: to.toISOString() }
      if (!data?.vehicles.some((v) => v.id === input.vehicle_id && v.available)) throw new Error('Elige un vehículo disponible.')
      setPending({ title: 'Crear turno ' + datePeru(input.starts_at), execute: () => service.createShift(input), reset: () => form.reset() })
    })
  }
  return <>
    <div className="page-heading"><div><span className="eyebrow">Operación municipal</span><h2>Recursos operativos</h2><p>Configura vehículos, puntos y jornadas. Crear un turno no genera una ruta.</p></div></div>
    <nav className="subnav" aria-label="Tipos de recursos">{([['vehicles', 'Vehículos'], ['sites', 'Sitios'], ['shifts', 'Turnos']] as const).map(([id, label]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => setTab(id)}>{label}</button>)}<button onClick={retry} disabled={loading}>Actualizar recursos</button></nav>
    {loading && <Loading />}{error && <ErrorBox message={error} retry={retry} />}{action.error && !pending && <ErrorBox message={action.error} />}{action.message && <p className="notice success" role="status">{action.message}</p>}
    {data && tab === 'vehicles' && <>
      <div className="card-grid">{data.vehicles.map((v) => <article className="panel resource-card" key={v.id}><div className="toolbar"><h3>{v.label}</h3><span className={'badge ' + (v.available ? 'status-abierto' : 'status-cerrado')}>{v.available ? 'Disponible' : 'No disponible'}</span></div><p>{v.vehicle_type} · Placa: {v.plate || 'No registrada'}</p><p>Capacidad: {v.capacity_kg === null ? 'No especificada' : numberText(v.capacity_kg, ' kg')}</p><p className="hint">ID: {v.id}</p><button disabled={action.busy} onClick={() => setPending({ title: (v.available ? 'Marcar no disponible: ' : 'Marcar disponible: ') + v.label, execute: () => service.availability(v.id, !v.available) })}>{v.available ? 'Marcar no disponible' : 'Marcar disponible'}</button></article>)}</div>
      {!data.vehicles.length && <Empty title="No hay vehículos registrados" />}
      <details className="panel"><summary>Registrar vehículo</summary><form onSubmit={vehicle}><fieldset disabled={action.busy}><label>Nombre de la unidad<input name="label" required minLength={2} maxLength={100} /></label><div className="fields"><label>Tipo de vehículo<select name="vehicle_type"><option value="compactadora">Compactadora</option><option value="volquete">Volquete</option><option value="camion_baranda">Camión baranda</option><option value="otro">Otro</option></select></label><label>Placa (opcional)<input name="plate" maxLength={20} /></label><label>Capacidad en kg (opcional)<input type="number" name="capacity_kg" min="0.01" step="any" /><span className="hint">Vacío significa desconocida.</span></label></div><label className="check-row"><input type="checkbox" name="available" /> Disponible para programar</label><button className="primary">Revisar alta de vehículo</button></fieldset></form></details>
    </>}
    {data && tab === 'sites' && <>
      <div className="card-grid">{data.sites.map((s) => <article className="panel" key={s.id}><div className="toolbar"><h3>{s.name}</h3><span className="badge">{s.active ? 'Activo' : 'Inactivo'}</span></div><p>Uso: {s.site_type}</p><p className="hint">{s.latitude}, {s.longitude}<br />ID: {s.id}</p><button onClick={() => setEditing(s)}>Editar sitio {s.name}</button></article>)}</div>
      {!data.sites.length && <Empty title="No hay sitios registrados" />}
      <details className="panel"><summary>Registrar punto de salida o descarga</summary><form onSubmit={site}><fieldset disabled={action.busy}><label>Nombre del sitio<input name="name" required minLength={2} maxLength={120} /></label><label>Uso del sitio<select name="site_type"><option value="salida">Salida</option><option value="descarga">Descarga</option><option value="ambos">Salida y descarga</option></select></label><LocationPicker key={locationVersion} location={location} disabled={action.busy} onChange={setLocation} /><button className="primary" disabled={!location?.confirmed}>Revisar alta de sitio</button></fieldset></form></details>
    </>}
    {data && tab === 'shifts' && <>
      <div className="card-grid">{data.shifts.map((s) => <article className="panel" key={s.id}><div className="toolbar"><h3>Turno {shortId(s.id)}</h3><Badge status={s.status} /></div><p>{datePeru(s.starts_at)}<br />hasta {datePeru(s.ends_at)}</p><p>{data.vehicles.find((v) => v.id === s.vehicle_id)?.label || 'Vehículo no disponible en la consulta'}</p><p className="hint">Chofer: {s.driver_id}<br />Salida: {data.sites.find((p) => p.id === s.departure_site_id)?.name || shortId(s.departure_site_id)}<br />Descarga: {data.sites.find((p) => p.id === s.disposal_site_id)?.name || shortId(s.disposal_site_id)}</p></article>)}</div>
      {!data.shifts.length && <Empty title="No hay turnos registrados" />}
      <details className="panel"><summary>Crear jornada o turno</summary><form onSubmit={shift}><fieldset disabled={action.busy}><div className="fields"><label>Vehículo para el nuevo turno<select name="vehicle_id" required><option value="">Selecciona un vehículo disponible</option>{data.vehicles.map((v) => <option key={v.id} value={v.id} disabled={!v.available}>{v.label}{!v.available ? ' — No disponible' : ''}</option>)}</select></label><label>Chofer autorizado<select name="driver_id" required><option value="">Selecciona un chofer</option>{data.drivers.map((d) => <option value={d.id} key={d.id}>Chofer {d.id}</option>)}</select><span className="hint">Perfiles habilitados por el servidor. No se publican correos ni datos personales.</span></label></div>
        <div className="fields"><label>Salida del nuevo turno<select name="departure_site_id" required><option value="">Elige salida activa</option>{data.sites.filter((s) => s.active && ['salida', 'ambos'].includes(s.site_type)).map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label><label>Descarga del nuevo turno<select name="disposal_site_id" required><option value="">Elige descarga activa</option>{data.sites.filter((s) => s.active && ['descarga', 'ambos'].includes(s.site_type)).map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label></div>
        <div className="fields"><label>Inicio del turno<input type="datetime-local" name="starts_at" required /></label><label>Fin del turno<input type="datetime-local" name="ends_at" required /></label></div><p className="hint">Introduce la hora del dispositivo; se envía con zona horaria y se presenta en hora de Perú.</p><button className="primary">Revisar nuevo turno</button></fieldset></form></details>
    </>}
    {editing && <EditSite key={editing.id} site={editing} service={service} close={() => setEditing(null)} saved={() => { setEditing(null); retry() }} simulated={simulated} />}
    {pending && <Modal title={pending.title} close={() => !action.busy && setPending(null)}><p>{simulated ? 'Solo cambiará la sesión de demostración; no se envía al servidor.' : 'Esta operación modificará los recursos en FastAPI. Revisa los datos antes de confirmar.'}</p>{action.error && <ErrorBox message={action.error} />}
      {uncertain ? <div className="notice warning"><p>Resultado no confirmado. Consulta los recursos antes de crear otro; no se repetirá este envío.</p><button onClick={() => { setPending(null); retry() }}>Consultar recursos actualizados</button></div>
        : <div className="actions"><button disabled={action.busy} onClick={() => setPending(null)}>Cancelar</button><button className="primary" disabled={action.busy} onClick={() => void action.run(async () => { try { await pending.execute() } catch (err) { if (!simulated && (!(err instanceof ApiError) || err.status === null || err.status >= 500)) setUncertain(true); throw err }; pending.reset?.(); setPending(null); retry(); return simulated ? 'Recurso actualizado solo en la demostración.' : 'Recurso guardado correctamente.' })}>Confirmar {simulated ? 'cambio simulado' : 'operación'}</button></div>}
    </Modal>}
  </>
}

function EditSite({ site, service, close, saved, simulated }: { site: Site; service: MunicipalService; close: () => void; saved: () => void; simulated: boolean }) {
  const [location, setLocation] = useState<ReportLocation>({ latitude: site.latitude, longitude: site.longitude, source: 'map', confirmed: true })
  const [changes, setChanges] = useState<(Partial<SiteInput> & { active: boolean }) | null>(null)
  const action = useAction()
  return <Modal title={'Editar punto ' + site.name} close={() => !action.busy && close()}>
    <p className="hint">Un sitio usado por un turno pendiente conserva su ubicación, uso y disponibilidad. Puede corregirse su nombre.</p>
    {action.error && <ErrorBox message={action.error} />}
    <form onSubmit={(event) => { event.preventDefault(); const f = new FormData(event.currentTarget); if (location.confirmed) setChanges({ name: String(f.get('name')).trim(), site_type: String(f.get('site_type')) as SiteInput['site_type'], active: f.get('active') === 'on', latitude: location.latitude, longitude: location.longitude }) }}>
      <fieldset disabled={action.busy || !!changes}>
        <label>Nombre del punto<input name="name" defaultValue={site.name} required minLength={2} maxLength={120} /></label>
        <label>Uso del punto<select name="site_type" defaultValue={site.site_type}><option value="salida">Salida</option><option value="descarga">Descarga</option><option value="ambos">Ambos</option></select></label>
        <label className="check-row"><input name="active" type="checkbox" defaultChecked={site.active} /> Punto activo</label>
        <LocationPicker purpose="site" location={location} onChange={setLocation} disabled={action.busy || !!changes} />
        <button className="primary" disabled={!location.confirmed}>Revisar cambios del punto</button>
      </fieldset>
    </form>
    {changes && <div className="notice"><p>Confirma los cambios de {changes.name}. {simulated ? 'Solo demostración.' : 'Se guardarán en FastAPI.'}</p><div className="actions"><button disabled={action.busy} onClick={() => setChanges(null)}>Corregir cambios</button><button className="primary" disabled={action.busy} onClick={() => void action.run(async () => { await service.updateSite(site.id, changes); saved() })}>Confirmar edición</button></div></div>}
  </Modal>
}
