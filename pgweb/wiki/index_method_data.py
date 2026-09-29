"""Stable identities and comparison labels for built-in index access methods."""
METHODS = {
    'btree': ('B-tree', '有序检索', ['b-tree', 'balanced tree', 'range', 'sorting', 'unique']),
    'hash': ('Hash', '等值检索', ['equality', 'hashing']),
    'gist': ('GiST', '可扩展检索', ['generalized search tree', 'spatial', 'nearest neighbor']),
    'spgist': ('SP-GiST', '可扩展检索', ['space-partitioned gist', 'radix tree', 'quadtree', 'nearest neighbor']),
    'gin': ('GIN', '组件检索', ['generalized inverted index', 'jsonb', 'array', 'full text']),
    'brin': ('BRIN', '块范围摘要', ['block range index', 'physical correlation', 'range summary']),
}
CAPABILITIES = (
    ('ordered', '有序输出'),
    ('unique', '唯一键'),
    ('multicolumn', '多列键'),
    ('include', 'INCLUDE 附加列'),
    ('index_only', '仅索引扫描'),
    ('distance', '距离排序'),
    ('parallel_scan', '并行索引扫描'),
    ('parallel_build', '并行索引构建'),
)
CAPABILITY_NOTES = {
    'ordered': '普通有序输出与按运算符（例如近邻距离）排序是不同能力。',
    'unique': '这里指唯一索引，排除约束采用不同的接口约定。',
    'multicolumn': '多个检索键与不参与检索的 INCLUDE 附加列不同。',
    'include': '附加列不会成为检索键；过宽的附加数据可能超过索引元组大小限制。',
    'index_only': '查询所需值须由索引覆盖；是否仍需访问堆取决于可见性映射。',
    'distance': '可用性取决于所选运算符类及排序运算符。',
    'parallel_scan': '多个进程协作扫描同一索引，不同于并行位图堆扫描，也不同于 Parallel Append 下独立的串行扫描。',
    'parallel_build': '并行构建与并行扫描分别记录，还受工作进程、配置及构建阶段影响。',
}
STATES = {'yes': '支持', 'no': '不支持', 'conditional': '有条件', 'unknown': '未确定'}


def validate(data):
    """Validate the extra domain payload before the generic topic importer writes it."""
    import re
    from urllib.parse import urlsplit

    def fingerprint(value):
        return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value)

    def local_source(source, major, known):
        prefix = '/docs/' + ('devel' if major == '20' else major) + '/'
        if (not isinstance(source, dict) or not source.get('url', '').startswith((prefix, 'https://pg.center' + prefix)) or
                not fingerprint(source.get('sha256')) or source.get('file') not in known or
                source['sha256'] != known[source['file']]):
            raise ValueError('Index method evidence must match its same-version manual page hash')

    if set(row.get('slug') for row in data.get('items', [])) != set(METHODS):
        raise ValueError('Index method snapshot must contain the six reviewed built-in identities')
    expected_keys = {key for key, _ in CAPABILITIES}
    for row in data['items']:
        for major, snapshot in row.get('versions', {}).items():
            release = snapshot.get('release') or {}
            manifest = release.get('manifest') or {}
            parsed = urlsplit(manifest.get('source_url', ''))
            if (not fingerprint(release.get('revision')) or not fingerprint(manifest.get('source_sha256')) or
                    parsed.scheme != 'https' or parsed.hostname != 'ftp.postgresql.org' or
                    parsed.username or manifest.get('major') != major):
                raise ValueError('Index method source build must retain the official manual manifest and fingerprints')
            if snapshot.get('evidence_kind') != 'documentation' or snapshot.get('runtime_verified') is not False:
                raise ValueError('Index method snapshots are documentation, not runtime measurements')
            sources = snapshot.get('sources', [])
            hashes = {source.get('file'): source.get('sha256') for source in sources}
            for source in sources:
                local_source(source, major, hashes)
            caps = snapshot.get('capabilities', [])
            if len(caps) != len(CAPABILITIES) or {cap.get('key') for cap in caps} != expected_keys:
                raise ValueError('Incomplete index method capability matrix')
            for cap in caps:
                state = cap.get('state')
                if state not in STATES or not isinstance(cap.get('value'), str) or not cap.get('value') or not isinstance(cap.get('note'), str):
                    raise ValueError('Invalid index method capability state')
                evidence = cap.get('evidence')
                if not isinstance(evidence, list) or bool(evidence) != (state != 'unknown'):
                    raise ValueError('Known index method capabilities require source evidence')
                for source in evidence:
                    local_source(source, major, hashes)
                    if not isinstance(source.get('quote'), str) or not source['quote']:
                        raise ValueError('Index method evidence must retain the source statement')
            seen = set()
            for option in snapshot.get('storage_options', []):
                name = option.get('name')
                if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z_]+', name) or name in seen:
                    raise ValueError('Invalid or duplicate index storage option')
                seen.add(name)
                local_source(option.get('source'), major, hashes)
                url = option.get('url', '')
                parsed_url = urlsplit(url)
                if not ((url.startswith(('/wiki/relopts/', '/docs/')) and not parsed_url.netloc) or
                        (url.startswith('https://pg.center/docs/') and parsed_url.hostname == 'pg.center' and not parsed_url.username)):
                    raise ValueError('Invalid storage option link')
                paragraphs = option.get('description')
                if not isinstance(paragraphs, list) or not paragraphs or not all(isinstance(p, str) and p for p in paragraphs):
                    raise ValueError('Missing storage option definition')
    return True
