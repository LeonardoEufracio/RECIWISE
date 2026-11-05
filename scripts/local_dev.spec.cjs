const { createRequire } = require('node:module')
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..')
const { test, expect } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test')
const config = JSON.parse(fs.readFileSync(path.join(root, '.localdev/config.json'), 'utf8'))
const credentials = JSON.parse(fs.readFileSync(path.join(root, '.localdev/credentials.json'), 'utf8'))
const fixtures = JSON.parse(fs.readFileSync(path.join(root, '.localdev/check-data.json'), 'utf8'))
const api = 'http://127.0.0.1:' + config.ports.api
const auth = 'http://127.0.0.1:' + config.ports.auth
const ui = 'http://127.0.0.1:' + config.ports.ui
const shortId = (id) => id.slice(0, 4) + '…' + id.slice(-4)
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')

test('React con FastAPI/PostgreSQL persistente: perfiles, fotos, eventos, historial y propuestas', async ({ page, context }) => {
  const external = []; const http = []; const errors = []
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (/^[abc]\.tile\.openstreetmap\.org$/.test(url.hostname)) return route.fulfill({ contentType: 'image/png', body: png })
    if ([api, auth, ui].includes(url.origin)) return route.continue()
    external.push(url.origin); return route.abort('blockedbyclient')
  })
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('response', (response) => {
    if (new URL(response.url()).origin === api) http.push({ method: response.request().method(), path: new URL(response.url()).pathname, status: response.status() })
  })
  async function login(name) {
    await page.goto('/')
    await page.getByLabel('Correo electrónico').fill(name + '@example.test')
    await page.getByLabel('Contraseña', { exact: true }).fill(credentials.auth_password)
    await page.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(page.locator('strong').filter({ hasText: name === 'citizen' ? /^ciudadano$/ : /^encargado_municipal$/ })).toBeVisible()
  }
  await login('citizen')
  await expect(page.getByRole('navigation', { name: 'Navegación municipal' })).toHaveCount(0)
  const article = page.locator('article').filter({ hasText: fixtures.report })
  await article.getByRole('button', { name: 'Ver fotografías', exact: true }).click()
  const image = article.getByAltText('Fotografía 1 del reporte')
  await expect(async () => {
    await image.scrollIntoViewIfNeeded()
    expect(await image.evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true)
  }).toPass({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
  await login('manager')
  await page.getByRole('button', { name: 'Eventos o puntos de atención', exact: true }).click()
  await page.getByRole('button', { name: 'Abrir evento ' + shortId(fixtures.event), exact: true }).click()
  await expect(page.getByRole('dialog').getByText('LOCALDEV: reporte ficticio persistente de verificación', { exact: true })).toBeVisible()
  await expect(page.getByRole('dialog').locator('.event-marker')).toHaveCount(1)
  await expect(page.getByRole('dialog').locator('path.leaflet-interactive')).toHaveCount(1)
  await page.getByRole('button', { name: 'Cerrar Detalle de evento ' + shortId(fixtures.event), exact: true }).click()
  await page.getByRole('button', { name: 'Revisión de agrupaciones', exact: true }).click()
  await page.getByRole('button', { name: 'Revisar relación ' + shortId(fixtures.report), exact: true }).click()
  await expect(page.getByLabel('Evento candidato')).toBeVisible()
  await page.getByRole('button', { name: 'Ver decisión ' + shortId(fixtures.decision), exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Detalle de decisión' })).toContainText(fixtures.decision)
  await page.getByRole('button', { name: 'Cerrar Detalle de decisión', exact: true }).click()
  await page.getByRole('button', { name: 'Planificación de rutas', exact: true }).click()
  await page.getByRole('button', { name: 'Abrir propuesta ' + shortId(fixtures.proposal), exact: true }).click()
  await expect(page.getByRole('dialog').getByText(/Pendiente de cálculo · NO OPERATIVA/)).toBeVisible()
  await expect(page.getByRole('dialog').getByText('No hay paradas en esta página', { exact: true })).toBeVisible()
  await page.screenshot({ path: path.join(process.env.RECIWISE_LOCAL_DEV_EVIDENCE, 'react-local.png'), fullPage: true })
  expect(external).toEqual([]); expect(errors).toEqual([])
  expect(http.some((r) => r.method !== 'GET')).toBe(false)
  for (const route of ['/me', '/municipal/events', '/municipal/events/' + fixtures.event + '/reports', '/municipal/groupings',
    '/municipal/groupings/reports/' + fixtures.report, '/municipal/groupings/candidates', '/municipal/groupings/decisions',
    '/municipal/groupings/decisions/' + fixtures.decision, '/municipal/route-proposals',
    '/municipal/route-proposals/' + fixtures.proposal + '/stops', '/municipal/route-proposals/' + fixtures.proposal + '/excluded-events']) {
    expect(http.some((r) => r.path === route && r.status === 200)).toBe(true)
  }
  fs.writeFileSync(path.join(process.env.RECIWISE_LOCAL_DEV_EVIDENCE, 'browser-http.json'), JSON.stringify({ http, external, errors }, null, 2))
})
