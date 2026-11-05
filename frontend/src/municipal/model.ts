import type { Report } from '../types'

// Resources match app/schemas.py. Sprint 2 shapes below are UI adapters,
// not claims of endpoints or finalized wire contracts.
export interface Vehicle { id: string; label: string; vehicle_type: string; plate: string | null; capacity_kg: number | null; available: boolean }
export type VehicleInput = Omit<Vehicle, 'id'>
export interface Site { id: string; name: string; site_type: 'salida' | 'descarga' | 'ambos'; latitude: number; longitude: number; active: boolean }
export type SiteInput = Omit<Site, 'id' | 'active'>
export interface Shift { id: string; vehicle_id: string; driver_id: string; departure_site_id: string; disposal_site_id: string; starts_at: string; ends_at: string; status: string; created_by: string }
export type ShiftInput = Omit<Shift, 'id' | 'status' | 'created_by'>
export interface Driver { id: string; role: 'chofer' }
export interface PriorityResult { score: number | null; factors: { label: string; value: string }[]; version: string | null }
export interface EventRecord { id: string; latitude: number; longitude: number; state: string; report_ids: string[]; intervention_type: string | null; priority: PriorityResult | null; restrictions: string[]; created_at: string; closed_at: string | null }
export type SuggestionKind = 'agrupar_candidato' | 'requiere_revision' | 'mantener_separado'
export interface Suggestion {
  id: string; reporte_nuevo_id: string; evento_candidato_id: string
  similitud_texto: number | null; distancia_metros: number | null; diferencia_horas: number | null
  sugerencia: SuggestionKind; motivos: string[]; factores: { label: string; value: string }[]; version_configuracion: string
}
export type DecisionKind = 'agrupar' | 'mantener_separado' | 'revisar'
export interface Decision { id: string; suggestion_id: string; report_id: string; event_id: string; decision: DecisionKind; notes: string; decided_at: string }
export interface RouteProposal {
  id: string; shift_id: string; status: 'propuesta' | 'aprobada'
  stops: { order: number; event_id: string }[]; excluded: { event_id: string; reason: string }[]
  distance_m: number | null; duration_seconds: number | null; matrix_source: string | null
  algorithm_version: string; limitations: string[]
  geometry: { type: 'LineString'; coordinates: [number, number][] } | null
}
export interface PlanningInput { shift_id: string; vehicle_id: string; driver_id: string; departure_site_id: string; disposal_site_id: string; event_ids: string[] }
export interface DemoData { reports: Report[]; vehicles: Vehicle[]; sites: Site[]; shifts: Shift[]; events: EventRecord[]; suggestions: Suggestion[]; decisions: Decision[]; proposals: RouteProposal[] }
export type Section = 'dashboard' | 'reports' | 'events' | 'groupings' | 'priorities' | 'planning' | 'resources'
