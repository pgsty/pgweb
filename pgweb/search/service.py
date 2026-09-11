import re
from time import perf_counter
from urllib.parse import quote

from django.core.cache import cache
from django.db import connection
from django.utils.html import escape

from pgweb.core.models import Version
from pgweb.docs.versions import manual_major
from .lexicon import query_text, words
from .models import IndexedPage, SearchEntry
from .taxonomy import GROUP_META, GROUP_OF, KIND_LABEL, normalize_name, resolve_group

PAGE_SIZE = 40
MAX_QUERY = 255
PREFIX = re.compile(r'^([a-z][a-z0-9-]*):(?![:/])\s*', re.I)
# Scope aliases: `pg:` is the current major, `pg17:` a specific one, `ex:` the
# extension catalogue on its own. Manual scopes also include the catalogue,
# so an extension name finds its entry without a prefix.
EXTENSION_SCOPES = ('ex', 'ext', 'pgext')
EXTERNAL_PREFIXES = ('pb', 'pt', 'br', 'patroni', 'pgbouncer', 'pgbackrest')
POPULAR = ('work_mem', 'SELECT', 'jsonb_set', 'pg_stat_activity', '23505', '\\d', 'EXPLAIN',
           'shared_buffers', 'CREATE TABLE', 'pg_dump', 'jsonb', 'wal_level', 'postgis', 'vector')


CATALOG_CACHE_KEY = 'pgweb:docsearch:catalog'


def catalog():
    """(current major, indexed versions). Cached briefly; index_docs clears it."""
    cached = cache.get(CATALOG_CACHE_KEY)
    if cached is not None:
        return cached
    versions = list(Version.objects.order_by('-tree'))
    current = next((int(v.tree) for v in versions if v.current), None)
    # The indexed-page table is small and joins docs on an indexed column;
    # the entry table would be a sequential scan on every request.
    indexed = set(IndexedPage.objects.values_list('page__version', flat=True).distinct())
    versions = sorted((v for v in versions if v.tree in indexed), key=lambda v: manual_major(v.tree), reverse=True)
    result = (current, [{'key': 'pg' + str(manual_major(v.tree)), 'version': manual_major(v.tree), 'current': v.current,
                         'testing': bool(v.testing), 'label': 'PostgreSQL ' + str(manual_major(v.tree)) +
                         (' · 开发版' if v.tree == 0 else ' · 当前' if v.current else ' · 测试版' if v.testing else '')} for v in versions])
    cache.set(CATALOG_CACHE_KEY, result, 60)
    return result


def forget_catalog():
    cache.delete(CATALOG_CACHE_KEY)


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
        if prefix == 'pg' or re.fullmatch(r'pg\d+', prefix) or prefix in EXTENSION_SCOPES:
            scope, term = prefix, term[match.end():].strip()
        elif prefix in EXTERNAL_PREFIXES:
            raise ValueError('第三方组件的文档不在本站索引中，请通过“文档 → 三方文档”访问对应站点。')
        elif prefix != 'kind':
            notice = '未识别的作用域，已按完整搜索词检索。可使用 pg:、pg17: 或 ex:。'
    kind_match = re.match(r'^kind:([a-z]*)\s*(.*)$', term, re.I | re.S)
    if kind_match:
        # "kind:" with no value is an incomplete filter, not a search term.
        kind, term = kind_match.group(1).lower() or kind, kind_match.group(2).strip()
    group = resolve_group(kind)
    if group is None:
        raise ValueError('未知的文档类别。')
    scope = scope.lower()
    if scope in EXTENSION_SCOPES:
        scope, sources, version = 'ex', ('ext',), current
    elif scope == 'pg':
        sources, version = ('pg', 'ext', 'errcode'), current
    elif re.fullmatch(r'pg\d+', scope):
        sources, version = ('pg', 'ext', 'errcode'), int(scope[2:])
    else:
        raise ValueError('未知的文档作用域。请使用 pg:、pg17: 或 ex:。')
    if 'pg' in sources and version not in available:
        raise ValueError('PostgreSQL {} 尚未建立文档索引。请选择已收录的版本。'.format(version or '当前版本'))
    return {'raw': raw, 'term': term, 'scope': scope, 'version': version, 'kind': group,
            'notice': notice, 'sources': sources}


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
    group = GROUP_OF.get(entry.kind, 'guide')
    if entry.source == 'pg' and entry.document_id:
        page = entry.document.page
        version = int(entry.version)
        url = '/docs/{}/{}'.format(page.display_version(), page.file) + ('#' + quote(entry.anchor, safe='-._~') if entry.anchor else '')
        source_label = 'PG' + str(version)
    else:
        version, url, source_label = None, entry.url, ('本站词条' if entry.source == 'errcode' else '扩展目录')
    return {
        'id': entry.id, 'name': entry.name, 'kind': entry.kind, 'kind_label': KIND_LABEL.get(entry.kind, entry.kind),
        'subtype': entry.subtype, 'group': group, 'label': GROUP_META[group]['label'],
        'source': entry.source, 'source_label': source_label, 'version': version,
        'heading': entry.heading, 'signature': entry.signature,
        'snippet': highlight(entry.body, term), 'name_html': highlight(entry.name, term, 500), 'url': url,
        'reason': ('名称精确匹配' if tier == 0 else '别名匹配' if tier == 1 else '名称匹配' if tier == 2 else
                   '近似名称' if tier == 5 else '章节正文' if entry.kind == 'guide' else '定义正文'),
        'variants': variants,
    }


