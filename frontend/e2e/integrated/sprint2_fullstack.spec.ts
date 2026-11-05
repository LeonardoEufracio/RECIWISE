import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { shortId } from '../../src/format'

const api = process.env.RECIWISE_INTEGRATED_API_URL!
const services = process.env.RECIWISE_INTEGRATED_SERVICES_URL!
const ui = process.env.RECIWISE_INTEGRATED_UI_URL!
const artifact = process.env.RECIWISE_INTEGRATED_ARTIFACT!
const password = process.env.RECIWISE_INTEGRATED_PASSWORD!
const profiles = JSON.parse(process.env.RECIWISE_ISOLATED_PROFILES || '{}')
const fixtureId = process.env.RECIWISE_EXECUTION_FIXTURE_ID!
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
type Headers = { Authorization: string }
let errors: string[] = []
let external: string[] = []
let http: { method: string; path: string; status: number }[] = []
test.beforeEach(async ({ page, context }) => {
  errors = []; external = []; http = []
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(url.hostname)) return route.fulfill({ contentType: 'image/png', body: png })
    if ([api, services, ui].includes(url.origin)) return route.continue()
    external.push(url.origin); return route.abort('blockedbyclient')
  })
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('response', (r) => { if (new URL(r.url()).origin === api) http.push({ method: r.request().method(), path: new URL(r.url()).pathname, status: r.status() }) })
})
test.afterEach(async ({}, info) => {
  fs.writeFileSync(path.join(artifact, 'fullstack-' + info.testId.replace(/[^a-z0-9]/gi, '_') + '.json'), JSON.stringify({
    title: info.title, errors, external, http, services: { react: 'real Chrome', leaflet: 'real, tiles simulated', fastapi: 'real HTTP, production auth and schema guard', postgres: 'real disposable 001+002+003', auth_storage: 'local HTTP simulators', approval: 'fictitious DB fixture, not real D3 verification' },
  }, null, 2))
  expect(errors).toEqual([]); expect(external).toEqual([])
})
async function login(page: Page, name: string) {
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill(name + '@example.test')
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  const response = page.waitForResponse((r) => r.url().startsWith(services + '/auth/v1/token') && r.status() === 200)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  const session = await (await response).json()
  expect(JSON.parse(Buffer.from(session.access_token.split('.')[0], 'base64url').toString()).alg).toBe('ES256')
  await expect(page.getByRole('button', { name: 'Consultar /me', exact: true })).toBeEnabled()
  return { Authorization: 'Bearer ' + session.access_token }
}
async function logout(page: Page) {
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
}
async function navigate(page: Page, name: string) {
  const button = page.getByRole('button', { name, exact: true, includeHidden: true })
  if (await button.isHidden()) await page.getByRole('button', { name: 'Abrir navegación', exact: true }).click()
  await page.getByRole('button', { name, exact: true }).click()
}
async function post(request: APIRequestContext, headers: Headers, route: string, data: unknown) {
  const response = await request.post(api + route, { headers, data })
  expect(response.status()).toBe(201)
  return response.json()
}
async function point(page: Page) {
  await page.getByRole('button', { name: 'Elegir en el mapa', exact: true }).click()
  await page.locator('.location-map').click({ position: { x: 155, y: 150 } })
  await page.getByRole('button', { name: 'Confirmar ubicación', exact: true }).click()
}

