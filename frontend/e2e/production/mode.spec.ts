import { expect, test } from '@playwright/test'

test('producción: VITE_ENABLE_DEMO=true no habilita demostración ni decisiones ficticias', async ({ page }) => {
  const expiry = Math.floor(Date.now() / 1000) + 3600
  const token = Buffer.from('{"alg":"HS256","typ":"JWT"}').toString('base64url') + '.' + Buffer.from(JSON.stringify({ sub: 'prod-fixture', exp: expiry })).toString('base64url') + '.ui-only'
  const unexpected: string[] = []
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url())
    if (url.origin === 'http://localhost:5174') return route.continue()
    if (url.origin === 'https://frontend-test.supabase.co') return route.fulfill({ json: {
      access_token: token, refresh_token: 'fictitious-refresh', token_type: 'bearer', expires_in: 3600, expires_at: expiry,
      user: { id: 'prod-fixture', aud: 'authenticated', role: 'authenticated', email: 'prod@example.test', app_metadata: {}, user_metadata: {}, created_at: '2026-10-30T00:00:00Z' },
    } })
    if (url.origin === 'http://127.0.0.1:8000' && url.pathname === '/me') return route.fulfill({ json: { id: 'prod-fixture', role: 'encargado_municipal' } })
    if (url.origin === 'http://127.0.0.1:8000' && url.pathname === '/municipal/reports') return route.fulfill({ json: [] })
    if (url.origin === 'http://127.0.0.1:8000' && url.pathname === '/municipal/groupings') return route.fulfill({ json: [] })
    unexpected.push(url.origin + url.pathname); return route.abort()
  })
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill('prod@example.test')
  await page.getByLabel('Contraseña', { exact: true }).fill('fixture-only')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByText('Aún no hay reportes', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Explorar demostración', exact: true })).toHaveCount(0)
  await expect(page.getByText('DATOS SIMULADOS — DEMOSTRACIÓN', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Revisión de agrupaciones', exact: true }).click()
  await expect(page.getByText('No hay reportes para revisar con este filtro', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirmar agrupación', exact: true })).toHaveCount(0)
  expect(unexpected).toEqual([])
})
