#!/usr/bin/env python3
"""Read clean, locally compiled PostgreSQL instances in an isolated container."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--pins', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pins = json.loads(args.pins.read_text())
    for major, pin in pins.items():
        def query(sql):
            command = ['docker', 'exec', args.container, '/opt/pg/' + major + '/bin/psql',
                       '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-h', '/socket/' + major,
                       '-U', 'postgres', '-d', 'postgres', '-c', sql]
            return json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        identity = query("SELECT json_build_object('version',version(),'server_version',current_setting('server_version'),'server_version_num',current_setting('server_version_num'),'locale',datcollate,'encoding',current_setting('server_encoding')) FROM pg_database WHERE datname=current_database()")
        assert identity['server_version'].split()[0] == pin['release'], identity
        settings = query('SELECT json_agg(row_to_json(s) ORDER BY name) FROM pg_settings s')
        relations = query("""SELECT json_agg(row_to_json(r) ORDER BY name) FROM (
          SELECT c.relname name,c.oid relation_oid,c.relkind,c.relisshared shared,
            (SELECT json_agg(row_to_json(a) ORDER BY attnum) FROM (
              SELECT attname name,attnum,format_type(atttypid,atttypmod) type,atttypid type_oid,
                     attnotnull not_null,atttypmod type_modifier,attndims array_dimensions
              FROM pg_attribute WHERE attrelid=c.oid AND NOT attisdropped) a) columns
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='pg_catalog' AND c.relkind IN ('r','v','m','S')) r""")
        catalogs = {}
        for table in ('pg_type','pg_operator','pg_opclass','pg_opfamily','pg_amop','pg_amproc',
                      'pg_am','pg_range','pg_language','pg_authid','pg_ts_parser','pg_ts_template',
                      'pg_ts_dict','pg_ts_config','pg_collation'):
            catalogs[table] = query('SELECT json_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM ' + table + ' t')
        output = dict(identity=identity, source=pin, settings=settings, relations=relations, catalogs=catalogs)
        path = args.output / major / 'sample.json'
        path.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        (path.parent / 'sample.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest() + '\n')
        print(major, identity['server_version'], len(settings), len(relations), flush=True)


if __name__ == '__main__':
    main()
