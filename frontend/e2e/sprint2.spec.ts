import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'
import { mkdir } from 'node:fs/promises'
import { initialDemo } from '../src/municipal/demo'
import type { VehicleInput, SiteInput, ShiftInput } from '../src/municipal/model'

const api = 'http://127.0.0.1:8000'
const artifact = path.resolve('..', '.test-artifacts', 'frontend-sprint2')
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
type Call = { path: string; method: string; url: string; body: unknown }
async function environment(page: Page, role = 'encargado_municipal') {
  const data = initialDemo()
  data.reports = data.reports.map((r) => ({ ...r, description: 'API controlada: ' + r.description.replace('Ejemplo: ', '') }))
  data.vehicles[0].label = 'Unidad API de prueba'
  const calls: Call[] = []; const unexpected: string[] = []; const errors: string[] = []
  const expiry = Math.floor(Date.now() / 1000) + 3600
  // UI-only session fixture; does not claim to verify a signed JWT or real Supabase Auth.
  const jwt = Buffer.from('{"alg":"HS256","typ":"JWT"}').toString('base64url') + '.' + Buffer.from(JSON.stringify({ sub: data.reports[0].citizen_id, exp: expiry })).toString('base64url') + '.ui-fixture'
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (url.origin === 'http://localhost:5173') return route.continue()
    unexpected.push(url.origin + url.pathname); return route.abort()
  })
  await page.route('https://frontend-test.supabase.co/**', (route) => route.fulfill({ json: {
    access_token: jwt, refresh_token: 'fictitious-refresh', expires_in: 3600, expires_at: expiry, token_type: 'bearer',
    user: { id: data.reports[0].citizen_id, aud: 'authenticated', role: 'authenticated', email: 'demo@example.test', app_metadata: {}, user_metadata: {}, created_at: data.reports[0].created_at },
  } }))
  await page.route('**/*.tile.openstreetmap.org/**', (route) => route.fulfill({ contentType: 'image/png', body: png }))
  await page.route('https://storage.test/**', (route) => route.fulfill({ contentType: 'image/png', body: png }))
  await page.route(api + '/**', async (route) => {
    const req = route.request(); const url = new URL(req.url()); const method = req.method()
    expect(req.headers().authorization).toBe('Bearer ' + jwt)
    calls.push({ path: url.pathname, method, url: url.toString(), body: req.postData() ? req.postDataJSON() : null })
    if (url.pathname === '/me') return route.fulfill({ json: { id: data.reports[0].citizen_id, role } })
    if (url.pathname === '/municipal/reports') return route.fulfill({ json: data.reports.filter((r) => !url.searchParams.get('status') || r.status === url.searchParams.get('status')).slice(Number(url.searchParams.get('offset') || 0), Number(url.searchParams.get('offset') || 0) + Number(url.searchParams.get('limit') || 50)) })
    if (url.pathname.endsWith('/photos')) return route.fulfill({ json: [{ id: 'test-photo', report_id: data.reports[0].id, content_type: 'image/png', size_bytes: 100, created_at: data.reports[0].created_at, signed_url: 'https://storage.test/private.png?fictitious=1' }] })
    if (url.pathname === '/reports/mine') return route.fulfill({ json: [] })
    if (url.pathname === '/municipal/route-proposals') return route.fulfill({ json: [] })
    if (url.pathname === '/municipal/vehicles') {
      if (method === 'POST') { const v = { ...(req.postDataJSON() as VehicleInput), id: 'd1000000-0000-4000-8000-000000000001' }; data.vehicles.push(v); return route.fulfill({ status: 201, json: v }) }
      return route.fulfill({ json: data.vehicles })
    }
    if (url.pathname.endsWith('/availability')) {
      const v = data.vehicles.find((v) => url.pathname.includes(v.id))!; v.available = req.postDataJSON().available
      return route.fulfill({ json: v })
    }
    if (url.pathname === '/municipal/drivers') return route.fulfill({ json: [{ id: data.shifts[0].driver_id, role: 'chofer' }] })
    if (url.pathname === '/municipal/sites') {
      if (method === 'POST') { const s = { ...(req.postDataJSON() as SiteInput), id: 'd1000000-0000-4000-8000-000000000002', active: true }; data.sites.push(s); return route.fulfill({ status: 201, json: s }) }
      return route.fulfill({ json: data.sites })
    }
    if (url.pathname === '/municipal/shifts') {
      if (method === 'POST') { const s = { ...(req.postDataJSON() as ShiftInput), id: 'd1000000-0000-4000-8000-000000000003', status: 'programado', created_by: 'test-manager' }; data.shifts.push(s); return route.fulfill({ status: 201, json: s }) }
      return route.fulfill({ json: data.shifts })
    }
    unexpected.push(url.pathname); return route.fulfill({ status: 500, json: { detail: 'Endpoint inesperado en la prueba' } })
  })
  return { data, calls, unexpected, errors }
}
async function login(page: Page) {
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill('demo@example.test')
  await page.getByLabel('Contraseña', { exact: true }).fill('ficticia-solo-pruebas')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
}
async function navigate(page: Page, name: string) {
  const target = page.getByRole('button', { name, exact: true, includeHidden: true })
  await target.waitFor({ state: 'attached' })
  if (await target.isHidden()) await page.getByRole('button', { name: 'Abrir navegación', exact: true }).click()
  await page.getByRole('button', { name, exact: true }).click()
}
async function demonstration(page: Page) {
  await page.getByRole('button', { name: 'Explorar demostración', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'Confirmar cambio de modo', exact: true }).click()
  await expect(page.getByText('DATOS SIMULADOS — DEMOSTRACIÓN', { exact: true })).toBeVisible()
}
async function screenshot(page: Page, name: string) {
  await mkdir(artifact, { recursive: true })
  await page.screenshot({ path: path.join(artifact, name + '.png'), fullPage: true })
}

