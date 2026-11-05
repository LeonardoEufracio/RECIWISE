import { describe, expect, it, vi } from 'vitest'
import type { Api } from '../api'
import { ApiError } from '../api'
import { createBackendService } from './backendService'
import { snapshotEvents } from './backendUi'
import type { DecisionCommand, ProposalDetailDto } from './backendTypes'

describe('Contratos REST de Sprint 2 (API simulada)', () => {
  it('consulta todos los endpoints reales, conserva filtros booleanos y cancela lecturas', async () => {
    const api = vi.fn().mockResolvedValue([])
    const s = createBackendService(api as Api); const signal = new AbortController().signal
    await s.events({ state: 'cerrado', offset: 50 }, signal); await s.event('evento id', signal)
    await s.eventReports('evento id', { offset: 50 }, signal)
    await s.groupings({ linked: false, pending_review: true }, signal); await s.relation('reporte id', signal)
    await s.candidates('reporte id', {}, signal); await s.decisions({ report_id: 'reporte id', event_id: 'evento id' }, signal)
    await s.decision('operación id', signal)
    await s.proposals({ calculation_status: 'completed', result_origin: 'test_fixture', shift_id: 'turno id' }, signal)
    await s.proposal('propuesta id', signal); await s.stops('propuesta id', {}, signal); await s.exclusions('propuesta id', {}, signal)
    expect(api.mock.calls.map(([path]) => path)).toEqual([
      '/municipal/events?limit=50&offset=50&state=cerrado', '/municipal/events/evento%20id', '/municipal/events/evento%20id/reports?limit=50&offset=50',
      '/municipal/groupings?limit=50&offset=0&linked=false&pending_review=true', '/municipal/groupings/reports/reporte%20id',
      '/municipal/groupings/candidates?report_id=reporte+id&limit=50&offset=0', '/municipal/groupings/decisions?limit=50&offset=0&report_id=reporte+id&event_id=evento+id',
      '/municipal/groupings/decisions/operaci%C3%B3n%20id', '/municipal/route-proposals?limit=50&offset=0&calculation_status=completed&result_origin=test_fixture&shift_id=turno+id',
      '/municipal/route-proposals/propuesta%20id', '/municipal/route-proposals/propuesta%20id/stops?limit=50&offset=0', '/municipal/route-proposals/propuesta%20id/excluded-events?limit=50&offset=0',
    ])
    expect(api.mock.calls.every(([, init]) => init.signal === signal && !init.method)).toBe(true)
  })
  it('envía el comando confirmado sin inventar metadatos ni omitir estados esperados nulos', async () => {
    const api = vi.fn().mockResolvedValue({}); const s = createBackendService(api as Api)
    const command: DecisionCommand = { operation_id: crypto.randomUUID(), report_id: crypto.randomUUID(), decision: 'agrupar', candidate_event_id: crypto.randomUUID(), expected_event_id: null, expected_decision_id: null, notes: null }
    await s.decide(command)
    expect(api).toHaveBeenCalledOnce()
    expect(api.mock.calls[0][0]).toBe('/municipal/groupings/decisions')
    expect(JSON.parse(api.mock.calls[0][1].body)).toEqual(command)
    expect(api.mock.calls[0][1].method).toBe('POST')
    expect('createProposal' in s).toBe(false)
  })
  it.each([401, 403, 404, 409, 422, 503])('preserva HTTP %i y no reintenta escrituras', async (status) => {
    const err = new ApiError('Error controlado', status)
    const api = vi.fn().mockRejectedValue(err)
    await expect(createBackendService(api as Api).decide({} as DecisionCommand)).rejects.toBe(err)
    expect(api).toHaveBeenCalledOnce()
  })
  it('rechaza un listado incompatible sin sustituirlo por datos de demostración', async () => {
    await expect(createBackendService(vi.fn().mockResolvedValue({ items: [] }) as Api).events()).rejects.toThrow('contrato')
  })
})

describe('Coordenadas de la instantánea de rutas', () => {
  it('utiliza solo coordenadas explícitas válidas de operational.events', () => {
    const snapshot = { operational: { events: [{ id: 'ok', latitude: -12, longitude: -75 }, { id: 'fuera', latitude: 91, longitude: 0 }, { id: 'texto', latitude: '-12', longitude: -75 }, null] } }
    expect(snapshotEvents({ input_snapshot: snapshot } as unknown as ProposalDetailDto)).toEqual([{ id: 'ok', latitude: -12, longitude: -75 }])
  })
  it.each([{}, { operational: null }, { operational: [] }, { operational: { events: {} } }])('no inventa posiciones para %j', (input_snapshot) => {
    expect(snapshotEvents({ input_snapshot } as unknown as ProposalDetailDto)).toEqual([])
  })
})
