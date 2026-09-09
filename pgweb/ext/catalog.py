"""The extension catalog reads only pgext.universe and pgext.doc.

Everything the pages show comes from those two tables plus the display
constants below: category names, blurbs and colours, dimension labels,
and the hue scale for licences, languages and repositories (all shared
with pgext/server/web). The URL helpers live here too, so views,
templates and the Markdown link rewriter agree on one scheme:

    /ext/                        catalogue: search, filters, the list
    /ext/list/                   every index on one page
    /ext/category/  license/  language/  repo/      one index each
    /ext/<code>/                 one functional category, e.g. /ext/gis/
    /ext/license/<value>/  language/<value>/  repo/<value>/
    /e/<name>/                   one extension
"""

from collections import Counter
from html import escape
from urllib.parse import quote, urlencode, urlsplit

from django.core.cache import cache
from django.db import connection
from django.utils.safestring import mark_safe


# code: (zh name, en name, colour, zh blurb, en blurb). Canonical order.
CATEGORIES = {
    'TIME': ('时序与时态', 'Time-Series & Temporal', '#b97e0c',
             '时序数据库 TimescaleDB，时态表与版本控制表，定时任务与异步后台任务调度。',
             'TimescaleDB, versioned and temporal tables, crontab, async and background job schedulers.'),
    'GIS': ('地理空间', 'Geospatial', '#2f9e4f',
            'PostGIS 地理空间类型、函数与索引，天球索引 Q3C，OGR FDW，路径规划与地理编码。',
            'GeoSpatial data types, operators and indexes, hexagonal indexing, OGR data FDW, GeoIP and MobilityDB.'),
    'RAG': ('AI 与向量', 'AI & Vectors', '#7c3aed',
            '向量数据库与 IVFFlat、HNSW、DiskANN 索引，相似度函数，库内机器学习与推理。',
            'Vector database with IVFFlat, HNSW and DiskANN indexes, similarity functions, AI and ML inside SQL.'),
    'FTS': ('全文检索', 'Full-Text Search', '#e8590c',
            'ElasticSearch 替代方案 pg_search 与 BM25，中文分词，Hunspell 词典，模糊检索与 n-gram 索引。',
            'ElasticSearch alternatives with BM25, 2-gram and 3-gram fuzzy search, Zhparser and Hunspell dictionaries.'),
    'OLAP': ('分析与列存', 'Analytics & Columnar', '#2456b8',
             '列式存储，DuckDB 集成与外部数据源，Parquet 与 S3 访问，冷热分级存储，分布式与透明分片。',
             'DuckDB integration with FDW and lakehouse, Parquet from files or S3, sharding with Citus, Partman and PL/Proxy.'),
    'FEAT': ('功能特性', 'New Capabilities', '#d13ad6',
             '图数据库 AGE，GraphQL，JSON Schema，查询提示与虚拟索引，HLL，RUM 索引，增量物化视图，消息队列。',
             'OpenCypher with AGE, GraphQL, JSON Schema, hints and hypothetical indexes, HLL, RUM, IVM, RDKit and message queues.'),
    'LANG': ('过程语言', 'Procedural Languages', '#0f9e99',
             '使用 Java、JavaScript、Lua、R、Shell、PRQL 等语言开发、测试、打包与分发存储过程。',
             'Develop, test, package and deliver stored procedures written in Java, JavaScript, Lua, R, Shell, PRQL and more.'),
    'TYPE': ('数据类型', 'Data Types', '#5b5bd6',
             '前缀树、语义版本号、SI 单位、位图、无符号整型、有理数、哈希、IP 地址段、球面坐标、RRULE 等新类型。',
             'New data types such as prefix, semver, uint, SI units, Roaring bitmaps, rationals, spheres, hashes and RRULE.'),
    'UTIL': ('实用工具', 'Utilities', '#9d5c00',
             'HTTP 请求，gzip 与 zstd 压缩，JWT，邮件发送，正则与 ICU，字符编码，加密解密等实用功能。',
             'Utilities for HTTP requests, gzip and zstd compression, mail, regex, ICU, encodings, documents and encryption.'),
    'FUNC': ('函数与聚合', 'Functions & Aggregates', '#0e8fb3',
             'ID 生成器，聚合函数，摘要与草图函数，数组与向量函数，数学与统计函数，伪随机数。',
             'ID generators, aggregations, sketches, vector, mathematical, statistical and digest functions.'),
    'ADMIN': ('管理运维', 'Administration', '#a61e4d',
              '膨胀治理，脏读，缓冲区检视，DDL 生成，校验和与损坏检查，权限与优先级管理，目录管理。',
              'Bloat control, dirty reads, buffer inspection, DDL generation, checksum verification, permissions and priorities.'),
    'STAT': ('监控统计', 'Observability', '#6a9a0a',
             'AWR 报告，可观测性指标与视图，执行计划展示，查询统计，等待事件采样，慢查询日志。',
             'Observability catalogs, monitoring metrics and views, statistics, query plans, wait sampling and slow logs.'),
    'SEC': ('安全', 'Security', '#d21f3c',
            '审计日志，密码强度，密钥管理，透明加密，商密算法，登录钩子，PII 匿名化，扩展白名单。',
            'Auditing logs, password enforcement, secrets, TDE, SM algorithms, login hooks, anonymization and extension whitelists.'),
    'FDW': ('外部数据源', 'Foreign Data Wrappers', '#e04e8f',
            'FDW 开发框架 Wrappers 与 Multicorn，访问 MySQL、MongoDB、SQLite、MSSQL、Oracle、HDFS、DB2 等外部数据源。',
            'Wrappers and Multicorn for FDW development, access to MySQL, MongoDB, SQLite, MSSQL, Oracle, HDFS and DB2.'),
    'SIM': ('兼容仿真', 'Compatibility', '#9741c9',
            '协议仿真与异构数据库兼容：Oracle、MSSQL、DB2、MySQL、Memcached 与 Babelfish。',
            'Protocol simulation and heterogeneous DBMS compatibility: Oracle, MSSQL, DB2, MySQL, Memcached and Babelfish.'),
    'ETL': ('复制与数据流', 'Replication & ETL', '#b8540f',
            '逻辑复制与解码，DDL 复制，Protobuf、JSON、Mongo 格式的变更抽取，数据迁移、导入与比对。',
            'Logical replication and decoding, CDC in protobuf, JSON or Mongo formats, copying, loading and comparing databases.'),
}
NEUTRAL = '#64748b'