def search(raw='', scope='pg', kind='', offset=0, limit=PAGE_SIZE):
    started = perf_counter()
    current, versions = catalog()
    limit = max(1, min(PAGE_SIZE, int(limit or PAGE_SIZE)))
    result = {'results': [], 'facets': [], 'versions': versions, 'current': current, 'total': 0, 'all_total': 0,
              'next_offset': None, 'error': '', 'notice': '', 'raw': raw, 'scope': scope, 'kind': kind,
              'version': current, 'term': '', 'elapsed_ms': 0}
    try:
        state = parse_query(raw, scope, kind, [v['version'] for v in versions], current)
    except ValueError as exc:
        result['error'] = str(exc)
        return result
    if not versions and 'pg' in state['sources']:
        result['error'] = '文档索引尚未准备好。'
        return result
    result.update({k: v for k, v in state.items() if k != 'sources'})
    name = normalize_name(state['term'])
    tokens = query_text(state['term'])
    # Literal quote delimiters request a contiguous textual phrase.
    phrase = len(name) >= 2 and name.startswith('"') and name.endswith('"')
    literal = name[1:-1] if phrase and name[1:-1].strip() else name
    kinds = GROUP_META[state['kind']]['kinds'] if state['kind'] else []
    parameters = {
        'version': state['version'], 'name': name, 'tokens': tokens,
        'prefix': connection.ops.prep_for_like_query(name) + '%',
        'literal': '%' + connection.ops.prep_for_like_query(literal) + '%',
        'filtered': bool(kinds), 'kinds': kinds, 'offset': offset, 'limit': limit,
        'popular': [normalize_name(n) for n in POPULAR],
    }
    source = ("((e.source = 'pg' AND e.version = %(version)s) OR e.source IN ('ext', 'errcode'))"
              if 'pg' in state['sources'] else "e.source = 'ext'")
    if not name:
        where = 'true'
        tier = 'CASE WHEN name_key = ANY(%(popular)s) AND kind != \'guide\' THEN 0 ELSE 3 END'
    else:
        where = '(e.name_key LIKE %(prefix)s OR e.aliases @> ARRAY[%(name)s]::text[] OR e.vector @@ q.query)'
        if not tokens or phrase or name.startswith('\\'):
            # Symbols and quoted phrases match names and aliases exactly; the
            # body scan only makes sense for a real phrase, not for a lone
            # quote, percent sign or backslash that appears in most chapters.
            literal_operator = 'LIKE' if name.startswith('\\') else 'ILIKE'
            scan = len(literal) >= 2 and any(c.isalnum() for c in literal)
            where = '(e.name_key = %(name)s OR e.aliases @> ARRAY[%(name)s]::text[]'
            where += ' OR (e.kind = \'guide\' AND e.body ' + literal_operator + ' %(literal)s))' if scan else ')'
        tier = """CASE WHEN e.kind != 'guide' AND e.name_key = %(name)s THEN 0
                       WHEN e.kind != 'guide' AND e.aliases @> ARRAY[%(name)s]::text[] THEN 1
                       WHEN e.name_key LIKE %(prefix)s THEN 2 ELSE 3 END"""
    # Group before pagination. Each entity keeps its best definition (a manual
    # definition before the catalogue card); every overload remains available
    # in the preview, and facets count result groups. Prefix matches list the
    # shortest names first (jsonb_set before jsonb_set_lax); text matches by
    # relevance plus, for catalogue rows, their popularity weight.
    sql = """
        WITH q AS (SELECT CASE WHEN %(tokens)s = '' THEN NULL ELSE plainto_tsquery('simple', %(tokens)s) END AS query),
        matched AS (
            SELECT e.id, e.kind, e.source, e.entity_key, e.name_key, {tier} AS tier,
                   CASE WHEN %(name)s = '' THEN 0 ELSE coalesce(ts_rank_cd(e.vector, q.query, 32), 0) + e.weight END AS relevance
            FROM search_searchentry e CROSS JOIN q
            WHERE {source} AND {where}
        ), grouped AS (
            SELECT *, row_number() OVER (PARTITION BY entity_key ORDER BY tier, (source <> 'errcode'), (source = 'ext'), relevance DESC, id) AS choice,
                   count(*) OVER (PARTITION BY entity_key) AS variants FROM matched
        ), chosen AS (SELECT * FROM grouped WHERE choice = 1),
        facet AS (SELECT kind, count(*) AS n FROM chosen GROUP BY kind),
        page AS (
            SELECT * FROM chosen WHERE (%(filtered)s = false OR kind = ANY(%(kinds)s::text[]))
            ORDER BY tier, CASE WHEN tier = 2 THEN length(name_key) ELSE 0 END, relevance DESC, name_key, id
            LIMIT %(limit)s OFFSET %(offset)s
        )
        SELECT (SELECT coalesce(json_agg(row_to_json(page)), '[]'::json) FROM page),
               (SELECT coalesce(json_object_agg(kind, n), '{{}}'::json) FROM facet)
    """.format(tier=tier, where=where, source=source)
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        hits, counts = cursor.fetchone()
        # Fuzzy names are an explicit fallback, bounded to this scope and group.
        if not hits and offset == 0 and re.fullmatch('[a-zA-Z_][a-zA-Z0-9_]{3,80}', name):
            cursor.execute("""
                SELECT DISTINCT ON (entity_key) id, kind, entity_key,
                    similarity(name_key, %(name)s) AS score
                FROM search_searchentry e
                WHERE {source} AND kind != 'guide'
                    AND (%(filtered)s = false OR kind = ANY(%(kinds)s::text[])) AND name_key %% %(name)s
                ORDER BY entity_key, score DESC, id
            """.format(source=source), parameters)
            fuzzy = sorted(cursor.fetchall(), key=lambda r: -r[3])[:8]
            hits = [{'id': r[0], 'kind': r[1], 'tier': 5, 'variants': 1} for r in fuzzy]
            if hits:
                result['notice'] = '没有精确结果，以下是名称相近的条目。'
                counts = {}
                for hit in hits:
                    counts[hit['kind']] = counts.get(hit['kind'], 0) + 1
    entries = {e.pk: e for e in SearchEntry.objects.filter(pk__in=[h['id'] for h in hits])
               .select_related('document__page').defer('vector', 'preview', 'document__page__content')}
    # A row can vanish between ranking and fetching while the catalogue is being rebuilt.
    result['results'] = [entry_data(entries[h['id']], state['term'], h['tier'], h['variants']) for h in hits if h['id'] in entries]
    groups = {}
    for key, n in counts.items():
        groups[GROUP_OF.get(key, 'guide')] = groups.get(GROUP_OF.get(key, 'guide'), 0) + n
    result['facets'] = [{'key': key, 'label': meta['label'], 'hint': meta['hint'], 'count': groups.get(key, 0)}
                        for key, meta in GROUP_META.items()]
    result['total'] = groups.get(state['kind'], 0) if state['kind'] else sum(groups.values())
    result['all_total'] = sum(groups.values())
    if offset + limit < result['total']:
        result['next_offset'] = offset + limit
    result['elapsed_ms'] = round((perf_counter() - started) * 1000)
    return result


