import { expect, test, type Page, type APIRequestContext } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { deflateSync } from 'node:zlib'
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
let criticalErrors: string[] = []

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
  events = []; externalOrigins = []; criticalErrors = []
  page.on('pageerror', (error) => criticalErrors.push(error.message))
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
  expect(criticalErrors).toEqual([])
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

async function photo(page: Page, reportId: string, expected: number, contents = png, name = 'ficticia.png') {
  const article = page.locator('article').filter({ hasText: reportId })
  if (await article.getByRole('button', { name: 'Ver fotografías', exact: true }).count()) {
    await article.getByRole('button', { name: 'Ver fotografías', exact: true }).click()
  }
  const input = article.getByLabel(/Fotografía \(JPG/)
  await expect(input).toBeEnabled()
  await input.setInputFiles({ name, mimeType: 'image/png', buffer: contents })
  const response = page.waitForResponse((r) => r.url() === api + '/reports/' + reportId + '/photos' && r.request().method() === 'POST')
  await article.getByRole('button', { name: 'Subir fotografía', exact: true }).click()
  expect((await response).status()).toBe(expected)
  return article
}

// Distinct valid one-pixel fixtures; never derived from personal photographs.
function colouredPng(red: number, green: number, blue: number) {
  function chunk(type: string, data: Buffer) {
    const content = Buffer.concat([Buffer.from(type), data])
    let crc = 0xffffffff
    for (const byte of content) {
      crc ^= byte
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0)
    }
    const size = Buffer.alloc(4), checksum = Buffer.alloc(4)
    size.writeUInt32BE(data.length); checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0)
    return Buffer.concat([size, content, checksum])
  }
  const header = Buffer.alloc(13)
  header.writeUInt32BE(1, 0); header.writeUInt32BE(1, 4); header[8] = 8; header[9] = 6
  return Buffer.concat([png.subarray(0, 8), chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.from([0, red, green, blue, 255]))), chunk('IEND', Buffer.alloc(0))])
}

test('recorrido completo: JWT ES256, React, PostgreSQL, fotografía, mapa municipal y reinicio', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 })
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
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect((await request.get(api + '/ready')).status()).toBe(200)
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
  await page.setViewportSize({ width: 1280, height: 900 })
  const manager = await login(page, 'manager')
  await page.getByRole('button', { name: 'Reportes ciudadanos', exact: true }).click()
  const municipal = await request.get(api + '/municipal/reports', { headers: manager.headers })
  expect(municipal.status()).toBe(200)
  const visible = (await municipal.json()).find((row: Report) => row.id === report.id)
  expect(visible).toEqual(report)
  const map = page.getByLabel('Mapa de reportes municipales', { exact: true })
  const circle = map.locator('.leaflet-interactive')
  await expect(circle).toHaveCount(1)
  await circle.click({ force: true })
  await expect(map.locator('.leaflet-popup')).toContainText(report.description)
  await map.getByRole('button', { name: 'Ver detalle y fotografías', exact: true }).click()
  const municipalImage = page.getByAltText('Fotografía 1 del reporte')
  // StrictMode can replace the image after the second initial photo read.
  // Retry locating/scanning the current image, still requiring a real download.
  await expect(async () => {
    await municipalImage.scrollIntoViewIfNeeded()
    expect(await municipalImage.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
  }).toPass({ timeout: 15_000 })
  expect(await page.getByRole('button', { name: 'Registrar reporte', exact: true }).count()).toBe(0)
  await page.screenshot({ path: path.join(artifact, 'municipal-map.png'), fullPage: true })
  const state = await control(request, 'state')
  expect(state.jwks_fetches).toBeGreaterThanOrEqual(2) // Separate real API processes.
  expect(state.object_hashes['controls/keep.png']).toBeTruthy()
  fs.writeFileSync(path.join(artifact, 'restart.json'), JSON.stringify({ ...restarted, before, after: afterRestart }, null, 2))
})

