-- RECIWISE / futura persistencia de rutas y ejecución.
-- Esta estructura prepara integración, NO significa que OR-Tools o la IA estén conectados.
BEGIN;
CREATE TABLE IF NOT EXISTS public.route_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  shift_id uuid NOT NULL REFERENCES public.shifts(id),
  status text NOT NULL DEFAULT 'propuesta'
    CHECK (status IN ('propuesta','aprobada','en_ejecucion','finalizada','cancelada')),
  created_by uuid NOT NULL REFERENCES public.profiles(id),
  approved_by uuid REFERENCES public.profiles(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  algorithm_version text NOT NULL,
  matrix_source text,
  input_snapshot jsonb NOT NULL,
  configuration jsonb NOT NULL,
  distance_m double precision CHECK (distance_m >= 0),
  estimated_duration_seconds double precision CHECK (estimated_duration_seconds >= 0),
  geometry_geojson jsonb,
  excluded_events jsonb NOT NULL DEFAULT '[]'::jsonb,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  CHECK ((approved_by IS NULL AND approved_at IS NULL)
       OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
-- Una jornada puede tener propuestas alternativas, pero no dos rutas ejecutables.
CREATE UNIQUE INDEX IF NOT EXISTS one_approved_plan_per_shift
ON public.route_plans(shift_id)
WHERE status IN ('aprobada','en_ejecucion','finalizada');

CREATE TABLE IF NOT EXISTS public.route_stops (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  route_plan_id uuid NOT NULL REFERENCES public.route_plans(id) ON DELETE CASCADE,
  event_id uuid NOT NULL REFERENCES public.events(id),
  stop_order integer NOT NULL CHECK (stop_order > 0),
  estimated_service_minutes double precision CHECK (estimated_service_minutes > 0),
  status text NOT NULL DEFAULT 'pendiente'
    CHECK (status IN ('pendiente','atendida','incidencia','no_atendida')),
  visited_at timestamptz,
  recorded_by uuid REFERENCES public.profiles(id),
  UNIQUE (route_plan_id, event_id),
  UNIQUE (route_plan_id, stop_order)
);

CREATE TABLE IF NOT EXISTS public.stop_incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stop_id uuid NOT NULL REFERENCES public.route_stops(id),
  reported_by uuid NOT NULL REFERENCES public.profiles(id),
  incident_type text NOT NULL,
  description text,
  evidence_storage_path text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.route_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.route_stops ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stop_incidents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.route_plans, public.route_stops, public.stop_incidents
FROM anon, authenticated;
COMMIT;
