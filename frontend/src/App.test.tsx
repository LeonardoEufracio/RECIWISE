import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  it.each(['ciudadano', 'chofer'])('no habilita navegación ni demostración municipal para %s aunque se active el flag', async (role) => {
    const { client } = authMock(session)
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (url) => String(url).endsWith('/me') ? json({ id: 'test-user', role }) : json([]))
    vi.stubGlobal('fetch', fetcher)
    render(<App supabase={client} config={config} demoAvailable />)
    await screen.findByText(role, { selector: 'strong' })
    expect(screen.queryByRole('navigation', { name: 'Navegación municipal' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Explorar demostración' })).toBeNull()
    expect(fetcher.mock.calls.some(([url]) => String(url).includes('/municipal/'))).toBe(false)
  })
  it('retira el espacio municipal cuando FastAPI devuelve 401 y permite volver a iniciar sesión', async () => {
    const { client } = authMock(session)
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async (url) => String(url).endsWith('/me')
      ? json({ id: 'manager', role: 'encargado_municipal' }) : json({ detail: 'Token vencido' }, 401)))
    render(<App supabase={client} config={config} />)
    await screen.findByRole('button', { name: 'Entrar' })
    expect(screen.queryByRole('navigation', { name: 'Navegación municipal' })).toBeNull()
    expect(screen.getByText(/La sesión no fue aceptada/)).toBeTruthy()
    expect(screen.getByText('401')).toBeTruthy()
  })
  it('por defecto no ofrece demostración al encargado y conserva un resumen real', async () => {
    const { client } = authMock(session)
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async (url) => String(url).endsWith('/me')
      ? json({ id: 'manager', role: 'encargado_municipal' }) : json([report])))
    render(<App supabase={client} config={config} />)
    await screen.findByText(report.description)
    expect(screen.getByRole('button', { name: 'Dashboard' }).getAttribute('aria-current')).toBe('page')
    expect(screen.queryByRole('button', { name: 'Explorar demostración' })).toBeNull()
  })
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

  it('dos reportes consecutivos conservan fotos distintas y el reintento no cambia su destino', async () => {
    const { client } = authMock(session)
    const reports: Report[] = []
    const photos = new Map<string, { id: string; report_id: string; signed_url: string }[]>()
    const posts: { reportId: string; name: string }[] = []
    let failed = false
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async (url, init) => {
      const path = new URL(String(url)).pathname
      if (path === '/me') return json({ id: 'citizen-1', role: 'ciudadano' })
      if (path === '/reports' && init?.method === 'POST') {
        const value = { ...report, ...JSON.parse(String(init.body)), id: 'consecutive-' + (reports.length + 1) }
        reports.push(value); photos.set(value.id, [])
        return json(value, 201)
      }
      if (path === '/reports/mine') return json([...reports].reverse())
      const match = path.match(/^\/reports\/([^/]+)\/photos$/)
      if (!match || !photos.has(match[1])) throw new Error('Unexpected test path')
      const id = match[1]
      if (init?.method === 'POST') {
        const file = (init.body as FormData).get('file') as File
        posts.push({ reportId: id, name: file.name })
        if (id === 'consecutive-2' && !failed) { failed = true; return json({ detail: 'Fallo ficticio de Storage' }, 502) }
        const result = { id: 'photo-' + id, report_id: id, signed_url: 'https://storage.invalid/' + file.name }
        photos.get(id)!.push(result)
        return json(result, 201)
      }
      return json(photos.get(id))
    }))
    render(<App supabase={client} config={config} />)
    async function create(number: number) {
      fireEvent.change(await screen.findByLabelText('Descripción'), { target: { value: 'Reporte consecutivo ' + number } })
      fireEvent.click(screen.getByRole('button', { name: 'Elegir en el mapa' }))
      fireEvent.click(screen.getByRole('button', { name: 'Seleccionar punto de prueba' }))
      fireEvent.click(screen.getByRole('button', { name: 'Confirmar ubicación' }))
      fireEvent.click(screen.getByRole('button', { name: 'Registrar reporte' }))
      const id = 'consecutive-' + number
      const card = (await screen.findByText('ID: ' + id)).closest('article')!
      await within(card).findByText('Este reporte no tiene fotografías.')
      expect(within(card).getByText(id, { selector: 'span' })).toBeTruthy()
      return card
    }
    async function upload(card: HTMLElement, name: string) {
      const input = within(card).getByLabelText(/Fotografía \(JPG/)
      await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false))
      fireEvent.change(input, { target: { files: [new File([name], name, { type: 'image/png' })] } })
      fireEvent.submit(input.closest('form')!)
    }
    const first = await create(1)
    await upload(first, 'primera.png')
    expect((await within(first).findByAltText('Fotografía 1 del reporte')).getAttribute('src')).toContain('/primera.png')
    const second = await create(2)
    await upload(second, 'segunda.png')
    await within(second).findByText('Fallo ficticio de Storage')
    expect(photos.get('consecutive-1')).toHaveLength(1)
    expect(photos.get('consecutive-2')).toHaveLength(0)
    expect(posts).toHaveLength(2) // Never automatically repeat a failed write.
    fireEvent.click(within(second).getByRole('button', { name: 'Renovar enlaces' }))
    await within(second).findByText('Fotografías (0/3)')
    await upload(second, 'segunda.png')
    expect((await within(second).findByAltText('Fotografía 1 del reporte')).getAttribute('src')).toContain('/segunda.png')
    expect(posts).toEqual([{ reportId: 'consecutive-1', name: 'primera.png' },
      { reportId: 'consecutive-2', name: 'segunda.png' }, { reportId: 'consecutive-2', name: 'segunda.png' }])
    expect(reports).toHaveLength(2)
    const firstAgain = screen.getByText('ID: consecutive-1').closest('article')!
    fireEvent.click(within(firstAgain).getByRole('button', { name: 'Ver fotografías' }))
    expect((await within(firstAgain).findByAltText('Fotografía 1 del reporte')).getAttribute('src')).toContain('/primera.png')
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
    fireEvent.click(screen.getByRole('button', { name: 'Reportes ciudadanos' }))
    await screen.findByRole('heading', { name: 'Reportes municipales' })
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
