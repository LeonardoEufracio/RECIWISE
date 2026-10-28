import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import App from './App'
import type { Coordinates, Report } from './types'

vi.mock('./MapView', () => ({ default: () => <div aria-label="Mapa Leaflet" /> }))
vi.mock('./LocationMap', () => ({ default: ({ onPick, editable }: { onPick: (point: Coordinates) => void; editable: boolean }) =>
  <button type="button" disabled={!editable} onClick={() => onPick({ latitude: -12.05, longitude: -75.2 })}>Seleccionar punto de prueba</button> }))
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const config = { apiUrl: 'http://api.test', supabaseUrl: 'https://project.supabase.co', publishableKey: 'sb_publishable_test' }
const report: Report = {
  id: 'report-1', citizen_id: 'citizen-1', description: 'Residuos cerca del parque', latitude: -12.05, longitude: -75.2,
  observed_at: '2026-01-01T15:00:00Z', created_at: '2026-01-01T15:01:00Z', waste_type: null, status: 'recibido',
}
const session = {
  access_token: 'test-jwt-no-real', user: { id: 'citizen-1', email: 'cuenta@example.test', user_metadata: { role: 'encargado_municipal' } },
} as unknown as Session

function authMock(initial: Session | null) {
  let current = initial
  let listener: (event: string, next: Session | null) => void = () => {}
  const auth = {
    getSession: vi.fn(async () => ({ data: { session: current }, error: null })),
    onAuthStateChange: vi.fn((callback: typeof listener) => {
      listener = callback
      callback('INITIAL_SESSION', current)
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    }),
    signInWithPassword: vi.fn(async (_credentials: { email: string; password: string }) => {
      current = session; listener('SIGNED_IN', current); return { error: null }
    }),
    signOut: vi.fn(async () => { current = null; listener('SIGNED_OUT', null); return { error: null } }),
  }
  return { auth, client: { auth } as unknown as SupabaseClient }
}

function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }) }

describe('Flujos de la interfaz con Auth y API simulados', () => {
  it('inicia sesión con una cuenta existente y usa el rol de /me, ignorando user_metadata', async () => {
    const getCurrentPosition = vi.fn()
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
    const { auth, client } = authMock(null)
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => String(url).endsWith('/me')
      ? json({ id: 'citizen-1', role: 'ciudadano' }) : json([]))
    vi.stubGlobal('fetch', fetcher)
    render(<App supabase={client} config={config} />)
    fireEvent.change(await screen.findByLabelText('Correo electrónico'), { target: { value: 'cuenta@example.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'password-solo-de-prueba' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await screen.findByRole('heading', { name: 'Mis reportes' })
    expect(auth.signInWithPassword).toHaveBeenCalledWith({ email: 'cuenta@example.test', password: 'password-solo-de-prueba' })
    expect(screen.queryByRole('heading', { name: 'Reportes municipales' })).toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(fetcher.mock.calls.some(([url]) => String(url).includes('/municipal/'))).toBe(false)
    expect(getCurrentPosition).not.toHaveBeenCalled()
  })

  it('registra un reporte, sube una foto con file y visualiza la URL firmada', async () => {
    const { client } = authMock(session)
    let created = false
    let uploaded = false
    const photo = { id: 'photo-1', report_id: report.id, signed_url: 'https://storage.test/photo.png?temporary=1' }
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url, init) => {
      const path = new URL(String(url)).pathname
      if (path === '/me') return json({ id: 'citizen-1', role: 'ciudadano' })
      if (path === '/reports' && init?.method === 'POST') { created = true; return json(report, 201) }
      if (path === '/reports/mine') return json(created ? [report] : [])
      if (path.endsWith('/photos') && init?.method === 'POST') { uploaded = true; return json({ ...photo, signed_url: null }, 201) }
      if (path.endsWith('/photos')) return json(uploaded ? [photo] : [])
      throw new Error(`Ruta inesperada: ${path}`)
    })
    vi.stubGlobal('fetch', fetcher)
    render(<App supabase={client} config={config} />)
    fireEvent.change(await screen.findByLabelText('Descripción'), { target: { value: report.description } })
    fireEvent.click(screen.getByRole('button', { name: 'Elegir en el mapa' }))
    fireEvent.click(screen.getByRole('button', { name: 'Seleccionar punto de prueba' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar ubicación' }))
    fireEvent.click(screen.getByRole('button', { name: 'Registrar reporte' }))
    await screen.findByText(/Reporte registrado/)
    const createCall = fetcher.mock.calls.find(([url, init]) => String(url).endsWith('/reports') && init?.method === 'POST')!
    const payload = JSON.parse(String(createCall[1]?.body))
    expect(payload.latitude).toBe(-12.05)
    expect(payload.observed_at).toMatch(/Z$/)
    expect(payload).not.toHaveProperty('role')
    const fileInput = await screen.findByLabelText(/Fotografía \(JPG/)
    await waitFor(() => expect((fileInput as HTMLInputElement).disabled).toBe(false))
    fireEvent.change(fileInput, { target: { files: [new File(['image'], 'prueba.png', { type: 'image/png' })] } })
    // jsdom no conecta el FileList simulado con la validación HTML nativa.
    fireEvent.submit(fileInput.closest('form')!)
    const image = await screen.findByAltText('Fotografía 1 del reporte')
    expect(image.getAttribute('src')).toBe(photo.signed_url)
    const uploadCall = fetcher.mock.calls.find(([url, init]) => String(url).endsWith('/photos') && init?.method === 'POST')!
    expect((uploadCall[1]?.body as FormData).get('file')).toBeInstanceOf(File)
    expect(new Headers(uploadCall[1]?.headers).has('Content-Type')).toBe(false)
    expect(screen.getAllByText('201').length).toBe(2)
    expect(screen.queryByText(session.access_token)).toBeNull()
  })

  it('consulta la ruta municipal y permite leer fotos sin ofrecer subidas ni registros', async () => {
    const { client } = authMock(session)
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => {
      if (String(url).endsWith('/me')) return json({ id: 'manager-1', role: 'encargado_municipal' })
      if (String(url).includes('/municipal/reports')) return json([report])
      return json([])
    })
    vi.stubGlobal('fetch', fetcher)
    render(<App supabase={client} config={config} />)
    await screen.findByText(report.description)
    expect(screen.queryByRole('button', { name: 'Registrar reporte' })).toBeNull()
    expect(fetcher.mock.calls.some(([url]) => String(url).includes('/reports/mine'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Ver fotografías' }))
    await screen.findByText('Este reporte no tiene fotografías.')
    expect(screen.queryByRole('button', { name: 'Subir fotografía' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await screen.findByRole('button', { name: 'Entrar' })
    expect(screen.queryByText(report.description)).toBeNull()
  })

  it('no habilita operaciones si /me rechaza la sesión y muestra el código HTTP', async () => {
    const { client } = authMock(session)
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(json({ detail: 'Usuario sin perfil habilitado' }, 403))
    vi.stubGlobal('fetch', fetcher)
    render(<App supabase={client} config={config} />)
    await screen.findByText('Usuario sin perfil habilitado')
    expect(screen.getByText('403')).toBeTruthy()
    expect(screen.queryByLabelText('Descripción')).toBeNull()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
