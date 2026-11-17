-- Run as the owner AFTER migrations, against the dedicated synthetic database.
-- No passwords here. Set one interactively with psql: \password casa_runtime
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'casa_runtime') THEN
    CREATE ROLE casa_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END $$;
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname='casa_runtime'
      AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
    OR EXISTS (SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='casa_runtime')) THEN
    RAISE EXCEPTION 'casa_runtime must be an unprivileged role with no inherited memberships';
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO casa_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM casa_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO casa_runtime;
GRANT INSERT, UPDATE, DELETE ON demo_visitors, demo_rate_buckets TO casa_runtime;
GRANT EXECUTE ON FUNCTION casa_demo_dataset_valid() TO casa_runtime;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
