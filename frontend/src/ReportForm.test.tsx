import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ReportForm from './ReportForm'
import LocationPicker from './LocationPicker'
import type { Api } from './api'
import type { Coordinates } from './types'

vi.mock('./LocationMap', () => ({ default: ({ onPick, editable }: { onPick: (point: Coordinates) => void; editable: boolean }) =>
  <div>
    <button type="button" disabled={!editable} onClick={() => onPick({ latitude: -12.05, longitude: -75.2 })}>Tocar mapa de prueba</button>
    <button type="button" disabled={!editable} onClick={() => onPick({ latitude: -12.06, longitude: -75.21 })}>Arrastrar marcador de prueba</button>
  </div> }))

const gps = vi.fn<Geolocation['getCurrentPosition']>()
beforeEach(() => {
  gps.mockReset()
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: gps } })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function setup() {
  const api = vi.fn<Api>().mockResolvedValue({ id: 'report-1' })
  const onCreated = vi.fn()
  const view = render(<ReportForm api={api as Api} onCreated={onCreated} />)
  fireEvent.change(screen.getByLabelText('Descripción'), { target: { value: 'Acumulación para prueba del selector' } })
  return { api, onCreated, ...view }
}
function click(name: string) { fireEvent.click(screen.getByRole('button', { name })) }
// La interfaz bloquea el botón; comprobar también la validación del handler
// cuando se intenta enviar por Enter o por código.
function attemptSubmit() { fireEvent.submit(screen.getByLabelText('Descripción').closest('form')!) }
function gpsSuccess(accuracy = 12) {
  act(() => gps.mock.calls[0][0]({ coords: { latitude: -12.07, longitude: -75.22, accuracy } } as GeolocationPosition))
}

