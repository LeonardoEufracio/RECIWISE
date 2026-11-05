export const reportStates: Record<string, string> = {
  recibido: 'Pendiente', en_revision: 'En revisión', programado: 'Programado',
  atendido: 'Atendido', descartado: 'Descartado', abierto: 'Abierto', cerrado: 'Cerrado',
  propuesta: 'Propuesta', aprobada: 'Aprobada', cancelado: 'Cancelado', finalizado: 'Finalizado',
  en_ejecucion: 'En ejecución', finalizada: 'Finalizada', cancelada: 'Cancelada',
  pendiente: 'Pendiente', atendida: 'Atendida', incidencia: 'Incidencia', no_atendida: 'No atendida',
}
export const stateLabel = (value: string) => reportStates[value] || value
export function datePeru(value: string | null | undefined) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Sin fecha'
  return new Intl.DateTimeFormat('es-PE', { timeZone: 'America/Lima', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}
export const numberText = (value: number | null | undefined, unit = '') =>
  value == null || !Number.isFinite(value) ? 'No disponible' : new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 }).format(value) + unit
export const shortId = (id: string) => id.length > 14 ? id.slice(0, 4) + '…' + id.slice(-4) : id
export const isUuid = (value: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
const statusColors: Record<string, string> = { recibido: '#c17b13', en_revision: '#4e66b1', programado: '#008d96', atendido: '#26835d', descartado: '#677783' }
export const statusColor = (status: string) => statusColors[status] || '#677783'
