import type { RequestEntry } from './types'

export class ApiError extends Error {
  constructor(message: string, public status: number | null) { super(message) }
}

function errorDetail(body: unknown): string | null {
  if (!body || typeof body !== 'object' || !('detail' in body)) return null
  const { detail } = body
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((issue) => `${issue.loc?.join('.') ?? 'dato'}: ${issue.msg ?? 'valor inválido'}`).join('; ')
  }
  return null
}

export function createApi(options: {
  baseUrl: string
  getAccessToken: () => Promise<string | null>
  onRequest: (entry: RequestEntry) => void
  fetcher?: typeof fetch
}) {
  let nextId = 0
  return async function request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
    const started = performance.now()
    const time = new Date().toISOString()
    let status: number | null = null
    try {
      const headers = new Headers(init.headers)
      if (authenticated) {
        const token = await options.getAccessToken()
        if (!token) throw new ApiError('La sesión ha vencido. Vuelve a iniciar sesión.', null)
        headers.set('Authorization', `Bearer ${token}`)
      }
      // El navegador agrega el boundary al enviar FormData.
      if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
      const response = await (options.fetcher ?? fetch)(`${options.baseUrl}${path}`, {
        ...init, headers, credentials: 'omit', redirect: 'error',
        signal: init.signal ?? AbortSignal.timeout(35_000),
      })
      status = response.status
      const text = await response.text()
      let body: unknown = null
      try { body = text ? JSON.parse(text) : null } catch { /* Error HTTP sin JSON. */ }
      if (!response.ok) {
        throw new ApiError(errorDetail(body) ?? `FastAPI respondió HTTP ${status}.`, status)
      }
      if (body === null && text) throw new ApiError('La API devolvió una respuesta que no es JSON.', status)
      return body as T
    } catch (error) {
      if (error instanceof ApiError) throw error
      throw new ApiError('No se pudo completar la petición. Revisa que FastAPI esté iniciado, VITE_API_URL y CORS_ORIGINS (http://localhost:5173).', status)
    } finally {
      // Nunca guardar tokens, contraseñas, cuerpos ni URLs firmadas.
      options.onRequest({ id: ++nextId, time, method: init.method ?? 'GET', path, status,
        duration: Math.round(performance.now() - started) })
    }
  }
}
export type Api = ReturnType<typeof createApi>
