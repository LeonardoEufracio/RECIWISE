import { describe, expect, it } from 'vitest'
import { reportPayload } from './reportPayload'
import { readConfig } from './config'

function formWith(overrides: Record<string, string> = {}) {
  const form = document.createElement('form')
  const fields = { description: '  Residuos en la esquina  ', latitude: '-12.05', longitude: '-75.2', observed_at: '2026-01-01T10:30', waste_type: '', ...overrides }
  for (const [name, value] of Object.entries(fields)) {
    const input = document.createElement('input')
    input.name = name; input.value = value; form.append(input)
  }
  return form
}

describe('Contrato ReportCreate', () => {
  it('envía coordenadas numéricas, fecha con zona y waste_type opcional', () => {
    const payload = reportPayload(formWith())
    expect(payload.description).toBe('Residuos en la esquina')
    expect(payload.latitude).toBe(-12.05)
    expect(payload.longitude).toBe(-75.2)
    expect(payload.observed_at).toMatch(/Z$/)
    expect(payload.waste_type).toBeNull()
    expect(payload).not.toHaveProperty('role')
    expect(payload).not.toHaveProperty('citizen_id')
  })
  it.each([
    { latitude: '' }, { latitude: '91' }, { longitude: '-181' },
    { description: '  ' }, { observed_at: 'fecha inválida' },
    { observed_at: '2999-01-01T12:00' },
  ] as Record<string, string>[])('rechaza entradas que el backend no admite: %j', (invalid) => {
    expect(() => reportPayload(formWith(invalid))).toThrow()
  })
})

describe('Configuración pública', () => {
  const env = { VITE_API_URL: 'http://127.0.0.1:8000/', VITE_SUPABASE_URL: 'https://project.supabase.co', VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_clave-publica' }
  it('acepta las tres variables y normaliza la URL', () => {
    const result = readConfig(env)
    expect(result.errors).toEqual([])
    expect(result.config.apiUrl).toBe('http://127.0.0.1:8000')
  })
  it.each(['sb_secret_clave', 'service_role', 'eyJhbGciOiJIUzI1NiJ9.payload.signature', 'sb_publishable_<PUBLIC_KEY>'])('rechaza claves privadas o inválidas: %s', (key) => {
    expect(readConfig({ ...env, VITE_SUPABASE_PUBLISHABLE_KEY: key }).errors.length).toBeGreaterThan(0)
  })
  it('explica las tres variables faltantes sin mostrar valores', () => {
    expect(readConfig({}).errors).toHaveLength(3)
  })
})
