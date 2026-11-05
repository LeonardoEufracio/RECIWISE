const { createRequire } = require('node:module')
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..')
const { test, expect } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test')
const read = (name) => JSON.parse(fs.readFileSync(path.join(root, '.localdev', name), 'utf8'))
const config = read('config.json'), credentials = read('credentials.json'), original = read('check-data.json')
const evidence = process.env.RECIWISE_MUNICIPAL_EVIDENCE
const api = 'http://127.0.0.1:' + config.ports.api, auth = 'http://127.0.0.1:' + config.ports.auth
const ui = 'http://127.0.0.1:' + config.ports.ui
const marker = 'PRUEBA MUNICIPAL LOCAL S2'
const reportLabel = marker + ': reporte para asociación manual'
const eventLabel = marker + ': revisión manual', vehicleLabel = marker + ': unidad NO OPERATIVA'
const shortId = (id) => id.slice(0, 4) + '…' + id.slice(-4)
const datePeru = (value) => new Intl.DateTimeFormat('es-PE', { timeZone: 'America/Lima', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
const manifestPath = path.join(root, '.localdev/municipal-acceptance.json')
let log
const saveFixture = (key, id) => {
  const data = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {}
  if (data.owner && data.owner !== config.owner) throw new Error('Wrong fixture owner')
  fs.writeFileSync(manifestPath, JSON.stringify({ ...data, owner: config.owner, [key]: id }, null, 2))
}

test.beforeEach(async ({ page, context }) => {
  log = { http: [], failedRequests: [], pageErrors: [], consoleErrors: [], blockedExternal: [], injected: [], gpsRequests: 0 }
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(url.hostname)) return route.fulfill({ contentType: 'image/png', body: png })
    if ([api, auth, ui].includes(url.origin)) return route.continue()
    log.blockedExternal.push(url.origin); return route.abort('blockedbyclient')
  })
  await page.addInitScript(() => {
    window.__gpsRequests = 0
    const original = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation)
    navigator.geolocation.getCurrentPosition = (...args) => { window.__gpsRequests++; return original(...args) }
  })
  page.on('pageerror', (e) => log.pageErrors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') log.consoleErrors.push(m.text()) })
  page.on('response', (r) => {
    const url = new URL(r.url())
    if (url.origin === api) log.http.push({ method: r.request().method(), path: url.pathname, status: r.status(), query: url.search })
  })
  page.on('requestfailed', (r) => {
    const url = new URL(r.url())
    if (url.origin === api) log.failedRequests.push({ method: r.method(), path: url.pathname, error: r.failure()?.errorText })
  })
})
test.afterEach(async ({ page }, info) => {
  log.gpsRequests = await page.evaluate(() => window.__gpsRequests || 0).catch(() => 0)
  fs.writeFileSync(path.join(evidence, info.title.replace(/[^a-zA-Z0-9]+/g, '-') + '.json'), JSON.stringify(log, null, 2))
  expect(log.pageErrors).toEqual([])
  expect(log.blockedExternal).toEqual([])
  expect(log.gpsRequests).toBe(0)
  expect(log.failedRequests.filter((r) => !(r.method === 'GET' && r.error === 'net::ERR_ABORTED'))).toEqual([])
  expect(log.http.filter((r) => r.status >= 500 && !(r.path === '/municipal/events' && r.status === 503 && log.injected.length))).toEqual([])
  // Expected failed HTTP requests are retained; uncaught JS errors are never ignored.
  expect(log.consoleErrors.filter((s) => !/^Failed to load resource:/.test(s))).toEqual([])
})

