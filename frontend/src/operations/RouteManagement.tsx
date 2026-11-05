import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { datePeru, shortId } from '../format'
import { Pager } from '../municipal/backendUi'
import { Badge, Empty, ErrorBox, Loading, Modal, useData } from '../municipal/ui'
import { createOperationsService, type OperationsService } from './service'
import OperationConfirm from './OperationConfirm'
import RouteDetails from './RouteDetails'
import type { Intent, RouteDetail, RouteState } from './types'

function Review({ id, service, close, changed, onPending }: { id: string; service: OperationsService; close: () => void; changed: () => void; onPending: (pending: boolean) => void }) {
  const load = useCallback((signal: AbortSignal) => service.detail(id, signal), [service, id])
  const data = useData(load)
  const [intent, setIntent] = useState<Intent | null>(null)
  useEffect(() => { onPending(!!intent); return () => onPending(false) }, [intent, onPending])
  function prepare(event: FormEvent<HTMLFormElement>, route: RouteDetail) {
    event.preventDefault()
    const f = new FormData(event.currentTarget)
    const decision = String(f.get('decision')) as 'cancel' | 'reject'
    setIntent({ scope: 'municipal', routeId: route.id, command: { operation_id: crypto.randomUUID(), expected_status: route.status, expected_revision: route.revision, notes: String(f.get('notes')).trim(), decision }, stage: 'prepared', error: '', notFound: false })
  }
  function refresh() { setIntent(null); data.retry(); changed() }
  return <>
    <Modal title={'Revisión municipal de ruta ' + shortId(id)} close={() => !intent && close()}>
      {data.loading && <Loading />}{data.error && <ErrorBox message={data.error} retry={data.retry} />}
      {data.data && <><RouteDetails route={data.data} /><section className="panel">
        <h3>Decisión municipal</h3><button disabled>Aprobar y asignar (proveedor pendiente)</button><p className="hint">La verificación del proveedor está pendiente. FastAPI rechaza la aprobación operativa, incluso si el resultado declara origen D3.</p>
        {['propuesta', 'aprobada'].includes(data.data.status) && <form onSubmit={(e) => prepare(e, data.data!)}><fieldset disabled={!!intent}><label>Decisión sobre la propuesta<select name="decision">{data.data.status === 'propuesta' && <option value="reject">Rechazar propuesta</option>}<option value="cancel">Cancelar propuesta o ruta</option></select></label><label>Motivo de la decisión<textarea name="notes" minLength={3} maxLength={2000} required /></label><button>Revisar decisión de ruta</button></fieldset></form>}
        {!['propuesta', 'aprobada'].includes(data.data.status) && <p>Este estado no admite rechazo ni cancelación municipal.</p>}
      </section></>}
    </Modal>
    {intent && <OperationConfirm key={intent.command.operation_id} service={service} initial={intent} close={refresh} saved={refresh} />}
  </>
}
export default function RouteManagement({ api, onPending }: { api: Api; onPending: (pending: boolean) => void }) {
  const service = useMemo(() => createOperationsService(api, 'municipal'), [api])
  const [status, setStatus] = useState<RouteState | ''>('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const load = useCallback((signal: AbortSignal) => service.routes(offset, status || undefined, signal), [service, offset, status])
  const data = useData(load)
  return <>
    <div className="page-heading"><div><span className="eyebrow">Control municipal</span><h2>Decisiones e historial de rutas</h2><p>Comprueba recursos y registra rechazos o cancelaciones con responsable y revisión de estado.</p></div><button onClick={data.retry} disabled={data.loading}>Actualizar historial de rutas</button></div>
    <label className="compact-field">Estado de rutas<select value={status} onChange={(e) => { setStatus(e.target.value as RouteState | ''); setOffset(0) }}><option value="">Todos</option>{(['propuesta', 'aprobada', 'en_ejecucion', 'finalizada', 'cancelada'] as const).map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
    {data.loading && <Loading />}{data.error && <ErrorBox message={data.error} retry={data.retry} />}
    {data.data && <>{!data.data.length && <Empty title="Sin rutas en este estado" />}<div className="card-grid">{data.data.map((r) => <article className="panel" key={r.id}><div className="toolbar"><h3>{r.vehicle_label}</h3><Badge status={r.status} /></div><p>{datePeru(r.starts_at)}</p><p className="hint">Ruta {shortId(r.id)} · Chofer {shortId(r.driver_id)}</p><p>{r.approval_verified ? 'Aprobación verificada' : 'Sin autorización operativa verificada'}</p><button onClick={() => setSelected(r.id)}>Revisar ruta {shortId(r.id)}</button></article>)}</div><Pager label="rutas" offset={offset} count={data.data.length} loading={data.loading} change={setOffset} /></>}
    {selected && <Review key={selected} id={selected} service={service} close={() => setSelected(null)} changed={data.retry} onPending={onPending} />}
  </>
}
