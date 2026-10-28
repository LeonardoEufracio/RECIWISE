# Contratos iniciales entre D2 (API/datos) y D3 (IA/rutas)

Estos contratos son **propuestas por validar en el equipo**, no endpoints ejecutados. No se inventan puntuaciones, umbrales o datos municipales.

## Datos de entrada para comparación

La capa D2 prepara un registro de esta forma desde `reports`, `event_reports` y `events`. `evento_asociado_id` puede ser nulo.

```json
{
  "id": "<uuid-del-reporte>",
  "descripcion": "Residuos acumulados junto a la esquina",
  "latitud": -12.0,
  "longitud": -75.0,
  "fecha_observacion": "2026-10-27T12:00:00-05:00",
  "fecha_reporte": "2026-10-27T12:10:00-05:00",
  "tipo_residuo": null,
  "evento_asociado_id": null,
  "estado_evento": null,
  "fecha_cierre_evento": null
}
```

**Nota:** las coordenadas y el texto de arriba son solamente ejemplos del formato, no reportes reales ni ubicación de un punto crítico.

## Respuesta esperada del comparador (módulo D3)

```json
{
  "reporte_nuevo_id": "<uuid>",
  "evento_candidato_id": "<uuid>",
  "similitud_texto": null,
  "distancia_metros": null,
  "diferencia_horas": null,
  "sugerencia": "requiere_revision",
  "motivos": [],
  "version_configuracion": "<version>"
}
```

`similitud_texto`, `distancia_metros` y `diferencia_horas` son `null` **solo en esta plantilla**. D3 debe calcularlos o declarar que faltan datos. Ni el texto ni la cercanía garantizan coincidencia. No agrupar automáticamente un evento cerrado.

El módulo de agrupación **no debe** modificar `reports.status` a `atendido`. La asignación y corrección se guardarán como relación `event_reports` y registro `grouping_decisions`.

## Entrada para planificar (Sprint 2)

D2 reunirá: eventos abiertos y revisados, prioridades y sus factores, `vehicle_id`, `driver_id`, jornada, `departure_site_id`, `disposal_site_id`, tiempos de servicio, compatibilidad de intervención, disponibilidad y limitaciones de capacidad.

D3 devolverá el orden de eventos, método y matriz vial, geometría, distancia/tiempo estimados, excluidos con motivo, parámetros y limitaciones. Un peso o volumen desconocido se conserva **desconocido**, no se inventa. La ruta calculada queda en estado `propuesta` y **solo** el encargado puede aprobarla. `route_plans` y `route_stops` preservarán estos resultados.

## Decisiones abiertas

- Sector exacto del piloto y sus límites.
- Enumeraciones finales de tipo de residuo y de intervención.
- Reglas de agrupación evaluadas y umbrales (aún no acordados).
- Regla piloto si no hay datos de capacidad.
- Criterios de compatibilidad de unidad y acceso.
- Procedimiento de fotografías de cierre del chofer.
- Servicio vial, disponibilidad, ubicación de salida y descarga realmente autorizadas.