async function login(page, actor = 'manager') {
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill(actor + '@example.test')
  await page.getByLabel('Contraseña', { exact: true }).fill(credentials.auth_password)
  const response = page.waitForResponse((r) => new URL(r.url()).origin === auth && new URL(r.url()).pathname === '/auth/v1/token')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  const token = (await (await response).json()).access_token
  const role = actor === 'manager' ? 'encargado_municipal' : 'ciudadano'
  await expect(page.locator('strong').filter({ hasText: new RegExp('^' + role + '$') })).toBeVisible()
  return token
}
async function navigate(page, section) {
  const menu = page.getByRole('button', { name: 'Abrir navegación', exact: true })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('navigation', { name: 'Navegación municipal' }).getByRole('button', { name: section, exact: true }).click()
  await expect(page.getByText('Modo real', { exact: true })).toBeVisible()
}
async function request(page, token, route, method = 'GET', body) {
  return page.evaluate(async ({ api, token, route, method, body }) => {
    const r = await fetch(api + route, { method, headers: { ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
    return { status: r.status, body: await r.json() }
  }, { api, token, route, method, body })
}
async function get(page, token, route) {
  const response = await request(page, token, route)
  expect(response.status).toBe(200)
  return response.body
}
async function all(page, token, route) {
  const rows = []
  for (let offset = 0; offset < 10000; offset += 200) {
    const next = await get(page, token, route + '?limit=200&offset=' + offset)
    rows.push(...next)
    if (next.length < 200) return rows
  }
  throw new Error('Fixture search exceeded safe bound')
}
async function unique(page, token, route, field, value) {
  const rows = (await all(page, token, route)).filter((r) => r[field] === value)
  expect(rows.length, 'No duplicate labelled fixtures').toBeLessThanOrEqual(1)
  return rows[0]
}
async function selectPoint(scope) {
  await scope.getByRole('button', { name: 'Elegir en el mapa', exact: true }).click()
  const map = scope.locator('.location-map')
  await expect(map).toBeVisible()
  const bounds = await map.boundingBox()
  await map.click({ position: { x: Math.floor(bounds.width * .55), y: 145 } })
  await expect(scope.getByTitle('Ubicación seleccionada', { exact: true })).toBeVisible()
  await scope.getByRole('button', { name: 'Confirmar ubicación', exact: true }).click()
}
async function photoLoaded(scope) {
  const image = scope.getByAltText('Fotografía 1 del reporte')
  await expect(async () => {
    await image.scrollIntoViewIfNeeded()
    expect(await image.evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true)
  }).toPass({ timeout: 15_000 })
}

test('01 reportes reales filtros detalle fotos Leaflet y recarga', async ({ page }) => {
  const token = await login(page)
  const reports = await get(page, token, '/municipal/reports?limit=50&offset=0')
  const report = reports.find((r) => r.id === original.report)
  expect(report).toBeTruthy()
  await navigate(page, 'Reportes ciudadanos')
  await expect(page.locator('article.report')).toHaveCount(reports.length)
  const card = page.locator('article.report').filter({ hasText: report.id })
  await expect(card.getByText(report.description, { exact: true })).toBeVisible()
  await expect(card).toContainText(`${report.latitude}, ${report.longitude}`)
  await expect(card).toContainText(report.waste_type)
  await expect(card.getByText('Pendiente', { exact: true })).toBeVisible()
  await expect(card).toContainText('Observado: ' + datePeru(report.observed_at))
  await expect(card).toContainText('Registrado: ' + datePeru(report.created_at))
  await page.getByLabel('Filtrar por estado (vacío = todos)').fill(report.status)
  const filtered = page.waitForResponse((r) => r.url().includes('/municipal/reports?') && new URL(r.url()).searchParams.get('status') === report.status && r.status() === 200)
  await page.getByRole('button', { name: 'Aplicar filtro', exact: true }).click()
  const expected = await (await filtered).json()
  await expect(page.locator('article.report')).toHaveCount(expected.length)
  await page.getByLabel('Buscar por descripción en esta página').fill(report.description)
  await expect(page.locator('article.report')).toHaveCount(1)
  const map = page.locator('.map[aria-label="Mapa de reportes municipales"]')
  await expect(map.locator('path.leaflet-interactive')).toHaveCount(1)
  await map.locator('path.leaflet-interactive').click({ force: true })
  await expect(map.locator('.leaflet-popup')).toContainText(report.description)
  await map.getByRole('button', { name: 'Ver detalle y fotografías', exact: true }).click()
  await expect(card).toHaveClass(/selected-report/)
  await photoLoaded(card)
  expect((await get(page, token, '/reports/' + report.id + '/photos')).length).toBeGreaterThan(0)
  await card.getByRole('button', { name: 'Renovar enlaces', exact: true }).click()
  await photoLoaded(card)
  await page.screenshot({ path: path.join(evidence, 'municipal-reportes-desktop.png'), fullPage: true })
  await page.getByLabel('Buscar por descripción en esta página').fill('sin coincidencias 7c89')
  await expect(page.getByText('No hay coincidencias en esta página.', { exact: true })).toBeVisible()
  await page.getByLabel('Buscar por descripción en esta página').fill('')
  await page.getByLabel('Filtrar por estado (vacío = todos)').fill('no_existe_prueba')
  await page.getByRole('button', { name: 'Aplicar filtro', exact: true }).click()
  await expect(page.getByText('No hay reportes en esta página.', { exact: true })).toBeVisible()
  await page.reload()
  await navigate(page, 'Reportes ciudadanos')
  await expect(card).toContainText(report.description)
  expect(log.http.every((r) => r.method === 'GET')).toBe(true)
})

test('02 evento manual asociado confirmado persistente y sin cambiar reporte', async ({ page }) => {
  let token = await login(page)
  let report = await unique(page, token, '/municipal/reports', 'description', reportLabel)
  if (!report) {
    await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
    token = await login(page, 'citizen')
    await page.getByLabel('Descripción', { exact: true }).fill(reportLabel)
    await expect(page.getByRole('button', { name: 'Registrar reporte', exact: true })).toBeDisabled()
    await selectPoint(page.getByRole('region', { name: 'Ubicación del reporte', exact: true }))
    const saved = page.waitForResponse((r) => r.url() === api + '/reports' && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Registrar reporte', exact: true }).click()
    const response = await saved
    expect(response.status()).toBe(201)
    report = await response.json(); saveFixture('report', report.id)
    await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
    token = await login(page)
  }
  saveFixture('report', report.id)
  let event = await unique(page, token, '/municipal/events', 'intervention_type', eventLabel)
  const reportBefore = (await all(page, token, '/municipal/reports')).find((r) => r.id === report.id)
  await navigate(page, 'Eventos o puntos de atención')
  if (!event) {
    const relation = await get(page, token, '/municipal/groupings/reports/' + report.id)
    expect(relation.event_id).toBeNull(); expect(relation.last_decision_id).toBeNull()
    await page.getByRole('button', { name: 'Crear evento manual', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Crear evento municipal', exact: true })
    await dialog.getByLabel('Intervención manual (opcional)').fill(eventLabel)
    await expect(dialog.getByRole('button', { name: 'Revisar evento manual', exact: true })).toBeDisabled()
    await selectPoint(dialog.getByRole('region', { name: 'Ubicación del evento', exact: true }))
    await dialog.locator('.report-choice').filter({ hasText: report.id }).getByRole('checkbox').check()
    const before = log.http.filter((r) => r.method === 'POST' && r.path === '/municipal/events').length
    await dialog.getByRole('button', { name: 'Revisar evento manual', exact: true }).click()
    await expect(dialog.getByRole('heading', { name: 'Confirmar evento', exact: true })).toBeVisible()
    expect(log.http.filter((r) => r.method === 'POST' && r.path === '/municipal/events').length).toBe(before)
    const saved = page.waitForResponse((r) => r.url() === api + '/municipal/events' && r.request().method() === 'POST')
    await dialog.getByRole('button', { name: 'Confirmar creación de evento', exact: true }).dblclick()
    const response = await saved
    expect(response.status()).toBe(201)
    event = await response.json(); saveFixture('event', event.id)
    expect(log.http.filter((r) => r.method === 'POST' && r.path === '/municipal/events').length).toBe(before + 1)
  } else {
    await page.getByRole('button', { name: 'Abrir evento ' + shortId(event.id), exact: true }).click()
  }
  saveFixture('event', event.id)
  const dialog = page.getByRole('dialog', { name: 'Detalle de evento ' + shortId(event.id), exact: true })
  await expect(dialog).toContainText(report.description)
  await expect(dialog).toContainText(`Ubicación: ${event.latitude}, ${event.longitude}`)
  await expect(dialog.locator('.event-marker')).toHaveCount(1)
  await expect(dialog.locator('path.leaflet-interactive')).toHaveCount(1)
  await page.screenshot({ path: path.join(evidence, 'municipal-evento-manual.png'), fullPage: true })
  const links = await get(page, token, '/municipal/events/' + event.id + '/reports')
  expect(links.map((r) => r.id)).toEqual([report.id])
  expect(links[0]).toEqual(reportBefore)
  const relation = await get(page, token, '/municipal/groupings/reports/' + report.id)
  expect(relation.event_id).toBe(event.id); expect(relation.linkage_method).toBe('manual')
  expect(relation.linked_by).toBe(config.profiles.manager)
  await page.reload()
  await navigate(page, 'Eventos o puntos de atención')
  await page.getByRole('button', { name: 'Abrir evento ' + shortId(event.id), exact: true }).click()
  await expect(dialog).toContainText(report.id)
  expect(await get(page, token, '/municipal/events/' + event.id)).toEqual(event)
  await page.getByRole('button', { name: 'Cerrar Detalle de evento ' + shortId(event.id), exact: true }).click()
  // Existing event/report/photo remain readable as well.
  await page.getByRole('button', { name: 'Abrir evento ' + shortId(original.event), exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Ver fotografías del reporte', exact: true }).click()
  await photoLoaded(page.getByRole('dialog'))
})

test('03 recursos reales disponibilidad sitios turnos y conflicto HTTP 409', async ({ page }) => {
  const token = await login(page)
  await navigate(page, 'Recursos operativos')
  const vehicles = await get(page, token, '/municipal/vehicles')
  for (const v of vehicles) {
    const card = page.locator('.resource-card').filter({ hasText: v.id })
    await expect(card.getByRole('heading', { name: v.label, exact: true })).toBeVisible()
    await expect(card.getByText(v.available ? 'Disponible' : 'No disponible', { exact: true })).toBeVisible()
    if (v.capacity_kg === null) await expect(card).toContainText('Capacidad: No especificada')
  }
  let unavailable = await unique(page, token, '/municipal/vehicles', 'label', vehicleLabel)
  if (!unavailable) {
    await page.getByText('Registrar vehículo', { exact: true }).click()
    await page.getByLabel('Nombre de la unidad', { exact: true }).fill(vehicleLabel)
    await page.getByRole('combobox', { name: 'Tipo de vehículo', exact: true }).selectOption('otro')
    await page.getByLabel('Disponible para programar', { exact: true }).uncheck()
    const before = log.http.filter((r) => r.method === 'POST' && r.path === '/municipal/vehicles').length
    await page.getByRole('button', { name: 'Revisar alta de vehículo', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Crear vehículo ' + vehicleLabel, exact: true })
    await expect(dialog).toBeVisible()
    expect(log.http.filter((r) => r.method === 'POST' && r.path === '/municipal/vehicles').length).toBe(before)
    const confirm = dialog.getByRole('button', { name: 'Confirmar operación', exact: true })
    await expect(confirm).toBeEnabled()
    const saved = page.waitForResponse((r) => r.url() === api + '/municipal/vehicles' && r.request().method() === 'POST')
    await confirm.click()
    const response = await saved; expect(response.status()).toBe(201)
    unavailable = await response.json(); saveFixture('vehicle', unavailable.id)
    await expect(page.getByText('Recurso guardado correctamente.', { exact: true })).toBeVisible()
  }
  saveFixture('vehicle', unavailable.id)
  await expect(page.locator('.resource-card').filter({ hasText: unavailable.id }).getByText('No disponible', { exact: true })).toBeVisible()
  const sites = await get(page, token, '/municipal/sites')
  await page.getByRole('button', { name: 'Sitios', exact: true }).click()
  for (const site of sites) {
    const card = page.locator('article.panel').filter({ hasText: site.id })
    await expect(card.getByRole('heading', { name: site.name, exact: true })).toBeVisible()
    await expect(card).toContainText(`Uso: ${site.site_type}`)
    await expect(card).toContainText(`${site.latitude}, ${site.longitude}`)
  }
  const shifts = await get(page, token, '/municipal/shifts')
  const shift = shifts.find((r) => r.id === original.shift)
  expect(shift).toBeTruthy()
  await page.getByRole('button', { name: 'Turnos', exact: true }).click()
  const card = page.locator('article.panel').filter({ hasText: 'Turno ' + shortId(shift.id) })
  await expect(card).toContainText(shift.driver_id)
  await expect(card).toContainText(vehicles.find((v) => v.id === shift.vehicle_id).label)
  await expect(card).toContainText(sites.find((s) => s.id === shift.departure_site_id).name)
  await expect(card).toContainText(sites.find((s) => s.id === shift.disposal_site_id).name)
  await expect(card).toContainText(datePeru(shift.starts_at))
  await expect(card).toContainText(datePeru(shift.ends_at))
  await page.getByText('Crear jornada o turno', { exact: true }).click()
  const unavailableOption = page.getByLabel('Vehículo para el nuevo turno').locator(`option[value="${unavailable.id}"]`)
  await expect(unavailableOption).toHaveAttribute('disabled', '')
  expect(await unavailableOption.evaluate((option) => option.disabled)).toBe(true)
  await page.getByLabel('Vehículo para el nuevo turno').selectOption(shift.vehicle_id)
  await page.getByLabel('Chofer autorizado').selectOption(shift.driver_id)
  await page.getByLabel('Salida del nuevo turno').selectOption(shift.departure_site_id)
  await page.getByLabel('Descarga del nuevo turno').selectOption(shift.disposal_site_id)
  const date = (value) => new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Lima', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value)).replace(' ', 'T')
  await page.getByLabel('Inicio del turno').fill(date(shift.starts_at))
  await page.getByLabel('Fin del turno').fill(date(shift.starts_at))
  await page.getByRole('button', { name: 'Revisar nuevo turno', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('El fin del turno debe ser posterior al inicio.')
  expect(log.http.filter((r) => r.method === 'POST' && r.path === '/municipal/shifts')).toHaveLength(0)
  await page.getByLabel('Fin del turno').fill(date(shift.ends_at))
  await page.getByRole('button', { name: 'Revisar nuevo turno', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const confirm = dialog.getByRole('button', { name: 'Confirmar operación', exact: true })
  await expect(confirm).toBeEnabled()
  const conflict = page.waitForResponse((r) => r.url() === api + '/municipal/shifts' && r.request().method() === 'POST')
  await confirm.click()
  expect((await conflict).status()).toBe(409)
  await expect(dialog.getByRole('alert')).toContainText(/reservado|superpuest|conflicto/i)
  await expect(page.getByRole('row').filter({ hasText: '/municipal/shifts' }).filter({ hasText: '409' })).toHaveCount(1)
  await page.screenshot({ path: path.join(evidence, 'municipal-turno-conflicto.png'), fullPage: true })
  await dialog.getByRole('button', { name: 'Cancelar', exact: true }).click()
  expect((await get(page, token, '/municipal/shifts')).map((s) => s.id)).toEqual(shifts.map((s) => s.id))
  expect(log.http.filter((r) => r.method === 'POST' && r.path === '/municipal/shifts')).toHaveLength(1)
  await page.reload(); await navigate(page, 'Recursos operativos')
  await expect(page.locator('.resource-card').filter({ hasText: unavailable.id })).toContainText(vehicleLabel)
})

test('04 permisos JWT validaciones y errores reales sin escrituras', async ({ page }) => {
  const token = await login(page, 'citizen')
  await expect(page.getByRole('navigation', { name: 'Navegación municipal' })).toHaveCount(0)
  expect((await request(page, null, '/municipal/events')).status).toBe(401)
  for (const endpoint of ['reports', 'events', 'vehicles', 'sites', 'shifts', 'drivers']) {
    expect((await request(page, token, '/municipal/' + endpoint)).status).toBe(403)
  }
  expect((await request(page, token, '/municipal/events', 'POST', { latitude: -12, longitude: -75, report_ids: [] })).status).toBe(403)
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  const manager = await login(page)
  for (const body of [{ latitude: 91, longitude: -75 }, { latitude: -12, longitude: -181 }, { latitude: -12, longitude: -75, report_ids: ['no-uuid'] }]) {
    expect((await request(page, manager, '/municipal/events', 'POST', body)).status).toBe(422)
  }
  expect((await request(page, manager, '/municipal/events/00000000-0000-4000-8000-000000000000')).status).toBe(404)
  // Original report is already associated: a second association must fail atomically.
  expect((await request(page, manager, '/municipal/events', 'POST', { latitude: -12, longitude: -75, report_ids: [original.report] })).status).toBe(409)
  expect((await request(page, manager, '/municipal/vehicles', 'POST', { label: marker, vehicle_type: 'otro', available: false, capacity_kg: -1 })).status).toBe(422)
})

test('05 carga error de lectura simulado y recuperacion con API real', async ({ page }) => {
  await login(page)
  // Only this test injects a GET failure; never pretends it came from FastAPI.
  let failing = true, delayed = true
  await page.route(api + '/municipal/events?*', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    if (delayed) { await new Promise((resolve) => setTimeout(resolve, 900)); delayed = false }
    if (failing) {
      log.injected.push({ path: '/municipal/events', status: 503, source: 'Playwright UI-only injection' })
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'PRUEBA: servicio temporalmente no disponible' }) })
    }
    return route.continue()
  })
  await navigate(page, 'Eventos o puntos de atención')
  await expect(page.getByText('Consultando información…', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('PRUEBA: servicio temporalmente no disponible')
  failing = false
  await page.getByRole('button', { name: 'Volver a intentar', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Abrir evento ' + shortId(original.event), exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(log.http.some((r) => r.path === '/municipal/events' && r.status === 200)).toBe(true)
  expect(log.http.every((r) => r.method === 'GET')).toBe(true)
})

test('06 celular navegacion siete secciones mapa fotos y cero desborde', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page)
  for (const section of ['Dashboard', 'Reportes ciudadanos', 'Eventos o puntos de atención', 'Revisión de agrupaciones', 'Priorización', 'Planificación de rutas', 'Recursos operativos']) {
    await navigate(page, section)
    await expect(page.locator('.municipal-page h2').first()).toBeVisible()
    // Wait for the actual data instead of taking a layout snapshot during loading.
    await expect(page.getByText('Consultando información…', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Consultando reportes…', { exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), section).toBe(true)
  }
  await navigate(page, 'Reportes ciudadanos')
  const card = page.locator('article.report').filter({ hasText: original.report })
  await card.getByRole('button', { name: 'Ver fotografías', exact: true }).click()
  await photoLoaded(card)
  await page.screenshot({ path: path.join(evidence, 'municipal-reportes-mobile.png'), fullPage: true })
  await navigate(page, 'Eventos o puntos de atención')
  await page.getByRole('button', { name: 'Abrir evento ' + shortId(original.event), exact: true }).click()
  await expect(page.getByRole('dialog').locator('.event-marker')).toHaveCount(1)
  expect(await page.getByRole('dialog').evaluate((e) => e.scrollWidth <= e.clientWidth + 1)).toBe(true)
  await page.screenshot({ path: path.join(evidence, 'municipal-evento-mobile.png'), fullPage: true })
  expect(log.http.every((r) => r.method === 'GET')).toBe(true)
})
