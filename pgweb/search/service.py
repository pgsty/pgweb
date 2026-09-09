import re
from time import perf_counter
from urllib.parse import quote

from django.db import connection
from django.utils.html import escape

from pgweb.core.models import Version
from .lexicon import query_text, words
from .models import SearchEntry
from .taxonomy import KIND_META, KIND_ALIASES, normalize_name

PAGE_SIZE = 40
MAX_QUERY = 255
PREFIX = re.compile(r'^([a-z][a-z0-9-]*):(?![:/])\s*', re.I)
POPULAR = ('work_mem', 'SELECT', 'jsonb_set', 'pg_stat_activity', '23505', '\\d', 'EXPLAIN',
           'shared_buffers', 'CREATE TABLE', 'pg_dump', 'jsonb', 'wal_level')


def catalog():
    versions = list(Version.objects.order_by('-tree'))
    current = next((int(v.tree) for v in versions if v.current), None)
    indexed = set(SearchEntry.objects.values_list('version', flat=True).distinct())
    versions = [v for v in versions if v.tree in indexed]
    return current, [{'key': 'pg' + str(int(v.tree)), 'version': int(v.tree), 'current': v.current,
                      'testing': bool(v.testing), 'label': 'PostgreSQL ' + str(int(v.tree)) +
                      (' · 当前' if v.current else ' · 测试版' if v.testing else '')} for v in versions]


def parse_query(raw, scope='pg', kind='', available=(), current=None):
    if len(raw) > MAX_QUERY:
        raise ValueError('搜索词最多 255 个字符。')
    if any(ord(c) < 32 and c not in '\t\n\r' for c in raw):
        raise ValueError('搜索词包含无效控制字符。')
    term = raw.strip()
    notice = ''
    match = PREFIX.match(term)
    if match:
        prefix = match.group(1).lower()
        if prefix == 'pg' or re.fullmatch(r'pg\d+', prefix):
            scope, term = prefix, term[match.end():].strip()
        elif prefix in ('pb', 'pt', 'br', 'ex', 'patroni', 'pgbouncer', 'pgbackrest'):
            raise ValueError('此入口检索 PostgreSQL 官方手册。第三方文档请通过“文档 → 三方文档”访问。')
        elif prefix != 'kind':
            notice = '未识别的作用域，已按完整搜索词检索。可使用 pg: 或 pg18:。'
    kind_match = re.match(r'^kind:([a-z]+)\s*(.*)$', term, re.I | re.S)
    if kind_match:
        kind, term = kind_match.group(1).lower(), kind_match.group(2).strip()
    kind = KIND_ALIASES.get(kind, kind)
    if kind and kind not in KIND_META:
        raise ValueError('未知的文档类别。')
    scope = scope.lower()
    if scope == 'pg':
        version = current
    elif re.fullmatch(r'pg\d+', scope):
        version = int(scope[2:])
    else:
        raise ValueError('未知的文档作用域。请使用 pg: 或 pg18:。')
    if version not in available:
        raise ValueError('PostgreSQL {} 尚未建立文档索引。请选择已收录的版本。'.format(version or '当前版本'))
    return {'raw': raw, 'term': term, 'scope': scope, 'version': version, 'kind': kind, 'notice': notice}


def highlight(value, term, limit=190):
    tokens = [] if term.startswith('\\') else words(term, query=True)
    needles = sorted(set([term.strip(), *tokens]), key=len, reverse=True)
    needles = [n for n in needles if n]
    position = min((value.casefold().find(n.casefold()) for n in needles if n.casefold() in value.casefold()), default=0)
    start = max(0, position - 45) if len(value) > limit else 0
    excerpt = value[start:start + limit]
    pattern = re.compile('|'.join(re.escape(n) for n in needles), re.I) if needles else None
    if pattern:
        parts, previous = [], 0
        for match in pattern.finditer(excerpt):
            parts.extend((str(escape(excerpt[previous:match.start()])), '<mark>' + str(escape(match.group())) + '</mark>'))
            previous = match.end()
        parts.append(str(escape(excerpt[previous:])))
        rendered = ''.join(parts)
    else:
        rendered = str(escape(excerpt))
    return ('…' if start else '') + rendered + ('…' if start + limit < len(value) else '')


def entry_data(entry, term='', tier=3, variants=1):
    page = entry.document.page
    base = '/docs/{}/{}'.format(int(entry.version), page.file)
    return {
        'id': entry.id, 'name': entry.name, 'kind': entry.kind, 'subtype': entry.subtype,
        'label': KIND_META[entry.kind]['label'], 'icon': KIND_META[entry.kind]['icon'],
        'version': int(entry.version), 'heading': entry.heading, 'signature': entry.signature,
        'snippet': highlight(entry.body, term), 'name_html': highlight(entry.name, term, 500),
        'url': base + ('#' + quote(entry.anchor, safe='-._~') if entry.anchor else ''),
        'reason': ('名称精确匹配' if tier == 0 else '别名匹配' if tier == 1 else '名称匹配' if tier == 2 else
                   '近似名称' if tier == 5 else '章节正文' if entry.kind == 'guide' else '定义正文'),
        'variants': variants,
    }


