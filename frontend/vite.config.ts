import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Coincide con CORS_ORIGINS del backend. No cambiar de puerto silenciosamente.
  server: { host: 'localhost', port: 5173, strictPort: true },
  preview: { host: 'localhost', port: 5173, strictPort: true },
  test: { include: ['src/**/*.test.{ts,tsx}'], environment: 'jsdom', restoreMocks: true, clearMocks: true },
})