test('Fullstack A/B: recursos, selector de chofer, turno y evento manual desde React', async ({ page, request }) => {
  const citizen = await login(page, 'citizen')
  const report = await post(request, citizen, '/reports', { description: 'AB reporte ficticio para evento manual', latitude: -12.05, longitude: -75.22, observed_at: new Date().toISOString() })
  expect((await request.get(api + '/municipal/drivers', { headers: citizen })).status()).toBe(403)
  await logout(page)
  const manager = await login(page, 'manager')
  await navigate(page, 'Recursos operativos')
  await page.getByText('Registrar vehículo', { exact: true }).click()
  await page.getByLabel('Nombre de la unidad', { exact: true }).fill('AB Unidad ficticia nueva')
  await page.getByLabel('Disponible para programar', { exact: true }).check()
  await page.getByRole('button', { name: 'Revisar alta de vehículo', exact: true }).click()
  const vehicleResponse = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/vehicles' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Confirmar operación', exact: true }).click()
  const vehicle = await (await vehicleResponse).json()
  await expect(page.getByRole('heading', { name: 'AB Unidad ficticia nueva', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Sitios', exact: true }).click()
  await page.getByText('Registrar punto de salida o descarga', { exact: true }).click()
  await page.getByLabel('Nombre del sitio', { exact: true }).fill('AB Punto de prueba')
  await point(page)
  await page.getByRole('button', { name: 'Revisar alta de sitio', exact: true }).click()
  const siteResponse = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/sites' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Confirmar operación', exact: true }).click()
  const site = await (await siteResponse).json()
  await page.getByRole('button', { name: 'Editar sitio AB Punto de prueba', exact: true }).click()
  await page.getByLabel('Nombre del punto', { exact: true }).fill('AB Salida corregida')
  await page.getByRole('button', { name: 'Revisar cambios del punto', exact: true }).click()
  const edited = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/sites/' + site.id && r.request().method() === 'PATCH')
  await page.getByRole('button', { name: 'Confirmar edición', exact: true }).click()
  expect((await edited).status()).toBe(200)
  await expect(page.getByRole('heading', { name: 'AB Salida corregida', exact: true })).toBeVisible()
  const disposal = await post(request, manager, '/municipal/sites', { name: 'AB Descarga ficticia', site_type: 'descarga', latitude: -12.07, longitude: -75.24 })
  await page.getByRole('button', { name: 'Actualizar recursos', exact: true }).click()
  await page.getByRole('button', { name: 'Turnos', exact: true }).click()
  await page.getByText('Crear jornada o turno', { exact: true }).click()
  await page.getByRole('combobox', { name: 'Vehículo para el nuevo turno', exact: true }).selectOption(vehicle.id)
  await page.getByRole('combobox', { name: /Chofer autorizado/ }).selectOption(profiles.driver2)
  await page.getByRole('combobox', { name: 'Salida del nuevo turno', exact: true }).selectOption(site.id)
  await page.getByRole('combobox', { name: 'Descarga del nuevo turno', exact: true }).selectOption(disposal.id)
  await page.getByLabel('Inicio del turno', { exact: true }).fill('2031-11-19T08:00')
  await page.getByLabel('Fin del turno', { exact: true }).fill('2031-11-19T10:00')
  await page.getByRole('button', { name: 'Revisar nuevo turno', exact: true }).click()
  const shiftResponse = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/shifts' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Confirmar operación', exact: true }).click()
  expect((await shiftResponse).status()).toBe(201)
  await expect(page.getByText('Recurso guardado correctamente.', { exact: true })).toBeVisible()
  await navigate(page, 'Eventos o puntos de atención')
  await page.getByRole('button', { name: 'Crear evento manual', exact: true }).click()
  await page.getByLabel('Intervención manual (opcional)', { exact: true }).fill('AB Intervención manual')
  await page.getByLabel(/AB reporte ficticio para evento manual/).check()
  await point(page)
  await page.getByRole('button', { name: 'Revisar evento manual', exact: true }).click()
  const eventResponse = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/events' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Confirmar creación de evento', exact: true }).click()
  const response = await eventResponse
  expect(response.status()).toBe(201)
  const event = await response.json()
  expect(event.report_ids).toEqual([report.id])
  expect(typeof response.request().postDataJSON().latitude).toBe('number')
  const detail = page.getByRole('dialog', { name: 'Detalle de evento ' + shortId(event.id) })
  await expect(detail.getByText('AB reporte ficticio para evento manual', { exact: true })).toBeVisible()
  await expect(detail.locator('.event-marker')).toHaveCount(1)
  const mine = await request.get(api + '/reports/mine', { headers: citizen })
  expect((await mine.json()).find((r: { id: string }) => r.id === report.id).status).toBe('recibido')
  await page.screenshot({ path: path.join(artifact, 'fullstack-manual-event.png'), fullPage: true })
})

