import type { ReportCreate, ReportLocation } from './types'

export function localDateTime(): string {
  const date = new Date()
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

export function reportPayload(form: HTMLFormElement, location: ReportLocation | null): ReportCreate {
  const data = new FormData(form)
  const description = String(data.get('description') ?? '').trim()
  const observed = new Date(String(data.get('observed_at') ?? ''))
  const wasteType = String(data.get('waste_type') ?? '').trim()
  if (description.length < 3 || description.length > 2000) throw new Error('La descripción debe tener entre 3 y 2000 caracteres.')
  if (!location?.confirmed) throw new Error('Selecciona y confirma la ubicación del reporte antes de enviarlo.')
  const { latitude, longitude } = location
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90
    || !Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
    throw new Error('La ubicación seleccionada no es válida. Vuelve a elegirla en el mapa.')
  }
  if (Number.isNaN(observed.getTime()) || observed.getTime() > Date.now() + 5 * 60_000) throw new Error('La fecha de observación es inválida o está en el futuro.')
  if (wasteType.length > 80) throw new Error('El tipo de residuo admite hasta 80 caracteres.')
  return { description, latitude, longitude, observed_at: observed.toISOString(), waste_type: wasteType || null }
}
