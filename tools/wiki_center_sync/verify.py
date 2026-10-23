"""Compare every Chinese version payload, then exercise fixed local HTTP routes."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from html.parser import HTMLParser
from urllib.parse import quote,parse_qs,urlsplit


def rows(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def version_key(value):
    return tuple(map(int,value.split('.')))


class RenderedText(HTMLParser):
    """Extract visible text and the active version without building a DOM tree."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.active_versions=[];self.hidden=0

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('script','style'): self.hidden+=1
        if tag=='a' and attrs.get('aria-current') in ('true','page'):
            self.active_versions.extend(parse_qs(urlsplit(attrs.get('href','')).query).get('v',[]))

    def handle_endtag(self,tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)

    def handle_data(self,value):
        if not self.hidden:self.parts.append(value)


def data(args):
    from bs4 import BeautifulSoup
    from django.apps import apps
    from django.db import connection
    from pgweb.wiki.topics import TOPICS
    expected={}; canonical_count=0
    for row in rows(args.source/'canonical.jsonl.gz'):
        canonical_count+=1
        if row['collection']=='sql' and row['key']=='wait':
            continue
        key=row['key']
        if row['collection']=='sql' and key=='wait-for': key='wait'
        if row['collection'] in ('catalog','guc','waitevent'):
            key=row['definition']['source_key']
        identity=(row['collection'],key,row['version'])
        assert identity not in expected
        expected[identity]=sha(row['text']['body_html'])
    by_table={m._meta.db_table:m for m in apps.get_app_config('wiki').get_models()}
    mapping={kind:spec['model'] for kind,spec in TOPICS.items()}
    mapping.update({kind:by_table[table] for kind,table in
                    [('sql','sqlcmd'),('sqlstate','sqlstate'),('func','func'),('catalog','catalog'),
                     ('guc','guc'),('waitevent','waitevent'),('lock','lock_mode')]})
    actual={}; counts={}; plan=[]
    for collection,model in mapping.items():
        versions=set();entities=0; total=0
        for entity in model.objects.all().iterator(chunk_size=10):
            entities+=1
            key=str(entity.pk)
            if collection=='sqlstate':
                text=entity.texts['zh']['center_zh']
                snapshots={version:{'center_zh':text} for version in entity.texts['zh']['manual_versions']}
            else:
                snapshots=entity.versions
            for version,snapshot in snapshots.items():
                identity=(collection,key,version)
                actual[identity]=sha(snapshot['center_zh']['body_html'])
                total+=1;versions.add(version)
            if collection=='waitevent':
                url='/wiki/waitevent/{}/{}/'.format(entity.type_slug,entity.name)
            else:
                url='/wiki/{}/{}/'.format(collection,quote(key,safe='_-'))
            latest=max(snapshots,key=version_key)
            soup=BeautifulSoup(snapshots[latest]['center_zh']['body_html'],'html.parser')
            # SQL places navigation between its synopsis and sections. Check
            # each source block, not a fragment spanning separate UI sections.
            blocks=soup.find_all(['pre','section'],recursive=False) if collection=='sql' else [soup]
            fragments=[]
            for block in blocks:
                body=re.sub(r'\s+','',block.get_text(' ',strip=True))
                starts=sorted({0,max(0,len(body)//2-40),max(0,len(body)-80)})
                fragments.extend(body[start:start+80] for start in starts if body[start:start+80])
            plan.append({'url':url,'collection':collection,'key':key,'kind':'entity'})
            plan.append({'url':url+'?v='+latest,'collection':collection,'key':key,
                         'version':latest,'kind':'latest','body_sha256':actual[(collection,key,latest)],
                         'body_fragments':fragments})
        counts[collection]={'entities':entities,'versions':total}
        if collection!='sqlstate':
            parameter='present' if collection in ('catalog','guc','waitevent','sql','func') else 'v'
            for version in sorted(versions,key=version_key):
                plan.append({'url':'/wiki/{}/?{}={}'.format(collection,parameter,version),'collection':collection,
                             'version':version,'kind':'index'})
        plan.append({'url':'/wiki/'+collection+'/','collection':collection,'kind':'index'})
    assert expected==actual, {'missing':len(expected.keys()-actual.keys()),
                             'extra':len(actual.keys()-expected.keys()),
                             'changed':sum(actual.get(k)!=v for k,v in expected.items())}
    for version in ['6.3','6.4','6.5','7.0','7.1','7.2','7.3','7.4','8.0','8.1','8.2','8.3','8.4',
                    '9.0','9.1','9.2','9.3','9.4','9.5','9.6',*map(str,range(10,21))]:
        plan.append({'url':'/wiki/versions/'+version+'/','kind':'version'})
    plan.extend([{'url':'/wiki/','kind':'index'},{'url':'/wiki/versions/','kind':'index'}])
    with connection.cursor() as cur:
        cur.execute('SELECT current_database()');database=cur.fetchone()[0]
    result={'database':database,'source_canonical_rows':canonical_count,
            'checked_versions':len(actual),'canonical_body_hash_parity':True,'counts':counts,
            'entities':sum(c['entities'] for c in counts.values()),'http_plan':len(plan)}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    args.plan.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    return result


def http(args):
    import requests
    bases=args.base.split(',')
    assert bases and all(re.fullmatch(r'http://127\.0\.0\.1:\d+',base) for base in bases)
    plan=json.loads(args.plan.read_text());errors=[];counts=Counter();records=[]
    archive=gzip.open(args.archive,'wt',encoding='utf-8') if args.archive else None
    checked_at=datetime.now(timezone.utc).isoformat()
    def check(item):
        with requests.Session() as session:
            session.trust_env=False
            base=bases[int(sha(item['url'])[:8],16)%len(bases)]
            response=session.get(base+item['url'],timeout=90,allow_redirects=False)
        error=None
        wanted=item.get('expected_status',200)
        if response.status_code!=wanted:
            error='HTTP '+str(response.status_code)
        elif wanted in (301,302):
            location=response.headers.get('Location','')
            if location!=item.get('location') or not location.startswith('/wiki/'):
                error='redirect destination mismatch'
            else:
                with requests.Session() as redirect_session:
                    redirect_session.trust_env=False
                    if redirect_session.get(base+location,timeout=90,allow_redirects=False).status_code!=200:
                        error='redirect target failed'
        elif '<html' not in response.text.lower() or not re.search(r'<html[^>]*lang=[\"\']zh',response.text):
            error='missing Chinese HTML'
        elif item['kind'] in ('entity','latest'):
            doc=RenderedText();doc.feed(response.text)
            text=' '.join(doc.parts)
            if not re.search('[\u3400-\u9fff]',text): error='no Chinese body'
            normalized=re.sub(r'\s+','',text)
            if any(fragment not in normalized for fragment in item.get('body_fragments',[])):
                error='canonical Chinese body fragment missing'
            if item.get('version') and item['collection']!='sqlstate':
                # The comparison dropdown selects the other version; the ribbon
                # identifies the version actually being displayed.
                if doc.active_versions and item['version'] not in doc.active_versions:
                    error='version selector mismatch'
        return item,response,error
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(check,item) for item in plan]):
                try:
                    item,response,error=future.result()
                except Exception as exc:
                    errors.append({'error':repr(exc)});continue
                counts[str(response.status_code)]+=1
                if error:
                    errors.append({'url':item['url'],'error':error})
                    print(json.dumps({'failed':item['url'],'error':error}),flush=True)
                records.append({'url':item['url'],'status':response.status_code,'bytes':len(response.content),
                                'sha256':sha(response.text)})
                if archive and not error and '?' not in item['url']:
                    archive.write(json.dumps({'url':item['url'],'status':response.status_code,'html':response.text,
                                              'sha256':sha(response.text),'checked_at':checked_at,
                                              'location':response.headers.get('Location','')},ensure_ascii=False)+'\n')
                if len(records)%250==0: print(json.dumps({'checked':len(records),'errors':len(errors)}),flush=True)
    finally:
        if archive: archive.close()
    result={'base':args.base,'checked':len(records),'expected':len(plan),'status_counts':dict(counts),'errors':errors,
            'records':records}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if errors: raise ValueError(str(len(errors))+' HTTP acceptance errors; see '+str(args.output))
    return {k:v for k,v in result.items() if k!='records'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['data','http'])
    p.add_argument('--source',type=Path)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--base')
    p.add_argument('--archive',type=Path)
    p.add_argument('--workers',type=int,default=6)
    args=p.parse_args()
    if args.mode=='data':
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE','pgweb.settings')
        import django
        django.setup()
        result=data(args)
    else: result=http(args)
    print(json.dumps(result,ensure_ascii=False))
