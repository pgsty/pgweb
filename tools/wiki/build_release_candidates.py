#!/usr/bin/env python3
"""Replay existing pure English generators against pinned PG14–19 inputs.

This offline tool never loads Django or connects to either site's database.
The generator checkout is read-only. Outputs are candidates, not import files.
Whole-range validators also receive the unchanged historical input snapshots.
"""
import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tarfile


def sha(raw):
    return hashlib.sha256(raw.encode() if isinstance(raw, str) else raw).hexdigest()


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def write(path, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(gzip.compress(raw, mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generators', type=Path, required=True)
    parser.add_argument('--pgdoc', type=Path, required=True)
    parser.add_argument('--pins', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group', required=True, choices=('type', 'indexam', 'plan', 'operator', 'client', 'server', 'interfaces', 'system'))
    parser.add_argument('--before', type=Path, help='Frozen PGSQL.CC inventory (system group only)')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.generators.resolve()))
    names = dict(type='data_types', indexam='index_methods', plan='plan_nodes', operator='operator_catalogs',
                 client='client_catalogs', server='server_components', interfaces='extension_interfaces', system='system_catalogs')
    module = importlib.import_module('tools.wiki.build_' + names[args.group])
    pins = read(args.pins)
    majors = tuple(pins)
    assert majors == tuple(map(str, range(14, 20)))
    module.MAJORS = majors
    if args.group == 'client':
        import pgweb.wiki.client_catalog_data as data
        data.MAJORS = majors
    manifest, files, manuals = {'versions': []}, {}, {}
    for major, pin in pins.items():
        release = pin['release']
        archive = args.pgdoc / '.cache/upstream' / ('postgresql-' + release + '.tar.bz2')
        assert sha(archive.read_bytes()) == pin['sha256'], archive
        meta = {'major': major, 'release': release, 'source_sha256': pin['sha256'],
                'source_url': 'https://ftp.postgresql.org/pub/source/v' + release + '/' + archive.name}
        manifest['versions'].append(meta)
        wanted = lambda p: p.startswith('src/include/catalog/') and p.endswith(('.h', '.dat'))
        if args.group == 'system':
            predicate = lambda p: p == module.VIEW_SOURCE
        elif args.group == 'type':
            predicate = lambda p: wanted(p) or p == 'doc/src/sgml/datatype.sgml'
        elif args.group == 'operator':
            predicate = wanted
        elif args.group == 'server':
            predicate = module.wanted_source
        elif args.group == 'interfaces':
            predicate = lambda p: p in module.SOURCE_FILES
        elif args.group == 'plan':
            predicate = lambda p: p in {module.EXPLAIN, module.DISPATCH, module.PLAN, module.TUPLESORT, module.TUPLESTORE, module.BITMAP} or p.startswith('src/backend/executor/node') and p.endswith('.c')
        else:
            predicate = lambda p: p == 'src/interfaces/libpq/fe-connect.c'
        files[major] = {}
        with tarfile.open(archive) as stream:
            for member in stream:
                path = member.name.partition('/')[2]
                if member.isfile() and predicate(path):
                    files[major][path] = stream.extractfile(member).read().decode()
        root = args.pgdoc / 'en' / release / 'html'
        if args.group == 'system':
            selected = set(module.FILES) | {p.name for p in root.glob('storage-*.html')}
        elif args.group == 'indexam':
            selected = set(module.FILES)
        elif args.group == 'plan':
            selected = module.MANUALS
        elif args.group == 'interfaces':
            selected = module.MANUAL_FILES
        elif args.group == 'operator':
            selected = module.MANUAL_FILES | {p.name for p in root.glob('functions-*.html')}
        elif args.group == 'type':
            selected = {p.name for p in root.glob('datatype*.html')} | {'arrays.html','rowtypes.html','domains.html','rangetypes.html','functions-info.html','catalog-pg-type.html','sql-createdomain.html'}
        elif args.group == 'client':
            selected = set(module.BASE_FILES)
            selected |= {file for toc in module.BASE_FILES[:2] for _, file in module.toc_inventory((root / toc).read_text())}
        else:
            selected = {p.name for p in root.glob('*.html') if p.name.startswith(('auth-', 'plpgsql', 'plperl', 'plpython', 'pltcl', 'textsearch-', 'xfunc-'))}
            selected |= {'gssapi-auth.html','sspi-auth.html','multibyte.html','collation.html','charset.html','plhandler.html','sql-createlanguage.html','catalog-pg-language.html','catalog-pg-collation.html','catalog-pg-ts-parser.html','catalog-pg-ts-template.html','catalog-pg-ts-dict.html','catalog-pg-ts-config.html'}
        pages = {name: (root / name).read_text() for name in sorted(selected) if (root / name).is_file()}
        manuals[major] = {'pages': pages, 'channel': 'historical' if major == '14' else 'stable', 'manifest': meta}
        print('Prepared', args.group, release, len(files[major]), len(pages), flush=True)

    # Validate selected-version results with untouched historical snapshots. No
    # regenerated PG20 content can escape into the selected-version outputs.
    if args.group in ('plan', 'interfaces'):
        original_validator = module.validate
        filenames = {'plan': 'plan_nodes.json.gz', 'fdw': 'foreign_data_wrappers.json.gz',
                     'tableam': 'table_methods.json.gz', 'decode': 'logical_decoding_plugins.json.gz'}
        def complete_validate(result):
            for row in result['items']:
                for snapshot in row['versions'].values():
                    for key in ('collection_tables', 'catalog_observation', 'extension_reviews'):
                        snapshot.pop(key, None)
            baseline = read(args.generators / 'data/wiki' / filenames[result['kind']])
            full = deepcopy(baseline)
            indexed = {r['slug']: r for r in full['items']}
            for row in result['items']:
                if row['slug'] not in indexed:
                    full['items'].append(deepcopy(row))
                else:
                    indexed[row['slug']]['versions'].update(deepcopy(row['versions']))
            releases = {r['major']: r for r in full['releases']}
            releases.update({r['major']: r for r in result['releases']})
            full['releases'] = list(releases.values())
            if 'inventories' in result:
                full['inventories'].update(result['inventories'])
            return original_validator(full)
        module.validate = complete_validate

    bundle = {'format': 1, 'language': 'en', 'manifest': manifest, 'manuals': manuals, 'sources': files}
    if args.group == 'system':
        from django.conf import settings
        settings.configure(REFERENCE_LANGUAGE='en', SECRET_KEY='offline-generator', DATABASES={})
        assert args.before, 'system requires --before'
        bundle['relations'] = read(args.output / 'system-relations.json.gz')
        bundle['manuals'] = {m: v['pages'] for m, v in manuals.items()}
        bundle['source_views'] = {}
        for major in majors:
            content = files[major][module.VIEW_SOURCE]
            meta = manuals[major]['manifest']
            bundle['source_views'][major] = dict(content=content, sha256=sha(content),
                archive_sha256=meta['source_sha256'], archive_url=meta['source_url'], path=module.VIEW_SOURCE)
        outputs = module.assemble(bundle)
    elif args.group == 'type':
        bundle['catalog_sources'] = files
        outputs = {'type': module.assemble(bundle)}
    elif args.group == 'operator' or args.group == 'server':
        bundle['releases'] = {m: dict(manuals[m], files=files[m]) for m in majors}
        outputs = module.assemble(bundle)
    elif args.group == 'client':
        bundle = {m: dict(manuals[m], libpq_source=files[m][module.SOURCE_FILE]) for m in majors}
        outputs = module.build(bundle)
    elif args.group == 'indexam':
        bundle['releases'] = manuals
        outputs = {'indexam': module.build(bundle)}
    elif args.group == 'plan':
        outputs = {'plan': module.build(bundle)}
    else:
        bundle['catalog'] = {'rows': [], 'sha256': module.digest(json.dumps([], sort_keys=True, ensure_ascii=False)),
                             'source': 'existing directory unchanged', 'observed_at': '2026-11-20'}
        outputs = module.build(bundle)
    for kind, output in outputs.items():
        assert all(set(row['versions']) <= set(majors) for row in output['items'])
        write(args.output / (kind + '.json.gz'), output)
        print('Candidate', kind, len(output['items']), flush=True)
    inputs = {'sources': {m: {p: sha(v) for p, v in rows.items()} for m, rows in files.items()},
              'manuals': {m: {p: sha(v) for p, v in rows['pages'].items()} for m, rows in manuals.items()},
              'generators': {str(Path(m.__file__).relative_to(args.generators)): sha(Path(m.__file__).read_bytes())
                             for m in list(sys.modules.values()) if getattr(m, '__file__', None)
                             and Path(m.__file__).is_relative_to(args.generators) and str(m.__file__).endswith('.py')}}
    write(args.output / (args.group + '-inputs.json.gz'), inputs)


if __name__ == '__main__':
    main()
