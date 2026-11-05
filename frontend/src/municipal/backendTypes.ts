import type { Report } from '../types'
export type Json = string | number | boolean | null | Json[] | { [key: string]: Json }
export type EventState = 'en_revision' | 'abierto' | 'programado' | 'atendido' | 'cerrado' | 'descartado'
export interface EventCreateCommand {
  latitude: number; longitude: number; intervention_type: string | null; report_ids: string[]
}
export interface EventDto {
  id: string; latitude: number; longitude: number; state: EventState
  intervention_type: string | null; priority: { score: number | null; factors: Json; version: string | null } | null
  restrictions: null; report_ids: string[]; report_count: number; created_at: string; closed_at: string | null
}
export type EventBrief = Pick<EventDto, 'id' | 'latitude' | 'longitude' | 'state' | 'intervention_type' | 'closed_at'>
export interface GroupingDto {
  report: Report; event_id: string | null; event: EventBrief | null; last_decision_id: string | null
  pending_review: boolean; linked_at: string | null; linked_by: string | null
  linkage_method: string | null; config_version: string | null
}
export type DecisionKindDto = 'agrupar' | 'separar' | 'mantener_separado' | 'revisar'
export interface DecisionCommand {
  operation_id: string; report_id: string; decision: DecisionKindDto; candidate_event_id: string | null
  expected_event_id: string | null; expected_decision_id: string | null; notes: string | null
}
export interface DecisionDto {
  id: string; report_id: string; candidate_event_id: string | null; resulting_event_id: string | null
  previous_event_id: string | null; previous_event_known: boolean; operation: string | null
  decision: DecisionKindDto; factors: Json; config_version: string | null
  decided_by: string | null; decided_at: string; notes: string | null
}
export interface DecisionResultDto { decision: DecisionDto; relation: GroupingDto; replayed: boolean }
export interface CandidatesDto {
  report_id: string; event_id: string | null; last_decision_id: string | null
  source: 'manual'; d3_available: false; candidates: EventDto[]
}
export interface DecisionIntent {
  command: DecisionCommand
  stage: 'prepared' | 'sending' | 'conflict' | 'uncertain' | 'rejected'
  error: string; notFound: boolean
}
export type OriginDto = 'pending' | 'test_fixture' | 'municipal_unverified' | 'd3' | 'legacy_unknown'
export interface ProposalSummaryDto {
  id: string; shift_id: string; status: 'propuesta'; created_by: string; created_at: string
  calculation_status: 'pending' | 'completed' | 'unknown'; result_origin: OriginDto; operational: false
  input_hash: string | null; algorithm_version: string | null; matrix_source: string | null
  distance_m: number | null; estimated_duration_seconds: number | null; stop_count: number; excluded_count: number
  limitations: string[]; unknowns: string[]
}
export interface RouteStopDto {
  id: string; route_plan_id: string; event_id: string; order: number
  estimated_service_minutes: number | null; status: string
}
export interface ExclusionDto { event_id: string; reason: string }
export interface ProposalDetailDto extends ProposalSummaryDto {
  input_snapshot: { [key: string]: Json }; configuration: { [key: string]: Json }
  geometry_geojson: { type: 'LineString'; coordinates: [number, number][] } | null
  stops: RouteStopDto[]; excluded_events: ExclusionDto[]
}
