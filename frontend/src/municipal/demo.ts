import type { Report } from '../types'
import type { DecisionKind, DemoData, PlanningInput, RouteProposal } from './model'

// Entirely fictitious. Never combined with API records or written to storage.
const id = (n: number) => 'd0000000-0000-4000-8000-' + String(n).padStart(12, '0')
const created = '2026-10-30T14:00:00-05:00'
export function initialDemo(): DemoData {
  const reports: Report[] = [
    { id: id(1), citizen_id: id(90), description: 'Ejemplo: bolsas y cartón junto a un cruce', latitude: -12.0528, longitude: -75.226, observed_at: created, created_at: created, waste_type: 'Mixto', status: 'recibido' },
    { id: id(2), citizen_id: id(91), description: 'Ejemplo: residuos en la esquina de la vía', latitude: -12.0529, longitude: -75.2261, observed_at: created, created_at: created, waste_type: null, status: 'en_revision' },
    { id: id(3), citizen_id: id(92), description: 'Ejemplo: material voluminoso en espacio abierto', latitude: -12.055, longitude: -75.222, observed_at: created, created_at: created, waste_type: 'Voluminoso', status: 'programado' },
    { id: id(4), citizen_id: id(93), description: 'Ejemplo cerrado: residuos retirados', latitude: -12.05, longitude: -75.223, observed_at: created, created_at: created, waste_type: null, status: 'atendido' },
  ]
  return {
    reports,
    vehicles: [
      { id: id(10), label: 'Unidad demostrativa 01', vehicle_type: 'compactadora', plate: null, available: true, capacity_kg: null },
      { id: id(11), label: 'Unidad demostrativa 02', vehicle_type: 'volquete', plate: null, available: false, capacity_kg: 3000 },
    ],
    sites: [
      { id: id(20), name: 'Salida ficticia', site_type: 'salida', latitude: -12.054, longitude: -75.228, active: true },
      { id: id(21), name: 'Descarga ficticia', site_type: 'descarga', latitude: -12.049, longitude: -75.22, active: true },
    ],
    shifts: [{ id: id(30), vehicle_id: id(10), driver_id: id(80), departure_site_id: id(20), disposal_site_id: id(21), starts_at: '2026-11-05T13:00:00Z', ends_at: '2026-11-05T17:00:00Z', status: 'programado', created_by: id(99) }],
    events: [
      { id: id(40), latitude: -12.0528, longitude: -75.226, state: 'abierto', report_ids: [id(1)], intervention_type: 'Recolección (ejemplo)', priority: null, restrictions: ['Acceso por verificar; ejemplo ficticio'], created_at: created, closed_at: null },
      { id: id(41), latitude: -12.055, longitude: -75.222, state: 'en_revision', report_ids: [id(3)], intervention_type: 'Evaluación de voluminosos (ejemplo)', priority: null, restrictions: ['Capacidad requerida desconocida'], created_at: created, closed_at: null },
      { id: id(42), latitude: -12.05, longitude: -75.223, state: 'cerrado', report_ids: [id(4)], intervention_type: null, priority: null, restrictions: [], created_at: created, closed_at: created },
    ],
    suggestions: [
      { id: id(50), reporte_nuevo_id: id(2), evento_candidato_id: id(40), similitud_texto: 0.84, distancia_metros: 35, diferencia_horas: 2.5, sugerencia: 'agrupar_candidato', motivos: ['Ejemplo de redacción parecida; requiere confirmar lugar y momento'], factores: [{ label: 'Origen', value: 'Valores ilustrativos, no salida del modelo' }], version_configuracion: 'ejemplo-ui-v1' },
      { id: id(51), reporte_nuevo_id: id(3), evento_candidato_id: id(40), similitud_texto: null, distancia_metros: null, diferencia_horas: null, sugerencia: 'requiere_revision', motivos: ['Datos de comparación no disponibles en este ejemplo'], factores: [], version_configuracion: 'ejemplo-ui-v1' },
      { id: id(52), reporte_nuevo_id: id(4), evento_candidato_id: id(42), similitud_texto: 0.5, distancia_metros: 0, diferencia_horas: 24, sugerencia: 'mantener_separado', motivos: ['El evento de ejemplo está cerrado; no vincular automáticamente una recurrencia'], factores: [], version_configuracion: 'ejemplo-ui-v1' },
    ],
    decisions: [], proposals: [],
  }
}

