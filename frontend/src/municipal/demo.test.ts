import { describe, expect, it } from 'vitest'
import { decideDemo, initialDemo, proposeDemo, validatePlanning } from './demo'
import type { PlanningInput } from './model'
import { datePeru, numberText } from '../format'

function planning(): PlanningInput {
  const d = initialDemo(); const s = d.shifts[0]
  return { shift_id: s.id, vehicle_id: s.vehicle_id, driver_id: s.driver_id, departure_site_id: s.departure_site_id, disposal_site_id: s.disposal_site_id, event_ids: d.events.slice(0, 2).map((e) => e.id) }
}
describe('Transiciones explícitas de la demostración, sin IA ni persistencia', () => {
  it('cada sesión recibe un conjunto independiente', () => { const a = initialDemo(); a.reports.pop(); expect(initialDemo().reports).toHaveLength(4) })
  it('agrupar relaciona sin marcar como atendido ni modificar el conjunto original', () => {
    const original = initialDemo(); const s = original.suggestions[0]
    const next = decideDemo(original, s.id, 'agrupar', '  Verificado en demostración  ')
    expect(next.events[0].report_ids).toContain(s.reporte_nuevo_id)
    expect(original.events[0].report_ids).not.toContain(s.reporte_nuevo_id)
    expect(next.reports).toEqual(original.reports)
    expect(next.decisions[0].notes).toBe('Verificado en demostración')
    expect(() => decideDemo(next, s.id, 'agrupar', '')).toThrow('ya tiene una decisión')
  })
  it.each(['mantener_separado', 'revisar'] as const)('%s registra auditoría local sin alterar relaciones', (kind) => {
    const d = initialDemo(); const next = decideDemo(d, d.suggestions[0].id, kind, 'Ejemplo')
    expect(next.events).toEqual(d.events); expect(next.decisions[0].decision).toBe(kind)
  })
  it('rechaza agrupar en eventos cerrados', () => {
    const d = initialDemo(); expect(() => decideDemo(d, d.suggestions[2].id, 'agrupar', '')).toThrow('cerrado')
  })
  it('genera únicamente una propuesta local sin estimaciones inventadas', () => {
    const d = initialDemo(); const value = planning(); const p = proposeDemo(d, value).proposals[0]
    expect(d.proposals).toHaveLength(0); expect(p.status).toBe('propuesta')
    expect(p.stops.map((s) => s.event_id)).toEqual(value.event_ids)
    expect(p.distance_m).toBeNull(); expect(p.duration_seconds).toBeNull(); expect(p.matrix_source).toBeNull()
    expect(p.excluded[0].reason).toBe('Evento cerrado')
    expect(p.geometry?.type).toBe('LineString')
  })
  it('no dibuja líneas inventadas para otra selección de eventos', () => {
    const d = initialDemo(); const value = planning(); value.event_ids.reverse()
    expect(proposeDemo(d, value).proposals[0].geometry).toBeNull()
  })
  it('la capacidad desconocida permanece nula', () => { const d = initialDemo(); expect(d.vehicles[0].capacity_kg).toBeNull(); expect(() => validatePlanning(d, planning())).not.toThrow() })
  it('rechaza vehículos no disponibles aunque figuren en el turno', () => {
    const d = initialDemo(); d.vehicles[0].available = false
    expect(() => validatePlanning(d, planning())).toThrow('no está disponible')
  })
  it.each(['driver_id', 'vehicle_id', 'departure_site_id', 'disposal_site_id', 'shift_id'] as const)('rechaza %s que no coincide con el turno', (field) => {
    expect(() => validatePlanning(initialDemo(), { ...planning(), [field]: 'otro' })).toThrow('turno programado')
  })
  it.each(['closed', 'missing', 'duplicate', 'empty'])('rechaza selección %s de eventos', (kind) => {
    const d = initialDemo(); const p = planning()
    p.event_ids = kind === 'closed' ? [d.events[2].id] : kind === 'missing' ? ['inexistente'] : kind === 'duplicate' ? [d.events[0].id, d.events[0].id] : []
    expect(() => validatePlanning(d, p)).toThrow('Selecciona eventos')
  })
  it('rechaza puntos inactivos o de tipo incompatible', () => {
    const d = initialDemo(); d.sites[0].site_type = 'descarga'
    expect(() => validatePlanning(d, planning())).toThrow('puntos activos')
    d.sites[0].site_type = 'salida'; d.sites[0].active = false
    expect(() => validatePlanning(d, planning())).toThrow('puntos activos')
  })
  it('presenta las fechas en Perú y no convierte valores nulos en cero', () => {
    expect(datePeru('2026-10-30T19:00:00Z')).toBe(datePeru('2026-10-30T14:00:00-05:00'))
    expect(datePeru(null)).toBe('Sin fecha'); expect(numberText(null, ' kg')).toBe('No disponible')
  })
})
