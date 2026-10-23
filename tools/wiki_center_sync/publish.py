"""Publish sealed center Chinese snapshots through PGWeb's native importers."""
import argparse
import gzip
import hashlib
import json
import io
import os
from pathlib import Path
import sys


def load(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def load_verified(path,item):
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=item['sha256']:
        raise ValueError('Snapshot hash changed: '+str(path))
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)


def native(kind):
    from pgweb.wiki import catalog_importer, guc_importer, waitevent_importer
    from pgweb.wiki import sqlcmd_importer, func_importer, importer, lock_importer
    return {'catalog':catalog_importer,'guc':guc_importer,'waitevent':waitevent_importer,
            'sqlcmd':sqlcmd_importer,'func':func_importer,'sqlstate':importer,'lock':lock_importer}[kind]


def validate_manifest(path):
    manifest=load(path)
    from tools.wiki_center_sync.freeze import EXPECTED
    if manifest['dataset_hash']!=EXPECTED or manifest['format']!=1:
        raise ValueError('Unrecognized frozen source dataset')
    domains=[]
    for item in manifest['files']:
        filename=path.parent/item['path']
        if hashlib.sha256(filename.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Snapshot hash changed: '+str(filename))
        if item['kind']=='site-search':
            continue
        snapshot=load_verified(filename,item)
        if item['kind']=='topic':
            from pgweb.wiki.topic_importer import prepare
            topic,_=prepare(snapshot)
            domains.append(topic)
        elif item['kind']=='releases':
            from pgweb.docs.compare_store import _validate
            _validate(snapshot,'releases')
            domains.append('releases')
        else:
            native(item['kind']).validate(snapshot)
            domains.append(item['kind'])
    from pgweb.wiki.topics import TOPICS
    wanted=set(TOPICS)|{'catalog','guc','waitevent','sqlcmd','func','sqlstate','lock','releases'}
    if set(domains)!=wanted or len(domains)!=len(wanted):
        raise ValueError('Publication must contain each of the 30 collections exactly once')
    return manifest


def guard_target(expected, *, definition_search=False, site_search=False):
    from django.apps import apps
    from django.db import connection
    tables={m._meta.db_table for m in apps.get_app_config('wiki').get_models()} | {
        'release','release_entry','release_patch','release_dataset'}
    if definition_search:
        tables.add('search_searchentry')
    if site_search:
        tables.update(('webpages','sites'))
    tables=sorted(tables)
    with connection.cursor() as cur:
        cur.execute("SET LOCAL TIME ZONE 'Asia/Shanghai'")
        # Readers continue; writes cannot race the drift check and publication.
        cur.execute('LOCK TABLE '+','.join(connection.ops.quote_name(t) for t in tables)+' IN SHARE ROW EXCLUSIVE MODE')
        if expected:
            before=load(expected)
            for table in tables:
                cur.execute('WITH r AS MATERIALIZED (SELECT md5(to_jsonb(t)::text) AS digest FROM '+
                            connection.ops.quote_name(table)+" t) SELECT count(*),md5(coalesce(string_agg(digest,'' ORDER BY digest),'')) FROM r")
                count,digest=cur.fetchone()
                if before['tables']['public.'+table]!={'rows':count,'content_md5':digest}:
                    raise ValueError('Target drifted before publication: '+table)


def site_search(path,item):
    """Replay verified HTML through the existing crawler parser and native writer."""
    from django.db import connection
    from datetime import datetime
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/search/crawler'))
    from lib.basecrawler import BaseSiteCrawler
    crawler=BaseSiteCrawler('pgsql.cc',connection.connection,1)
    count=0
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=item['sha256']:
        raise ValueError('Site search snapshot changed')
    with gzip.open(io.BytesIO(data),'rt',encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if not row['url'].startswith('/wiki/') or row['status'] not in (200,301,302):
                raise ValueError('Site snapshot outside Wiki scope')
            if hashlib.sha256(row['html'].encode()).hexdigest()!=row['sha256']:
                raise ValueError('Site snapshot HTML hash mismatch')
            if row['status'] in (301,302):
                if not row.get('location','').startswith('/wiki/'):
                    raise ValueError('Site snapshot redirect outside Wiki scope')
                # Native crawler retires an indexed redirect, leaving its actual
                # destination to the separately verified canonical page record.
                crawler.fetch_page=lambda url: (1,row['location'],None)
                crawler.queue_url=lambda url: None
                crawler.crawl_page(row['url'],0.5,False)
                count+=1
                continue
            crawler.page=crawler.parse_html(row['html'])
            crawler.save_page(row['url'],datetime.fromisoformat(row['checked_at']),0.5,False)
            count+=1
    with connection.cursor() as cur:
        cur.execute('UPDATE sites SET pagecount=(SELECT count(*) FROM webpages WHERE site=1) WHERE id=1')
    return {'pages':count,'updated':crawler.pages_updated,'created':crawler.pages_new,
            'retired_redirects':crawler.pages_deleted}


def publish(args):
    from django.db import connection, transaction
    manifest=validate_manifest(args.manifest)
    with connection.cursor() as cur:
        cur.execute("SELECT current_database(),current_user,pg_get_userbyid(datdba),inet_server_addr(),(SELECT system_identifier::text FROM pg_control_system()) FROM pg_database WHERE datname=current_database()")
        database,user,owner,address,cluster=cur.fetchone()
    if not (user==owner=='pgweb' and address is None and cluster=='7637324916256241865'):
        raise ValueError('Database role, owner, local connection or cluster identity differs')
    if not (database=='pgweb' or database.startswith('test_pgweb_wiki_center_')):
        raise ValueError('Database outside approved local destination scope')
    if database=='pgweb' and args.write and not args.expected:
        raise ValueError('Live publication requires a fresh target drift fingerprint')
    report={'database':database,'write':args.write,'dataset_hash':manifest['dataset_hash'],'imports':{}}
    with transaction.atomic():
        guard_target(args.expected, definition_search=args.search,
                     site_search=any(item['kind']=='site-search' for item in manifest['files']))
        for item in manifest['files']:
            kind=item['kind']; path=args.manifest.parent/item['path']
            if kind=='site-search':
                report['site_search']=site_search(path,item)
                continue
            snapshot=load_verified(path,item)
            if kind=='topic':
                from pgweb.wiki.topic_importer import prepare,apply
                topic,rows=prepare(snapshot)
                result=apply(topic,rows)
                key=topic
            elif kind=='releases':
                from pgweb.docs.compare_store import import_snapshot
                result=import_snapshot(snapshot,language='zh',complete=True)
                key=kind
            else:
                result=native(kind).import_snapshot(snapshot)
                key=kind
            report['imports'][key]=result
            print(json.dumps({'imported':key},ensure_ascii=False),flush=True)
        if args.search:
            from pgweb.search import indexer
            from pgweb.wiki.version_search import rebuild_versions
            report['search']={}
            for name in ('errcodes','catalog','guc','waitevents','sqlcmd','func','locks','topics'):
                report['search'][name]=getattr(indexer,'rebuild_'+name)()
                print(json.dumps({'indexed':name}),flush=True)
            report['search']['versions']=rebuild_versions()
        if not args.write:
            transaction.set_rollback(True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2,default=str)+'\n')
    return {'database':database,'committed':args.write,'report':str(args.report)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--expected',type=Path)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--write',action='store_true')
    p.add_argument('--search',action='store_true')
    args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','pgweb.settings')
    import django
    django.setup()
    print(json.dumps(publish(args),ensure_ascii=False))
