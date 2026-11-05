import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { Api } from '../api'
import { ApiError } from '../api'
import LiveEvents from './LiveEvents'
import LiveGroupings from './LiveGroupings'
import LiveProposals from './LiveProposals'
import { createBackendService } from './backendService'
import { createMunicipalService } from './services'
import type { DecisionCommand, DecisionDto, DecisionIntent, EventDto, GroupingDto, ProposalDetailDto } from './backendTypes'
import type { Report } from '../types'

vi.mock('../MapView', () => ({ default: () => <div aria-label="Mapa de eventos" /> }))
vi.mock('./RouteMap', () => ({ default: ({ simulated }: { simulated: boolean }) => <div aria-label={simulated ? 'Mapa simulado' : 'Mapa recibido'} /> }))
afterEach(cleanup)
const report: Report = { id: 'r1', citizen_id: 'citizen', description: 'Acumulación ficticia para integración', latitude: -12.04, longitude: -75.21, status: 'recibido', observed_at: '2026-10-29T10:00:00Z', created_at: '2026-10-29T11:00:00Z', waste_type: null }
const event: EventDto = { id: 'e1', latitude: -12.04, longitude: -75.21, state: 'abierto', intervention_type: 'Inspección ficticia', priority: null, restrictions: null, report_count: 1, report_ids: [report.id], closed_at: null, created_at: report.created_at }
const baseRelation: GroupingDto = { report, event_id: null, event: null, last_decision_id: null, pending_review: false, linked_at: null, linked_by: null, linkage_method: null, config_version: null }
function decision(c: DecisionCommand): DecisionDto { return { id: c.operation_id, report_id: c.report_id, candidate_event_id: c.candidate_event_id, resulting_event_id: c.decision === 'agrupar' ? c.candidate_event_id : c.decision === 'separar' ? null : c.expected_event_id, previous_event_id: c.expected_event_id, previous_event_known: true, operation: c.decision === 'agrupar' ? c.expected_event_id ? 'reassign' : 'confirm' : c.decision === 'separar' ? 'separate' : c.decision === 'revisar' ? 'review' : 'keep_separate', decision: c.decision, factors: null, config_version: null, decided_by: 'manager', decided_at: report.created_at, notes: c.notes } }
function fixture(initial = baseRelation) {
  let relation = structuredClone(initial); const history: DecisionDto[] = []
  let fail: number | null = null; let recover = false
  const api = vi.fn().mockImplementation(async (path: string, init?: RequestInit) => {
    const url = new URL(path, 'http://test.invalid')
    if (init?.method === 'POST') {
      const command = JSON.parse(init.body as string) as DecisionCommand
      if (fail && !recover) throw new ApiError('Error controlado HTTP ' + fail, fail)
      const item = decision(command); history.unshift(item)
      relation = { ...relation, event_id: item.resulting_event_id, event: item.resulting_event_id ? event : null, last_decision_id: item.id }
      return { decision: item, relation, replayed: false }
    }
    if (url.pathname.endsWith('/candidates')) return { report_id: report.id, event_id: relation.event_id, last_decision_id: relation.last_decision_id, source: 'manual', d3_available: false, candidates: [event, { ...event, id: 'e2' }] }
    if (url.pathname === '/municipal/groupings/decisions') return [...history]
    if (url.pathname.includes('/decisions/')) {
      const found = history.find((h) => url.pathname.endsWith(h.id))
      if (!found) throw new ApiError('Operación no encontrada', 404)
      return found
    }
    if (url.pathname.includes('/groupings/reports/')) return { ...relation }
    if (url.pathname === '/municipal/groupings') return [{ ...relation }]
    throw new Error('Petición inesperada ' + path)
  })
  const service = createBackendService(api as Api)
  function Harness() {
    const [intent, setIntent] = useState<DecisionIntent | null>(null)
    return <LiveGroupings service={service} intent={intent} setIntent={setIntent} />
  }
  return { api, Harness, history, fail: (code: number) => { fail = code }, recover: () => { recover = true } }
}
async function openReview() {
  fireEvent.click(await screen.findByRole('button', { name: 'Revisar relación r1' }))
  await screen.findByLabelText('Evento candidato')
  fireEvent.change(screen.getByLabelText('Evento candidato'), { target: { value: 'e1' } })
}
async function prepare(name = 'Confirmar agrupación') {
  fireEvent.click(screen.getByRole('button', { name }))
  return screen.findByRole('dialog', { name: 'Confirmar decisión municipal' })
}