test('dos reportes consecutivos conservan su fotografía distinta tras fallo y reintento', async ({ page, request }) => {
  const citizen = await login(page)
  const firstImage = colouredPng(255, 0, 0), secondImage = colouredPng(0, 0, 255)
  await selectLocation(page, 'PRUEBA AISLADA FOTOS A: imagen roja')
  const { report: first } = await submit(page)
  await photo(page, first.id, 201, firstImage, 'primera-roja.png')
  const before = await control(request, 'report/' + first.id)
  await selectLocation(page, 'PRUEBA AISLADA FOTOS B: imagen azul')
  const { report: second } = await submit(page)
  expect(second.id).not.toBe(first.id)
  await control(request, 'fault', { kind: 'storage_upload' })
  let card = await photo(page, second.id, 502, secondImage, 'segunda-azul.png')
  await expect(card.getByRole('alert')).toContainText('No se pudo guardar la imagen')
  expect((await control(request, 'report/' + second.id)).photos).toHaveLength(0)
  expect(await control(request, 'report/' + first.id)).toEqual(before)
  expect(events.filter((r) => r.method === 'POST' && r.path === '/reports/' + second.id + '/photos')).toHaveLength(1)
  await card.getByRole('button', { name: 'Renovar enlaces', exact: true }).click()
  await expect(card.getByText('Fotografías (0/3)', { exact: true })).toBeVisible()
  card = await photo(page, second.id, 201, secondImage, 'segunda-azul.png')
  await expect(card.getByText('Fotografías (1/3)', { exact: true })).toBeVisible()
  const evidence = []
  for (const [report, expected] of [[first, firstImage], [second, secondImage]] as const) {
    const response = await request.get(api + '/reports/' + report.id + '/photos', { headers: citizen.headers })
    expect(response.status()).toBe(200)
    const photos = await response.json()
    expect(photos).toHaveLength(1); expect(photos[0].report_id).toBe(report.id)
    expect(new URL(photos[0].signed_url).origin).toBe(services)
    const download = await request.get(photos[0].signed_url)
    expect(download.status()).toBe(200)
    const expectedHash = createHash('sha256').update(expected).digest('hex')
    expect(createHash('sha256').update(await download.body()).digest('hex')).toBe(expectedHash)
    const sql = await control(request, 'report/' + report.id)
    expect(sql.photos).toHaveLength(1)
    expect(sql.photos[0].report_id).toBe(report.id)
    expect(sql.photos[0].storage_path).toContain('/' + report.id + '/')
    expect(sql.operations.some((o: { id: string; state: string }) => o.id === sql.photos[0].id && o.state === 'complete')).toBe(true)
    evidence.push({ report_id: report.id, photo_id: sql.photos[0].id, storage_path: sql.photos[0].storage_path, sha256: expectedHash })
  }
  expect(evidence[0].sha256).not.toBe(evidence[1].sha256)
  await page.reload()
  for (const report of [second, first]) {
    const article = page.locator('article.report').filter({ hasText: report.id })
    await article.getByRole('button', { name: 'Ver fotografías', exact: true }).click()
    await expect(article.getByText('Fotografías (1/3)', { exact: true })).toBeVisible()
    const image = article.getByAltText('Fotografía 1 del reporte')
    await expect(async () => {
      await image.scrollIntoViewIfNeeded()
      expect(await image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth === 1)).toBe(true)
    }).toPass({ timeout: 15_000 })
  }
  expect(events.filter((r) => r.method === 'POST' && r.path === '/reports')).toHaveLength(2)
  expect(events.filter((r) => r.method === 'POST' && r.path === '/reports/' + first.id + '/photos')).toHaveLength(1)
  expect(events.filter((r) => r.method === 'POST' && r.path === '/reports/' + second.id + '/photos')).toHaveLength(2)
  const state = await control(request, 'state')
  expect(state.object_hashes['controls/keep.png']).toBeTruthy()
  fs.writeFileSync(path.join(artifact, 'photo-association.json'), JSON.stringify({ evidence, uploads: events.filter((r) => r.method === 'POST' && r.path.endsWith('/photos')) }, null, 2))
  await page.screenshot({ path: path.join(artifact, 'photo-association-two-reports.png'), fullPage: true })
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
  // StrictMode/cleanup may also cancel an initial GET. Assert the failed write,
  // rather than treating cancelled reads as another attempted report creation.
  const failedWrite = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'POST', exact: true }) })
    .filter({ has: page.getByRole('cell', { name: '/reports', exact: true }) })
  await expect(failedWrite.getByRole('cell', { name: 'Sin HTTP', exact: true })).toHaveCount(1)
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
