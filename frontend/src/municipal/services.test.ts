import { describe, expect, it, vi } from 'vitest'
import type { Api } from '../api'
import { createMunicipalService, mayUseDemo, reportSnapshot } from './services'
import { initialDemo } from './demo'

describe('Contratos municipales y separación de fuentes', () => {
  it.each([[true, 'true', true], [true, undefined, false], [true, 'false', false], [false, 'true', false]])('habilitación de demostración %s/%s → %s', (dev, flag, expected) => {
    expect(mayUseDemo(dev as boolean, flag as string | undefined)).toBe(expected)
  })
  it('respeta los endpoints y cuerpos reales sin inventar rutas D2/D3', async () => {
    const api = vi.fn().mockResolvedValue([])
    const s = createMunicipalService(api as Api)
    const d = initialDemo()
    await s.reports(50, 100, 'en_revision'); await s.vehicles(); await s.sites(); await s.shifts()
    const { id: _v, ...vehicle } = d.vehicles[0]
    const { id: _s, active: _a, ...site } = d.sites[0]
    const { id: _t, created_by: _c, status: _state, ...shift } = d.shifts[0]
    await s.createVehicle(vehicle); await s.availability('vehicle id', false); await s.createSite(site); await s.createShift(shift)
    expect(api.mock.calls.map(([path]) => path)).toEqual([
      '/municipal/reports?limit=50&offset=100&status=en_revision', '/municipal/vehicles', '/municipal/sites', '/municipal/shifts',
      '/municipal/vehicles', '/municipal/vehicles/vehicle%20id/availability', '/municipal/sites', '/municipal/shifts',
    ])
    expect(JSON.parse(api.mock.calls[4][1].body)).toEqual(vehicle)
    expect(JSON.parse(api.mock.calls[5][1].body)).toEqual({ available: false })
    expect(JSON.parse(api.mock.calls[6][1].body)).toEqual(site)
    expect(JSON.parse(api.mock.calls[7][1].body)).toEqual(shift)
  })
  it('consulta todas las páginas y elimina IDs repetidos sin inflar el total', async () => {
    const base = initialDemo().reports[0]
    const reports = vi.fn().mockResolvedValueOnce(Array.from({ length: 200 }, (_, i) => ({ ...base, id: String(i) })))
      .mockResolvedValueOnce([{ ...base, id: '199' }, { ...base, id: '200' }])
    const result = await reportSnapshot({ reports })
    expect(result.complete).toBe(true)
    expect(result.reports.length).toBe(201)
    expect(reports.mock.calls.map((args) => args.slice(0, 2))).toEqual([[200, 0], [200, 200]])
  })
  it('declara muestra limitada al alcanzar el máximo, sin afirmar un total global', async () => {
    const reports = vi.fn().mockImplementation(async (_limit, offset) => Array.from({ length: 200 }, (_, i) => ({ ...initialDemo().reports[0], id: String(i + offset) })))
    const result = await reportSnapshot({ reports })
    expect(result.complete).toBe(false); expect(result.reports).toHaveLength(1000); expect(reports).toHaveBeenCalledTimes(5)
  })
  it('interrumpe la consulta cancelada sin seguir paginando', async () => {
    const controller = new AbortController(); controller.abort()
    const reports = vi.fn()
    await expect(reportSnapshot({ reports }, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(reports).not.toHaveBeenCalled()
  })
  it('no convierte un error del servidor en estadísticas vacías', async () => {
    await expect(reportSnapshot({ reports: vi.fn().mockRejectedValue(new Error('Servicio temporalmente no disponible')) })).rejects.toThrow('temporalmente')
  })
  it('el selector consulta también choferes posteriores a la primera página', async () => {
    const api = vi.fn().mockResolvedValueOnce(Array.from({ length: 200 }, (_, i) => ({ id: String(i), role: 'chofer' })))
      .mockResolvedValueOnce([{ id: 'ultimo', role: 'chofer' }])
    expect(await createMunicipalService(api as Api).drivers()).toHaveLength(201)
    expect(api.mock.calls[1][0]).toBe('/municipal/drivers?limit=200&offset=200')
  })
})
