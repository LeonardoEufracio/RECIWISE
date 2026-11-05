import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import type { Report } from './types'
import type { EventRecord } from './municipal/model'
import { datePeru, shortId, stateLabel, statusColor } from './format'

const EMPTY_REPORTS: Report[] = []
const EMPTY_EVENTS: EventRecord[] = []
type Position = { latitude: number; longitude: number }

export default function MapView({ reports = EMPTY_REPORTS, events = EMPTY_EVENTS, location, onPick, onReportSelect, selectedReportId, onEventSelect }: {
  reports?: Report[]; events?: Pick<EventRecord, 'id' | 'latitude' | 'longitude' | 'state' | 'report_ids'>[]; location?: Position
  onPick?: (position: Position) => void; onReportSelect?: (id: string) => void
  selectedReportId?: string | null; onEventSelect?: (id: string) => void
}) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const [tileError, setTileError] = useState(false)
  useEffect(() => {
    // Leaflet 1.9's zoom transition can outlive a screen removed by React.
    const instance = L.map(element.current!, { zoomAnimation: false, fadeAnimation: false }).setView([-12.05, -75.2], 12)
    map.current = instance
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', maxZoom: 19,
    }).on('tileerror', () => setTileError(true)).addTo(instance)
    return () => { instance.remove(); map.current = null }
  }, [])
  useEffect(() => {
    if (!onPick) return
    const instance = map.current!
    const pick = (event: L.LeafletMouseEvent) => { const p = event.latlng.wrap(); onPick({ latitude: Number(p.lat.toFixed(6)), longitude: Number(p.lng.toFixed(6)) }) }
    instance.on('click', pick)
    return () => { instance.off('click', pick) }
  }, [onPick])
  useEffect(() => {
    if (!location) return
    const instance = map.current!
    const marker = L.circleMarker([location.latitude, location.longitude], { radius: 9, color: '#166534', fillOpacity: 0.8 }).addTo(instance)
    instance.panTo([location.latitude, location.longitude])
    return () => { marker.remove() }
  }, [location?.latitude, location?.longitude])
  useEffect(() => {
    const instance = map.current!
    const group = L.featureGroup().addTo(instance)
    // Only identical coordinates share a popup. This never creates a business grouping.
    const points = new Map<string, Report[]>()
    for (const report of reports) {
      const key = report.latitude + ',' + report.longitude
      points.set(key, [...(points.get(key) || []), report])
    }
    for (const colocated of points.values()) {
      const content = document.createElement('div')
      if (colocated.length > 1) { const notice = document.createElement('p'); notice.textContent = colocated.length + ' reportes en estas coordenadas; no implica un mismo evento.'; content.append(notice) }
      for (const report of colocated) {
        const section = document.createElement('div')
        const text = document.createElement('p'); text.textContent = report.description + ' · ' + stateLabel(report.status)
        const date = document.createElement('p'); date.textContent = 'Observado: ' + datePeru(report.observed_at)
        section.append(text, date)
        if (onReportSelect) { const button = document.createElement('button'); button.textContent = 'Ver detalle y fotografías'; button.addEventListener('click', () => onReportSelect(report.id)); section.append(button) }
        content.append(section)
      }
      const first = colocated[0]
      L.circleMarker([first.latitude, first.longitude], { radius: colocated.length > 1 ? 12 : 8, color: statusColor(first.status), fillOpacity: 0.8, weight: 3 })
        .bindPopup(content).addTo(group)
    }
    for (const event of events) {
      const content = document.createElement('div')
      const text = document.createElement('p'); text.textContent = 'Evento ' + shortId(event.id) + ' · ' + stateLabel(event.state) + ' · ' + event.report_ids.length + ' reportes'
      content.append(text)
      if (onEventSelect) { const button = document.createElement('button'); button.textContent = 'Abrir evento'; button.addEventListener('click', () => onEventSelect(event.id)); content.append(button) }
      const icon = L.divIcon({ className: 'event-marker ' + (event.state === 'cerrado' ? 'closed' : ''), html: '<span aria-hidden="true">◆</span>', iconSize: [26, 26], iconAnchor: [13, 13] })
      L.marker([event.latitude, event.longitude], { icon, title: 'Evento ' + shortId(event.id), keyboard: true }).bindPopup(content).addTo(group)
    }
    if (group.getLayers().length) instance.fitBounds(group.getBounds(), { padding: [36, 36], maxZoom: 16 })
    return () => { group.remove() }
  }, [reports, events, onReportSelect, onEventSelect])
  useEffect(() => {
    const report = reports.find((r) => r.id === selectedReportId)
    if (report) map.current?.setView([report.latitude, report.longitude], 17)
  }, [reports, selectedReportId])
  return <div>
    <div ref={element} className="map" aria-label={onPick ? 'Mapa para elegir la ubicación del reporte' : 'Mapa de reportes municipales'} />
    {tileError && <p role="status">No se pudo cargar parte del mapa base. Revisa tu conexión; puedes usar las coordenadas y el listado.</p>}
    {onPick && <p className="hint">Haz clic en el mapa para seleccionar una ubicación. El centro inicial es solo una referencia.</p>}
  </div>
}
