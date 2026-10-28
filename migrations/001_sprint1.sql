-- RECIWISE / Supabase PostgreSQL / versión 001
-- Ejecutar con la herramienta SQL Editor de Supabase, una sola vez.
-- Este archivo crea datos y permisos del Sprint 1, NO crea cuentas reales.
BEGIN;

CREATE TABLE IF NOT EXISTS public.profiles (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'ciudadano'
    CHECK (role IN ('ciudadano', 'encargado_municipal', 'chofer')),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Al registrarse en Supabase Auth el rol SIEMPRE inicia como ciudadano.
-- El metadata enviado por el cliente NO decide los permisos.
CREATE OR REPLACE FUNCTION public.reciwise_create_profile()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  INSERT INTO public.profiles(id, role) VALUES (NEW.id, 'ciudadano')
  ON CONFLICT(id) DO NOTHING;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS reciwise_on_auth_user_created ON auth.users;
CREATE TRIGGER reciwise_on_auth_user_created
AFTER INSERT ON auth.users FOR EACH ROW
EXECUTE FUNCTION public.reciwise_create_profile();

-- Cubre únicamente usuarios existentes; nunca cambia roles ya asignados.
INSERT INTO public.profiles(id, role)
SELECT id, 'ciudadano' FROM auth.users ON CONFLICT(id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  citizen_id uuid NOT NULL REFERENCES public.profiles(id),
  description text NOT NULL CHECK (char_length(btrim(description)) BETWEEN 3 AND 2000),
  latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  observed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  waste_type varchar(80),
  status text NOT NULL DEFAULT 'recibido'
    CHECK (status IN ('recibido','en_revision','programado','atendido','descartado'))
);
CREATE INDEX IF NOT EXISTS reports_citizen_created_idx ON public.reports(citizen_id, created_at DESC);
CREATE INDEX IF NOT EXISTS reports_status_created_idx ON public.reports(status, created_at DESC);
CREATE INDEX IF NOT EXISTS reports_location_idx ON public.reports(latitude, longitude);

CREATE TABLE IF NOT EXISTS public.report_photos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id uuid NOT NULL REFERENCES public.reports(id) ON DELETE CASCADE,
  storage_path text NOT NULL UNIQUE,
  content_type text NOT NULL CHECK (content_type IN ('image/jpeg','image/png','image/webp')),
  size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_photos_report_idx ON public.report_photos(report_id);

CREATE TABLE IF NOT EXISTS public.vehicles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label varchar(100) NOT NULL UNIQUE,
  vehicle_type text NOT NULL
    CHECK (vehicle_type IN ('compactadora','volquete','camion_baranda','otro')),
  plate varchar(20),
  available boolean NOT NULL DEFAULT false,
  capacity_kg double precision CHECK (capacity_kg > 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.service_sites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name varchar(120) NOT NULL,
  site_type text NOT NULL CHECK (site_type IN ('salida','descarga','ambos')),
  latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS public.shifts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vehicle_id uuid NOT NULL REFERENCES public.vehicles(id),
  driver_id uuid NOT NULL REFERENCES public.profiles(id),
  departure_site_id uuid NOT NULL REFERENCES public.service_sites(id),
  disposal_site_id uuid NOT NULL REFERENCES public.service_sites(id),
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'programado'
    CHECK (status IN ('programado','cancelado','finalizado')),
  created_by uuid NOT NULL REFERENCES public.profiles(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shifts_valid_interval CHECK (ends_at > starts_at)
);
CREATE INDEX IF NOT EXISTS shifts_vehicle_time_idx ON public.shifts(vehicle_id, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS shifts_driver_time_idx ON public.shifts(driver_id, starts_at, ends_at);

-- Estructuras para que D3 y D2 no confundan reporte, evento y parada.
CREATE TABLE IF NOT EXISTS public.events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  state text NOT NULL DEFAULT 'en_revision'
    CHECK (state IN ('en_revision','abierto','programado','atendido','cerrado','descartado')),
  intervention_type text,
  priority_score double precision,
  priority_factors jsonb,
  priority_config_version text,
  created_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  CONSTRAINT events_closed_timestamp CHECK (state <> 'cerrado' OR closed_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS public.event_reports (
  -- El reporte pertenece a un evento activo a la vez; moverlo requiere guardar la decisión.
  report_id uuid PRIMARY KEY REFERENCES public.reports(id) ON DELETE CASCADE,
  event_id uuid NOT NULL REFERENCES public.events(id),
  linked_at timestamptz NOT NULL DEFAULT now(),
  linked_by uuid REFERENCES public.profiles(id),
  linkage_method text NOT NULL CHECK (linkage_method IN ('automatica','manual')),
  factors jsonb,
  config_version text
);
CREATE INDEX IF NOT EXISTS event_reports_event_idx ON public.event_reports(event_id);

CREATE TABLE IF NOT EXISTS public.grouping_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id uuid NOT NULL REFERENCES public.reports(id),
  candidate_event_id uuid REFERENCES public.events(id),
  resulting_event_id uuid REFERENCES public.events(id),
  decision text NOT NULL CHECK (decision IN ('agrupar','separar','revisar','mantener_separado')),
  factors jsonb NOT NULL DEFAULT '{}'::jsonb,
  config_version text,
  decided_by uuid REFERENCES public.profiles(id),
  decided_at timestamptz NOT NULL DEFAULT now(),
  notes text
);
CREATE INDEX IF NOT EXISTS grouping_decisions_report_idx ON public.grouping_decisions(report_id, decided_at DESC);

-- No permitimos operaciones directas a las tablas desde el cliente.
-- Toda lectura/escritura pasa por FastAPI y sus comprobaciones de rol.
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shifts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grouping_decisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.profiles, public.reports, public.report_photos,
  public.vehicles, public.service_sites, public.shifts, public.events,
  public.event_reports, public.grouping_decisions FROM anon, authenticated;

COMMIT;

-- Crear el bucket privado fuera de la transacción de tablas (supone Supabase Storage habilitado).
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('reciwise-reportes', 'reciwise-reportes', false, 5242880,
        ARRAY['image/jpeg', 'image/png', 'image/webp']::text[])
ON CONFLICT (id) DO NOTHING;

-- Asignación de roles internos: ejecutar MANUALMENTE desde SQL Editor, solo tras
-- verificar la identidad del usuario; nunca habilitar una API de autoascenso.
-- UPDATE public.profiles SET role = 'encargado_municipal' WHERE id = '<uuid_autorizado>';
-- UPDATE public.profiles SET role = 'chofer' WHERE id = '<uuid_autorizado>';
