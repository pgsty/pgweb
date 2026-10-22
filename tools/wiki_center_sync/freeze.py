"""Freeze the active native Chinese reader and the Django destination, read-only."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

import psycopg2
from psycopg2 import sql

EXPECTED = '7c31b524dfe136022d39a6ae8dcfac6b3bbd5f8fdaf422536599981252aff0c9'


def dump_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as out:
        for row in rows:
            out.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode())
            count += 1
    return {'rows': count, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def freeze_source(root, dsn):
    root.mkdir(parents=True, exist_ok=False)
    with psycopg2.connect(dsn) as conn:
        conn.set_session(isolation_level='REPEATABLE READ', readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")
            assert cur.fetchone() == ('center', 'center2_owner')
            cur.execute('SELECT id,content_hash FROM knowledge.wiki_dataset WHERE active')
            active = cur.fetchall()
            assert len(active) == 1 and active[0][1] == EXPECTED
            dataset = active[0][0]
            cur.execute('SELECT source_database,table_name,content_hash,archive FROM knowledge.wiki_source_file WHERE dataset_id=%s ORDER BY 1,2', (dataset,))
            files = {}
            for db, table, expected, data in cur:
                data = bytes(data)
                assert hashlib.sha256(data).hexdigest() == expected
                path = root/'raw'/db/(table+'.jsonl.gz')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                files[str(path.relative_to(root))] = {'sha256': expected, 'bytes': len(data)}
        with conn.cursor(name='canonical_reader') as cur:
            cur.itersize = 100
            cur.execute("""SELECT jsonb_build_object(
              'collection',e.collection,'key',e.entry_key,'name',e.name,'aliases',e.aliases,'metadata',e.metadata,
              'version',f.version,'definition',to_jsonb(f)-'dataset_id'-'collection'-'entry_key',
              'text',to_jsonb(t)-'dataset_id'-'collection'-'entry_key')
              FROM knowledge.wiki_entry e
              JOIN LATERAL (SELECT DISTINCT ON(version) * FROM knowledge.wiki_definition
                WHERE dataset_id=e.dataset_id AND collection=e.collection AND entry_key=e.entry_key
                ORDER BY version,(source_database='center') DESC) f ON true
              JOIN LATERAL (SELECT * FROM knowledge.wiki_text WHERE dataset_id=e.dataset_id
                AND collection=e.collection AND entry_key=e.entry_key AND version IN (f.version,'')
                ORDER BY (locale='zh-Hans') DESC,(source_database='center') DESC,(version=f.version) DESC LIMIT 1) t ON true
              WHERE e.dataset_id=%s ORDER BY e.collection,e.entry_key,f.version""", (dataset,))
            def rows():
                for row, in cur:
                    assert row['text']['locale'] == 'zh-Hans' and row['text']['body_html'].strip()
                    yield row
            files['canonical.jsonl.gz'] = dump_rows(root/'canonical.jsonl.gz', rows())
            assert files['canonical.jsonl.gz']['rows'] == 57459
        manifest = {'format':1,'dataset_id':dataset,'dataset_hash':EXPECTED,'read_only':True,'files':files}
        (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        return manifest


def freeze_target(root):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()
    from django.apps import apps
    from django.db import connection
    from pgweb.wiki.manuals import manual_slug
    from bs4 import BeautifulSoup
    params = connection.get_connection_params()
    params.pop('cursor_factory', None)
    root.mkdir(parents=True, exist_ok=False)
    with psycopg2.connect(**params) as conn:
        conn.set_session(isolation_level='REPEATABLE READ', readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user,pg_get_userbyid(datdba),current_setting('transaction_read_only') FROM pg_database WHERE datname=current_database()")
            identity = cur.fetchone()
            assert identity == ('pgweb','pgweb','pgweb','on')
        models = list(apps.get_app_config('wiki').get_models())
        tables = {m._meta.db_table: m._meta.pk.column for m in models}
        assert len(tables) == 35
        tables.update({'core_version':'id','release':'version','release_dataset':'key'})
        files = {}
        for table, pk in sorted(tables.items()):
            with conn.cursor(name='table_export') as cur:
                cur.itersize = 100
                cur.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t ORDER BY {}').format(sql.Identifier(table),sql.Identifier(pk)))
                files[table+'.jsonl.gz'] = dump_rows(root/(table+'.jsonl.gz'), (row for row, in cur))
        with conn.cursor(name='manual_coordinates') as cur:
            cur.itersize=100
            cur.execute('SELECT id,version,file,title,content FROM docs ORDER BY version,file')
            def pages():
                for identity, version, filename, title, content in cur:
                    body = content or ''
                    try:
                        doc = BeautifulSoup(body, 'html.parser')
                        anchors = sorted({tag.get('id') or tag.get('name') for tag in doc.find_all(attrs={'id':True})+doc.find_all('a',attrs={'name':True})})
                    except Exception:
                        anchors = []
                    yield {'id':identity,'version':manual_slug(version),'file':filename,'title':title,'anchors':anchors,'content_sha256':hashlib.sha256(body.encode()).hexdigest()}
            files['manual-pages.jsonl.gz'] = dump_rows(root/'manual-pages.jsonl.gz', pages())
        manifest={'format':1,'database':identity[0] if isinstance(identity,tuple) else 'pgweb','read_only':True,'files':files}
        (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['source','target'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=freeze_source(args.output,os.environ['CENTER_DSN']) if args.kind=='source' else freeze_target(args.output)
    print(json.dumps(result,ensure_ascii=False))