# The hue scale for the other dimensions aliases the category palette so
# both themes stay tuned: cool for permissive/common, warm for restrictive
# or rare, violet for commercial or exotic.
HUES = {
    'blue': '#2456b8', 'cyan': '#0e8fb3', 'teal': '#0f9e99', 'green': '#2f9e4f', 'olive': '#6a9a0a',
    'amber': '#b97e0c', 'orange': '#e8590c', 'red': '#d21f3c', 'maroon': '#a61e4d', 'violet': '#7c3aed',
    'indigo': '#5b5bd6', 'pink': '#e04e8f', 'pgblue': '#336791', 'pgnavy': '#1d4266', 'slate': '#64748b',
}
LANGUAGE_HUES = {
    'C': 'blue', 'C++': 'indigo', 'SQL': 'green', 'PLpgSQL': 'teal', 'PL/pgSQL': 'teal', 'Go': 'teal',
    'Rust': 'orange', 'Python': 'amber', 'JavaScript': 'amber', 'TypeScript': 'amber', 'Zig': 'amber',
    'Java': 'red', 'R': 'red', 'Ruby': 'red', 'Shell': 'maroon', 'Perl': 'maroon', 'Data': 'slate',
}
REPO_HUES = {'PGDG': 'pgblue', 'PIGSTY': 'green', 'CONTRIB': 'pgnavy', 'MIXED': 'teal'}

# key: how the dimension appears in rows, query strings, paths and labels.
DIMENSIONS = {
    'category': {'field': 'category', 'param': 'category', 'pgext': 'category',
                 'label': ('功能分类', 'Categories'), 'column': ('分类', 'Category')},
    'license': {'field': 'license', 'param': 'license', 'pgext': 'license',
                'label': ('许可证', 'Licenses'), 'column': ('许可证', 'License')},
    'language': {'field': 'lang', 'param': 'language', 'pgext': 'lang',
                 'label': ('编程语言', 'Languages'), 'column': ('语言', 'Language')},
    'repo': {'field': 'repository', 'param': 'repo', 'pgext': 'repo',
             'label': ('仓库来源', 'Repositories'), 'column': ('仓库', 'Repository')},
}
LEGACY_DIMENSIONS = {'repository': 'repo', 'lang': 'language', 'cate': 'category', 'categories': 'category'}
SORTS = ('stars', 'name', 'recent')
VIEWS = ('table', 'card')
PAGE_SIZE = 50
QUERY_PARAMS = ('lang', 'q', 'sort', 'page', 'view', 'repository') + tuple(spec['param'] for spec in DIMENSIONS.values())
PGEXT = 'https://pgext.cloud'


def localized(pair, language):
    return pair[1 if language == 'en' else 0]


def category_label(code, language):
    return localized(CATEGORIES.get(code, (code, code)), language)


