import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createClient } from '@supabase/supabase-js'
import App from './App'
import { readConfig } from './config'
import 'leaflet/dist/leaflet.css'
import './styles.css'

const { config, errors } = readConfig(import.meta.env)
const supabase = errors.length ? null : createClient(config.supabaseUrl, config.publishableKey, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode><App supabase={supabase} config={config} configErrors={errors} /></StrictMode>,
)
