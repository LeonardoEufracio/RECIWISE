export interface PublicConfig { apiUrl: string; supabaseUrl: string; publishableKey: string }

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
      && !url.search && !url.hash && !/[<>]/.test(value)
  } catch { return false }
}

export function readConfig(env: Record<string, string | undefined>) {
  const config: PublicConfig = {
    apiUrl: (env.VITE_API_URL ?? '').trim().replace(/\/+$/, ''),
    supabaseUrl: (env.VITE_SUPABASE_URL ?? '').trim().replace(/\/+$/, ''),
    publishableKey: (env.VITE_SUPABASE_PUBLISHABLE_KEY ?? '').trim(),
  }
  const errors: string[] = []
  if (!isHttpUrl(config.apiUrl)) errors.push('Configura VITE_API_URL con la URL HTTP de FastAPI.')
  if (!isHttpUrl(config.supabaseUrl)) errors.push('Configura VITE_SUPABASE_URL con la URL de tu proyecto.')
  if (!/^sb_publishable_[A-Za-z0-9_-]+$/.test(config.publishableKey)) {
    errors.push('VITE_SUPABASE_PUBLISHABLE_KEY debe ser la clave pública sb_publishable_… del proyecto; no uses service_role ni sb_secret_.')
  }
  return { config, errors }
}
