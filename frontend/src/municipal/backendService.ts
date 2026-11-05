import type { Api } from '../api'
import type { Report } from '../types'
import type { CandidatesDto, DecisionCommand, DecisionDto, DecisionResultDto, EventCreateCommand, EventDto, EventState,
  ExclusionDto, GroupingDto, OriginDto, ProposalDetailDto, ProposalSummaryDto, RouteStopDto } from './backendTypes'

type Page = { limit?: number; offset?: number }
function query(values: Record<string, string | number | boolean | undefined>) {
  return new URLSearchParams(Object.entries(values).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString()
}
const id = encodeURIComponent
export function createBackendService(api: Api) {
  async function list<T>(path: string, signal?: AbortSignal) {
    const value = await api<T[]>(path, { signal })
    if (!Array.isArray(value)) throw new Error('La respuesta no coincide con el contrato actual de FastAPI.')
    return value
  }
  return {
    createEvent: (command: EventCreateCommand) => api<EventDto>('/municipal/events', { method: 'POST', body: JSON.stringify(command) }),
    events: (page: Page & { state?: EventState } = {}, signal?: AbortSignal) =>
      list<EventDto>('/municipal/events?' + query({ limit: 50, offset: 0, ...page }), signal),
    event: (eventId: string, signal?: AbortSignal) => api<EventDto>('/municipal/events/' + id(eventId), { signal }),
    eventReports: (eventId: string, page: Page = {}, signal?: AbortSignal) =>
      list<Report>('/municipal/events/' + id(eventId) + '/reports?' + query({ limit: 50, offset: 0, ...page }), signal),
    groupings: (page: Page & { linked?: boolean; pending_review?: boolean } = {}, signal?: AbortSignal) =>
      list<GroupingDto>('/municipal/groupings?' + query({ limit: 50, offset: 0, ...page }), signal),
    relation: (reportId: string, signal?: AbortSignal) => api<GroupingDto>('/municipal/groupings/reports/' + id(reportId), { signal }),
    candidates: (reportId: string, page: Page = {}, signal?: AbortSignal) =>
      api<CandidatesDto>('/municipal/groupings/candidates?' + query({ report_id: reportId, limit: 50, offset: 0, ...page }), { signal }),
    decisions: (page: Page & { report_id?: string; event_id?: string } = {}, signal?: AbortSignal) =>
      list<DecisionDto>('/municipal/groupings/decisions?' + query({ limit: 50, offset: 0, ...page }), signal),
    decision: (operationId: string, signal?: AbortSignal) => api<DecisionDto>('/municipal/groupings/decisions/' + id(operationId), { signal }),
    decide: (command: DecisionCommand) => api<DecisionResultDto>('/municipal/groupings/decisions', { method: 'POST', body: JSON.stringify(command) }),
    proposals: (page: Page & { shift_id?: string; calculation_status?: ProposalSummaryDto['calculation_status']; result_origin?: OriginDto } = {}, signal?: AbortSignal) =>
      list<ProposalSummaryDto>('/municipal/route-proposals?' + query({ limit: 50, offset: 0, ...page }), signal),
    proposal: (proposalId: string, signal?: AbortSignal) => api<ProposalDetailDto>('/municipal/route-proposals/' + id(proposalId), { signal }),
    stops: (proposalId: string, page: Page = {}, signal?: AbortSignal) =>
      list<RouteStopDto>('/municipal/route-proposals/' + id(proposalId) + '/stops?' + query({ limit: 50, offset: 0, ...page }), signal),
    exclusions: (proposalId: string, page: Page = {}, signal?: AbortSignal) =>
      list<ExclusionDto>('/municipal/route-proposals/' + id(proposalId) + '/excluded-events?' + query({ limit: 50, offset: 0, ...page }), signal),
  }
}
export type BackendService = ReturnType<typeof createBackendService>