test('Fullstack C: aprobación bloqueada, conflicto de revisión y cancelación auditada', async ({ page, request }) => {
  const manager = await login(page, 'manager')
  const vehicle = await post(request, manager, '/municipal/vehicles', { label: 'C Unidad ficticia', vehicle_type: 'otro', available: true })
  const departure = await post(request, manager, '/municipal/sites', { name: 'C Salida', site_type: 'salida', latitude: -12.05, longitude: -75.22 })
  const disposal = await post(request, manager, '/municipal/sites', { name: 'C Descarga', site_type: 'descarga', latitude: -12.06, longitude: -75.23 })
  const shift = await post(request, manager, '/municipal/shifts', { vehicle_id: vehicle.id, driver_id: profiles.driver2, departure_site_id: departure.id, disposal_site_id: disposal.id, starts_at: '2032-11-19T13:00:00Z', ends_at: '2032-11-19T18:00:00Z' })
  const event = await post(request, manager, '/municipal/events', { latitude: -12.05, longitude: -75.22 })
  const a = await post(request, manager, '/municipal/route-proposals', { proposal_id: randomUUID(), shift_id: shift.id, event_ids: [event.id] })
  const b = await post(request, manager, '/municipal/route-proposals', { proposal_id: randomUUID(), shift_id: shift.id, event_ids: [event.id] })
  const c = await post(request, manager, '/municipal/route-proposals', { proposal_id: randomUUID(), shift_id: shift.id, event_ids: [event.id] })
  const decision = { operation_id: randomUUID(), expected_status: 'propuesta', expected_revision: null, decision: 'approve', notes: 'Intento de aprobación no verificada' }
  expect((await request.post(api + '/municipal/routes/' + a.id + '/decisions', { headers: manager, data: decision })).status()).toBe(409)
  await navigate(page, 'Planificación de rutas')
  await page.getByRole('button', { name: 'Decisiones e historial', exact: true }).click()
  await page.getByRole('button', { name: 'Revisar ruta ' + shortId(a.id), exact: true }).click()
  await expect(page.getByRole('button', { name: 'Aprobar y asignar (proveedor pendiente)', exact: true })).toBeDisabled()
  await page.getByLabel('Motivo de la decisión', { exact: true }).fill('Revisión concurrente de prueba')
  await page.getByRole('button', { name: 'Revisar decisión de ruta', exact: true }).click()
  const concurrent = await request.post(api + '/municipal/routes/' + a.id + '/decisions', { headers: manager, data: { ...decision, operation_id: randomUUID(), decision: 'cancel' } })
  expect(concurrent.status()).toBe(200)
  const conflict = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/routes/' + a.id + '/decisions')
  await page.getByRole('button', { name: 'Confirmar operación de ruta', exact: true }).click()
  expect((await conflict).status()).toBe(409)
  await page.getByRole('button', { name: 'Descartar y actualizar ruta', exact: true }).click()
  await expect(page.getByText('Este estado no admite rechazo ni cancelación municipal.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Cerrar Revisión municipal de ruta ' + shortId(a.id), exact: true }).click()
  await page.getByRole('button', { name: 'Revisar ruta ' + shortId(b.id), exact: true }).click()
  await page.getByRole('combobox', { name: 'Decisión sobre la propuesta', exact: true }).selectOption('cancel')
  await page.getByLabel('Motivo de la decisión', { exact: true }).fill('Cancelar alternativa ficticia')
  await page.getByRole('button', { name: 'Revisar decisión de ruta', exact: true }).click()
  const cancelled = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/routes/' + b.id + '/decisions')
  await page.getByRole('button', { name: 'Confirmar operación de ruta', exact: true }).click()
  expect((await cancelled).status()).toBe(200)
  await page.getByText('Historial de decisiones y ejecución (1)', { exact: true }).click()
  await expect(page.getByText('Cancelar alternativa ficticia', { exact: true })).toBeVisible()
  const history = await request.get(api + '/municipal/routes/' + b.id + '/history', { headers: manager })
  expect((await history.json())[0].actor_id).toBe(profiles.manager)
  await page.screenshot({ path: path.join(artifact, 'fullstack-route-cancelled.png'), fullPage: true })
  await page.getByRole('button', { name: 'Cerrar Revisión municipal de ruta ' + shortId(b.id), exact: true }).click()
  await page.getByRole('button', { name: 'Revisar ruta ' + shortId(c.id), exact: true }).click()
  await page.getByRole('combobox', { name: 'Decisión sobre la propuesta', exact: true }).selectOption('reject')
  await page.getByLabel('Motivo de la decisión', { exact: true }).fill('Rechazar alternativa ficticia sin proveedor verificado')
  await page.getByRole('button', { name: 'Revisar decisión de ruta', exact: true }).click()
  const rejected = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/routes/' + c.id + '/decisions')
  await page.getByRole('button', { name: 'Confirmar operación de ruta', exact: true }).click()
  expect((await rejected).status()).toBe(200)
  const rejectedHistory = await request.get(api + '/municipal/routes/' + c.id + '/history', { headers: manager })
  expect((await rejectedHistory.json())[0].action).toBe('reject')
  await page.getByText('Historial de decisiones y ejecución (1)', { exact: true }).click()
  await expect(page.getByText('Rechazar alternativa ficticia sin proveedor verificado', { exact: true })).toBeVisible()
  await page.screenshot({ path: path.join(artifact, 'fullstack-route-rejected.png'), fullPage: true })
})

