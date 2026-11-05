export type RouteState = 'propuesta' | 'aprobada' | 'en_ejecucion' | 'finalizada' | 'cancelada'
export type OperationAction = 'approve' | 'reject' | 'cancel' | 'start' | 'finish' | 'attend' | 'incident' | 'not_attended'
export interface Audit {
  operation_id: string; actor_id: string; action: OperationAction; at: string
  previous_status: RouteState; resulting_status: RouteState; stop_id: string | null; notes: string | null; request_hash: string
}
export interface ExecutionStop {
  id: string; event_id: string; order: number; latitude: number | null; longitude: number | null
  status: 'pendiente' | 'atendida' | 'incidencia' | 'no_atendida'; estimated_service_minutes: number | null
  visited_at: string | null; recorded_by: string | null
  incidents: { id: string; stop_id: string; reported_by: string; incident_type: string; description: string | null; created_at: string }[]
}
export interface RouteSummary {
  id: string; shift_id: string; driver_id: string; vehicle_id: string; vehicle_label: string
  starts_at: string; ends_at: string; status: RouteState; created_at: string; revision: string | null
  approved_by: string | null; approved_at: string | null; approval_verified: boolean
  can_approve: false; approval_blockers: string[]
}
export interface RouteDetail extends RouteSummary {
  shift_status: string; vehicle_available: boolean
  departure: { id: string; name: string; site_type: string; active: boolean; latitude: number; longitude: number }
  disposal: RouteDetail['departure']; stops: ExecutionStop[]; history: Audit[]
  distance_m: number | null; estimated_duration_seconds: number | null
  geometry_geojson: { type: 'LineString'; coordinates: [number, number][] } | null
  limitations: string[]; excluded_events: { event_id: string; reason: string }[]
}
export interface OperationCommand {
  operation_id: string; expected_status: RouteState; expected_revision: string | null; notes: string | null
  decision?: 'approve' | 'reject' | 'cancel'; action?: 'start' | 'finish' | 'attend' | 'incident' | 'not_attended'; incident_type?: string
}
export interface OperationResult { operation: Audit; route: RouteDetail; replayed: boolean }
export interface Intent {
  scope: 'municipal' | 'driver'; routeId: string; stopId?: string; command: OperationCommand
  stage: 'prepared' | 'sending' | 'uncertain' | 'conflict' | 'rejected'; error: string; notFound: boolean
}
export const actionNames: Record<OperationAction, string> = { approve: 'Aprobar propuesta', reject: 'Rechazar propuesta', cancel: 'Cancelar propuesta o ruta', start: 'Iniciar recorrido', finish: 'Finalizar recorrido', attend: 'Registrar parada atendida', incident: 'Registrar incidencia', not_attended: 'Registrar no atención' }
