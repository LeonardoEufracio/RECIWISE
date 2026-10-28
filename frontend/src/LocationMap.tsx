import { useEffect, useState } from 'react'
import { Circle, MapContainer, Marker, TileLayer, useMapEvents } from 'react-leaflet'
import { icon, type Marker as LeafletMarker } from 'leaflet'
import markerUrl from 'leaflet/dist/images/marker-icon.png'
import markerRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'
import type { Coordinates, ReportLocation } from './types'

const markerIcon = icon({
  iconUrl: markerUrl, iconRetinaUrl: markerRetinaUrl, shadowUrl,
  iconSize: [25, 41], iconAnchor: [12, 41], shadowSize: [41, 41],
})

function Selection({ location, editable, onPick }: {
  location: ReportLocation | null; editable: boolean; onPick: (point: Coordinates) => void
}) {
  const map = useMapEvents({
    click(event) {
      if (!editable) return
      const point = event.latlng.wrap()
      onPick({ latitude: point.lat, longitude: point.lng })
    },
  })

  useEffect(() => {
    if (location?.source === 'device') {
      map.setView([location.latitude, location.longitude], 16)
    }
  }, [map, location?.latitude, location?.longitude, location?.source])

  if (!location) return null
  const position: [number, number] = [location.latitude, location.longitude]
  return <>
    {location.source === 'device' && location.accuracy !== undefined && <Circle center={position} radius={location.accuracy} pathOptions={{ color: '#166534', weight: 1, fillOpacity: 0.08 }} />}
    <Marker position={position} icon={markerIcon} draggable={editable} autoPan
      title="Ubicación seleccionada" alt="Ubicación seleccionada"
      eventHandlers={{
        dragend(event) {
          if (!editable) return
          const point = (event.target as LeafletMarker).getLatLng().wrap()
          onPick({ latitude: point.lat, longitude: point.lng })
        },
      }} />
  </>
}

export default function LocationMap({ location, editable, onPick }: {
  location: ReportLocation | null; editable: boolean; onPick: (point: Coordinates) => void
}) {
  const [tileError, setTileError] = useState(false)
  return <div role="region" aria-label="Mapa para elegir la ubicación del reporte">
    <MapContainer center={[-12.05, -75.2]} zoom={12} className="map location-map" scrollWheelZoom={false}>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19}
        eventHandlers={{ tileerror: () => setTileError(true) }} />
      <Selection location={location} editable={editable} onPick={onPick} />
    </MapContainer>
    {tileError && <p role="status">No se pudo cargar parte del mapa base. Revisa tu conexión antes de confirmar el lugar.</p>}
  </div>
}
