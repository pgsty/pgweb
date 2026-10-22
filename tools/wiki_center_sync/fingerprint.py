"""Read-only row fingerprints for isolated backup validation and drift guards."""
import argparse
import json
import os
from pathlib import Path
import psycopg2
from psycopg2 import sql


def fingerprint(dsn):
    result = {'tables': {}}
    with psycopg2.connect(dsn) as conn:
        conn.set_session(isolation_level='REPEATABLE READ', readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")
            name, owner = cur.fetchone()
            assert owner == 'pgweb' and (name == 'pgweb' or name.startswith('test_pgweb_wiki_center_'))
            result['database'] = name
            cur.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' ORDER BY 1,2")
            tables=cur.fetchall()
            for schema, table in tables:
                cur.execute(sql.SQL("WITH r AS MATERIALIZED (SELECT md5(to_jsonb(t)::text) AS digest FROM {} t) SELECT count(*),md5(coalesce(string_agg(digest,'' ORDER BY digest),'')) FROM r").format(sql.Identifier(schema,table)))
                count,digest=cur.fetchone()
                result['tables'][schema+'.'+table]={'rows':count,'content_md5':digest}
            cur.execute("SELECT schemaname,sequencename,start_value,min_value,max_value,increment_by,cycle,cache_size,last_value FROM pg_sequences WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
            result['sequences']=cur.fetchall()
            cur.execute("SELECT table_schema,table_name,column_name,ordinal_position,data_type,udt_schema,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2,4")
            result['columns']=cur.fetchall()
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    data=fingerprint(os.environ['PGWEB_SYNC_DSN'])
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n')
    print(json.dumps({'database':data['database'],'tables':len(data['tables']),'rows':sum(t['rows'] for t in data['tables'].values())}))