describe('Ubicación ciudadana y consentimiento', () => {
  it('no pide GPS al montar ni presenta campos técnicos; valida ubicación antes de POST', async () => {
    const { api, container } = setup()
    expect(gps).not.toHaveBeenCalled()
    expect(container.querySelector('input[name="latitude"], input[name="longitude"]')).toBeNull()
    expect((screen.getByRole('button', { name: 'Registrar reporte' }) as HTMLButtonElement).disabled).toBe(true)
    attemptSubmit()
    await screen.findByText('Selecciona y confirma la ubicación del reporte antes de enviarlo.')
    expect(api).not.toHaveBeenCalled()
  })

  it('guarda solo en memoria hasta confirmar y enviar; conserva el contrato numérico', async () => {
    const save = vi.spyOn(Storage.prototype, 'setItem')
    const { api, onCreated } = setup()
    click('Elegir en el mapa'); click('Tocar mapa de prueba')
    expect((screen.getByRole('button', { name: 'Registrar reporte' }) as HTMLButtonElement).disabled).toBe(true)
    attemptSubmit()
    await screen.findByText('Selecciona y confirma la ubicación del reporte antes de enviarlo.')
    expect(api).not.toHaveBeenCalled()
    click('Confirmar ubicación')
    expect((screen.getByRole('button', { name: 'Registrar reporte' }) as HTMLButtonElement).disabled).toBe(false)
    expect(api).not.toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
    click('Registrar reporte')
    await waitFor(() => expect(onCreated).toHaveBeenCalled())
    const payload = JSON.parse(String(api.mock.calls[0][1]?.body))
    expect(payload).toEqual({ description: 'Acumulación para prueba del selector', latitude: -12.05, longitude: -75.2,
      observed_at: expect.stringMatching(/Z$/), waste_type: null })
    expect(screen.queryByText(/Punto seleccionado/)).toBeNull()
    expect(gps).not.toHaveBeenCalled()
  })

  it('solicita GPS solo al pulsar y muestra carga, precisión y confirmación independiente del envío', async () => {
    const { api } = setup()
    click('Usar mi ubicación')
    expect(gps).toHaveBeenCalledTimes(1)
    expect(gps.mock.calls[0][2]).toEqual({ enableHighAccuracy: true, timeout: 15000, maximumAge: 0 })
    expect(screen.getByText(/Buscando tu ubicación/)).toBeTruthy()
    gpsSuccess()
    expect(screen.getByText(/Precisión estimada: ±12 m/)).toBeTruthy()
    expect(screen.getByText(/-12.070000, -75.220000/)).toBeTruthy()
    expect(screen.getByText(/Origen: ubicación del dispositivo/)).toBeTruthy()
    expect(screen.getByText(/no solo dónde estás/)).toBeTruthy()
    expect(api).not.toHaveBeenCalled()
    click('Confirmar ubicación')
    expect(api).not.toHaveBeenCalled()
    click('Registrar reporte')
    await waitFor(() => expect(api).toHaveBeenCalledTimes(1))
    const payload = JSON.parse(String(api.mock.calls[0][1]?.body))
    expect(payload.latitude).toBe(-12.07)
    expect(payload.longitude).toBe(-75.22)
    expect(payload).not.toHaveProperty('accuracy')
  })

  it('exige otra confirmación al corregir y descarta la precisión del GPS al mover el punto', async () => {
    const { api } = setup()
    click('Usar mi ubicación'); gpsSuccess(); click('Confirmar ubicación')
    expect((screen.getByRole('button', { name: 'Arrastrar marcador de prueba' }) as HTMLButtonElement).disabled).toBe(true)
    click('Corregir ubicación'); click('Arrastrar marcador de prueba')
    expect(screen.queryByText(/Precisión estimada/)).toBeNull()
    attemptSubmit()
    await screen.findByText('Selecciona y confirma la ubicación del reporte antes de enviarlo.')
    expect(api).not.toHaveBeenCalled()
    click('Confirmar ubicación'); click('Registrar reporte')
    await waitFor(() => expect(api).toHaveBeenCalledTimes(1))
    expect(JSON.parse(String(api.mock.calls[0][1]?.body)).latitude).toBe(-12.06)
  })

  it.each([
    [1, 'Se denegó el permiso de ubicación'], [2, 'No se pudo determinar tu ubicación'], [3, 'La ubicación tardó demasiado'],
  ] as const)('explica el error GPS %s y permite elegir manualmente', (code, message) => {
    const { api } = setup()
    click('Usar mi ubicación')
    act(() => gps.mock.calls[0][1]?.({ code } as GeolocationPositionError))
    expect(screen.getByRole('alert').textContent).toContain(message)
    click('Elegir en el mapa'); click('Tocar mapa de prueba')
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('button', { name: 'Confirmar ubicación' })).toBeTruthy()
    expect(api).not.toHaveBeenCalled()
  })

  it('ignora una respuesta GPS tardía si el ciudadano ya eligió manualmente', () => {
    setup()
    click('Usar mi ubicación'); click('Elegir en el mapa'); click('Tocar mapa de prueba')
    gpsSuccess()
    expect(screen.getByText(/-12.050000, -75.200000/)).toBeTruthy()
    expect(screen.queryByText(/Precisión estimada/)).toBeNull()
  })

  it('descarta la respuesta GPS al desmontar el selector o cerrar sesión', () => {
    const onChange = vi.fn()
    const { unmount } = render(<LocationPicker location={null} onChange={onChange} disabled={false} />)
    click('Usar mi ubicación')
    unmount(); gpsSuccess()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('deshabilita la confirmación anterior al volver a pedir GPS', async () => {
    const { api } = setup()
    click('Elegir en el mapa'); click('Tocar mapa de prueba'); click('Confirmar ubicación')
    click('Usar mi ubicación'); attemptSubmit()
    await screen.findByText('Selecciona y confirma la ubicación del reporte antes de enviarlo.')
    expect(api).not.toHaveBeenCalled()
    expect((screen.getByRole('button', { name: 'Confirmar ubicación' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('explica HTTPS/localhost cuando el contexto no es seguro', () => {
    vi.stubGlobal('isSecureContext', false)
    setup(); click('Usar mi ubicación')
    expect(screen.getByRole('alert').textContent).toContain('HTTPS en móvil o localhost')
    expect(gps).not.toHaveBeenCalled()
  })

  it('ofrece el mapa cuando el navegador no dispone de geolocalización', () => {
    vi.stubGlobal('navigator', {})
    setup(); click('Usar mi ubicación')
    expect(screen.getByRole('alert').textContent).toContain('no ofrece geolocalización')
  })

  it('no muestra una precisión inexistente ni acepta coordenadas GPS inválidas', () => {
    setup(); click('Usar mi ubicación'); gpsSuccess(NaN)
    expect(screen.queryByText(/Precisión estimada/)).toBeNull()
    click('Usar mi ubicación')
    act(() => gps.mock.calls[1][0]({ coords: { latitude: NaN, longitude: 0 } } as GeolocationPosition))
    expect(screen.getByRole('alert').textContent).toContain('ubicación inválida')
  })
})
