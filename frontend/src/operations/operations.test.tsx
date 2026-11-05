import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ApiError, type Api } from '../api'
import DriverWorkspace from './DriverWorkspace'
import OperationConfirm from './OperationConfirm'
import RouteManagement from './RouteManagement'
import { createOperationsService } from './service'
import type { Intent, RouteDetail } from './types'

vi.mock('../municipal/RouteMap', () => ({ default: ({ events }: { events: object[] }) => <div>Mapa de {events.length} paradas de la instantánea</div> }))
afterEach(cleanup)
const route: RouteDetail = {
  id: 'route1', shift_id: 'shift1', driver_id: 'driver1', vehicle_id: 'v1', vehicle_label: 'Unidad de prueba',
  starts_at: '2026-10-31T08:00:00Z', ends_at: '2026-10-31T18:00:00Z', created_at: '2026-10-31T07:00:00Z',
  status: 'aprobada', revision: null, approved_by: 'manager', approved_at: '2026-10-31T07:10:00Z',
  approval_verified: true, can_approve: false, approval_blockers: [], shift_status: 'programado', vehicle_available: true,
  departure: { id: 's1', name: 'Salida de prueba', site_type: 'salida', active: true, latitude: -12, longitude: -77 },
  disposal: { id: 's2', name: 'Descarga de prueba', site_type: 'descarga', active: true, latitude: -12, longitude: -77 },
  stops: [{ id: 'stop1', event_id: 'event1', order: 1, latitude: -12, longitude: -77, status: 'pendiente', estimated_service_minutes: null, visited_at: null, recorded_by: null, incidents: [] }],
  history: [], distance_m: null, estimated_duration_seconds: null, geometry_geojson: null, limitations: ['Autorización ficticia de prueba de interfaz'], excluded_events: [],
}
const initial: Intent = { scope: 'municipal', routeId: route.id, stage: 'prepared', error: '', notFound: false, command: { operation_id: '12345678-1234-4234-8234-123456789abc', expected_status: 'propuesta', expected_revision: null, decision: 'reject', notes: 'Motivo de prueba' } }
it('la confirmación conserva el comando y bloquea doble envío', async () => {
  let complete: () => void = () => {}
  const api = vi.fn().mockImplementation(() => new Promise((resolve) => { complete = () => resolve({ route }) }))
  const saved = vi.fn()
  render(<OperationConfirm service={createOperationsService(api as Api, 'municipal')} initial={initial} close={vi.fn()} saved={saved} />)
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar operación de ruta' }))
  fireEvent.click(screen.getByText('Guardando operación…'))
  expect(api).toHaveBeenCalledTimes(1)
  expect(JSON.parse(api.mock.calls[0][1].body)).toEqual(initial.command)
  complete(); await waitFor(() => expect(saved).toHaveBeenCalledTimes(1))
})
it('409 exige actualizar y confirmar nuevamente sin reenvíos', async () => {
  const api = vi.fn().mockRejectedValue(new ApiError('HTTP 409', 409))
  render(<OperationConfirm service={createOperationsService(api as Api, 'municipal')} initial={initial} close={vi.fn()} saved={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar operación de ruta' }))
  await screen.findByText(/La ruta cambió o no permite esta acción/)
  expect(screen.queryByRole('button', { name: 'Confirmar operación de ruta' })).toBeNull()
  expect(api).toHaveBeenCalledTimes(1)
})
it.each([null, 500, 503])('resultado incierto %s: consulta UUID y repite exactamente el cuerpo solo tras 404', async (code) => {
  let posts = 0
  const api = vi.fn().mockImplementation(async (_: string, init?: RequestInit) => {
    if (init?.method === 'POST') { if (++posts === 1) throw new ApiError('Resultado incierto', code); return { route } }
    throw new ApiError('Operación no encontrada', 404)
  })
  const saved = vi.fn()
  render(<OperationConfirm service={createOperationsService(api as Api, 'municipal')} initial={initial} close={vi.fn()} saved={saved} />)
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar operación de ruta' }))
  await screen.findByText(/Resultado incierto. Consulta/)
  expect(screen.queryByText('Reintentar el mismo comando de ruta')).toBeNull()
  fireEvent.click(screen.getByText('Comprobar operación de ruta'))
  fireEvent.click(await screen.findByText('Reintentar el mismo comando de ruta'))
  await waitFor(() => expect(saved).toHaveBeenCalled())
  const writes = api.mock.calls.filter(([, init]) => init?.method === 'POST')
  expect(writes).toHaveLength(2)
  expect(writes[0][1].body).toBe(writes[1][1].body)
})
it('commit confirmado por UUID se recupera sin otro POST', async () => {
  const api = vi.fn().mockImplementation(async (_: string, init?: RequestInit) => {
    if (init?.method === 'POST') throw new ApiError('HTTP 503', 503)
    return { operation_id: initial.command.operation_id }
  })
  const saved = vi.fn()
  render(<OperationConfirm service={createOperationsService(api as Api, 'municipal')} initial={initial} close={vi.fn()} saved={saved} />)
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar operación de ruta' }))
  fireEvent.click(await screen.findByText('Comprobar operación de ruta'))
  await waitFor(() => expect(saved).toHaveBeenCalled())
  expect(api.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
})
it('municipal revisa recursos, ve bloqueo operativo y rechaza con estado esperado', async () => {
  const item = { ...route, status: 'propuesta', approval_verified: false, approved_by: null, approved_at: null }
  const api = vi.fn().mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return { route: { ...item, status: 'cancelada' } }
    return path.includes('?') ? [item] : item
  })
  render(<RouteManagement api={api as Api} onPending={vi.fn()} />)
  fireEvent.click(await screen.findByText('Revisar ruta route1'))
  const review = await screen.findByRole('dialog')
  await within(review).findByText('Salida de prueba')
  expect((within(review).getByText('Aprobar y asignar (proveedor pendiente)') as HTMLButtonElement).disabled).toBe(true)
  fireEvent.change(within(review).getByLabelText('Motivo de la decisión'), { target: { value: 'No es operativa' } })
  fireEvent.click(within(review).getByText('Revisar decisión de ruta'))
  const confirm = screen.getByRole('dialog', { name: 'Confirmar operación de ruta' })
  fireEvent.click(within(confirm).getByRole('button', { name: 'Confirmar operación de ruta' }))
  await waitFor(() => expect(api.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
  const body = JSON.parse(api.mock.calls.find(([, init]) => init?.method === 'POST')![1].body)
  expect(body.decision).toBe('reject'); expect(body.expected_status).toBe('propuesta'); expect(body.expected_revision).toBe(null)
})
it('chofer sin asignaciones no recibe propuestas ficticias', async () => {
  const api = vi.fn().mockResolvedValue([])
  render(<DriverWorkspace api={api as Api} />)
  await screen.findByText('No tienes recorridos autorizados')
  expect(api.mock.calls.every(([path]) => path.startsWith('/driver/routes'))).toBe(true)
})
it('chofer consulta paradas y confirma el inicio con revisión y UUID', async () => {
  const api = vi.fn().mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return { route: { ...route, status: 'en_ejecucion' } }
    return path.includes('?') ? [route] : route
  })
  render(<DriverWorkspace api={api as Api} />)
  fireEvent.click(await screen.findByText('Abrir mi recorrido route1'))
  await screen.findByText('Mapa de 1 paradas de la instantánea')
  fireEvent.click(screen.getByText('Revisar inicio de recorrido'))
  expect(api.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar operación de ruta' }))
  await waitFor(() => expect(api.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
  const write = api.mock.calls.find(([, init]) => init?.method === 'POST')!
  expect(write[0]).toBe('/driver/routes/route1/actions')
  expect(JSON.parse(write[1].body)).toMatchObject({ action: 'start', expected_status: 'aprobada', expected_revision: null })
})
it.each(['Registrar incidencia', 'Registrar no atención'])('chofer exige motivo para %s y conserva la ubicación en el mapa', async (name) => {
  const item = { ...route, status: 'en_ejecucion', revision: 'previous-operation' }
  const api = vi.fn().mockImplementation(async (path: string) => path.includes('?') ? [item] : item)
  render(<DriverWorkspace api={api as Api} />)
  fireEvent.click(await screen.findByText('Abrir mi recorrido route1'))
  fireEvent.click(await screen.findByText(name))
  await screen.findByText('Escribe el motivo de la incidencia o de la no atención.')
  expect(api.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  fireEvent.change(screen.getByLabelText('Observación o motivo de no atención'), { target: { value: 'Acceso bloqueado' } })
  fireEvent.change(screen.getByLabelText('Tipo de incidencia (si corresponde)'), { target: { value: 'acceso' } })
  fireEvent.click(screen.getByText(name))
  await screen.findByRole('dialog', { name: 'Confirmar operación de ruta' })
  expect(screen.getByText('Mapa de 1 paradas de la instantánea')).toBeTruthy()
})
it.each([401, 403, 404, 422, 503])('chofer muestra HTTP %i sin mezclar demostraciones', async (status) => {
  render(<DriverWorkspace api={vi.fn().mockRejectedValue(new ApiError('HTTP ' + status, status)) as Api} />)
  expect((await screen.findByRole('alert')).textContent).toContain(String(status))
  expect(screen.queryByText('No tienes recorridos autorizados')).toBeNull()
})
