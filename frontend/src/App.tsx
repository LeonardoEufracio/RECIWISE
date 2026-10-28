import { useEffect, useMemo, useState, type FormEvent } from 'react'
import type { Session, SupabaseClient } from '@supabase/supabase-js'
import { createApi, type Api } from './api'
import type { PublicConfig } from './config'
import type { Actor, Report, RequestEntry } from './types'
import ReportForm from './ReportForm'
import Reports from './Reports'

function Login({ supabase }: { supabase: SupabaseClient }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    setBusy(true); setError('')
    try {
      const { error: authError } = await supabase.auth.signInWithPassword({
        email: String(fields.get('email')).trim(), password: String(fields.get('password')),
      })
      if (authError) setError(authError.message)
    } catch { setError('No se pudo contactar con Supabase Auth. Revisa la configuración y tu conexión.') }
    finally {
      const input = form.elements.namedItem('password') as HTMLInputElement | null
      if (input) input.value = ''
      setBusy(false)
    }
  }
  return <section className="panel login">
    <h2>Iniciar sesión</h2>
    <p>Usa una cuenta existente de Supabase. FastAPI consultará el rol asociado a tu perfil.</p>
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <label>Correo electrónico<input name="email" type="email" autoComplete="username" required /></label>
        <label>Contraseña<input name="password" type="password" autoComplete="current-password" required /></label>
        <button>{busy ? 'Iniciando sesión…' : 'Entrar'}</button>
      </fieldset>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
  </section>
}

function Workspace({ api }: { api: Api }) {
  const [actor, setActor] = useState<Actor | null>(null)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(true)
  const [reload, setReload] = useState(0)
  const [revision, setRevision] = useState(0)
  const [createdReportId, setCreatedReportId] = useState<string>()
  useEffect(() => {
    let active = true
    setActor(null); setError(''); setChecking(true)
    void api<Actor>('/me')
      .then((data) => { if (active) setActor(data) })
      .catch((err: Error) => { if (active) setError(err.message) })
      .finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [api, reload])

  function created(report: Report) { setCreatedReportId(report.id); setRevision((value) => value + 1) }

  return <>
    <section className="panel">
      <div className="toolbar">
        <h2>Perfil de FastAPI</h2>
        <button type="button" disabled={checking} onClick={() => setReload((value) => value + 1)}>Consultar /me</button>
      </div>
      {checking && <p role="status">Consultando identidad y permisos…</p>}
      {actor && <p>Rol: <strong>{actor.role}</strong> · ID: <span className="identifier">{actor.id}</span></p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
    {actor?.role === 'ciudadano' && <>
      <ReportForm api={api} onCreated={created} />
      <Reports api={api} municipal={false} revision={revision} createdReportId={createdReportId} />
    </>}
    {actor?.role === 'encargado_municipal' && <Reports api={api} municipal />}
    {actor?.role === 'chofer' && <p className="panel">La cuenta tiene rol chofer. Este frontend de pruebas cubre las operaciones de ciudadano y encargado municipal.</p>}
  </>
}

function Diagnostics({ api, apiUrl, entries, clear }: {
  api: Api; apiUrl: string; entries: RequestEntry[]; clear: () => void
}) {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function health() {
    setBusy(true); setMessage('')
    try {
      const result = await api<{ status: string; version: string }>('/health', {}, false)
      setMessage(`API: ${result.status} · versión ${result.version}. /health comprueba el proceso, no la base de datos.`)
    } catch (err) { setMessage((err as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="panel">
    <div className="toolbar">
      <h2>Comunicación con FastAPI</h2>
      <div className="actions">
        <button type="button" onClick={() => void health()} disabled={busy || !apiUrl}>Comprobar /health</button>
        <button type="button" onClick={clear}>Limpiar historial</button>
      </div>
    </div>
    <p className="hint">API: {apiUrl || 'sin configurar'} · Últimas 50 peticiones de esta pestaña. «Sin HTTP» indica que no se recibió una respuesta HTTP legible.</p>
    {message && <p role="status">{message}</p>}
    <div className="table-scroll"><table>
      <thead><tr><th>Hora</th><th>Método</th><th>Ruta</th><th>HTTP</th><th>Duración</th></tr></thead>
      <tbody>{entries.map((entry) => <tr key={entry.id}>
        <td>{new Date(entry.time).toLocaleTimeString('es-PE')}</td><td>{entry.method}</td><td className="identifier">{entry.path}</td>
        <td className={entry.status !== null && entry.status < 400 ? 'success' : 'error'}>{entry.status ?? 'Sin HTTP'}</td><td>{entry.duration} ms</td>
      </tr>)}</tbody>
    </table></div>
    {!entries.length && <p>Aún no hay peticiones registradas.</p>}
  </section>
}

export default function App({ supabase, config, configErrors = [] }: {
  supabase: SupabaseClient | null; config: PublicConfig; configErrors?: string[]
}) {
  const [session, setSession] = useState<Session | null>(null)
  const [initializing, setInitializing] = useState(Boolean(supabase))
  const [authError, setAuthError] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [entries, setEntries] = useState<RequestEntry[]>([])

  const api = useMemo(() => createApi({
    baseUrl: config.apiUrl,
    getAccessToken: async () => {
      if (!supabase) return null
      const { data, error } = await supabase.auth.getSession()
      if (error) return null
      return data.session?.access_token ?? null
    },
    onRequest: (entry) => setEntries((current) => [entry, ...current].slice(0, 50)),
  }), [supabase, config.apiUrl])

  useEffect(() => {
    if (!supabase) return
    let active = true
    let receivedEvent = false
    // El callback permanece síncrono para no bloquear el candado interno de Auth.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      receivedEvent = true
      if (active) { setSession(nextSession); setInitializing(false) }
    })
    void supabase.auth.getSession().then(({ data, error }) => {
      if (!active) return
      if (error) setAuthError(error.message)
      if (!receivedEvent) setSession(data.session)
      setInitializing(false)
    }).catch(() => {
      if (active) { setAuthError('No se pudo recuperar la sesión. Intenta iniciar sesión otra vez.'); setInitializing(false) }
    })
    return () => { active = false; subscription.unsubscribe() }
  }, [supabase])

  async function logout() {
    setSigningOut(true); setAuthError('')
    try {
      const { error } = await supabase!.auth.signOut({ scope: 'local' })
      if (error) setAuthError(error.message)
      else { setSession(null); setEntries([]) }
    } catch { setAuthError('No se pudo cerrar la sesión. Intenta nuevamente.') }
    finally { setSigningOut(false) }
  }

  return <main>
    <header>
      <div><h1>RECIWISE</h1><p>Pruebas de reportes ciudadanos y consulta municipal</p></div>
      {session && <div className="session"><span>{session.user.email}</span><button type="button" disabled={signingOut} onClick={() => void logout()}>Cerrar sesión</button></div>}
    </header>
    {configErrors.length > 0 && <section className="panel" role="alert">
      <h2>Configura el frontend</h2>
      <p>Copia <code>frontend/.env.example</code> a <code>frontend/.env.local</code>, completa sus tres variables y reinicia Vite.</p>
      <ul>{configErrors.map((error) => <li key={error}>{error}</li>)}</ul>
    </section>}
    {authError && <p className="error" role="alert">{authError}</p>}
    {initializing ? <p role="status">Recuperando sesión…</p> : supabase && (session
      ? <Workspace key={session.user.id} api={api} />
      : <Login supabase={supabase} />)}
    <Diagnostics api={api} apiUrl={config.apiUrl} entries={entries} clear={() => setEntries([])} />
  </main>
}
