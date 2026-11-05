import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import type { EventRecord, RouteProposal } from './model'

export default function RouteMap({ proposal, events, simulated = true, execution = false }: {
  proposal: Pick<RouteProposal, 'geometry' | 'stops'>; events: Pick<EventRecord, 'id' | 'latitude' | 'longitude'>[]; simulated?: boolean; execution?: boolean
}) {
  const container = useRef<HTMLDivElement>(null)
  const [tileError, setTileError] = useState(false)
  useEffect(() => {
    const map = L.map(container.current!, { zoomAnimation: false, fadeAnimation: false }).setView([-12.05, -75.22], 13)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).on('tileerror', () => setTileError(true)).addTo(map)
    const group = L.featureGroup().addTo(map)
    if (proposal.geometry) {
      const geometry = proposal.geometry
      if (geometry.type === 'LineString' && geometry.coordinates.length >= 2
        && geometry.coordinates.every((p) => p.length === 2 && p.every(Number.isFinite) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90)) {
        L.geoJSON(geometry, { style: { color: '#008c91', weight: 5, dashArray: '8 7', opacity: 0.8 } }).addTo(group)
      }
    }
    proposal.stops.forEach((stop) => {
      const event = events.find((e) => e.id === stop.event_id)
      if (!event) return
      const content = document.createElement('span')
      content.className = 'route-stop-icon'
      content.textContent = String(stop.order)
      L.marker([event.latitude, event.longitude], { icon: L.divIcon({ html: content, className: 'route-stop', iconSize: [30, 30], iconAnchor: [15, 15] }), title: 'Parada ' + stop.order })
        .bindTooltip('Parada ' + stop.order).addTo(group)
    })
    if (group.getLayers().length) map.fitBounds(group.getBounds(), { padding: [35, 35], maxZoom: 16 })
    return () => { map.remove() }
  }, [proposal, events])
  return <div><div ref={container} className="map route-map" aria-label={execution ? 'Mapa del recorrido asignado' : simulated ? 'Mapa de propuesta de demostración' : 'Mapa de propuesta recibida'} />{tileError && <p role="status">No se pudo cargar el mapa base. Consulta el orden de paradas en el listado.</p>}<p className="hint">{proposal.geometry ? execution ? 'Geometría persistida del recorrido; no ofrece navegación giro a giro.' : simulated ? 'Geometría GeoJSON esquemática devuelta por el adaptador simulado; no es una ruta vial optimizada.' : 'Geometría recibida con la propuesta. Revisa su procedencia y limitaciones; no autoriza su ejecución.' : 'Sin geometría disponible: se muestran solo las paradas, sin unirlas con líneas.'}</p></div>
}