def preview(entry):
    data = entry_data(entry)
    data['html'] = entry.preview
    others = (SearchEntry.objects.filter(entity_key=entry.entity_key).select_related('document__page')
              .defer('vector', 'preview', 'document__page__content').order_by('-version', 'id'))
    versions, variants, catalogue = {}, [], None
    for other in others:
        if other.source != 'pg':
            # Catalogue and 百科 entries have no version line of their own.
            if other.source == 'ext' and other.id != entry.id and catalogue is None:
                catalogue = entry_data(other)
            continue
        if entry.source == 'pg' and other.version == entry.version:
            if other.id != entry.id:
                item = entry_data(other)
                if all((v['signature'], v['url']) != (item['signature'], item['url']) for v in variants):
                    variants.append(item)
        elif str(other.version) not in versions:
            versions[str(other.version)] = entry_data(other)
    # The version line of the preview: every major that documents this entity,
    # newest first, the one being read marked as current.
    line = [{'version': v['version'], 'url': v['url'], 'id': v['id'], 'current': False} for v in versions.values()]
    if data['version'] is not None:
        line.append({'version': data['version'], 'url': data['url'], 'id': data['id'], 'current': True})
    data['versions'] = sorted(line, key=lambda v: -v['version'])
    data['other_versions'] = list(versions.values())
    data['definitions'] = variants
    data['catalog'] = catalogue
    return data
