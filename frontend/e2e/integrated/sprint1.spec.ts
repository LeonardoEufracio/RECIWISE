import { expect, test, type Page, type APIRequestContext } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { createHash } from 'node:crypto'
import type { Report } from '../../src/types'

const api = process.env.RECIWISE_INTEGRATED_API_URL!
const services = process.env.RECIWISE_INTEGRATED_SERVICES_URL!
const ui = process.env.RECIWISE_INTEGRATED_UI_URL!
const artifact = process.env.RECIWISE_INTEGRATED_ARTIFACT!
const controlHeaders = { 'x-test-control': process.env.RECIWISE_INTEGRATED_CONTROL! }
const password = process.env.RECIWISE_INTEGRATED_PASSWORD!
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
type HttpEvent = { method: string; path: string; status: number }
let events: HttpEvent[] = []
let externalOrigins: string[] = []

async function control(request: APIRequestContext, route: string, data?: unknown) {
  const response = await (async () => {
    try {
      return data === undefined
        ? await request.get(services + '/__test/' + route, { headers: controlHeaders })
        : await request.post(services + '/__test/' + route, { headers: controlHeaders, data })
    } catch {
      throw new Error('Local test observation unavailable; credentials omitted')
    }
  })()
  expect(response.status()).toBe(200)
  return response.json()
}

test.beforeEach(async ({ page, context }) => {
  events = []; externalOrigins = []
  // Business requests are continued to the real API, never fulfilled here.
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(url.hostname)) {
      await route.fulfill({ contentType: 'image/png', body: png })
    } else if ([api, services, ui].includes(url.origin)) {
      await route.continue()
    } else {
      externalOrigins.push(url.origin)
      await route.abort('blockedbyclient')
    }
  })
  page.on('response', (response) => {
    if (new URL(response.url()).origin === api) {
      events.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() })
    }
  })
})

test.afterEach(async ({}, info) => {
  fs.writeFileSync(path.join(artifact, 'http-' + info.testId.replace(/[^a-zA-Z0-9]/g, '_') + '.json'),
    JSON.stringify({ title: info.title, events, externalOrigins }, null, 2))
  expect(externalOrigins).toEqual([])
})

async function login(page: Page, name = 'citizen') {
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill(name + '@example.test')
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  const sessionResponse = page.waitForResponse((r) => r.url().startsWith(services + '/auth/v1/token') && r.status() === 200)
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  const session = await (await sessionResponse).json()
  const header = JSON.parse(Buffer.from(session.access_token.split('.')[0], 'base64url').toString())
  expect(header.alg).toBe('ES256')
  const role = name === 'manager' ? 'encargado_municipal' : 'ciudadano'
  await expect(page.locator('strong').filter({ hasText: new RegExp('^' + role + '$') })).toBeVisible()
  return { headers: { Authorization: 'Bearer ' + session.access_token }, session }
}

async function selectLocation(page: Page, description: string) {
  await page.getByLabel('Descripción', { exact: true }).fill(description)
  await expect(page.getByRole('button', { name: 'Registrar reporte', exact: true })).toBeDisabled()
  await expect(page.locator('input[name="latitude"],input[name="longitude"]')).toHaveCount(0)
  await page.getByRole('button', { name: 'Elegir en el mapa', exact: true }).click()
  await page.locator('.location-map').click({ position: { x: 175, y: 165 } })
  const marker = page.locator('.location-map .leaflet-marker-icon')
  await expect(marker).toHaveCount(1)
  const box = (await marker.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 25, box.y + box.height / 2 + 15, { steps: 8 })
  await page.mouse.up()
  const summary = await page.locator('.location-summary p').first().innerText()
  const coordinates = summary.match(/-?\d+\.\d+/g)!.map(Number)
  await page.getByRole('button', { name: 'Confirmar ubicación', exact: true }).click()
  await expect(page.getByText(/Ubicación confirmada/)).toBeVisible()
  return coordinates
}

