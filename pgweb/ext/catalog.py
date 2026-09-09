"""Chinese extension catalogue, backed only by pgext.universe."""

from collections import Counter
from urllib.parse import quote, urlencode, urlsplit

from django.core.cache import cache
from django.db import connection


# Category order matches PGEXT; colours live in extensions.css.
CATEGORIES = {
    'TIME': '时序与时态',
    'GIS': '地理空间',
    'RAG': 'AI 与向量',
    'FTS': '全文检索',
    'OLAP': '分析与列存',
    'FEAT': '功能特性',
    'LANG': '过程语言',
    'TYPE': '数据类型',
    'UTIL': '实用工具',
    'FUNC': '函数与聚合',
    'ADMIN': '管理运维',
    'STAT': '监控统计',
    'SEC': '安全',
    'FDW': '外部数据源',
    'SIM': '兼容仿真',
    'ETL': '复制与数据流',
}
DIMENSIONS = {
    'category': {'field': 'category', 'param': 'category', 'label': '功能分类'},
    'license': {'field': 'license', 'param': 'license', 'label': '许可证'},
    'language': {'field': 'lang', 'param': 'language', 'label': '编程语言'},
    'repo': {'field': 'repository', 'param': 'repo', 'label': '仓库来源'},
}
LEGACY_DIMENSIONS = {'repository': 'repo', 'lang': 'language', 'cate': 'category', 'categories': 'category'}
PAGE_SIZE = 50
QUERY_PARAMS = ('lang', 'q', 'sort', 'page', 'view', 'repository') + tuple(DIMENSIONS)
PGEXT = 'https://pgext.cloud'
CACHE_KEY = 'pgweb:ext:catalog:v4'


def category_label(code):
    return CATEGORIES.get(code, code)


def category_color(code):
    return 'ext-tone-' + code if code in CATEGORIES else ''


def value_label(dimension, value):
    if dimension == 'category':
        return category_label(value)
    if value == 'Unknown':
        return '未标记'
    if dimension == 'repo':
        return {'CONTRIB': 'PostgreSQL 自带', 'MIXED': '多个仓库'}.get(value, value)
    return value


def detail_url(name):
    return '/e/{}/'.format(quote(name, safe=''))


def browse_url(filters=None, *, q='', page=None):
    params = {key: value for key, value in (filters or {}).items() if key in DIMENSIONS and value}
    if q:
        params['q'] = q
    if page and page not in (1, '1'):
        params['page'] = page
    query = urlencode(params)
    return '/ext/' + ('?' + query if query else '')


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
    rows = cache.get(CACHE_KEY)
    if rows is not None:
        return rows
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT u.*,
                   COALESCE(NULLIF(u.extra->>'repo', 'n/a'),
                     CASE WHEN u.contrib THEN 'CONTRIB'
                          WHEN u.rpm_repo = u.deb_repo THEN u.rpm_repo
                          WHEN u.rpm_repo IS NULL THEN u.deb_repo
                          WHEN u.deb_repo IS NULL THEN u.rpm_repo
                          ELSE 'MIXED' END, 'Unknown') AS repository
            FROM pgext.universe u
            ORDER BY u.id
        """)
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for row in rows:
        for key in ('license', 'lang', 'repository'):
            row[key] = row[key] or 'Unknown'
        row['search_text'] = ' '.join(str(row.get(key) or '') for key in (
            'name', 'pkg', 'en_desc', 'zh_desc', 'category', 'tags', 'lang', 'license', 'vendor', 'repository',
        )).casefold()
    cache.set(CACHE_KEY, rows, 60)
    return rows


def facets(rows):
    result = {}
    for dimension, spec in DIMENSIONS.items():
        counts = Counter(row[spec['field']] for row in rows)
        values = list(CATEGORIES) if dimension == 'category' else sorted(counts, key=lambda value: (value == 'Unknown', value.casefold()))
        result[dimension] = [{'value': value, 'label': value_label(dimension, value), 'count': counts[value]}
                             for value in values]
    return result


def present(row):
    value = dict(row)
    value.update({
        'description': row.get('zh_desc') or '暂无中文简介',
        'category_label': category_label(row['category']),
        'color': category_color(row['category']),
        'href': detail_url(row['name']),
        'category_href': browse_url(filters={'category': row['category']}),
        'license_href': browse_url(filters={'license': row['license']}),
        'language_href': browse_url(filters={'language': row['lang']}),
        'repository_href': browse_url(filters={'repo': row['repository']}),
        'repository_label': value_label('repo', row['repository']),
        'upstream': safe_url(row.get('repo_url')) or safe_url(row.get('url')),
        'stars_short': short_number(row.get('stars')),
        'pg_range': pg_range(row.get('pg_ver')),
    })
    return value