export function decideDemo(data: DemoData, suggestionId: string, kind: DecisionKind, notes: string): DemoData {
  const suggestion = data.suggestions.find((s) => s.id === suggestionId)
  if (!suggestion) throw new Error('La sugerencia ya no está disponible.')
  if (data.decisions.some((d) => d.suggestion_id === suggestionId)) throw new Error('Este caso ya tiene una decisión en la demostración.')
  const target = data.events.find((e) => e.id === suggestion.evento_candidato_id)
  if (!target) throw new Error('Evento no disponible.')
  if (kind === 'agrupar' && target.state === 'cerrado') throw new Error('No puedes agrupar en un evento cerrado.')
  const events = kind === 'agrupar' ? data.events.map((event) => ({
    ...event, report_ids: event.id === target.id
      ? [...new Set([...event.report_ids, suggestion.reporte_nuevo_id])]
      : event.report_ids.filter((rid) => rid !== suggestion.reporte_nuevo_id),
  })) : data.events
  return { ...data, events, decisions: [...data.decisions, {
    id: crypto.randomUUID(), suggestion_id: suggestionId, report_id: suggestion.reporte_nuevo_id,
    event_id: target.id, decision: kind, notes: notes.trim(), decided_at: new Date().toISOString(),
  }] }
}

export function proposeDemo(data: DemoData, value: PlanningInput): DemoData {
  validatePlanning(data, value)
  const proposal: RouteProposal = {
    id: crypto.randomUUID(), shift_id: value.shift_id, status: 'propuesta',
    stops: value.event_ids.map((event_id, index) => ({ order: index + 1, event_id })),
    excluded: data.events.filter((e) => !value.event_ids.includes(e.id)).map((e) => ({ event_id: e.id, reason: e.state === 'cerrado' ? 'Evento cerrado' : 'No seleccionado en la demostración' })),
    distance_m: null, duration_seconds: null, matrix_source: null, algorithm_version: 'simulador-frontend-v1',
    limitations: ['Propuesta no operativa; sin optimizador ni matriz vial.', 'El orden solo conserva la selección de demostración; no se ha optimizado.', 'No se ha comprobado capacidad ni acceso.'],
    // Fixed example returned by this adapter, never a line generated between selected stops.
    geometry: value.shift_id === id(30) && value.event_ids.join(',') === [id(40), id(41)].join(',') ? { type: 'LineString', coordinates: [
      [-75.228, -12.054], [-75.2278, -12.0538], [-75.2272, -12.0535],
      [-75.226, -12.0528], [-75.2258, -12.053], [-75.2245, -12.054],
      [-75.223, -12.0545], [-75.222, -12.055], [-75.2216, -12.0545], [-75.22, -12.049],
    ] } : null,
  }
  return { ...data, proposals: [proposal, ...data.proposals] }
}

export function validatePlanning(data: Pick<DemoData, 'vehicles' | 'sites' | 'shifts' | 'events'>, value: PlanningInput) {
  const shift = data.shifts.find((s) => s.id === value.shift_id && s.status === 'programado')
  if (!shift || shift.vehicle_id !== value.vehicle_id || shift.driver_id !== value.driver_id
    || shift.departure_site_id !== value.departure_site_id || shift.disposal_site_id !== value.disposal_site_id) {
    throw new Error('Los recursos deben corresponder al turno programado elegido.')
  }
  if (!data.vehicles.some((v) => v.id === value.vehicle_id && v.available)) throw new Error('El vehículo no está disponible.')
  if (!data.sites.some((s) => s.id === value.departure_site_id && s.active && ['salida', 'ambos'].includes(s.site_type))
    || !data.sites.some((s) => s.id === value.disposal_site_id && s.active && ['descarga', 'ambos'].includes(s.site_type))) throw new Error('Revisa los puntos activos de salida y descarga.')
  if (!value.event_ids.length || new Set(value.event_ids).size !== value.event_ids.length
    || value.event_ids.some((id) => !data.events.some((e) => e.id === id && !['cerrado', 'descartado', 'atendido'].includes(e.state)))) throw new Error('Selecciona eventos de atención abiertos, sin duplicados.')
}
