import { defineConfig } from '@playwright/test'

// Build first using the fictitious public environment documented in FRONTEND_SPRINT2.md.
export default defineConfig({
  testDir: './e2e/production',
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://localhost:5174', browserName: 'chromium', channel: process.env.PLAYWRIGHT_CHANNEL || undefined, headless: true },
  webServer: { command: 'npm run preview -- --port 5174', url: 'http://localhost:5174', reuseExistingServer: false },
})
