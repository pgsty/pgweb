from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('ext', '0002_remove_doc')]
    operations = [migrations.RunSQL(
        sql="""
CREATE TABLE pgext.cloud (
    service text NOT NULL CHECK (service ~ '^[a-z][a-z0-9_]*$'),
    pg_major smallint NOT NULL CHECK (pg_major BETWEEN 10 AND 99),
    provider text NOT NULL CHECK (btrim(provider) <> ''),
    service_name text NOT NULL CHECK (btrim(service_name) <> ''),
    engine_status text NOT NULL CHECK (engine_status IN ('GA','PREVIEW','EXISTING_ONLY','UNAVAILABLE','UNKNOWN')),
    data_status text NOT NULL CHECK (data_status IN ('COMPLETE','PARTIAL','MISSING')),
    list_scope text NOT NULL CHECK (list_scope IN ('PG_MAJOR','PG_MAJOR_PARTIAL','PG_RANGE','SERVICE_WIDE','CURRENT_MAJOR','DELEGATED','UNVERSIONED','INSTANCE_ONLY')),
    source_url text NOT NULL CHECK (source_url ~ '^https://'),
    engine_url text NOT NULL CHECK (engine_url ~ '^https://'),
    checked_at timestamptz NOT NULL,
    note text,
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(provenance) = 'object'),
    PRIMARY KEY (service, pg_major),
    CHECK (data_status <> 'COMPLETE' OR engine_status NOT IN ('UNAVAILABLE','UNKNOWN'))
);
CREATE TABLE pgext.cloud_fact (
    service text NOT NULL,
    pg_major smallint NOT NULL,
    raw_name text NOT NULL CHECK (raw_name = btrim(raw_name) AND raw_name <> ''),
    extension text REFERENCES pgext.universe(name),
    status text NOT NULL CHECK (status IN ('SUPPORTED','UNSUPPORTED','OTHER')),
    version text,
    note text,
    extra jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (service, pg_major, raw_name),
    FOREIGN KEY (service, pg_major) REFERENCES pgext.cloud(service, pg_major),
    CHECK (extension IS NULL OR (extension = btrim(extension) AND extension <> ''))
);
CREATE UNIQUE INDEX cloud_fact_canonical_idx ON pgext.cloud_fact(service, pg_major, extension) WHERE extension IS NOT NULL;
CREATE INDEX cloud_fact_extension_idx ON pgext.cloud_fact(extension);
COMMENT ON TABLE pgext.cloud IS 'Service-major evidence coverage, copied from PGEXT with a package-derived Pigsty comparison anchor';
COMMENT ON COLUMN pgext.cloud.checked_at IS 'Source capture time; never replace historical cloud evidence dates with import time';
COMMENT ON COLUMN pgext.cloud.data_status IS 'Only COMPLETE permits inferring unsupported from a missing canonical fact';
COMMENT ON TABLE pgext.cloud_fact IS 'Unified extension facts, preserving raw labels and source metadata; Pigsty package details live in extra';
COMMENT ON COLUMN pgext.cloud_fact.extension IS 'Local Universe canonical name; NULL retains an unresolved vendor label';
""",
        reverse_sql='DROP TABLE pgext.cloud_fact; DROP TABLE pgext.cloud;',
    )]
