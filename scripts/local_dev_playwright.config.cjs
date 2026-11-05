const { createRequire } = require('node:module')
const path = require('node:path')
const fs = require('node:fs')
const root = path.resolve(__dirname, '..')
const { defineConfig } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test')
const config = JSON.parse(fs.readFileSync(path.join(root, '.localdev/config.json'), 'utf8'))
const artifact = path.resolve(process.env.RECIWISE_LOCAL_DEV_EVIDENCE || '')
if (!artifact.startsWith(path.join(root, '.test-artifacts/local-dev') + path.sep)) throw new Error('Run scripts/check_local_dev.py')
module.exports = defineConfig({
  testDir: __dirname, testMatch: 'local_dev.spec.cjs', workers: 1, retries: 0, timeout: 90_000,
  expect: { timeout: 15_000 }, reporter: [['list'], ['junit', { outputFile: path.join(artifact, 'browser.xml') }]],
  outputDir: path.join(artifact, 'browser-output'),
  use: { baseURL: 'http://127.0.0.1:' + config.ports.ui, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    headless: true, trace: 'off', video: 'off', screenshot: 'off' },
})
