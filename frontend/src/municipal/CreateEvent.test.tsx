import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ApiError } from '../api'
import type { BackendService } from './backendService'
import CreateEvent from './CreateEvent'

vi.mock('../LocationPicker', () => ({ default: ({ onChange }: { onChange: (p: object) => void }) => <button type="button" onClick={() => onChange({ latitude: -12.04, longitude: -77.03, source: 'map', confirmed: true })}>Confirmar punto de prueba</button> }))
afterEach(cleanup)
function setup() {
  const service = { groupings: vi.fn().mockResolvedValue([]), createEvent: vi.fn().mockResolvedValue({ id: 'evento' }) }
  const saved = vi.fn()
  render(<CreateEvent service={service as unknown as BackendService} saved={saved} close={vi.fn()} />)
  return { service, saved }
}
async function prepare() {
  await screen.findByText('Sin reportes en esta página')
  fireEvent.click(screen.getByText('Confirmar punto de prueba'))
  fireEvent.change(screen.getByLabelText('Intervención manual (opcional)'), { target: { value: '  Recolección manual  ' } })
  fireEvent.click(screen.getByText('Revisar evento manual'))
}
it('confirma ubicación y evento antes del POST y evita envíos duplicados', async () => {
  const { service, saved } = setup()
  expect((screen.getByText('Revisar evento manual') as HTMLButtonElement).disabled).toBe(true)
  await prepare()
  expect(service.createEvent).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Confirmar creación de evento')); fireEvent.click(screen.getByText('Guardando evento…'))
  await screen.findByText('Confirmar creación de evento')
  expect(saved).toHaveBeenCalledWith('evento')
  expect(service.createEvent).toHaveBeenCalledExactlyOnceWith({ latitude: -12.04, longitude: -77.03, intervention_type: 'Recolección manual', report_ids: [] })
})
it('409 vuelve a revisión sin repetir automáticamente la asociación', async () => {
  const { service } = setup()
  service.createEvent.mockRejectedValue(new ApiError('Conflicto HTTP 409', 409))
  await prepare(); fireEvent.click(screen.getByText('Confirmar creación de evento'))
  await screen.findByRole('alert')
  expect(screen.queryByText('Confirmar creación de evento')).toBeNull()
  expect(service.createEvent).toHaveBeenCalledTimes(1)
})
it.each([500, 503])('%i conserva el resultado incierto y exige consultar antes de crear otro', async (code) => {
  const { service } = setup()
  service.createEvent.mockRejectedValue(new ApiError('Servicio HTTP ' + code, code))
  await prepare(); fireEvent.click(screen.getByText('Confirmar creación de evento'))
  await screen.findByText(/El resultado no está confirmado/)
  expect(screen.queryByText('Confirmar creación de evento')).toBeNull()
  expect(service.createEvent).toHaveBeenCalledTimes(1)
})
