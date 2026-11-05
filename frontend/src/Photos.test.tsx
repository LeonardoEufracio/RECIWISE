import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ApiError, type Api } from './api'
import Photos from './Photos'
import type { Photo } from './types'

afterEach(cleanup)
const photo = (reportId: string): Photo => ({ id: 'photo-' + reportId, report_id: reportId,
  content_type: 'image/png', size_bytes: 10, created_at: '2026-11-04T15:00:00Z',
  signed_url: 'https://storage.invalid/' + reportId + '.png' })
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
async function chooseAndUpload(name = 'photo.png') {
  const input = await screen.findByLabelText(/Fotografía \(JPG/)
  await waitFor(() => expect((input as HTMLInputElement).disabled).toBe(false))
  fireEvent.change(input, { target: { files: [new File([name], name, { type: 'image/png' })] } })
  fireEvent.submit(input.closest('form')!)
}

it('un GET fallido después de POST 201 no presenta el cero anterior como ausencia confirmada', async () => {
  let reads = 0
  const api = vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return photo('new')
    reads++
    if (reads === 1) return []
    if (reads === 2) throw new ApiError('No se pudo acceder a la imagen', 502)
    return [photo('new')]
  })
  render(<Photos api={api as Api} reportId="new" canUpload />)
  await screen.findByText('Este reporte no tiene fotografías.')
  await chooseAndUpload()
  await screen.findByText('Fotografía guardada.')
  await screen.findByRole('alert')
  expect(screen.queryByText('Este reporte no tiene fotografías.')).toBeNull()
  expect(screen.queryByText('Fotografías (0/3)')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Renovar enlaces' }))
  await screen.findByText('Fotografías (1/3)')
  expect(api.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  expect(api.mock.calls.every(([path]) => path === '/reports/new/photos')).toBe(true)
})

it('la lectura tardía de otro reporte no contamina el reporte seleccionado', async () => {
  const old = deferred<Photo[]>()
  const api = vi.fn(async (path: string) => path === '/reports/old/photos' ? old.promise : [])
  const view = render(<Photos api={api as Api} reportId="old" canUpload />)
  view.rerender(<Photos api={api as Api} reportId="new" canUpload />)
  await screen.findByText('Fotografías (0/3)')
  await act(async () => old.resolve([photo('old')]))
  expect(screen.queryByAltText('Fotografía 1 del reporte')).toBeNull()
  expect(screen.getByText('Fotografías (0/3)')).toBeTruthy()
})

it('una lectura anterior del mismo reporte no sobrescribe la renovación más reciente', async () => {
  const slow = deferred<Photo[]>()
  let count = 0
  const api = vi.fn(async () => {
    count++
    if (count === 1) return []
    return count === 2 ? slow.promise : [photo('new')]
  })
  const view = render(<Photos api={api as Api} reportId="new" canUpload />)
  await screen.findByText('Fotografías (0/3)')
  fireEvent.click(screen.getByRole('button', { name: 'Renovar enlaces' }))
  // Effect/API replacement supersedes an in-flight read (as during a remount).
  const latest = vi.fn(async () => [photo('new')])
  view.rerender(<Photos api={latest as Api} reportId="new" canUpload />)
  await screen.findByText('Fotografías (1/3)')
  await act(async () => slow.resolve([]))
  expect(screen.getByText('Fotografías (1/3)')).toBeTruthy()
})

it('una subida iniciada en A mantiene su destino y no refresca ni altera B', async () => {
  const pending = deferred<Photo>()
  const api = vi.fn(async (_path: string, init?: RequestInit) => init?.method === 'POST' ? pending.promise : [])
  const view = render(<Photos api={api as Api} reportId="old" canUpload />)
  await chooseAndUpload('old.png')
  await waitFor(() => expect(api.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
  view.rerender(<Photos api={api as Api} reportId="new" canUpload />)
  await screen.findByText('Fotografías (0/3)')
  const before = api.mock.calls.length
  await act(async () => pending.resolve(photo('old')))
  expect(api.mock.calls.slice(before)).toHaveLength(0)
  expect(api.mock.calls.filter(([, init]) => init?.method === 'POST').map(([path]) => path)).toEqual(['/reports/old/photos'])
  expect(screen.queryByText('Fotografía guardada.')).toBeNull()
})
