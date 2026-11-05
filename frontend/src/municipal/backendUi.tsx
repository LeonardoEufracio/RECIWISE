import type { Json, ProposalDetailDto } from './backendTypes'

export const eventStates = ['en_revision', 'abierto', 'programado', 'atendido', 'cerrado', 'descartado'] as const
export const editable = (event: { state: string; closed_at: string | null } | null) =>
  !event || (['abierto', 'en_revision'].includes(event.state) && !event.closed_at)
export function Pager({ offset, count, loading, change, label = 'resultados' }: {
  offset: number; count: number; loading: boolean; change: (offset: number) => void; label?: string
}) {
  return <nav className="toolbar pagination" aria-label={'Páginas de ' + label}>
    <button type="button" disabled={loading || offset === 0} onClick={() => change(Math.max(0, offset - 50))}>Anterior</button>
    <span>Página {offset / 50 + 1} · {count} {label}</span>
    <button type="button" disabled={loading || count < 50} onClick={() => change(offset + 50)}>Siguiente</button>
  </nav>
}
export function JsonDetails({ value, label = 'Factores recibidos' }: { value: Json; label?: string }) {
  return <details><summary>{label}</summary><pre className="json-details">{JSON.stringify(value, null, 2)}</pre></details>
}
export function snapshotEvents(proposal: ProposalDetailDto) {
  const operational = proposal.input_snapshot.operational
  if (!operational || Array.isArray(operational) || typeof operational !== 'object') return []
  const events = operational.events
  if (!Array.isArray(events)) return []
  return events.flatMap((item) => {
    if (!item || Array.isArray(item) || typeof item !== 'object') return []
    const { id, latitude, longitude } = item
    return typeof id === 'string' && typeof latitude === 'number' && typeof longitude === 'number'
      && Number.isFinite(latitude) && Number.isFinite(longitude) && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180
      ? [{ id, latitude, longitude }] : []
  })
}
