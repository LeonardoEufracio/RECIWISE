import type { Api } from '../api'
import type { Photo, Report } from '../types'
import type { Driver, Shift, ShiftInput, Site, SiteInput, Vehicle, VehicleInput } from './model'

export function createMunicipalService(api: Api) {
  return {
    reports: (limit = 50, offset = 0, status = '', signal?: AbortSignal) => {
      const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
      if (status) query.set('status', status)
      return api<Report[]>('/municipal/reports?' + query, { signal })
    },
    photos: (id: string) => api<Photo[]>('/reports/' + encodeURIComponent(id) + '/photos'),
    vehicles: (signal?: AbortSignal) => api<Vehicle[]>('/municipal/vehicles', { signal }),
    sites: (signal?: AbortSignal) => api<Site[]>('/municipal/sites', { signal }),
    shifts: (signal?: AbortSignal) => api<Shift[]>('/municipal/shifts', { signal }),
    drivers: async (signal?: AbortSignal) => {
      const result: Driver[] = []
      for (let offset = 0; ; offset += 200) {
        if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
        const page = await api<Driver[]>('/municipal/drivers?limit=200&offset=' + offset, { signal })
        if (!Array.isArray(page)) throw new Error('Directorio de choferes incompatible con FastAPI.')
        result.push(...page)
        if (page.length < 200) return result
      }
    },
    createVehicle: (value: VehicleInput) => api<Vehicle>('/municipal/vehicles', { method: 'POST', body: JSON.stringify(value) }),
    availability: (id: string, available: boolean) => api<Vehicle>('/municipal/vehicles/' + encodeURIComponent(id) + '/availability', { method: 'PATCH', body: JSON.stringify({ available }) }),
    createSite: (value: SiteInput) => api<Site>('/municipal/sites', { method: 'POST', body: JSON.stringify(value) }),
    updateSite: (id: string, value: Partial<SiteInput> & { active?: boolean }) => api<Site>('/municipal/sites/' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify(value) }),
    createShift: (value: ShiftInput) => api<Shift>('/municipal/shifts', { method: 'POST', body: JSON.stringify(value) }),
  }
}
export type MunicipalService = ReturnType<typeof createMunicipalService>

export function mayUseDemo(development: boolean, flag: string | undefined) {
  return development && flag === 'true'
}

export async function reportSnapshot(service: Pick<MunicipalService, 'reports'>, signal?: AbortSignal) {
  const unique = new Map<string, Report>()
  let complete = false
  for (let offset = 0; offset < 1000; offset += 200) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const page = await service.reports(200, offset, '', signal)
    page.forEach((report) => unique.set(report.id, report))
    if (page.length < 200) { complete = true; break }
  }
  return { reports: [...unique.values()], complete, fetchedAt: new Date().toISOString() }
}
