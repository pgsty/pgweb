"""Version-specific previews for the original Wiki collections."""
import re

from bs4 import BeautifulSoup
from django.db.models import JSONField
from django.db.models.expressions import RawSQL
from django.template.loader import render_to_string

from pgweb.wiki import models
from pgweb.wiki.center_text import localized_html
from pgweb.wiki.guc_common import human_value


MODELS = {'catalog': models.CatalogRelation, 'guc': models.GucParameter,
          'wait': models.WaitEvent, 'func': models.PgFunction, 'errcode': models.ErrorCode}


def number(major):
    return int(major) if major.isdigit() else major


def result_summaries(entries, major):
    """Fetch only the selected snapshots, in one query per core collection."""
    output = {}
    for source, model in MODELS.items():
        if source == 'errcode':
            continue  # SQLSTATE definitions are invariant; cases retain their build.
        selected = [e for e in entries if e.source == source]
        identities = {e.url.rstrip('/').rsplit('/', 1)[-1] if source == 'func'
                      else e.entity_key.split(':', 1)[1]: e.id for e in selected}
        if not identities:
            continue
        key = 'key' if source == 'guc' else 'pk'
        rows = model.objects.filter(**{key + '__in': identities}).annotate(
            selected_snapshot=RawSQL('versions -> %s', [str(major)], output_field=JSONField()))
        for identity, snapshot in rows.values_list(key, 'selected_snapshot'):
            if not snapshot:
                continue
            description = snapshot.get('description_zh') or snapshot.get('description') or ''
            if isinstance(description, list):
                description = ' '.join(description)
            signature = ''
            if source == 'guc':
                signature = ' · '.join([snapshot.get('vartype', ''), snapshot.get('context', ''),
                                        human_value(snapshot.get('boot_val'), snapshot.get('unit'))])
            elif source == 'func':
                signature = ' · '.join(s['text'] for s in snapshot.get('signatures', [])[:2])
            output[identities[identity]] = (description, signature)
    return output


def build(entry, wanted, current):
    model = MODELS[entry.source]
    identity = entry.entity_key.split(':', 1)[1]
    if entry.source == 'func':
        # The function name and stable reader slug are not always identical.
        identity = entry.url.rstrip('/').rsplit('/', 1)[-1]
    elif entry.source == 'errcode':
        identity = identity.upper()
    item = model.objects.get(**({'key': identity.lower()} if entry.source == 'guc' else {'pk': identity}))
    present = list(item.present_in)
    wanted = str(wanted or current)
    wanted = '20' if wanted == 'devel' else wanted
    if not re.fullmatch(r'\d+(?:\.\d+)?', wanted):
        wanted = str(current)
    if wanted.endswith('.0') and int(float(wanted)) >= 10:
        wanted = str(int(float(wanted)))
    missing = wanted not in present
    snapshot = {} if entry.source == 'errcode' else item.versions.get(wanted, {})
    facts, signatures, description, body = [], [], '', ''
    if not missing:
        if entry.source == 'catalog':
            facts = [('类别', item.kind_label), ('字段数', len(snapshot.get('columns', [])))]
            signatures = [' · '.join(c['name'] for c in snapshot.get('columns', [])[:24])]
        elif entry.source == 'guc':
            facts = [('类型', snapshot.get('vartype', '')), ('上下文', snapshot.get('context', '')),
                     ('启动默认值', human_value(snapshot.get('boot_val'), snapshot.get('unit')))]
        elif entry.source == 'wait':
            facts = [('类型', snapshot.get('type', '')), ('名称', snapshot.get('name', ''))]
        elif entry.source == 'func':
            signatures = [s['text'] for s in snapshot.get('signatures', [])[:8]]
            facts = [('签名数', len(snapshot.get('signatures', [])))]
        else:
            description = (item.texts.get('zh') or {}).get('summary') or item.summary_zh
            facts = [('条件名', item.condition_name), ('源码定义', '该版已收录')]
        if snapshot:
            description = snapshot.get('description_zh') or snapshot.get('short_desc_zh') or snapshot.get('description', '')
            if isinstance(description, list):
                description = ' '.join(description[:2])
            translated = snapshot.get('center_zh') or {}
            markup = translated.get('body_html') or snapshot.get('doc_html') or ''
            if markup:
                soup = BeautifulSoup(markup, 'html.parser')
                paragraphs = [p for p in soup.find_all('p') if not p.find_parent(['table', 'pre'])][:2]
                body = localized_html(''.join(map(str, paragraphs)), '/docs/' + wanted + '/', translated.get('link_map'))
    payload = {'major': wanted, 'missing': missing, 'description': description, 'body': body,
               'facts': facts, 'signatures': signatures,
               'shared_evidence': entry.source == 'errcode'}
    return {'url': item.url + '?v=' + wanted, 'version': number(wanted),
            'html': render_to_string('search/wiki_preview.html', payload),
            'signature': ' · '.join(str(v) for _, v in facts if v != '') if facts else '',
            'versions': [{'version': number(m), 'major': m, 'label': m, 'id': entry.id,
                          'url': item.url + '?v=' + m, 'current': m == wanted}
                         for m in sorted(set(present + [wanted]), key=float, reverse=True)],
            'other_versions': [], 'definitions': [], 'catalog': None}
