import { expect, test, type Page } from '@playwright/test'

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
const citizenId = '00000000-0000-4000-8000-000000000001'
const reportId = '00000000-0000-4000-8000-000000000002'
const report = {
  id: reportId, citizen_id: citizenId, description: 'Reporte sintético del navegador',
  latitude: -12.05, longitude: -75.2, status: 'recibido', waste_type: null,
  observed_at: '2026-01-01T15:00:00Z', created_at: '2026-01-01T15:01:00Z',
}

async function mockAuth(page: Page) {
  const expires = Math.floor(Date.now() / 1000) + 3600
  const jwt = `${Buffer.from('{"alg":"HS256","typ":"JWT"}').toString('base64url')}.${Buffer.from(JSON.stringify({ sub: citizenId, exp: expires })).toString('base64url')}.test-signature`
  await page.route('https://frontend-test.supabase.co/**', (route) => route.fulfill({
    json: { access_token: jwt, refresh_token: 'test-refresh', token_type: 'bearer', expires_in: 3600, expires_at: expires,
      user: { id: citizenId, aud: 'authenticated', role: 'authenticated', email: 'test@example.test', app_metadata: {}, user_metadata: {}, created_at: report.created_at } },
  }))
  await page.route('**/*.tile.openstreetmap.org/**', (route) => route.fulfill({ contentType: 'image/png', body: png }))
}

async function login(page: Page) {
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill('test@example.test')
  await page.getByLabel('Contraseña', { exact: true }).fill('password-solo-de-prueba')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
}

test('el navegador se comunica con FastAPI real y respeta CORS', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Comprobar /health' }).click()
  await expect(page.getByText(/API: ok/)).toBeVisible()
  await expect(page.getByRole('cell', { name: '200', exact: true })).toBeVisible()
  const status = await page.evaluate(async () => {
    const response = await fetch('http://127.0.0.1:8000/me')
    return response.status
  })
  expect(status).toBe(401)
})

test('ciudadano: Leaflet, registro, fotografía y sesión con servicios simulados', async ({ page }) => {
  await mockAuth(page)
  let created = false
  let uploaded = false
  await page.route('http://127.0.0.1:8000/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/me') return route.fulfill({ json: { id: citizenId, role: 'ciudadano' } })
    if (path === '/reports' && request.method() === 'POST') {
      const body = request.postDataJSON()
      expect(body.description).toBe(report.description)
      expect(typeof body.latitude).toBe('number')
      expect(body.observed_at).toMatch(/Z$/)
      expect(body).not.toHaveProperty('role')
      expect(request.headers().authorization).toMatch(/^Bearer /)
      created = true
      return route.fulfill({ status: 201, json: { ...report, ...body } })
    }
    if (path === '/reports/mine') return route.fulfill({ json: created ? [report] : [] })
    if (path.endsWith('/photos')) {
      const photo = { id: 'photo-1', report_id: reportId, content_type: 'image/png', size_bytes: png.length, created_at: report.created_at, signed_url: 'https://storage.test/test.png?temporary=1' }
      if (request.method() === 'POST') {
        expect(request.headers()['content-type']).toContain('multipart/form-data; boundary=')
        expect(request.postDataBuffer()?.toString()).toContain('name="file"')
        uploaded = true
        return route.fulfill({ status: 201, json: { ...photo, signed_url: null } })
      }
      return route.fulfill({ json: uploaded ? [photo] : [] })
    }
    throw new Error(`Ruta inesperada: ${path}`)
  })
  await page.route('https://storage.test/**', (route) => route.fulfill({ contentType: 'image/png', body: png }))
  await login(page)
  await page.getByLabel('Descripción', { exact: true }).fill(report.description)
  await page.locator('.map').click({ position: { x: 140, y: 140 } })
  await expect(page.getByLabel('Latitud', { exact: true })).not.toHaveValue('')
  await expect(page.locator('.map .leaflet-interactive')).toHaveCount(1)
  await page.getByRole('button', { name: 'Registrar reporte', exact: true }).click()
  await expect(page.getByText(/Reporte registrado/)).toBeVisible()
  const input = page.getByLabel(/Fotografía \(JPG/)
  await expect(input).toBeEnabled()
  await input.setInputFiles({ name: 'prueba.png', mimeType: 'image/png', buffer: png })
  await page.getByRole('button', { name: 'Subir fotografía', exact: true }).click()
  await expect(page.getByAltText('Fotografía 1 del reporte')).toBeVisible()
  await expect(page.getByRole('cell', { name: '201', exact: true })).toHaveCount(2)
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
  await expect(page.getByText(report.description, { exact: true })).toHaveCount(0)
})

test('encargado: puntos Leaflet, filtro y vista móvil con servicios simulados', async ({ page }) => {
  await mockAuth(page)
  await page.route('http://127.0.0.1:8000/**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/me') return route.fulfill({ json: { id: citizenId, role: 'encargado_municipal' } })
    if (url.pathname === '/municipal/reports') return route.fulfill({ json: url.searchParams.get('status') === 'sin-resultados' ? [] : [report] })
    throw new Error(`Ruta inesperada: ${url.pathname}`)
  })
  await login(page)
  await expect(page.getByRole('heading', { name: 'Reportes municipales' })).toBeVisible()
  await expect(page.locator('.map .leaflet-interactive')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Registrar reporte', exact: true })).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByLabel(/Filtrar por estado/).fill('sin-resultados')
  await page.getByRole('button', { name: 'Aplicar filtro', exact: true }).click()
  await expect(page.getByText('No hay reportes en esta página.')).toBeVisible()
  await expect(page.locator('.map .leaflet-interactive')).toHaveCount(0)
})
