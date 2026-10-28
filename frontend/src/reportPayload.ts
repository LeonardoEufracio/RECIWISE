import type { ReportCreate } from './types'

export function localDateTime(): string {
  const date = new Date()
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

export function reportPayload(form: HTMLFormElement): ReportCreate {
  const data = new FormData(form)
  const description = String(data.get('description') ?? '').trim()
  const latitudeText = String(data.get('latitude') ?? '').trim()
  const longitudeText = String(data.get('longitude') ?? '').trim()
  const latitude = Number(latitudeText)
  const longitude = Number(longitudeText)
  const observed = new Date(String(data.get('observed_at') ?? ''))
  const wasteType = String(data.get('waste_type') ?? '').trim()
  if (description.length < 3 || description.length > 2000) throw new Error('La descripción debe tener entre 3 y 2000 caracteres.')
  if (!latitudeText || !Number.isFinite(latitude) || latitude < -90 || latitude > 90) throw new Error('Latitud inválida (−90 a 90).')
  if (!longitudeText || !Number.isFinite(longitude) || longitude < -180 || longitude > 180) throw new Error('Longitud inválida (−180 a 180).')
  if (Number.isNaN(observed.getTime()) || observed.getTime() > Date.now() + 5 * 60_000) throw new Error('La fecha de observación es inválida o está en el futuro.')
  if (wasteType.length > 80) throw new Error('El tipo de residuo admite hasta 80 caracteres.')
  return { description, latitude, longitude, observed_at: observed.toISOString(), waste_type: wasteType || null }
}