test('Sprint 2: dashboard, reportes, búsqueda local, Leaflet y fotos con API controlada', async ({ page }) => {
  const env = await environment(page); await login(page)
  await expect(page.getByText('Total de reportes consultados', { exact: true })).toBeVisible()
  await expect(page.locator('.stat-card').first().locator('strong')).toHaveText('4')
  await expect(page.getByText('DATOS SIMULADOS — DEMOSTRACIÓN', { exact: true })).toHaveCount(0)
  await screenshot(page, '01-dashboard-real-api-simulada')
  await navigate(page, 'Reportes ciudadanos')
  await expect(page.locator('.map .leaflet-interactive')).toHaveCount(4)
  await page.getByLabel('Buscar por descripción en esta página').fill('cartón')
  await expect(page.locator('.report-list > article')).toHaveCount(1)
  await expect(page.locator('.map .leaflet-interactive')).toHaveCount(1)
  await page.getByRole('button', { name: 'Centrar en el mapa', exact: true }).click()
  await expect(page.locator('.selected-report')).toHaveCount(1)
  await page.locator('.map .leaflet-interactive').click()
  await expect(page.locator('.leaflet-popup-content')).toContainText('Observado:')
  await page.getByRole('button', { name: 'Ver detalle y fotografías', exact: true }).click()
  await expect(page.getByAltText('Fotografía 1 del reporte')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Subir fotografía', exact: true })).toHaveCount(0)
  await screenshot(page, '02-reportes-mapa')
  await page.getByLabel(/Filtrar por estado/).fill('inexistente')
  await page.getByRole('button', { name: 'Aplicar filtro', exact: true }).click()
  await expect(page.getByText('No hay reportes en esta página.', { exact: true })).toBeVisible()
  expect(env.calls.some((c) => new URL(c.url).searchParams.has('q'))).toBe(false)
  expect(env.unexpected).toEqual([]); expect(env.errors).toEqual([])
})

test('Sprint 2: eventos, decisiones confirmadas e historial aislado de FastAPI', async ({ page }) => {
  const env = await environment(page); await login(page)
  await expect(page.getByText(/API controlada:/).first()).toBeVisible()
  await demonstration(page)
  const before = env.calls.length
  await expect(page.getByText(/API controlada:/)).toHaveCount(0)
  await navigate(page, 'Eventos o puntos de atención')
  await expect(page.locator('.event-card')).toHaveCount(3)
  await expect(page.locator('.event-marker')).toHaveCount(3)
  await page.getByRole('button', { name: /Abrir evento/ }).first().click()
  await expect(page.getByRole('dialog')).toContainText('Reportes asociados (1)')
  await page.keyboard.press('Escape')
  await navigate(page, 'Revisión de agrupaciones')
  await expect(page.locator('.suggestion-tag').getByText('Candidato a agrupar', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirmar agrupación', exact: true }).last()).toBeDisabled()
  await page.getByRole('button', { name: 'Confirmar agrupación', exact: true }).first().click()
  await page.getByLabel('Motivo de la decisión').fill('Comparación revisada en simulación')
  await page.getByRole('button', { name: 'Confirmar decisión simulada', exact: true }).dblclick()
  await expect(page.locator('.timeline > li')).toHaveCount(1)
  await screenshot(page, '03-agrupaciones')
  await navigate(page, 'Eventos o puntos de atención')
  await expect(page.getByText('2 reportes asociados', { exact: true })).toBeVisible()
  await navigate(page, 'Priorización')
  await expect(page.getByRole('option', { name: 'Prioridad entregada por el servicio' })).toHaveJSProperty('disabled', true)
  await expect(page.getByText('Sin cálculo', { exact: true })).toHaveCount(2)
  expect(env.calls.length).toBe(before)
  await page.getByRole('button', { name: 'Volver al modo real', exact: true }).click()
  await page.getByRole('button', { name: 'Confirmar cambio de modo', exact: true }).click()
  await expect(page.getByText(/API controlada:/).first()).toBeVisible()
  await expect(page.getByText('DATOS SIMULADOS — DEMOSTRACIÓN', { exact: true })).toHaveCount(0)
  expect(env.unexpected).toEqual([]); expect(env.errors).toEqual([])
})

test('Sprint 2: turno, vehículo, propuesta GeoJSON y aprobación exclusivamente simulada', async ({ page }) => {
  const env = await environment(page); await login(page); await demonstration(page)
  const before = env.calls.length
  await navigate(page, 'Planificación de rutas')
  await page.getByRole('combobox', { name: 'Jornada o turno', exact: true }).selectOption({ index: 1 })
  await expect(page.getByRole('option', { name: 'Unidad demostrativa 02 — No disponible', exact: true })).toHaveJSProperty('disabled', true)
  await expect(page.getByText(/Capacidad registrada: No especificada/)).toBeVisible()
  await page.getByRole('button', { name: 'Generar propuesta simulada', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Selecciona eventos')
  const events = page.locator('.choice-list input[type=checkbox]')
  await events.nth(0).check(); await events.nth(1).check(); await expect(events.nth(2)).toBeDisabled()
  await page.getByRole('button', { name: 'Generar propuesta simulada', exact: true }).click()
  await page.getByRole('button', { name: 'Confirmar simulación', exact: true }).click()
  await expect(page.locator('.route-map .route-stop')).toHaveCount(2)
  await expect(page.locator('.route-map path.leaflet-interactive')).toHaveCount(1)
  await expect(page.getByText('PROPUESTA SIMULADA — NO OPERATIVA.', { exact: false })).toBeVisible()
  await screenshot(page, '04-propuesta-ruta-simulada')
  await page.getByRole('button', { name: 'Aprobar solo en demostración', exact: true }).click()
  await page.getByRole('button', { name: 'Confirmar simulación', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Aprobar solo en demostración', exact: true })).toBeDisabled()
  expect(env.calls.length).toBe(before)
  expect(env.unexpected).toEqual([]); expect(env.errors).toEqual([])
})

test('Sprint 2: recursos reales, altas confirmadas y contratos POST sin campos inventados', async ({ page }) => {
  const env = await environment(page); await login(page)
  await navigate(page, 'Recursos operativos')
  await expect(page.getByText('Capacidad: No especificada', { exact: true })).toBeVisible()
  await page.getByText('Registrar vehículo', { exact: true }).click()
  await page.getByLabel('Nombre de la unidad', { exact: true }).fill('Unidad nueva de prueba')
  await page.getByRole('button', { name: 'Revisar alta de vehículo', exact: true }).click()
  expect(env.calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  await page.getByRole('button', { name: 'Confirmar operación', exact: true }).click()
  await expect(page.getByText('Unidad nueva de prueba', { exact: true })).toBeVisible()
  expect(env.calls.find((c) => c.method === 'POST')?.body).toMatchObject({ capacity_kg: null, plate: null, available: false })
  await page.getByRole('button', { name: 'Sitios', exact: true }).click()
  await page.getByText('Registrar punto de salida o descarga', { exact: true }).click()
  await page.getByLabel('Nombre del sitio', { exact: true }).fill('Punto ficticio nuevo')
  await page.getByRole('button', { name: 'Elegir en el mapa', exact: true }).click()
  await page.locator('.location-map').click({ position: { x: 160, y: 160 } })
  await page.getByRole('button', { name: 'Confirmar ubicación', exact: true }).click()
  await page.getByRole('button', { name: 'Revisar alta de sitio', exact: true }).click()
  await page.getByRole('button', { name: 'Confirmar operación', exact: true }).click()
  await expect(page.getByText('Punto ficticio nuevo', { exact: true })).toBeVisible()
  const site = env.calls.find((c) => c.path === '/municipal/sites' && c.method === 'POST')!.body as SiteInput
  expect(typeof site.latitude).toBe('number'); expect(typeof site.longitude).toBe('number'); expect(site).not.toHaveProperty('confirmed')
  await page.getByRole('button', { name: 'Turnos', exact: true }).click()
  await page.getByText('Crear jornada o turno', { exact: true }).click()
  await page.getByRole('combobox', { name: 'Vehículo para el nuevo turno', exact: true }).selectOption(env.data.vehicles[0].id)
  await page.getByRole('combobox', { name: /Chofer autorizado/ }).selectOption(env.data.shifts[0].driver_id)
  await page.getByRole('combobox', { name: 'Salida del nuevo turno', exact: true }).selectOption(env.data.sites[0].id)
  await page.getByRole('combobox', { name: 'Descarga del nuevo turno', exact: true }).selectOption(env.data.sites[1].id)
  await page.getByLabel('Inicio del turno', { exact: true }).fill('2026-11-06T08:00')
  await page.getByLabel('Fin del turno', { exact: true }).fill('2026-11-06T12:00')
  await page.getByRole('button', { name: 'Revisar nuevo turno', exact: true }).click()
  await page.getByRole('button', { name: 'Confirmar operación', exact: true }).click()
  await expect(page.getByText('Recurso guardado correctamente.', { exact: true })).toBeVisible()
  const shift = env.calls.find((c) => c.path === '/municipal/shifts' && c.method === 'POST')!.body as ShiftInput
  expect(shift.starts_at).toMatch(/Z$/); expect(Date.parse(shift.ends_at)).toBeGreaterThan(Date.parse(shift.starts_at))
  expect(Object.keys(shift).sort()).toEqual(['vehicle_id', 'driver_id', 'departure_site_id', 'disposal_site_id', 'starts_at', 'ends_at'].sort())
  await navigate(page, 'Planificación de rutas')
  await expect(page.getByRole('button', { name: 'Solicitar propuesta (pendiente)', exact: true })).toBeDisabled()
  expect(env.calls.some((c) => c.path === '/municipal/route-proposals' && c.method === 'GET')).toBe(true)
  expect(env.calls.some((c) => c.path === '/municipal/route-proposals' && c.method !== 'GET')).toBe(false)
  expect(env.unexpected).toEqual([]); expect(env.errors).toEqual([])
})

test('Sprint 2: conflicto 409 visible dentro de la confirmación sin reenviar la operación', async ({ page }) => {
  const env = await environment(page); let writes = 0
  await page.route(api + '/municipal/vehicles/*/availability', (route) => {
    writes += 1; return route.fulfill({ status: 409, json: { detail: 'Conflicto HTTP 409 de prueba' } })
  })
  await login(page); await navigate(page, 'Recursos operativos')
  await page.getByRole('button', { name: 'Marcar no disponible', exact: true }).click()
  await page.getByRole('button', { name: 'Confirmar operación', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('alert')).toHaveText('Conflicto HTTP 409 de prueba')
  expect(writes).toBe(1)
  await expect(page.getByText('Recurso guardado correctamente.', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click()
  expect(env.errors).toEqual([])
})

for (const status of [403, 503]) test('Sprint 2: error HTTP ' + status + ' y recuperación sin ocultar el fallo', async ({ page }) => {
  const env = await environment(page); let fail = true
  await page.route(api + '/municipal/reports**', (route) => fail ? route.fulfill({ status, json: { detail: 'Error controlado HTTP ' + status } }) : route.fulfill({ json: [] }))
  await login(page)
  await expect(page.getByRole('alert')).toContainText('Error controlado HTTP ' + status)
  await expect(page.locator('.stat-card')).toHaveCount(0)
  fail = false
  await page.getByRole('button', { name: 'Volver a intentar', exact: true }).click()
  await expect(page.getByText('Aún no hay reportes', { exact: true })).toBeVisible()
  expect(env.unexpected).toEqual([]); expect(env.errors).toEqual([])
})

test('Sprint 2: un 401 retira las funciones municipales y solicita nuevo login', async ({ page }) => {
  const env = await environment(page)
  await page.route(api + '/municipal/reports**', (route) => route.fulfill({ status: 401, json: { detail: 'Sesión de prueba vencida' } }))
  await login(page)
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Navegación municipal' })).toHaveCount(0)
  await expect(page.getByRole('alert')).toContainText('La sesión no fue aceptada')
  expect(env.errors).toEqual([])
})

for (const width of [375, 390, 768]) test('Sprint 2: navegación adaptable sin desborde a ' + width + ' px', async ({ page }) => {
  await page.setViewportSize({ width, height: 900 })
  const env = await environment(page); await login(page)
  await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible()
  await demonstration(page)
  await navigate(page, 'Revisión de agrupaciones')
  await expect(page.locator('.suggestion')).toHaveCount(3)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await screenshot(page, '05-agrupaciones-' + width)
  await navigate(page, 'Planificación de rutas')
  await page.getByRole('combobox', { name: 'Jornada o turno', exact: true }).selectOption({ index: 1 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(env.errors).toEqual([])
})