def category_blurb(code, language):
    spec = CATEGORIES.get(code)
    return localized(spec[3:5], language) if spec else ''


def category_color(code):
    """A tone class; extensions.css maps it to the light and dark colours.
    The site's CSP forbids inline style attributes, so colours travel as classes."""
    return 'ext-tone-{}'.format(code) if code in CATEGORIES else 'ext-hue-slate'


def license_hue(value):
    text = (value or '').casefold()
    if not text or text == 'unknown':
        return ''
    for prefixes, hue in (
        (('postgresql',), 'pgblue'), (('mit',), 'blue'),
        (('bsd', '0bsd', 'isc', 'zlib', 'unlicense', 'cc0', 'wtfpl', 'public'), 'cyan'),
        (('apache',), 'green'), (('mpl', 'epl', 'cddl', 'osl'), 'teal'),
        (('artistic', 'eupl', 'cecill'), 'olive'), (('lgpl',), 'amber'),
        (('gpl',), 'orange'), (('agpl',), 'red'),
    ):
        if text.startswith(prefixes):
            return hue
    return 'violet'


def value_color(dimension, value):
    if dimension == 'category':
        return category_color(value)
    if dimension == 'license':
        hue = license_hue(value)
    elif dimension == 'language':
        hue = LANGUAGE_HUES.get(value, 'red' if value and value != 'Unknown' else '')
    elif dimension == 'repo':
        hue = REPO_HUES.get(value, '')
    else:
        hue = ''
    return 'ext-hue-{}'.format(hue) if hue in HUES else ''


def value_label(dimension, value, language):
    if dimension == 'category':
        return category_label(value, language)
    if value == 'Unknown':
        return localized(('未标记', 'Unspecified'), language)
    if dimension == 'repo':
        return localized({
            'CONTRIB': ('PostgreSQL 自带', 'PostgreSQL contrib'),
            'MIXED': ('多个仓库', 'Multiple repositories'),
        }.get(value, (value, value)), language)
    return value


def with_lang(path, ui='zh', **params):
    """Attach the surviving query parameters and the English switch. The
    first argument is the interface language; a `language` key in params is
    the programming-language filter."""
    params = {key: value for key, value in params.items() if value not in ('', None)}
    if ui == 'en':
        params['lang'] = 'en'
    query = urlencode(params)
    return path + ('?' + query if query else '')


def detail_url(name, ui='zh', **params):
    return with_lang('/e/{}/'.format(quote(name, safe='')), ui, **params)


def dimension_url(dimension, ui='zh'):
    return with_lang('/ext/{}/'.format(dimension), ui)


def browse_url(ui='zh', filters=None, **extra):
    """A catalogue list. One filter and no search gets its own path
    (/ext/gis/, /ext/license/MIT/); everything else is /ext/ with a query."""
    filters = {key: value for key, value in (filters or {}).items() if value}
    if extra.get('sort') == 'stars':
        extra['sort'] = ''
    if extra.get('view') == 'table':
        extra['view'] = ''
    if extra.get('page') in (1, '1'):
        extra['page'] = ''
    if len(filters) == 1 and not extra.get('q'):
        (key, value), = filters.items()
        if key == 'category':
            path = '/ext/{}/'.format(value.lower())
        else:
            path = '/ext/{}/{}/'.format(key, quote(value, safe=''))
        return with_lang(path, ui, **extra)
    params = {DIMENSIONS[key]['param']: value for key, value in filters.items()}
    return with_lang('/ext/', ui, **params, **extra)


def safe_url(value):
    try:
        parsed = urlsplit(value or '')
        return value if parsed.scheme in ('https', 'http') and parsed.netloc else ''
    except ValueError:
        return ''


def short_number(value):
    if value is None:
        return ''
    if value >= 10000:
        return '{:.0f}k'.format(value / 1000)
    if value >= 1000:
        return '{:.1f}k'.format(value / 1000)
    return str(value)


def pg_range(values):
    numbers = sorted({int(v) for v in values or [] if str(v).isdigit()})
    if not numbers:
        return ''
    return '{}–{}'.format(numbers[0], numbers[-1]) if len(numbers) > 1 else str(numbers[0])


