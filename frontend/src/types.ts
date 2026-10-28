// Contratos de app/schemas.py. Los permisos siempre los decide FastAPI.
export type Role = 'ciudadano' | 'encargado_municipal' | 'chofer'
export interface Actor { id: string; role: Role }
export interface ReportCreate {
  description: string
  latitude: number
  longitude: number
  observed_at: string
  waste_type: string | null
}
export interface Report extends ReportCreate {
  id: string
  citizen_id: string
  created_at: string
  status: string
}
export interface Photo {
  id: string
  report_id: string
  content_type: string
  size_bytes: number
  created_at: string
  signed_url: string | null
}
export interface RequestEntry {
  id: number
  time: string
  method: string
  path: string
  status: number | null
  duration: number
}