def search(raw='', scope='pg', kind='', offset=0):
    started = perf_counter()
    current, versions = catalog()
    result = {'results': [], 'facets': [], 'versions': versions, 'current': current, 'total': 0,
              'next_offset': None, 'error': '', 'notice': '', 'raw': raw, 'scope': scope, 'kind': kind,
              'version': current, 'term': '', 'elapsed_ms': 0}
    if not versions:
        result['error'] = '文档索引尚未准备好。'
        return result
    try:
        state = parse_query(raw, scope, kind, [v['version'] for v in versions], current)
    except ValueError as exc:
        result['error'] = str(exc)
        return result
    result.update(state)
    name = normalize_name(state['term'])
    tokens = query_text(state['term'])
    # Literal quote delimiters request a contiguous textual phrase.
    phrase = len(name) >= 2 and name.startswith('"') and name.endswith('"')
    literal = name[1:-1] if phrase and name[1:-1].strip() else name
    parameters = {
        'version': state['version'], 'name': name, 'tokens': tokens,
        'prefix': connection.ops.prep_for_like_query(name) + '%',
        'literal': '%' + connection.ops.prep_for_like_query(literal) + '%',
        'kind': state['kind'], 'offset': offset, 'limit': PAGE_SIZE,
        'popular': [normalize_name(n) for n in POPULAR],
    }
    if not name:
        where = 'true'
        tier = 'CASE WHEN name_key = ANY(%(popular)s) AND kind != \'guide\' THEN 0 ELSE 3 END'
    else:
        where = '(e.name_key LIKE %(prefix)s OR e.aliases @> ARRAY[%(name)s]::text[] OR e.vector @@ q.query)'
        if not tokens or phrase or name.startswith('\\'):
            literal_operator = 'LIKE' if name.startswith('\\') else 'ILIKE'
            where = '(e.name_key = %(name)s OR e.aliases @> ARRAY[%(name)s]::text[] OR (e.kind = \'guide\' AND e.body ' + literal_operator + ' %(literal)s))'
        tier = """CASE WHEN e.kind != 'guide' AND e.name_key = %(name)s THEN 0
                       WHEN e.kind != 'guide' AND e.aliases @> ARRAY[%(name)s]::text[] THEN 1
                       WHEN e.name_key LIKE %(prefix)s THEN 2 ELSE 3 END"""
    # Group before pagination. Each group keeps its best matching definition/fragment;
    # every overload remains available in the preview, and facets count result groups.
    sql = """
        WITH q AS (SELECT plainto_tsquery('simple', %(tokens)s) AS query),
        matched AS (
            SELECT e.id, e.kind, e.entity_key, e.name_key, {tier} AS tier,
                   ts_rank_cd(e.vector, q.query, 32) AS relevance
            FROM search_searchentry e CROSS JOIN q
            WHERE e.version = %(version)s AND {where}
        ), grouped AS (
            SELECT *, row_number() OVER (PARTITION BY entity_key ORDER BY tier, relevance DESC, id) AS choice,
                   count(*) OVER (PARTITION BY entity_key) AS variants FROM matched
        ), chosen AS (SELECT * FROM grouped WHERE choice = 1),
        facet AS (SELECT kind, count(*) AS n FROM chosen GROUP BY kind),
        page AS (
            SELECT * FROM chosen WHERE (%(kind)s = '' OR kind = %(kind)s)
            ORDER BY tier, relevance DESC, name_key, id LIMIT %(limit)s OFFSET %(offset)s
        )
        SELECT (SELECT coalesce(json_agg(row_to_json(page)), '[]'::json) FROM page),
               (SELECT coalesce(json_object_agg(kind, n), '{{}}'::json) FROM facet)
    """.format(tier=tier, where=where)
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        hits, counts = cursor.fetchone()
        # Fuzzy names are an explicit fallback, bounded to this version and kind.
        if not hits and offset == 0 and re.fullmatch('[a-zA-Z_][a-zA-Z0-9_]{3,80}', name):
            cursor.execute("""
                SELECT DISTINCT ON (entity_key) id, kind, entity_key,
                    similarity(name_key, %(name)s) AS score
                FROM search_searchentry
                WHERE version = %(version)s AND kind != 'guide'
                    AND (%(kind)s = '' OR kind = %(kind)s) AND name_key %% %(name)s
                ORDER BY entity_key, score DESC, id
            """, parameters)
            fuzzy = sorted(cursor.fetchall(), key=lambda r: -r[3])[:8]
            hits = [{'id': r[0], 'kind': r[1], 'tier': 5, 'variants': 1} for r in fuzzy]
            if hits:
                result['notice'] = '没有精确结果，以下是本版本中名称相近的条目。'
                counts = {}
                for hit in hits:
                    counts[hit['kind']] = counts.get(hit['kind'], 0) + 1
    entries = {e.pk: e for e in SearchEntry.objects.filter(pk__in=[h['id'] for h in hits])
               .select_related('document__page').defer('vector', 'preview', 'document__page__content')}
    result['results'] = [entry_data(entries[h['id']], state['term'], h['tier'], h['variants']) for h in hits]
    result['facets'] = [dict(meta, count=counts.get(key, 0)) for key, meta in KIND_META.items()]
    result['total'] = counts.get(state['kind'], 0) if state['kind'] else sum(counts.values())
    result['all_total'] = sum(counts.values())
    if offset + PAGE_SIZE < result['total']:
        result['next_offset'] = offset + PAGE_SIZE
    result['elapsed_ms'] = round((perf_counter() - started) * 1000)
    return result


def preview(entry):
    data = entry_data(entry)
    data['html'] = entry.preview
    others = (SearchEntry.objects.filter(entity_key=entry.entity_key).select_related('document__page')
              .defer('vector', 'preview', 'document__page__content').order_by('-version', 'id'))
    versions, variants = {}, []
    for other in others:
        if other.version == entry.version:
            if other.id != entry.id:
                item = entry_data(other)
                if all((v['signature'], v['url']) != (item['signature'], item['url']) for v in variants):
                    variants.append(item)
        elif str(other.version) not in versions:
            versions[str(other.version)] = entry_data(other)
    data['other_versions'] = list(versions.values())
    data['definitions'] = variants
    return data
