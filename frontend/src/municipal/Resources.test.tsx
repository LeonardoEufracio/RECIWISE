import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import Resources from './Resources'
import { initialDemo } from './demo'
import type { MunicipalService } from './services'
import { ApiError } from '../api'
vi.mock('../LocationMap', () => ({ default: () => <div>Mapa de prueba</div> }))
afterEach(cleanup)
function service() {
  const d = initialDemo()
  return {
    reports: vi.fn(), photos: vi.fn(), vehicles: vi.fn().mockResolvedValue(d.vehicles),
    sites: vi.fn().mockResolvedValue(d.sites), shifts: vi.fn().mockResolvedValue(d.shifts),
    createVehicle: vi.fn().mockResolvedValue(d.vehicles[0]), availability: vi.fn().mockResolvedValue(d.vehicles[0]),
    drivers: vi.fn().mockResolvedValue([{ id: d.shifts[0].driver_id, role: 'chofer' }]),
    createSite: vi.fn(), updateSite: vi.fn().mockResolvedValue(d.sites[0]), createShift: vi.fn().mockResolvedValue(d.shifts[0]),
  }
}
it('consulta recursos y muestra capacidad desconocida sin inventar valores', async () => {
  const s = service(); render(<Resources service={s as MunicipalService} simulated={false} />)
  await screen.findByText('Capacidad: No especificada')
  expect(s.vehicles).toHaveBeenCalledTimes(1); expect(s.sites).toHaveBeenCalledTimes(1); expect(s.shifts).toHaveBeenCalledTimes(1)
})
it('exige confirmar un alta y envía capacidad vacía como null sin duplicar clicks', async () => {
  const s = service(); let done: () => void = () => {}
  s.createVehicle.mockImplementation(() => new Promise((resolve) => { done = () => resolve(initialDemo().vehicles[0]) }))
  render(<Resources service={s as MunicipalService} simulated={false} />)
  await screen.findByText('Unidad demostrativa 01')
  fireEvent.change(screen.getByLabelText('Nombre de la unidad'), { target: { value: '  Unidad nueva  ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Revisar alta de vehículo' }))
  const confirm = await screen.findByRole('button', { name: 'Confirmar operación' })
  expect(s.createVehicle).not.toHaveBeenCalled()
  fireEvent.click(confirm); fireEvent.click(confirm)
  expect(s.createVehicle).toHaveBeenCalledTimes(1)
  expect(s.createVehicle.mock.calls[0][0]).toEqual({ label: 'Unidad nueva', vehicle_type: 'compactadora', plate: null, capacity_kg: null, available: false })
  done()
  await screen.findByText('Recurso guardado correctamente.')
})
it('permite cancelar una modificación de disponibilidad sin escribir', async () => {
  const s = service(); render(<Resources service={s as MunicipalService} simulated={false} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Marcar no disponible' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(s.availability).not.toHaveBeenCalled()
})
it('conserva el diálogo ante un conflicto de persistencia y no muestra éxito', async () => {
  const s = service(); s.availability.mockRejectedValue(new Error('Conflicto HTTP 409'))
  render(<Resources service={s as MunicipalService} simulated={false} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Marcar no disponible' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar operación' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('dialog')).toBeTruthy()
  expect(within(screen.getByRole('dialog')).getByRole('alert').textContent).toContain('Conflicto HTTP 409')
  expect(screen.queryByText('Recurso guardado correctamente.')).toBeNull()
  expect(s.availability).toHaveBeenCalledTimes(1)
})
it('no ofrece una unidad indisponible para un nuevo turno ni inventa choferes', async () => {
  const s = service(); render(<Resources service={s as MunicipalService} simulated={false} />)
  await screen.findByText('Unidad demostrativa 01')
  fireEvent.click(screen.getByRole('button', { name: 'Turnos' }))
  const option = screen.getByRole('option', { name: 'Unidad demostrativa 02 — No disponible' }) as HTMLOptionElement
  expect(option.disabled).toBe(true)
  expect(screen.getByRole('combobox', { name: /Chofer autorizado/ })).toBeTruthy()
  expect(s.drivers).toHaveBeenCalledTimes(1)
  expect(s.createShift).not.toHaveBeenCalled()
})
it('un error de lectura permite reintentar sin producir altas', async () => {
  const s = service(); s.vehicles.mockRejectedValueOnce(new Error('Servicio temporalmente no disponible'))
  render(<Resources service={s as MunicipalService} simulated={false} />)
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Volver a intentar' }))
  await screen.findByText('Unidad demostrativa 01')
  await waitFor(() => expect(s.vehicles).toHaveBeenCalledTimes(2))
  expect(s.createVehicle).not.toHaveBeenCalled()
})
it('edita un punto conservando números y confirmación antes de persistir', async () => {
  const s = service(); const site = initialDemo().sites[0]
  render(<Resources service={s as MunicipalService} simulated={false} />)
  await screen.findByText('Unidad demostrativa 01')
  fireEvent.click(screen.getByRole('button', { name: 'Sitios' }))
  fireEvent.click(screen.getByRole('button', { name: 'Editar sitio ' + site.name }))
  fireEvent.change(screen.getByLabelText('Nombre del punto'), { target: { value: 'Punto corregido' } })
  fireEvent.click(screen.getByText('Revisar cambios del punto'))
  expect(s.updateSite).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Confirmar edición'))
  await waitFor(() => expect(s.updateSite).toHaveBeenCalledTimes(1))
  expect(s.updateSite.mock.calls[0]).toEqual([site.id, { name: 'Punto corregido', site_type: site.site_type, active: true, latitude: site.latitude, longitude: site.longitude }])
})
it.each([500, 503])('un alta de resultado incierto %i no ofrece reenviar y consulta los recursos', async (code) => {
  const s = service(); s.createVehicle.mockRejectedValue(new ApiError('HTTP ' + code, code))
  render(<Resources service={s as MunicipalService} simulated={false} />)
  await screen.findByText('Unidad demostrativa 01')
  fireEvent.change(screen.getByLabelText('Nombre de la unidad'), { target: { value: 'Unidad incierta' } })
  fireEvent.click(screen.getByText('Revisar alta de vehículo'))
  const confirm = await screen.findByRole('button', { name: 'Confirmar operación' })
  await waitFor(() => expect((confirm as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(confirm)
  await screen.findByText(/Resultado no confirmado/)
  expect(screen.queryByText('Confirmar operación')).toBeNull()
  fireEvent.click(screen.getByText('Consultar recursos actualizados'))
  await screen.findByText('Unidad demostrativa 01')
  expect(s.createVehicle).toHaveBeenCalledTimes(1)
})
