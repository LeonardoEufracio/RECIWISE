// Uses the existing React/Vite config, with .env loading disabled for this launcher.
import { pathToFileURL } from 'node:url'
import path from 'node:path'
const frontend = process.cwd()
const { createServer } = await import(pathToFileURL(path.join(frontend, 'node_modules/vite/dist/node/index.js')).href)
const server = await createServer({
  configFile: path.join(frontend, 'vite.config.ts'),
  envDir: false,
  server: { host: '127.0.0.1', port: Number(process.argv[2]), strictPort: true },
})
await server.listen()
