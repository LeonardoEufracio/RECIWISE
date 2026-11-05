import type { Api } from '../api'
import type { Audit, Intent, OperationResult, RouteDetail, RouteState, RouteSummary } from './types'

const encode = encodeURIComponent
export function createOperationsService(api: Api, scope: 'municipal' | 'driver') {
  const root = '/' + scope + '/routes'
  return {
    scope,
    async routes(offset = 0, status?: RouteState, signal?: AbortSignal) {
      const value = await api<RouteSummary[]>(root + '?' + new URLSearchParams({ limit: '50', offset: String(offset), ...(status ? { status } : {}) }), { signal })
      if (!Array.isArray(value)) throw new Error('Respuesta de rutas incompatible con FastAPI.')
      return value
    },
    detail: (id: string, signal?: AbortSignal) => api<RouteDetail>(root + '/' + encode(id), { signal }),
    operation: (route: string, op: string) => api<Audit>(root + '/' + encode(route) + '/operations/' + encode(op)),
    perform: (intent: Intent) => api<OperationResult>(root + '/' + encode(intent.routeId) + (scope === 'municipal' ? '/decisions' : intent.stopId ? '/stops/' + encode(intent.stopId) + '/actions' : '/actions'), { method: 'POST', body: JSON.stringify(intent.command) }),
  }
}
export type OperationsService = ReturnType<typeof createOperationsService>
