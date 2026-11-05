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
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
type Headers = { Authorization: string }
type Http = { method: string; path: string; status: number }
let http: Http[] = []
let external: string[] = []
let errors: string[] = []

test.beforeEach(async ({ page, context }) => {
  http = []; external = []; errors = []
  // Auth and Storage are local simulators; business API and PostgreSQL are real.
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(url.hostname)) return route.fulfill({ contentType: 'image/png', body: png })
    if ([api, services, ui].includes(url.origin)) return route.continue()
    external.push(url.origin); return route.abort('blockedbyclient')
  })
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('response', (response) => {
    if (new URL(response.url()).origin === api) http.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() })
  })
})
test.afterEach(async ({}, info) => {
  fs.writeFileSync(path.join(artifact, 'sprint2-' + info.testId.replace(/[^a-z0-9]/gi, '_') + '.json'), JSON.stringify({ title: info.title, http, external, errors, services: { react: 'real', leaflet: 'real', fastapi: 'real HTTP', postgresql: 'real isolated 001+002+003', auth: 'local simulator with verifiable ES256 and HTTP JWKS', storage: 'local simulator', tiles: 'simulated' } }, null, 2))
  expect(external).toEqual([]); expect(errors).toEqual([])
})
async function login(page: Page, name: 'citizen' | 'manager') {
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill(name + '@example.test')
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  const response = page.waitForResponse((r) => r.url().startsWith(services + '/auth/v1/token') && r.status() === 200)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  const session = await (await response).json()
  expect(JSON.parse(Buffer.from(session.access_token.split('.')[0], 'base64url').toString()).alg).toBe('ES256')
  await expect(page.locator('strong').filter({ hasText: name === 'manager' ? /^encargado_municipal$/ : /^ciudadano$/ })).toBeVisible()
  return { Authorization: 'Bearer ' + session.access_token }
}
async function logout(page: Page) { await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click(); await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible() }
async function navigate(page: Page, name: string) {
  const button = page.getByRole('button', { name, exact: true, includeHidden: true })
  if (await button.isHidden()) await page.getByRole('button', { name: 'Abrir navegación', exact: true }).click()
  await page.getByRole('button', { name, exact: true }).click()
}
async function post(request: APIRequestContext, headers: Headers, route: string, data: unknown) {
  const r = await request.post(api + route, { headers, data }); expect(r.status()).toBe(201); return r.json()
}
async function newEvent(request: APIRequestContext, headers: Headers, label: string, n = 0) {
  return post(request, headers, '/municipal/events', { latitude: -12.05 - n * .001, longitude: -75.22, intervention_type: label })
}
async function review(page: Page, reportId: string) {
  await navigate(page, 'Revisión de agrupaciones')
  await page.getByRole('button', { name: 'Revisar relación ' + shortId(reportId), exact: true }).click()
  await expect(page.getByLabel('Evento candidato')).toBeVisible()
}
async function decide(page: Page, action: string, candidate?: string) {
  if (candidate) await page.getByLabel('Evento candidato').selectOption(candidate)
  await page.getByLabel('Observaciones de la decisión').fill('Verificación integrada con datos ficticios')
  await page.getByRole('button', { name: action, exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Confirmar decisión municipal' })).toBeVisible()
  const result = page.waitForResponse((r) => new URL(r.url()).pathname === '/municipal/groupings/decisions' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Confirmar decisión', exact: true }).click()
  const response = await result; expect(response.status()).toBe(200)
  const command = response.request().postDataJSON(); const body = await response.json()
  expect(body.decision.id).toBe(command.operation_id)
  await expect(page.getByRole('dialog', { name: 'Detalle de decisión' })).toBeVisible()
  await page.getByRole('button', { name: 'Cerrar Detalle de decisión', exact: true }).click()
  await expect(page.getByLabel('Evento candidato')).toBeVisible()
  return { command, body }
}

test('Sprint 2 integrado: reporte desde Leaflet, eventos, cinco decisiones e historial en PostgreSQL', async ({ page, request }) => {
  const citizen = await login(page, 'citizen')
  const description = 'S2 integrado: reporte ciudadano para revisión municipal'
  await page.getByLabel('Descripción', { exact: true }).fill(description)
  await page.getByRole('button', { name: 'Elegir en el mapa', exact: true }).click()
  await page.locator('.location-map').click({ position: { x: 180, y: 170 } })
  await page.getByRole('button', { name: 'Confirmar ubicación', exact: true }).click()
  const created = page.waitForResponse((r) => r.url() === api + '/reports' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Registrar reporte', exact: true }).click()
  const response = await created; expect(response.status()).toBe(201); const report = await response.json()
  expect(typeof report.latitude).toBe('number'); expect(typeof report.longitude).toBe('number')
  for (const route of ['/municipal/events', '/municipal/groupings', '/municipal/route-proposals']) expect((await request.get(api + route, { headers: citizen })).status()).toBe(403)
  await expect(page.getByRole('navigation', { name: 'Navegación municipal' })).toHaveCount(0)
  await logout(page); const manager = await login(page, 'manager')
  const a = await newEvent(request, manager, 'Evento integrado A')
  const b = await newEvent(request, manager, 'Evento integrado B', 1)
  await review(page, report.id)
  const confirm = await decide(page, 'Confirmar agrupación', a.id)
  expect(confirm.command.expected_event_id).toBe(null); expect(confirm.command.expected_decision_id).toBe(null)
  await navigate(page, 'Eventos o puntos de atención')
  await page.getByRole('button', { name: 'Abrir evento ' + shortId(a.id), exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText(description, { exact: true })).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'Reportes asociados (1)', exact: true })).toBeVisible()
  await expect(dialog.locator('.event-marker')).toHaveCount(1)
  await expect(dialog.locator('path.leaflet-interactive')).toHaveCount(1)
  await page.getByRole('button', { name: 'Cerrar Detalle de evento ' + shortId(a.id), exact: true }).click()
  await review(page, report.id)
  const revision = await decide(page, 'Registrar revisión', b.id)
  expect(revision.command.expected_decision_id).toBe(confirm.body.decision.id)
  await decide(page, 'Mantener separados', b.id)
  const correction = await decide(page, 'Corregir asociación', b.id)
  expect(correction.body.decision.operation).toBe('reassign')
  const separate = await decide(page, 'Separar reporte')
  expect(separate.command.candidate_event_id).toBe(null); expect(separate.body.relation.event_id).toBe(null)
  await expect(page.locator('.timeline > li')).toHaveCount(5)
  await page.getByRole('button', { name: 'Ver decisión ' + shortId(separate.body.decision.id), exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Detalle de decisión' })).toContainText(separate.body.decision.id)
  await page.getByRole('button', { name: 'Cerrar Detalle de decisión', exact: true }).click()
  const mine = await request.get(api + '/reports/mine', { headers: citizen })
  expect((await mine.json()).find((r: { id: string }) => r.id === report.id).status).toBe('recibido')
  const associated = await request.get(api + '/municipal/events/' + a.id + '/reports', { headers: manager }); expect(await associated.json()).toEqual([])
  await page.screenshot({ path: path.join(artifact, 'sprint2-groupings.png'), fullPage: true })
})

test('Sprint 2 integrado: conflicto PostgreSQL 409 requiere nueva lectura y consentimiento', async ({ page, request }) => {
  const citizen = await login(page, 'citizen')
  const report = await post(request, citizen, '/reports', { description: 'S2 conflicto de revisión entre encargados', latitude: -12.05, longitude: -75.22, observed_at: new Date().toISOString(), waste_type: null })
  await logout(page); const manager = await login(page, 'manager')
  const e = await newEvent(request, manager, 'Candidato para conflicto')
  await review(page, report.id); await page.getByLabel('Evento candidato').selectOption(e.id)
  await page.getByRole('button', { name: 'Confirmar agrupación', exact: true }).click()
  const concurrent = await request.post(api + '/municipal/groupings/decisions', { headers: manager, data: { operation_id: randomUUID(), report_id: report.id, decision: 'revisar', candidate_event_id: e.id, expected_event_id: null, expected_decision_id: null, notes: 'Otra revisión municipal' } })
  expect(concurrent.status()).toBe(200)
  const result = page.waitForResponse((r) => r.url() === api + '/municipal/groupings/decisions' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Confirmar decisión', exact: true }).click()
  expect((await result).status()).toBe(409)
  await expect(page.getByText(/Debes descartar este comando/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirmar decisión', exact: true })).toHaveCount(0)
  expect(http.filter((h) => h.method === 'POST' && h.path === '/municipal/groupings/decisions')).toHaveLength(1)
  await page.getByRole('button', { name: 'Descartar y actualizar relación', exact: true }).click()
  await expect(page.getByLabel('Evento candidato')).toBeVisible()
  const next = await decide(page, 'Confirmar agrupación', e.id)
  expect(next.command.expected_decision_id).toBe((await concurrent.json()).decision.id)
  await page.screenshot({ path: path.join(artifact, 'sprint2-conflict-recovered.png'), fullPage: true })
})

test('Sprint 2 integrado: consulta de propuestas, geometría persistida, paradas y exclusiones sin generación UI', async ({ page, request }) => {
  const manager = await login(page, 'manager')
  // Seeding runs only through test APIRequestContext against the owned local API.
  // This is an explicit result fixture, never a frontend algorithm or D3 result.
  const vehicle = await post(request, manager, '/municipal/vehicles', { label: 'Unidad de prueba S2', vehicle_type: 'compactadora', available: true, plate: null, capacity_kg: null })
  const start = await post(request, manager, '/municipal/sites', { name: 'Salida ficticia S2', site_type: 'salida', latitude: -12.05, longitude: -75.22 })
  const end = await post(request, manager, '/municipal/sites', { name: 'Descarga ficticia S2', site_type: 'descarga', latitude: -12.07, longitude: -75.24 })
  const shift = await post(request, manager, '/municipal/shifts', { vehicle_id: vehicle.id, driver_id: profiles.driver, departure_site_id: start.id, disposal_site_id: end.id, starts_at: '2030-11-19T13:00:00Z', ends_at: '2030-11-19T18:00:00Z' })
  const events = await Promise.all([0, 1, 2].map((n) => newEvent(request, manager, 'Parada ficticia ' + n, n)))
  const command = { proposal_id: randomUUID(), shift_id: shift.id, event_ids: events.map((e) => e.id) }
  const pending = await post(request, manager, '/municipal/route-proposals', command)
  expect(pending.calculation_status).toBe('pending'); expect(pending.geometry_geojson).toBe(null)
  const fixture = await post(request, manager, '/municipal/route-proposals', { ...command, proposal_id: randomUUID(), test_data: true, result: {
    algorithm_version: 'browser-fixture-v1', matrix_source: null,
    stops: [{ event_id: events[1].id, order: 1 }, { event_id: events[0].id, order: 2 }],
    excluded_events: [{ event_id: events[2].id, reason: 'Exclusión ficticia para aceptación de interfaz' }],
    distance_m: 1200, estimated_duration_seconds: 600,
    geometry_geojson: { type: 'LineString', coordinates: [[-75.22, -12.051], [-75.22, -12.05]] },
    limitations: ['Datos de prueba; sin optimizador D3 ni validación vial'],
  } })
  expect(fixture.result_origin).toBe('test_fixture'); expect(fixture.operational).toBe(false)
  await navigate(page, 'Planificación de rutas')
  await expect(page.getByRole('button', { name: 'Solicitar propuesta (pendiente)', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Abrir propuesta ' + shortId(fixture.id), exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText(/Datos de prueba · NO OPERATIVA/)).toBeVisible()
  await expect(dialog.getByText('Exclusión ficticia para aceptación de interfaz', { exact: false })).toBeVisible()
  await expect(dialog.getByText('browser-fixture-v1', { exact: true })).toBeVisible()
  await expect(dialog.getByText('10 min', { exact: true })).toBeVisible()
  await expect(dialog.locator('.route-map .route-stop')).toHaveCount(2)
  await expect(dialog.locator('.route-map path.leaflet-interactive')).toHaveCount(1)
  await expect(dialog.getByText(/sin coordenadas verificables/)).toHaveCount(0)
  const stops = await request.get(api + '/municipal/route-proposals/' + fixture.id + '/stops', { headers: manager })
  expect((await stops.json()).map((s: { event_id: string }) => s.event_id)).toEqual([events[1].id, events[0].id])
  await page.screenshot({ path: path.join(artifact, 'sprint2-route-readonly.png'), fullPage: true })
  await page.getByRole('button', { name: 'Cerrar Detalle de propuesta ' + shortId(fixture.id), exact: true }).click()
  await page.getByRole('button', { name: 'Abrir propuesta ' + shortId(pending.id), exact: true }).click()
  await expect(dialog.getByText(/Pendiente de cálculo · NO OPERATIVA/)).toBeVisible()
  await expect(dialog.getByText('No hay paradas en esta página', { exact: true })).toBeVisible()
  await expect(dialog.locator('.route-map path.leaflet-interactive')).toHaveCount(0)
  expect(http.some((h) => h.path.startsWith('/municipal/route-proposals') && h.method !== 'GET')).toBe(false)
  expect(http.some((h) => h.path.endsWith('/stops') && h.status === 200)).toBe(true)
  expect(http.some((h) => h.path.endsWith('/excluded-events') && h.status === 200)).toBe(true)
})
