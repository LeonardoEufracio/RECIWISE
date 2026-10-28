import { describe, expect, it, vi } from 'vitest'
import { ApiError, createApi } from './api'
import type { RequestEntry } from './types'

function setup(fetcher: typeof fetch, getAccessToken: () => Promise<string | null> = async () => 'access-token-de-prueba') {
  const entries: RequestEntry[] = []
  const api = createApi({ baseUrl: 'http://api.test', getAccessToken, fetcher, onRequest: (entry) => entries.push(entry) })
  return { api, entries }
}

describe('Comunicación con FastAPI', () => {
  it('obtiene el token actual en cada petición y registra HTTP sin credenciales', async () => {
    const token = vi.fn().mockResolvedValueOnce('primer-token').mockResolvedValueOnce('token-renovado')
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => new Response('{"role":"ciudadano"}', { status: 200 }))
    const { api, entries } = setup(fetcher, token)
    await api('/me'); await api('/reports/mine')
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer primer-token')
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Authorization')).toBe('Bearer token-renovado')
    expect(fetcher.mock.calls[0][1]?.credentials).toBe('omit')
    expect(entries.map((entry) => entry.status)).toEqual([200, 200])
    expect(JSON.stringify(entries)).not.toContain('token')
  })

  it('sube multipart con file sin imponer Content-Type y conserva HTTP 201', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{"id":"foto"}', { status: 201 }))
    const { api, entries } = setup(fetcher)
    const body = new FormData()
    body.append('file', new File(['image'], 'foto.png', { type: 'image/png' }))
    await api('/reports/reporte/photos', { method: 'POST', body })
    const init = fetcher.mock.calls[0][1]!
    expect(init.body).toBe(body)
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
    expect(entries[0].status).toBe(201)
    expect(JSON.stringify(entries)).not.toContain('foto.png')
  })

  it('conserva códigos de permisos y detalles de validación de FastAPI', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response('{"detail":"No tienes permiso"}', { status: 403 }))
      .mockResolvedValueOnce(new Response('{"detail":[{"loc":["body","observed_at"],"msg":"La fecha debe incluir zona horaria"}]}', { status: 422 }))
    const { api, entries } = setup(fetcher)
    await expect(api('/municipal/reports')).rejects.toMatchObject({ status: 403, message: 'No tienes permiso' })
    await expect(api('/reports', { method: 'POST', body: '{}' })).rejects.toThrow('body.observed_at')
    expect(entries.map((entry) => entry.status)).toEqual([403, 422])
  })

  it('distingue un fallo de red/CORS de una respuesta HTTP', async () => {
    const { api, entries } = setup(vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api('/me')).rejects.toThrow('CORS_ORIGINS')
    expect(entries[0].status).toBeNull()
  })

  it('no envía una petición protegida sin sesión; /health permanece público', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{"status":"ok"}'))
    const { api } = setup(fetcher, async () => null)
    await expect(api('/me')).rejects.toBeInstanceOf(ApiError)
    expect(fetcher).not.toHaveBeenCalled()
    await api('/health', {}, false)
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).has('Authorization')).toBe(false)
  })
})
