#!/usr/bin/env python3
"""Build a guarded Wiki release delta; never write a database.

Inputs are full before inventories, SHA-pinned archives, actual runtime samples,
same-build manuals and replayed topic candidates. Unselected snapshots are
asserted byte-equivalent before any output is emitted.
"""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value)).hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def walk(value, transform):
    if isinstance(value, dict):
        return {k: walk(v, transform) for k, v in value.items()}
    if isinstance(value, list):
        return [walk(v, transform) for v in value]
    return transform(value) if isinstance(value, str) else value


def refine_guc_history(rows, order):
    """Unknown documentary defaults do not form measured history segments."""
    for row in rows:
        history = []
        for major in order:
            snapshot = row['versions'].get(major)
            if not snapshot or snapshot.get('facts_source') == 'documentation' or snapshot.get('boot_val') is None:
                continue
            fields = dict(boot_val=snapshot['boot_val'], unit=snapshot.get('unit') or '', human=snapshot.get('human', ''))
            if history and all(history[-1].get(k) == v for k, v in fields.items()):
                history[-1]['to'] = major
            else:
                history.append(dict(fields, **{'from': major, 'to': major}))
        row['default_history'] = history
        if '19' in row['versions'] and row['versions']['19'].get('calibration'):
            for key in ('references', 'references_zh'):
                for ref in row.get('editorial', {}).get(key, []):
                    if '/docs/19/' in ref.get('url', ''):
                        ref['title'] = re.sub(r'PostgreSQL 19\s*(?:Beta\s*4|beta4|RC\s*[12]|rc[12])',
                                             'PostgreSQL 19.0', ref.get('title', ''))
        if row['name'] == 'max_locks_per_transaction':
            row['short_desc'] = 'Sizes the shared lock table by the average number of lockable objects per backend or prepared transaction.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--pgdoc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Use a new candidate directory'
    run = args.run
    pins = read(run / 'pins.json')
    majors = tuple(pins)
    tags = {line.split()[1].split('/')[-1]: line.split()[0] for line in (run / 'tags.txt').read_text().splitlines()}
    manifest = read(run / 'before/manifest.json')
    before = {m['table']: [json.loads(line) for line in gzip.decompress(
        (run / 'before' / (m['table'] + '.jsonl.gz')).read_bytes()).splitlines()] for m in manifest}
    after = deepcopy(before)
    report = {'versions': {}, 'topics': {}, 'changes': {}, 'preserved_pg20': {}}
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pgweb.settings')
    import django
    django.setup()
    from bs4 import BeautifulSoup
    from django.db import connection, transaction
    from pgweb.docs.models import DocPage
    from pgweb.wiki import func_importer, sqlcmd_importer, topics, guc_importer
    from pgweb.wiki.func_common import signature_key
    from pgweb.wiki.guc_common import human_value
    from pgweb.wiki.sqlcmd import localized_snapshot
    from pgweb.wiki.waitevent_importer import parse_event_tables, parse_names_txt

    # The only database reads are the already-published Chinese manuals.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        manuals = {m: dict(DocPage.objects.filter(version_id=m).values_list('file', 'content')) for m in majors}

    calibrations, trees = {}, {}
    runtime = {m: read(run / 'runtime' / m / 'sample.json') for m in majors}
    for m, pin in pins.items():
        tag = 'REL_' + pin['release'].replace('.', '_')
        trees[m] = run / 'source' / tags[tag]
        archive = args.pgdoc / '.cache/upstream' / ('postgresql-' + pin['release'] + '.tar.bz2')
        assert sha(archive.read_bytes()) == pin['sha256']
        assert runtime[m]['identity']['server_version'] == pin['release']
        calibrations[m] = dict(release=pin['release'], tag=tag, commit=tags[tag], archive_sha256=pin['sha256'],
            source_url='https://ftp.postgresql.org/pub/source/v' + pin['release'] + '/' + archive.name,
            runtime_sha256=sha((run / 'runtime' / m / 'sample.json').read_bytes()),
            manual_sha256=sha(manuals[m]), date='2026-11-20')
        report['versions'][m] = deepcopy(calibrations[m])

    def calibration(m, method, **extra):
        return dict(calibrations[m], method=method, **extra)

    def release(m):
        c = calibrations[m]
        return dict(major=m, label=c['release'], ref=c['tag'], revision=c['commit'],
                    channel='historical' if m == '14' else 'stable')

    def selected(table, m):
        return {r.get('name', r.get('slug')): r['versions'][m] for r in after[table] if m in r.get('versions', {})}

    # Actual catalogs: every relation and every user/system attribute is checked.
    for m in majors:
        measured = {r['name']: r for r in runtime[m]['relations']}
        stored = selected('catalog', m)
        assert measured.keys() == stored.keys(), ('catalog membership', m)
        for name, s in stored.items():
            actual = measured[name]
            for key in ('relation_oid', 'relkind', 'shared'):
                assert str(s[key]) == str(actual[key]), (m, name, key)
            columns = {c['name']: c for c in s['columns'] + s.get('system_columns', [])}
            assert columns.keys() == {c['name'] for c in actual['columns']}, (m, name, 'columns')
            for c in actual['columns']:
                for k, value in c.items():
                    assert str(columns[c['name']].get(k)) == str(value), (m, name, c['name'], k)
            s['release'] = pins[m]['release']
            s['runtime_verified'] = True
            s['calibration'] = calibration(m, 'pg_class + pg_attribute; exact column and attribute equality')
        report['versions'][m]['catalog_count'] = len(stored)

    # Settings absent from pg_settings remain explicitly source/build-specific.
    # No compiler-dependent enum alternative is deleted from the reference.
    for m in majors:
        measured = {r['name']: r for r in runtime[m]['settings']}
        stored = selected('guc', m)
        assert measured.keys() <= stored.keys(), ('new GUC', m, measured.keys() - stored.keys())
        source_files = list((trees[m] / 'src/backend/utils/misc').glob('guc*'))
        source_files += list((trees[m] / 'src/include').glob('utils/guc*'))
        definitions = '\n'.join(p.read_text() for p in source_files if p.is_file())
        for name, s in stored.items():
            if name not in measured:
                distro = name == 'extension_destdir'
                assert distro or name in definitions or any(name in raw for f, raw in manuals[m].items() if f.startswith('runtime-config'))
                s['runtime_verified'] = False
                s['calibration'] = calibration(m, 'distribution-specific historical sample' if distro else 'conditional source/manual definition',
                    note=('此参数属于发行版补丁，原发行版采样保留；上游正式源码构建未提供此参数。' if distro else
                          '此参数依赖调试或平台编译选项；本次正式版构建未启用，保留同版源码／手册事实。'))
                continue
            actual = measured[name]
            for key in ('context', 'vartype', 'unit', 'min_val', 'max_val'):
                if name != 'server_version_num':
                    assert (s.get(key) or '') == (actual.get(key) or ''), (m, name, key)
            old_enums, new_enums = s.get('enumvals') or [], actual.get('enumvals') or []
            assert set(new_enums) <= set(old_enums), (m, name, 'enums')
            assert name in ('krb_server_keyfile', 'unix_socket_directories', 'server_version', 'server_version_num') or s['boot_val'] == actual['boot_val'], (m, name, 'default')
            previous = {k: s.get(k) for k in ('boot_val', 'setting', 'min_val', 'max_val')}
            for key in ('boot_val', 'setting', 'min_val', 'max_val'):
                s[key] = actual[key]
            s['human'] = human_value(s['boot_val'], s.get('unit') or '')
            s['runtime_verified'] = True
            s['calibration'] = calibration(m, 'pg_settings on clean source build', observed_enumvals=new_enums)
            if any(previous[k] != s[k] for k in previous):
                s['calibration']['previous_observation'] = previous
            if name in ('krb_server_keyfile', 'unix_socket_directories'):
                s['calibration']['note'] = '当前值取自上游源码的 Linux 构建；较早采样使用 Debian 包，路径默认值差异来自构建配置。'
            if set(old_enums) != set(new_enums):
                s['calibration']['note'] = '枚举包含源码支持的编译条件分支；本次 ARM64 构建的实际可选值为 ' + ', '.join(new_enums) + '。'
            facts = s.get('center_zh', {}).get('definition', {}).get('facts', {})
            for key in ('boot_val', 'setting', 'min_val', 'max_val', 'human'):
                if key in facts:
                    facts[key] = s[key]
        report['versions'][m]['guc_runtime_count'] = len(measured)
        report['versions'][m]['guc_source_only'] = sorted(stored.keys() - measured.keys())

    # Re-extract all function and SQL signatures; retain reviewed Chinese prose.
    for m in majors:
        english_root = args.pgdoc / 'en' / pins[m]['release'] / 'html'
        for lang, pages in [('en', {p.name: p.read_text() for p in english_root.glob('functions-*.html')}),
                            ('zh', {f: raw for f, raw in manuals[m].items() if f.startswith('functions-')})]:
            functions, _ = func_importer.harvest_version(pages, func_importer.parse_context(m, m, lang),
                {'pages_without_functions': []}, {r['name_key'] for r in after['func']})
            stored = {r['name_key']: r['versions'][m] for r in after['func'] if m in r['versions']}
            assert functions.keys() == stored.keys(), (m, lang, 'function membership')
            for name, actual in functions.items():
                left = {signature_key(x['text']) for x in actual['signatures']}
                right = {signature_key(x['text']) for x in stored[name]['signatures']}
                if lang == 'en' and left != right:
                    def normalize_translation(value):
                        return value.replace('见说明', 'see text').replace('与输入类型相同', 'same as input type').replace(
                            '对于 real 或 double precision 输入，返回 double precision；否则返回 numeric',
                            'double precision for real or double precision, otherwise numeric')
                    assert left == {normalize_translation(v) for v in right}, (m, name, 'unreviewed signature translation')
                    report.setdefault('translated_signature_phrases', []).append(dict(major=m, name=name, english=sorted(left), stored=sorted(right)))
                else:
                    assert left == right, (m, lang, name)
                stored[name]['calibration'] = calibration(m, 'same-build English and Chinese function signatures')
        commands = {}
        for filename, raw in manuals[m].items():
            if filename.startswith('sql-'):
                parsed = sqlcmd_importer.parse_page(raw, filename, {'major': m, 'doc_slug': m})
                if parsed:
                    commands[sqlcmd_importer.sqlcmd_slug(parsed['name'])] = parsed
        stored = {r['slug']: r['versions'][m] for r in after['sqlcmd'] if m in r['versions']}
        assert commands.keys() == stored.keys(), (m, 'SQL membership')
        for name, actual in commands.items():
            norm = lambda value: re.sub(r'\s+', '', value)
            assert norm(actual['synopsis_text']) == norm(localized_snapshot(stored[name])['synopsis_text']), (m, name)
            stored[name]['calibration'] = calibration(m, 'same-build Chinese SQL manual; exact synopsis equality')
        waits = {(a, b): d for a, b, d in parse_event_tables(BeautifulSoup(manuals[m]['monitoring-stats.html'], 'html.parser'))}
        stored = {(r['versions'][m]['type'], r['versions'][m]['name']): r['versions'][m] for r in after['waitevent'] if m in r['versions']}
        assert waits.keys() == stored.keys(), (m, 'wait membership')
        source = trees[m] / 'src/backend/utils/activity/wait_event_names.txt'
        if source.exists():
            assert {(a, b) for a, b, _ in parse_names_txt(source.read_text())} == stored.keys(), (m, 'wait source')
        for s in stored.values():
            s['calibration'] = calibration(m, 'same-build wait definitions and manual inventory')
        codes = {}
        raw_codes = (trees[m] / 'src/backend/utils/errcodes.txt').read_text()
        for line in raw_codes.splitlines():
            parts = line.split()
            if len(parts) >= 4 and re.fullmatch('[A-Z0-9]{5}', parts[0]):
                codes.setdefault(parts[0], set()).add(parts[3])
        stored_codes = {r['sqlstate']: r for r in after['sqlstate'] if m in r['present_in']}
        assert codes.keys() == stored_codes.keys(), (m, 'SQLSTATE membership')
        for code, conditions in codes.items():
            row = stored_codes[code]
            assert conditions <= set(row['condition_names']), (m, code)
            row['evidence'].setdefault('release_calibrations', {})[m] = calibration(m, 'errcodes.txt definitions; runtime histories preserved', definition_sha256=sha(raw_codes.encode()))
            row['preview_in'] = [v for v in row['preview_in'] if v != m]
        report['versions'][m].update(func_count=len(functions), sql_count=len(commands), wait_count=len(waits), sqlstate_count=len(codes))

    # Replay all 22 topic inventories. Only two known GA semantic changes are
    # accepted here; additional changes stop publication for editorial review.
    for kind, model in topics.MODELS.items():
        table = model._meta.db_table
        candidate = read(run / 'candidates' / (kind + '.json.gz'))
        new = {r['slug']: r for r in candidate['items']}
        old = {r['slug']: r for r in after[table]}
        changes = []
        for m in majors:
            assert {k for k, r in new.items() if m in r['versions']} == {k for k, r in old.items() if m in r['versions']}, (kind, m, 'membership')
        for slug, item in new.items():
            for m, actual in item['versions'].items():
                s = old[slug]['versions'][m]
                keys = ['comparison_data'] if 'comparison_data' in actual else ['signature', 'catalog', 'casts', 'operators', 'operator_classes', 'ranges', 'attributes']
                if kind in ('relopts', 'role', 'oid'):
                    keys.append('facts')
                fields = [k for k in keys if s.get(k) != actual.get(k)]
                if fields:
                    changes.append([slug, m, fields])
                    assert (kind, slug, m) in [('tool', 'pg-combinebackup', '19'), ('fdw', 'file_fdw', '19')], (kind, slug, m, fields)
                    for key in fields:
                        s[key] = deepcopy(actual[key])
                    if 'comparison_hash' in actual:
                        s['comparison_hash'] = actual['comparison_hash']
                # Native hook signatures normalize whitespace only; prose is kept.
                if kind == 'hook':
                    assert re.sub(r'\s+', '', s['signature']) == re.sub(r'\s+', '', actual['signature'])
                s['calibration'] = calibration(m, 'replayed ' + kind + ' generator; membership and technical attributes verified', candidate_sha256=sha(actual))
                s['calibration']['previous_release'] = deepcopy(s.get('release'))
                s['release'] = release(m)
                if kind == 'hook':
                    s['historical_sources'] = deepcopy(s.get('sources', []))
                    s['sources'] = deepcopy(actual['sources'])
        report['topics'][kind] = dict(entities=len(new), semantic_changes=changes)

    lock_candidate = read(run / 'candidates/lock.json.gz')
    locks = {r['slug']: r for r in lock_candidate['modes']}
    provenance = {r['major']: r for r in lock_candidate['versions']}
    for row in after['lock_mode']:
        for m in majors:
            s, actual = row['versions'][m], locks[row['slug']]['versions'][m]
            assert s['conflicts'] == actual['conflicts'], (m, row['slug'], 'lock conflicts')
            key = lambda c: (c['slug'], c['label'], c.get('note', ''))
            assert {key(c) for c in s['commands']} == {key(c) for c in actual['commands']}, (m, row['slug'], 'lock commands')
            s['historical_sources'] = deepcopy(s['sources'])
            s['sources'], s['commands'] = deepcopy(actual['sources']), deepcopy(actual['commands'])
            s['provenance'] = dict(provenance[m], label=pins[m]['release'], status='stable' if m == '19' else 'historical')
            s['calibration'] = calibration(m, 'source/manual lock matrices, tuple conflicts and command rules')

    # Correct only the GA-changed option blocks, using the published Chinese GA manual.
    def update_option(value, term, replacement):
        if term not in value or '<' not in value:
            return value
        soup = BeautifulSoup(value, 'html.parser')
        changed = False
        for dt in soup.find_all('dt'):
            if term in dt.get_text() and dt.find_next_sibling('dd'):
                dt.find_next_sibling('dd').replace_with(BeautifulSoup(replacement, 'html.parser').find('dd'))
                changed = True
        return str(soup) if changed else value
    for table, slug, filename, term in [('foreign_data_wrapper', 'file_fdw', 'file-fdw.html', 'reject_limit'),
                                       ('command_tool', 'pg-combinebackup', 'app-pgcombinebackup.html', '--sync-method')]:
        soup = BeautifulSoup(manuals['19'][filename], 'html.parser')
        dt = next(dt for dt in soup.find_all('dt') if term in dt.get_text())
        replacement = str(dt.find_next_sibling('dd')).replace('href="', 'href="/docs/19/')
        row = next(r for r in after[table] if r['slug'] == slug)
        row['versions']['19'] = walk(row['versions']['19'], lambda s: update_option(s, term, replacement))
        current_text = dt.find_next_sibling('dd').get_text(' ', strip=True)
        def fix_table(value):
            if isinstance(value, dict):
                if term == 'reject_limit' and value.get('name') == term and 'definition' in value:
                    # English comparison_data is the verified generator result.
                    if re.search('[\u4e00-\u9fff]', value['definition']):
                        value['definition'] = current_text
                for child in value.values():
                    fix_table(child)
            elif isinstance(value, list):
                for child in value:
                    fix_table(child)
        fix_table(row['versions']['19'])
        if term == '--sync-method':
            row['versions']['19'] = walk(row['versions']['19'], lambda value:
                value.replace('备份目录', '输出目录').replace('使用普通文件格式时，', '')
                if value.startswith('当设置为 fsync') and '<' not in value else value)

    for row in after['procedural_language']:
        for m in majors:
            if m not in row['versions']:
                continue
            s = row['versions'][m]
            s = walk(s, lambda value: value.replace('操作符家族', '语言家族'))
            def trusted(value):
                if isinstance(value, dict):
                    if value.get('label') in ('可信', '受信任') and value.get('value') in ('t', 'f'):
                        value['label'] = '受信任'
                        value['value'] = '是' if value['value'] == 't' else '否'
                    for child in value.values():
                        trusted(child)
                elif isinstance(value, list):
                    for child in value:
                        trusted(child)
            trusted(s)
            row['versions'][m] = s
    guc = next(r for r in after['guc'] if r['name'] == 'max_locks_per_transaction')
    guc['short_desc_zh'] = '每个后端或预备事务平均预留的可锁定对象数'
    guc['editorial'] = walk(guc['editorial'], lambda value: value.replace(
        '设置每个事务的锁数量上限。该值在服务器启动时固定，修改后必须重启。',
        '按每个后端或预备事务平均涉及的对象数确定共享锁表容量。单个事务可以超过此数；修改该启动参数需要重启。').replace(
        'Sets the maximum number of locks per transaction. The value is fixed when the server starts, so changing it requires a restart.',
        'Sizes the shared lock table by the average number of lockable objects per backend or prepared transaction. A single transaction can exceed this number; changing the parameter requires a restart.'))

    # Apply only independently verified same-version link repairs.
    repairs = {r['url']: r['candidate'] for r in read(ROOT / 'data/wiki/audit-20261120-links.json')['mappings']}
    url_pattern = re.compile(r'(?:https://pg\.center)?(?:/zh)?(?P<url>/docs/[^\s\"\'<>)]*)')
    def repair(value):
        return url_pattern.sub(lambda match: repairs.get(match['url'], match[0]), value)
    def repair_coordinates(value):
        if isinstance(value, dict):
            if value.get('file') and value.get('slug') in majors:
                url = '/docs/' + value['slug'] + '/' + value['file'] + ('#' + value['anchor'] if value.get('anchor') else '')
                if url in repairs:
                    from urllib.parse import urlsplit
                    parsed = urlsplit(repairs[url])
                    value['file'], value['anchor'] = parsed.path.rsplit('/', 1)[-1], parsed.fragment
            for child in value.values():
                repair_coordinates(child)
        elif isinstance(value, list):
            for child in value:
                repair_coordinates(child)
    for table, rows in after.items():
        for row in rows:
            for m in majors:
                if m in row.get('versions', {}):
                    s = walk(row['versions'][m], repair)
                    repair_coordinates(s)
                    # English source labels must open the original English manual.
                    for source in s.get('sources', []):
                        url = source.get('url', '')
                        if ('English' in source.get('label', '') or '英文' in source.get('label', '')) and url.startswith(('/docs/', '/zh/docs/')):
                            source['url'] = 'https://www.postgresql.org' + url.removeprefix('/zh')
                    row['versions'][m] = s

    # Update release metadata only after the corresponding verification passes.
    for table in ('catalog_version', 'guc_version', 'func_version', 'waitevent_version', 'sqlstate_version'):
        for row in after[table]:
            m = row['major']
            if m not in majors:
                continue
            c = calibrations[m]
            if table == 'sqlstate_version':
                row.update(channel='formal', release=c['release'], tag=c['tag'], commit=c['commit'])
                continue
            row.update(label=c['release'], status='stable' if m == '19' else 'historical',
                       support_status='end-of-life' if m == '14' else 'supported')
            if table == 'catalog_version':
                row.update(release=c['release'], source_tag=c['tag'], documentation_version=c['release'], runtime_verified=True)
            if table == 'guc_version':
                row.update(server_version=c['release'], source_key=c['release'])
            if table == 'waitevent_version':
                row['notes']['release_calibration'] = c
                row['notes']['previous_build'] = {k: row['notes'].get(k) for k in ('doc_tag', 'documentation_release')}
                row['notes'].update(doc_tag=c['tag'], documentation_release=c['release'])

    # Recompute affected GUC derivatives, while preserving the PG20 version row.
    order = [r['major'] for r in sorted(after['guc_version'], key=lambda r: r['position'])]
    for row in after['guc']:
        row['changes'] = guc_importer.build_changes(row['versions'], order)
        history = []
        for m in order:
            s = row['versions'].get(m)
            if not s or s.get('facts_source') == 'documentation' or s.get('boot_val') is None:
                continue
            fields = dict(boot_val=s.get('boot_val'), unit=s.get('unit') or '', human=s.get('human', ''))
            if history and all(history[-1].get(k) == v for k, v in fields.items()):
                history[-1]['to'] = m
            else:
                history.append(dict(fields, **{'from': m, 'to': m}))
        row['default_history'] = history
        row['changed_in'] = [c['to'] for c in row['changes'] if c['status'] == 'changed' and c['substantive']]
        row['default_changed_in'] = [c['to'] for c in row['changes'] if c['status'] == 'changed' and c['default_changed']]
    transitions = guc_importer.build_transitions(after['guc'], order)
    refine_guc_history(after['guc'], order)
    for row in after['guc_version']:
        if row['major'] in majors:
            tr = transitions[row['major']]
            row['transition'] = tr
            for key in ('added', 'removed', 'changed', 'default_changed', 'reworded'):
                row[key + '_count'] = len(tr[key])

    args.output.mkdir(parents=True)
    for meta in manifest:
        table, key = meta['table'], meta['key']
        old, new = before[table], after[table]
        for a, b in zip(old, new):
            assert a[key] == b[key]
            for m, s in a.get('versions', {}).items():
                if m not in majors:
                    assert s == b['versions'][m], ('unselected snapshot changed', table, a[key], m)
            if a.get('major') not in majors and table.endswith('_version'):
                assert a == b, ('unselected version metadata', table, a[key])
        report['preserved_pg20'][table] = meta['pg20_sha256']
        report['changes'][table] = [{'key': b[key], 'fields': [k for k in b if a.get(k) != b[k]]}
                                    for a, b in zip(old, new) if a != b]
        raw = b''.join(encoded(row) + b'\n' for row in new)
        (args.output / (table + '.jsonl.gz')).write_bytes(gzip.compress(raw, mtime=0))
        meta['sha256'] = sha(raw)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (args.output / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({t: len(rows) for t, rows in report['changes'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
