-- Atomic active-uplink observations; existing rows remain unknown, not Starlink.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.bluetti_stats ADD COLUMN IF NOT EXISTS network jsonb;
-- Preserve the installed view's columns, order, owner and grants.
DO $$
DECLARE definition text;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='bluetti_latest' AND column_name='network'
  ) THEN
    SELECT pg_get_viewdef('public.bluetti_latest'::regclass, true) INTO definition;
    EXECUTE 'CREATE OR REPLACE VIEW public.bluetti_latest AS SELECT current.*, stats.network FROM ('
      || rtrim(definition, E';\n ') || ') current JOIN public.bluetti_stats stats'
      || ' ON stats.device_id=current.device_id AND stats.time=current.time';
  END IF;
END $$;
NOTIFY pgrst, 'reload schema';
COMMIT;