describe('Agrupaciones conectadas con API simulada', () => {
  it.each(['Confirmar agrupación', 'Mantener separados', 'Registrar revisión'])('confirma %s con UUID, controles de estado e historial', async (name) => {
    const f = fixture(); render(<f.Harness />); await openReview()
    const dialog = await prepare(name)
    expect(f.api.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar decisión' }))
    fireEvent.click(within(dialog).queryByRole('button', { name: 'Confirmar decisión' }) || within(dialog).getByRole('button', { name: /Guardando/ }))
    await screen.findByRole('dialog', { name: 'Detalle de decisión' })
    const writes = f.api.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(writes).toHaveLength(1)
    const command = JSON.parse(writes[0][1].body)
    expect(command.operation_id).toMatch(/^[a-f0-9-]{36}$/)
    expect(command.expected_event_id).toBe(null); expect(command.expected_decision_id).toBe(null)
    expect(command).not.toHaveProperty('status'); expect(f.history).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar Detalle de decisión' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Ver decisión ' + command.operation_id.slice(0, 4) + '…' + command.operation_id.slice(-4) }))
    await screen.findByRole('dialog', { name: 'Detalle de decisión' })
    expect(f.api.mock.calls.some(([path]) => path.endsWith('/decisions/' + command.operation_id))).toBe(true)
  })
  it.each(['Separar reporte', 'Corregir asociación'])('envía %s conservando ambos estados esperados', async (name) => {
    const f = fixture({ ...baseRelation, event_id: 'e2', event: { ...event, id: 'e2' }, last_decision_id: 'last' })
    render(<f.Harness />); await openReview(); const dialog = await prepare(name)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar decisión' }))
    await screen.findByRole('dialog', { name: 'Detalle de decisión' })
    const command = JSON.parse(f.api.mock.calls.find(([, init]) => init?.method === 'POST')![1].body)
    expect(command.expected_event_id).toBe('e2'); expect(command.expected_decision_id).toBe('last')
    expect(command.candidate_event_id).toBe(name === 'Separar reporte' ? null : 'e1')
    expect(command.decision).toBe(name === 'Separar reporte' ? 'separar' : 'agrupar')
  })
  it('409 exige descartar y volver a consultar, sin reenvío automático', async () => {
    const f = fixture(); f.fail(409); render(<f.Harness />); await openReview(); const dialog = await prepare()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar decisión' }))
    await screen.findByText(/La relación o su revisión cambiaron/)
    expect(within(dialog).queryByRole('button', { name: 'Confirmar decisión' })).toBeNull()
    expect(f.api.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Descartar y actualizar relación' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await screen.findByLabelText('Evento candidato')
    expect(f.api.mock.calls.filter(([path]) => path === '/municipal/groupings/reports/r1').length).toBeGreaterThan(1)
  })
  it('503 consulta el UUID y reintenta exclusivamente el mismo cuerpo tras 404', async () => {
    const f = fixture(); f.fail(503); render(<f.Harness />); await openReview(); const dialog = await prepare()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar decisión' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Comprobar operación' }))
    const retry = await screen.findByRole('button', { name: 'Reintentar el mismo comando' }); f.recover(); fireEvent.click(retry)
    await screen.findByRole('dialog', { name: 'Detalle de decisión' })
    const writes = f.api.mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(writes).toHaveLength(2); expect(writes[0][1].body).toBe(writes[1][1].body)
  })
  it('503 con operación encontrada recupera el resultado sin repetir POST', async () => {
    const f = fixture(); f.fail(503); render(<f.Harness />); await openReview(); const dialog = await prepare()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar decisión' }))
    await screen.findByRole('button', { name: 'Comprobar operación' })
    f.history.push(decision(JSON.parse(f.api.mock.calls.find(([, init]) => init?.method === 'POST')![1].body)))
    fireEvent.click(screen.getByRole('button', { name: 'Comprobar operación' }))
    await screen.findByRole('dialog', { name: 'Detalle de decisión' })
    expect(f.api.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })
})