async function submit(page: Page) {
  const response = page.waitForResponse((r) => r.url() === api + '/reports' && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Registrar reporte', exact: true }).click()
  const received = await response
  expect(received.status()).toBe(201)
  await expect(page.getByText(/Reporte registrado/)).toBeVisible()
  return { report: await received.json() as Report, payload: received.request().postDataJSON() }
}

async function photo(page: Page, reportId: string, expected: number) {
  const article = page.locator('article').filter({ hasText: reportId })
  if (await article.getByRole('button', { name: 'Ver fotografías', exact: true }).count()) {
    await article.getByRole('button', { name: 'Ver fotografías', exact: true }).click()
  }
  const input = article.getByLabel(/Fotografía \(JPG/)
  await expect(input).toBeEnabled()
  await input.setInputFiles({ name: 'ficticia.png', mimeType: 'image/png', buffer: png })
  const response = page.waitForResponse((r) => r.url() === api + '/reports/' + reportId + '/photos' && r.request().method() === 'POST')
  await article.getByRole('button', { name: 'Subir fotografía', exact: true }).click()
  expect((await response).status()).toBe(expected)
  return article
}

test('recorrido completo: JWT ES256, React, PostgreSQL, fotografía, mapa municipal y reinicio', async ({ page, request }) => {
  const citizen = await login(page)
  // Fake privileged metadata does not replace the profile role stored in PostgreSQL.
  expect(citizen.session.user.user_metadata.role).toBe('encargado_municipal')
  const me = await request.get(api + '/me', { headers: citizen.headers })
  expect(me.status()).toBe(200)
  expect((await me.json()).role).toBe('ciudadano')
  const initialPosts = events.filter((r) => r.method === 'POST' && r.path === '/reports').length
  const [latitude, longitude] = await selectLocation(page, 'S1 integrado: ubicación elegida y corregida en Leaflet')
  expect(events.filter((r) => r.method === 'POST' && r.path === '/reports')).toHaveLength(initialPosts)
  const { report, payload } = await submit(page)
  expect(report.latitude).toBeCloseTo(latitude, 5)
  expect(report.longitude).toBeCloseTo(longitude, 5)
  expect(typeof payload.latitude).toBe('number')
  expect(typeof payload.longitude).toBe('number')
  const sql = await control(request, 'report/' + report.id)
  expect(sql.read_only).toBe(true)
  expect(sql.report.id).toBe(report.id)
  expect(sql.report.citizen_id).toBe(citizen.session.user.id)
  expect(sql.report.latitude).toBe(payload.latitude)
  expect(sql.report.longitude).toBe(payload.longitude)
  const mine = await request.get(api + '/reports/mine', { headers: citizen.headers })
  expect(mine.status()).toBe(200)
  expect((await mine.json()).some((row: Report) => row.id === report.id)).toBe(true)
  expect((await request.get(api + '/municipal/reports', { headers: citizen.headers })).status()).toBe(403)
  expect((await request.get(api + '/me')).status()).toBe(401)
  expect((await request.get(api + '/me', { headers: { Authorization: 'Bearer a.b.c' } })).status()).toBe(401)
  const article = await photo(page, report.id, 201)
  const image = article.getByAltText('Fotografía 1 del reporte')
  await image.scrollIntoViewIfNeeded()
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
  expect(new URL((await image.getAttribute('src'))!).origin).toBe(services)
  const downloaded = Buffer.from(await image.evaluate(async (img: HTMLImageElement) => {
    const response = await fetch(img.src)
    return Array.from(new Uint8Array(await response.arrayBuffer()))
  }))
  expect(downloaded.equals(png)).toBe(true)
  const before = await control(request, 'report/' + report.id)
  expect(before.photos).toHaveLength(1)
  expect(before.photos[0].slot).toBe(1)
  expect(before.photos[0].size_bytes).toBe(png.length)
  expect(before.operations[0].state).toBe('complete')
  fs.writeFileSync(path.join(artifact, 'report-flow.json'), JSON.stringify({
    report, payload, sql: before, photo_sha256: createHash('sha256').update(downloaded).digest('hex'),
  }, null, 2))
  await page.screenshot({ path: path.join(artifact, 'citizen.png'), fullPage: true })
  const restarted = await control(request, 'restart', {})
  expect(restarted.before_pid).not.toBe(restarted.after_pid)
  const afterRestart = await control(request, 'report/' + report.id)
  expect(afterRestart).toEqual(before)
  await page.reload()
  await expect(page.locator('article').filter({ hasText: report.id })).toContainText(report.description)
  expect((await request.get(api + '/ready')).status()).toBe(200)
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
  const manager = await login(page, 'manager')
  const municipal = await request.get(api + '/municipal/reports', { headers: manager.headers })
  expect(municipal.status()).toBe(200)
  const visible = (await municipal.json()).find((row: Report) => row.id === report.id)
  expect(visible).toEqual(report)
  const map = page.getByLabel('Mapa de reportes municipales', { exact: true })
  const circle = map.locator('.leaflet-interactive')
  await expect(circle).toHaveCount(1)
  await circle.click({ force: true })
  await expect(map.locator('.leaflet-popup')).toContainText(report.description)
  await map.getByRole('button', { name: 'Ver fotografías', exact: true }).click()
  const municipalImage = page.getByAltText('Fotografía 1 del reporte')
  await municipalImage.scrollIntoViewIfNeeded()
  await expect.poll(() => municipalImage.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
  expect(await page.getByRole('button', { name: 'Registrar reporte', exact: true }).count()).toBe(0)
  await page.screenshot({ path: path.join(artifact, 'municipal-map.png'), fullPage: true })
  const state = await control(request, 'state')
  expect(state.jwks_fetches).toBeGreaterThanOrEqual(2) // Separate real API processes.
  expect(state.object_hashes['controls/keep.png']).toBeTruthy()
  fs.writeFileSync(path.join(artifact, 'restart.json'), JSON.stringify({ ...restarted, before, after: afterRestart }, null, 2))
})

test('validación 422 y autorización por perfil/autor con JWT reales de pruebas', async ({ page, request }) => {
  const citizen = await login(page)
  const invalid = await request.post(api + '/reports', {
    headers: citizen.headers, data: { description: ' ab ', latitude: 91, longitude: -75, observed_at: new Date().toISOString() },
  })
  expect(invalid.status()).toBe(422)
  const errors = await invalid.json()
  expect(errors.detail.some((issue: { loc: string[] }) => issue.loc[1] === 'description')).toBe(true)
  expect(errors.detail.some((issue: { loc: string[] }) => issue.loc[1] === 'latitude')).toBe(true)
  await selectLocation(page, 'S1 aislado: autorización por autor')
  const { report } = await submit(page)
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
  const other = await login(page, 'citizen2')
  const mine = await request.get(api + '/reports/mine', { headers: other.headers })
  expect((await mine.json()).some((row: Report) => row.id === report.id)).toBe(false)
  expect((await request.get(api + '/reports/' + report.id, { headers: other.headers })).status()).toBe(404)
  expect((await request.get(api + '/reports/' + report.id + '/photos', { headers: other.headers })).status()).toBe(404)
  expect((await request.get(api + '/municipal/reports', { headers: other.headers })).status()).toBe(403)
})

test('fallos de Storage y persistencia: errores visibles, compensación y reintento sin duplicar reporte', async ({ page, request }) => {
  await login(page)
  await selectLocation(page, 'S1 aislado: recuperación de fotografía')
  const { report } = await submit(page)
  await control(request, 'fault', { kind: 'storage_upload' })
  let article = await photo(page, report.id, 502)
  await expect(article.getByRole('alert')).toContainText('No se pudo guardar la imagen')
  let sql = await control(request, 'report/' + report.id)
  expect(sql.photos).toHaveLength(0)
  expect(sql.operations[0].state).toBe('quarantined')
  await control(request, 'fault', { kind: 'photo_persistence' })
  article = await photo(page, report.id, 503)
  await expect(article.getByRole('alert')).toContainText('No se pudo guardar la fotografía')
  sql = await control(request, 'report/' + report.id)
  expect(sql.photos).toHaveLength(0)
  expect(sql.operations.some((op: { state: string }) => op.state === 'cleaned')).toBe(true)
  article = await photo(page, report.id, 201)
  await expect(article.getByText('Fotografía guardada.')).toBeVisible()
  sql = await control(request, 'report/' + report.id)
  expect(sql.photos).toHaveLength(1)
  expect(sql.report.id).toBe(report.id)
  const state = await control(request, 'state')
  expect(state.deletions).toHaveLength(1)
  expect(state.object_hashes['controls/keep.png']).toBeTruthy()
  expect(events.filter((r) => r.method === 'POST' && r.path === '/reports')).toHaveLength(1)
  fs.writeFileSync(path.join(artifact, 'photo-failures.json'), JSON.stringify({ sql, deletions: state.deletions }, null, 2))
})

test('fallo de comunicación, recuperación y CORS sin escribir un reporte duplicado', async ({ page, request }) => {
  const citizen = await login(page)
  const before = await (await request.get(api + '/reports/mine', { headers: citizen.headers })).json()
  await selectLocation(page, 'S1 aislado: comunicación recuperada')
  // Only this deliberate transport-failure request is intercepted; happy path is HTTP real.
  await page.route(api + '/reports', (route) => route.abort('connectionrefused'), { times: 1 })
  await page.getByRole('button', { name: 'Registrar reporte', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('No se pudo completar la petición')
  const after = await (await request.get(api + '/reports/mine', { headers: citizen.headers })).json()
  expect(after).toEqual(before)
  await expect(page.getByRole('cell', { name: 'Sin HTTP', exact: true })).toHaveCount(1)
  await submit(page)
  const final = await (await request.get(api + '/reports/mine', { headers: citizen.headers })).json()
  expect(final).toHaveLength(before.length + 1)
  const denied = await request.fetch(api + '/reports', { method: 'OPTIONS', headers: {
    Origin: 'https://untrusted.invalid', 'Access-Control-Request-Method': 'POST',
    'Access-Control-Request-Headers': 'authorization,content-type',
  } })
  expect(denied.status()).toBe(400)
  expect(denied.headers()['access-control-allow-origin']).toBeUndefined()
})