test('Fullstack D móvil: ejecución con autorización ficticia aislada, incidencias y reinicio', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const driver = await login(page, 'driver')
  expect((await request.get(api + '/municipal/routes', { headers: driver })).status()).toBe(403)
  const otherLogin = await request.post(services + '/auth/v1/token?grant_type=password', { headers: { apikey: process.env.VITE_SUPABASE_PUBLISHABLE_KEY! }, data: { email: 'driver2@example.test', password } })
  expect(otherLogin.status()).toBe(200)
  const other = { Authorization: 'Bearer ' + (await otherLogin.json()).access_token }
  expect((await request.get(api + '/driver/routes/' + fixtureId, { headers: other })).status()).toBe(404)
  await page.getByRole('button', { name: 'Abrir mi recorrido ' + shortId(fixtureId), exact: true }).click()
  await expect(page.locator('.route-map .route-stop')).toHaveCount(3)
  async function confirm(expectedAction: string) {
    const pending = page.waitForResponse((r) => r.url().startsWith(api + '/driver/routes/' + fixtureId) && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Confirmar operación de ruta', exact: true }).click()
    const response = await pending
    expect(response.status()).toBe(200)
    expect(response.request().postDataJSON().action).toBe(expectedAction)
    await expect(page.getByRole('dialog', { name: 'Confirmar operación de ruta' })).toHaveCount(0)
    return (await response.json()).route
  }
  await page.getByRole('button', { name: 'Revisar inicio de recorrido', exact: true }).click()
  await confirm('start')
  await page.getByRole('button', { name: 'Registrar parada atendida', exact: true }).click()
  await confirm('attend')
  await page.getByLabel('Observación o motivo de no atención', { exact: true }).fill('Acceso bloqueado en la prueba')
  await page.getByLabel('Tipo de incidencia (si corresponde)', { exact: true }).fill('acceso_bloqueado')
  await page.getByRole('button', { name: 'Registrar incidencia', exact: true }).click()
  await confirm('incident')
  await page.getByLabel('Observación o motivo de no atención', { exact: true }).fill('Zona insegura ficticia')
  await page.getByRole('button', { name: 'Registrar no atención', exact: true }).click()
  await confirm('not_attended')
  await page.getByRole('button', { name: 'Revisar fin de recorrido', exact: true }).click()
  const before = await confirm('finish')
  expect(before.status).toBe('finalizada')
  expect(before.stops.map((s: { status: string }) => s.status)).toEqual(['atendida', 'incidencia', 'no_atendida'])
  const restart = await request.post(services + '/__test/restart', { headers: { 'x-test-control': process.env.RECIWISE_INTEGRATED_CONTROL! }, data: {} })
  expect(restart.status()).toBe(200)
  const after = await request.get(api + '/driver/routes/' + fixtureId, { headers: driver })
  expect(await after.json()).toEqual(before)
  await page.reload()
  await page.getByRole('button', { name: 'Abrir mi recorrido ' + shortId(fixtureId), exact: true }).click()
  await expect(page.getByText('Recorrido finalizado. Los registros permanecen disponibles para consulta.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: path.join(artifact, 'fullstack-driver-mobile.png'), fullPage: true })
})