describe('Eventos y propuestas con API simulada', () => {
  it('consulta detalle y reportes de eventos sin inferir restricciones ni prioridad', async () => {
    const api = vi.fn().mockImplementation(async (path: string) => path.endsWith('/e1') ? event : path.includes('/e1/reports') ? [report] : [event])
    render(<LiveEvents api={api as Api} service={createBackendService(api as Api)} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Abrir evento e1' }))
    await screen.findByText(report.description)
    expect(screen.getByText(/Sin información de restricciones/)).toBeTruthy()
    expect(api.mock.calls.some(([path]) => path.includes('/e1/reports?limit=50&offset=0'))).toBe(true)
    fireEvent.change(screen.getByLabelText('Estado de eventos'), { target: { value: 'cerrado' } })
    await waitFor(() => expect(api.mock.calls.some(([path]) => path.endsWith('state=cerrado'))).toBe(true))
  })
  it.each([403, 404, 422, 503])('muestra HTTP %i al consultar eventos sin datos de demostración', async (status) => {
    const api = vi.fn().mockRejectedValue(new ApiError('Fallo HTTP ' + status, status))
    render(<LiveEvents api={api as Api} service={createBackendService(api as Api)} />)
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('HTTP ' + status))
    expect(screen.queryByRole('button', { name: /Abrir evento/ })).toBeNull()
  })
  it('consulta propuesta, paradas y exclusiones como no operativa sin POST', async () => {
    const item: ProposalDetailDto = { id: 'p1', shift_id: 's1', status: 'propuesta', calculation_status: 'completed', result_origin: 'test_fixture', operational: false, created_by: 'manager', created_at: report.created_at, input_hash: null, algorithm_version: 'fixture-v1', matrix_source: null, distance_m: null, estimated_duration_seconds: null, stop_count: 1, excluded_count: 1, limitations: ['Solo prueba'], unknowns: ['Matriz desconocida'], input_snapshot: {}, configuration: {}, geometry_geojson: null, stops: [{ id: 'stop1', route_plan_id: 'p1', event_id: 'e1', order: 1, status: 'propuesto', estimated_service_minutes: null }], excluded_events: [{ event_id: 'e2', reason: 'Exclusión ficticia' }] }
    const api = vi.fn().mockImplementation(async (path: string) => path.endsWith('/p1') ? item : path.includes('/p1/stops') ? item.stops : path.includes('/p1/excluded-events') ? item.excluded_events : path.startsWith('/municipal/route-proposals?') ? [item] : [])
    render(<LiveProposals service={createBackendService(api as Api)} resources={createMunicipalService(api as Api)} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Abrir propuesta p1' }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('Exclusión ficticia', { exact: false })
    expect(within(dialog).getByText(/Datos de prueba · NO OPERATIVA/)).toBeTruthy()
    expect(within(dialog).getByText('Parada 1')).toBeTruthy()
    expect(screen.getByLabelText('Mapa recibido')).toBeTruthy()
    expect(within(dialog).getByText(/sin coordenadas verificables/)).toBeTruthy()
    expect(api.mock.calls.some(([, init]) => init?.method && init.method !== 'GET')).toBe(false)
    expect(api.mock.calls.some(([path]) => path.includes('/p1/stops?'))).toBe(true)
    expect(api.mock.calls.some(([path]) => path.includes('/p1/excluded-events?'))).toBe(true)
  })
})
