#!/usr/bin/env python3
"""Build the PostgreSQL hook reference from pinned, upstream source trees.

    .venv/bin/python tools/wiki/build_hooks.py --fetch
    .venv/bin/python tools/wiki/build_hooks.py --check

The scope is all global hook variables declared in src/include with a
hook-named function-pointer typedef.  Per-object callbacks, GUC check/assign
functions, frontend callbacks and procedural-language plugins are not globals
of this kind.  Every header is scanned; names are not discovered from the
editorial list.  Missing Chinese descriptions or definitions fail the build.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
REVISIONS = {
    '10': ('REL_10_STABLE', 'f4e8f137bfb08a664c8288824c1e36b5143ac875'),
    '11': ('REL_11_STABLE', '170e416034ec0231d9e9238f2577eeb76ca8d181'),
    '12': ('REL_12_STABLE', '3f302f0ed06f69c5ebd33d4df95895323a3cbef6'),
    '13': ('REL_13_STABLE', '05f6c9ec2c475fae8fdd56ae40bd01afcf70d1f2'),
    '14': ('REL_14_STABLE', 'fba35c7c28a567839faba867db0808564c0a66db'),
    '15': ('REL_15_STABLE', '0351991b8e7c7b64382e2f30ce581a8f276590a6'),
    '16': ('REL_16_STABLE', 'dcc37b7099a9f3cf2c75167d8dc92e75f96bc1fa'),
    '17': ('REL_17_STABLE', '163288afd32a448244c8df75b3c33181aadd7f20'),
    '18': ('REL_18_STABLE', '753057e340da8f22e57c9a409ea7a235fd6a46bd'),
    '19': ('REL_19_BETA4', 'b73d13c32c834a2c8e1c60cb92f79530376cedf1'),
    '20': ('master', '1a846a555afb0e5f2008f3aefe8f77acbe6ffba6'),
}

SCOPE = ('逐版扫描 PostgreSQL 10–20 固定源码构建的 src/include，收录以含 hook 的函数指针类型'
         '声明、由服务器核心导出的全局钩子变量。逐对象回调、GUC 的校验/赋值函数、前端回调、'
         '过程语言插件及扩展自有接口不在此清单内。版本方格表示该源码构建存在此接口；'
         '最早收录版本不是实际引入版本。')

# Transport only these implementation files when reconstructing a newer tree
# from a local clone. Header discovery is exhaustive and independent of this
# list: a hook without a matching definition/call site fails the build.
IMPLEMENTATIONS = {
    'catalog/objectaccess.c', 'commands/explain.c', 'commands/explain_state.c',
    'commands/user.c', 'executor/execMain.c', 'libpq/auth.c', 'libpq/be-secure-openssl.c',
    'optimizer/path/allpaths.c', 'optimizer/path/joinpath.c', 'optimizer/plan/planner.c',
    'optimizer/util/relnode.c', 'optimizer/util/plancat.c', 'parser/analyze.c',
    'rewrite/rowsecurity.c', 'storage/ipc/ipci.c', 'tcop/utility.c',
    'utils/adt/selfuncs.c', 'utils/cache/lsyscache.c', 'utils/error/elog.c',
    'utils/fmgr/fmgr.c', 'utils/init/miscinit.c',
}


def strip_comments(text):
    """Keep line coordinates while removing comments that can mimic declarations."""
    return re.sub(r'/\*.*?\*/|//[^\n]*',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()),
                  text, flags=re.S)


def parse_header(raw, path):
    text = strip_comments(raw)
    typedefs = {}
    pattern = r'\btypedef\s+[^;{}]*?\(\s*\*\s*(\w*hook\w*)\s*\)\s*\([^;{}]*?\)\s*;'
    for match in re.finditer(pattern, text, re.I | re.S):
        typedefs[match[1]] = (' '.join(match[0].split()), text[:match.start()].count('\n') + 1)
    hooks = []
    for match in re.finditer(r'\bextern\s+(?:PGDLLIMPORT\s+)?(\w*hook\w*)\s+(\w+)\s*;', text, re.I):
        typename, name = match.groups()
        if typename not in typedefs:
            raise ValueError(f'{path}: missing function-pointer typedef {typename} for {name}')
        signature, type_line = typedefs[typename]
        hooks.append(dict(name=name, typename=typename, signature=signature,
                          path=path, line=text[:match.start()].count('\n') + 1,
                          type_line=type_line, declaration=' '.join(match[0].split())))
    return hooks


def unpack_sources(archive, destination):
    """Extract only regular source files; do not follow archive paths or symlinks."""
    for member in archive:
        parts = Path(member.name).parts
        if not member.isfile() or len(parts) < 3 or '..' in parts:
            continue
        relative = Path(*parts[1:])
        if not (str(relative).startswith('src/include/') and relative.suffix == '.h' or
                str(relative).startswith('src/backend/') and relative.suffix == '.c'):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.extractfile(member).read())
    (destination / '.complete').write_text('1\n')


def tree_from_api(cache, revision, destination, source_repo):
    """Reuse matching local Git blobs; fetch changed files by immutable SHA.

    This avoids downloading a whole source archive when an older PostgreSQL
    checkout is available. The recursive upstream tree is the complete file
    inventory, and every transported file is verified against its Git blob ID.
    """
    cache.mkdir(parents=True, exist_ok=True)
    manifest = cache / (revision + '.tree.json')
    if not manifest.exists():
        partial = manifest.with_suffix('.partial')
        subprocess.run(['curl', '--fail', '--location', '--compressed', '--silent', '--show-error',
                        '--max-time', '90', '--retry', '2',
                        f'https://api.github.com/repos/postgres/postgres/git/trees/{revision}?recursive=1',
                        '-o', str(partial)], check=True)
        partial.replace(manifest)
    tree = json.loads(manifest.read_text())
    if tree.get('truncated') or not tree.get('tree'):
        raise ValueError(f'Incomplete upstream source inventory: {manifest}')
    entries = [e for e in tree['tree'] if e['type'] == 'blob' and
               ((e['path'].startswith('src/include/') and e['path'].endswith('.h')) or
                e['path'].removeprefix('src/backend/') in IMPLEMENTATIONS)]
    batch = subprocess.run(['git', '-C', str(source_repo), 'cat-file', '--batch'],
                           input=''.join(e['sha'] + '\n' for e in entries).encode(),
                           capture_output=True, check=True)
    stream = io.BytesIO(batch.stdout)
    missing = []

    def save(entry, data):
        digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if digest != entry['sha']:
            raise ValueError(f'Git blob checksum mismatch: {entry["path"]}@{revision}')
        target = destination / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    for entry in entries:
        header = stream.readline().decode().strip().split()
        if len(header) == 2 and header[1] == 'missing':
            missing.append(entry)
        else:
            if len(header) != 3 or header[1] != 'blob' or header[0] != entry['sha']:
                raise ValueError(f'Unexpected Git batch header: {header}')
            data = stream.read(int(header[2]))
            if stream.read(1) != b'\n':
                raise ValueError('Invalid Git batch boundary')
            save(entry, data)

    def download(entry):
        target = destination / entry['path']
        if target.exists():
            data = target.read_bytes()
            digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if digest == entry['sha']:
                return
        response = subprocess.run(['curl', '--fail', '--location', '--compressed', '--silent', '--show-error',
                                   '--connect-timeout', '10', '--max-time', '25',
                                   '--user-agent', 'PGSQL.CC source builder',
                                   f'https://raw.githubusercontent.com/postgres/postgres/{revision}/{entry["path"]}'],
                                  capture_output=True)
        if response.returncode == 0:
            save(entry, response.stdout)
        else:
            fallback = subprocess.run(['curl', '--fail', '--location', '--compressed', '--silent', '--show-error',
                '--connect-timeout', '10', '--max-time', '60', '--retry', '1',
                '--user-agent', 'PGSQL.CC source builder',
                f'https://api.github.com/repos/postgres/postgres/git/blobs/{entry["sha"]}'],
                capture_output=True, check=True)
            blob = json.loads(fallback.stdout)
            if blob.get('encoding') != 'base64' or blob.get('sha') != entry['sha']:
                raise ValueError(f'Unexpected upstream blob: {entry["path"]}')
            save(entry, base64.b64decode(blob['content']))
    print(f'{revision[:8]}: reuse {len(entries)-len(missing)} local blobs, fetch {len(missing)}', file=sys.stderr)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download, missing))
    (destination / '.complete').write_text('1\n')
    return destination


def ensure_source(cache, revision, fetch=False, source_repo=None):
    destination = cache / revision
    if (destination / '.complete').exists():
        return destination
    if source_repo:
        archive = subprocess.run(['git', '-C', str(source_repo), 'archive', '--prefix=postgres/',
                                  revision, 'src/include', 'src/backend'], capture_output=True)
        if archive.returncode == 0:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as bundle:
                unpack_sources(bundle, destination)
            return destination
        if fetch:
            return tree_from_api(cache, revision, destination, source_repo)
    archive = cache / (revision + '.tar.gz')
    if not archive.exists():
        if not fetch:
            raise ValueError(f'Missing source tree {revision}; use --fetch or --source-repo')
        cache.mkdir(parents=True, exist_ok=True)
        partial = archive.with_suffix('.partial')
        subprocess.run(['curl', '--fail', '--location', '--compressed', '--silent', '--show-error',
                        '--max-time', '900', '--retry', '2',
                        f'https://codeload.github.com/postgres/postgres/tar.gz/{revision}',
                        '-o', str(partial)], check=True)
        partial.replace(archive)
    with tarfile.open(archive, 'r:gz') as bundle:
        unpack_sources(bundle, destination)
    return destination


def scan_tree(tree):
    hooks = {}
    headers = sorted((tree / 'src/include').rglob('*.h'))
    for path in headers:
        relative = path.relative_to(tree).as_posix()
        for hook in parse_header(path.read_text(), relative):
            if hook['name'] in hooks:
                raise ValueError(f'Duplicate hook declaration: {hook["name"]}')
            hooks[hook['name']] = hook
    # Match exact identifiers, so e.g. planner_hook and planner_hook_type do
    # not become each other's evidence. Declaration and use are independent.
    mentions = {name: [] for name in hooks}
    pattern = re.compile(r'\b(?:' + '|'.join(re.escape(n) for n in hooks) + r')\b')
    for path in sorted((tree / 'src/backend').rglob('*.c')) + headers:
        raw = path.read_text()
        text = strip_comments(raw)
        relative = path.relative_to(tree).as_posix()
        for lineno, line in enumerate(text.splitlines(), 1):
            for name in set(pattern.findall(line)):
                mentions[name].append((relative, lineno, line.strip()))
    for name, hook in hooks.items():
        initializer = re.compile(r'\b' + re.escape(hook['typename']) + r'\s+' +
                                 re.escape(name) + r'\s*=\s*(\w+)\s*;')
        definitions = [(p, n, line) for p, n, line in mentions[name]
                       if initializer.search(line)]
        if len(definitions) != 1:
            raise ValueError(f'{name}: expected one initialized definition, got {definitions}')
        hook['definition'] = definitions[0]
        hook['initial_value'] = initializer.search(definitions[0][2])[1]
        # Hook invocations may use (*hook)(...) as well as hook(...).
        calls = [(p, n, line) for p, n, line in mentions[name]
                 if re.search(r'(?:\b' + re.escape(name) + r'\s*\(|\(\s*\*\s*' +
                              re.escape(name) + r'\s*\)\s*\()', line)]
        if not calls:
            raise ValueError(f'{name}: no core call site found')
        hook['calls'] = calls
    return hooks, len(headers)


def release(major, ref, revision):
    return dict(major=major, label={'19': '19 Beta 4', '20': '20 devel'}.get(major, major),
                revision=revision, ref=ref,
                channel='historical' if int(major) <= 13 else
                        'preview' if major == '19' else 'devel' if major == '20' else 'stable')


def evidence(tree, revision, path, line, label):
    return dict(label=label, path=path,
                url=f'https://github.com/postgres/postgres/blob/{revision}/{path}#L{line}',
                sha256=hashlib.sha256((tree / path).read_bytes()).hexdigest())


def build(cache, fetch=False, source_repo=None):
    from pgweb.wiki.hook_data import HOOKS, notes_for, related_for
    with ThreadPoolExecutor(max_workers=3) as pool:
        trees = dict(zip(REVISIONS, pool.map(
            lambda pair: ensure_source(cache, pair[1], fetch, source_repo), REVISIONS.values())))
    items, inventory, releases = {}, {}, []
    for major, (ref, revision) in REVISIONS.items():
        tree = trees[major]
        hooks, header_count = scan_tree(tree)
        build_release = release(major, ref, revision)
        releases.append(build_release)
        inventory[major] = dict(header_count=header_count, hook_count=len(hooks),
                                names=sorted(hooks))
        for name, hook in sorted(hooks.items()):
            if name not in HOOKS:
                raise ValueError(f'Missing Chinese editorial content for {name} (PG{major})')
            title, category, summary, detail = HOOKS[name]
            item = items.setdefault(name, dict(slug=name.lower(), name=name, name_zh=title,
                        category=category, summary=summary, aliases=[], versions={}))
            definition_path, definition_line, _ = hook['definition']
            sources = [evidence(tree, revision, hook['path'], hook['type_line'], '接口声明'),
                       evidence(tree, revision, definition_path, definition_line, '核心定义')]
            call_paths = []
            for path, lineno, _ in hook['calls']:
                if path not in call_paths:
                    sources.append(evidence(tree, revision, path, lineno, '调用位置'))
                    call_paths.append(path)
            sections = notes_for(name, major)
            sections.append(dict(title='调用位置', paragraphs=[
                f'{path}:{lineno}' for path, lineno, _ in hook['calls']]))
            item['versions'][major] = dict(description=[detail],
                signature=hook['signature'] + '\n' + hook['declaration'],
                facts=[dict(label='接口类型', value=hook['typename']),
                       dict(label='声明头文件', value=hook['path']),
                       dict(label='调用阶段', value=category),
                       dict(label='初始值', value='NULL（未安装钩子）' if hook['initial_value'] == 'NULL'
                            else hook['initial_value'])],
                sections=sections, sources=sources, related=related_for(name, major), release=build_release)
        print(f'PG{major}: {len(hooks)} hooks in {header_count} headers', file=sys.stderr)
    unknown = set(HOOKS) - set(items)
    if unknown:
        raise ValueError(f'Editorial names absent from every sampled version: {sorted(unknown)}')
    return dict(format=1, kind='hook', scope=SCOPE, releases=releases, inventory=inventory,
                items=sorted(items.values(), key=lambda item: (item['category'], item['slug'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / 'tmp/hooks-sources')
    parser.add_argument('--source-repo', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/wiki/hooks.json')
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    payload = build(args.cache, args.fetch, args.source_repo)
    if args.check:
        if json.loads(args.output.read_text()) != payload:
            raise SystemExit(f'{args.output}: snapshot differs; rebuild it')
        print(f'{args.output}: verified {len(payload["items"])} hooks')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        print(f'{args.output}: wrote {len(payload["items"])} hooks')


if __name__ == '__main__':
    main()
