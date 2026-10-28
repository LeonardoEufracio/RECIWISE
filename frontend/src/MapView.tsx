import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import type { Report } from './types'

const EMPTY_REPORTS: Report[] = []
type Position = { latitude: number; longitude: number }

export default function MapView({ reports = EMPTY_REPORTS, location, onPick, onReportSelect }: {
  reports?: Report[]
  location?: Position
  onPick?: (position: Position) => void
  onReportSelect?: (id: string) => void
}) {
  const element = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const [tileError, setTileError] = useState(false)

  useEffect(() => {
    const instance = L.map(element.current!).setView([-12.05, -75.2], 12)
    map.current = instance
    const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(instance)
    tiles.on('tileerror', () => setTileError(true))
    return () => { instance.remove(); map.current = null }
  }, [])

  useEffect(() => {
    if (!onPick) return
    const instance = map.current!
    const pick = (event: L.LeafletMouseEvent) => {
      const point = event.latlng.wrap()
      onPick({ latitude: Number(point.lat.toFixed(6)), longitude: Number(point.lng.toFixed(6)) })
    }
    instance.on('click', pick)
    return () => { instance.off('click', pick) }
  }, [onPick])

  useEffect(() => {
    if (!location) return
    const instance = map.current!
    const marker = L.circleMarker([location.latitude, location.longitude], {
      radius: 9, color: '#166534', fillOpacity: 0.8,
    }).addTo(instance)
    instance.panTo([location.latitude, location.longitude])
    return () => { marker.remove() }
  }, [location?.latitude, location?.longitude])

  useEffect(() => {
    const instance = map.current!
    const group = L.featureGroup().addTo(instance)
    for (const report of reports) {
      const content = document.createElement('div')
      const text = document.createElement('p')
      text.textContent = `${report.description} (${report.status})`
      content.append(text)
      if (onReportSelect) {
        const button = document.createElement('button')
        button.textContent = 'Ver fotografías'
        button.addEventListener('click', () => onReportSelect(report.id))
        content.append(button)
      }
      L.circleMarker([report.latitude, report.longitude], { radius: 8, color: '#166534', fillOpacity: 0.7 })
        .bindPopup(content).addTo(group)
    }
    if (reports.length) instance.fitBounds(group.getBounds(), { padding: [30, 30], maxZoom: 16 })
    return () => { group.remove() }
  }, [reports, onReportSelect])

  return <div>
    <div ref={element} className="map" aria-label={onPick ? 'Mapa para elegir la ubicación del reporte' : 'Mapa de reportes municipales'} />
    {tileError && <p role="status">No se pudo cargar parte del mapa base. Revisa tu conexión; puedes usar las coordenadas y el listado.</p>}
    {onPick && <p className="hint">Haz clic en el mapa o escribe las coordenadas. El centro inicial es solo una referencia; no selecciona una ubicación.</p>}
  </div>
}