def catalog():
    rows = cache.get('pgweb:ext:catalog:v2')
    if rows is not None:
        return rows
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT u.*,
                   NULLIF(d.en_doc, '') IS NOT NULL AS has_en,
                   NULLIF(d.zh_doc, '') IS NOT NULL AS has_zh,
                   COALESCE(NULLIF(u.extra->>'repo', 'n/a'),
                     CASE WHEN u.contrib THEN 'CONTRIB'
                          WHEN u.rpm_repo = u.deb_repo THEN u.rpm_repo
                          WHEN u.rpm_repo IS NULL THEN u.deb_repo
                          WHEN u.deb_repo IS NULL THEN u.rpm_repo
                          ELSE 'MIXED' END, 'Unknown') AS repository
            FROM pgext.universe u LEFT JOIN pgext.doc d ON d.id = u.id AND d.ext = u.name
            ORDER BY u.id
        """)
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for row in rows:
        for key in ('license', 'lang', 'repository'):
            row[key] = row[key] or 'Unknown'
        row['search_text'] = ' '.join(str(row.get(key) or '') for key in (
            'name', 'pkg', 'en_desc', 'zh_desc', 'category', 'tags', 'lang', 'license', 'vendor',
        )).casefold()
    cache.set('pgweb:ext:catalog:v2', rows, 60)
    return rows


def facets(rows, language):
    """Every value of every dimension with its global count, label and colour."""
    result = {}
    for dimension, spec in DIMENSIONS.items():
        counts = Counter(row[spec['field']] for row in rows)
        values = [{
            'value': value, 'label': value_label(dimension, value, language), 'count': count,
            'color': value_color(dimension, value), 'url': browse_url(language, {dimension: value}),
        } for value, count in counts.items()]
        if dimension == 'category':
            order = list(CATEGORIES)
            values.sort(key=lambda v: (order.index(v['value']) if v['value'] in order else len(order), v['value']))
        else:
            values.sort(key=lambda v: (v['value'] == 'Unknown', -v['count'], v['value']))
        result[dimension] = values
    return result


def present(row, language):
    value = dict(row)
    value.update({
        'description': row.get(language + '_desc') or row.get('en_desc') or row.get('zh_desc') or '',
        'category_label': category_label(row['category'], language),
        'color': category_color(row['category']),
        'href': detail_url(row['name'], language),
        'category_href': browse_url(language, {'category': row['category']}),
        'license_href': browse_url(language, {'license': row['license']}),
        'language_href': browse_url(language, {'language': row['lang']}),
        'repository_href': browse_url(language, {'repo': row['repository']}),
        'repository_label': value_label('repo', row['repository'], language),
        'license_label': value_label('license', row['license'], language),
        'license_color': value_color('license', row['license']),
        'language_color': value_color('language', row['lang']),
        'repository_color': value_color('repo', row['repository']),
        'upstream': safe_url(row.get('repo_url')) or safe_url(row.get('url')),
        'github': 'github.com' in (row.get('repo_url') or ''),
        'stars_short': short_number(row.get('stars')),
        'pg_range': pg_range(row.get('pg_ver')),
    })
    return value


def sql_readout(query, selected, sort):
    """The psql line under the search box: the query the page is answering."""
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"

    where = []
    for word in query.casefold().split():
        where.append("concat_ws(' ', name, pkg, en_desc, zh_desc, array_to_string(tags, ' ')) ILIKE " + literal('%' + word + '%'))
    if selected.get('category'):
        where.append('category = ' + literal(selected['category']))
    for key, column in (('license', 'license'), ('language', 'lang')):
        if selected.get(key) == 'Unknown':
            where.append("COALESCE(NULLIF({}, ''), 'Unknown') = 'Unknown'".format(column))
        elif selected.get(key):
            where.append('{} = {}'.format(column, literal(selected[key])))
    if selected.get('repo'):
        where.append("COALESCE(extra->>'repo', rpm_repo, deb_repo, 'Unknown') = " + literal(selected['repo']))
    order = {'stars': 'stars DESC NULLS LAST', 'name': 'name', 'recent': 'last_active DESC NULLS LAST'}[sort]
    sql = 'SELECT * FROM pgext.universe' + (' WHERE ' + ' AND '.join(where) if where else '') + ' ORDER BY ' + order + ';'

    def keyword(text):
        return '<b>' + text + '</b>'
    html = keyword('SELECT') + ' * ' + keyword('FROM') + ' pgext.universe'
    if where:
        clauses = escape(' AND '.join(where))
        parts = clauses.split('&#x27;')
        for index in range(1, len(parts), 2):
            parts[index] = '<i>&#x27;' + parts[index] + '&#x27;</i>'
        for index in range(0, len(parts), 2):
            parts[index] = parts[index].replace(' AND ', ' ' + keyword('AND') + ' ').replace(' ILIKE ', ' ' + keyword('ILIKE') + ' ')
        html += ' ' + keyword('WHERE') + ' ' + ''.join(parts)
    html += ' ' + keyword('ORDER BY') + ' ' + escape(order).replace(' DESC NULLS LAST', ' ' + keyword('DESC NULLS LAST')) + ';'
    return sql, mark_safe(html)
