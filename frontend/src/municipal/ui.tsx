import { useEffect, useRef, useState, type ReactNode } from 'react'
import { stateLabel } from '../format'

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const shapes: Record<string, ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="11" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="18" width="7" height="3" rx="1" /></>,
    reports: <><path d="M7 3h10v3h3v15H4V6h3z" /><path d="M8 11h8M8 15h5" /></>,
    events: <><path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2" /></>,
    groupings: <><circle cx="6" cy="6" r="3" /><circle cx="18" cy="6" r="3" /><circle cx="12" cy="18" r="3" /><path d="m8 8 3 7m5-7-3 7M9 6h6" /></>,
    priorities: <><path d="M5 5h14M5 12h10M5 19h6" /><path d="m17 17 3 3 3-3M20 10v10" /></>,
    planning: <><circle cx="5" cy="5" r="2" /><circle cx="19" cy="19" r="2" /><path d="M7 5h9a4 4 0 0 1 0 8H8a3 3 0 0 0 0 6h9" /></>,
    resources: <><path d="M3 6h11v11H3zM14 10h4l3 4v3h-7" /><circle cx="7" cy="18" r="2" /><circle cx="18" cy="18" r="2" /></>,
    leaf: <><path d="M20 3C7 2 2 7 6 15c8 5 15-1 14-12Z" /><path d="M4 21 15 10" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name] || shapes.events}</svg>
}
export function Badge({ status }: { status: string }) { return <span className={'badge status-' + status}>{stateLabel(status)}</span> }
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty-state"><Icon name="events" size={30} /><h3>{title}</h3>{children && <p>{children}</p>}</div>
}
export function Pending({ feature }: { feature: string }) {
  return <section className="panel"><span className="eyebrow">Integración pendiente</span><h2>{feature}</h2>
    <Empty title="Esta función aún no está habilitada en el servicio">
      Puedes seguir consultando reportes y recursos. Las propuestas de agrupación, prioridad y rutas se habilitarán cuando estén disponibles y autorizadas.
    </Empty>
  </section>
}
export function Loading() { return <p className="loading-state" role="status"><span className="spinner" /> Consultando información…</p> }
export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="notice danger" role="alert"><p>{message}</p>{retry && <button type="button" onClick={retry}>Volver a intentar</button>}</div>
}
export function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const dialog = ref.current!
    if (typeof dialog.showModal === 'function') dialog.showModal()
    else dialog.setAttribute('open', '')
    return () => previous?.focus()
  }, [])
  return <dialog ref={ref} className="dialog" aria-label={title} onCancel={(event) => { event.preventDefault(); close() }}>
    <div className="toolbar"><h2>{title}</h2><button type="button" onClick={close} aria-label={'Cerrar ' + title}>Cerrar</button></div>{children}
  </dialog>
}

export function useData<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setData(null)
    void load(controller.signal).then((value) => { if (!controller.signal.aborted) setData(value) })
      .catch((err: Error) => { if (!controller.signal.aborted) setError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [load, revision])
  return { data, loading, error, retry: () => setRevision((v) => v + 1) }
}

export function useAction() {
  const lock = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  async function run(action: () => Promise<string | void>) {
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setMessage('')
    try { const result = await action(); if (result) setMessage(result) }
    catch (err) { setError(err instanceof Error ? err.message : 'No se pudo completar la operación.') }
    finally { lock.current = false; setBusy(false) }
  }
  return { busy, error, message, run }
}
