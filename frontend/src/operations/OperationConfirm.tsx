import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api'
import { ErrorBox, Modal } from '../municipal/ui'
import type { OperationsService } from './service'
import { actionNames, type Intent } from './types'

export default function OperationConfirm({ service, initial, close, saved }: { service: OperationsService; initial: Intent; close: () => void; saved: () => void }) {
  const [intent, setIntent] = useState(initial)
  const [checking, setChecking] = useState(false)
  const lock = useRef(false)
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [])
  async function send() {
    if (lock.current || !['prepared', 'uncertain'].includes(intent.stage) || (intent.stage === 'uncertain' && !intent.notFound)) return
    lock.current = true
    const snapshot = { ...intent, stage: 'sending' as const, error: '', notFound: false }
    setIntent(snapshot)
    try { await service.perform(snapshot); saved() }
    catch (err) {
      const code = err instanceof ApiError ? err.status : null
      setIntent({ ...snapshot, stage: code === null || code >= 500 ? 'uncertain' : code === 409 ? 'conflict' : 'rejected', error: err instanceof Error ? err.message : 'No se pudo completar la operación.', notFound: false })
    } finally { lock.current = false }
  }
  async function check() {
    if (lock.current) return
    lock.current = true; setChecking(true)
    try { await service.operation(intent.routeId, intent.command.operation_id); saved() }
    catch (err) {
      setIntent((value) => ({ ...value, notFound: err instanceof ApiError && err.status === 404, error: err instanceof Error ? err.message : 'No se pudo consultar la operación.' }))
    } finally { lock.current = false; setChecking(false) }
  }
  const canClose = ['prepared', 'rejected', 'conflict'].includes(intent.stage) && !lock.current
  const label = actionNames[(intent.command.decision || intent.command.action)!]
  return <Modal title="Confirmar operación de ruta" close={() => canClose && close()}>
    <h3>{label}</h3><p>Ruta: <span className="identifier">{intent.routeId}</span></p>
    {intent.stopId && <p>Parada: <span className="identifier">{intent.stopId}</span></p>}
    <p>Estado esperado: {intent.command.expected_status}. Revisión: {intent.command.expected_revision || 'Sin decisiones anteriores'}.</p>
    <p>Motivo: {intent.command.notes || 'Sin observaciones'}</p>
    <p className="hint">Operación: <span className="identifier">{intent.command.operation_id}</span>. Conserva este identificador si se interrumpe la conexión.</p>
    {intent.error && <ErrorBox message={intent.error} />}
    {intent.stage === 'uncertain' && <div className="notice warning"><p>Resultado incierto. Consulta esta operación antes de volver a enviarla. La comprobación utiliza el mismo UUID.</p><button disabled={checking} onClick={() => void check()}>Comprobar operación de ruta</button>{intent.notFound && <button disabled={checking} onClick={() => void send()}>Reintentar el mismo comando de ruta</button>}</div>}
    {intent.stage === 'conflict' && <p>La ruta cambió o no permite esta acción. Actualiza y revisa antes de preparar una nueva decisión.</p>}
    <div className="actions">{canClose && <button onClick={close}>{intent.stage === 'prepared' ? 'Volver sin guardar' : 'Descartar y actualizar ruta'}</button>}
      {intent.stage === 'prepared' && <button className="primary" onClick={() => void send()}>Confirmar operación de ruta</button>}
      {intent.stage === 'sending' && <p role="status">Guardando operación…</p>}
    </div>
  </Modal>
}
