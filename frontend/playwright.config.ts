import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    browserName: 'chromium',
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    headless: true,
  },
  // El backend debe iniciarse aparte. Las pruebas solo hacen lecturas reales
  // de /health y /me sin token; Auth y los datos de negocio se interceptan.
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: false,
    env: {
      VITE_API_URL: 'http://127.0.0.1:8000',
      VITE_SUPABASE_URL: 'https://frontend-test.supabase.co',
      VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_browser_test',
    },
  },
})
