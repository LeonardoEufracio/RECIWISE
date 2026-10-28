import { useCallback, useEffect, useState, type FormEvent } from 'react'
import type { Api } from './api'
import type { Photo } from './types'

function PhotoImage({ photo, index }: { photo: Photo; index: number }) {
  const [failed, setFailed] = useState(false)
  const url = photo.signed_url
  if (!url || !/^https?:\/\//.test(url) || failed) return <p>Foto {index + 1} no disponible. Renueva los enlaces para volver a cargarla.</p>
  return <a href={url} target="_blank" rel="noreferrer" referrerPolicy="no-referrer">
    <img src={url} alt={`Fotografía ${index + 1} del reporte`} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
  </a>
}

export default function Photos({ api, reportId, canUpload }: { api: Api; reportId: string; canUpload: boolean }) {
  const [photos, setPhotos] = useState<Photo[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [version, setVersion] = useState(0)
  const path = `/reports/${reportId}/photos`

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try { setPhotos(await api<Photo[]>(path)); setVersion((value) => value + 1) }
    catch (err) { setError((err as Error).message) }
    finally { setLoading(false) }
  }, [api, path])
  useEffect(() => { void load() }, [load])

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const file = (form.elements.namedItem('file') as HTMLInputElement).files?.[0]
    setError(''); setMessage('')
    if (!(file instanceof File) || !file.size) { setError('Selecciona una fotografía.'); return }
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setError('Solo se admite JPG, PNG o WebP.'); return }
    if (file.size > 5 * 1024 * 1024) { setError('La fotografía supera 5 MB.'); return }
    if ((photos?.length ?? 0) >= 3) { setError('El reporte ya tiene el máximo de 3 fotografías.'); return }
    const body = new FormData()
    body.append('file', file)
    setUploading(true)
    try {
      await api<Photo>(path, { method: 'POST', body })
      form.reset()
      setMessage('Fotografía guardada.')
      await load()
    } catch (err) { setError((err as Error).message) }
    finally { setUploading(false) }
  }

  return <section className="photos" aria-label="Fotografías del reporte">
    <div className="toolbar">
      <strong>Fotografías {photos ? `(${photos.length}/3)` : ''}</strong>
      <button type="button" onClick={() => void load()} disabled={loading || uploading}>Renovar enlaces</button>
    </div>
    <p className="hint">Los enlaces de lectura vencen a los 5 minutos.</p>
    {loading && <p role="status">Cargando fotografías…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p className="success" role="status">{message}</p>}
    {photos?.length === 0 && <p>Este reporte no tiene fotografías.</p>}
    <div className="photo-grid">{photos?.map((photo, index) => <PhotoImage key={`${photo.id}-${version}`} photo={photo} index={index} />)}</div>
    {canUpload && <form onSubmit={upload}>
      <label>Fotografía (JPG, PNG o WebP; hasta 5 MB)
        <input name="file" type="file" accept="image/jpeg,image/png,image/webp" required disabled={uploading || loading || photos === null || photos.length >= 3} />
      </label>
      <button disabled={uploading || loading || photos === null || photos.length >= 3}>{uploading ? 'Subiendo…' : 'Subir fotografía'}</button>
    </form>}
  </section>
}
