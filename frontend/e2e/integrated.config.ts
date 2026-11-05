import { defineConfig } from '@playwright/test'
import path from 'node:path'

function local(name: string) {
  const value = process.env[name] || ''
  const url = new URL(value)
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port) {
    throw new Error('Isolated local integration runner required')
  }
  return value
}
const artifact = path.resolve(process.env.RECIWISE_INTEGRATED_ARTIFACT || '')
const allowed = path.resolve('..', '.test-artifacts') + path.sep
if (!artifact.startsWith(allowed) || !process.env.RECIWISE_ISOLATED_TOKEN) {
  throw new Error('Run tests/run_isolated_postgres.py --phase integrated')
}
local('RECIWISE_INTEGRATED_API_URL')
local('RECIWISE_INTEGRATED_SERVICES_URL')

export default defineConfig({
  testDir: './integrated',
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['junit', { outputFile: path.join(artifact, 'browser-junit.xml') }]],
  outputDir: path.join(artifact, 'browser-output'),
  use: {
    baseURL: local('RECIWISE_INTEGRATED_UI_URL'),
    browserName: 'chromium',
    channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    headless: true,
    trace: 'off', video: 'off', screenshot: 'off', // No stored Authorization/session bodies.
  },
})
