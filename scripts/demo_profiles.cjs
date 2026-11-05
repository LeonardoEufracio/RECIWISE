// Test/demo launcher only. Credentials stay in process memory; never bundled by Vite.
const { createRequire } = require('node:module')
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..')
const { chromium, expect } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test')
const artifact = path.resolve(process.env.RECIWISE_TEST_EVIDENCE_DIR || '')
const token = process.env.RECIWISE_ISOLATED_TOKEN || ''
if (!/^[a-f0-9]{32}$/.test(token) || artifact !== path.join(root, '.test-artifacts/reciwise-d2-test-' + token)
  || !process.env.RECIWISE_DEMO_CONTAINER_ID) throw new Error('Disposable demo parent required')
const fixtures = JSON.parse(process.env.RECIWISE_DEMO_FIXTURES || '{}')
const ui = process.env.RECIWISE_DEMO_UI, api = process.env.RECIWISE_DEMO_API, services = process.env.RECIWISE_DEMO_SERVICES
for (const target of [ui, api, services]) {
  const url = new URL(target)
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port) throw new Error('Local demo required')
}
const png = fs.readFileSync(path.join(artifact, 'DEMO-imagen-tecnica.png'))
const shortId = (id) => id.slice(0, 4) + '…' + id.slice(-4)
const results = { roles: [], pageErrors: [], consoleErrors: [], external: [], http: [], mutations: [] }
let browser
async function navigate(page, section) {
  const menu = page.getByRole('button', { name: 'Abrir navegación', exact: true })
  if (await menu.isVisible()) await menu.click()
  await page.getByRole('navigation', { name: 'Navegación municipal' }).getByRole('button', { name: section, exact: true }).click()
}
async function run() {
  const check = process.env.RECIWISE_DEMO_CHECK === '1'
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless: check })
  const pages = []
  for (const [actor, role] of [['citizen', 'ciudadano'], ['manager', 'encargado_municipal'], ['driver', 'chofer']]) {
    const context = await browser.newContext({ viewport: actor === 'manager' ? { width: 1280, height: 900 } : { width: 390, height: 844 }, timezoneId: 'America/Lima' })
    context.setDefaultTimeout(15_000)
    await context.route('**/*', (route) => {
      const url = new URL(route.request().url())
      if (/^[abc]\.tile\.openstreetmap\.org$/.test(url.hostname)) return route.fulfill({ contentType: 'image/png', body: png })
      if ([ui, api, services].includes(url.origin)) return route.continue()
      results.external.push(url.origin); return route.abort('blockedbyclient')
    })
    const page = await context.newPage(); pages.push(page)
    page.on('pageerror', (error) => results.pageErrors.push({ actor, message: error.message }))
    page.on('console', (m) => { if (m.type() === 'error') results.consoleErrors.push({ actor, message: m.text() }) })
    page.on('response', (r) => {
      if (new URL(r.url()).origin === api) {
        results.http.push({ actor, method: r.request().method(), path: new URL(r.url()).pathname, status: r.status() })
        if (r.request().method() !== 'GET') results.mutations.push({ actor, path: new URL(r.url()).pathname, status: r.status() })
      }
    })
    await page.goto(ui)
    await page.getByLabel('Correo electrónico').fill(actor + '@example.test')
    await page.getByLabel('Contraseña', { exact: true }).fill(process.env.RECIWISE_DEMO_PASSWORD)
    await page.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(page.locator('strong').filter({ hasText: new RegExp('^' + role + '$') })).toBeVisible()
    if (actor === 'citizen') {
      await expect(page.getByRole('button', { name: 'Registrar reporte', exact: true })).toBeDisabled()
      const card = page.locator('article.report').filter({ hasText: fixtures.report })
      await expect(card).toContainText('DEMO FICTICIA: reporte inicial con fotografía')
      await card.getByRole('button', { name: 'Ver fotografías', exact: true }).click()
      const image = card.getByAltText('Fotografía 1 del reporte')
      await expect(async () => {
        await image.scrollIntoViewIfNeeded()
        expect(await image.evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true)
      }).toPass({ timeout: 15_000 })
      await expect(card.getByText('Pendiente', { exact: true })).toBeVisible()
      await page.screenshot({ path: path.join(artifact, 'demo-citizen-mobile.png'), fullPage: false })
      await page.getByRole('heading', { name: 'Registrar acumulación de basura', exact: true }).scrollIntoViewIfNeeded()
    } else if (actor === 'manager') {
      await expect(page.getByText('Modo real', { exact: true })).toBeVisible()
      await navigate(page, 'Planificación de rutas')
      await page.getByRole('button', { name: 'Decisiones e historial', exact: true }).click()
      await page.getByRole('button', { name: 'Revisar ruta ' + shortId(fixtures.proposals.reject), exact: true }).click()
      const dialog = page.getByRole('dialog')
      await expect(dialog.getByRole('button', { name: 'Aprobar y asignar (proveedor pendiente)', exact: true })).toBeDisabled()
      await dialog.screenshot({ path: path.join(artifact, 'demo-manager-approval-blocked.png') })
      await page.getByRole('button', { name: 'Cerrar Revisión municipal de ruta ' + shortId(fixtures.proposals.reject), exact: true }).click()
      await navigate(page, 'Reportes ciudadanos')
      await expect(page.locator('article.report').filter({ hasText: fixtures.report })).toBeVisible()
    } else {
      await page.getByRole('button', { name: 'Abrir mi recorrido ' + shortId(fixtures.driver_route), exact: true }).click()
      await expect(page.locator('.route-map .route-stop')).toHaveCount(3)
      await expect(page.getByRole('button', { name: 'Revisar inicio de recorrido', exact: true })).toBeVisible()
      await page.getByText('Limitaciones del resultado', { exact: true }).click()
      await expect(page.getByText('No demuestra aprobación real ni verificación de D3. Sin optimizador ni matriz vial.', { exact: true })).toBeVisible()
      await page.screenshot({ path: path.join(artifact, 'demo-driver-mobile-ready.png'), fullPage: false })
    }
    if (actor !== 'manager') expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    results.roles.push({ actor, role, ready: true })
    console.log('Demo session ready: ' + actor + '@example.test (' + role + ')')
  }
  expect(results.pageErrors).toEqual([]); expect(results.external).toEqual([])
  expect(results.consoleErrors).toEqual([])
  expect(results.mutations).toEqual([]) // Initial windows only read business data.
  fs.writeFileSync(path.join(artifact, 'demo-ready.json'), JSON.stringify({ roles: results.roles, ui, api, fictitious: true }, null, 2))
  if (!check) {
    console.log('DEMO READY. Three separate sessions; all records and the driver authorization are fictitious.')
    while (!fs.existsSync(path.join(artifact, 'demo.stop')) && browser.isConnected() && pages.some((p) => !p.isClosed())) {
      await new Promise((resolve) => setTimeout(resolve, 200))
    }
  }
  return 0
}
run().then((code) => { process.exitCode = code }).catch(() => {
  console.error('Demo browser failed safely; inspect readiness without publishing credentials.')
  process.exitCode = 1
}).finally(async () => {
  fs.writeFileSync(path.join(artifact, 'demo-browser.json'), JSON.stringify(results, null, 2))
  await browser?.close()
})
